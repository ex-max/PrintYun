# -*- coding: utf-8 -*-
"""本地打印拦截器 — 付款弹窗（tkinter）。

弹出一个置顶窗口，显示：
  - 打印信息（文件名、页数、价格）
  - 支付宝二维码
  - 倒计时
  - 后台轮询付款状态，自动感知付款成功
"""

import threading
import time
import logging
import tkinter as tk
from io import BytesIO

import qrcode
from PIL import Image, ImageTk

from local_printer import config
from local_printer.job_processor import check_payment_status

logger = logging.getLogger(__name__)


def show_payment_window(order_info, pay_info):
    """显示付款弹窗。

    阻塞直到：用户付款成功('paid') / 点取消('cancelled') / 超时('timeout')。

    Args:
        order_info: dict — 来自 create_order API 的响应
        pay_info:   dict — 来自 pay_url API 的响应

    Returns:
        'paid' | 'cancelled' | 'timeout'
    """
    result = {'value': 'timeout'}  # 用 dict 做闭包变量

    trade_number = order_info.get('trade_number', '')
    cost = order_info.get('cost', 0)
    pages = order_info.get('pages', 0)
    copies = order_info.get('copies', 1)
    unit_price = order_info.get('unit_price', 0)
    qr_data = pay_info.get('qr_data', '')

    timeout_sec = config.TIMEOUT_MINUTES * 60

    # ---- 创建窗口 ----
    root = tk.Tk()
    root.title('云打印 - 待付款')
    root.configure(bg='#f5f7fa')
    root.resizable(False, False)
    root.attributes('-topmost', True)

    # 窗口居中
    win_w, win_h = 420, 600
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - win_w) // 2
    y = (screen_h - win_h) // 2
    root.geometry(f'{win_w}x{win_h}+{x}+{y}')

    # 禁止关闭按钮（必须点取消）
    root.protocol('WM_DELETE_WINDOW', lambda: None)

    # ---- 标题栏 ----
    header = tk.Frame(root, bg='#1E9FFF', height=50)
    header.pack(fill='x')
    header.pack_propagate(False)
    tk.Label(header, text='⎙  云打印 - 扫码付款', font=('Microsoft YaHei', 14, 'bold'),
             bg='#1E9FFF', fg='white').pack(expand=True)

    # ---- 信息区 ----
    info_frame = tk.Frame(root, bg='#ffffff', padx=24, pady=16)
    info_frame.pack(fill='x', padx=16, pady=(16, 0))

    def _info_row(parent, label, value, bold=False):
        row = tk.Frame(parent, bg='#ffffff')
        row.pack(fill='x', pady=2)
        tk.Label(row, text=label, font=('Microsoft YaHei', 11),
                 bg='#ffffff', fg='#888', anchor='w', width=8).pack(side='left')
        font = ('Microsoft YaHei', 11, 'bold') if bold else ('Microsoft YaHei', 11)
        fg = '#e74c3c' if bold else '#333'
        tk.Label(row, text=value, font=font, bg='#ffffff', fg=fg, anchor='w').pack(side='left')

    filename = order_info.get('filename', '本地打印文档')
    if len(filename) > 20:
        filename = filename[:18] + '...'

    color_text = '黑白' if config.DEFAULT_COLOR == 'CMYGray' else '彩色'
    duplex_text = {'one-sided': '单面', 'two-sided-long-edge': '双面长边',
                   'two-sided-short-edge': '双面短边'}.get(config.DEFAULT_DUPLEX, '单面')

    _info_row(info_frame, '文件', filename)
    _info_row(info_frame, '页数', f'{pages} 页')
    _info_row(info_frame, '颜色', color_text)
    _info_row(info_frame, '方式', duplex_text)
    _info_row(info_frame, '份数', f'{copies} 份')
    _info_row(info_frame, '单价', f'¥{unit_price:.1f}/页')
    _info_row(info_frame, '总计', f'¥{cost:.2f}', bold=True)

    # ---- 二维码 ----
    qr_frame = tk.Frame(root, bg='#f5f7fa')
    qr_frame.pack(pady=12)

    if qr_data:
        qr_img = qrcode.make(qr_data, box_size=6, border=2)
        qr_img = qr_img.resize((200, 200), Image.Resampling.NEAREST)
        qr_photo = ImageTk.PhotoImage(qr_img)
        qr_label = tk.Label(qr_frame, image=qr_photo, bg='#ffffff',
                            relief='solid', borderwidth=1)
        qr_label.image = qr_photo  # 防止 GC
        qr_label.pack()
    else:
        tk.Label(qr_frame, text='⚠ 无法生成二维码\n请联系管理员',
                 font=('Microsoft YaHei', 12), bg='#f5f7fa', fg='#e74c3c').pack()

    tk.Label(root, text='请使用支付宝扫码支付', font=('Microsoft YaHei', 10),
             bg='#f5f7fa', fg='#666').pack()

    # ---- 状态 + 倒计时 ----
    status_var = tk.StringVar(value='⏳ 等待付款中...')
    status_label = tk.Label(root, textvariable=status_var,
                            font=('Microsoft YaHei', 11),
                            bg='#f5f7fa', fg='#1E9FFF')
    status_label.pack(pady=(12, 4))

    countdown_var = tk.StringVar(value='')
    countdown_label = tk.Label(root, textvariable=countdown_var,
                               font=('Microsoft YaHei', 9),
                               bg='#f5f7fa', fg='#999')
    countdown_label.pack()

    # ---- 关闭窗口辅助函数 ----
    def _close_window():
        """安全关闭窗口。"""
        try:
            root.quit()       # 先停止 mainloop
            root.destroy()    # 再销毁窗口
        except Exception:
            try:
                root.quit()
            except Exception:
                pass

    # ---- 取消按钮 ----
    def on_cancel():
        result['value'] = 'cancelled'
        _close_window()

    cancel_btn = tk.Button(root, text='取消打印', command=on_cancel,
                           font=('Microsoft YaHei', 11),
                           bg='#fff', fg='#666', relief='solid', borderwidth=1,
                           width=16, height=1, cursor='hand2')
    cancel_btn.pack(pady=(12, 16))

    # ---- 后台轮询线程 ----
    poll_running = {'active': True}
    start_time = time.time()

    def poll_status():
        while poll_running['active']:
            elapsed = time.time() - start_time
            remaining = max(0, timeout_sec - elapsed)

            if remaining <= 0:
                result['value'] = 'timeout'
                try:
                    root.after(0, _close_window)
                except Exception:
                    pass
                return

            # 更新倒计时
            mins, secs = divmod(int(remaining), 60)
            try:
                root.after(0, countdown_var.set, f'剩余时间 {mins:02d}:{secs:02d}')
            except Exception:
                return

            # 查询状态
            status = check_payment_status(trade_number)
            if status and status.get('paid'):
                result['value'] = 'paid'
                poll_running['active'] = False

                def _on_paid():
                    status_var.set('✅ 付款成功！正在打印...')
                    countdown_var.set('')
                    cancel_btn.config(state='disabled')
                    root.after(1500, _close_window)

                try:
                    root.after(0, _on_paid)
                except Exception:
                    pass
                return

            time.sleep(config.POLL_INTERVAL)

    poll_thread = threading.Thread(target=poll_status, daemon=True)
    poll_thread.start()

    # ---- 启动事件循环（阻塞） ----
    try:
        root.mainloop()
    except Exception:
        pass

    poll_running['active'] = False
    logger.info('弹窗关闭，结果: %s', result['value'])
    return result['value']
