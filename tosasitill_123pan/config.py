#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

# 123云盘 API 地址与配置常量（集中管理）
# 更新: 2026-07-03 — 已迁移到新 API 架构（user.123pan.cn）

# 基础地址
BASE_URL = "https://www.123pan.cn"
LOGIN_URL = "https://user.123pan.cn"

# 认证接口（新: user.123pan.cn，JSON 请求体，无需签名）
URL_SIGN_IN = f"{LOGIN_URL}/api/user/sign_in"

# 扫码登录接口
URL_QR_CODE_GENERATE = f"{LOGIN_URL}/api/user/qr-code/generate"
URL_QR_CODE_WX = f"{LOGIN_URL}/api/user/qr-code/wx_code"
URL_QR_CODE_RESULT = f"{LOGIN_URL}/api/user/qr-code/result"
URL_TOKEN_VERIFY = f"{LOGIN_URL}/api/user/token/verify"

# 扫码登录页面地址（访问该页面以获取 Cookie）
LOGIN_PAGE_URL = f"{LOGIN_URL}/centerlogin?redirect_url=https%3A%2F%2Fyun.123pan.cn&source_page=website"

# 扫码登录文件
QRCODE_FILE = "qrcode.txt"

# 二维码轮询间隔（秒）
QRCODE_POLL_INTERVAL = 2
# 二维码超时时间（秒，默认 120 秒）
QRCODE_TIMEOUT = 120

# 文件操作接口（Bearer Token 认证，无需签名）
URL_FILE_LIST = f"{BASE_URL}/b/api/file/list/new"
URL_UPLOAD_REQUEST = f"{BASE_URL}/b/api/file/upload_request"
URL_S3_PREPARE_PARTS = f"{BASE_URL}/b/api/file/s3_repare_upload_parts_batch"
# 单分片（≤16MB）取上传链接接口
URL_S3_UPLOAD_AUTH = f"{BASE_URL}/b/api/file/s3_upload_object/auth"
# 官方新版上传完成接口（2026-10 实测：文件落地的关键，旧版完成链已失效）
URL_UPLOAD_COMPLETE_V2 = f"{BASE_URL}/b/api/file/upload_complete/v2"

# 旧版上传接口（2026-10 起服务端不再完整支持：调用返回成功但不落地文件，
# 部分环境还会报 session_expired，勿再使用，仅作参考）
URL_S3_LIST_PARTS = f"{BASE_URL}/b/api/file/s3_list_upload_parts"
URL_S3_COMPLETE_MULTIPART = f"{BASE_URL}/b/api/file/s3_complete_multipart_upload"
URL_UPLOAD_COMPLETE = f"{BASE_URL}/b/api/file/upload_complete"
URL_BATCH_DOWNLOAD_INFO = f"{BASE_URL}/a/api/file/batch_download_info"
URL_DOWNLOAD_INFO = f"{BASE_URL}/a/api/file/download_info"
URL_FILE_TRASH = f"{BASE_URL}/a/api/file/trash"
URL_SHARE_CREATE = f"{BASE_URL}/a/api/share/create"

# HTTP 请求超时（秒）
TIMEOUT_SHORT = 10      # 快速接口调用（登录、创建目录等）
TIMEOUT_MEDIUM = 30      # 常规接口调用（文件列表、上传请求等）
TIMEOUT_LONG = 60        # 大文件操作（下载、上传完成等）
TIMEOUT_UPLOAD_PART = 120 # 每个分片（16MB）上传到预签名 URL 的超时

# 配置文件
CREDENTIALS_FILE = "123pan.txt"
HISTORY_FILE = "~/.123pan_history"

# 日志目录（三类日志: 命令、运行、错误）
LOG_DIR = "logs"
LOG_DIR_COMMANDS = os.path.join(LOG_DIR, "commands")
LOG_DIR_RUNTIME = os.path.join(LOG_DIR, "runtime")
LOG_DIR_ERRORS = os.path.join(LOG_DIR, "errors")

# 上传默认值
DEFAULT_BLOCK_SIZE = 16 * 1024 * 1024  # 16MB 分片（与官方 Web 端一致）
DEFAULT_MAX_WORKERS = 5                # 并发上传线程数

# 下载默认值
DEFAULT_DOWNLOAD_THREADS = 8
