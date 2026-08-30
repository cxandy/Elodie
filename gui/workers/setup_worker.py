"""Worker thread for ExifTool installation."""
import os
import re
import shutil
import subprocess

from PySide6.QtCore import Signal

from gui.workers.base_worker import BaseWorker


class SetupWorker(BaseWorker):
    """Worker thread that installs ExifTool via a package manager.

    Reads output line by line to provide real-time progress updates.
    """

    progress = Signal(str)
    progress_bar = Signal(int)    # 0-100, -1 for indeterminate
    finished = Signal(bool, str)  # success, message

    def __init__(self, manager, command):
        super().__init__()
        self.manager = manager
        self.command = command

    def run(self):
        self.progress.emit(f"正在通过 {self.manager} 安装 ExifTool ...")
        self.progress_bar.emit(-1)

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(
                self.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )

            output_lines = []
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    line = line.rstrip('\n\r')
                    output_lines.append(line)
                    parsed = self._parse_progress(line)
                    if parsed is not None:
                        self.progress_bar.emit(parsed)
                    if line.strip():
                        self.progress.emit(line.strip())

            proc.wait()
            full_output = '\n'.join(output_lines)

            if proc.returncode == 0:
                path = shutil.which('exiftool')
                if path:
                    self.finished.emit(True, f"ExifTool 安装成功\n路径: {path}")
                else:
                    self.finished.emit(
                        True,
                        "ExifTool 安装完成，但需要重启应用才能识别。\n"
                        "如果问题持续，请检查 PATH 环境变量。"
                    )
            else:
                self.finished.emit(False, f"安装失败 (返回码 {proc.returncode}):\n{full_output[-500:]}")

        except subprocess.TimeoutExpired:
            proc.kill()
            self.finished.emit(False, "安装超时（超过 5 分钟）")
        except Exception as e:
            self.finished.emit(False, f"安装出错:\n{e}")

    def _parse_progress(self, line):
        """Try to extract a percentage from the output line.

        Returns an int 0-100 or None.
        """
        # winget progress: "  ████████████████  12.5 MB / 12.5 MB" or "Downloading  12.5 MB / 12.5 MB"
        m = re.search(r'(\d+(?:\.\d+)?)\s*[MmGgKk]\w*\s*/\s*(\d+(?:\.\d+)?)\s*[MmGgKk]\w*', line)
        if m:
            current = float(m.group(1))
            total = float(m.group(2))
            if total > 0:
                return min(int(current / total * 100), 100)

        # Percentage: "  45%" or "45 %"
        m = re.search(r'(\d{1,3})\s*%', line)
        if m:
            val = int(m.group(1))
            if val <= 100:
                return val

        # choco progress: "[|] 45%"
        m = re.search(r'\[.?\]\s*(\d{1,3})%', line)
        if m:
            val = int(m.group(1))
            if val <= 100:
                return val

        return None


def detect_package_managers():
    """Detect available package managers on the system.

    Returns a list of (name, install_command) tuples.
    """
    managers = []

    if shutil.which('choco'):
        managers.append(('Chocolatey', 'choco install exiftool -y'))

    if shutil.which('scoop'):
        managers.append(('Scoop', 'scoop install exiftool'))

    if shutil.which('winget'):
        managers.append(('winget', 'winget install exiftool'))

    return managers
