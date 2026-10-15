#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import shlex
from utils.input_handler import normalize_path
from utils.mget import MGet, _validate_output_path
from utils.logger import log_command, log_runtime, log_error


def create_argument_parser():
    """创建并配置上传命令的参数解析器。

    支持的参数:
        path:           要上传的文件或目录路径（可选）
        -d, --dest:     目标目录名
        -f, --force:    强制覆盖已存在文件
        -k, --keep:     冲突时保留两份文件
        --no-skip:      关闭 MD5 重复校验
        --qr, --qrcode: 强制扫码登录（微信扫码）

    返回:
        argparse.ArgumentParser: 配置好的上传命令参数解析器
    """
    parser = argparse.ArgumentParser(
        description="123云盘上传工具 CLI",
        add_help=False  # 禁用默认帮助，避免直接退出
    )

    parser.add_argument("path", nargs="?", help="要上传的文件或目录路径")
    parser.add_argument("-d", "--dest", help="目标名称（默认与源相同）")
    parser.add_argument("-f", "--force", action="store_true", help="覆盖已存在文件（删除后重新上传）")
    parser.add_argument("-k", "--keep", action="store_true", help="冲突时保留两份文件")
    parser.add_argument("--no-skip", action="store_true", help="不跳过 MD5 相同的已存在文件")
    parser.add_argument("--qr", "--qrcode", dest="qrcode", action="store_true", help="强制扫码登录（使用微信或 123云盘 App 扫码）")

    return parser


def _is_flag(token):
    """判断 token 是否为 flag 参数。返回 (is_flag, flag_name)。"""
    if not token.startswith('-'):
        return False, None

    # 单独的 "-" 不是合法 flag，按路径的一部分处理
    if token == '-':
        return False, None

    # 单字母 flag: -d、-f、-k（必须是 ASCII 字母）
    if len(token) == 2 and token[1].isascii() and token[1].isalpha():
        return True, token

    # 长 flag: --dest、--force、--no-skip
    if token.startswith('--'):
        return True, token

    # Windows 下路径可能包含以 "-" 开头、后接非 ASCII 字符的片段
    # （如 "- 副本"、"-中文"），将这类片段按路径的一部分处理。
    # "-X" 中 X 为非 ASCII/非字母时同样按路径处理。
    if len(token) >= 2 and not (token[1].isascii() and token[1].isalpha()):
        return False, None

    return True, token


def parse_upload_command(user_input, default_sure_option, default_skip_existing):
    """
    解析上传命令的用户输入并提取参数。

    参数:
        user_input: 用户输入的原始字符串
        default_sure_option: 默认冲突处理选项
        default_skip_existing: 默认是否跳过已存在文件

    返回:
        dict: 解析后的命令，包含以下键:
            - path: 要上传的路径 (str)
            - dest_name: 目标名称 (str 或 None)
            - sure_option: 冲突处理选项 (str)
            - skip_existing: 是否跳过已存在文件 (bool)
            - error: 解析失败时的错误信息 (str 或 None)
    """
    result = {
        'path': None,
        'dest_name': None,
        'sure_option': default_sure_option,
        'skip_existing': default_skip_existing,
        'error': None
    }

    user_input = user_input.strip()
    if not user_input:
        result['error'] = "输入为空"
        return result

    try:
        parts = shlex.split(user_input, posix=False)
    except ValueError as e:
        result['error'] = f"命令格式无效: {e}"
        return result

    if not parts:
        result['error'] = "输入为空"
        return result

    # 检测未加引号且包含空格的路径 — shlex 会把它们拆开，
    # 导致 "C:\path\to file" 这类路径被破坏。
    # 检测方法：任何非 flag 片段（不以引号开头）包含空格即视为未加引号的路径。
    unquoted_path_with_spaces = False
    for i, part in enumerate(parts):
        if not part.startswith('-') and ' ' in part and not part.startswith('"') and not part.startswith("'"):
            unquoted_path_with_spaces = True
            break

    # 需要取值的 flag（后面必须跟一个非 flag 参数）
    flags_with_value = {'-d', '--dest'}
    # 布尔 flag（不消耗额外参数）
    bool_flags = {'-f', '--force', '-k', '--keep', '--no-skip', '--qr', '--qrcode'}

    path_parts = []
    i = 0

    while i < len(parts):
        token = parts[i]
        is_flag, _ = _is_flag(token)

        # 非 flag token: 属于路径的一部分
        if not is_flag:
            path_parts.append(token)
            i += 1
            # 后续所有非 flag token 同样属于路径
            while i < len(parts):
                next_token = parts[i]
                next_is_flag, _ = _is_flag(next_token)
                if not next_is_flag:
                    path_parts.append(next_token)
                    i += 1
                else:
                    break
            continue

        # 这是一个 flag
        if token in bool_flags:
            i += 1
        elif token in flags_with_value:
            # -d 需要一个取值（下一个 token，除非它也是 flag）
            if i + 1 < len(parts):
                next_token = parts[i + 1]
                next_is_flag, _ = _is_flag(next_token)
                if not next_is_flag:
                    i += 2  # 消耗 flag + 取值
                else:
                    result['error'] = f"flag {token} 需要一个取值"
                    return result
            else:
                result['error'] = f"flag {token} 需要一个取值"
                return result
        else:
            result['error'] = f"未知 flag: {token}"
            return result

    # 从收集到的片段还原路径
    raw_path = ' '.join(path_parts).strip().strip('"\'')
    if not raw_path:
        result['error'] = "必须提供路径"
        return result

    # 路径包含空格但未加引号时，提示加引号
    if unquoted_path_with_spaces and ' ' in raw_path:
        result['error'] = (f'路径 "{raw_path}" 包含空格，'
                           '请用引号包裹: "{raw_path}"')
        return result

    # 使用 argparse 解析实际的 flag
    try:
        parser = create_argument_parser()
        parsed_args = parser.parse_args(parts[len(path_parts):])
    except SystemExit:
        result['error'] = "flag 无效。用法: <path> [-d dest] [-f | -k] [--no-skip]"
        return result

    result['path'] = normalize_path(raw_path)
    result['dest_name'] = normalize_path(parsed_args.dest) if parsed_args.dest else None

    if parsed_args.force:
        result['sure_option'] = "2"
    elif parsed_args.keep:
        result['sure_option'] = "1"

    result['skip_existing'] = not parsed_args.no_skip
    return result


def handle_mget_command(user_input):
    """处理 mget（下载）命令。

    解析 mget 命令、校验参数并执行下载。
    命令会记录到命令日志和运行日志。

    参数:
        user_input: 以 'mget' 开头的原始命令输入

    用法:
        mget <url> [-o output_file] [-t threads] [-s]
    """
    import shlex
    import argparse

    try:
        # 正确拆分命令
        if sys.platform == "win32":
            parts = shlex.split(user_input, posix=False)
        else:
            parts = shlex.split(user_input)

        # 去掉开头的 'mget'
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            print("用法: mget <url> [-o 输出文件] [-t 线程数] [-s]")
            print("  -o: 输出文件名（默认: 'downloaded_file'）")
            print("  -t: 下载线程数（默认: 8）")
            print("  -s: 使用单线程下载")
            return

        # 为 mget 参数创建解析器
        parser = argparse.ArgumentParser(
            description="文件下载器",
            add_help=False
        )
        parser.add_argument("url", help="要下载的文件 URL")
        parser.add_argument("-o", "--output", help="输出文件路径", default="downloaded_file")
        parser.add_argument("-t", "--threads", type=int, help="下载线程数", default=8)
        parser.add_argument("-s", "--single", action="store_true", help="使用单线程下载")

        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            print("mget 命令格式无效")
            return

        url = parsed_args.url
        output = normalize_path(parsed_args.output)
        threads = parsed_args.threads
        single_thread = parsed_args.single

        # 下载前校验输出路径
        try:
            validated_output = _validate_output_path(output)
        except ValueError as e:
            print(f"输出路径错误: {e}")
            return

        print(f"开始下载: {url}")
        print(f"保存到: {validated_output}")
        print(f"线程数: {'1（单线程）' if single_thread else threads}")

        downloader = MGet(default_threads=threads)
        # 直接传入已校验的路径；MGet.download 会跳过自身校验
        result = downloader._download_raw(url, validated_output, threads, force_single=single_thread)

        # 显示完成信息
        if result is not None and os.path.exists(validated_output):
            file_size = os.path.getsize(validated_output)
            print(f"下载完成！文件大小: {file_size / 1024 / 1024:.2f} MB")
        elif result is None:
            print("下载失败。")

    except Exception as e:
        print(f"下载失败: {str(e)}")


def execute_upload(mpush, path, sure_option, dest_name, skip_existing):
    """执行文件或目录的上传操作。

    上传开始和完成时会写入运行日志。

    参数:
        mpush: 用于上传的 MPush 实例
        path: 要上传的文件或目录路径
        sure_option: 冲突处理选项（"1" 保留两份，"2" 覆盖）
        dest_name: 目标名称（None 表示保持原名）
        skip_existing: 是否跳过 MD5 相同的文件
    """
    log_runtime(f"开始上传: path='{path}', mode={sure_option}, dest='{dest_name}', skip={skip_existing}")

    if os.path.isdir(path):
        # 上传目录
        print(f"准备上传目录: {os.path.basename(path)}")
        if dest_name:
            mpush.upload_directory_concurrent(
                path, sure=sure_option, custom_dirname=dest_name, skip_existing=skip_existing
            )
        else:
            mpush.upload_directory_concurrent(path, sure=sure_option, skip_existing=skip_existing)
        mpush.pan.parentFileId = 0
        mpush.pan.parentFileList = [0]
    elif os.path.isfile(path):
        # 上传单个文件
        if dest_name:
            # 为单文件上传创建自定义目录
            folder_id = mpush.pan.mkdir(dest_name, remake=False)
            if folder_id:
                mpush.upload_file(path, parent_id=folder_id, sure=sure_option, skip_existing=skip_existing)
                mpush.pan.parentFileId = 0
                mpush.pan.parentFileList = [0]
            else:
                print(f"错误: 创建目录 '{dest_name}' 失败")
        else:
            mpush.upload_file(path, sure=sure_option, skip_existing=skip_existing)
    else:
        print(f"错误: {path} 既不是文件也不是目录")


def validate_upload_path(path):
    """
    校验上传路径是否存在。

    参数:
        path: 要校验的路径

    返回:
        bool: 路径存在返回 True，否则 False
    """
    if not os.path.exists(path):
        print(f"错误: 路径 {path} 不存在")
        return False
    return True


def format_upload_mode(sure_option, skip_existing):
    """
    格式化上传模式的显示字符串。

    参数:
        sure_option: 冲突处理选项
        skip_existing: 是否跳过已存在文件

    返回:
        str: 格式化后的模式描述
    """
    mode = '覆盖' if sure_option == '2' else '保留两份'
    return f"上传模式: {mode}，跳过已存在: {skip_existing}"
