#### 启动项目
run.bat----->>启动web服务
run_worker.bat----->>启动worker服务----->>处理pdf文件
run_daemon.bat----->>启动打印守护进程-----轮询未打印的订单
run_local_print.bat----->>启动本地打印服务-----订单打印

#### 流程
用户上传文件---->>创建订单---->>调用支付

#### 状态
待支付---->>已支付---->>已完成


### 内网穿透
cpolar start website
本地8081端口

### 启动项目前先启动
redis 启动：redis-server.exe redis.windows.conf
高性能的开源键值对数据库
存储在内存中