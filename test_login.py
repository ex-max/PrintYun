import requests

try:
    r = requests.get('http://127.0.0.1:8001/login/login')
    print(f'GET /login/login: HTTP {r.status_code}')

    r2 = requests.post('http://127.0.0.1:8001/login/login', data={
        'tel': '123456',
        'password': '123456',
        'remember': False
    }, allow_redirects=False)
    print(f'POST /login/login: HTTP {r2.status_code}')
    print(f'Redirection: {r2.headers.get("Location", "None")}')
except Exception as e:
    print(f'Error: {e}')
