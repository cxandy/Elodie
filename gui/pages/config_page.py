"""Config page - manage Elodie settings."""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QGroupBox, QFormLayout,
    QLineEdit, QMessageBox, QScrollArea, QDialog,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

from elodie import constants
from elodie.config import load_config, get_config_file


HELP_TEXT = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  配置文件帮助
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

配置文件路径: ~/.elodie/config.ini

━━━ [Directory] 目录结构配置 ━━━

控制导入后照片的文件夹组织方式。

可用占位符:
  日期类（支持所有 Python strftime 格式）:
    %Y    四位年份，如 2024
    %m    两位月份，如 01-12
    %b    月份缩写，如 Jan-Dec
    %B    月份全名，如 January-December
    %d    两位日期，如 01-31
    %H    小时 (24h)
    %M    分钟
    %S    秒

  位置类:
    %city      城市名（需 EXIF 含 GPS）
    %state     州/省名
    %country   国家名

  相机类:
    %camera_make   相机品牌
    %camera_model  相机型号

  组合类:
    %location  组合位置，如 location=%city, %state
    %date      组合日期，如 date=%Y-%m
    %custom    自定义组合

  回退机制（用 | 分隔）:
    full_path=%album|%location|"未知位置"
    含义: 优先用相册名，没有则用位置，都没有则用"未知位置"

关键配置项:
  full_path  完整文件夹路径模板
  date       日期文件夹格式
  location   位置文件夹格式

示例:
  [Directory]
  date=%Y-%m-%b
  location=%city, %state
  full_path=%date/%location
  # 结果: 2024-01-Jan/北京, 中国

━━━ [File] 文件命名配置 ━━━

控制导入后文件的命名方式。

关键配置项:
  name             文件名模板
  date             日期格式（用于文件名中的 %date）
  capitalization   设为 upper 则文件名大写

占位符:
  %date            日期（由上方 date 定义）
  %original_name   原始文件名
  %title           标题（来自 EXIF）
  %extension       文件扩展名

示例:
  [File]
  date=%Y-%m-%d_%H-%M-%S
  name=%date-%original_name-%title.%extension
  # 结果: 2024-01-15_10-30-00-img_1234-my-title.jpg

━━━ [Exclusions] 排除规则 ━━━

指定不导入的文件或文件夹（正则表达式）。

示例:
  [Exclusions]
  synology_folders=@eaDir
  thumbnails=.thumbnails

━━━ [MapQuest] 地理位置配置 ━━━

用于将 GPS 坐标转换为城市/州名称。

  key                  MapQuest API 密钥
  prefer_english_names 是否优先使用英文名 (True/False)

注意: MapQuest 已弃用，现在默认使用 ExifTool 进行反向地理编码。

━━━ [Plugins] 插件配置 ━━━

启用的插件列表，逗号分隔。

示例:
  [Plugins]
  plugins=googlephotos

"""


class ConfigPage(QWidget):
    """Page for managing Elodie configuration."""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("配置")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        btn_help = QPushButton("帮助")
        btn_help.setStyleSheet(
            "QPushButton { padding: 4px 12px; }"
        )
        btn_help.clicked.connect(self._show_help)
        header.addWidget(btn_help)

        layout.addLayout(header)

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
        self.config_editor.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px;"
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
        layout.addWidget(config_group, 1)

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

    def _load_config_content(self):
        config_file = get_config_file()
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8-sig') as f:
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
        with open(config_file, 'w', encoding='utf-8-sig') as f:
            f.write(content)

        QMessageBox.information(self, "成功", "配置已保存")

    def _show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("配置帮助")
        dlg.setMinimumSize(620, 520)

        dlg_layout = QVBoxLayout(dlg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        help_label = QLabel(HELP_TEXT)
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; "
            "padding: 12px;"
        )
        scroll.setWidget(help_label)
        dlg_layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.close)
        dlg_layout.addWidget(buttons)

        dlg.exec()

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
