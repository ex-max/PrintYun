import os
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=False)
except ImportError:
    pass

import redis, subprocess
from rq import Queue
from rq.worker import SimpleWorker

listen = ['to_pdf']
redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
conn = redis.Redis.from_url(redis_url)

que = Queue(connection=conn, name='to_pdf')



# 转换pdf
# 定义文件转换后保存的目录
# basepath = os.path.abspath(os.path.dirname(__file__))
# FileSaveDir = os.path.join('/root/print/app/static/Upload_Files') #linux路径
FileSaveDir = os.path.join(os.path.dirname(__file__), 'app', 'static', 'Upload_Files')  #win路径


def switch_topdf(filename, current_Id):
    # cmd = "libreoffice --headless --convert-to pdf:writer_pdf_Export {} --outdir {}".format(filename, FileSaveDir) #mac linux

    cmd = "soffice --headless --convert-to pdf:writer_pdf_Export {} --outdir {}".format(filename, FileSaveDir)  # win
    print(cmd)

    # 生成失败标记文件路径（与 PDF 同目录同名但以 .failed 结尾）
    base = os.path.splitext(os.path.basename(filename))[0]
    failed_marker = os.path.join(FileSaveDir, base + '.failed')

    try:
        returnCode = subprocess.call(cmd, shell=True)
        # returnCode = os.system(cmd)
        if returnCode != 0:
            raise IOError("{} failed to switch".format(filename))
    except Exception:
        # 写失败标记，让 convert_status 端点能立即感知
        try:
            with open(failed_marker, 'w') as f:
                f.write('conversion failed')
        except Exception:
            pass
        conn.publish(current_Id, 'None')
        return 1
    else:
        conn.publish(current_Id, 'OK')
        return 0


if __name__ == '__main__':
    # Windows 没有 os.fork，必须用 SimpleWorker（单进程执行 job）
    worker = SimpleWorker(['to_pdf'], connection=conn)
    worker.work()