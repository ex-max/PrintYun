# -*- coding: utf-8 -*-
"""集中式日志配置。

调用 setup_logging(app) 后：
  - 控制台输出带颜色的简洁日志
  - logs/app.log 保存详细日志（按天轮转，保留 30 天）
  - Flask/Werkzeug 内置日志也统一走此配置

使用：
  from app.logging_config import setup_logging
  setup_logging(app)

  # 在各模块中：
  import logging
  logger = logging.getLogger(__name__)
  logger.info('something happened')
"""

import os
import logging
from logging.handlers import TimedRotatingFileHandler


def setup_logging(app):
    """初始化全局日志：控制台 + 文件（按天轮转）。"""
    log_level = logging.DEBUG if app.debug else logging.INFO

    # 日志格式
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    # 确保日志目录
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # 文件 handler：按天轮转，保留 30 天
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # 根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # 清除默认 handler 避免重复输出
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Flask 内置 logger 也走同样的 handler
    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)

    # 降低第三方库噪音
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

    app.logger.info('日志系统初始化完成（级别=%s，文件=%s）',
                     logging.getLevelName(log_level),
                     os.path.join(log_dir, 'app.log'))
