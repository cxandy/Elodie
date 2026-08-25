"""Setup page - check and install ExifTool."""
import shutil
import subprocess

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QGroupBox, QFrame,
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal

from gui.workers.setup_worker import SetupWorker, detect_package_managers


class SetupPage(QWidget):
    """Page for checking and installing ExifTool."""

    exiftool_ready = Signal()

    def __init__(self):
        super().__init__()
        self.worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("环境配置")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # --- ExifTool status ---
        status_group = QGroupBox("ExifTool 状态")
        status_layout = QVBoxLayout()

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 13px; padding: 4px;")
        status_layout.addWidget(self.status_label)

        self.btn_check = QPushButton("重新检测")
        self.btn_check.clicked.connect(self._check_exiftool)
        status_layout.addWidget(self.btn_check)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # --- Install options ---
        self.install_group = QGroupBox("安装 ExifTool")
        self.install_layout = QVBoxLayout()

        self.managers_info = detect_package_managers()

        if self.managers_info:
            hint = QLabel("检测到以下可用的安装方式，点击按钮即可一键安装：")
            hint.setWordWrap(True)
            self.install_layout.addWidget(hint)

            for name, cmd in self.managers_info:
                row = QHBoxLayout()
                btn = QPushButton(f"使用 {name} 安装")
                btn.setStyleSheet(
                    "QPushButton { padding: 8px 16px; font-weight: bold; }"
                )
                btn.clicked.connect(lambda checked, c=cmd, n=name: self._install(n, c))
                row.addWidget(btn)

                cmd_label = QLabel(cmd)
                cmd_label.setStyleSheet("color: #888; font-family: monospace; font-size: 11px;")
                row.addWidget(cmd_label)
                row.addStretch()
                self.install_layout.addLayout(row)
        else:
            hint = QLabel("未检测到包管理器（Chocolatey / Scoop / winget）。")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #c62828;")
            self.install_layout.addWidget(hint)

        self.install_group.setLayout(self.install_layout)
        layout.addWidget(self.install_group)

        # --- Manual instructions ---
        manual_group = QGroupBox("手动安装")
        manual_layout = QVBoxLayout()

        manual_text = QLabel(
            "如果自动安装不可用，请手动操作：\n\n"
            "1. 访问 https://exiftool.org\n"
            "2. 下载 Windows 64-bit Executable\n"
            "3. 解压后将 exiftool(-k).exe 重命名为 exiftool.exe\n"
            "4. 将 exiftool.exe 和 exiftool_files 文件夹放到一个目录中\n"
            "5. 将该目录添加到系统 PATH 环境变量\n"
            "6. 重启本应用"
        )
        manual_text.setWordWrap(True)
        manual_text.setStyleSheet("font-size: 12px; line-height: 1.6;")
        manual_layout.addWidget(manual_text)

        manual_group.setLayout(manual_layout)
        layout.addWidget(manual_group)

        # --- Progress / result ---
        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet("font-size: 12px; color: #555;")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #ccc; border-radius: 4px; "
            "text-align: center; height: 22px; }"
            "QProgressBar::chunk { background-color: #4CAF50; border-radius: 3px; }"
        )
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setVisible(False)
        self.log_text.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background-color: #f5f5f5; border: 1px solid #ddd;"
        )
        layout.addWidget(self.log_text)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(80)
        self.result_text.setVisible(False)
        layout.addWidget(self.result_text)

        layout.addStretch()

        # Initial check
        self._check_exiftool()

    def _check_exiftool(self):
        path = shutil.which('exiftool')
        if path:
            try:
                r = subprocess.run(
                    ['exiftool', '-ver'],
                    capture_output=True, text=True, timeout=10
                )
                version = r.stdout.strip() if r.returncode == 0 else '未知版本'
            except Exception:
                version = '未知版本'
            self.status_label.setText(
                f"ExifTool 已安装\n"
                f"路径: {path}\n"
                f"版本: {version}"
            )
            self.status_label.setStyleSheet(
                "font-size: 13px; padding: 4px; "
                "color: #2e7d32; font-weight: bold;"
            )
            self.install_group.setVisible(False)
            self.btn_check.setVisible(False)
            self.result_text.setVisible(False)
            self.progress_label.setVisible(False)
            self.exiftool_ready.emit()
        else:
            self.status_label.setText(
                "ExifTool 未安装\n"
                "Elodie 需要 ExifTool 来读写照片的 EXIF 元数据。"
            )
            self.status_label.setStyleSheet(
                "font-size: 13px; padding: 4px; "
                "color: #c62828; font-weight: bold;"
            )
            self.install_group.setVisible(True)
            self.btn_check.setVisible(True)

    def _install(self, manager_name, command):
        self.btn_check.setEnabled(False)
        self._set_install_buttons_enabled(False)

        self.progress_label.setVisible(True)
        self.progress_label.setText(f"正在通过 {manager_name} 安装 ExifTool ...")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate initially
        self.progress_bar.setValue(0)

        self.log_text.setVisible(True)
        self.log_text.clear()

        self.result_text.setVisible(False)

        self.worker = SetupWorker(manager_name, command)
        self.worker.progress.connect(self._on_progress)
        self.worker.progress_bar.connect(self._on_progress_bar)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, msg):
        self.progress_label.setText(msg)
        self.log_text.append(msg)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_progress_bar(self, value):
        if value < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)

    def _on_finished(self, success, message):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.result_text.setVisible(True)
        self.result_text.setText(message)

        if success:
            self.result_text.setStyleSheet("color: #2e7d32;")
            self._check_exiftool()
        else:
            self.result_text.setStyleSheet("color: #c62828;")
            self.btn_check.setEnabled(True)
            self._set_install_buttons_enabled(True)

    def _set_install_buttons_enabled(self, enabled):
        for i in range(self.install_layout.count()):
            item = self.install_layout.itemAt(i)
            if item and item.layout():
                for j in range(item.layout().count()):
                    child = item.layout().itemAt(j)
                    if child and child.widget() and isinstance(child.widget(), QPushButton):
                        child.widget().setEnabled(enabled)
