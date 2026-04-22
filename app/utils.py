# 自定义函数

import PyPDF2, subprocess, os, filetype, uuid, datetime, hashlib, json, requests, redis
from app.models import User


# from rq import Queue
# from app.worker import conn

# q = Queue(connection=conn)

# pool = redis.ConnectionPool(host='192.168.1.199', port=6379, password='Zxs123456', decode_responses=True)
# redis_client = redis.Redis(connection_pool=pool)



# 定义文件转换后保存的目录
basepath = os.path.abspath(os.path.dirname(__file__))
FileSaveDir = os.path.join(basepath, 'static/Upload_Files')



# 读取pdf页数
# def read_pdf_pages(file):
#     with open(file, 'rb') as PdfFileObj:
#         try:
#             PdfReader = PyPDF2.PdfFileReader(PdfFileObj)
#         except:
#             return None
#         else:
#             return PdfReader.numPages

def read_pdf_pages(file):
    with open(file, 'rb') as PdfFileObj:
        reader = PyPDF2.PdfReader(PdfFileObj)
        return len(reader.pages)


# 转pdf
def switch_topdf(filename):
    # cmd = "libreoffice --headless --convert-to pdf:writer_pdf_Export {} --outdir {}".format(filename, FileSaveDir) #mac linux

    cmd = "soffice --headless --convert-to pdf:writer_pdf_Export {} --outdir {}".format(filename, FileSaveDir)  # win
    print(cmd)
    try:
        returnCode = subprocess.call(cmd, shell=True)
        # returnCode = os.system(cmd)
        if returnCode != 0:
            raise IOError("{} failed to switch".format(filename))
    except Exception:
        return 1
    else:
        return 0


# 随机取文件名
def random_filename(filename):
    ext = os.path.splitext(filename)[1]
    new_filename = uuid.uuid4().hex + ext
    return new_filename


# 判断日期并记录数字
def date_count(db_date):
    if db_date.Born_Date_Day == datetime.datetime.now().date():
        macs = int(db_date.Trade_Number[9:]) + 1
        return macs
    else:
        macs = 1
        return macs


# ---------- 订单号生成：保证一号一单一码 ----------
def next_trade_number():
    """生成今日下一个可用订单号 YYYYMMDD-N。

    算法：扫描今日前缀的全部 Trade_Number，取数字部分的最大值 +1。
    - 相比 "当日订单总数+1"：订单被取消/删除后不会复用旧号，避免撞号。
    - 相比 "全表最新一条 +1"：不会因今天还没新单但昨天有单而错出 -None。
    - 索引到位时（`Trade_Number` 有 UNIQUE index），LIKE 'YYYYMMDD-%' 命中索引，很快。

    注意：本函数并发不安全（两个请求同时算出同号），所以写入时必须配合
    `save_order_atomic` 的唯一键冲突重试。
    """
    from app.models import db, Order  # 延迟导入避免循环
    prefix = datetime.date.today().strftime('%Y%m%d')
    rows = db.session.query(Order.Trade_Number).filter(
        Order.Trade_Number.like(prefix + '-%')
    ).all()
    max_seq = 0
    for (tn,) in rows:
        try:
            n = int(tn.rsplit('-', 1)[1])
            if n > max_seq:
                max_seq = n
        except (ValueError, IndexError, AttributeError, TypeError):
            continue
    return '{}-{}'.format(prefix, max_seq + 1)


def save_order_atomic(order, max_retries=5):
    """入库订单，若 Trade_Number 唯一键冲突则重新生成并重试。

    返回最终成功入库的订单号（可能与初始分配的不同）。
    上限 max_retries 次后仍失败则向上抛异常。
    """
    from app.models import db
    from sqlalchemy.exc import IntegrityError

    for attempt in range(max_retries):
        try:
            db.session.add(order)
            db.session.commit()
            return order.Trade_Number
        except IntegrityError:
            db.session.rollback()
            # 重新生成号码再来一次（本轮冲突大概率是并发插入撞号）
            order.Trade_Number = next_trade_number()
    # 已达重试上限，最后一次不再吞异常，向上抛出，让调用方感知
    db.session.add(order)
    db.session.commit()
    return order.Trade_Number


def sign(*p):
    return hashlib.md5(u''.join(p).encode('utf8')).hexdigest().lower()


def query_status(aoid):
    resp = requests.get('https://xorpay.com/api/query/' + aoid)
    return json.loads(resp.text)


def bedict_order(items):
    lic = []
    for item in items:
        tel = User.query.order_by(User.Id == item.User_Id)
        dicts = {
            'Print_Money': item.Print_Money,
            'File_Name': item.File_Name,
            'Print_Status': item.Print_Status,
            'Print_Copies': item.Print_Copies,
            'Print_Colour': item.Print_Colour,
            'Print_size': item.Print_size,
            'Print_way': item.Print_way,
            'Print_Direction':item.Print_Direction,
            'Trade_Number': item.Trade_Number,
            'tel_num': tel
            }
        lic.append(dicts)
    return lic


def bedict_order_date(items , b):
    da = datetime.datetime.strptime(b, '%Y-%m-%d').date()
    lic = []
    for item in items:
        if da == item.Born_Date_Day:
            born_date = str(item.Born_Date.year) + "-" + str(item.Born_Date.month) + "-" + str(
                item.Born_Date.day) + " " + str(item.Born_Date.hour) + ":" + str(item.Born_Date.minute) + ":" + str(
                item.Born_Date.second)
            lic.append(
                {
                'Print_Money': item.Print_Money,
                'File_Name': item.File_Name,
                'Born_Date': born_date,
                'Print_Place': item.Print_Place,
                'Print_Status': item.Print_Status,

                'Print_Copies': item.Print_Copies,
                'Print_Colour': item.Print_Colour,
                'Print_size': item.Print_size,
                'Print_way': item.Print_way,
                'Print_Direction':item.Print_Direction,
                'Print_Date': item.Print_Date,
                'File_Dir': item.File_Dir,
                'Trade_Number': item.Trade_Number
                }
            )
    return lic