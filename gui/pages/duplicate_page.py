"""Duplicate page - scan a directory and manage duplicate files."""
import json
import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

        self.chk_same_dir = QCheckBox("只查找同目录重复文件")
        layout.addWidget(self.chk_same_dir)

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

        self.worker = DuplicateWorker(directory, same_dir_only=self.chk_same_dir.isChecked())
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

        # --- 安全移动开始 ---
        # 目标目录：原目录名_重复文件
        base_dir = os.path.dirname(to_delete[0])
        target_dir = os.path.join(base_dir, "_重复文件")
        os.makedirs(target_dir, exist_ok=True)

        # 移动日志路径
        log_path = os.path.join(target_dir, "move_log.json")

        # 读取已有日志（断点续传）
        moved_set = set()
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    moved_set = set(data.get("moved", []))
            except Exception:
                moved_set = set()

        # 获取相对于基目录的相对路径，用于比较和目标路径构造
        rel_base = base_dir

        # 过滤掉已移动的文件
        remaining = []
        for path in to_delete:
            try:
                rel = os.path.relpath(path, base_dir)
                if rel not in moved_set:
                    remaining.append(path)
                else:
                    moved_set.add(path)  # 确保集合里有这项
            except ValueError:
                remaining.append(path)  # 路径异常，依旧参与移动

        deleted = len(moved_set)

        if not remaining:
            QMessageBox.information(self, "提示", "所有已选文件已 previously 移动过。")
            return

        # 确认弹窗
        reply = QMessageBox.question(
            self, "确认移动",
            f"确定将 {len(remaining)} 个重复副本移动到 {os.path.basename(target_dir)} 吗？\n"
            f"（中途如意外，可用日志恢复，原文件不受影响）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

# 移动循环
        failed = []
        failed_details = []
        count = 0

        for i, path in enumerate(remaining):
            try:
                # 计算相对路径和目标路径
                rel = os.path.relpath(path, base_dir)
                target_path = os.path.join(target_dir, rel)
                # 关键检查：如果目标已存在，跳过防止覆盖重要文件
                if os.path.exists(target_path):
                    failed.append((path, "目标已存在，已跳过"))
                    continue
                # 确保目标目录存在
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                # 执行移动
                shutil.move(path, target_path)
                moved_set.add(path)
                count += 1

                # 每 50 个文件刷新日志，防止丢失
                if (i + 1) % 50 == 0:
                    self._flush_log(log_path, moved_set)

                # 更新进度显示
                self.status_label.setVisible(True)
                self.status_label.setText(f"已移动 {len(moved_set) + len(failed)} / {len(to_delete)}")

            except Exception as e:
                failed.append((path, str(e)[:60]))

        # 最后一次刷新日志
        self._flush_log(log_path, moved_set)

        # 更新进度显示
        self.status_label.setVisible(True)
        if failed:
            detail_text = "；".join(failed_details[:2])
            self.status_label.setText(
                f"已移动 {len(moved_set)} / {len(to_delete)}，失败：{detail_text}" + 
                (f"，共{len(failed)}个" if len(failed) > 2 else "")
            )
        else:
            self.status_label.setText(f"已移动 {len(moved_set)} / {len(to_delete)}")

        # 移除树中的条目
        self._remove_deleted_from_tree(to_delete)

        return

    def _flush_log(self, log_path, moved_set):
        """将移动日志写入磁盘"""
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump({"moved": list(moved_set)}, f, ensure_ascii=False)
        except Exception:
            pass  # 日志写入失败不中断主流程

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
