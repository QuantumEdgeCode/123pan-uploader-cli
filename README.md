# 123Pan Uploader CLI

<div align="center">

![Python](https://img.shields.io/badge/Python-3.6+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=for-the-badge)
![Last Commit](https://img.shields.io/github/last-commit/OlyMarco/123pan-uploader-cli?style=for-the-badge)
![Issues](https://img.shields.io/github/issues/OlyMarco/123pan-uploader-cli?style=for-the-badge)

**🚀 A high-performance CLI tool for 123Pan Cloud Storage**

[Features](#-features) • [Quick Start](#-quick-start) • [Usage](#-usage-guide) • [Architecture](#-architecture) • [Changelog](#-changelog)

</div>

---

## 📖 Overview

A practical server-side file uploading tool that supports:
- Fast uploading of large files to 123Pan Cloud
- Multi-threaded downloading for direct links
- **Three login methods**: Account/Password, QR Code (WeChat scan), Saved Token
- **Auto token recovery**: re-login with saved password if token expires
- **Comprehensive logging**: command, runtime, and error logs saved locally
- **Bash-style input** with Tab completion and command history
- **Smart duplicate detection** - skip files with same MD5
- **Flexible upload modes** - skip, overwrite, or keep both on conflict

一个实用的服务器端文件上传工具，支持：
- 123云盘大文件快速上传
- 多线程直链下载
- **三种登录方式**：账号密码、扫码登录（微信扫码）、已保存 Token
- **Token 自动恢复**：Token 过期时自动使用已保存的账号密码重新登录
- **完整日志系统**：命令、运行、错误、控制台镜像四类日志本地保存
- **Bash 风格输入**：支持 Tab 补全与命令历史
- **智能去重**：跳过 MD5 相同的文件
- **灵活的冲突处理**：跳过、覆盖或保留两者

> 🤗 Managing checkpoint files across multiple servers requires speed and rapid distribution. 123Pan's unlimited uploads and high-speed downloads perfectly match my requirements.

> 🤗 在多台服务器间管理 checkpoint 文件需要速度和快速分发。123云盘的不限速上传和高速下载完美契合我的需求。

## ✨ Features | 功能特性

| Feature | Description | 说明 |
|---------|-------------|------|
| 🚀 **Fast Upload** | Concurrent multi-file uploads with progress bar | 并发多文件上传，带进度条 |
| 📥 **Multi-threaded Download** | Configurable threads (default: 8) | 可配置线程数（默认8线程） |
| 📋 **Checksum Export** | Export cloud file checksums (Etag/MD5) in TXT / CSV / JSON | 导出云盘文件校验值清单（TXT / CSV / JSON） |
| 🔄 **Smart Deduplication** | Skip files with same name and MD5 hash | 智能去重，跳过同名同MD5文件 |
| ⌨️ **Bash-style Input** | Tab completion, command history, arrow keys | Tab补全、历史记录、方向键 |
| 📊 **Progress Tracking** | Real-time progress bar with upload statistics | 实时进度条和上传统计 |
| 🔐 **Multi-Login Support** | Account/Password, QR Code (WeChat), Token persistence | 账密登录、微信扫码登录、Token持久化 |
| 🔑 **Auto Token Recovery** | Re-login with saved password if token expires | Token过期自动用账密重登 |
| 📝 **Comprehensive Logging** | Command, runtime, error, and console-mirror logs in `logs/` | 命令日志、运行日志、错误日志、控制台镜像 |
| 🔧 **Flexible Modes** | `-f` overwrite, `-k` keep both, `--no-skip` force upload | 多种冲突处理模式 |
| 🧩 **Large-file Uploads** | S3 multipart upload for large files (16MB chunks, aligned with web client); interrupted uploads restart from the beginning | S3分片上传（16MB 分片，与官方 Web 端一致）；不支持断点续传，中断后需重新上传 |

## 📦 Installation | 安装

```bash
git clone https://github.com/OlyMarco/123pan-uploader-cli.git
cd 123pan-uploader-cli
pip install -r requirements.txt
```

**Dependencies | 依赖:**
```
requests>=2.25.0
tqdm>=4.50.0
qrcode>=7.3.1
pyreadline3>=3.1.0  # Optional: For bash-style input on Windows
```

> **Note | 注意**: Linux/macOS 系统自带 readline。Windows 用户需安装 `pyreadline3` 以获得完整的 Bash 风格体验。QR Code 登录需要 `qrcode` 库。

## 🚀 Quick Start | 快速开始

```bash
# Interactive mode (account/password or QR code login) | 交互模式
python app.py

# Force QR code login | 强制扫码登录
python app.py --qr

# Direct upload | 直接上传
python app.py /path/to/file_or_directory

# Upload with options | 带参数上传
python app.py /path/to/file -d "Remote_Folder" -f
```

First run will prompt for login method (account/password or QR code). Credentials are auto-saved to `123pan.txt`.

首次运行会提示选择登录方式（账密或扫码）。凭据自动保存到 `123pan.txt`。

## 🔐 Login Methods | 登录方式

### 1. QR Code Login (WeChat Scan) | 微信扫码登录

```bash
python app.py --qr
```

- Generates a QR code saved to `qrcode.txt` and `qrcode.png`
- Scan with WeChat or 123Pan app
- Click "微信授权登录" (WeChat Authorize) in the scan page
- Token is automatically obtained and saved
- **No username/password required** — QR login saves empty credentials

> ⚠️ QR code expires in ~60 seconds. Scan quickly and authorize immediately!

### 2. Account & Password Login | 账号密码登录

First run without `123pan.txt` will prompt for credentials:

```
No saved credentials found. Please choose a login method:
  1. Account & Password login
  2. QR Code login (scan with WeChat or 123Pan app)
Enter choice (1 or 2): 1
Please enter username: <your_phone_number>
Please enter password: <your_password>
```

### 3. Saved Token (Auto-Verify) | 已保存Token自动验证

If `123pan.txt` exists, the saved token is loaded and verified:

- **Token valid** → proceed directly (no login needed)
- **Token invalid + password saved** → auto re-login with saved credentials (try once)
- **Token invalid + no password (QR login)** → program exits with error message
- **Token invalid + re-login fails** → program exits with error message

### Token Recovery Flow | Token恢复流程

```
123pan.txt exists
    ↓
Load token → get_dir() verify
    ↓
Token valid? ── YES ──→ Continue
    │
    NO
    ↓
Has userName + passWord? ── YES ──→ Re-login (try once)
    │                                    │
    NO                                   ├─ Success → Continue
    ↓                                    └─ Fail → Exit (code=1)
Exit (code=1)
"Please re-run with --qr"
```

## 📘 Usage Guide | 使用指南

### Bash-style Input Features | Bash风格输入

| Feature | Key/Action | 说明 |
|---------|------------|------|
| **Tab Completion** | `Tab` | 自动补全文件路径 |
| **Command History** | `↑`/`↓` | 浏览历史命令 |
| **Line Editing** | `Ctrl+A`/`Ctrl+E`/`Ctrl+U` | 行首/行尾/清空行 |

### Upload Mode Options | 上传模式选项

| Option | Behavior | 说明 |
|--------|----------|------|
| *(默认)* | Skip if same filename **AND** same MD5 exist | 文件名和MD5都相同则跳过 |
| `--no-skip` | Re-upload all, keep both if name conflicts | 全部重传，同名文件保留两者 |
| `-f` | Delete existing and re-upload (overwrite) | 删除已存在文件后重新上传（覆盖） |
| `-k` | Keep both files on conflict (default) | 冲突时保留两者（默认行为） |

### Interactive Mode | 交互模式

```bash
# Basic upload | 基本上传
> /path/to/file

# Upload with custom directory name | 指定远程目录名
> /path/to/dir -d "My_Backup"

# Force overwrite | 强制覆盖
> /path/to/file -f

# Keep both on conflict | 冲突时保留两者
> /path/to/file -k

# Disable MD5 skip, re-upload all | 禁用MD5检查，全部重传
> /path/to/file --no-skip

# Combine flags (order doesn't matter) | 组合使用（顺序无关）
> /path/to/file -f -d "Backup" --no-skip
> /path/to/file -d "Backup" -f
```

> 💡 **Tip**: For paths with spaces, use quotes: `"C:\path with spaces\file"`

### Download Command | 下载命令

```bash
> mget <url> [-o output_file] [-t threads] [-s]

# Examples | 示例
> mget https://example.com/file.zip -o file.zip -t 16  # 16线程下载
> mget https://example.com/file.zip -s                 # 单线程下载
```

### Export Command | 导出命令

导出云盘文件的校验值（Etag/MD5）清单，支持当前目录或递归全部目录，输出 TXT / CSV / JSON：

```bash
> export                          # 当前目录，TXT 表格输出到终端
> export -r                       # 递归导出全部目录
> export -o result.csv            # 保存为 CSV（按扩展名推断格式）
> export -o result.json           # 保存为 JSON
> export -o json                  # 纯格式名 → 自动文件名 123pan_checksums_YYYY-MM-DD.json
> export -r -o json               # 递归 + JSON（完整清单）
> export -r -o csv                # 递归 + CSV
```

> `-o` 自动推断格式（`.csv`/`.json`/`.txt`）；已存在的输出文件不会被覆盖，自动递增 `_01`、`_02`。

### Exit Program | 退出程序

```bash
> 0                    # 方法1: 输入 '0'
> Ctrl+C twice         # 方法2: 2秒内连按两次 Ctrl+C
```

## 🔧 Command Line Arguments | 命令行参数

| Argument | Description | 说明 |
|----------|-------------|------|
| `-f, --force` | Force overwrite existing files | 强制覆盖已存在的文件 |
| `--no-skip` | Disable MD5 check, re-upload all | 禁用MD5检查，全部重传 |
| `-d, --dest` | Specify custom destination directory | 指定远程目录名 |
| `-k, --keep` | Keep both files when names conflict | 同名文件保留两者（默认行为） |
| `--qr, --qrcode` | **Force QR code login** (scan with WeChat) | **强制扫码登录**（微信扫码） |

```bash
python app.py /path/to/directory                    # 默认: 智能跳过
python app.py /path/to/directory -f                 # 强制覆盖
python app.py /path/to/directory --no-skip          # 全部重传
python app.py /path/to/directory -d "Backup" -f     # 自定义目录 + 覆盖
python app.py --qr                                  # 强制扫码登录
python app.py --qr /path/to/file                    # 扫码登录 + 直接上传
```

## 📝 Logging System | 日志系统

All program activities are logged to four directories under `logs/`:

| Directory | Content | 内容 |
|-----------|---------|------|
| `logs/commands/` | User input commands and parsed results | 用户输入命令和解析结果 |
| `logs/runtime/` | Program events (startup, login, upload, download) | 程序事件（启动、登录、上传、下载） |
| `logs/errors/` | Error events, program exits, and uncaught exception tracebacks | 错误事件、程序退出、未捕获异常堆栈 |
| `logs/console/` | Console mirror — every message the user actually saw in the terminal | 控制台镜像 —— 终端上实际看到的每一条消息 |

Log files are named by date: `command_2026-07-05.log`, `runtime_2026-07-05.log`, `error_2026-07-05.log`, `console_2026-07-05.log`

The console mirror is installed automatically by `install_console_mirror()` at startup (wrapping `sys.stdout` / `sys.stderr`), so **no business code has to log each message by hand** — every `print()`, `tqdm.write()`, argparse error, or library message written to stderr lands in `logs/console/`. Console output itself is completely unchanged. tqdm progress-bar frames (redrawn with `\r`, no newline) are treated as transient UI and are not written to the log; the final frame of a bar is kept as one line.

控制台镜像由启动时的 `install_console_mirror()` 自动安装（包装 `sys.stdout` / `sys.stderr`），因此**业务代码无需逐条埋点** —— 任何 `print()`、`tqdm.write()`、argparse 参数错误或第三方库往 stderr 写的内容都会落盘。终端输出行为完全不变。tqdm 进度条帧（用 `\r` 回退重绘、不带换行）属于瞬时 UI，不写入日志；进度条收尾那一帧会保留一行。

Uncaught exceptions are also captured in full: `install_excepthook()` writes the complete traceback to `logs/errors/` while stderr still prints it as usual.

未捕获异常同样完整留存：`install_excepthook()` 会把完整堆栈写入 `logs/errors/`，同时 stderr 照常打印一份。

## 🏗 Architecture | 项目架构

```
123pan-uploader-cli/
├── app.py                          # 主入口 — CLI解析 + 交互模式 + 登录管理
├── tosasitill_123pan/
│   ├── class123.py                 # API客户端 — 登录/Token验证/文件列表/上传/下载
│   └── config.py                   # 配置中心 — API端点URL + 超时/分片/日志参数
├── utils/
│   ├── mpush.py                    # 上传引擎 — MD5去重 + S3分片上传 + 并发
│   ├── mget.py                     # 下载引擎 — 多线程分块下载
│   ├── command_handler.py          # 命令解析 — 路径/标志分离 + argparse集成
│   ├── input_handler.py            # 输入处理 — readline配置 + 路径补全
│   ├── qr_login.py                 # 扫码登录 — QR生成 + 轮询 + Token获取
│   ├── logger.py                   # 日志系统 — 命令/运行/错误 + 控制台镜像
│   └── get-token.py                # Token工具 — 独立获取并保存登录凭据
├── logs/                           # 日志目录（自动生成）
│   ├── commands/                   # 命令日志
│   ├── runtime/                    # 运行日志
│   ├── errors/                     # 错误日志（含未捕获异常堆栈）
│   └── console/                    # 控制台镜像（终端上实际看到的消息）
├── requirements.txt
├── 123pan.txt                      # 凭据文件（自动生成，勿提交）
├── qrcode.txt                      # 二维码文件（扫码登录时生成）
└── qrcode.png                      # 二维码图片（扫码登录时生成）
```

### API Authentication | API 鉴权流程

```
方式1: 账号/密码 → POST user.123pan.cn/api/user/sign_in (JSON)
                        ↓
                 返回 Bearer Token (code=200)
                        ↓
              保存至 123pan.txt + 后续请求 Authorization 头

方式2: 微信扫码 → GET /api/user/qr-code/generate → 生成二维码
                        ↓
              用户微信扫码 + 授权 → POST /api/user/qr-code/wx_code
                        ↓
              获取 wechat_code → POST /api/user/sign_in (type=4)
                        ↓
              返回 Bearer Token (code=200) → 保存至 123pan.txt
```

> **Note**: 2026-07-03 起，123云盘已废弃旧的请求签名（`getSign`）机制，所有 API 调用仅需 Bearer Token 鉴权。

## 🙏 Credits | 致谢

Based on [tosasitill/123pan](https://github.com/tosasitill/123pan) - Provides core authentication and API functionality.

基于 [tosasitill/123pan](https://github.com/tosasitill/123pan) - 提供核心认证和API功能。

---

## 📋 Changelog | 更新日志

### [2026-10-16] — Complete Console Logging | 日志记录补齐

> **修复**: 日志此前只记录显式埋点的事件（登录、退出、部分失败），终端上大量用户可见消息（准备上传 / 分片进度 / 上传成功 / 已跳过 / 目录上传完成及统计等）完全没有落盘，事后无法复盘。

#### 🐛 Bug Fixes | Bug 修复

##### 📝 Console Mirror | 控制台镜像
- **Every console message is now logged** — 新增 `logs/console/`，把终端上实际出现的每一条消息逐行落盘（stdout 记 `OUT`、stderr 记 `ERR`），无需业务代码逐条埋点
- **Library output included** — argparse 参数错误、第三方库往 stderr 写的内容也一并记录
- **Progress bars excluded** — 实测 tqdm 每一帧进度条都以 `\r` 回退重绘且不含换行，这类瞬时 UI 不入日志；进度条收尾那一帧保留一行
- **Uncaught tracebacks persisted** — 新增 `install_excepthook()`，未捕获异常的完整堆栈写入 `logs/errors/`，stderr 仍照常打印一份（不重复回显）
- **Console behavior unchanged** — 终端输出与改动前完全一致

#### 🔧 Technical Details | 技术细节
- `utils/logger.py`: 新增 `logs/console/` 目录、`_ConsoleMirror`（包装 `sys.stdout`/`sys.stderr`，按完整行落盘、过滤进度条帧）、`install_console_mirror()`（幂等）、`install_excepthook()`；日志前缀到目录的映射收敛为 `_PREFIX_DIRS`（原先 `os.path.join(_LOG_ROOT, LOG_DIR_X, ...)` 中 `LOG_DIR_X` 是绝对路径，会把 `_LOG_ROOT` 顶掉，导致目录无法从单点重定向）
- `app.py`: `main()` 开头安装控制台镜像与异常钩子（置于 `parse_args()` 之前，否则 `--help` 之类的输出抓不到）
- 顺带把 `tqdm.write` 与进度条共存时的日志回显统一（`_echo` 优先走 `tqdm.write`，打印前先清掉进度条再重绘，避免互相覆盖）
- 验证：`.workbuddy/test_console_log.py` 17 项全 PASS（日志目录已重定向到临时目录，不污染真实 logs/）；真实入口 `python app.py --help` 的 argparse 报错已落盘到 `logs/console/`

---

### [2026-10-16] — Upload Resilience: Retry, Part Concurrency, Integrity | 上传抗瞬断

> **修复**: 大文件分片上传偶发 `ConnectionResetError(104, 'Connection reset by peer')` / `SSLError(SSLEOFError(8, 'EOF occurred in violation of protocol'))` 时，一个已传数百片的大文件会整单作废。

#### 🐛 Bug Fixes | Bug 修复

##### 📤 Retry & Resumable Parts | 重试与分片自愈
- **Retries were never enabled** — requests 默认 `Retry(0, read=False)`（零重试），报错文案里的 `Max retries exceeded` 其实一次都没重试；现挂上带退避的重试适配器
- **Part-level retry with link refresh** — 单个分片失败后重新申请预签名链接再试（最多 3 轮），不再因一次瞬断放弃整个文件
- **Batch concurrency** — 原先一次取 10 个预签名链接却串行上传，而链接仅 10 分钟有效；现改为批内并发（`UPLOAD_PART_CONCURRENCY`，默认 4），单批耗时降至约 1/4，403 概率显著下降
- **No more silent part skipping** — 读盘改为按偏移独立读取，读到的字节数不足即判失败并记录偏移/期望/实读字节，杜绝静默漏传后由提交接口报一个看不出原因的错
- **Failures now logged** — 关键失败路径写入 `logs/errors/`

#### 🔧 Technical Details | 技术细节
- `utils/mpush.py`: 新增 `build_upload_session()`（带 `Retry` + 连接复用的会话，一个文件的全部请求共用，连接只握手一次）、`MPush._upload_one_part()`（换链接重试）、`MPush._upload_part_task()`（按偏移读盘 + 上传，供线程池调用）
- `tosasitill_123pan/config.py`: 新增 `UPLOAD_RETRY_TOTAL` / `UPLOAD_RETRY_BACKOFF` / `UPLOAD_RETRY_STATUS` / `UPLOAD_PART_ATTEMPTS` / `UPLOAD_SESSION_POOL` / `UPLOAD_PART_CONCURRENCY`
- 验证：`.workbuddy/test_upload_retry.py` 5 项、`.workbuddy/test_upload_file_e2e.py` 9 项全 PASS（本地桩服务，含 403、TCP RST、越界读取、并发/串行对照）

---

### [2026-10-16] — Cloud Disk Checksum Export | 云盘清单导出命令

> **新功能**: 交互模式新增 `export` 命令，批量导出 123云盘文件的校验值（Etag/MD5）清单，支持 TXT / CSV / JSON 三种格式。

#### ✨ New Features | 新功能

##### 📋 Export Command | 导出命令
- **Export checksums** — 导出云盘文件校验值清单（文件名 / Etag(MD5) / 大小 / FileId / 路径）
  - `export` — 当前目录，TXT 表格输出到终端
  - `export -r` — 递归遍历全部目录
  - `export -o <file|csv|json|txt>` — `-o` 自动推断格式；纯格式名自动生成 `123pan_checksums_YYYY-MM-DD.<格式>` 文件名
  - 输出文件已存在时自动递增 `_01`、`_02`，不覆盖已有文件
- 实测：全盘递归导出 5460 个文件，字段结构与历史清单（`123pan_checksums_*.json`）完全一致

#### 🔧 Technical Details | 技术细节
- `tosasitill_123pan/class123.py`: 新增 `list_files_recursive()`（递归遍历，完成后自动恢复导航状态）
- `utils/command_handler.py`: 新增 `handle_export_command()` 与 `_format_export_txt/csv/json()`
- `app.py`: 交互模式新增 `export` 命令路由与帮助文本

---

### [2026-10-16] — 上传收尾接口 2×2 实测矩阵 | v2 才是唯一全场景有效的收尾接口

> **第二次订正**：当天上午曾把收尾改成「v1 主力、v2 兜底」，依据是"v2 对已有分片记录会稳定返回 `非法请求(uid_mismatch)`"。当天下午在远程服务器上做完完整的 2×2 对照实验后，**该结论被推翻并作废**。

#### 🔬 实测矩阵（远程服务器、真实云盘账号）

| 收尾接口 | 单分片（≤16MB） | 多分片（>16MB） |
| :--- | :--- | :--- |
| `POST /b/api/file/upload_complete`（v1，body 仅 `{"fileId":…}`） | ✅ **真正落地**，响应 `data.Info` 带 FileId/Etag | ❌ **假成功**：返回 `code=0` 但 `data={}`，实测 60 秒内、乃至永久都不落地，记录状态仍是未完成 |
| `POST /b/api/file/upload_complete/v2`（body 带 StorageNode/bucket/fileId/fileSize/isMultipart/key/uploadId） | ✅ 真正落地（响应 `data.file_info`，实测 4 秒内） | ✅ **真正落地**（响应 `data.file_info`，实测 3~5 秒内即可在目录查到） |

- **`upload_complete/v2` 是唯一全场景有效的收尾接口；v1 只在单分片场景下有效。**
- **判定成功的可靠标志**：响应 `data` 里出现 `file_info`（v2）或 `Info`（v1 单分片）；**`code=0` 但 `data={}` 即为假成功**。

#### 🐛 Bug Fixes | Bug 修复

##### 📤 收尾接口 | Completion endpoint
- **收尾顺序改为 v2 主力 → v1 兜底**（原先写反了）
- **新增「落地标志」判定**：`code=0` 且 `data.file_info`（v2）/ `data.Info`（v1）才算服务端承认合并；否则立即判为假成功并转下一接口，不再空等回查窗口
- **保留落地回查**：仍以「收尾前不存在的 FileId + Etag + Size 与本地一致」做最终确认（`duplicate=1` 时服务端会自动改名，故不认文件名）
- 报 `uid_mismatch` 时输出明确诊断而不是笼统失败

#### 🔧 已实测排除的诱因（均不成立）
- ❌ **不是跨出口 IP**：本机（xxx.xx.xx.xx）建记录并传完分片 → 服务器（1x.xx.xx.xxx）收尾 → **正常落地**
- ❌ **不是 payload 字段问题**：当天报错那版与新版的 v2 报文逐字段一致
- ❌ **不是 key 里的 uid 段**：把 `key` 的 uid 段改成 `9999999999-0` 仍能正常收尾
- ❌ **不是"重传已有记录"**：同会话内对已有半成品记录重传，v2 收尾正常落地

---

### [2026-10-16 上午版（已作废）] — ~~v1 `upload_complete` 回归主力~~

> ⚠️ 本节结论已被上方 2026-10-16 第二次订正**推翻**，仅作留痕：当时误判「v1 收尾 5.6GB / 5.7GB 两个文件落地」，实际那次落地是 v2 兜底完成的；v1 对多分片是静默假成功。

---

### [2026-10-15] — Upload Protocol Fix & Chinese Localization | 上传协议适配修复与代码中文化

> **重大修复**（⚠️ 其中"完成接口"部分已被 2026-10-16 一节更正）: 123云盘于 2026-10 前后变更了 Web API 上传协议，旧版完成流程（`s3_list_upload_parts` + `s3_complete_multipart_upload` + `upload_complete` v1）已不再被服务端完整支持 —— 调用返回成功但文件不会落地；部分环境（如远程服务器）直接报 `非法请求(session_expired)`。

#### 🐛 Bug Fixes | Bug 修复

##### 📤 Upload Protocol Adaptation | 上传协议适配
- **Fixed uploads never landing** — 完成接口改用 `upload_complete/v2`（携带 `fileSize` / `isMultipart` / `fileId` 等参数）
  - ⚠️ **2026-10-16 更正**：v2 对已有分片上传记录的收尾会稳定报 `非法请求(uid_mismatch)`；现已改为 **v1 主力、v2 兜底**
- **Single-chunk path** — 单分片（≤16MB）改用 `s3_upload_object/auth` 获取上传链接；多分片继续使用 `s3_repare_upload_parts_batch`，分片大小调整为 16MB（与官方 Web 端一致）、按批获取链接
- **Link refresh on 403** — 分片上传链接过期（403）时自动刷新链接并重试一次
- 已实测验证：2MB（单分片）与 20MB（多分片）上传后均立即落地，大小校验一致

#### 📖 Documentation | 文档更新
- **Chinese localization** — 全部代码注释、docstring 与用户可见输出（交互帮助、提示、日志、报错消息）全量中文化；功能性载荷（API 字段、命令关键字、URL）保持原样

#### 🔧 Technical Details | 技术细节
- 停用旧完成链调用：`s3_list_upload_parts`（预检/二次查询）、`s3_complete_multipart_upload`
- `config.py`: 新增 `URL_S3_UPLOAD_AUTH`、`URL_UPLOAD_COMPLETE_V2`；`DEFAULT_BLOCK_SIZE` 5MB → 16MB；分片上传超时 30s → 120s
- 方案参考 AList `drivers/123` 驱动现行实现（2026-07-05 适配 yun.123pan.com）并用真实 API 验证

---

### [2026-07-05] — QR Code Login & Logging System | 扫码登录与日志系统

> **重大更新**: 新增微信扫码登录功能，无需账号密码即可通过微信扫码获取 Token。同时新增完整的日志系统和 Token 自动恢复机制。

#### ✨ New Features | 新功能

##### 🔐 QR Code Login | 扫码登录
- **WeChat QR scan login** — 使用微信或123云盘App扫码登录，无需输入账号密码
  - `--qr` / `--qrcode` 命令行参数强制使用扫码登录
  - 二维码自动保存到 `qrcode.txt`（ASCII码）和 `qrcode.png`（图片）
  - 终端实时显示扫码状态（等待/已扫码/已确认/过期）
  - 扫码后 0.5s 高频轮询获取 `wechat_code`，防止二维码过期
  - QR URL 包含 `env=production` 参数，确保微信页面正确调用扫码API
- **No-credentials login prompt** — 首次运行无 `123pan.txt` 时提示选择登录方式（账密/扫码）

##### 🔑 Token Auto-Recovery | Token自动恢复
- **Smart token verification** — 程序启动时自动验证已保存的 Token
- **Password re-login** — Token 过期时，如保存了账号密码则自动重新登录（尝试一次）
- **Graceful exit on failure** — Token 无效且无账密（扫码登录）或重登失败时，打印日志并退出程序

##### 📝 Logging System | 日志系统
- **Three log types** — 命令日志、运行日志、错误日志分别保存在 `logs/` 下的三个子目录
  - `logs/commands/` — 用户输入的每条命令及解析结果
  - `logs/runtime/` — 程序启动、登录、上传、下载等运行事件
  - `logs/errors/` — 登录失败、异常崩溃等错误事件和程序退出
- 日志文件按日期命名，带时间戳，同时输出到终端

#### 🔧 Technical Details | 技术细节
- QR code login flow reverse-engineered from 123Pan web client (`wx-app-login.html`)
- `envConfig` in `v2-pay.js` maps `env=production` to `https://api.123278.com/api/` API host
- Scan notification via `POST /user/qr-code/scan` (called by WeChat page, not by CLI)
- `wechat_code` obtained via `POST /api/user/qr-code/wx_code`, used for `POST /api/user/sign_in` with `type=4`
- Fast polling (0.5s) after scan detection to prevent QR expiry before `wechat_code` is available
- `login_with_wechat_code` accepts both `code=0` and `code=200` for compatibility

#### 📖 Documentation | 文档更新
- README 新增「登录方式」章节，详细说明三种登录方法和 Token 恢复流程
- README 新增「日志系统」章节
- README 命令行参数表新增 `--qr` / `--qrcode`
- 架构图新增 `qr_login.py`、`logger.py`、`logs/` 目录
- 所有脚本签名和注释全面更新

---

### [2026-07-03] — API Migration & Login Fix | API 迁移与登录修复

> 123云盘于 6 月 30 日更新了接口和认证体系（[公告](https://yun.123pan.cn/Notice/240156)），旧版本完全无法登录。此版本完整适配了全新的 API 架构。

#### 🔧 Breaking Changes | 重大变更
- **Login endpoint migrated** — 登录接口从 `www.123pan.com/b/api/user/sign_in` 迁移至 `user.123pan.cn/api/user/sign_in`，旧端点返回 404
- **Base domain migrated** — 主域名从 `www.123pan.com` 切换至 `www.123pan.cn`，Web 端已统一跳转至 `yun.123pan.cn`
- **Signature mechanism removed** — 彻底移除 `getSign` 签名机制及 `sign_get.py` 模块，新 API 仅需 Bearer Token 鉴权，不再要求请求签名参数
- **Login request format** — 登录请求从 `form-data` 改为 `application/json`，与官方 Web 端保持一致

#### 🐛 Bug Fixes | Bug 修复
- **Fixed login failure** — 修复因 123pan 接口迁移导致的登录 404 问题
- **Fixed file list retrieval** — 修复 `get_dir()` 因签名参数被拒绝的问题
- **Fixed upload request** — 修复 `upload_request` / `mkdir` / `download_info` 等接口因携带废弃签名参数导致的调用失败
- **Fixed token tool** — 更新 `get-token.py` 请求头以匹配新 API 要求

#### ⬆️ Upgrades | 升级适配
- Updated request headers: `App-Version` → `3`，`Origin`/`Referer` → `yun.123pan.cn`
- Unified `Content-Type: application/json` for all authenticated API calls
- Consolidated duplicate `URL_SIGN_IN` / `URL_123PAN_SIGN_IN` into single `URL_SIGN_IN`
- Improved login error handling with `ValueError` catch for JSON parse failures
- Deleted `sign_get.py` — dead code, no longer referenced by any module

#### ✅ Verified | 验证通过
- Login with phone number + password ✅
- File list / directory navigation ✅
- Single file upload (MD5 dedup + chunk upload + complete) ✅
- `app.py <path>` CLI mode ✅
- `app.py <path> --no-skip` force upload ✅

## ⚠️ Disclaimer | 免责声明

**This project is for personal use only and is not affiliated with 123Pan Cloud. Please comply with 123Pan Cloud's terms of service.**

**本项目仅供个人使用，与123云盘官方无关。请遵守123云盘的服务条款。**

<div align="center">

**⭐ Star this repo if you find it useful! ⭐**

</div>
