new_cartube = frontend mua key tu cartube-server + admin/server Python tu source-web + SQLite DB dung chung.

Run local:
HOST=127.0.0.1 PORT=3010 ADMIN_PORT=3011 HTTPS_PORT=3012 python3 -B server.py

Public:
http://127.0.0.1:3010/ hoac /mua-key.html

Admin:
http://127.0.0.1:3010/admin

Runtime data local/server-side:
data/cartube.db
data/config.json

GitHub repo khong commit DB/token that. Khi deploy len VPS, copy DB/config rieng vao data/.
