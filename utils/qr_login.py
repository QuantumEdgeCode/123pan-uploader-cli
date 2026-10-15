#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
123云盘扫码登录模块

基于 API 逆向实现扫码登录流程:
1. 访问登录页获取必要 Cookie（aliyungf_tc）
2. GET /api/user/qr-code/generate 创建二维码会话并获取 URL
3. 展示二维码（URL: https://yun.123pan.cn/wx-app-login.html?uniID=...）
4. 轮询 GET /api/user/qr-code/result 检查扫码状态（loginStatus）
5. 扫码后（loginStatus != 0）POST /api/user/qr-code/wx_code 获取 wechat_code
6. POST /api/user/sign_in 携带 wechat_code（type=4）获取 Token

loginStatus 取值:
  0 = 等待扫码
  1 = 已扫码，等待确认
  2 = 已确认
  3 = 已过期
  4 = 会话无效
"""

import os
import uuid
import time
import socket
import hashlib
import platform
import requests
from datetime import datetime
from tosasitill_123pan import config


# 登录状态常量
LOGIN_STATUS_WAITING = 0
LOGIN_STATUS_SCANNED = 1
LOGIN_STATUS_CONFIRMED = 2
LOGIN_STATUS_EXPIRED = 3
LOGIN_STATUS_NO_SESSION = 4


def _generate_loginuuid():
    """生成持久化设备指纹（64 位十六进制字符串）。

    使用机器主机名 + 用户名生成 SHA-256 哈希，
    同一台机器上跨会话保持稳定。

    返回:
        str: 64 位十六进制字符串
    """
    try:
        username = os.getlogin()
    except OSError:
        username = os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))
    hostname = socket.gethostname()
    os_name = platform.system()
    raw = f"{hostname}:{username}:{os_name}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _generate_uni_id():
    """生成 UUID v4 字符串。

    返回:
        str: UUID 字符串（如 '7e9fd53d-113c-48a6-a97d-0de85de75a8c'）
    """
    return str(uuid.uuid4())


def _build_qr_headers(loginuuid):
    """构建扫码 API 请求头。

    基于 123云盘网页登录抓包结果。

    参数:
        loginuuid: 设备指纹字符串

    返回:
        dict: 请求头字典
    """
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Content-Type': 'application/json',
        'Origin': 'https://user.123pan.cn',
        'Referer': 'https://user.123pan.cn/centerlogin?redirect_url=https%3A%2F%2Fyun.123pan.cn&source_page=website',
        'platform': 'web',
        'app-version': '132',
        'loginuuid': loginuuid,
    }


def _save_qrcode_to_file(qr_url, uni_id, loginuuid):
    """将二维码保存到 qrcode.txt（含 ASCII 图形）和 qrcode.png（图片）。

    同时把二维码 URL 元数据和可扫描的 ASCII 图形二维码写入 qrcode.txt，
    方便用户直接打开文件扫码；
    并保存 PNG 图片 qrcode.png，便于手机扫描。

    参数:
        qr_url: 二维码 URL 字符串
        uni_id: 本次登录会话的服务器端 uniID
        loginuuid: 设备指纹
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构建 ASCII 二维码图形
    ascii_qr = ""
    try:
        import io as _io
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)
        # 将 ASCII 输出捕获到字符串
        buf = _io.StringIO()
        qr.print_ascii(invert=True, out=buf)
        ascii_qr = buf.getvalue()
    except ImportError:
        ascii_qr = "(未安装 qrcode 库，无法渲染 ASCII 二维码)\n"

    content = (
        f"{'=' * 60}\n"
        f"[{timestamp}] 123云盘扫码登录\n"
        f"{'=' * 60}\n"
        f"uniID: {uni_id}\n"
        f"loginuuid: {loginuuid[:16]}...\n"
        f"二维码链接: {qr_url}\n"
        f"{'=' * 60}\n"
        f"请使用微信或 123云盘 App 扫描下方二维码:\n"
        f"{'=' * 60}\n\n"
        f"{ascii_qr}\n"
        f"{'=' * 60}\n"
        f"或在浏览器中打开此链接: {qr_url}\n"
        f"{'=' * 60}\n"
    )
    try:
        with open(config.QRCODE_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  [二维码已保存到 {config.QRCODE_FILE}]")
    except OSError as e:
        print(f"  [警告: 二维码保存到文件失败: {e}]")

    # 同时保存 PNG 图片
    try:
        import qrcode
        qr_img = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr_img.add_data(qr_url)
        qr_img.make(fit=True)
        img = qr_img.make_image(fill_color="black", back_color="white")
        img.save("qrcode.png")
        print(f"  [二维码图片已保存到 qrcode.png]")
    except ImportError:
        pass
    except Exception as e:
        print(f"  [警告: 二维码图片保存失败: {e}]")


def _display_qr_in_terminal(qr_url):
    """在终端中用 qrcode 库显示二维码。

    若 qrcode 库不可用，则回退为打印 URL。

    参数:
        qr_url: 要编码为二维码的 URL 字符串
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)

        print("\n" + "=" * 50)
        print("  请使用微信或 123云盘 App 扫描二维码")
        print("=" * 50 + "\n")
        qr.print_ascii(invert=True)
        print("\n" + "=" * 50)
        print(f"  或访问: {qr_url}")
        print("=" * 50 + "\n")
    except ImportError:
        print("\n" + "=" * 50)
        print("  请使用微信或 123云盘 App 扫描二维码")
        print("=" * 50)
        print(f"  二维码链接: {qr_url}")
        print(f"  （安装 'qrcode' 库可在终端显示二维码）")
        print("=" * 50 + "\n")


def get_qrcode(session, loginuuid):
    """向 123云盘 API 请求二维码。

    调用 GET /api/user/qr-code/generate 创建二维码会话。
    服务器返回新的 uniID 和二维码基础 URL。
    完整二维码 URL 拼接方式: {base_url}?uniID={server_uniID}

    参数:
        session: 带必要 Cookie 的 requests.Session
        loginuuid: 设备指纹字符串

    返回:
        dict: {'success': bool, 'uni_id': str, 'qr_url': str, 'error': str}
    """
    client_uni_id = _generate_uni_id()
    headers = _build_qr_headers(loginuuid)

    try:
        resp = session.get(
            config.URL_QR_CODE_GENERATE,
            params={'uniID': client_uni_id},
            headers=headers,
            timeout=config.TIMEOUT_SHORT
        )
        result = resp.json()
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f"请求失败: {e}"}
    except ValueError as e:
        return {'success': False, 'error': f"响应解析失败: {e}"}

    code = result.get('code', -1)
    if code != 0:
        return {
            'success': False,
            'error': f"API 错误 code={code}: {result.get('message', '未知错误')}"
        }

    data = result.get('data', {})
    server_uni_id = data.get('uniID', '')
    base_url = data.get('url', '')

    if not server_uni_id or not base_url:
        return {
            'success': False,
            'error': f"响应中缺少 uniID 或 url: {result}"
        }

    # 拼接完整二维码 URL
    # env=production 必须保留: wx-app-login.html 通过 envConfig[env] 确定
    # 调用 POST /user/qr-code/scan（通知服务端已扫码）的 API 主机。
    # 缺少 env 时 hostUrl 未定义，扫码不会被注册。
    qr_url = f"{base_url}?uniID={server_uni_id}&env=production"

    return {
        'success': True,
        'uni_id': server_uni_id,
        'qr_url': qr_url,
        'error': None
    }


def poll_qrcode_result(session, uni_id, loginuuid, timeout=None):
    """轮询二维码扫码状态，直到已扫码、已确认或超时。

    调用 GET /api/user/qr-code/result 检查用户是否已扫码并确认。

    当 loginStatus 从 0（等待中）发生变化时，调用
    POST /api/user/qr-code/wx_code 获取 sign_in 所需的 wechat_code。

    参数:
        session: 带必要 Cookie 的 requests.Session
        uni_id: get_qrcode() 返回的服务器端 uniID
        loginuuid: 设备指纹字符串
        timeout: 最长等待秒数（默认: config.QRCODE_TIMEOUT）

    返回:
        dict: {'success': bool, 'wechat_code': str, 'status': int, 'error': str}
    """
    if timeout is None:
        timeout = config.QRCODE_TIMEOUT

    headers = _build_qr_headers(loginuuid)
    params = {
        'uniID': uni_id,
        'remember': 'true',
        'gray': 'true',
    }

    start_time = time.time()
    poll_count = 0
    last_status = -1
    scanned = False

    while time.time() - start_time < timeout:
        poll_count += 1
        try:
            resp = session.get(
                config.URL_QR_CODE_RESULT,
                headers=headers,
                params=params,
                timeout=config.TIMEOUT_SHORT
            )
            result = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"  轮询请求失败（重试中）: {e}")
            time.sleep(0.5 if scanned else config.QRCODE_POLL_INTERVAL)
            continue
        except ValueError as e:
            print(f"  轮询响应解析失败（重试中）: {e}")
            time.sleep(0.5 if scanned else config.QRCODE_POLL_INTERVAL)
            continue

        code = result.get('code', -1)
        if code != 0:
            print(f"  轮询出错: code={code}, message={result.get('message', '')}")
            time.sleep(0.5 if scanned else config.QRCODE_POLL_INTERVAL)
            continue

        data = result.get('data', {})
        login_status = data.get('loginStatus', -1)
        scan_platform = data.get('scanPlatform', 0)

        # 打印状态变化
        if login_status != last_status:
            status_messages = {
                0: "等待扫码...",
                1: "已扫码！等待微信授权确认...",
                2: "已确认！正在获取 wechat_code...",
                3: "二维码已过期",
                4: "会话无效",
            }
            msg = status_messages.get(login_status, f"未知状态: {login_status}")
            print(f"  [{msg}]（平台: {scan_platform}）")
            last_status = login_status

        if login_status == LOGIN_STATUS_NO_SESSION:
            return {
                'success': False,
                'wechat_code': None,
                'status': login_status,
                'error': '会话无效（二维码可能已过期）'
            }

        # 已扫码或已确认时，加快轮询 wx_code（快速模式）
        if login_status in (LOGIN_STATUS_SCANNED, LOGIN_STATUS_CONFIRMED):
            scanned = True
            wx_result = _get_wx_code(session, uni_id, loginuuid)
            if wx_result['success'] and wx_result['wechat_code']:
                print(f"  [已获取 wechat_code！]")
                return {
                    'success': True,
                    'wechat_code': wx_result['wechat_code'],
                    'status': login_status,
                    'error': None
                }
            # wx_code 尚未就绪时继续快速轮询

        # 处理过期情况: 若曾扫码成功，最后再尝试一次 wx_code
        if login_status == LOGIN_STATUS_EXPIRED:
            if scanned:
                print(f"  二维码已过期但曾扫码成功 - 最后尝试一次 wx_code...")
                wx_result = _get_wx_code(session, uni_id, loginuuid)
                if wx_result['success'] and wx_result['wechat_code']:
                    print(f"  [过期后仍成功获取 wechat_code！]")
                    return {
                        'success': True,
                        'wechat_code': wx_result['wechat_code'],
                        'status': login_status,
                        'error': None
                    }
            return {
                'success': False,
                'wechat_code': None,
                'status': login_status,
                'error': '二维码已过期'
            }

        # 定期打印进度
        if poll_count % 15 == 0 and login_status == LOGIN_STATUS_WAITING:
            elapsed = int(time.time() - start_time)
            remaining = int(timeout - elapsed)
            print(f"  仍在等待...（已过 {elapsed}s，剩余 {remaining}s）")

        # 已扫码时快速轮询（0.5s），等待时常规轮询（2s）
        time.sleep(0.5 if scanned else config.QRCODE_POLL_INTERVAL)

    return {
        'success': False,
        'wechat_code': None,
        'status': -1,
        'error': f'扫码超时（{timeout}s）'
    }


def _get_wx_code(session, uni_id, loginuuid):
    """从 wx_code 接口获取 wechat_code。

    调用 POST /api/user/qr-code/wx_code，携带 uniID 获取
    sign_in 所需的 wechat_code。

    参数:
        session: 带必要 Cookie 的 requests.Session
        uni_id: 服务器端 uniID
        loginuuid: 设备指纹字符串

    返回:
        dict: {'success': bool, 'wechat_code': str, 'error': str}
    """
    headers = _build_qr_headers(loginuuid)
    payload = {"uniID": uni_id}

    try:
        resp = session.post(
            config.URL_QR_CODE_WX,
            headers=headers,
            json=payload,
            timeout=config.TIMEOUT_SHORT
        )
        result = resp.json()
    except requests.exceptions.RequestException as e:
        return {'success': False, 'wechat_code': None, 'error': f"请求失败: {e}"}
    except ValueError as e:
        return {'success': False, 'wechat_code': None, 'error': f"响应解析失败: {e}"}

    code = result.get('code', -1)
    if code != 0:
        return {
            'success': False,
            'wechat_code': None,
            'error': f"API 错误 code={code}: {result.get('message', '')}"
        }

    data = result.get('data', {})
    wechat_code = data.get('wxCode', '') or data.get('wechat_code', '')

    if not wechat_code:
        return {
            'success': False,
            'wechat_code': None,
            'error': 'wxCode 为空（扫码可能尚未完成）'
        }

    return {
        'success': True,
        'wechat_code': wechat_code,
        'error': None
    }


def login_with_wechat_code(session, wechat_code, loginuuid):
    """使用扫码获得的 wechat_code 登录 123云盘。

    调用 POST /api/user/sign_in，携带 wechat_code 和 type=4（微信登录）。

    参数:
        session: 带必要 Cookie 的 requests.Session
        wechat_code: 扫码获得的 code
        loginuuid: 设备指纹字符串

    返回:
        dict: {'success': bool, 'token': str, 'error': str}
    """
    headers = _build_qr_headers(loginuuid)
    payload = {
        "from": "web",
        "wechat_code": wechat_code,
        "type": 4,
        "remember": True,
        "gray": True,
    }

    try:
        resp = session.post(
            config.URL_SIGN_IN,
            headers=headers,
            json=payload,
            timeout=config.TIMEOUT_MEDIUM
        )
        result = resp.json()
    except requests.exceptions.RequestException as e:
        return {'success': False, 'token': None, 'error': f"请求失败: {e}"}
    except ValueError as e:
        return {'success': False, 'token': None, 'error': f"响应解析失败: {e}"}

    code = result.get('code', -1)
    # 123云盘 sign_in 接口: 扫码登录成功返回 code=0（账号密码登录返回 code=200）
    if code not in (0, 200):
        return {
            'success': False,
            'token': None,
            'error': f"登录失败（code={code}）: {result.get('message', '未知错误')}"
        }

    data = result.get('data', {})

    # 尝试从 JSON 响应中获取 Token
    token = data.get('token', '')

    # JSON 中没有时，尝试从 Cookie 获取
    if not token:
        token = resp.cookies.get('sso-token', '')

    # 仍未找到时，尝试响应头（set-cookie）
    if not token:
        set_cookie = resp.headers.get('set-cookie', '')
        if 'sso-token=' in set_cookie:
            import re
            match = re.search(r'sso-token=([^;]+)', set_cookie)
            if match:
                token = match.group(1)

    if not token:
        return {
            'success': False,
            'token': None,
            'error': f"登录响应中没有 Token。完整响应: {result}"
        }

    # 清理 Token（如有 'Bearer ' 前缀则移除）
    if token.startswith('Bearer '):
        token = token[7:]

    return {
        'success': True,
        'token': token,
        'error': None
    }


def qr_login(timeout=None):
    """执行完整的扫码登录流程。

    这是扫码登录的主入口，流程:
    1. 生成设备指纹
    2. 访问登录页获取必要 Cookie
    3. 从 API 获取二维码（GET /api/user/qr-code/generate）
    4. 将二维码保存到 qrcode.txt（带时间戳）
    5. 在终端显示二维码
    6. 轮询扫码状态（GET /api/user/qr-code/result）
    7. 获取 wechat_code（POST /api/user/qr-code/wx_code）
    8. 使用 wechat_code 登录（POST /api/user/sign_in）

    参数:
        timeout: 等待扫码的最长秒数（默认: config.QRCODE_TIMEOUT）

    返回:
        dict: {'success': bool, 'token': str, 'loginuuid': str, 'error': str}
    """
    print("\n" + "=" * 60)
    print("  123云盘扫码登录")
    print("=" * 60)

    # 步骤 1: 生成设备指纹
    loginuuid = _generate_loginuuid()
    print(f"  [1/5] 设备 ID 已生成: {loginuuid[:16]}...")

    # 步骤 2: 创建会话并访问登录页获取 Cookie
    print(f"  [2/5] 正在初始化会话...")
    session = requests.Session()
    try:
        session.get(
            config.LOGIN_PAGE_URL,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            timeout=config.TIMEOUT_SHORT
        )
    except requests.exceptions.RequestException as e:
        print(f"  [警告: 无法访问登录页: {e}]")

    # 步骤 3: 获取二维码
    print(f"  [3/5] 正在请求二维码...")
    qr_result = get_qrcode(session, loginuuid)
    if not qr_result['success']:
        print(f"  [错误] 获取二维码失败: {qr_result['error']}")
        return {'success': False, 'token': None, 'loginuuid': loginuuid, 'error': qr_result['error']}

    uni_id = qr_result['uni_id']
    qr_url = qr_result['qr_url']

    # 保存二维码到文件
    _save_qrcode_to_file(qr_url, uni_id, loginuuid)

    # 在终端显示二维码
    _display_qr_in_terminal(qr_url)

    # 步骤 4: 轮询扫码状态
    print(f"  [4/5] 监听扫码中（超时: {timeout or config.QRCODE_TIMEOUT}s）...")
    poll_result = poll_qrcode_result(session, uni_id, loginuuid, timeout)
    if not poll_result['success']:
        print(f"  [错误] {poll_result['error']}")
        return {'success': False, 'token': None, 'loginuuid': loginuuid, 'error': poll_result['error']}

    wechat_code = poll_result['wechat_code']

    # 步骤 5: 使用 wechat_code 登录
    print(f"  [5/5] 正在使用 wechat_code 登录...")
    login_result = login_with_wechat_code(session, wechat_code, loginuuid)
    if not login_result['success']:
        print(f"  [错误] 登录失败: {login_result['error']}")
        return {'success': False, 'token': None, 'loginuuid': loginuuid, 'error': login_result['error']}

    token = login_result['token']
    print(f"\n  登录成功！Token: {token[:20]}...")
    print("=" * 60 + "\n")

    return {
        'success': True,
        'token': token,
        'loginuuid': loginuuid,
        'error': None
    }
