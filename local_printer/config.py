# -*- coding: utf-8 -*-
"""本地打印拦截器 — 配置管理。"""

import os
import configparser

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_BASE_DIR)
_CONFIG_FILE = os.path.join(_BASE_DIR, 'config.ini')


def _load_config():
    """从 config.ini 加载配置，不存在时生成默认文件。"""
    cfg = configparser.ConfigParser()

    if os.path.exists(_CONFIG_FILE):
        cfg.read(_CONFIG_FILE, encoding='utf-8')
    else:
        _create_default_config(cfg)

    return cfg


def _create_default_config(cfg):
    """生成默认 config.ini。"""
    # 从 .env 读取已有值作为默认
    try:
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_PROJECT_DIR, '.env'))
    except ImportError:
        env = {}

    cfg['server'] = {
        'base_url': 'http://localhost:5000',
        'machine_key': env.get('LOCAL_PRINT_KEY', 'printyun_local_2026'),
    }
    cfg['printer'] = {
        'name': env.get('PRINTER_NAME', ''),
        'sumatra_path': env.get('SUMATRA_PATH', r'C:\Users\Su Ki\AppData\Local\SumatraPDF\SumatraPDF.exe'),
        'ghostscript_path': env.get('LOCAL_PRINT_GHOSTSCRIPT',
                                    r'C:\Program Files\gs\gs10.06.0\bin\gswin64c.exe'),
    }
    cfg['paths'] = {
        'watch_dir': r'C:\PrintJobs',
        'temp_dir': r'C:\PrintJobs\temp',
    }
    cfg['defaults'] = {
        'color': 'CMYGray',
        'duplex': 'one-sided',
        'copies': '1',
        'paper': 'A4',
        'timeout_minutes': '10',
        'poll_interval_seconds': '2',
    }

    with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
        cfg.write(f)


# 加载配置（模块级单例）
_cfg = _load_config()


# ---- 便捷访问函数 ----

def get(section, key, fallback=''):
    return _cfg.get(section, key, fallback=fallback)


# 服务器
SERVER_URL = get('server', 'base_url', 'http://localhost:5000').rstrip('/')
MACHINE_KEY = get('server', 'machine_key', '')

# 打印机
PRINTER_NAME = get('printer', 'name', '')
SUMATRA_PATH = get('printer', 'sumatra_path', '')
GHOSTSCRIPT_PATH = get('printer', 'ghostscript_path', '')

# 路径
WATCH_DIR = get('paths', 'watch_dir', r'C:\PrintJobs')
TEMP_DIR = get('paths', 'temp_dir', r'C:\PrintJobs\temp')

# 默认打印参数
DEFAULT_COLOR = get('defaults', 'color', 'CMYGray')
DEFAULT_DUPLEX = get('defaults', 'duplex', 'one-sided')
DEFAULT_COPIES = int(get('defaults', 'copies', '1') or 1)
DEFAULT_PAPER = get('defaults', 'paper', 'A4')
TIMEOUT_MINUTES = int(get('defaults', 'timeout_minutes', '10') or 10)
POLL_INTERVAL = int(get('defaults', 'poll_interval_seconds', '2') or 2)

# 确保目录存在
os.makedirs(WATCH_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
