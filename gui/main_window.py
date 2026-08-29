"""Main window with sidebar navigation and stacked pages."""
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.pages.config_page import ConfigPage
from gui.pages.duplicate_page import DuplicatePage
from gui.pages.import_page import ImportPage
from gui.pages.preview_page import PreviewPage
from gui.pages.setup_page import SetupPage
from gui.pages.update_page import UpdatePage


class MainWindow(QMainWindow):
    """Main application window with sidebar and content area."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Elodie - 照片管理助手")
        self.setMinimumSize(900, 600)
        self._setup_ui()

        # Check ExifTool on startup
        if not shutil.which('exiftool'):
            self._show_setup_page()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar_widget = self._create_sidebar()
        main_layout.addWidget(self.sidebar_widget)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("color: #ddd;")
        main_layout.addWidget(separator)

        self.stack = QStackedWidget()

        self.setup_page = SetupPage()
        self.setup_page.exiftool_ready.connect(self._on_exiftool_ready)
        self.stack.addWidget(self.setup_page)  # index 0

        self.import_page = ImportPage()
        self.stack.addWidget(self.import_page)  # index 1

        self.update_page = UpdatePage()
        self.stack.addWidget(self.update_page)  # index 2

        self.preview_page = PreviewPage()
        self.stack.addWidget(self.preview_page)  # index 3

        self.config_page = ConfigPage()
        self.stack.addWidget(self.config_page)  # index 4

        self.duplicate_page = DuplicatePage()
        self.stack.addWidget(self.duplicate_page)  # index 5

        main_layout.addWidget(self.stack, 1)

        self.stack.setCurrentIndex(0)

    def _create_sidebar(self):
        sidebar = QWidget()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet(
            "QWidget { background-color: #f5f5f5; }"
        )

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(4)

        logo = QLabel("Elodie")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #333; "
            "padding: 12px 0;"
        )
        layout.addWidget(logo)

        subtitle = QLabel("照片管理助手")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 11px; color: #888; padding-bottom: 12px;")
        layout.addWidget(subtitle)

        self.sidebar_layout = layout
        self.nav_buttons = []
        self.nav_items = []

        self._add_nav_item("  环境配置", 0)
        self._add_nav_item("  导入", 1)
        self._add_nav_item("  更新元数据", 2)
        self._add_nav_item("  文件预览", 3)
        self._add_nav_item("  配置", 4)
        self._add_nav_item("  重复扫描", 5)

        layout.addStretch()

        version = QLabel("v1.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("font-size: 10px; color: #aaa; padding: 8px;")
        layout.addWidget(version)

        return sidebar

    def _add_nav_item(self, label, index):
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setStyleSheet(
            "QPushButton { text-align: left; padding: 10px 16px; "
            "border: none; font-size: 13px; color: #555; }"
            "QPushButton:hover { background-color: #e8e8e8; }"
            "QPushButton:checked { background-color: #e0e0e0; color: #333; "
            "font-weight: bold; border-left: 3px solid #2196F3; }"
        )
        btn.clicked.connect(lambda checked, idx=index: self._switch_page(idx))
        self.sidebar_layout.insertWidget(len(self.nav_items) + 2, btn)
        self.nav_buttons.append(btn)
        self.nav_items.append((label, index))

    def _show_setup_page(self):
        self.stack.setCurrentIndex(0)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == 0)

    def _on_exiftool_ready(self):
        self.stack.setCurrentIndex(1)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == 1)

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
