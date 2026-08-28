"""Preview page - browse and view media files with EXIF info."""
import io
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTextEdit,
    QGridLayout, QScrollArea, QFrame, QStackedWidget,
    QLineEdit,
)
from PySide6.QtCore import (
    Qt, QSize, QRectF, QPointF, QThreadPool, QRunnable,
    QObject, Signal, QTimer,
)
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPolygonF, QBrush, QPen, QFont,
    QFontMetrics,
)


class _ThumbnailSignals(QObject):
    done = Signal(int, int, object)  # generation, cell_index, image-bytes-or-None


class _ThumbnailTask(QRunnable):
    """Decode a single image to raw bytes off the main thread.

    A worker thread must never create Qt GUI objects (QPixmap/QImage),
    so this only performs plain file/CPU decoding and returns raw bytes.
    The GUI thread converts the bytes into a QPixmap.
    """

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
        self._current_page = 0
        self._page_size = 40
        self._generation = 0
        self._pending_cells = {}
        self._thumb_data = {}
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
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)
        self.scroll_area.setWidget(self.grid_widget)
        self._stack.addWidget(self.scroll_area)

        self._stack.setCurrentIndex(1)
        layout.addWidget(self._stack)

        pager = QHBoxLayout()

        btn_open = QPushButton("打开文件夹")
        btn_open.clicked.connect(self._open_folder)
        pager.addWidget(btn_open)

        pager.addStretch()

        self.btn_first = QPushButton("首页")
        self.btn_first.clicked.connect(self._first_page)
        self.btn_first.setEnabled(False)
        pager.addWidget(self.btn_first)

        self.btn_prev = QPushButton("上一页")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_prev.setEnabled(False)
        pager.addWidget(self.btn_prev)

        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pager.addWidget(self.page_label)

        self.btn_next = QPushButton("下一页")
        self.btn_next.clicked.connect(self._next_page)
        self.btn_next.setEnabled(False)
        pager.addWidget(self.btn_next)

        self.btn_last = QPushButton("末页")
        self.btn_last.clicked.connect(self._last_page)
        self.btn_last.setEnabled(False)
        pager.addWidget(self.btn_last)

        pager.addSpacing(12)
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("页码")
        self.page_input.setFixedWidth(60)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self._jump_to_page)
        pager.addWidget(self.page_input)

        self.btn_jump = QPushButton("跳转")
        self.btn_jump.clicked.connect(self._jump_to_page)
        pager.addWidget(self.btn_jump)

        layout.addLayout(pager)

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._load_folder(folder)

    def _load_folder(self, folder):
        from elodie.filesystem import FileSystem
        fs = FileSystem()
        self._files = list(fs.get_all_files(folder))
        self._current_page = 0
        self._render_grid()

    def _total_pages(self):
        if not self._files:
            return 1
        return (len(self._files) + self._page_size - 1) // self._page_size

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_grid()
            self.scroll_area.verticalScrollBar().setValue(0)

    def _next_page(self):
        if self._current_page < self._total_pages() - 1:
            self._current_page += 1
            self._render_grid()
            self.scroll_area.verticalScrollBar().setValue(0)

    def _first_page(self):
        if self._current_page != 0:
            self._current_page = 0
            self._render_grid()
            self.scroll_area.verticalScrollBar().setValue(0)

    def _last_page(self):
        last = self._total_pages() - 1
        if self._current_page != last:
            self._current_page = last
            self._render_grid()
            self.scroll_area.verticalScrollBar().setValue(0)

    def _jump_to_page(self):
        text = self.page_input.text().strip()
        if not text:
            return
        try:
            page = int(text)
        except ValueError:
            return
        total = self._total_pages()
        if page < 1 or page > total:
            return
        self._current_page = page - 1
        self.page_input.clear()
        self._render_grid()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _render_grid(self):
        # Clear old grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._generation += 1
        generation = self._generation
        self._pending_cells = {}
        self._thumb_data = {}

        start = self._current_page * self._page_size
        end = start + self._page_size
        page_files = self._files[start:end]

        decode_exts = ('jpg', 'jpeg', 'png', 'bmp', 'gif', 'heic')

        thumb_w = self._thumb_width
        thumb_h = self._thumb_height
        cols = self._cols
        for col_idx in range(cols):
            self.grid_layout.setColumnMinimumWidth(col_idx, thumb_w + 12)

        for cell, filepath in enumerate(page_files):
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
            if ext in decode_exts:
                self._pending_cells[cell] = filepath
                self._thumb_data[cell] = None
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

            row = cell // cols
            col = cell % cols
            self.grid_layout.addWidget(frame, row, col)

        if self._pending_cells:
            self._stack.setCurrentIndex(0)
            self._spin_angle = 0
            self._spin_timer.start()
            for cell, filepath in self._pending_cells.items():
                self._thread_pool.start(
                    _ThumbnailTask(self._thumb_signals, generation, cell, filepath)
                )
        else:
            self._stack.setCurrentIndex(1)

        total = self._total_pages()
        self.page_label.setText(
            f"第 {self._current_page + 1}/{total} 页，共 {len(self._files)} 个文件"
        )
        has_prev = self._current_page > 0
        has_next = self._current_page < total - 1
        self.btn_first.setEnabled(has_prev)
        self.btn_prev.setEnabled(has_prev)
        self.btn_next.setEnabled(has_next)
        self.btn_last.setEnabled(has_next)
        self.btn_jump.setEnabled(total > 1)

    def _on_thumbnail_ready(self, generation, cell, image_bytes):
        """Receive decoded thumbnail bytes and populate grid when all done."""
        if generation != self._generation:
            return
        if image_bytes is not None:
            self._thumb_data[cell] = image_bytes
        self._pending_cells.pop(cell, None)
        if self._pending_cells:
            return

        # All thumbnails decoded — show grid
        self._spin_timer.stop()
        self._populate_grid(generation)

    def _populate_grid(self, generation):
        """Replace placeholder frames with real thumbnails (main thread)."""
        if generation != self._generation:
            return
        thumb_w = self._thumb_width
        thumb_h = self._thumb_height
        cols = self._cols
        count = self.grid_layout.count()
        for i in range(count):
            item = self.grid_layout.itemAt(i)
            if item is None:
                continue
            frame = item.widget()
            if frame is None:
                continue
            vlayout = frame.layout()
            data = self._thumb_data.get(i)
            if data is not None:
                pixmap = self._bytes_to_pixmap(data)
                if pixmap is not None and not pixmap.isNull():
                    img_label = QLabel()
                    img_label.setPixmap(pixmap)
                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    vlayout.insertWidget(0, img_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self._stack.setCurrentIndex(1)

    def _draw_spinner_pixmap(self, angle, size=None):
        """Draw a single rotating-arc loading spinner at the given angle."""
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
        """Advance the loading spinner animation."""
        self._spin_angle = (self._spin_angle + 24) % 360
        pm = self._draw_spinner_pixmap(self._spin_angle)
        self._loading_label.setPixmap(pm)

    @staticmethod
    def _load_image_bytes(filepath):
        """Read/convert an image file to raw bytes on the worker thread.

        HEIC is decoded to PNG bytes via pillow-heif (CPU-only, safe in a
        worker). Other formats are read as-is; the GUI thread decodes them
        with Qt. Returns bytes, or None on failure.
        """
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
        """Decode an HEIC image to PNG bytes using pillow-heif.

        pillow-heif bundles its own HEVC decoder, so no system codec is
        required. Returns PNG bytes, or None if HEIC support is missing.
        """
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
        """Convert raw image bytes to a scaled QPixmap (main thread only)."""
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
        """Draw a clean media-type icon (video/audio/text) using QPainter."""
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
