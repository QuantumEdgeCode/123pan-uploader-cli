#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import hashlib
import requests
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from tosasitill_123pan import config


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
            return result
        except ValueError as e:
            tqdm.write(f"上传请求解析失败: {e}")
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
                return result
            except ValueError as e:
                tqdm.write(f"上传请求解析失败: {e}")
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
                resp = requests.post(
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

        with open(file_path, "rb") as f, tqdm(
            total=file_size, unit="B", unit_scale=True, desc=file_name, position=1, leave=False
        ) as pbar:
            part = 1
            while part <= chunk_count:
                start = part
                end = min(part + batch_size, chunk_count + 1)
                urls = fetch_presigned_urls(start, end)
                if urls is None:
                    return result

                for part_num in range(start, end):
                    data = f.read(block_size)
                    if not data:
                        break
                    upload_url = urls.get(str(part_num))
                    if not upload_url:
                        tqdm.write(f"分片 {part_num} 未返回上传链接")
                        return result
                    try:
                        put_res = requests.put(upload_url, data=data, timeout=config.TIMEOUT_UPLOAD_PART)
                        if put_res.status_code == 403:
                            # 链接过期时刷新一次后重试
                            refreshed = fetch_presigned_urls(part_num, part_num + 1)
                            if not refreshed or not refreshed.get(str(part_num)):
                                tqdm.write(f"分片 {part_num} 上传链接刷新失败")
                                return result
                            put_res = requests.put(refreshed[str(part_num)], data=data, timeout=config.TIMEOUT_UPLOAD_PART)
                        put_res.raise_for_status()
                    except requests.exceptions.RequestException as e:
                        tqdm.write(f"分片上传失败: {e}")
                        return result
                    pbar.update(len(data))

                part = end

        tqdm.write("分片上传完成，正在提交...")

        # 新版完成接口 upload_complete/v2（2026-10 实测）：旧版
        # s3_complete_multipart_upload + upload_complete 已失效（不落地文件）
        comp_v2_data = {
            "StorageNode": storage_node,
            "bucket": bucket,
            "fileId": up_file_id,
            "fileSize": file_size,
            "isMultipart": is_multipart,
            "key": upload_key,
            "uploadId": upload_id,
        }

        try:
            comp_res = requests.post(
                config.URL_UPLOAD_COMPLETE_V2,
                headers=self.pan.headerLogined,
                json=comp_v2_data,
                timeout=config.TIMEOUT_LONG
            )
            comp_json = comp_res.json()
        except requests.exceptions.RequestException as e:
            tqdm.write(f"完成上传请求失败: {e}")
            return result
        except ValueError as e:
            tqdm.write(f"完成响应解析失败: {e}")
            return result

        if comp_json.get("code") == 0:
            tqdm.write(f"上传成功: {file_name}")
            result['success'] = True
            return result
        else:
            tqdm.write(f"上传失败: {comp_json}")
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
