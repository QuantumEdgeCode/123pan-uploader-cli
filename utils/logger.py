#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
123云盘上传工具的日志系统

在 `logs/` 目录下提供三类日志:
  - logs/commands/  — 命令日志: 用户输入的命令及解析结果
  - logs/runtime/   — 运行日志: 程序启动、登录、上传、下载等事件
  - logs/errors/    — 错误日志: 登录失败、异常、崩溃退出

所有日志均带时间戳写入文件，同时打印到终端（stdout）。
错误日志除写入文件外还会输出到 stderr。
"""

import os
import sys
import logging
from datetime import datetime


# ─── 日志目录结构 ───
_LOG_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_DIR_COMMANDS = os.path.join(_LOG_ROOT, "commands")
LOG_DIR_RUNTIME = os.path.join(_LOG_ROOT, "runtime")
LOG_DIR_ERRORS = os.path.join(_LOG_ROOT, "errors")

# 确保目录存在
for _d in (LOG_DIR_COMMANDS, LOG_DIR_RUNTIME, LOG_DIR_ERRORS):
    os.makedirs(_d, exist_ok=True)


def _get_log_filename(prefix):
    """生成带当天日期的日志文件名。

    参数:
        prefix: 日志类型前缀（如 'command'、'runtime'、'error'）

    返回:
        str: 日志文件的完整路径
    """
    today = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(_LOG_ROOT, {
        'command': LOG_DIR_COMMANDS,
        'runtime': LOG_DIR_RUNTIME,
        'error': LOG_DIR_ERRORS,
    }.get(prefix, LOG_DIR_RUNTIME), f"{prefix}_{today}.log")


def _log(filepath, level, message):
    """将日志条目写入文件并打印到终端。

    参数:
        filepath: 日志文件路径
        level: 日志级别字符串（INFO、WARNING、ERROR 等）
        message: 日志消息内容
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] [{level}] {message}"

    # 写入文件
    try:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass  # 日志写入失败不应导致程序崩溃

    # 打印到终端
    if level == 'ERROR':
        print(line, file=sys.stderr)
    else:
        print(line)


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
    """返回三个日志目录路径，供外部引用。

    返回:
        dict: {'commands': str, 'runtime': str, 'errors': str}
    """
    return {
        'commands': LOG_DIR_COMMANDS,
        'runtime': LOG_DIR_RUNTIME,
        'errors': LOG_DIR_ERRORS,
    }
