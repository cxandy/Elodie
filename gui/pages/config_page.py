"""Config page - manage Elodie settings."""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QGroupBox, QFormLayout,
    QLineEdit, QMessageBox,
)
from PySide6.QtCore import Qt

from elodie import constants
from elodie.config import load_config, get_config_file


class ConfigPage(QWidget):
    """Page for managing Elodie configuration."""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("配置")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        info_group = QGroupBox("应用信息")
        info_layout = QFormLayout()

        self.config_path_label = QLabel(get_config_file())
        self.config_path_label.setWordWrap(True)
        info_layout.addRow("配置文件:", self.config_path_label)

        self.app_dir_label = QLabel(constants.application_directory())
        self.app_dir_label.setWordWrap(True)
        info_layout.addRow("应用目录:", self.app_dir_label)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        config_group = QGroupBox("配置文件内容")
        config_layout = QVBoxLayout()

        self.config_editor = QTextEdit()
        self.config_editor.setPlaceholderText(
            "配置文件不存在。将创建默认配置。"
        )
        self._load_config_content()
        config_layout.addWidget(self.config_editor)

        config_btn_row = QHBoxLayout()

        btn_save = QPushButton("保存配置")
        btn_save.clicked.connect(self._save_config)
        config_btn_row.addWidget(btn_save)

        btn_reload = QPushButton("重新加载")
        btn_reload.clicked.connect(self._load_config_content)
        config_btn_row.addWidget(btn_reload)

        btn_reload.setHidden(True)
        config_btn_row.addStretch()
        config_layout.addLayout(config_btn_row)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        tools_group = QGroupBox("工具")
        tools_layout = QHBoxLayout()

        btn_generate_db = QPushButton("重建哈希数据库")
        btn_generate_db.setToolTip("重新扫描照片库并生成 hash.json")
        btn_generate_db.clicked.connect(self._show_generate_db_info)
        tools_layout.addWidget(btn_generate_db)

        btn_verify = QPushButton("验证文件完整性")
        btn_verify.setToolTip("检查照片库中的文件是否损坏")
        btn_verify.clicked.connect(self._show_verify_info)
        tools_layout.addWidget(btn_verify)

        tools_layout.addStretch()
        tools_group.setLayout(tools_layout)
        layout.addWidget(tools_group)

        layout.addStretch()

    def _load_config_content(self):
        config_file = get_config_file()
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config_editor.setText(f.read())
        else:
            default_config = """[Directory]
date=%Y-%m-%b
location=%city
full_path=%date/%album|%location|"Unknown Location"

[File]
date=%Y-%m-%d_%H-%M-%S
name=%date-%original_name-%title.%extension
"""
            self.config_editor.setText(default_config)

    def _save_config(self):
        config_file = get_config_file()
        config_dir = os.path.dirname(config_file)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        content = self.config_editor.toPlainText()
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(content)

        QMessageBox.information(self, "成功", "配置已保存")

    def _show_generate_db_info(self):
        QMessageBox.information(
            self, "重建数据库",
            "请在终端中运行以下命令:\n\n"
            f"python elodie.py generate-db --source=\"你的照片目录\"\n\n"
            "此操作会重建 ~/.elodie/hash.json 文件。"
        )

    def _show_verify_info(self):
        QMessageBox.information(
            self, "验证文件",
            "请在终端中运行以下命令:\n\n"
            "python elodie.py verify\n\n"
            "此操作会检查所有已导入文件的完整性。"
        )
