#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
123云盘上传工具 CLI — 主入口

支持三种登录方式:
  1. 已保存的 Token（123pan.txt）— 自动校验，失效时用账号密码重新登录
  2. 账号密码 — 交互输入或命令行传入
  3. 扫码登录（--qr 参数）— 使用微信或 123云盘 App 扫码

登录失败处理:
  - Token 失效且存在账号密码 → 尝试重新登录一次
  - 重新登录失败或没有账号密码（扫码登录）→ 记录错误并以 exit(1) 退出
  - 所有退出都会写入 logs/errors/ 日志并打印到终端

日志:
  - logs/commands/  — 用户命令输入及解析结果
  - logs/runtime/   — 程序运行事件（启动、登录、上传、下载）
  - logs/errors/    — 错误事件及程序退出
"""

import os
import sys
import time
import signal
import json
from tosasitill_123pan.class123 import Pan123
from tosasitill_123pan import config
from utils.mpush import MPush
from utils.logger import log_runtime, log_error, log_command, log_exit
from utils.input_handler import setup_readline, normalize_path
from utils.command_handler import (
    create_argument_parser,
    parse_upload_command,
    handle_mget_command,
    execute_upload,
    validate_upload_path,
    format_upload_mode
)

# 用于跟踪 Ctrl+C 按键次数和退出标志的全局变量
_ctrl_c_count = 0
_last_ctrl_c_time = 0
_should_exit = False


def handle_ctrl_c(signum, frame):
    """处理 Ctrl+C 信号，实现优雅退出。

    2 秒内连续按两次 Ctrl+C 退出程序；单次 Ctrl+C 只中断当前操作。

    参数:
        signum: 信号编号
        frame: 当前堆栈帧
    """
    global _ctrl_c_count, _last_ctrl_c_time, _should_exit
    current_time = time.time()

    if current_time - _last_ctrl_c_time < 2:
        _ctrl_c_count += 1
    else:
        _ctrl_c_count = 1

    _last_ctrl_c_time = current_time

    if _ctrl_c_count >= 2:
        log_runtime("检测到连续两次 Ctrl+C，正在退出程序...")
        _should_exit = True
        raise KeyboardInterrupt()
    else:
        print("\n请在 2 秒内再次按 Ctrl+C 退出，或继续输入。")
        raise KeyboardInterrupt()


def print_interactive_help():
    """打印交互模式命令帮助"""
    print("\n" + "="*60)
    print("交互模式 - 命令:")
    print("  <path>                    上传文件或目录")
    print('  <path> -d "name"          上传并自定义目录名')
    print("  <path> -f                 强制覆盖已存在的文件")
    print("  <path> -k                 冲突时保留两份")
    print("  <path> --no-skip          关闭 MD5 重复校验")
    print("  mget <url> [-o file] [-t n] 下载文件")
    print("  0                         退出程序")
    print("  Ctrl+C 两次               退出程序")
    print("="*60 + "\n")


def run_interactive_mode(mpush, default_sure_option, default_skip_existing):
    """运行交互式命令循环。

    读取用户输入、记录每条命令，并执行上传或下载。
    支持双击 Ctrl+C 退出。

    参数:
        mpush: 用于上传的 MPush 实例
        default_sure_option: 默认冲突处理选项（"1" 或 "2"）
        default_skip_existing: 默认是否跳过已存在文件（bool）
    """
    global _ctrl_c_count, _should_exit

    print_interactive_help()

    while True:
        if _should_exit:
            break

        try:
            user_input = input("\033[91m >\033[0m ")

            _ctrl_c_count = 0
            user_input = user_input.strip()

            if not user_input:
                continue

            # 记录命令
            log_command(user_input)

            # 退出命令
            if user_input == "0":
                log_runtime("用户请求退出（输入 '0'）")
                print("正在退出程序")
                break

            # 下载命令
            if user_input.startswith("mget "):
                handle_mget_command(user_input)
                continue

            # 解析上传命令
            cmd = parse_upload_command(user_input, default_sure_option, default_skip_existing)

            if cmd['error']:
                print(cmd['error'])
                continue

            # 校验路径
            if not validate_upload_path(cmd['path']):
                continue

            # 显示上传模式
            print(format_upload_mode(cmd['sure_option'], cmd['skip_existing']))

            # 执行上传
            execute_upload(
                mpush,
                cmd['path'],
                cmd['sure_option'],
                cmd['dest_name'],
                cmd['skip_existing']
            )

        except KeyboardInterrupt:
            if _should_exit:
                break
            print("\n操作已中断。再次按 Ctrl+C 退出。")
            continue
        except EOFError:
            log_runtime("收到 EOF，正在退出程序")
            print("\n正在退出程序")
            break
        except Exception as e:
            log_error(f"交互模式错误: {str(e)}")
            print(f"发生错误: {str(e)}")
            continue


def main():
    """123云盘上传工具主入口。

    支持命令行模式和交互模式。
    - 命令行: python app.py <路径> [-f] [-k] [-d 目标名] [--no-skip]
    - 交互模式: python app.py（然后输入命令）
    - 扫码登录: python app.py --qr（强制扫码登录）

    登录流程:
    1. 带 --qr 参数时: 强制扫码登录
    2. 123pan.txt 存在时: 加载 Token 并校验，必要时重新登录
    3. 没有任何凭据时: 提示输入账号密码或扫码登录

    登录失败时，程序记录错误并以退出码 1 退出。
    """
    signal.signal(signal.SIGINT, handle_ctrl_c)
    setup_readline()

    parser = create_argument_parser()
    args = parser.parse_args()

    # 设置冲突处理策略
    if args.force:
        sure_option = "2"  # 覆盖
    else:
        sure_option = "1"  # 默认保留两份

    skip_existing = not args.no_skip

    log_runtime(f"程序启动。路径={args.path or '交互模式'}，强制覆盖={args.force}，扫码={args.qrcode}")

    # ─── 登录 ───
    print("正在登录 123云盘...")
    log_runtime("开始登录流程...")

    # 检查凭据文件是否存在
    has_credentials = False
    if os.path.exists(config.CREDENTIALS_FILE):
        try:
            with open(config.CREDENTIALS_FILE, "r") as f:
                cred_data = json.loads(f.read())
            if cred_data.get('authorization'):
                has_credentials = True
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    try:
        if args.qrcode:
            # 强制扫码登录（--qr 参数）
            print("\n开始扫码登录（--qr 参数）...")
            log_runtime("--qr 参数强制使用扫码登录")
            pan = Pan123(readfile=False, use_qrcode=True)
        elif has_credentials:
            # 使用已有凭据 — Pan123 会校验 Token 并在失效时自动恢复
            log_runtime("使用 123pan.txt 中保存的凭据")
            pan = Pan123(readfile=True, input_pwd=True)
        else:
            # 未找到凭据，询问用户选择登录方式
            print("\n未找到已保存的凭据，请选择登录方式:")
            print("  1. 账号密码登录")
            print("  2. 扫码登录（使用微信或 123云盘 App 扫码）")
            choice = input("\n请输入选项 (1 或 2): ").strip()
            log_command(f"登录方式选择: {choice}")

            if choice == "2":
                print("\n开始扫码登录...")
                log_runtime("用户选择扫码登录")
                pan = Pan123(readfile=False, use_qrcode=True)
            else:
                log_runtime("用户选择账号密码登录")
                pan = Pan123(readfile=False, input_pwd=True)

        mpush = MPush(pan)
        print("登录成功！")
        log_runtime("登录成功，进入主模式")
    except Exception as e:
        log_error(f"登录失败: {str(e)}")
        print(f"\n登录失败: {str(e)}")
        print(f"错误已记录到 logs/errors/")
        log_exit(f"登录失败: {str(e)}", exit_code=1)

    # ─── 命令行模式（非交互） ───
    if args.path:
        path = normalize_path(args.path)
        log_runtime(f"命令行模式: 正在上传 '{path}'")

        if not validate_upload_path(path):
            log_exit("命令行模式下上传路径无效", exit_code=1)

        dest_name = normalize_path(args.dest) if args.dest else None

        print(format_upload_mode(sure_option, skip_existing))
        execute_upload(mpush, path, sure_option, dest_name, skip_existing)
        log_runtime("命令行模式上传完成，退出")
        return

    # ─── 交互模式 ───
    run_interactive_mode(mpush, sure_option, skip_existing)
    log_runtime("程序正常退出")


if __name__ == "__main__":
    main()
