#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from tosasitill_123pan import config


def _validate_output_path(output_path):
    """校验并准备下载输出路径。

    参数:
        output_path: 期望的输出路径

    返回:
        str: 校验后的输出路径

    抛出:
        ValueError: 路径无效或存在风险时
    """
    output_path = output_path.strip()

    if not output_path:
        raise ValueError("输出路径不能为空")

    normalized = os.path.normpath(output_path)

    if os.path.isdir(normalized):
        raise ValueError(f"输出路径 '{normalized}' 是目录而不是文件，请指定文件名。")

    parent_dir = os.path.dirname(normalized)
    if parent_dir and not os.path.exists(parent_dir):
        raise ValueError(f"输出目录 '{parent_dir}' 不存在，请先创建或使用其他路径。")

    if os.path.exists(normalized):
        response = input(f"文件 '{normalized}' 已存在，是否覆盖？(y/N): ").strip().lower()
        if response != 'y':
            raise ValueError("用户取消了下载")

    abs_path = os.path.abspath(normalized)
    return abs_path


class MGet:
    """多线程文件下载器，支持单线程回退"""

    def __init__(self, default_threads=8):
        """初始化 MGet 下载器，可配置线程数"""
        self.default_threads = default_threads

    def get_file_size(self, url):
        """使用 HEAD 请求获取文件大小"""
        try:
            response = requests.head(url, timeout=config.TIMEOUT_SHORT)
            file_size = int(response.headers.get("content-length", 0))
            return file_size
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"获取文件大小失败: {e}")

    def download_single_thread(self, url, output_path):
        """使用单线程方式下载文件"""
        start_time = time.time()

        try:
            response = requests.get(url, stream=True, timeout=config.TIMEOUT_LONG)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"单线程下载失败: {e}")
            return None

        file_size = int(response.headers.get("content-length", 0))
        print(f"单线程下载 - 文件大小: {file_size/1024/1024:.2f} MB")

        progress_bar = tqdm(
            total=file_size, unit="B", unit_scale=True, desc="单线程"
        )

        downloaded_size = 0
        try:
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress_bar.update(len(chunk))
                        downloaded_size += len(chunk)
        except IOError as e:
            progress_bar.close()
            print(f"写入错误: {e}")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return None

        progress_bar.close()
        elapsed_time = time.time() - start_time
        print(f"单线程下载完成，耗时 {elapsed_time:.2f} 秒")
        return elapsed_time

    def download_chunk(self, args):
        """下载文件的指定字节范围"""
        url, start, end, output_path, chunk_id = args
        headers = {"Range": f"bytes={start}-{end}"}
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=config.TIMEOUT_LONG)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"分片 {chunk_id} 下载失败: {e}")

        chunk_path = f"{output_path}.part{chunk_id}"
        try:
            with open(chunk_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        except IOError as e:
            if os.path.exists(chunk_path):
                try:
                    os.remove(chunk_path)
                except OSError:
                    pass
            raise IOError(f"写入分片 {chunk_id} 失败: {e}")

        return chunk_path, chunk_id, end - start + 1

    def download_multi_thread(self, url, output_path, num_threads=None):
        """使用多个并行线程下载文件"""
        if num_threads is None:
            num_threads = self.default_threads

        start_time = time.time()
        chunk_files = []

        try:
            file_size = self.get_file_size(url)
        except ConnectionError as e:
            print(f"多线程下载失败: {e}")
            return None

        print(
            f"多线程下载 - 文件大小: {file_size/1024/1024:.2f} MB，线程数: {num_threads}"
        )

        chunk_size = file_size // num_threads
        chunks = []
        for i in range(num_threads):
            start_byte = i * chunk_size
            end_byte = (
                start_byte + chunk_size - 1 if i < num_threads - 1 else file_size - 1
            )
            chunks.append((url, start_byte, end_byte, output_path, i))

        progress_bar = tqdm(
            total=file_size, unit="B", unit_scale=True, desc="多线程"
        )
        downloaded = 0
        failed = False

        try:
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                for chunk_path, _, size in executor.map(self.download_chunk, chunks):
                    chunk_files.append(chunk_path)
                    downloaded += size
                    progress_bar.update(size)
        except (ConnectionError, IOError) as e:
            print(f"\n多线程下载失败: {e}")
            failed = True

        progress_bar.close()

        if failed:
            for cf in chunk_files:
                try:
                    os.remove(cf)
                except OSError:
                    pass
            return None

        try:
            with open(output_path, "wb") as output_file:
                for i in range(num_threads):
                    chunk_path = f"{output_path}.part{i}"
                    try:
                        with open(chunk_path, "rb") as chunk_file:
                            output_file.write(chunk_file.read())
                    finally:
                        try:
                            os.remove(chunk_path)
                        except OSError:
                            pass
        except IOError as e:
            print(f"合并分片失败: {e}")
            for cf in chunk_files:
                try:
                    os.remove(cf)
                except OSError:
                    pass
            return None

        elapsed_time = time.time() - start_time
        print(f"多线程下载完成，耗时 {elapsed_time:.2f} 秒")
        return elapsed_time

    def download(self, url, output_path, num_threads=None, force_single=False):
        """根据参数自动选择下载模式（含路径校验）"""
        validated_path = _validate_output_path(output_path)
        return self._download_raw(url, validated_path, num_threads, force_single)

    def _download_raw(self, url, output_path, num_threads=None, force_single=False):
        """内部下载逻辑，不做路径校验（用于路径已校验的场景）"""
        if force_single:
            return self.download_single_thread(url, output_path)
        else:
            if num_threads is None:
                num_threads = self.default_threads
            return self.download_multi_thread(url, output_path, num_threads)


def download_single_thread(url, output_path):
    """单线程下载"""
    downloader = MGet()
    return downloader.download_single_thread(url, output_path)


def download_multi_thread(url, output_path, num_threads=8):
    """多线程下载"""
    downloader = MGet()
    return downloader.download_multi_thread(url, output_path, num_threads)


def main():
    """MGet 下载器的命令行入口"""
    parser = argparse.ArgumentParser(
        description="文件下载器 - 单线程与多线程"
    )
    parser.add_argument("url", help="要下载的文件 URL")
    parser.add_argument(
        "-o", "--output", help="输出文件路径", default="downloaded_file"
    )
    parser.add_argument(
        "-t", "--threads", type=int, help="下载线程数", default=8
    )
    parser.add_argument(
        "-s", "--single", action="store_true", help="使用单线程下载"
    )
    args = parser.parse_args()

    downloader = MGet(default_threads=args.threads)

    print(f"开始下载: {args.url}")

    if args.single:
        print("使用单线程模式")
        single_time = downloader.download_single_thread(args.url, args.output)
        if single_time is not None:
            print(f"下载完成，耗时 {single_time:.2f} 秒")
    else:
        print(f"使用多线程模式（线程数: {args.threads}）")
        multi_time = downloader.download_multi_thread(args.url, args.output, args.threads)

        if multi_time is not None and args.output.endswith("_multi"):
            single_output = f"{args.output[:-6]}_single"
            print("\n运行单线程对比测试...")
            single_time = downloader.download_single_thread(args.url, single_output)

            if single_time:
                speedup = single_time / multi_time if multi_time > 0 else 0
                print("\n" + "=" * 50)
                print(f"性能对比:")
                print(f"单线程: {single_time:.2f} 秒")
                print(f"多线程: {multi_time:.2f} 秒")
                print(f"加速比: {speedup:.2f}x")
                print("=" * 50)

                single_size = os.path.getsize(single_output)
                multi_size = os.path.getsize(args.output)
                if single_size == multi_size:
                    print(
                        f"文件大小校验通过: {single_size/1024/1024:.2f} MB"
                    )
                else:
                    print(
                        f"警告: 文件大小不一致！单线程: {single_size/1024/1024:.2f} MB，多线程: {multi_size/1024/1024:.2f} MB"
                    )


if __name__ == "__main__":
    main()
