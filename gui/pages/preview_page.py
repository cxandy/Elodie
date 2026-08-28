"""Preview page - browse and view media files with EXIF info."""
import io
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTextEdit, QGroupBox,
    QGridLayout, QScrollArea, QFrame,
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
        self._thumb_slots = {}
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(4)
        self._thumb_signals = _ThumbnailSignals(self)
        self._thumb_signals.done.connect(self._on_thumbnail_ready)
        self._spin_angle = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(60)
        self._spin_timer.timeout.connect(self._animate_spinners)
        self._name_font = QFont()
        self._name_font.setPointSizeF(8.0)
        self._font_metrics = QFontMetrics(self._name_font)
        self._name_max_width = 112
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("文件预览")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        btn_open = QPushButton("打开文件夹")
        btn_open.clicked.connect(self._open_folder)
        toolbar.addWidget(btn_open)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)
        self.scroll_area.setWidget(self.grid_widget)
        layout.addWidget(self.scroll_area)

        pager = QHBoxLayout()
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

        layout.addLayout(pager)

        info_group = QGroupBox("EXIF 信息")
        info_layout = QVBoxLayout()
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        self.info_text.setPlaceholderText("选择一个文件查看 EXIF 信息")
        info_layout.addWidget(self.info_text)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

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

    def _render_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._generation += 1
        generation = self._generation
        self._thumb_slots = {}

        start = self._current_page * self._page_size
        end = start + self._page_size
        page_files = self._files[start:end]

        decode_exts = ('jpg', 'jpeg', 'png', 'bmp', 'gif', 'heic')
        raw_exts = ('dng', 'nef', 'arw', 'cr2', 'rw2')

        cols = 4
        for cell, filepath in enumerate(page_files):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.Box)
            frame.setStyleSheet(
                "QFrame { border: 1px solid #ddd; border-radius: 4px; "
                "padding: 4px; }"
                "QFrame:hover { border-color: #2196F3; }"
            )

            vlayout = QVBoxLayout(frame)
            vlayout.setSpacing(4)

            ext = os.path.splitext(filepath)[1][1:].lower()
            if ext in decode_exts:
                spinner = QLabel()
                spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spinner.setFixedSize(120, 120)
                spinner.setPixmap(self._draw_spinner_pixmap(self._spin_angle))
                vlayout.addWidget(spinner, alignment=Qt.AlignmentFlag.AlignCenter)
                self._thumb_slots[cell] = spinner
                self._thread_pool.start(
                    _ThumbnailTask(self._thumb_signals, generation, cell, filepath)
                )
            elif ext in raw_exts:
                icon_label = self._create_media_icon(ext)
                vlayout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
            else:
                icon_label = self._create_media_icon(ext)
                vlayout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

            name_label = QLabel()
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            full_name = os.path.basename(filepath)
            max_w = self._name_max_width
            if full_name and self._font_metrics.horizontalAdvance(full_name) > max_w:
                elided = self._font_metrics.elidedText(
                    full_name, Qt.TextElideMode.ElideMiddle, max_w
                )
                name_label.setText(elided)
            else:
                name_label.setText(full_name)
            name_label.setToolTip(full_name)
            name_label.setStyleSheet("font-size: 11px; color: #333;")
            vlayout.addWidget(name_label)

            frame.mousePressEvent = lambda e, p=filepath: self._show_info(p)

            row = cell // cols
            col = cell % cols
            self.grid_layout.addWidget(frame, row, col)

        self._ensure_spin_timer()

        total = self._total_pages()
        self.page_label.setText(
            f"第 {self._current_page + 1}/{total} 页，共 {len(self._files)} 个文件"
        )
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < total - 1)

        if not self._files:
            self.info_text.setText("未找到文件。请打开一个文件夹。")
            self._spin_timer.stop()

    def _on_thumbnail_ready(self, generation, cell, image_bytes):
        """Replace a spinner with the decoded thumbnail once it's ready.

        ``image_bytes`` is raw image data (JPEG/PNG/BMP/GIF bytes) from the
        worker thread.  We must convert to QPixmap on the main thread.
        """
        if generation != self._generation:
            return
        slot = self._thumb_slots.pop(cell, None)
        if slot is None:
            return
        vlayout = slot.parentWidget().layout()
        if image_bytes is not None:
            pixmap = self._bytes_to_pixmap(image_bytes)
            if pixmap is not None and not pixmap.isNull():
                label = QLabel()
                label.setPixmap(pixmap)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                vlayout.replaceWidget(slot, label)
                label.show()
                slot.deleteLater()
                if not self._thumb_slots:
                    self._spin_timer.stop()
                return
        # fallback: show file-type icon
        ext = os.path.splitext(
            self._files[self._current_page * self._page_size + cell]
        )[1][1:].lower()
        icon_label = self._create_media_icon(ext)
        vlayout.replaceWidget(slot, icon_label)
        icon_label.show()
        slot.deleteLater()
        if not self._thumb_slots:
            self._spin_timer.stop()

    def _draw_spinner_pixmap(self, angle, size=48):
        """Draw a single rotating-arc loading spinner at the given angle."""
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
        """Advance the spinner and repaint all pending thumbnail slots."""
        if not self._thumb_slots:
            self._spin_timer.stop()
            return
        self._spin_angle = (self._spin_angle + 24) % 360
        pm = self._draw_spinner_pixmap(self._spin_angle)
        for slot in list(self._thumb_slots.values()):
            if slot is not None:
                slot.setPixmap(pm)

    def _ensure_spin_timer(self):
        if self._thumb_slots and not self._spin_timer.isActive():
            self._spin_timer.start()

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

    @staticmethod
    def _bytes_to_pixmap(data):
        """Convert raw image bytes to a scaled QPixmap (main thread only)."""
        try:
            if not data:
                return None
            image = QImage.fromData(data)
            if image.isNull():
                return None
            return QPixmap.fromImage(image).scaled(
                QSize(120, 120), Qt.AspectRatioMode.KeepAspectRatio,
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

        size = 120
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
            tri = QPolygonF([
                QPointF(cx - 12, cy - 18),
                QPointF(cx + 16, cy),
                QPointF(cx - 12, cy + 18),
            ])
            painter.drawPolygon(tri)
        else:
            font = QFont()
            font.setPointSize(20)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(fg_color))
            short = ext.upper() if len(ext) <= 4 else ext[:3].upper()
            painter.drawText(QRectF(8, 8, size - 16, size - 16),
                             Qt.AlignmentFlag.AlignCenter, short)

        painter.end()

        label = QLabel()
        label.setPixmap(
            pixmap.scaled(QSize(120, 120), Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setToolTip(f"{label_text} 文件")
        return label

    def _show_info(self, filepath):
        try:
            from elodie.media.base import Base, get_all_subclasses
            from elodie.media.media import Media
            from elodie.media.photo import Photo  # noqa: F401
            from elodie.media.video import Video  # noqa: F401
            from elodie.media.audio import Audio  # noqa: F401
            from elodie.media.text import Text  # noqa: F401

            media = Media.get_class_by_file(filepath, get_all_subclasses())
            if not media:
                self.info_text.setText(f"无法读取文件信息: {filepath}")
                return

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
            self.info_text.setText("\n".join(lines))
        except Exception as e:
            self.info_text.setText(f"读取 EXIF 信息时出错: {e}")
