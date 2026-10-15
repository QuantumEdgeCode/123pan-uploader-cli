#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import os
import sys
import getpass
from tosasitill_123pan import config


def get_token(passport=None, password=None, remember=True):
    """通过账号密码获取 123云盘登录 Token。

    参数:
        passport: 用户名/手机号（为 None 时提示输入）
        password: 登录密码（为 None 时提示输入）
        remember: 是否记住登录状态（默认: True）

    返回:
        成功时返回包含凭据和 Token 的 dict，否则返回 None。
        dict 键: userName、passWord、authorization（Bearer Token）
    """
    url = config.URL_SIGN_IN

    if not passport:
        passport = input("请输入 123云盘用户名/手机号: ")
    if not password:
        password = getpass.getpass("请输入密码: ")

    payload = {"passport": passport, "password": password, "remember": remember}

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://yun.123pan.cn",
        "Referer": "https://yun.123pan.cn/",
        "platform": "web",
        "App-Version": "3",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=config.TIMEOUT_SHORT)
        result = response.json()

        if result.get("code") == 200:
            token = result.get("data", {}).get("token")
            if token:
                print("登录成功，已获取 Token")
                return {
                    "userName": passport,
                    "passWord": password,
                    "authorization": f"Bearer {token}",
                }
            else:
                print("登录成功，但获取 Token 失败")
                return None
        else:
            print(f"登录失败: {result.get('message', '未知错误')}")
            return None

    except Exception as e:
        print(f"请求错误: {str(e)}")
        return None


def save_token_to_file(credentials, filename="123pan.txt"):
    """保存凭据到文件"""
    try:
        dirname = os.path.dirname(filename)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        with open(filename, "w") as f:
            json.dump(credentials, f)

        print(f"凭据已保存到 {filename}")
        return True
    except Exception as e:
        print(f"保存凭据失败: {str(e)}")
        return False


def main():
    """主函数"""
    print("123云盘 Token 工具")
    print("-" * 30)

    if len(sys.argv) >= 3:
        passport = sys.argv[1]
        password = sys.argv[2]
    else:
        passport = None
        password = None

    credentials = get_token(passport, password)

    if credentials:
        filepath = os.path.join("123pan.txt")
        save_token_to_file(credentials, filepath)

        token = credentials["authorization"].replace("Bearer ", "")
        print(f"Token 预览: {token[:20]}...")


if __name__ == "__main__":
    main()
