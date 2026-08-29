"""Import page - select files and destination for import."""
import os

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.workers.import_worker import ImportWorker


class ImportPage(QWidget):
    """Page for importing photos into the library."""

    def __init__(self):
        super().__init__()
        self.worker = None
        self._files = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("导入照片")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        source_group = QGroupBox("源文件")
        source_layout = QVBoxLayout()

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("选择文件或文件夹...")
        self.source_input.setReadOnly(True)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_input)

        self.btn_select_files = QPushButton("选择文件")
        self.btn_select_files.clicked.connect(self._select_files)
        source_row.addWidget(self.btn_select_files)

        self.btn_select_folder = QPushButton("选择文件夹")
        self.btn_select_folder.clicked.connect(self._select_folder)
        source_row.addWidget(self.btn_select_folder)
        source_layout.addLayout(source_row)

        self.file_list = QTextEdit()
        self.file_list.setReadOnly(True)
        self.file_list.setMaximumHeight(80)
        self.file_list.setPlaceholderText("未选择文件")
        source_layout.addWidget(self.file_list)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        dest_group = QGroupBox("目标目录")
        dest_layout = QHBoxLayout()

        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText("选择目标目录...")
        self.dest_input.setReadOnly(True)
        dest_layout.addWidget(self.dest_input)

        btn_dest = QPushButton("浏览...")
        btn_dest.clicked.connect(self._select_destination)
        dest_layout.addWidget(btn_dest)

        dest_group.setLayout(dest_layout)
        layout.addWidget(dest_group)

        options_group = QGroupBox("选项")
        options_layout = QFormLayout()

        self.chk_album_from_folder = QCheckBox("使用源文件夹名作为相册名")
        options_layout.addRow(self.chk_album_from_folder)

        self.chk_trash = QCheckBox("导入后移除原文件到回收站")
        options_layout.addRow(self.chk_trash)

        self.chk_move = QCheckBox("移动文件（不复制，原文件不保留）")
        self.chk_move.setChecked(True)
        options_layout.addRow(self.chk_move)

        self.chk_keep_filename = QCheckBox("保留原文件名（不按模板重命名）")
        self.chk_keep_filename.setChecked(True)
        options_layout.addRow(self.chk_keep_filename)

        self.chk_clean_empty = QCheckBox("导入后删除空目录")
        self.chk_clean_empty.setChecked(True)
        options_layout.addRow(self.chk_clean_empty)

        self.chk_allow_duplicates = QCheckBox("允许重复导入")
        options_layout.addRow(self.chk_allow_duplicates)

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("例如: 北京, 中国")
        options_layout.addRow("覆盖位置:", self.location_input)

        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("例如: 2024-01-15 10:30:00")
        options_layout.addRow("覆盖时间:", self.time_input)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_import = QPushButton("开始导入")
        self.btn_import.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 8px 24px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self.btn_import.clicked.connect(self._start_import)
        btn_row.addWidget(self.btn_import)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; "
            "padding: 8px 24px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #d32f2f; }"
        )
        self.btn_cancel.clicked.connect(self._cancel_import)
        btn_row.addWidget(self.btn_cancel)

        layout.addLayout(btn_row)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(120)
        self.result_text.setVisible(False)
        layout.addWidget(self.result_text)

        layout.addStretch()

    def _select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择照片文件", "",
            "媒体文件 (*.jpg *.jpeg *.png *.bmp *.dng *.nef *.heic *.arw *.cr2 "
            "*.gif *.rw2 *.mp4 *.mov *.avi *.m4a *.txt);;所有文件 (*)"
        )
        if files:
            self._files = files
            self.source_input.setText(f"已选择 {len(files)} 个文件")
            names = [os.path.basename(f) for f in files[:10]]
            if len(files) > 10:
                names.append(f"...共 {len(files)} 个文件")
            self.file_list.setText("\n".join(names))

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择源文件夹")
        if folder:
            self.source_input.setText(folder)
            from elodie.filesystem import FileSystem
            fs = FileSystem()
            all_files = list(fs.get_all_files(folder))
            self._files = all_files
            self.file_list.setText(
                f"文件夹: {folder}\n共 {len(all_files)} 个媒体文件"
            )

    def _select_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if folder:
            self.dest_input.setText(folder)

    def _start_import(self):
        import shutil
        if not self._files:
            return
        destination = self.dest_input.text()
        if not destination:
            return

        if not shutil.which('exiftool'):
            self.result_text.setVisible(True)
            self.result_text.setStyleSheet("color: #c62828;")
            self.result_text.setText(
                "ExifTool 未安装，无法导入。\n"
                "请先前往「环境配置」页面安装 ExifTool。"
            )
            return

        self.btn_import.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self._files))
        self.progress_label.setVisible(True)
        self.result_text.setVisible(False)

        location = self.location_input.text() or None
        time_str = self.time_input.text() or None

        self.worker = ImportWorker(
            files=self._files,
            destination=destination,
            album_from_folder=self.chk_album_from_folder.isChecked(),
            trash=self.chk_trash.isChecked(),
            allow_duplicates=self.chk_allow_duplicates.isChecked(),
            move=self.chk_move.isChecked(),
            clean_empty=self.chk_clean_empty.isChecked(),
            keep_filename=self.chk_keep_filename.isChecked(),
            location=location,
            time=time_str,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.confirm.connect(self._on_confirm)
        self.worker.start()

    def _on_progress(self, current, total, filename):
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"正在处理 ({current}/{total}): {filename}")

    def _cancel_import(self):
        if self.worker:
            self.worker.cancel()
            self.progress_label.setText("正在取消...")

    def _on_confirm(self, message, filepath):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "确认操作",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if self.worker:
            self.worker.set_confirm_result(reply == QMessageBox.StandardButton.Yes)

    def _on_finished(self, results):
        self.btn_import.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.result_text.setVisible(True)

        success = [r for r in results if r[2]]
        failed = [r for r in results if not r[2]]

        lines = [f"导入完成: {len(success)} 成功, {len(failed)} 失败/跳过"]
        for source, dest, ok in results[:20]:
            name = os.path.basename(source)
            if ok:
                lines.append(f"  [OK] {name} -> {dest}")
            elif dest is None and not ok:
                lines.append(f"  [跳过] {name} (目标已存在或无法处理)")
            else:
                lines.append(f"  [失败] {name}")
        if len(results) > 20:
            lines.append(f"  ...还有 {len(results) - 20} 个结果")

        self.result_text.setText("\n".join(lines))
