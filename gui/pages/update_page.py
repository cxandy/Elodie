"""Update page - update EXIF metadata of selected files."""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QCheckBox, QProgressBar,
    QTextEdit, QGroupBox, QFormLayout, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt

from gui.workers.import_worker import UpdateWorker


class UpdatePage(QWidget):
    """Page for updating photo EXIF metadata."""

    def __init__(self):
        super().__init__()
        self.worker = None
        self._files = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("更新元数据")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        file_group = QGroupBox("选择文件")
        file_layout = QVBoxLayout()

        file_row = QHBoxLayout()
        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_files.clicked.connect(self._add_files)
        file_row.addWidget(self.btn_add_files)

        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_add_folder.clicked.connect(self._add_folder)
        file_row.addWidget(self.btn_add_folder)

        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self._clear_files)
        file_row.addWidget(self.btn_clear)
        file_row.addStretch()
        file_layout.addLayout(file_row)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(100)
        file_layout.addWidget(self.file_list_widget)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        meta_group = QGroupBox("元数据")
        meta_layout = QFormLayout()

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("例如: 北京, 中国")
        meta_layout.addRow("位置:", self.location_input)

        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("例如: 2024-01-15 10:30:00")
        meta_layout.addRow("时间:", self.time_input)

        self.album_input = QLineEdit()
        self.album_input.setPlaceholderText("例如: 2024年旅行")
        meta_layout.addRow("相册:", self.album_input)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("例如: 日落风景")
        meta_layout.addRow("标题:", self.title_input)

        meta_group.setLayout(meta_layout)
        layout.addWidget(meta_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_update = QPushButton("开始更新")
        self.btn_update.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; "
            "padding: 8px 24px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1976D2; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.btn_update.clicked.connect(self._start_update)
        btn_row.addWidget(self.btn_update)

        layout.addLayout(btn_row)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(120)
        self.result_text.setVisible(False)
        layout.addWidget(self.result_text)

        layout.addStretch()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                files.append(path)
            elif os.path.isdir(path):
                from elodie.filesystem import FileSystem
                fs = FileSystem()
                files.extend(fs.get_all_files(path))
        self._add_files_to_list(files)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "媒体文件 (*.jpg *.jpeg *.png *.dng *.nef *.heic *.arw *.cr2 "
            "*.gif *.rw2 *.mp4 *.mov *.avi *.m4a *.txt);;所有文件 (*)"
        )
        self._add_files_to_list(files)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            from elodie.filesystem import FileSystem
            fs = FileSystem()
            files = list(fs.get_all_files(folder))
            self._add_files_to_list(files)

    def _add_files_to_list(self, files):
        for f in files:
            if f not in self._files:
                self._files.append(f)
                self.file_list_widget.addItem(os.path.basename(f))

    def _clear_files(self):
        self._files.clear()
        self.file_list_widget.clear()

    def _start_update(self):
        import shutil
        if not self._files:
            return

        if not shutil.which('exiftool'):
            self.result_text.setVisible(True)
            self.result_text.setStyleSheet("color: #c62828;")
            self.result_text.setText(
                "ExifTool 未安装，无法更新元数据。\n"
                "请先前往「环境配置」页面安装 ExifTool。"
            )
            return

        location = self.location_input.text() or None
        time_str = self.time_input.text() or None
        album = self.album_input.text() or None
        title = self.title_input.text() or None

        if not location and not time_str and not album and not title:
            return

        self.btn_update.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self._files))
        self.progress_label.setVisible(True)
        self.result_text.setVisible(False)

        self.worker = UpdateWorker(
            files=self._files,
            location=location,
            time=time_str,
            album=album,
            title=title,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, current, total, filename):
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"正在处理 ({current}/{total}): {filename}")

    def _on_finished(self, results):
        self.btn_update.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.result_text.setVisible(True)

        success = [r for r in results if r[2]]
        failed = [r for r in results if not r[2]]

        lines = [f"更新完成: {len(success)} 成功, {len(failed)} 失败"]
        for source, dest, ok in results[:20]:
            name = os.path.basename(source)
            if ok:
                lines.append(f"  [OK] {name} -> {dest}")
            else:
                lines.append(f"  [失败] {name}")
        if len(results) > 20:
            lines.append(f"  ...还有 {len(results) - 20} 个结果")

        self.result_text.setText("\n".join(lines))
