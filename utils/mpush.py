#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import hashlib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from tosasitill_123pan import config
from utils.logger import log_error, log_runtime


def format_size(size_bytes):
    """将字节数转换为可读格式

    参数:
        size_bytes: 字节大小

    返回:
        str: 可读的大小字符串（如 '1.50 MB'）
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.2f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.2f} GB"


def build_upload_session():
    """构建专用于上传链路的 HTTP 会话（带重试 + 连接复用）。

    为什么需要它:
    1. requests 默认重试次数为 0（内部是 Retry(0, read=False)），一旦存储节点
       偶发回 TCP RST（Linux errno 104）或 TLS 被无 close_notify 掐断
       （SSLEOFError），请求会立刻抛出且不做任何重试。
    2. 模块级 requests.put() 每次调用都会新建并销毁一个 Session，导致每个分片
       都要重新做一次 TCP + TLS 握手；一个 GB 级文件有数百个分片，等于数百次
       握手，既慢又容易触发节点的连接频率限制。

    每个文件上传独占一个会话（由 with 语句自动关闭），既复用了连接，又避免
    不同账号之间通过会话 Cookie 串味。

    返回:
        requests.Session: 已挂载重试适配器的会话对象
    """
    retry = Retry(
        total=config.UPLOAD_RETRY_TOTAL,
        connect=config.UPLOAD_RETRY_TOTAL,
        read=config.UPLOAD_RETRY_TOTAL,
        status=config.UPLOAD_RETRY_TOTAL,
        other=config.UPLOAD_RETRY_TOTAL,
        status_forcelist=config.UPLOAD_RETRY_STATUS,
        # 预签名链接过期会返回 403，必须靠重新申请链接解决，
        # 重发同一个 URL 没有意义，故 403 不放进 status_forcelist
        allowed_methods=frozenset(["PUT", "POST", "GET"]),
        backoff_factor=config.UPLOAD_RETRY_BACKOFF,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=config.UPLOAD_SESSION_POOL,
        pool_maxsize=config.UPLOAD_SESSION_POOL,
    )
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class MPush:
    """123云盘上传处理器

    该类提供上传文件和目录到 123云盘的方法。
    功能:
    - 单文件上传，带进度条
    - 目录并发上传
    - 基于 MD5 的重复检测与跳过
    - 大文件分片上传
    """

    def __init__(self, pan):
        """使用已认证的 Pan123 实例初始化 MPush

        参数:
            pan: 用于 API 调用的已认证 Pan123 实例
        """
        self.pan = pan

    @staticmethod
    def compute_file_md5(file_path):
        """使用分块读取计算文件的 MD5 哈希

        参数:
            file_path: 要计算哈希的文件路径

        返回:
            str: 十六进制 MD5 哈希字符串
        """
        with open(file_path, "rb") as f:
            md5 = hashlib.md5()
            for chunk in iter(lambda: f.read(64 * 1024), b""):
                md5.update(chunk)
            return md5.hexdigest()

    def check_file_exists_with_md5(self, file_name, local_md5, parent_id=None):
        """检查目标目录中是否已存在同名且 MD5 相同的文件

        参数:
            file_name: 要检查的文件名
            local_md5: 本地文件的 MD5 哈希
            parent_id: 要检查的父文件夹 ID（None 表示当前目录）

        返回:
            bool: 存在同名且 MD5 相同的文件时返回 True，否则 False
        """
        try:
            if parent_id is not None and self.pan.parentFileId != parent_id:
                self.pan.cdById(parent_id)

            if self.pan.list is None:
                return False

            for file_info in self.pan.list:
                if file_info["FileName"] == file_name and file_info["Type"] == 0:
                    remote_md5 = file_info.get("Etag", "").lower()
                    if remote_md5 and remote_md5 == local_md5.lower():
                        return True
            return False
        except Exception as e:
            tqdm.write(f"警告: 无法检查已存在的文件: {e}")
            return False

    def _upload_one_part(self, session, part_num, data, upload_url, fetch_presigned_urls, file_name):
        """上传单个分片，失败时重新申请预签名链接后重试。

        分片的 PUT 请求是幂等的（分片号与内容固定），可以安全地重复发送，
        因此这里做多轮尝试：每轮内部由 urllib3 负责网络级重试，整轮仍失败
        （或返回 403 表示链接已过期）时，重新申请链接再进入下一轮。

        参数:
            session: 带重试策略的 requests.Session
            part_num: 分片序号（从 1 开始）
            data: 分片字节内容
            upload_url: 本次要使用的预签名上传链接（可能为 None）
            fetch_presigned_urls: 获取预签名链接的回调，签名 (start, end)
            file_name: 所属文件名（仅用于日志）

        返回:
            bool: 上传成功返回 True，重试次数用尽返回 False
        """
        last_error = None

        for attempt in range(1, config.UPLOAD_PART_ATTEMPTS + 1):
            if upload_url:
                try:
                    put_res = session.put(
                        upload_url, data=data, timeout=config.TIMEOUT_UPLOAD_PART
                    )
                    if put_res.status_code == 403:
                        last_error = "上传链接已过期(HTTP 403)"
                    else:
                        put_res.raise_for_status()
                        return True
                except requests.exceptions.RequestException as e:
                    last_error = e
            else:
                last_error = "未获取到上传链接"

            if attempt < config.UPLOAD_PART_ATTEMPTS:
                # 403 与网络异常都意味着旧链接不可再用，统一重新申请
                refreshed = fetch_presigned_urls(part_num, part_num + 1)
                upload_url = (refreshed or {}).get(str(part_num))
                wait = config.UPLOAD_RETRY_BACKOFF * (2 ** (attempt - 1))
                tqdm.write(
                    f"分片 {part_num} 第 {attempt} 次失败（{last_error}），{wait:.1f}s 后重试"
                )
                time.sleep(wait)

        tqdm.write(
            f"分片 {part_num} 已重试 {config.UPLOAD_PART_ATTEMPTS} 轮仍失败: {last_error}"
        )
        log_error(
            f"分片上传失败: {file_name} 的第 {part_num} 分片重试 "
            f"{config.UPLOAD_PART_ATTEMPTS} 轮仍失败，最后错误: {last_error}"
        )
        return False

    def _upload_part_task(self, session, part_num, file_path, offset, size,
                          upload_url, fetch_presigned_urls, file_name):
        """线程池任务体：按偏移量读盘 + 上传该分片。

        读盘必须在任务内部按 offset/size 独立完成 —— 单个文件句柄的读写位置是共享的，
        多线程共用一个句柄会让分片内容错位。因此这里每次重新打开文件并 seek，只读
        当前分片需要的字节。

        同时这里也是「文件被截断」的检测点：读到的字节数少于预期即说明文件在传输
        过程中被改动，直接判失败并留痕。原先的实现遇到这种情况只是 break，会静默
        漏传该批剩余分片，最后由提交接口报一个看不出原因的错。

        参数:
            session: 带重试策略的 requests.Session
            part_num: 分片序号（从 1 开始）
            file_path: 本地文件路径
            offset: 本分片在文件中的起始偏移
            size: 本分片应有的字节数
            upload_url: 预签名上传链接（可能为 None）
            fetch_presigned_urls: 获取预签名链接的回调，签名 (start, end)
            file_name: 所属文件名（仅用于日志）

        返回:
            bool: 上传成功返回 True
        """
        with open(file_path, "rb") as fh:
            fh.seek(offset)
            data = fh.read(size)

        if len(data) != size:
            tqdm.write(
                f"错误: 分片 {part_num} 期望 {size} 字节，实际只读到 {len(data)} 字节"
                f"（文件可能已被改动或截断）"
            )
            log_error(
                f"分片上传中止: {file_name} 第 {part_num} 分片（偏移 {offset}）"
                f"期望 {size} 字节、实际读到 {len(data)} 字节，文件可能在传输过程中被修改"
            )
            return False

        return self._upload_one_part(
            session, part_num, data, upload_url, fetch_presigned_urls, file_name
        )

    def _list_dir(self, parent_id):
        """线程安全地列出某目录下的条目（只读，不改动 Pan123 的共享导航状态）。

        为什么不直接用 self.pan.get_dir(): 目录上传是多线程共用一个 Pan123 实例，
        get_dir() 会改写 parentFileId 等共享字段，并发时会互相踩；
        这里自己发请求，只借用认证头。

        参数:
            parent_id: 目标目录 ID

        返回:
            list: 目录条目列表；请求或解析失败时返回 None
        """
        items = []
        page = 1
        try:
            while True:
                params = {
                    "driveId": 0,
                    "limit": 100,
                    "next": 0,
                    "orderBy": "file_id",
                    "orderDirection": "desc",
                    "parentFileId": str(parent_id),
                    "trashed": False,
                    "SearchData": "",
                    "Page": str(page),
                    "OnlyLookAbnormalFile": 0,
                }
                resp = requests.get(
                    config.URL_FILE_LIST,
                    headers=self.pan.headerLogined,
                    params=params,
                    timeout=config.TIMEOUT_MEDIUM,
                )
                data = resp.json()
                if data.get("code") != 0:
                    return None
                info = data["data"]["InfoList"]
                items.extend(info)
                if not info or len(items) >= data["data"].get("Total", 0):
                    return items
                page += 1
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            tqdm.write(f"警告: 读取云盘目录失败: {e}")
            return None

    def _verify_uploaded(self, parent_id, md5, file_size, existing_ids):
        """回查云盘目录，确认文件确实已经落地。

        判据: 目录里出现了一个「收尾前不存在的 FileId」，且它的 Etag 与本地 MD5 一致、
        Size 一致。不按文件名判定 —— duplicate=1（保留两份）时服务端会自动改名。

        为什么必须回查: 历史上出现过完成接口返回 code=0 但文件没上来的情况，
        不校验就等于把静默失败当成成功。

        参数:
            parent_id: 目标目录 ID
            md5: 本地文件 MD5（云盘 Etag 与之同源）
            file_size: 本地文件字节数
            existing_ids: 收尾前该目录已有的 FileId 集合

        返回:
            bool: 确认落地返回 True
        """
        for attempt in range(config.UPLOAD_VERIFY_ATTEMPTS):
            items = self._list_dir(parent_id)
            if items is not None:
                for item in items:
                    if item.get("Type") != 0:
                        continue
                    if item.get("FileId") in existing_ids:
                        continue
                    if (str(item.get("Etag", "")).lower() == md5.lower()
                            and int(item.get("Size", -1)) == file_size):
                        return True
            if attempt < config.UPLOAD_VERIFY_ATTEMPTS - 1:
                time.sleep(config.UPLOAD_VERIFY_INTERVAL)
        return False

    def upload_file(self, file_path, parent_id=None, sure=None, skip_existing=True):
        """上传单个文件到 123云盘

        参数:
            file_path: 要上传的文件路径
            parent_id: 父文件夹 ID（None 表示当前目录）
            sure: 重复处理策略 - "1":保留两份, "2":覆盖
            skip_existing: 为 True 时跳过 MD5 相同的已存在文件（默认: True）

        返回:
            dict: 上传结果，包含 'success'、'skipped'、'file_name' 键
        """
        result = {'success': False, 'skipped': False, 'file_name': ''}

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            tqdm.write(f"错误: {file_path} 不是有效文件")
            return result

        file_path = file_path.replace('"', "").replace("\\", "/")
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        result['file_name'] = file_name

        tqdm.write(f"准备上传: {file_name} ({format_size(file_size)})")

        tqdm.write("正在计算文件 MD5...")
        md5 = self.compute_file_md5(file_path)

        if parent_id is None:
            parent_id = self.pan.parentFileId

        if skip_existing:
            if self.check_file_exists_with_md5(file_name, md5, parent_id):
                tqdm.write(f"已跳过（存在相同 MD5）: {file_name}")
                result['success'] = True
                result['skipped'] = True
                return result

        if sure == "2":
            self.pan.get_dir()
            for i, file_info in enumerate(self.pan.list):
                if file_info["FileName"] == file_name and file_info["Type"] == 0:
                    tqdm.write(f"正在删除已存在文件: {file_name}")
                    self.pan.delete_file(i, by_num=True, operation=True)
                    self.pan.get_dir()
                    break

        list_up_request = {
            "driveId": 0,
            "etag": md5,
            "fileName": file_name,
            "parentFileId": parent_id,
            "size": file_size,
            "type": 0,
            "duplicate": 0,
        }

        try:
            up_res = requests.post(
                config.URL_UPLOAD_REQUEST,
                headers=self.pan.headerLogined,
                json=list_up_request,
                timeout=config.TIMEOUT_MEDIUM
            )
            up_res_json = up_res.json()
        except requests.exceptions.RequestException as e:
            tqdm.write(f"上传请求失败: {e}")
            log_error(f"上传请求失败: {file_name}: {e}")
            return result
        except ValueError as e:
            tqdm.write(f"上传请求解析失败: {e}")
            log_error(f"上传请求解析失败: {file_name}: {e}")
            return result

        code = up_res_json.get("code")

        if code == 5060:
            tqdm.write("检测到重复文件")
            if sure not in ["1", "2"]:
                sure = input(
                    "检测到重复文件。输入 1 保留两份，2 覆盖，0 取消: "
                )

            if sure == "1":
                list_up_request["duplicate"] = 1
            elif sure == "2":
                self.pan.get_dir()
                for i, file_info in enumerate(self.pan.list):
                    if file_info["FileName"] == file_name and file_info["Type"] == 0:
                        tqdm.write(f"正在删除已存在文件: {file_name}")
                        self.pan.delete_file(i, by_num=True, operation=True)
                        self.pan.get_dir()
                        break
                list_up_request["duplicate"] = 2
            else:
                tqdm.write("已取消上传")
                return result

            try:
                up_res = requests.post(
                    config.URL_UPLOAD_REQUEST,
                    headers=self.pan.headerLogined,
                    json=list_up_request,
                    timeout=config.TIMEOUT_MEDIUM
                )
                up_res_json = up_res.json()
            except requests.exceptions.RequestException as e:
                tqdm.write(f"重复处理后上传请求失败: {e}")
                log_error(f"重复处理后上传请求失败: {file_name}: {e}")
                return result
            except ValueError as e:
                tqdm.write(f"上传请求解析失败: {e}")
                log_error(f"上传请求解析失败: {file_name}: {e}")
                return result
            code = up_res_json.get("code")

        if code == 0:
            reuse = up_res_json["data"].get("Reuse")
            if reuse:
                tqdm.write(f"上传成功，文件 MD5 已复用: {file_name}")
                result['success'] = True
                return result
        else:
            tqdm.write(f"上传请求失败: {up_res_json}")
            log_error(f"上传请求失败: {file_name}: {up_res_json}")
            return result

        bucket = up_res_json["data"]["Bucket"]
        storage_node = up_res_json["data"]["StorageNode"]
        upload_key = up_res_json["data"]["Key"]
        upload_id = up_res_json["data"]["UploadId"]
        up_file_id = up_res_json["data"]["FileId"]

        # 分片规划（16MB 分片，与官方 Web 端一致）
        block_size = config.DEFAULT_BLOCK_SIZE
        chunk_count = max(1, (file_size + block_size - 1) // block_size)
        is_multipart = chunk_count > 1

        def fetch_presigned_urls(start, end):
            """获取 [start, end) 区间分片的预签名上传链接。

            官方现行协议: 单分片用 s3_upload_object/auth，
            多分片用 s3_repare_upload_parts_batch。
            """
            req_body = {
                "bucket": bucket,
                "key": upload_key,
                "partNumberEnd": end,
                "partNumberStart": start,
                "uploadId": upload_id,
                "StorageNode": storage_node,
            }
            url = config.URL_S3_PREPARE_PARTS if is_multipart else config.URL_S3_UPLOAD_AUTH
            try:
                # 走复用连接的会话，避免每次申请链接都重新握手
                resp = session.post(
                    url,
                    headers=self.pan.headerLogined,
                    json=req_body,
                    timeout=config.TIMEOUT_MEDIUM
                )
                resp_json = resp.json()
            except requests.exceptions.RequestException as e:
                tqdm.write(f"获取上传链接失败: {e}")
                return None
            except ValueError as e:
                tqdm.write(f"上传链接响应解析失败: {e}")
                return None
            if resp_json.get("code") != 0:
                tqdm.write(f"获取上传链接失败: {resp_json}")
                return None
            return (resp_json.get("data") or {}).get("presignedUrls") or {}

        # 多分片每批取 10 个分片链接（与官方 Web 端一致）
        batch_size = 10 if is_multipart else 1
        # 批内并发度：不超过批大小，也不小于 1
        part_concurrency = max(1, min(config.UPLOAD_PART_CONCURRENCY, batch_size))

        # 整个文件的所有分片共用同一个会话，连接（含 TLS）只握手一次
        with build_upload_session() as session, tqdm(
            total=file_size, unit="B", unit_scale=True, desc=file_name, position=1, leave=False
        ) as pbar:
            aborted = False
            part_pool = ThreadPoolExecutor(max_workers=part_concurrency)
            try:
                part = 1
                while part <= chunk_count and not aborted:
                    start = part
                    end = min(part + batch_size, chunk_count + 1)
                    urls = fetch_presigned_urls(start, end)
                    if urls is None:
                        log_error(
                            f"分片上传失败: {file_name} 获取第 {start}-{end - 1} 批分片链接失败"
                        )
                        return result

                    # 先按偏移算好每片的字节数，再并发提交；读盘在各任务内部独立完成
                    sizes = {}
                    futures = {}
                    for part_num in range(start, end):
                        offset = (part_num - 1) * block_size
                        size = min(block_size, file_size - offset)
                        if size <= 0:
                            tqdm.write(f"错误: 分片 {part_num} 偏移 {offset} 已超出文件大小")
                            log_error(
                                f"分片上传失败: {file_name} 第 {part_num} 分片偏移 "
                                f"{offset} 超出文件大小 {file_size}"
                            )
                            return result
                        sizes[part_num] = size
                        futures[part_pool.submit(
                            self._upload_part_task,
                            session,
                            part_num,
                            file_path,
                            offset,
                            size,
                            urls.get(str(part_num)),
                            fetch_presigned_urls,
                            file_name,
                        )] = part_num

                    for fut in as_completed(futures):
                        part_num = futures[fut]
                        try:
                            ok = fut.result()
                        except Exception as e:
                            ok = False
                            tqdm.write(f"分片 {part_num} 上传异常: {e}")
                            log_error(
                                f"分片上传失败: {file_name} 第 {part_num} 分片异常: {e}"
                            )
                        if not ok:
                            aborted = True
                            break
                        pbar.update(sizes[part_num])

                    if aborted:
                        break
                    part = end
            finally:
                # 失败时取消本批尚未开跑的分片，避免继续白传
                part_pool.shutdown(wait=True, cancel_futures=aborted)

            if aborted:
                return result

        tqdm.write("分片上传完成，正在提交...")

        # 收尾接口（2026-10-16 远程实测，2×2 矩阵已全覆盖）:
        #   upload_complete/v2 — 单分片与多分片**均真正落地**，响应 data.file_info 里
        #                        带回落地后的 FileId/Etag/Size；唯一全场景有效的收尾接口。
        #   upload_complete(v1)— 仅**单分片**（≤16MB）有效（响应 data.Info 含落地信息）；
        #                        对**多分片**会返回 code=0 但 data={} 的**假成功**，
        #                        实测 60 秒内、乃至永久都不落地，记录状态仍是未完成。
        # 故顺序为 v2 主力 → v1 兜底；且无论响应如何都必须回查目录确认真的落地，
        # 避免「返回 code=0 但文件没上来」被当成成功。
        v2_payload = {
            "StorageNode": storage_node,
            "bucket": bucket,
            "fileId": up_file_id,
            "fileSize": file_size,
            "isMultipart": is_multipart,
            "key": upload_key,
            "uploadId": upload_id,
        }
        v1_payload = {"fileId": up_file_id}

        # 收尾前的目录快照：用「新增的 FileId」判定落地，避免同名同 MD5 的旧文件造成误判
        pre_items = self._list_dir(parent_id)
        existing_ids = {item.get("FileId") for item in (pre_items or [])}

        last_detail = ""
        # ok_field 表示「服务端真的合并了」的标志字段：
        #   v2 -> data.file_info；v1（仅单分片）-> data.Info
        for api_name, url, payload, ok_field in (
            ("upload_complete/v2", config.URL_UPLOAD_COMPLETE_V2, v2_payload, "file_info"),
            ("upload_complete(v1)", config.URL_UPLOAD_COMPLETE, v1_payload, "Info"),
        ):
            try:
                # 分片已全部上传，此时因一次瞬断就放弃整个文件代价极高，
                # 故同样走带重试的会话
                with build_upload_session() as session:
                    comp_res = session.post(
                        url,
                        headers=self.pan.headerLogined,
                        json=payload,
                        timeout=config.TIMEOUT_LONG
                    )
                comp_json = comp_res.json()
            except requests.exceptions.RequestException as e:
                last_detail = f"{api_name} 请求失败: {e}"
            except ValueError as e:
                last_detail = f"{api_name} 响应解析失败: {e}"
            else:
                code = comp_json.get("code")
                data = comp_json.get("data")
                if code == 0 and isinstance(data, dict) and data.get(ok_field):
                    if self._verify_uploaded(parent_id, md5, file_size, existing_ids):
                        tqdm.write(f"上传成功: {file_name}")
                        result['success'] = True
                        return result
                    last_detail = f"{api_name} 返回成功，但目录中查不到该文件"
                elif code == 0:
                    # 典型情况：v1 收尾多分片时返回 code=0 但 data={}，属假成功
                    last_detail = (
                        f"{api_name} 返回 code=0 但 data 里没有 {ok_field}"
                        f"（假成功，服务端未合并）: {comp_json}"
                    )
                elif "uid_mismatch" in str(comp_json.get("message", "")):
                    last_detail = (
                        f"{api_name} 报 非法请求(uid_mismatch)：该文件的预上传记录属于"
                        f"另一次登录（换账号/换登录方式后遗留），本会话无法收尾；"
                        f"需删除远端同名文件后重传，或改用其它文件名"
                    )
                else:
                    last_detail = f"{api_name} 返回异常: {comp_json}"
            # 只是「这一个接口没收成功」，后面还有兜底，记运行日志即可，
            # 不能写 errors/ —— 否则一次成功上传会被误记成失败
            tqdm.write(f"收尾未成功（转下一接口）: {last_detail}")
            log_runtime(f"分片上传收尾降级: {file_name} {last_detail}")

        tqdm.write(f"上传失败: {last_detail}")
        log_error(f"分片上传失败: {file_name} {last_detail}")
        return result

    def upload_directory_concurrent(
        self,
        dir_path,
        parent_id=None,
        max_workers=5,
        file_types=None,
        sure=None,
        custom_dirname=None,
        skip_existing=True,
    ):
        """使用并发线程上传目录到 123云盘

        该方法将整个目录结构上传到 123云盘。
        先创建远程目录结构，然后使用线程池并发上传文件，
        并通过 tqdm 显示整体进度。

        参数:
            dir_path: 要上传的本地目录路径
            parent_id: 123云盘中的父文件夹 ID（None 表示当前目录）
            max_workers: 最大并发上传线程数（默认: 5）
            file_types: 要包含的文件扩展名列表（如 ['.jpg', '.png']）
            sure: 重复处理策略 - "1":保留两份, "2":覆盖
            custom_dirname: 远程目录的自定义名称（默认: 使用本地名称）
            skip_existing: 为 True 时跳过 MD5 相同的已存在文件（默认: True）

        返回:
            bool: 上传成功返回 True，否则 False
        """
        if not os.path.isdir(dir_path):
            print(f"错误: {dir_path} 不是有效目录")
            return False

        dir_path = dir_path.replace('"', "").replace("\\", "/")
        dir_name = custom_dirname if custom_dirname else os.path.basename(dir_path)

        print(f"准备上传目录: {dir_name}")

        if parent_id is None:
            parent_id = self.pan.parentFileId

        folder_id = self.pan.mkdir(dir_name, parent_id, remake=False)
        if not folder_id:
            print(f"创建目录失败: {dir_name}")
            return False

        print(f"目录已创建: {dir_name}, ID: {folder_id}")

        mkdir_list = {dir_path: folder_id}
        skip_dirs = ["venv", ".idea", "__pycache__", ".git", "node_modules"]

        files_to_upload = []

        for filepath, dirnames, filenames in os.walk(dir_path):
            if any(skip_dir in filepath for skip_dir in skip_dirs):
                continue

            parent_path = os.path.dirname(filepath)
            if parent_path in mkdir_list and filepath != dir_path:
                sub_dir_name = os.path.basename(filepath)
                parent_folder_id = mkdir_list[parent_path]
                sub_folder_id = self.pan.mkdir(sub_dir_name, parent_folder_id, remake=False)
                time.sleep(0.2)
                if sub_folder_id:
                    mkdir_list[filepath] = sub_folder_id
                    tqdm.write(f"已创建目录: {sub_dir_name}, ID: {sub_folder_id}")

            if filepath in mkdir_list:
                current_folder_id = mkdir_list[filepath]
                for filename in filenames:
                    if file_types:
                        if not any(filename.endswith(ft) for ft in file_types):
                            continue
                    file_path = os.path.join(filepath, filename)
                    files_to_upload.append((file_path, current_folder_id))

        total_files = len(files_to_upload)
        uploaded_count = 0
        skipped_count = 0
        failed_count = 0

        with tqdm(total=total_files, desc="总进度", position=0, unit="文件") as overall_pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for file_path, target_folder_id in files_to_upload:
                    # 提交任务时立即捕获 target_folder_id（避免延迟绑定问题）
                    future = executor.submit(
                        self.upload_file, file_path, target_folder_id, sure, skip_existing
                    )
                    futures[future] = file_path

                for future in as_completed(futures):
                    file_path = futures[future]
                    try:
                        result = future.result()
                        if result.get('success'):
                            if result.get('skipped'):
                                skipped_count += 1
                            else:
                                uploaded_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        tqdm.write(f"上传 {file_path} 出错: {e}")
                        failed_count += 1

                    overall_pbar.update(1)
                    overall_pbar.set_postfix(
                        uploaded=uploaded_count,
                        skipped=skipped_count,
                        failed=failed_count
                    )

        print(f"\n目录上传完成")
        print(f"  文件总数: {total_files}")
        print(f"  已上传: {uploaded_count}")
        print(f"  已跳过（MD5 相同）: {skipped_count}")
        print(f"  失败: {failed_count}")

        return failed_count == 0
