# -*- coding: utf-8 -*-
"""本地打印拦截器 — 打印工具函数。

提供：
  - PostScript → PDF 转换（Ghostscript）
  - PDF 页数读取（PyPDF2）
  - 调用 SumatraPDF 打印
"""

import os
import uuid
import subprocess
import logging

import PyPDF2

from local_printer import config

logger = logging.getLogger(__name__)


def convert_ps_to_pdf(ps_path):
    """用 Ghostscript 将 PostScript 文件转为 PDF。

    返回生成的 PDF 文件路径，失败返回 None。
    """
    pdf_name = os.path.splitext(os.path.basename(ps_path))[0] + '.pdf'
    pdf_path = os.path.join(config.TEMP_DIR, pdf_name)

    cmd = [
        config.GHOSTSCRIPT_PATH,
        '-dNOPAUSE', '-dBATCH', '-dSAFER',
        '-sDEVICE=pdfwrite',
        '-dCompatibilityLevel=1.4',
        f'-sOutputFile={pdf_path}',
        ps_path,
    ]

    logger.info('Ghostscript 转换: %s → %s', os.path.basename(ps_path), pdf_name)

    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')[:500]
            logger.error('Ghostscript 失败 (退出码 %d): %s', result.returncode, stderr)
            return None
    except subprocess.TimeoutExpired:
        logger.error('Ghostscript 转换超时')
        return None
    except Exception as e:
        logger.exception('Ghostscript 异常: %s', e)
        return None

    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        logger.info('转换成功: %s (%d bytes)', pdf_name, os.path.getsize(pdf_path))
        return pdf_path

    logger.error('转换后文件不存在或为空: %s', pdf_path)
    return None


def read_pdf_pages(pdf_path):
    """读取 PDF 页数。失败返回 0。"""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            pages = len(reader.pages)
            logger.info('PDF 页数: %s → %d 页', os.path.basename(pdf_path), pages)
            return pages
    except Exception as e:
        logger.error('读取 PDF 页数失败: %s', e)
        return 0


def print_pdf(pdf_path, color='CMYGray', duplex='one-sided', copies=1, paper='A4'):
    """调用 SumatraPDF 将 PDF 发送到真实打印机。

    返回 True/False。
    """
    if not os.path.exists(pdf_path):
        logger.error('打印文件不存在: %s', pdf_path)
        return False

    # 构建 SumatraPDF 打印参数（与 printer_daemon.py 一致）
    parts = []
    if color == 'CMYGray':
        parts.append('monochrome')
    else:
        parts.append('color')

    if duplex == 'one-sided':
        parts.append('simplex')
    elif duplex == 'two-sided-long-edge':
        parts.append('duplexlong')
    elif duplex == 'two-sided-short-edge':
        parts.append('duplexshort')

    if copies > 1:
        parts.append(f'{copies}x')

    if paper:
        parts.append(f'paper={paper}')

    settings = ','.join(parts)

    cmd = [config.SUMATRA_PATH]
    if config.PRINTER_NAME:
        cmd += ['-print-to', config.PRINTER_NAME]
    else:
        cmd += ['-print-to-default']
    if settings:
        cmd += ['-print-settings', settings]
    cmd += ['-silent', '-exit-when-done', pdf_path]

    logger.info('SumatraPDF 打印: %s 参数=%s', os.path.basename(pdf_path), settings)

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        logger.error('SumatraPDF 打印超时')
        return False
    except Exception as e:
        logger.exception('SumatraPDF 异常: %s', e)
        return False

    if proc.returncode == 0:
        logger.info('打印成功: %s', os.path.basename(pdf_path))
        return True

    stderr = proc.stderr.decode('utf-8', errors='replace')[:500] if proc.stderr else ''
    logger.error('SumatraPDF 退出码 %d: %s', proc.returncode, stderr)
    return False


def cleanup(*paths):
    """清理临时文件。"""
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
                logger.debug('已清理: %s', p)
        except Exception as e:
            logger.warning('清理文件失败 %s: %s', p, e)
