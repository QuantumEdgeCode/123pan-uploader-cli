#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import atexit

# 配置 readline，实现 bash 风格的命令行编辑（历史记录、方向键等）
try:
    import readline
    _readline_available = True
except ImportError:
    try:
        import pyreadline3 as readline
        _readline_available = True
    except ImportError:
        readline = None
        _readline_available = False

# 历史记录文件配置
HISTORY_FILE = os.path.expanduser("~/.123pan_history")


def setup_readline():
    """配置 readline，提供 bash 风格的输入体验"""
    if not _readline_available or readline is None:
        return

    # 设置历史记录条数上限
    readline.set_history_length(1000)

    # 加载历史记录文件（若存在）
    try:
        if os.path.exists(HISTORY_FILE):
            readline.read_history_file(HISTORY_FILE)
    except (IOError, OSError):
        pass

    # 退出时保存历史记录
    atexit.register(save_history)

    # 启用文件路径 Tab 补全
    if hasattr(readline, 'set_completer'):
        readline.set_completer(path_completer)
        # 设置补全分隔符
        readline.set_completer_delims('\t\n;')
        # 启用 Tab 补全
        readline.parse_and_bind('tab: complete')

    # 设置编辑模式为 emacs（类似 bash）
    try:
        readline.parse_and_bind('set editing-mode emacs')
    except:
        pass


def save_history():
    """保存命令历史到文件"""
    if _readline_available and readline is not None:
        try:
            readline.write_history_file(HISTORY_FILE)
        except (IOError, OSError):
            pass


def path_completer(text, state):
    """文件路径 Tab 补全"""
    try:
        # 展开用户主目录
        if text.startswith('~'):
            text = os.path.expanduser(text)

        # 获取目录和部分文件名
        if os.path.isdir(text):
            directory = text
            partial = ''
        else:
            directory = os.path.dirname(text) or '.'
            partial = os.path.basename(text)

        # 列出匹配的文件/目录
        try:
            entries = os.listdir(directory)
        except OSError:
            return None

        # 筛选匹配部分名称的条目
        matches = []
        for entry in entries:
            if entry.startswith(partial):
                full_path = os.path.join(directory, entry)
                if os.path.isdir(full_path):
                    matches.append(full_path + os.sep)
                else:
                    matches.append(full_path)

        if state < len(matches):
            return matches[state]
        return None
    except Exception:
        return None


def normalize_path(path_str):
    """
    规范化路径字符串：去除引号并展开特殊字符，兼容 Windows 和 Unix 路径。

    参数:
        path_str: 可能包含引号或特殊字符的路径字符串

    返回:
        规范化后的路径
    """
    # 去除首尾引号和空白
    path_str = path_str.strip().strip("\"'")

    # 展开用户主目录（~）
    path_str = os.path.expanduser(path_str)

    # 规范化路径分隔符
    path_str = os.path.normpath(path_str)

    return path_str
