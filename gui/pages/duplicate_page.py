"""Duplicate page - scan a directory and manage duplicate files."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.workers.duplicate_worker import DuplicateWorker


class DuplicatePage(QWidget):
    """Scan a directory for content-identical photos/videos.

    Files are grouped by content hash. In each group one file is suggested
    as the one to keep (first found); the rest are pre-selected as removable
    candidates. The user can adjust the selection and then send the checked
    copies to the recycle bin.
    """

    def __init__(self):
        super().__init__()
        self.worker = None
        self.groups = []  # list of [hash, [paths]]
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("重复照片扫描")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        scan_group = QGroupBox("扫描目录")
        scan_row = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("选择要扫描的目录...")
        self.dir_input.setReadOnly(True)
        scan_row.addWidget(self.dir_input)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self._browse)
        scan_row.addWidget(self.btn_browse)

        self.btn_scan = QPushButton("开始扫描")
        self.btn_scan.clicked.connect(self._scan)
        scan_row.addWidget(self.btn_scan)
        scan_group.setLayout(scan_row)
        layout.addWidget(scan_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["保留", "文件路径"])
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.tree, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_select_all = QPushButton("全选可删副本")
        self.btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(self.btn_select_all)

        self.btn_delete = QPushButton("删除勾选的副本（回收站）")
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)
        layout.addLayout(btn_row)

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(self, "选择扫描目录")
        if directory:
            self.dir_input.setText(directory)

    def _scan(self):
        directory = self.dir_input.text().strip()
        if not directory or not os.path.isdir(directory):
            QMessageBox.warning(self, "提示", "请先选择一个有效的目录。")
            return

        self.tree.clear()
        self.groups = []
        self.btn_scan.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("正在收集文件...")

        self.worker = DuplicateWorker(directory)
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, scanned, total):
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(scanned)
        self.status_label.setText(f"正在计算哈希: {scanned} / {total}")

    def _on_finished(self, groups):
        self.btn_scan.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        self.groups = groups

        if not groups:
            self.status_label.setVisible(True)
            self.status_label.setText("未发现重复文件。")
            return

        self._populate(groups)

    def _populate(self, groups):
        for digest, paths in groups:
            group_item = QTreeWidgetItem([f"{len(paths)} 个重复", ""])
            group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for i, path in enumerate(paths):
                file_item = QTreeWidgetItem([str(len(paths) - i - 1), path])
                file_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                # Suggest keeping the first; pre-check the rest as removable
                # candidates. Lowest-numbered copies are the ones to delete.
                file_item.setCheckState(
                    0, Qt.CheckState.Unchecked if i == 0 else Qt.CheckState.Checked
                )
                group_item.addChild(file_item)
            self.tree.addTopLevelItem(group_item)
            group_item.setExpanded(True)

    def _select_all(self):
        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                if j != 0:
                    child.setCheckState(0, Qt.CheckState.Checked)

    def _delete_selected(self):
        to_delete = []
        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                # PySide6: checkState returns CheckState enum; compare with enum
                if child.checkState(0) == Qt.CheckState.Checked:
                    raw_path = child.text(1)
                    # Normalize path: fix slashes and convert to absolute
                    clean_path = os.path.abspath(os.path.normpath(raw_path))
                    to_delete.append(clean_path)

        if not to_delete:
            QMessageBox.information(self, "提示", "未勾选任何副本。")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定将 {len(to_delete)} 个重复副本移到回收站吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from send2trash import send2trash as _send2trash
        except Exception:
            QMessageBox.critical(self, "错误", "无法加载 send2trash。")
            return

        deleted = 0
        failed = []
        failed_details = []
        for path in to_delete:
            try:
                if os.path.isfile(path):
                    _send2trash(path)
                    deleted += 1
            except FileNotFoundError:
                failed.append(path)
                failed_details.append(f"文件未找到: {os.path.basename(path)}")
            except PermissionError:
                failed.append(path)
                failed_details.append(f"权限不足: {os.path.basename(path)}")
            except Exception as e:
                failed.append(path)
                failed_details.append(f"错误: {type(e).__name__}: {str(e)[:50]}")

        self._remove_deleted_from_tree(to_delete)
        self.status_label.setVisible(True)
        if failed:
            # Show first 2 failure details
            detail_text = "；".join(failed_details[:2])
            self.status_label.setText(
                f"已移除 {deleted} 个副本，失败：{detail_text}" + 
                (f"，共{len(failed)}个" if len(failed) > 2 else "")
            )
        else:
            self.status_label.setText(f"已移除 {deleted} 个副本")

    def _remove_deleted_from_tree(self, paths_to_remove):
        removed_set = set(paths_to_remove)
        for i in range(self.tree.topLevelItemCount() - 1, -1, -1):
            group_item = self.tree.topLevelItem(i)
            for j in range(group_item.childCount() - 1, -1, -1):
                child = group_item.child(j)
                if child.text(1) in removed_set:
                    group_item.removeChild(child)
            if group_item.childCount() <= 1:
                self.tree.takeTopLevelItem(i)
