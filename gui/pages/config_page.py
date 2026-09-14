"""Config page - manage Elodie settings."""
import json
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from elodie import constants
from elodie.config import get_config_file, invalidate_config

PRESETS_FILE = os.path.join(constants.application_directory(), 'presets.json')

DEFAULT_PRESETS = {
    "家庭照片": """[Directory]
year=%Y
month=%m
full_path=%year/%month/%album|"家庭照片"

[File]
time=%H-%M-%S
name=%time-%original_name.%extension
""",
    "旅行照片": """[Directory]
year=%Y
month=%m
location=%city, %state
full_path=%year/%month/%album|%location|"旅行照片"

[File]
time=%H-%M-%S
name=%time-%original_name.%extension
""",
    "简洁模式": """[Directory]
year=%Y
month=%m
full_path=%year/%month

[File]
time=%H-%M-%S
name=%time-%original_name.%extension
""",
    "按日期分类": """[Directory]
date=%Y-%m-%d
full_path=%date

[File]
time=%H-%M-%S
name=%time-%original_name.%extension
""",
    "专业模式": """[Directory]
year=%Y
camera=%camera_make %camera_model
full_path=%year/%camera

[File]
time=%H-%M-%S
name=%time-%original_name-%title.%extension
""",
    "按地点分类": """[Directory]
country=%country
state=%state
city=%city
date=%Y-%m
full_path=%country/%date/%state/%city
full_path_home_country=%country/%state/%date/%city
full_path_home_province=%country/%state/%city/%date

[Home]
country=中国
state=四川省

[File]
time=%Y-%m-%d_%H.%M.%S
name=%time.%extension
""",
}


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
  year       年份文件夹格式
  month      月份文件夹格式
  location   位置文件夹格式

示例:
  [Directory]
  year=%Y
  month=%m
  location=%city, %state
  full_path=%year/%month/%location
  # 结果: 2024/01/北京, 中国

━━━ 家乡分档（按地点分类）━━━

配置 [Home] 后，可按文件相对家乡的国家/省份自动选用不同的目录结构：

  [Home]
  country=中国     # 家乡所在国家
  state=四川省     # 家乡所在省份

三个目录模板（[Directory] 中定义）:
  full_path                 其他国家
                            %country/%date/%state/%city
  full_path_home_country   祖国其他省（同国家、不同省）
                            %country/%state/%date/%city
  full_path_home_province  与家乡同省
                            %country/%state/%city/%date

未配置 [Home] 时只使用 full_path（向后兼容）。

━━━ [File] 文件命名配置 ━━━

控制导入后文件的命名方式。

关键配置项:
  name             文件名模板
  time             时间格式（用于文件名中的 %time）
  capitalization   设为 upper 则文件名大写

占位符:
  %time            时间（由上方 time 定义）
  %original_name   原始文件名
  %title           标题（来自 EXIF）
  %extension       文件扩展名

示例:
  [File]
  time=%H-%M-%S
  name=%time-%original_name-%title.%extension
  # 结果: 10-30-00-img_1234-my-title.jpg

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


class _HomeDetectWorker(QThread):
    """Background thread: read GPS from a photo and reverse-geocode it."""

    finished = Signal(str, str, str)  # country, state, city (or '' on error)
    error = Signal(str)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        from elodie.dependencies import get_exiftool
        from elodie.external.pyexiftool import ExifTool
        from elodie import constants, geolocation

        exe = get_exiftool()
        if not exe:
            self.error.emit("exiftool 未安装，无法读取照片信息。")
            return

        try:
            et = ExifTool(
                executable_=exe,
                addedargs=[
                    u'-config', u'"{}"'.format(constants.exiftool_config),
                ],
            )
            et.start()
            attrs = et.get_metadata(self.filepath)
            et.terminate()
        except Exception as e:
            self.error.emit(f"读取 GPS 失败: {e}")
            return

        if not attrs:
            self.error.emit("照片中未找到 EXIF 元数据。")
            return

        # Prefer the Composite values: they already include the signed
        # hemisphere (N/S, E/W) from the reference tags, unlike the raw
        # EXIF values which are unsigned.
        lat = attrs.get('Composite:GPSLatitude') or attrs.get('EXIF:GPSLatitude')
        lon = attrs.get('Composite:GPSLongitude') or attrs.get('EXIF:GPSLongitude')
        if lat is None or lon is None:
            self.error.emit("照片中没有 GPS 坐标，请选一张在家乡拍的有定位的照片。")
            return

        place = geolocation.place_name(float(lat), float(lon))
        country = (place.get('country') or '').strip()
        state = (place.get('state') or '').strip()
        city = (place.get('city') or place.get('default') or '').strip()

        if not country:
            self.error.emit("无法通过 GPS 坐标识别国家/省份。")
            return

        self.finished.emit(country, state, city)


class ConfigPage(QWidget):
    """Page for managing Elodie configuration."""

    def __init__(self):
        super().__init__()
        self._home_worker = None
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

        cache_group = QGroupBox("缓存管理")
        cache_layout = QVBoxLayout()

        cache_row = QHBoxLayout()
        self.btn_clear_location_cache = QPushButton("清除位置缓存")
        self.btn_clear_location_cache.clicked.connect(
            self._clear_location_cache
        )
        cache_row.addWidget(self.btn_clear_location_cache)

        self.btn_clear_hash_cache = QPushButton("清除文件去重缓存")
        self.btn_clear_hash_cache.clicked.connect(self._clear_hash_cache)
        cache_row.addWidget(self.btn_clear_hash_cache)

        cache_row.addStretch()
        cache_layout.addLayout(cache_row)

        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        home_group = QGroupBox("设置家乡")
        home_layout = QVBoxLayout()

        home_row = QHBoxLayout()
        self.btn_set_home = QPushButton("选择照片并设置家乡...")
        self.btn_set_home.clicked.connect(self._set_home)
        home_row.addWidget(self.btn_set_home)

        home_row.addStretch()
        home_layout.addLayout(home_row)

        home_group.setLayout(home_layout)
        layout.addWidget(home_group)

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

        presets_group = QGroupBox("常用配置")
        presets_layout = QVBoxLayout()

        preset_row = QHBoxLayout()

        self.preset_list = QListWidget()
        self.preset_list.setMaximumHeight(100)
        self.preset_list.currentItemChanged.connect(self._on_preset_selected)
        preset_row.addWidget(self.preset_list)

        preset_btn_col = QVBoxLayout()
        self.preset_name_input = QLineEdit()
        self.preset_name_input.setPlaceholderText("输入配置名称...")
        preset_btn_col.addWidget(self.preset_name_input)

        btn_save_preset = QPushButton("保存为预设")
        btn_save_preset.clicked.connect(self._save_preset)
        preset_btn_col.addWidget(btn_save_preset)

        btn_load_preset = QPushButton("加载选中")
        btn_load_preset.clicked.connect(self._load_preset)
        preset_btn_col.addWidget(btn_load_preset)

        btn_delete_preset = QPushButton("删除预设")
        btn_delete_preset.clicked.connect(self._delete_preset)
        preset_btn_col.addWidget(btn_delete_preset)

        preset_row.addLayout(preset_btn_col)
        presets_layout.addLayout(preset_row)

        presets_group.setLayout(presets_layout)
        layout.addWidget(presets_group)

        self._load_presets()

    def _load_config_content(self):
        config_file = get_config_file()
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8-sig') as f:
                self.config_editor.setText(f.read())
        else:
            default_config = """[Directory]
year=%Y
month=%m
location=%city
full_path=%year/%month/%album|%location|"Unknown Location"

[File]
time=%H-%M-%S
name=%time-%original_name-%title.%extension
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

        # Drop the cached config so subsequent imports use the new settings.
        invalidate_config()

        QMessageBox.information(self, "成功", "配置已保存")

    def _set_home(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择家乡照片", "",
            "照片/视频 (*.jpg *.jpeg *.png *.heic *.dng *.nef *.cr2 *.arw *.mov *.mp4)",
        )
        if not filepath:
            return

        self.btn_set_home.setEnabled(False)

        self._home_worker = _HomeDetectWorker(filepath)
        self._home_worker.finished.connect(self._on_home_detected)
        self._home_worker.error.connect(self._on_home_error)
        self._home_worker.start()

    def _on_home_detected(self, country, state, city):
        self.btn_set_home.setEnabled(True)

        if not os.path.exists(get_config_file()):
            self._save_config()

        from elodie.config import load_config
        config = load_config()
        home = dict(config['Home']) if 'Home' in config else {}
        home['country'] = country
        if state:
            home['state'] = state
        config['Home'] = home

        with open(get_config_file(), 'w', encoding='utf-8-sig') as f:
            config.write(f)
        invalidate_config()

        self._load_config_content()
        QMessageBox.information(
            self, "设置家乡",
            f"已设置家乡: {country}"
            + (f" {state}" if state else "")
            + (f" {city}" if city else "") + "。\n"
            "现在按地点分类时会按家乡分档。",
        )

    def _on_home_error(self, message):
        self.btn_set_home.setEnabled(True)
        QMessageBox.warning(self, "设置家乡失败", message)

    def _clear_cache_file(self, path, description):
        if not os.path.exists(path):
            QMessageBox.information(self, "清除缓存", f"{description}已为空，无需清除。")
            return

        reply = QMessageBox.question(
            self, "确认",
            f"确定要清除{description}吗？\n\n{path}\n\n"
            "清除后相关缓存会重新生成，首次导入可能变慢。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            os.remove(path)
            QMessageBox.information(self, "清除缓存", f"{description}已清除。")
        except OSError as e:
            QMessageBox.warning(self, "清除失败", f"无法清除{description}: {e}")

    def _clear_location_cache(self):
        # Also drop the in-memory bucket cache so a fresh process/import
        # re-resolves place names instead of reusing stale ones.
        from elodie.geolocation import clear_caches
        clear_caches()
        self._clear_cache_file(constants.location_db(), "位置缓存")

    def _clear_hash_cache(self):
        self._clear_cache_file(constants.hash_db(), "文件去重缓存")

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

    def _load_presets(self):
        presets = self._read_presets()
        self.preset_list.clear()
        for name in presets:
            self.preset_list.addItem(name)

    def _read_presets(self):
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8-sig') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return dict(DEFAULT_PRESETS)

    def _write_presets(self, presets):
        config_dir = os.path.dirname(PRESETS_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(PRESETS_FILE, 'w', encoding='utf-8-sig') as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)

    def _on_preset_selected(self, current, previous):
        if current:
            self.preset_name_input.setText(current.text())

    def _save_preset(self):
        name = self.preset_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入配置名称")
            return

        presets = self._read_presets()
        content = self.config_editor.toPlainText()

        if name in presets:
            reply = QMessageBox.question(
                self, "确认",
                f"预设「{name}」已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        presets[name] = content
        self._write_presets(presets)
        self._load_presets()
        QMessageBox.information(self, "成功", f"预设「{name}」已保存")

    def _load_preset(self):
        current = self.preset_list.currentItem()
        if not current:
            QMessageBox.warning(self, "错误", "请先选择一个预设")
            return

        name = current.text()
        presets = self._read_presets()
        if name in presets:
            self.config_editor.setText(presets[name])

            config_file = get_config_file()
            config_dir = os.path.dirname(config_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            with open(config_file, 'w', encoding='utf-8-sig') as f:
                f.write(presets[name])

            invalidate_config()

            QMessageBox.information(self, "成功", f"已加载并应用预设「{name}」")

    def _delete_preset(self):
        current = self.preset_list.currentItem()
        if not current:
            QMessageBox.warning(self, "错误", "请先选择一个预设")
            return

        name = current.text()
        reply = QMessageBox.question(
            self, "确认",
            f"确定要删除预设「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        presets = self._read_presets()
        if name in presets:
            del presets[name]
            self._write_presets(presets)
            self._load_presets()
            QMessageBox.information(self, "成功", f"预设「{name}」已删除")
