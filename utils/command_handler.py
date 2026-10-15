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


def _format_export_txt(file_records):
    """将文件记录格式化为对齐的纯文本表格

    参数:
        file_records: 文件记录列表，每项含 FileName, Etag, SizeHuman, FileId, FilePath

    返回:
        str: 格式化后的文本表格
    """
    if not file_records:
        return "未找到文件。"

    # 计算各列宽度
    max_name = max(len(r["FileName"]) for r in file_records)
    max_name = max(max_name, len("文件名"))
    max_name = min(max_name, 48)

    max_etag = max(len(r["Etag"]) for r in file_records)
    max_etag = max(max_etag, len("Etag (MD5)"))
    max_etag = min(max_etag, 36)

    max_size = max(len(r["SizeHuman"]) for r in file_records)
    max_size = max(max_size, len("大小"))
    max_size = min(max_size, 14)

    # 构建表头格式
    header_fmt = f"  {{:<{max_name}}}  {{:<{max_etag}}}  {{:>{max_size}}}  {{:<10}}  {{:<20}}"
    separator_fmt = f"  {{:-<{max_name}}}  {{:-<{max_etag}}}  {{:->{max_size}}}  {{:-<10}}  {{:-<20}}"

    lines = []
    lines.append("=" * 60)
    lines.append("  123云盘文件校验值导出")
    lines.append("=" * 60)
    lines.append(header_fmt.format("文件名", "Etag (MD5)", "大小", "FileId", "路径"))
    lines.append(separator_fmt.format("", "", "", "", ""))

    for r in file_records:
        name = r["FileName"][:max_name]
        etag = r["Etag"][:max_etag] if r["Etag"] else "-"
        lines.append(header_fmt.format(name, etag, r["SizeHuman"], str(r["FileId"]), r["FilePath"]))

    lines.append("-" * 60)
    lines.append(f"  总计: {len(file_records)} 个文件")
    return "\n".join(lines)


def _format_export_csv(file_records):
    """将文件记录格式化为 CSV

    参数:
        file_records: 文件记录列表，每项含 FileName, Etag, Size, SizeHuman, FileId, FilePath

    返回:
        str: CSV 格式字符串
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["文件名", "Etag (MD5)", "大小(字节)", "大小(可读)", "FileId", "路径"])

    for r in file_records:
        writer.writerow([
            r["FileName"],
            r["Etag"] if r["Etag"] else "",
            r["Size"],
            r["SizeHuman"],
            r["FileId"],
            r["FilePath"],
        ])

    return output.getvalue()


def _format_export_json(file_records):
    """将文件记录格式化为 JSON

    参数:
        file_records: 文件记录列表

    返回:
        str: JSON 格式字符串
    """
    import json
    return json.dumps(file_records, ensure_ascii=False, indent=2)


def handle_export_command(user_input, pan):
    """处理 export 命令，批量导出云盘文件的校验值

    解析交互模式下的 export 命令，导出文件的 Etag/MD5 校验值。

    参数:
        user_input: 原始命令字符串（如 'export -r -o all.csv'）
        pan: 已认证的 Pan123 实例

    用法:
        export [-r] [-o <file>]

    -o 自动推断逻辑:
        all.csv   → CSV 格式，输出到 all.csv
        all.json  → JSON 格式，输出到 all.json
        csv       → CSV 格式，自动文件名 123pan_checksums_YYYY-MM-DD.csv
        json      → JSON 格式，自动文件名 123pan_checksums_YYYY-MM-DD.json
        other     → TXT 格式，输出到指定文件
    无 -o        → TXT 表格输出到终端
    """
    # 解析参数
    try:
        parts = shlex.split(user_input, posix=False)
    except ValueError as e:
        print(f"命令格式错误: {e}")
        print("用法: export [-r] [-o <文件路径|格式名>]")
        return

    # 去掉开头的 "export"
    args = parts[1:] if len(parts) > 1 else []

    recursive = False
    output_file = None
    output_format = "txt"

    i = 0
    while i < len(args):
        token = args[i]
        if token == "-r":
            recursive = True
            i += 1
        elif token == "-o":
            if i + 1 < len(args):
                raw = args[i + 1]

                # 检查是否有可识别的扩展名
                ext = os.path.splitext(raw)[1].lower()
                known_formats = {".csv": "csv", ".json": "json", ".txt": "txt"}
                bare_formats = {"csv": "csv", "json": "json", "txt": "txt"}

                if ext in known_formats:
                    # 如 all.csv → CSV, all.json → JSON
                    output_format = known_formats[ext]
                    output_file = normalize_path(raw)
                elif raw.lower() in bare_formats:
                    # 如 "csv" → 自动生成带日期的文件名
                    output_format = raw.lower()
                    from datetime import date
                    today = date.today().isoformat()
                    base_name = f"123pan_checksums_{today}"
                    output_file = normalize_path(f"{base_name}.{output_format}")
                else:
                    # 普通文件名 → TXT 格式
                    output_format = "txt"
                    output_file = normalize_path(raw)

                # 任何情况都不覆盖本地文件，自动递增 _01, _02...
                counter = 0
                while os.path.exists(output_file):
                    counter += 1
                    base, ext_out = os.path.splitext(output_file)
                    # 去掉已有的 _NN 后缀再拼，防止越叠越长（data_01.json → data_02.json）
                    if len(base) >= 3 and base[-3:-2] == "_" and base[-2:].isdigit():
                        base = base[:-3]
                    output_file = normalize_path(f"{base}_{counter:02d}{ext_out}")

                i += 2
            else:
                print("错误: -o 需要跟文件路径或格式名 (csv|json|txt)")
                return
        elif token == "--format":
            print("提示: --format 参数已移除，直接用 -o 加扩展名即可")
            print("  示例: export -o out.csv   (CSV)")
            print("        export -o out.json  (JSON)")
            print("        export -o csv       (自动文件名 CSV)")
            print("        export              (终端输出 TXT 表格)")
            return
        else:
            print(f"错误: 未知参数: {token}")
            print("用法: export [-r] [-o <文件路径|格式名>]")
            return

    print("正在从 123云盘拉取文件列表...")

    if recursive:
        file_records = pan.list_files_recursive()
    else:
        # 刷新当前目录文件列表
        code = pan.get_dir()
        if code != 0:
            print(f"拉取文件列表失败 (code={code})")
            return

        if pan.list is None:
            print("当前目录没有文件。")
            return

        file_records = []
        for item in pan.list:
            if item.get("Type") == 0:
                size = item.get("Size", 0)
                if size > 1073741824:
                    size_human = f"{size / 1073741824:.2f} GB"
                elif size > 1048576:
                    size_human = f"{size / 1048576:.2f} MB"
                elif size > 1024:
                    size_human = f"{size / 1024:.2f} KB"
                else:
                    size_human = f"{size} B"

                file_records.append({
                    "FileName": item.get("FileName", ""),
                    "Etag": item.get("Etag", ""),
                    "Size": size,
                    "SizeHuman": size_human,
                    "FileId": item.get("FileId", ""),
                    "FilePath": "/",
                })

    if not file_records:
        print("未找到文件。")
        return

    # 按格式输出
    if output_format == "csv":
        output = _format_export_csv(file_records)
    elif output_format == "json":
        output = _format_export_json(file_records)
    else:
        output = _format_export_txt(file_records)

    # 写入文件或打印到终端
    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已导出 {len(file_records)} 个文件到: {output_file}")
        except IOError as e:
            print(f"写入文件失败: {e}")
    else:
        print(output)
