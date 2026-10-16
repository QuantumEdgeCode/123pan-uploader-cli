#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
123云盘上传工具的日志系统

在 `logs/` 目录下提供四类日志:
  - logs/commands/  — 命令日志: 用户输入的命令及解析结果
  - logs/runtime/   — 运行日志: 程序启动、登录、上传、下载等事件
  - logs/errors/    — 错误日志: 登录失败、异常、崩溃退出、未捕获异常堆栈
  - logs/console/   — 控制台镜像: 用户实际在终端看到的每一条消息（完整逐行记录）

前三类由代码显式调用（log_command / log_runtime / log_error）写入；
第四类由 install_console_mirror() 安装的 stdout/stderr 镜像自动写入，无需在业务
代码里逐条调用，因此不会漏记 —— 任何 print() / tqdm.write()，以及库自己往 stderr
写的内容（例如 argparse 的参数错误、未捕获异常堆栈），都会进 logs/console/。

所有日志均带时间戳写入文件，同时打印到终端（控制台输出行为完全不变）。
错误日志除写入文件外还会输出到 stderr。

注意: tqdm 的进度条帧（以 \\r 回退重绘、不带换行）属于瞬时 UI，不写入
logs/console/；进度条结束时那一帧（带换行）会保留一行，便于事后确认进度。
"""

import os
import sys
import threading
import traceback
from datetime import datetime


# ─── 日志目录结构 ───
_LOG_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_DIR_COMMANDS = os.path.join(_LOG_ROOT, "commands")
LOG_DIR_RUNTIME = os.path.join(_LOG_ROOT, "runtime")
LOG_DIR_ERRORS = os.path.join(_LOG_ROOT, "errors")
LOG_DIR_CONSOLE = os.path.join(_LOG_ROOT, "console")

# 确保目录存在
for _d in (LOG_DIR_COMMANDS, LOG_DIR_RUNTIME, LOG_DIR_ERRORS, LOG_DIR_CONSOLE):
    os.makedirs(_d, exist_ok=True)

# 写日志时使用的锁: 上传是多线程的, 避免行与行之间互相穿插
_WRITE_LOCK = threading.Lock()


# 前缀 -> 目录。集中放在这里，既便于阅读，也便于测试把日志重定向到临时目录
_PREFIX_DIRS = {
    'command': LOG_DIR_COMMANDS,
    'runtime': LOG_DIR_RUNTIME,
    'error': LOG_DIR_ERRORS,
    'console': LOG_DIR_CONSOLE,
}


def _get_log_filename(prefix):
    """生成带当天日期的日志文件名。

    参数:
        prefix: 日志类型前缀（如 'command'、'runtime'、'error'、'console'）

    返回:
        str: 日志文件的完整路径
    """
    today = datetime.now().strftime('%Y-%m-%d')
    directory = _PREFIX_DIRS.get(prefix, LOG_DIR_RUNTIME)
    return os.path.join(directory, f"{prefix}_{today}.log")


def _append(filepath, level, message):
    """仅把一条日志追加到文件（不回显控制台）。

    参数:
        filepath: 日志文件路径
        level: 日志级别字符串（INFO、WARNING、ERROR、OUT 等）
        message: 日志消息内容

    返回:
        str: 实际写入的整行文本（含时间戳与级别）
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] [{level}] {message}"
    with _WRITE_LOCK:
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass  # 日志写入失败不应导致程序崩溃
    return line


def _echo(line, level):
    """把日志行回显到控制台。

    优先使用 tqdm.write: 它会在打印前先把进度条清掉再重绘，避免日志与进度条
    互相覆盖。tqdm 不可用时退回普通 print。

    参数:
        line: 已带时间戳的完整日志行
        level: 日志级别字符串（ERROR 走 stderr，其余走 stdout）
    """
    to_stderr = level == 'ERROR'
    try:
        from tqdm import tqdm
        tqdm.write(line, file=sys.stderr if to_stderr else None)
    except Exception:
        print(line, file=sys.stderr if to_stderr else sys.stdout)


def _log(filepath, level, message):
    """将日志条目写入文件并打印到终端。

    参数:
        filepath: 日志文件路径
        level: 日志级别字符串（INFO、WARNING、ERROR 等）
        message: 日志消息内容
    """
    line = _append(filepath, level, message)
    _echo(line, level)


def log_command(message):
    """记录用户命令或命令解析结果。

    参数:
        message: 命令描述或解析结果字符串
    """
    _log(_get_log_filename('command'), 'COMMAND', message)


def log_runtime(message):
    """记录运行事件（启动、登录、上传、下载等）。

    参数:
        message: 事件描述字符串
    """
    _log(_get_log_filename('runtime'), 'INFO', message)


def log_error(message):
    """记录错误事件（登录失败、异常、崩溃退出）。

    错误会写入错误日志文件并输出到 stderr。

    参数:
        message: 错误描述字符串
    """
    _log(_get_log_filename('error'), 'ERROR', message)


def log_exit(reason, exit_code=1):
    """记录程序退出事件并在退出前保存到错误日志。

    因严重故障（如登录失败、Token 失效）必须退出程序时，
    调用此函数。

    参数:
        reason: 便于阅读的退出原因
        exit_code: 进程退出码（默认: 1）
    """
    log_error(f"程序退出 (code={exit_code}): {reason}")
    sys.exit(exit_code)


def get_log_dirs():
    """返回四个日志目录路径，供外部引用。

    返回:
        dict: {'commands': str, 'runtime': str, 'errors': str, 'console': str}
    """
    return {
        'commands': LOG_DIR_COMMANDS,
        'runtime': LOG_DIR_RUNTIME,
        'errors': LOG_DIR_ERRORS,
        'console': LOG_DIR_CONSOLE,
    }


class _ConsoleMirror:
    """控制台镜像: 转发到真实流的同时, 把完整行追加到控制台日志。

    设计要点:
    - stdout 与 stderr 都镜像（分别标记为 OUT / ERR），保证「终端上出现过什么，
      日志里就有什么」，包括库自己写的 stderr 内容。
    - 按「完整行」落盘: 行没写完（例如 readline 提示符）不写日志，避免日志里
      出现半截无意义的内容。
    - 进度条过滤: 实测 tqdm 的每一帧进度条都以 \\r 开头回退重绘、且不含 \\n，
      因此「不含 \\n 但含 \\r」的片段一律丢弃（瞬时 UI，没有保留价值）；
      带 \\n 的片段只保留最后一个 \\r 之后的部分，这样进度条收尾那一帧会留下
      一行，便于事后确认进度。
    - 控制台行为完全不变: write/flush 等全部转发给真实流，其余属性
      （isatty、encoding、fileno 等）通过 __getattr__ 透传。

    参数:
        stream: 被包装的真实输出流（sys.stdout 或 sys.stderr）
        level: 写入日志时使用的级别标记（'OUT' 或 'ERR'）
    """

    def __init__(self, stream, level):
        self._stream = stream
        self._level = level
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, text):
        """写入控制台并镜像到日志。

        参数:
            text: 待写入的文本片段

        返回:
            int: 真实流的写入结果
        """
        if not isinstance(text, str):
            text = str(text)

        # 1) 原样转发到控制台（行为与未安装镜像时完全一致）
        written = self._stream.write(text)

        # 2) 镜像: 只处理已经写完的整行
        try:
            if "\n" in text:
                # 同一片段里可能既有进度条重绘又有正文，只取最后一个 \r 之后的部分
                text = text.rsplit("\r", 1)[-1]
            elif "\r" in text:
                return written  # 纯进度条帧，不进日志

            with self._lock:
                self._buffer += text
                complete_lines = self._buffer.split("\n")
                self._buffer = complete_lines.pop()  # 最后一段是未写完的半行
            for raw in complete_lines:
                line = raw.rsplit("\r", 1)[-1].rstrip()
                if line:
                    _append(_get_log_filename('console'), self._level, line)
        except Exception:
            # 镜像失败绝不能影响正常输出
            pass

        return written

    def flush(self):
        """刷新真实流。"""
        return self._stream.flush()

    def __getattr__(self, name):
        """未显式实现的属性/方法一律透传给真实流。"""
        return getattr(self._stream, name)


def install_console_mirror():
    """安装 stdout/stderr 镜像，让控制台输出同时落盘到 logs/console/。

    幂等: 重复调用只安装一次，不会造成嵌套包装（否则日志会出现重复行）。

    返回:
        bool: 本次调用是否真的安装了镜像（已安装则返回 False）
    """
    if isinstance(sys.stdout, _ConsoleMirror):
        return False
    sys.stdout = _ConsoleMirror(sys.stdout, 'OUT')
    sys.stderr = _ConsoleMirror(sys.stderr, 'ERR')
    return True


def install_excepthook():
    """安装全局异常钩子: 未捕获异常的完整堆栈写入错误日志。

    默认行为（把堆栈打印到 stderr）保持不变，只是额外多写一份到
    logs/errors/，这样程序崩溃后也能从日志里查到完整堆栈。

    注意: 这里用 _append 只写文件、不再回显，否则 stderr 上会出现两份堆栈。

    返回:
        bool: 本次调用是否真的安装了钩子（已安装则返回 False）
    """
    if getattr(sys, '_123pan_excepthook_installed', False):
        return False

    original_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _append(_get_log_filename('error'), 'ERROR', f"未捕获异常:\n{detail.rstrip()}")
        except Exception:
            pass
        original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    sys._123pan_excepthook_installed = True
    return True
