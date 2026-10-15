#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time
import os
import json
import base64
import requests
from . import config
from utils.logger import log_runtime, log_error


class Pan123:
    """123云盘客户端

    该类提供与 123云盘服务交互的方法。
    功能包括登录、文件列表、上传、下载和目录管理。

    登录流程:
        1. 如果 123pan.txt 存在，加载已保存 Token 并通过 get_dir() 校验
        2. 如果 Token 无效（get_dir 失败）:
           a. 如果保存了 userName/passWord → 用账号密码重新登录（仅一次）
           b. 如果没有凭据（扫码登录）→ 抛出异常，程序退出
        3. 如果 123pan.txt 不存在:
           a. use_qrcode=True → 扫码登录
           b. 否则 → 提示输入账号密码

    参数:
        readfile: 为 True 时从 123pan.txt 文件读取凭据（默认: True）
        user_name: 登录用户名（readfile=False 时使用）
        pass_word: 登录密码（readfile=False 时使用）
        authorization: 用于认证的 Bearer Token（可选）
        input_pwd: 为 True 时在凭据不可用时提示输入（默认: True）
        use_qrcode: 为 True 时使用扫码登录代替账号密码登录（默认: False）

    抛出:
        Exception: 登录失败且没有恢复途径时（Token 无效、
                   没有可重新登录的凭据、或扫码登录失败）
    """

    _header_base = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Content-Type': 'application/json',
        'Origin': 'https://yun.123pan.cn',
        'Referer': 'https://yun.123pan.cn/',
        'platform': 'web',
        'App-Version': '3',
    }

    _header_authenticated_template = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "App-Version": "3",
        "Authorization": "",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Origin": "https://yun.123pan.cn",
        "Referer": "https://yun.123pan.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "platform": "web",
        "Content-Type": "application/json",
    }

    def __init__(self, readfile=True, user_name="", pass_word="", authorization="", input_pwd=True, use_qrcode=False):
        """初始化 Pan123 客户端，完成登录和 Token 校验。

        初始化流程处理三种场景:
        1. 扫码登录（use_qrcode=True）: 执行扫码登录，无需凭据
        2. 从文件读取（readfile=True）: 加载已保存 Token 并校验，
           Token 无效且存在账号密码时尝试重新登录
        3. 手动凭据（readfile=False）: 使用传入或提示输入的凭据

        如果登录失败且无法恢复，会抛出 Exception，
        导致程序以错误信息退出。

        参数:
            readfile: 为 True 时从 123pan.txt 读取凭据（默认: True）
            user_name: 登录用户名（readfile=False 时使用）
            pass_word: 登录密码（readfile=False 时使用）
            authorization: 用于认证的 Bearer Token（可选）
            input_pwd: 为 True 时在凭据不可用时提示输入（默认: True）
            use_qrcode: 为 True 时使用扫码登录（默认: False）

        抛出:
            Exception: Token 无效且没有可用的密码凭据重新登录，
                       或扫码/密码登录失败时
        """
        self.RecycleList = None
        self.list = None
        self.userName = ""
        self.passWord = ""
        self.authorization = ""
        self._is_qr_login = False  # 记录当前会话是否为扫码登录

        if use_qrcode:
            # 扫码登录流程：无需用户名/密码
            self._is_qr_login = True
            self.login_qrcode()
        elif readfile:
            self.read_ini(user_name, pass_word, input_pwd, authorization)
            # 判断是否为纯扫码登录（未保存密码）
            if not self.userName and not self.passWord and self.authorization:
                self._is_qr_login = True
        else:
            if user_name == "" or pass_word == "":
                print("读取已禁用，用户名或密码为空")
                if input_pwd:
                    user_name = input("请输入用户名:")
                    pass_word = input("请输入密码:")
                else:
                    raise Exception("用户名或密码为空: 禁用读取时，userName 与 passWord 不能为空")
            self.userName = user_name
            self.passWord = pass_word
            self.authorization = authorization

        self.headerOnlyUsage = self._header_base.copy()
        self.headerLogined = self._build_auth_header()
        self.parentFileId = 0
        self.parentFileList = [0]

        # 通过调用 get_dir() 校验 Token
        code = self.get_dir()
        if code != 0:
            # Token 无效或已过期
            log_error(f"Token 校验失败（get_dir code={code}），尝试恢复登录...")

            if self._is_qr_login:
                # 扫码登录：未保存密码，无法自动恢复
                msg = ("Token 无效或已过期。本次会话使用扫码登录（未保存密码），"
                       "请使用 --qr 参数重新运行并扫描新的二维码。")
                log_error(msg)
                raise Exception(msg)
            elif self.userName and self.passWord:
                # 存在账号密码：尝试重新登录（仅一次）
                log_runtime("Token 无效，尝试使用账号密码重新登录...")
                print("Token 已过期，使用已保存的凭据重新登录...")
                login_code = self.login()
                if login_code != 200:
                    msg = f"账号密码重新登录失败（code={login_code}），程序即将退出。"
                    log_error(msg)
                    raise Exception(msg)
                log_runtime("账号密码重新登录成功。")
                # 重新登录后重试 get_dir
                code = self.get_dir()
                if code != 0:
                    msg = f"重新登录后 get_dir 仍然失败（code={code}），程序即将退出。"
                    log_error(msg)
                    raise Exception(msg)
            else:
                # 没有任何凭据
                msg = ("Token 无效且没有可用的登录凭据，"
                       "请使用 --qr 参数重新运行，或提供账号密码。")
                log_error(msg)
                raise Exception(msg)

    def _build_auth_header(self):
        header = self._header_authenticated_template.copy()
        header["Authorization"] = self.authorization
        return header

    def _update_auth_header(self):
        self.authorization = getattr(self, 'authorization', '')
        self.headerLogined = self._build_auth_header()

    def login_qrcode(self):
        """使用扫码方式登录 123云盘

        该方法使用微信/123云盘 App 扫码登录流程，无需用户名和密码，
        用户使用微信或 123云盘 App 扫描二维码完成认证。

        二维码数据会带时间戳保存到 qrcode.txt。
        方法会轮询扫码状态并自动获取 Token。

        返回:
            bool: 登录成功返回 True

        抛出:
            Exception: 扫码登录失败时（超时、过期、网络错误）
        """
        from utils.qr_login import qr_login

        log_runtime("开始扫码登录...")
        result = qr_login()
        if not result['success']:
            msg = f"扫码登录失败: {result.get('error', '未知错误')}"
            log_error(msg)
            raise Exception(msg)

        token = result['token']
        self.authorization = 'Bearer ' + token
        self.userName = ""
        self.passWord = ""
        self._is_qr_login = True
        self._update_auth_header()
        self.save_file()
        log_runtime("扫码登录成功。")
        return True

    def login(self):
        """使用 123云盘账号密码认证并获取 Bearer Token

        使用已保存的 userName 和 passWord，通过
        POST /api/user/sign_in 以 JSON 请求体进行认证。

        返回:
            int: 响应码（200 表示成功，其他值表示失败）
        """
        log_runtime(f"尝试账号密码登录，用户: {self.userName}")
        data = {"remember": True, "passport": self.userName, "password": self.passWord}
        try:
            loginRes = requests.post(
                config.URL_SIGN_IN,
                headers=self.headerOnlyUsage,
                json=data,
                timeout=config.TIMEOUT_SHORT
            )
            res = loginRes.json()
        except requests.exceptions.RequestException as e:
            log_error(f"登录请求失败: {e}")
            return -1
        except ValueError as e:
            log_error(f"登录响应解析失败: {e}")
            return -1

        code = res.get('code', -1)
        if code != 200:
            log_error(f"登录失败: code={code}, message={res.get('message', '')}")
            return code
        token = res['data']['token']
        self.authorization = 'Bearer ' + token
        self._is_qr_login = False  # 账号密码登录，可自动恢复
        self._update_auth_header()
        self.save_file()
        log_runtime("账号密码登录成功。")
        return code

    def save_file(self):
        """保存凭据和授权 Token 到 123pan.txt 文件。

        扫码登录时 userName 和 passWord 为空字符串；
        账号密码登录时保存全部三个字段。
        """
        try:
            with open(config.CREDENTIALS_FILE, "w") as f:
                saveList = {
                    "userName": self.userName,
                    "passWord": self.passWord,
                    "authorization": self.authorization,
                }
                f.write(json.dumps(saveList))
            log_runtime(f"凭据已保存到 {config.CREDENTIALS_FILE}")
        except OSError as e:
            log_error(f"保存凭据失败: {e}")

    def get_dir(self, _recursion_depth=0):
        """获取当前目录的文件列表

        从 123云盘分页获取文件列表。包含 IP 封禁检测，
        若被封禁会在 20 秒后自动重试。

        参数:
            _recursion_depth: 内部计数器，防止无限递归（最多重试 3 次）

        返回:
            int: 响应码（0 表示成功，其他值表示失败）
        """
        if _recursion_depth >= 3:
            print("get_dir: 已达到最大重试次数，放弃")
            return -1

        code = 0
        page = 1
        lists = []
        lenth_now = 0
        total = -1
        while lenth_now < total or total == -1:
            params = {
                "driveId": 0,
                "limit": 100,
                "next": 0,
                "orderBy": "file_id",
                "orderDirection": "desc",
                "parentFileId": str(self.parentFileId),
                "trashed": False,
                "SearchData": "",
                "Page": str(page),
                "OnlyLookAbnormalFile": 0
            }

            try:
                a = requests.get(config.URL_FILE_LIST, headers=self.headerLogined, params=params, timeout=config.TIMEOUT_MEDIUM)
            except requests.exceptions.RequestException as e:
                print(f"get_dir: 请求失败: {e}")
                return -1

            try:
                text = a.json()
            except ValueError as e:
                print(f"get_dir: 响应解析失败: {e}")
                return -1

            code = text['code']
            if code != 0:
                print(f"get_dir: 错误 code={code}: {a.text}")
                if code == 403:
                    print("get_dir: IP 被封禁，休眠 20 秒...")
                    time.sleep(20)
                    return self.get_dir(_recursion_depth=_recursion_depth + 1)
                return code
            lists_page = text['data']['InfoList']
            lists += lists_page
            total = text['data']['Total']
            lenth_now += len(lists_page)
            page += 1

        for i, item in enumerate(lists):
            item["FileNum"] = i

        self.list = lists
        return code

    def show(self):
        """显示当前目录列表，包含文件编号、大小和名称"""
        print("--------------------")
        for i in self.list:
            size = i["Size"]
            if size > 1048576:
                size_print = str(round(size / 1048576, 2)) + "M"
            else:
                size_print = str(round(size / 1024, 2)) + "K"

            if i["Type"] == 0:
                print("\033[33m" + "编号:", self.list.index(i) + 1, "\033[0m \t\t" + size_print + "\t\t\033[36m",
                      i["FileName"], "\033[0m")
            elif i["Type"] == 1:
                print("\033[35m" + "编号:", self.list.index(i) + 1, " \t\t\033[36m",
                      i["FileName"], "\033[0m")

        print("--------------------")

    def link(self, file_number, showlink=True):
        """获取文件的下载链接

        参数:
            file_number: 当前目录列表中的文件编号（从 0 开始）
            showlink: 为 True 时打印下载链接（默认: True）

        返回:
            str: 直链下载地址，失败时返回错误码
        """
        fileDetail = self.list[file_number]
        typeDetail = fileDetail['Type']
        if typeDetail == 1:
            down_request_url = config.URL_BATCH_DOWNLOAD_INFO
            down_request_data = {"fileIdList": [{"fileId": int(fileDetail["FileId"])}]}
        else:
            down_request_url = config.URL_DOWNLOAD_INFO
            down_request_data = {
                "driveId": 0, "etag": fileDetail["Etag"], "fileId": fileDetail["FileId"],
                "s3keyFlag": fileDetail['S3KeyFlag'], "type": fileDetail['Type'],
                "fileName": fileDetail['FileName'], "size": fileDetail['Size']
            }

        try:
            linkRes = requests.post(
                down_request_url,
                headers=self.headerLogined,
                json=down_request_data,
                timeout=config.TIMEOUT_MEDIUM
            )
            res_json = linkRes.json()
        except requests.exceptions.RequestException as e:
            print(f"link: 请求失败: {e}")
            return -1
        except ValueError as e:
            print(f"link: 响应解析失败: {e}")
            return -1

        code = res_json['code']
        if code != 0:
            print(f"link: 错误 code={code}")
            return code

        downloadLinkBase64 = res_json["data"]["DownloadUrl"]
        Base64Url = re.findall("params=(.*)&", downloadLinkBase64)[0]
        downLoadUrl = base64.b64decode(Base64Url).decode("utf-8")

        try:
            nextToGet = requests.get(downLoadUrl, timeout=config.TIMEOUT_SHORT).json()
        except requests.exceptions.RequestException as e:
            print(f"link: 获取重定向地址失败: {e}")
            return -1

        redirect_url = nextToGet['data']['redirect_url']
        if showlink:
            print(redirect_url)

        return redirect_url

    def download(self, file_number):
        """从 123云盘下载文件

        参数:
            file_number: 当前目录列表中的文件编号（从 0 开始）
        """
        fileDetail = self.list[file_number]
        downLoadUrl = self.link(file_number, showlink=False)
        name = fileDetail['FileName']
        if os.path.exists(name):
            print(f"文件 {name} 已存在，是否覆盖？")
            sure = input("输入 1 覆盖，输入 2 取消: ")
            if sure != '1':
                return
        try:
            down = requests.get(downLoadUrl, stream=True, timeout=config.TIMEOUT_LONG)
        except requests.exceptions.RequestException as e:
            print(f"download: 请求失败: {e}")
            return

        size = int(down.headers['content-length'])
        content_size = int(size)
        data_count = 0
        if size > 1048576:
            size_print = str(round(size / 1048576, 2)) + "M"
        else:
            size_print = str(round(size / 1024, 2)) + "K"
        print(name + "    " + size_print)
        time1 = time.time()
        time_temp = time1
        data_count_temp = 0
        with open(name, "wb") as f:
            for i in down.iter_content(1024):
                f.write(i)
                done_block = int((data_count / content_size) * 50)
                data_count = data_count + len(i)
                now_jd = (data_count / content_size) * 100
                time1 = time.time()
                pass_time = time1 - time_temp
                if pass_time > 1:
                    time_temp = time1
                    pass_data = int(data_count) - int(data_count_temp)
                    data_count_temp = data_count
                    speed = pass_data / int(pass_time)
                    speed_M = speed / 1048576
                    if speed_M > 1:
                        speed_print = str(round(speed_M, 2)) + "M/S"
                    else:
                        speed_print = str(round(speed_M * 1024, 2)) + "K/S"
                    print(
                        "\r [%s%s] %d%%  %s" % (done_block * '█', ' ' * (50 - 1 - done_block), now_jd, speed_print),
                        end="")
                elif data_count == content_size:
                    print("\r [%s%s] %d%%  %s" % (50 * '█', '', 100, ""), end="")
        print("\n完成")

    def recycle(self):
        """获取回收站文件列表"""
        url = f"{config.BASE_URL}/b/api/file/list/new?driveId=0&limit=100&next=0&orderBy=fileId&orderDirection=desc&parentFileId=0&trashed=true&Page=1"
        try:
            recycleRes = requests.get(url, headers=self.headerLogined, timeout=config.TIMEOUT_MEDIUM)
            jsonRecycle = recycleRes.json()
            self.RecycleList = jsonRecycle['data']['InfoList']
        except requests.exceptions.RequestException as e:
            print(f"recycle: 请求失败: {e}")
        except (KeyError, ValueError) as e:
            print(f"recycle: 响应解析失败: {e}")

    def delete_file(self, file, by_num=True, operation=True):
        """删除或恢复文件

        参数:
            file: 文件编号（从 0 开始）或文件详情对象
            by_num: 为 True 时 file 是编号；为 False 时 file 是详情对象
            operation: True 表示删除，False 表示恢复
        """
        if by_num:
            if not str(file).isdigit():
                print("请输入数字")
                return -1
            if 0 <= file < len(self.list):
                file_detail = self.list[file]
            else:
                print("超出有效范围")
                return
        else:
            if file in self.list:
                file_detail = file
            else:
                print("未找到文件")
                return

        dataDelete = {
            "driveId": 0,
            "fileTrashInfoList": file_detail,
            "operation": operation
        }
        try:
            deleteRes = requests.post(
                config.URL_FILE_TRASH,
                headers=self.headerLogined,
                json=dataDelete,
                timeout=config.TIMEOUT_SHORT
            )
            DeleJson = deleteRes.json()
            print(DeleJson)
            print(DeleJson.get('message', ''))
        except requests.exceptions.RequestException as e:
            print(f"delete_file: 请求失败: {e}")
        except ValueError as e:
            print(f"delete_file: 响应解析失败: {e}")

    def list_files_recursive(self, start_parent_id=None, _files=None, _base_path=""):
        """递归遍历目录及子目录，收集每个文件的 Etag/MD5 校验值

        从当前目录或指定目录开始，递归遍历整个目录树，
        收集每个文件的信息（包括 123云盘 API 返回的 Etag/MD5 哈希值）。
        操作完成后会自动恢复导航状态（parentFileId、parentFileList）。

        参数:
            start_parent_id: 起始目录 ID（None 表示从当前目录开始）
            _files: 递归内部累加器（外部不要传入）
            _base_path: 递归内部路径追踪（外部不要传入）

        返回:
            list[dict]: 文件信息列表，每项包含:
                - FileName: 文件名
                - Etag: MD5 校验值（不可用则为空字符串）
                - Size: 文件大小（字节）
                - SizeHuman: 可读的大小字符串
                - FileId: 123云盘的文件 ID
                - S3KeyFlag: 存储标识
                - Type: 文件类型（0=文件）
                - FilePath: 相对于起始目录的路径
        """
        # 保存当前导航状态，结束后恢复
        saved_parent_file_id = self.parentFileId
        saved_parent_file_list = self.parentFileList.copy()

        try:
            # 如果指定了起始目录，先导航过去
            if start_parent_id is not None:
                self.parentFileId = start_parent_id
                self.parentFileList = [start_parent_id]

            if _files is None:
                _files = []

            # 获取当前目录的文件列表
            code = self.get_dir()
            if code != 0:
                print(f"警告: list_files_recursive: get_dir 返回 code={code}")
                return _files

            if self.list is None:
                return _files

            for item in self.list:
                if item.get("Type") == 0:
                    # 普通文件
                    size = item.get("Size", 0)
                    if size > 1073741824:
                        size_human = f"{size / 1073741824:.2f} GB"
                    elif size > 1048576:
                        size_human = f"{size / 1048576:.2f} MB"
                    elif size > 1024:
                        size_human = f"{size / 1024:.2f} KB"
                    else:
                        size_human = f"{size} B"

                    _files.append({
                        "FileName": item.get("FileName", ""),
                        "Etag": item.get("Etag", ""),
                        "Size": size,
                        "SizeHuman": size_human,
                        "FileId": item.get("FileId", ""),
                        "S3KeyFlag": item.get("S3KeyFlag", 0),
                        "Type": 0,
                        "FilePath": _base_path,
                    })

                elif item.get("Type") == 1:
                    # 子目录 —— 递归遍历
                    dir_id = item.get("FileId")
                    dir_name = item.get("FileName", "")
                    sub_path = f"{_base_path}/{dir_name}" if _base_path else f"/{dir_name}"
                    self.list_files_recursive(
                        start_parent_id=dir_id,
                        _files=_files,
                        _base_path=sub_path,
                    )

        finally:
            # 恢复导航状态
            self.parentFileId = saved_parent_file_id
            self.parentFileList = saved_parent_file_list
            self.get_dir()

        return _files

    def share(self):
        """为所选文件创建分享链接"""
        fileIdList = ""
        share_name_list = []
        add = '1'
        while str(add) == '1':
            share_num = input("请输入要分享的文件编号: ")
            num_test2 = share_num.isdigit()
            if num_test2:
                share_num = int(share_num)
                if 0 < share_num < len(self.list) + 1:
                    share_id = self.list[int(share_num) - 1]['FileId']
                    share_name = self.list[int(share_num) - 1]['FileName']
                    share_name_list.append(share_name)
                    print(share_name_list)
                    fileIdList = fileIdList + str(share_id) + ","
                    add = input("输入 1 继续添加文件，输入 0 创建分享，其他取消: ")
            else:
                print("请输入数字")
                add = "1"

        if str(add) == "0":
            sharePwd = input("提取码（留空表示无提取码）: ")
            fileIdList = fileIdList.strip(',')
            data = {
                "driveId": 0,
                "expiration": "2030-12-31T23:59:59+08:00",
                "fileIdList": fileIdList,
                "shareName": "My Share",
                "sharePwd": sharePwd,
            }
            try:
                shareRes = requests.post(
                    config.URL_SHARE_CREATE,
                    headers=self.headerLogined,
                    json=data,
                    timeout=config.TIMEOUT_SHORT
                )
                shareResJson = shareRes.json()
                message = shareResJson.get('message', '')
                print(message)
                ShareKey = shareResJson['data']['ShareKey']
                share_url = f"{config.BASE_URL}/s/{ShareKey}"
                print(f"分享链接:\n{share_url} 提取码: {sharePwd}")
            except requests.exceptions.RequestException as e:
                print(f"share: 请求失败: {e}")
            except (KeyError, ValueError) as e:
                print(f"share: 响应解析失败: {e}")
        else:
            print("已取消分享")

    def cd(self, dir_num):
        """切换当前目录

        参数:
            dir_num: 目录编号（从 1 开始），'..' 返回上级，'/' 回到根目录
        """
        if not dir_num.isdigit():
            if dir_num == "..":
                if len(self.parentFileList) > 1:
                    self.parentFileList.pop()
                    self.parentFileId = self.parentFileList[-1]
                    self.get_dir()
                    self.show()
                else:
                    print("已在根目录")
                return
            elif dir_num == "/":
                self.parentFileId = 0
                self.parentFileList = [0]
                self.get_dir()
                self.show()
                return
            else:
                print("输入无效")
                return
        dir_num = int(dir_num) - 1
        if dir_num >= (len(self.list) - 1) or dir_num < 0:
            print("输入无效")
            return
        if self.list[dir_num]['Type'] != 1:
            print("不是文件夹")
            return
        self.parentFileId = self.list[dir_num]['FileId']
        self.parentFileList.append(self.parentFileId)
        self.get_dir()
        self.show()

    def cdById(self, id, _recursion_depth=0):
        """按文件夹 ID 切换当前目录

        参数:
            id: 要进入的文件夹 ID
            _recursion_depth: 内部计数器，防止 get_dir() 重试导致的无限递归
        """
        if _recursion_depth >= 3:
            print("cdById: 已达到最大重试次数，放弃")
            return
        self.parentFileId = id
        self.parentFileList.append(self.parentFileId)
        code = self.get_dir(_recursion_depth=_recursion_depth)
        self.show()
        if code != 0:
            print(f"cdById: 警告 - get_dir 返回 code {code}")

    def read_ini(self, user_name, pass_word, input_pwd, authorization=""):
        """从 123pan.txt 配置文件读取凭据

        参数:
            user_name: 文件读取失败时使用的默认用户名
            pass_word: 文件读取失败时使用的默认密码
            input_pwd: 为 True 时在文件不存在时提示输入凭据
            authorization: 默认授权 Token
        """
        try:
            with open(config.CREDENTIALS_FILE, "r") as f:
                text = f.read()
            text = json.loads(text)
            user_name = text['userName']
            pass_word = text['passWord']
            authorization = text['authorization']
        except (FileNotFoundError, json.decoder.JSONDecodeError, KeyError):
            print("读取失败")

            if user_name == "" or pass_word == "":
                if input_pwd:
                    user_name = input("用户名:")
                    pass_word = input("密码:")
                    authorization = ""
                else:
                    raise Exception("输入模式已禁用，且没有用户名或密码")

        self.userName = user_name
        self.passWord = pass_word
        self.authorization = authorization

    def mkdir(self, dirname, parentFileId=None, remake=False):
        """在 123云盘创建目录

        参数:
            dirname: 要创建的目录名
            parentFileId: 父文件夹 ID（None 表示当前目录）
            remake: 为 False 时先检查文件夹是否存在并返回其 ID

        返回:
            int: 成功时返回文件夹 ID，否则返回 None
        """
        target_parent = parentFileId if parentFileId is not None else self.parentFileId

        if target_parent != self.parentFileId:
            self.cdById(target_parent)

        if not remake:
            for i in self.list:
                if i['FileName'] == dirname:
                    print("文件夹已存在")
                    return i['FileId']

        if parentFileId is None:
            parentFileId = self.parentFileId

        dataMk = {
            "driveId": 0, "etag": "", "fileName": dirname,
            "parentFileId": parentFileId, "size": 0,
            "type": 1, "duplicate": 1, "NotReuse": True,
            "event": "newCreateFolder", "operateType": 1
        }
        try:
            resMk = requests.post(
                config.URL_UPLOAD_REQUEST,
                headers=self.headerLogined,
                json=dataMk,
                timeout=config.TIMEOUT_SHORT
            )
            resJson = resMk.json()
        except requests.exceptions.RequestException as e:
            print(f"mkdir: 请求失败: {e}")
            return None
        except ValueError:
            print("mkdir: 创建失败（JSON 响应无效）")
            print(f"mkdir: 响应内容: {resMk.text}")
            return None

        code = resJson.get('code')
        if code == 0:
            print("创建成功")
            self.get_dir()
            return resJson["data"]["Info"]["FileId"]
        else:
            print(f"mkdir: 创建失败, code={code}")
            print(resJson)
            return None
