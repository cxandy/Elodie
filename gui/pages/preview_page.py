"""Preview page - browse and view media files with EXIF info."""
import io
import os
from collections import OrderedDict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTextEdit,
    QGridLayout, QScrollArea, QFrame, QStackedWidget,
)
from PySide6.QtCore import (
    Qt, QSize, QRectF, QPointF, QThreadPool, QRunnable,
    QObject, Signal, QTimer,
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPolygonF, QBrush, QPen, QFont,
    QFontMetrics,
)

MAX_THUMB_CACHE = 200


class _ThumbnailSignals(QObject):
    done = Signal(int, int, object)  # generation, cell_index, image-bytes-or-None


class _ThumbnailTask(QRunnable):
    """Decode a single image to raw bytes off the main thread."""

    def __init__(self, signals, generation, index, filepath):
        super().__init__()
        self.signals = signals
        self.generation = generation
        self.index = index
        self.filepath = filepath

    def run(self):
        data = PreviewPage._load_image_bytes(self.filepath)
        self.signals.done.emit(self.generation, self.index, data)


class PreviewPage(QWidget):
    """Page for previewing media files and their EXIF data."""

    def __init__(self):
        super().__init__()
        self._files = []
        self._loaded_count = 0
        self._batch_size = 40
        self._generation = 0
        self._pending_cells = {}
        self._thumb_cache = OrderedDict()  # cell_index → raw image bytes
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(4)
        self._thumb_signals = _ThumbnailSignals(self)
        self._thumb_signals.done.connect(self._on_thumbnail_ready)
        self._spin_angle = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(60)
        self._spin_timer.timeout.connect(self._animate_spinners)
        self._cols = 4
        self._thumb_height = 180
        self._thumb_width = 180
        self._name_font = QFont()
        self._name_font.setPointSizeF(8.0)
        self._font_metrics = QFontMetrics(self._name_font)
        self._loading_more = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("文件预览")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self._stack = QStackedWidget()

        # Page 0: loading overlay
        self._loading_label = QLabel()
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setText("加载中...")
        self._loading_label.setStyleSheet(
            "font-size: 16px; color: #888; padding: 40px;"
        )
        self._stack.addWidget(self._loading_label)

        # Page 1: scroll area with grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)
        self.scroll_area.setWidget(self.grid_widget)
        self._stack.addWidget(self.scroll_area)

        self._stack.setCurrentIndex(1)
        layout.addWidget(self._stack)

        toolbar = QHBoxLayout()

        btn_open = QPushButton("打开文件夹")
        btn_open.clicked.connect(self._open_folder)
        toolbar.addWidget(btn_open)

        btn_clean = QPushButton("清理空目录")
        btn_clean.clicked.connect(self._clean_empty_dirs)
        toolbar.addWidget(btn_clean)

        toolbar.addStretch()

        self._info_label = QLabel()
        self._info_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self._info_label)

        layout.addLayout(toolbar)

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._load_folder(folder)

    def _clean_empty_dirs(self):
        folder = QFileDialog.getExistingDirectory(self, "选择要清理的文件夹")
        if not folder:
            return

        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "确认清理",
            f"将扫描并删除以下目录中的所有空文件夹:\n{folder}\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        empty_dirs = []
        for dirpath, dirnames, filenames in os.walk(folder, topdown=False):
            if not dirnames and not filenames:
                empty_dirs.append(dirpath)

        for d in empty_dirs:
            try:
                os.rmdir(d)
            except OSError:
                pass

        QMessageBox.information(
            self,
            "清理完成",
            f"共删除 {len(empty_dirs)} 个空目录",
        )

    def _load_folder(self, folder):
        from elodie.filesystem import FileSystem
        fs = FileSystem()
        self._files = list(fs.get_all_files(folder))
        self._loaded_count = 0
        self._thumb_cache.clear()
        self._clear_grid()
        self._load_next_batch()
        self._update_info()

    def _clear_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._generation += 1
        self._pending_cells = {}

    def _on_scroll(self, value):
        bar = self.scroll_area.verticalScrollBar()
        if bar.maximum() - value < 300 and not self._loading_more:
            self._load_next_batch()

    def _load_next_batch(self):
        if self._loaded_count >= len(self._files):
            return

        self._loading_more = True
        self._generation += 1
        generation = self._generation
        self._pending_cells = {}

        start = self._loaded_count
        end = min(start + self._batch_size, len(self._files))
        batch = self._files[start:end]

        decode_exts = ('jpg', 'jpeg', 'png', 'bmp', 'gif', 'heic')
        thumb_w = self._thumb_width
        cols = self._cols

        for col_idx in range(cols):
            self.grid_layout.setColumnMinimumWidth(col_idx, thumb_w + 12)

        global_idx = start
        for filepath in batch:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.Box)
            frame.setStyleSheet(
                "QFrame { border: 1px solid #ddd; border-radius: 6px; }"
                "QFrame:hover { border-color: #2196F3; }"
            )

            vlayout = QVBoxLayout(frame)
            vlayout.setContentsMargins(6, 6, 6, 6)
            vlayout.setSpacing(4)

            ext = os.path.splitext(filepath)[1][1:].lower()

            # Check cache
            if global_idx in self._thumb_cache:
                pixmap = self._bytes_to_pixmap(self._thumb_cache[global_idx])
                if pixmap is not None and not pixmap.isNull():
                    img_label = QLabel()
                    img_label.setPixmap(pixmap)
                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    vlayout.addWidget(img_label, alignment=Qt.AlignmentFlag.AlignCenter)
            elif ext in decode_exts:
                self._pending_cells[global_idx] = filepath
            else:
                icon_label = self._create_media_icon(ext)
                vlayout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

            name_label = QLabel()
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            full_name = os.path.basename(filepath)
            if len(full_name) > 20:
                elided = full_name[:9] + '...' + full_name[-9:]
                name_label.setText(elided)
            else:
                name_label.setText(full_name)
            name_label.setToolTip(full_name)
            name_label.setStyleSheet("font-size: 11px; color: #333;")
            name_label.setMaximumWidth(thumb_w)
            vlayout.addWidget(name_label, alignment=Qt.AlignmentFlag.AlignHCenter)

            frame.mousePressEvent = lambda e, p=filepath: self._show_info(p)
            frame.setProperty("cell_idx", global_idx)

            row = global_idx // cols
            col = global_idx % cols
            self.grid_layout.addWidget(frame, row, col)
            global_idx += 1

        self._loaded_count = end
        self._update_info()

        if self._pending_cells:
            self._spin_timer.start()
            for cell, filepath in self._pending_cells.items():
                self._thread_pool.start(
                    _ThumbnailTask(self._thumb_signals, generation, cell, filepath)
                )
        else:
            self._loading_more = False

    def _update_info(self):
        total = len(self._files)
        self._info_label.setText(f"已加载 {self._loaded_count}/{total} 个文件")

    def _on_thumbnail_ready(self, generation, cell, image_bytes):
        if generation != self._generation:
            return
        if image_bytes is not None:
            self._thumb_cache[cell] = image_bytes
            # Evict oldest if cache too large
            while len(self._thumb_cache) > MAX_THUMB_CACHE:
                self._thumb_cache.popitem(last=False)
        self._pending_cells.pop(cell, None)
        if self._pending_cells:
            return
        self._spin_timer.stop()
        self._populate_thumbnails(generation)
        self._loading_more = False

    def _populate_thumbnails(self, generation):
        """Insert decoded thumbnails into the frames that are waiting."""
        if generation != self._generation:
            return
        count = self.grid_layout.count()
        for i in range(count):
            item = self.grid_layout.itemAt(i)
            if item is None:
                continue
            frame = item.widget()
            if frame is None:
                continue
            cell = frame.property("cell_idx")
            if cell is None:
                continue
            data = self._thumb_cache.get(cell)
            if data is None:
                continue
            vlayout = frame.layout()
            # Skip if already has image
            if vlayout.count() > 1:
                first_widget = vlayout.itemAt(0).widget() if vlayout.itemAt(0) else None
                if first_widget and isinstance(first_widget, QLabel) and first_widget.pixmap():
                    continue
            pixmap = self._bytes_to_pixmap(data)
            if pixmap is not None and not pixmap.isNull():
                img_label = QLabel()
                img_label.setPixmap(pixmap)
                img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                vlayout.insertWidget(0, img_label, alignment=Qt.AlignmentFlag.AlignCenter)

    def _draw_spinner_pixmap(self, angle, size=None):
        if size is None:
            size = self._thumb_height
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(size / 2, size / 2)
        painter.rotate(angle)
        painter.translate(-size / 2, -size / 2)
        pen = QPen(QColor('#2196F3'), 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(4, 4, size - 8, size - 8), 0 * 16, 110 * 16)
        painter.end()
        return pm

    def _animate_spinners(self):
        self._spin_angle = (self._spin_angle + 24) % 360
        pm = self._draw_spinner_pixmap(self._spin_angle)
        self._loading_label.setPixmap(pm)

    @staticmethod
    def _load_image_bytes(filepath):
        ext = os.path.splitext(filepath)[1][1:].lower()
        if ext in ('dng', 'nef', 'arw', 'cr2', 'rw2'):
            return None
        try:
            if ext == 'heic':
                return PreviewPage._heic_to_png_bytes(filepath)
            with open(filepath, 'rb') as f:
                data = f.read()
            if not data:
                return None
            return data
        except Exception:
            return None

    @staticmethod
    def _heic_to_png_bytes(filepath):
        try:
            from PIL import Image
            import pillow_heif
            pillow_heif.register_heif_opener()
            with Image.open(filepath) as img:
                img.load()
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                return buffer.getvalue()
        except Exception:
            return None

    def _bytes_to_pixmap(self, data):
        try:
            if not data:
                return None
            image = QImage.fromData(data)
            if image.isNull():
                return None
            return QPixmap.fromImage(image).scaled(
                QSize(self._thumb_width, self._thumb_height),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        except Exception:
            return None

    def _create_media_icon(self, ext):
        video_exts = ('avi', 'm4v', 'mov', 'mp4', 'mpg', 'mpeg', '3gp', 'mts', 'mkv', 'webm', 'wmv')
        audio_exts = ('m4a', 'mp3', 'wav', 'aac', 'flac', 'ogg')
        text_exts = ('txt', 'md', 'log', 'csv', 'json', 'xml')

        if ext in video_exts:
            bg_color, fg_color = QColor('#1976D2'), QColor('#FFFFFF')
            label_text = "VIDEO"
        elif ext in audio_exts:
            bg_color, fg_color = QColor('#388E3C'), QColor('#FFFFFF')
            label_text = "AUDIO"
        elif ext in text_exts:
            bg_color, fg_color = QColor('#757575'), QColor('#FFFFFF')
            label_text = "TEXT"
        elif ext in ('heic', 'dng', 'nef', 'arw', 'cr2', 'rw2'):
            bg_color, fg_color = QColor('#F57C00'), QColor('#FFFFFF')
            label_text = ext.upper()
        else:
            bg_color, fg_color = QColor('#607D8B'), QColor('#FFFFFF')
            label_text = ext.upper()

        size = self._thumb_height
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(QPen(bg_color, 2))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(QRectF(8, 8, size - 16, size - 16), 12, 12)

        if ext in video_exts:
            painter.setPen(QPen(fg_color, 0))
            painter.setBrush(QBrush(fg_color))
            cx, cy = float(size) / 2, float(size) / 2
            s = size / 120.0
            tri = QPolygonF([
                QPointF(cx - 12 * s, cy - 18 * s),
                QPointF(cx + 16 * s, cy),
                QPointF(cx - 12 * s, cy + 18 * s),
            ])
            painter.drawPolygon(tri)
        else:
            font = QFont()
            font.setPointSize(max(16, int(20 * size / 120)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(fg_color))
            short = ext.upper() if len(ext) <= 4 else ext[:3].upper()
            painter.drawText(QRectF(8, 8, size - 16, size - 16),
                             Qt.AlignmentFlag.AlignCenter, short)

        painter.end()

        label = QLabel()
        label.setPixmap(
            pixmap.scaled(QSize(self._thumb_width, self._thumb_height),
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setToolTip(f"{label_text} 文件")
        return label

    def _show_info(self, filepath):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton
        try:
            from elodie.media.base import Base, get_all_subclasses
            from elodie.media.media import Media
            from elodie.media.photo import Photo  # noqa: F401
            from elodie.media.video import Video  # noqa: F401
            from elodie.media.audio import Audio  # noqa: F401
            from elodie.media.text import Text  # noqa: F401

            media = Media.get_class_by_file(filepath, get_all_subclasses())
            if not media:
                text = f"无法读取文件信息: {filepath}"
            else:
                metadata = media.get_metadata()
                lines = [
                    f"文件: {os.path.basename(filepath)}",
                    f"路径: {filepath}",
                    f"类型: {media.__name__}",
                    f"拍摄时间: {metadata.get('date_taken', '未知')}",
                    f"相机: {metadata.get('camera_make', '')} {metadata.get('camera_model', '')}",
                    f"相册: {metadata.get('album', '未知')}",
                    f"标题: {metadata.get('title', '未知')}",
                    f"纬度: {metadata.get('latitude', '未知')}",
                    f"经度: {metadata.get('longitude', '未知')}",
                ]
                text = "\n".join(lines)
        except Exception as e:
            text = f"读取 EXIF 信息时出错: {e}"

        dlg = QDialog(self)
        dlg.setWindowTitle("EXIF 信息")
        dlg.setMinimumWidth(420)
        dlg.setMinimumHeight(260)
        dlg_layout = QVBoxLayout(dlg)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText(text)
        dlg_layout.addWidget(text_edit)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        dlg_layout.addLayout(btn_row)

        dlg.exec()
