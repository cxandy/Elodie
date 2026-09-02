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
        self._last_stats = None  # (total files, groups, removable copies)
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

        self.btn_cancel = QPushButton("取消扫描")
        self.btn_cancel.clicked.connect(self._cancel_scan)
        self.btn_cancel.setVisible(False)
        scan_row.addWidget(self.btn_cancel)
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
        self.btn_select_all = QPushButton("全选可移动副本")
        self.btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(self.btn_select_all)

        self.btn_delete = QPushButton("移动勾选的副本到 重复照片")
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
        self._last_stats = None
        self.btn_scan.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("正在收集文件...")

        self.worker = DuplicateWorker(directory, same_dir_only=self.chk_same_dir.isChecked())
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self.status_label.setText)
        self.worker.stats.connect(self._on_stats)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _cancel_scan(self):
        if self.worker is not None and self.worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("正在取消...")
            self.status_label.setText("正在取消扫描，请稍候...")
            self.worker.cancel()

    def _on_stats(self, total, groups, removable):
        self._last_stats = (total, groups, removable)

    def _on_progress(self, scanned, total):
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(scanned)
        self.status_label.setText(f"正在计算哈希: {scanned} / {total}")

    def _on_finished(self, groups):
        self.btn_scan.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        self.groups = groups

        # A cancelled scan produced partial (possibly empty) results; do not
        # re-enable the tree or claim a normal "scan complete".
        was_cancelled = self.worker is not None and self.worker.is_cancelled()

        total, group_count, removable = self._last_stats or (0, len(groups), 0)

        if was_cancelled:
            self.status_label.setVisible(True)
            self.status_label.setText(f"扫描已取消。已完成 {total} 个文件。")
            return

        if not groups:
            self.status_label.setVisible(True)
            self.status_label.setText(
                f"扫描完成：共 {total} 个文件，未发现重复文件。"
            )
            return

        self._populate(groups)
        self.status_label.setVisible(True)
        checked = self._checked_count()
        self.status_label.setText(
            f"扫描完成：共 {total} 个文件，发现 {group_count} 组重复，"
            f"可移动副本 {removable} 个，已勾选 {checked} 个。"
        )

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

    def _checked_count(self):
        count = 0
        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                if group_item.child(j).checkState(0) == Qt.CheckState.Checked:
                    count += 1
        return count

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

        # --- 安全移动 ---
        # 取所有勾选文件的共同基目录，保证子目录结构保持不变
        try:
            base_dir = os.path.commonpath(to_delete)
        except ValueError:
            # 跨驱动器无法求共同路径，退回第一个文件的目录
            base_dir = os.path.dirname(to_delete[0])

        # 目标目录：放到文件所在盘符的根目录下，方便查找
        drive = os.path.splitdrive(base_dir)[0]
        if drive:
            target_dir = os.path.join(drive + os.sep, "重复照片")
        else:
            # 无盘符（网络路径等）时退回原位置
            target_dir = os.path.join(base_dir, "重复照片")
        os.makedirs(target_dir, exist_ok=True)

        # 移动日志路径（用于断点续传）
        log_path = os.path.join(target_dir, "move_log.json")

        # 读取已有日志，恢复已移动的文件记录
        moved_set = set()
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    moved_set = set(data.get("moved", []))
            except Exception:
                moved_set = set()

        # 过滤掉已移动的文件，剩下的才是本次要处理的
        remaining = []
        for path in to_delete:
            # 子目录保留原文件的全路径（相对盘符根目录）
            if drive:
                rel = os.path.relpath(path, drive + os.sep)
            else:
                rel = os.path.relpath(path, base_dir)
            if rel in moved_set:
                moved_set.add(path)
            else:
                remaining.append((path, rel))

        if not remaining:
            QMessageBox.information(self, "提示", "所有已选文件均已在之前移动过，无需重复操作。")
            return

        # 确认弹窗
        reply = QMessageBox.question(
            self, "确认移动",
            f"确定将 {len(remaining)} 个重复副本移动到 {os.path.basename(target_dir)} 吗？\n"
            f"（保持子目录结构；中途如意外可用日志恢复）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 移动循环
        failed = []
        for idx, (path, rel) in enumerate(remaining, 1):
            try:
                target_path = os.path.join(target_dir, rel)
                # 目标已存在时跳过，防止覆盖重要文件
                if os.path.exists(target_path):
                    failed.append((path, "目标已存在，已跳过"))
                    continue
                # 确保目标目录存在
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                # 执行移动
                shutil.move(path, target_path)
                moved_set.add(path)

                # 每 50 个文件刷新日志，避免中途意外丢失进度
                if len(moved_set) % 50 == 0:
                    self._flush_log(log_path, moved_set)
            except Exception as e:
                failed.append((path, str(e)[:60]))

            self.status_label.setVisible(True)
            self.status_label.setText(f"正在移动 {idx} / {len(to_delete)}")

        # 最后一次刷新日志
        self._flush_log(log_path, moved_set)

        # 统计并显示结果（含勾选数量）
        moved_count = len(remaining) - len(failed)
        checked_count = len(to_delete)
        self.status_label.setVisible(True)
        if failed:
            detail_text = "；".join(reason for _, reason in failed[:2])
            self.status_label.setText(
                f"勾选 {checked_count} 个，已移动 {moved_count} / {len(remaining)}，失败 {len(failed)} 个"
            )
            QMessageBox.warning(
                self, "移动完成（部分失败）",
                f"勾选 {checked_count} 个，成功移动 {moved_count} 个，失败 {len(failed)} 个。\n"
                f"失败原因：{detail_text}\n"
                f"失败的文件将保留在原位置，可处理后重试。",
            )
        else:
            self.status_label.setText(
                f"勾选 {checked_count} 个，已移动 {moved_count} / {len(remaining)}"
            )

        # 移除树中已成功移动的条目（失败的保留以便用户处理）
        failed_paths = {path for path, _ in failed}
        moved_paths = [path for path, _ in remaining if path not in failed_paths]
        self._remove_deleted_from_tree(moved_paths)

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
