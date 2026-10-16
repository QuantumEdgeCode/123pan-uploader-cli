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

# 上传完成接口（2026-10-16 远程实测，2×2 矩阵已全覆盖）:
#   URL_UPLOAD_COMPLETE_V2（主力）：body 需带 StorageNode/bucket/fileId/fileSize/
#       isMultipart/key/uploadId。单分片与多分片**均真正落地**，响应 data.file_info
#       带回落地后的 FileId/Etag/Size（实测 3~5 秒内即可在目录里查到）。
#   URL_UPLOAD_COMPLETE (v1)（兜底）：body 只有 {"fileId": ...}。
#       **仅单分片（≤16MB）有效**，响应 data.Info 里含落地信息；
#       对**多分片**会返回 code=0 但 data={} 的**假成功**，实测 60 秒内、乃至永久
#       都不落地、记录状态仍是未完成 —— 切不可依据 code=0 判定上传成功。
#   另：响应报 `非法请求(uid_mismatch)` 表示该文件的预上传记录属于另一次登录
#       （换账号/换登录方式后遗留），本会话收不了尾；与出口 IP、payload 字段、
#       key 里的 uid 段均无关（这三点都已实测排除）。
URL_UPLOAD_COMPLETE = f"{BASE_URL}/b/api/file/upload_complete"
URL_UPLOAD_COMPLETE_V2 = f"{BASE_URL}/b/api/file/upload_complete/v2"

# 已废弃的上传接口（2026-10-16 实测：s3_list_upload_parts 返回 非法请求(session_expired)，
# s3_complete_multipart_upload 返回 S3 MalformedXML，均不可用，保留常量仅供排查参考）
URL_S3_LIST_PARTS = f"{BASE_URL}/b/api/file/s3_list_upload_parts"
URL_S3_COMPLETE_MULTIPART = f"{BASE_URL}/b/api/file/s3_complete_multipart_upload"
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

# 分片上传的抗瞬断参数（存储节点偶发 TCP RST / TLS 中断时自愈）
# 背景: requests 默认零重试，存储节点偶发 errno 104 或 SSLEOFError
#       会让一个已经传了几百片的大文件直接作废
UPLOAD_RETRY_TOTAL = 5          # 单个 HTTP 请求的总重试次数（含连接/读取/其他错误）
UPLOAD_RETRY_BACKOFF = 0.6      # 退避因子: 0.6s, 1.2s, 2.4s, 4.8s, 9.6s
UPLOAD_RETRY_STATUS = (500, 502, 503, 504)  # 需要重试的服务端错误码
# 注意: 403 表示预签名链接过期，重发同一链接无用，必须重新申请链接，
#       故不放入上面的重试状态码，改由 _upload_one_part 的换链接重试处理
UPLOAD_PART_ATTEMPTS = 3        # 单个分片的完整尝试轮数（每轮内部还含上面的重试）
UPLOAD_SESSION_POOL = 10        # 上传会话连接池大小（必须 >= UPLOAD_PART_CONCURRENCY）
UPLOAD_PART_CONCURRENCY = 4     # 批内并发上传的分片数（1 = 退回完全串行）
# 收尾后回查目录、确认文件真的落地的参数（防止「接口返回 code=0 但文件没上来」）
# 实测云盘目录列表存在「秒级到十几秒」的延迟，窗口给足，避免把「还没刷出来」误判成失败
UPLOAD_VERIFY_ATTEMPTS = 8      # 回查次数（每个收尾接口各自重试这么多轮）
UPLOAD_VERIFY_INTERVAL = 2.0    # 每次回查之间的间隔（秒）
# 说明: 预签名链接有效期仅 10 分钟（X-Amz-Expires=600）。原先一次申请 10 个链接
#       却串行上传，慢链路下单批耗时可能超过 10 分钟，导致后几个链接过期报 403。
#       批内并发后单批耗时降到约 1/4，大幅降低 403 概率。

# 下载默认值
DEFAULT_DOWNLOAD_THREADS = 8
