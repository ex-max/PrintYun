# -*- coding: utf-8 -*-
"""Redmon 重定向目标脚本。

Redmon 会把打印数据通过 stdin 传给本脚本，
脚本将数据保存到 C:\PrintJobs\<时间戳>.ps 文件。
"""
import sys
import os
import time
import random

OUTPUT_DIR = r"C:\PrintJobs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

timestamp = time.strftime('%Y%m%d_%H%M%S')
rand = random.randint(1000, 9999)
filename = f"{timestamp}_{rand}.ps"
filepath = os.path.join(OUTPUT_DIR, filename)

try:
    with open(filepath, 'wb') as f:
        while True:
            chunk = sys.stdin.buffer.read(8192)
            if not chunk:
                break
            f.write(chunk)
except Exception:
    pass
