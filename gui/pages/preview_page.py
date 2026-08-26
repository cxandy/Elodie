"""Preview page - browse and view media files with EXIF info."""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTextEdit, QGroupBox,
    QGridLayout, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QImage


class PreviewPage(QWidget):
    """Page for previewing media files and their EXIF data."""

    def __init__(self):
        super().__init__()
        self._files = []
        self._current_page = 0
        self._page_size = 40
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

        start = self._current_page * self._page_size
        end = start + self._page_size
        page_files = self._files[start:end]

        cols = 4
        for i, filepath in enumerate(page_files):
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
            if ext in ('jpg', 'jpeg', 'png', 'bmp', 'gif', 'heic', 'dng', 'nef', 'arw', 'cr2'):
                thumb = self._create_thumbnail(filepath)
                if thumb:
                    vlayout.addWidget(thumb, alignment=Qt.AlignmentFlag.AlignCenter)
            else:
                icon_label = QLabel(f"[{ext.upper()}]")
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_label.setStyleSheet("font-size: 24px; color: #666; padding: 20px;")
                vlayout.addWidget(icon_label)

            name_label = QLabel(os.path.basename(filepath))
            name_label.setWordWrap(True)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet("font-size: 11px;")
            vlayout.addWidget(name_label)

            frame.mousePressEvent = lambda e, p=filepath: self._show_info(p)

            row = i // cols
            col = i % cols
            self.grid_layout.addWidget(frame, row, col)

        total = self._total_pages()
        self.page_label.setText(
            f"第 {self._current_page + 1}/{total} 页，共 {len(self._files)} 个文件"
        )
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < total - 1)

        if not self._files:
            self.info_text.setText("未找到文件。请打开一个文件夹。")

    def _create_thumbnail(self, filepath):
        ext = os.path.splitext(filepath)[1][1:].lower()
        if ext in ('heic', 'dng', 'nef', 'arw', 'cr2', 'rw2'):
            return None
        try:
            pixmap = QPixmap(filepath)
            if pixmap.isNull():
                return None
            label = QLabel()
            label.setPixmap(
                pixmap.scaled(QSize(120, 120), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return label
        except Exception:
            return None

    def _show_info(self, filepath):
        try:
            from elodie.media.base import Base, get_all_subclasses
            from elodie.media.media import Media

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
