# Elodie 照片管理助手

一个基于 EXIF 的图像 / 视频整理工具。它以「**不修改文件内容**」为原则，扫描照片的拍摄时间、地理位置等信息，把散乱的照片按照你设定的目录结构（如「国家 / 省, 城市 / 年 / 月」）自动归类，并提供重复照片扫描、元数据更新、可视化预览等功能。本工具带完整的图形界面（GUI），也保留命令行（CLI）能力。

> 本中文文档描述的是当前 **GUI 版** 的功能与行为。原始的英文命令行文档请见 [Readme.md](Readme.md)。

---

## 功能总览

侧边栏共 **6 个页面**：

| 页面 | 功能 |
|---|---|
| 环境配置 | 检测 / 一键安装 ExifTool |
| 导入 | 把照片、视频按 EXIF 信息移动 / 复制到库里并整理目录 |
| 更新元数据 | 批量修改已有文件的位置、时间、相册、标题 |
| 文件预览 | 缩略图网格浏览，点击查看 EXIF 信息，可清理空目录 |
| 配置 | 编辑目录 / 命名模板，管理内置预设 |
| 重复扫描 | 找出内容完全相同的重复照片 / 视频，移入回收站 |

所有耗时操作都在**后台线程**执行，不会卡住界面；每个任务都带进度条与取消按钮。

---

## 安装与首次启动

### 1. 安装 ExifTool

Elodie 依赖 [ExifTool](https://exiftool.org) 来读取 / 写入媒体元数据。首次打开程序时「环境配置」页会自动检测，检测不到时可通过包管理器一键安装，或按屏幕提示手动安装。

**手动安装步骤**：
1. 访问 <https://exiftool.org>
2. 下载 **Windows 64-bit Executable**
3. 解压后把 `exiftool(-k).exe` 重命名为 `exiftool.exe`
4. 把 `exiftool.exe` 和 `exiftool_files` 文件夹放到同一个目录
5. 把该目录加入系统 `PATH` 环境变量
6. 重启本应用

安装成功后，程序可正常读取各类格式的 EXIF。程序本身（GUI EXE）**不内置 exiftool 本体**，但会随包携带其配置文件与离线中文地名库。

### 2. 启动程序

- **打包版**：运行 `dist\Elodie GUI\Elodie GUI.exe`
- **源码版**：`python gui_main.py` 或 `python -m gui`

---

## 导入照片

「导入」页用于把照片 / 视频整理进照片库。

### 步骤
1. **选择源**：点「选择文件」或「选择文件夹」（也可直接拖拽路径）
2. **选择目标目录**：点「浏览...」选择照片库根目录
3. 勾选选项（见下表），可填写「覆盖位置」「覆盖时间」
4. 点 **开始导入**

### 选项说明与默认值

| 选项 | 默认 | 说明 |
|---|---|---|
| 使用源文件夹名作为相册名 | 关 | 把源文件夹名写成 EXIF 相册字段 |
| 导入后移除原文件到回收站 | 关 | 复制模式下是否把原文件送回收站 |
| **移动文件（不复制）** | **开** | 移动原文件（不复制） |
| **保留原文件名** | **开** | 不按模板重命名，只整理目录 |
| 导入后删除空目录 | 开 | 整理后自底向上清理空的源目录 |
| 允许重复导入 | 关 | 是否允许已导入的重复文件再次入库 |

### 重要行为（保持文件原样）

- **默认「移动 + 保留原文件名 + 不写 EXIF」**，整个导入过程**不会修改文件内容字节**：
  - 移动只改目录项，跨盘则原样复制字节 + 删除源；
  - 不调用任何写 EXIF 的方法（`album_from_folder` / `location` / `time` 均默认关闭）；
  - 文件名按原样保留，不套用重命名模板。
- 因此文件的 **SHA-256 内容哈希保持不变**，以后用「重复扫描」仍能识别出它与其他副本的关系。
- 缺 EXIF 的照片：拍摄时间回退到文件系统时间（`min(mtime, ctime)`），无位置则放入 `Unknown Location`。
- **重名不覆盖**：目标目录若已有同名文件，会自动生成 `name (1).jpg`、`name (2).jpg` 等，绝不覆盖已有文件。

### 关于时间戳

- 有 EXIF 拍摄时间的文件，复制入库后会用它校准目标文件的“修改时间”。
- 移动（默认）会保持源文件的修改时间，不会强制对齐到 EXIF 拍摄时间。
- 修改时间、创建时间存在文件系统目录项里（不在文件内容中），请只把它们当作“最近整理时间”，不要当作可靠的拍摄时间。**唯一可靠的拍摄事实是 EXIF / 文件名里的时间戳**——而 Elodie 默认不写 EXIF，目的就是让照片内容保持原样、副本可被可靠识别。

---

## 更新元数据

「更新元数据」页用于修改**已存在**照片的 EXIF 字段，改完会自动按当前目录模板把文件重新归类。

可填写（留空则不修改）：
- **位置**：如「北京, 中国」
- **时间**：如 `2024-01-15 10:30:00` 或 `2024-01-15`
- **相册**：如「2024年旅行」
- **标题**：如「日落风景」

支持多选文件或拖拽文件到列表。注意：更新元数据会**真实修改文件内容（写入 EXIF）**，与「导入」默认行为相反，请确认后再操作。

---

## 文件预览

以 **4 列缩略图网格**浏览照片库：

- 支持缩略图解码：`jpg / jpeg / png / bmp / gif / heic`
- RAW 格式（`dng / nef / arw / cr2 / rw2`）显示橙色格式图标（无法直接预览画质）
- 视频 / 音频 / 文本分别以彩色图标区分
- 点击任意文件弹出「EXIF 信息」对话框：文件名、路径、类型、拍摄时间、相机、相册、标题、经纬度
- 「清理空目录」可删除所选文件夹下的空子目录

---

## 配置目录结构与命名

「配置」页直接编辑 `config.ini`，可调整目录结构和文件命名模板，并可保存 / 加载预设。

### 配置文件位置

- 配置文件：`~/.elodie/config.ini`
- 应用目录默认 `~/.elodie`，可通过环境变量 `ELODIE_APPLICATION_DIRECTORY` 指向其它目录
- 哈希库：`~/.elodie/hash.json`；地名缓存：`~/.elodie/location.json`；预设：`~/.elodie/presets.json`

### 目录模板（`[Directory]`）

默认目录模板为 **`%country/%city/%year/%month`**（国家 / 城市 / 年 / 月 4 层）。可用占位符：

| 占位符 | 含义 |
|---|---|
| `%country` | 国家 |
| `%state` | 省 / 州 |
| `%city` | 城市 |
| `%year` `%month` `%day` | 拍摄的年 / 月 / 日（Python strftime 语法） |
| `%camera_make` `%camera_model` | 相机制造商 / 型号 |
| `%album` | 相册 |

支持 fallback 语法：用 `|` 分隔，取第一个有值的部分；`"..."` 内的双引号表示字面量兜底。例如：

```ini
[Directory]
year=%Y
month=%m
full_path=%year/%month/%album|%location|"Unknown Location"
```

### 文件命名模板（`[File]`）

默认不采用（保留原文件名时）。若要按模板重命名，在 `[File]` 定义 `name`，例如：

```ini
[File]
time=%H-%M-%S
name=%time-%original_name-%title.%extension
```

### 内置预设

「配置」页内置多个预设，可一键加载（加载即写入 config 并立即生效）：

| 预设 | 目录结构 |
|---|---|
| 家庭照片 | `年/月/相册\|"家庭照片"` |
| 旅行照片 | `年/月/相册\|城市, 省\|"旅行照片"` |
| 简洁模式 | `年/月` |
| 按日期分类 | `年-月-日` |
| 专业模式 | `年/相机制造商 型号` |
| **按地点分类** | **`国家/省/市`**；文件名 `年月日_时分秒`（如 `2024-12-05_08.45.17.jpg`） |

> 提示：使用「按地点分类」前，请先确认 `~/.elodie/config.ini` 的 `[Directory]` 是否与此一致。若之前加载的是旧预设，重新加载该预设即可。

### 缺失信息的占位处理

- 某层缺失（如无国家）→ **跳过该层**，不会产生 `Unknown Location/Unknown Location` 这样重复的层级；
- 完全无位置信息 → 落在单个 `Unknown Location`；
- 组合层（如 `%state, %city`）两部分都缺失时折叠成单个 `Unknown Location`。

---

## 地点中文翻译

Elodie 友善地把英文地名翻译成中文，采用**离线优先 + 多级兜底**，且绝不影响导入进程：

1. **ExifTool 官方 GeoLang 中文地名库**（随程序打包的 `zh_cn.pm`，含一万多条中文地名）
2. **复合键查询**（处理同名的市县）
3. **内置补充表**：浙江各市（慈溪、余姚、宁波、杭州等）及全国省份、常见国家
4. **MyMemory 在线机翻兜底**（`langpair=en|zh-CN`）：对拼音类、库中未收录的地名做机翻
5. 任何翻译失败都**悄悄静默**（超时 / 断网 / 无中文结果）→ 保留英文名，**不阻塞导入，离线可用**

---

## 重复照片扫描

「重复扫描」页用于找出因多次复制而散落各处的**内容完全相同**的照片 / 视频（字节级一致）。

### 工作原理
1. 遍历所选目录下支持的媒体文件；
2. **先按文件大小分桶**——只有同样大小的文件才可能重复，不同的直接跳过（大幅减少大文件的哈希 I/O）；
3. 只对同大小的候选文件计算 **SHA-256**，哈希一致即判为重复；
4. 重复文件**分组**显示，每组建议保留一个，其余**默认勾选**为可删副本；
5. 点「删除勾选的副本」把勾选项**移入系统回收站**（可反悔，不是永久删除）。

### 判定标准说明
判定依据是**内容哈希**，只看文件字节：
- 只改文件名 / 移动位置 / 原样复制 → **仍能识别**为副本；
- 一旦改过内容（写过 EXIF、压缩、转格式、改尺寸、旋转重编码）→ **不再视为重复**。

因此强烈建议：**导入时保持文件原样**（默认已如此），这样所有副本字节一致，重复扫描才最准确。

---

## 命令行（CLI）

除 GUI 外，也提供 CLI（`elodie.py`）。常用命令：

```bash
# 导入（复制模式）
./elodie.py import --destination="/path/to/library" /path/to/photos
# 导入并保留文件名、只整理目录
./elodie.py import --destination="/path/to/library" --keep-filename /path/to/photos
# 导入前先预览（不实际改动）
./elodie.py import --dry-run --destination="/path/to/library" /path/to/photos
# 更新元数据
./elodie.py update --location="Las Vegas, NV" /path/to/photo.jpg
# 重建哈希数据库
./elodie.py generate-db --source="/path/to/library"
# 启动 GUI
./elodie.py gui
```

常用选项：
- `--keep-filename` 保留原文件名、只整理目录结构
- `--dry-run` 只显示将要做什么，不做任何修改
- `--location` / `--time` 覆盖位置 / 时间
- `--album-from-folder` 用源文件夹名作为相册名
- `--allow-duplicates` 允许已导入的重复文件再次入库
- `--exclude-regex` 排除匹配的文件 / 目录
- `--debug` 更详细的调试输出

---

## 支持的媒体格式

| 类型 | 扩展名 |
|---|---|
| 照片 | `arw, bmp, cr2, dng, gif, heic, jpeg, jpg, nef, png, rw2` |
| 视频 | `avi, m4v, mov, mp4, mpg, mpeg, 3gp, mts` |
| 音频 | `m4a` |
| 文本 | `txt` |

> RAW 格式（`arw / cr2 / nef / rw2`）Pillow 无法直接解码，但 Elodie 会回退用 ExifTool 读取其 EXIF（拍摄时间、位置、相机等），因此能在导入 / 预览中正常识别。

---

## 打包为 Windows 可执行程序

本程序用 [PyInstaller](https://pyinstaller.org) 打包为 **ONEFOLDER** 目录结构（`dist\Elodie GUI\`），控制台窗口隐藏（GUI）、并裁剪未用的 Qt 模块以减小体积。

### 本地打包

```bash
python -m PyInstaller --noconfirm --clean gui_elodie.spec
```

产物位于 `dist\Elodie GUI\Elodie GUI.exe`。运行时需系统已安装 ExifTool（程序启动时自动检测并引导安装）。

### CI 自动构建

仓库 `.github/workflows/build-gui.yml` 会在 `windows-latest`（Python 3.12）上自动执行打包，并上传产物 / 发布 Release（打 `v*` 标签触发发布）。GitHub Actions 直接安装依赖：`pyinstaller PySide6 send2trash piexif pillow-heif future six requests tabulate`。

---

## 数据与文件一览

| 路径 | 说明 |
|---|---|
| `~/.elodie/config.ini` | 目录 / 命名模板等配置 |
| `~/.elodie/hash.json` | SHA-256 哈希库 |
| `~/.elodie/location.json` | 地名反查缓存 |
| `~/.elodie/presets.json` | 用户保存的预设 |
| `elodie/geolocations/zh_cn.pm` | 随包分发的 GeoLang 中文地名库 |
| `configs/ExifTool_config` | 随包分发的 ExifTool 配置 |
| `gui_elodie.spec` | PyInstaller 打包配置 |
| `.github/workflows/build-gui.yml` | CI 打包工作流 |
