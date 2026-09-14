#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
May chu key + kich hoat cho CarTube.

Chi dung THU VIEN CHUAN cua Python (http.server, sqlite3, json, secrets, hmac).
Khong phu thuoc goi ngoai -> deploy chi can copy 1 file + systemd.

Chuc nang:
  App  (cong khai):
    POST /v1/activate   {key, device}      -> kich hoat + gan may
    POST /v1/check      {key, device}       -> nhip tim / kiem tra con hieu luc
    POST /v1/deactivate {key, device}       -> DANG XUAT key khoi may
    POST /v1/order      {plan}              -> tao don thanh toan (STUB - tich hop sau)
  Admin (can token qua header X-Admin-Token hoac ?token=):
    GET  /                                  -> trang admin co ban (HTML)
    GET  /admin/list                        -> danh sach key (JSON)
    POST /admin/create  {plan, count, note} -> tao key
    POST /admin/disable {key} / enable {key}
    POST /admin/unbind  {key}               -> go may khoi key (dang xuat ho)
    POST /admin/delete  {key}
    GET/POST /admin/plans                    -> xem/sua bang gia (goi + gia + so ngay)

Bao mat: ban dau chay HTTP cleartext theo IP (chua co domain/HTTPS). App cho
phep cleartext RIENG IP nay. Se nang cap ky token/HTTPS sau (payment cung sau).
"""

import http.server
import socketserver
import json
import os
import re
import sqlite3
import secrets
import string
import hmac
import time
import ssl
import urllib.parse
import urllib.request
import mimetypes

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'data')
ASSETS = os.path.join(ROOT, 'assets')
os.makedirs(DATA, exist_ok=True)
os.makedirs(ASSETS, exist_ok=True)
DB_PATH = os.path.join(DATA, 'cartube.db')
CFG_PATH = os.path.join(DATA, 'config.json')

HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '24710'))


# ---------------------------------------------------------------- config -----
def load_config():
    cfg = {}
    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    changed = False
    if not cfg.get('admin_token'):
        cfg['admin_token'] = secrets.token_urlsafe(24)
        changed = True
    if changed:
        with open(CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def save_config(cfg):
    with open(CFG_PATH, 'w', encoding='utf-8') as fp:
        json.dump(cfg, fp, ensure_ascii=False, indent=2)


CFG = load_config()
_changed = False
for _k, _d in (('bank_bin', ''), ('bank_account', ''), ('bank_name', ''),
               ('webhook_secret', ''), ('sepay_api_key', '')):
    if _k not in CFG:
        CFG[_k] = _d
        _changed = True
if not CFG.get('webhook_secret'):
    CFG['webhook_secret'] = secrets.token_urlsafe(18)
    _changed = True
# Cho phep nap SEPAY_API_KEY tu env (uu tien)
if os.environ.get('SEPAY_API_KEY') and CFG.get('sepay_api_key') != os.environ.get('SEPAY_API_KEY'):
    CFG['sepay_api_key'] = os.environ['SEPAY_API_KEY']
    _changed = True
if _changed:
    save_config(CFG)
ADMIN_TOKEN = CFG['admin_token']
PUBLIC_WEBHOOK_BASE = (os.environ.get('PUBLIC_WEBHOOK_BASE') or '').rstrip('/')

ADMIN_HTML_PATH = os.path.join(ROOT, 'admin.html')


def load_admin_html():
    """Doc trang admin tu file (de sua giao dien khong can restart)."""
    try:
        with open(ADMIN_HTML_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ('<!doctype html><meta charset="utf-8"><title>CarTube Admin</title>'
                '<h1>CarTube Admin</h1><p>Thieu file admin.html.</p>')


# -------------------------------------------------------------------- db -----
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS keys (
            key         TEXT PRIMARY KEY,
            plan        TEXT,
            price       INTEGER DEFAULT 0,
            days        INTEGER DEFAULT 0,      -- 0 = vinh vien
            status      TEXT DEFAULT 'unused',  -- unused | active | disabled
            device      TEXT,                   -- may dang gan (null = chua gan)
            note        TEXT,
            created_at  INTEGER,
            activated_at INTEGER,
            expires_at  INTEGER                 -- 0/null = vinh vien
        );
        CREATE TABLE IF NOT EXISTS plans (
            name      TEXT PRIMARY KEY,
            price     INTEGER DEFAULT 0,
            days      INTEGER DEFAULT 0,
            published INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders (
            id         TEXT PRIMARY KEY,
            plan       TEXT,
            amount     INTEGER,
            status     TEXT DEFAULT 'pending',  -- pending | paid | canceled
            key        TEXT,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS shop_orders (
            code       TEXT PRIMARY KEY,        -- ma don = noi dung CK
            plan       TEXT,
            amount     INTEGER,
            contact    TEXT,
            status     TEXT DEFAULT 'pending',  -- pending | paid | canceled
            key        TEXT,                    -- key sinh ra khi da tra
            txn_id     TEXT,
            created_at INTEGER,
            paid_at    INTEGER
        );
        """
    )
    # gia mac dinh neu bang rong
    n = conn.execute('SELECT COUNT(*) c FROM plans').fetchone()['c']
    if n == 0:
        conn.executemany(
            'INSERT INTO plans(name,price,days,published) VALUES(?,?,?,?)',
            [
                ('1thang', 50000, 30, 1),
                ('6thang', 250000, 180, 0),
                ('12thang', 450000, 365, 0),
                ('vinhvien', 150000, 0, 1),
            ],
        )
    conn.commit()
    conn.close()


init_db()


def ensure_column(table, column, column_type):
    conn = db()
    cols = [r['name'] for r in conn.execute('PRAGMA table_info(%s)' % table).fetchall()]
    if column not in cols:
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, column_type))
        conn.commit()
    conn.close()


ensure_column('shop_orders', 'contact', 'TEXT')
ensure_column('plans', 'published', 'INTEGER DEFAULT 1')


# ---------------------------------------------------------------- helpers ----
KEY_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'  # bo 0O1I de de doc


def gen_key():
    parts = []
    for _ in range(3):
        parts.append(''.join(secrets.choice(KEY_ALPHABET) for _ in range(4)))
    return 'CT-' + '-'.join(parts)


def norm_key(k):
    """Chuan hoa key ve dang chinh 'CT-XXXX-XXXX-XXXX' - chap nhan nguoi dung
    go co/khong dau '-', khoang trang, chu thuong."""
    x = re.sub(r'[^A-Za-z0-9]', '', k or '').upper()
    if len(x) <= 2:
        return x
    parts = [x[:2]]
    i = 2
    while i < len(x):
        parts.append(x[i:i + 4])
        i += 4
    return '-'.join(parts)


def now():
    return int(time.time())


ORDER_ALPHABET = '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ'


def gen_order_code():
    return 'CT' + ''.join(secrets.choice(ORDER_ALPHABET) for _ in range(6))


def qr_url(amount, code):
    b_bin = CFG.get('bank_bin', '')
    acc = CFG.get('bank_account', '')
    if not b_bin or not acc:
        return ''
    q = urllib.parse.urlencode({
        'amount': str(amount),
        'addInfo': code,
        'accountName': CFG.get('bank_name', ''),
    })
    return 'https://img.vietqr.io/image/%s-%s-compact2.png?%s' % (b_bin, acc, q)


def parse_amount(v):
    if v is None or v == '':
        return None
    try:
        return int(float(re.sub(r'[^0-9.]', '', str(v))))
    except Exception:
        return None


def extract_order_code(text):
    m = re.search(r'CT[0-9A-Z]{6}', str(text or '').upper())
    return m.group(0) if m else ''


def sepay_has_payment(code, amount=None):
    """Hoi SePay API xem da co giao dich IN chua. Tra dict {txn_id, amount} hoac None."""
    token = (CFG.get('sepay_api_key') or os.environ.get('SEPAY_API_KEY') or '').strip()
    if not token or not code:
        return None
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json',
    }
    urls = [
        'https://userapi.sepay.vn/v2/transactions?q=%s&transfer_type=in&per_page=20'
        % urllib.parse.quote(code),
        'https://my.sepay.vn/userapi/transactions/list?limit=50',
    ]
    want = int(amount or 0)
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read().decode('utf-8', 'replace')
            j = json.loads(raw)
            rows = j.get('data') or j.get('transactions') or []
            if isinstance(rows, dict):
                rows = rows.get('transactions') or rows.get('data') or []
            for tx in rows:
                text = ' '.join(str(tx.get(k) or '') for k in (
                    'transaction_content', 'content', 'code', 'description', 'remark'))
                got = extract_order_code(text)
                if got != code:
                    continue
                pay = parse_amount(
                    tx.get('amount_in') or tx.get('transferAmount') or tx.get('amount')
                ) or 0
                ttype = str(tx.get('transfer_type') or tx.get('transferType') or 'in')
                if ttype == 'out':
                    continue
                if want and pay and pay < want:
                    continue
                return {
                    'txn_id': str(tx.get('id') or tx.get('reference_number') or ''),
                    'amount': pay or want or None,
                }
        except Exception as e:
            print('sepay poll fail %s: %s' % (url, e))
    return None


BUY_HTML_PATH = os.path.join(ROOT, 'buy.html')


def load_buy_html():
    try:
        with open(BUY_HTML_PATH, 'r', encoding='utf-8') as fp:
            return fp.read()
    except Exception:
        return ('<!doctype html><meta charset="utf-8"><title>CarTube</title>'
                '<h1>CarTube</h1><p>Thieu file buy.html.</p>')


def key_row_public(r):
    return {
        'key': r['key'],
        'plan': r['plan'],
        'status': r['status'],
        'device': r['device'],
        'days': r['days'],
        'expires_at': r['expires_at'] or 0,
    }


def is_expired(r):
    exp = r['expires_at'] or 0
    return exp != 0 and now() > exp


# ---------------------------------------------------------------- handler ----
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'CarTubeKey/1.0'

    # --- utils ---
    def _send(self, code, obj, ctype='application/json'):
        if ctype == 'application/json':
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        else:
            body = obj if isinstance(obj, bytes) else str(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Admin-Token, X-Webhook-Secret, Authorization')
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _body(self):
        try:
            n = int(self.headers.get('Content-Length', '0') or '0')
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n > 0 else b''
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            # thu dang form
            try:
                return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode('utf-8')).items()}
            except Exception:
                return {}

    def _query(self):
        u = urllib.parse.urlparse(self.path)
        return u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}

    def _admin_ok(self, q):
        tok = self.headers.get('X-Admin-Token') or q.get('token') or ''
        return hmac.compare_digest(tok, ADMIN_TOKEN)

    def log_message(self, fmt, *args):
        # gon log
        try:
            print('%s - %s' % (self.address_string(), fmt % args))
        except Exception:
            pass

    def do_OPTIONS(self):
        self._send(204, b'', ctype='text/plain')

    # --- GET ---
    def do_GET(self):
        path, q = self._query()
        if path.startswith('/assets/'):
            return self._static_asset(path)
        if path.startswith('/downloads/'):
            return self._static_file(path[len('/'):])
        if path in ('/styles.css', '/app.js', '/mua-key.html', '/favicon.ico'):
            return self._static_file(path.lstrip('/'))
        # ACME HTTP-01 challenge (de xin Let's Encrypt tu may co internet)
        if path.startswith('/.well-known/acme-challenge/'):
            name = path.rsplit('/', 1)[-1]
            if re.match(r'^[A-Za-z0-9_.-]+$', name):
                fp = os.path.join(ROOT, 'acme-challenge', name)
                if os.path.isfile(fp):
                    with open(fp, 'rb') as f:
                        return self._send(200, f.read(), ctype='text/plain')
            return self._send(404, 'not found', ctype='text/plain')
        if path == '/health' or path == '/v1/ping':
            return self._send(200, {'ok': True, 'ts': now()})
        if path == '/getPublicContent':
            return self._send(200, {
                'ok': True,
                'result': {
                    'appName': 'CarTube',
                    'zalo': '077 91 88 789',
                    'website': 'https://cartube.io.vn',
                },
            })
        if path == '/v1/plans' or path == '/v1/shop/plans':
            conn = db()
            rows = conn.execute('SELECT name,price,days FROM plans WHERE COALESCE(published,1)=1 ORDER BY days').fetchall()
            conn.close()
            return self._send(200, {'ok': True, 'plans': [dict(r) for r in rows]})
        if path == '/v1/webhooks/sepay':
            return self._send(200, {
                'ok': True,
                'service': 'cartube-webhook',
                'hint': 'POST giao dich co tien vao vao URL nay, kem ?secret=WEBHOOK_SECRET',
            })
        if path == '/':
            return self._send(200, load_buy_html(), ctype='text/html')
        if path == '/admin':
            return self._admin_page(q)
        m = re.match(r'^/v1/order/([A-Za-z0-9]+)$', path)
        if m:
            return self._shop_get(m.group(1))
        if path == '/admin/bank':
            if not self._admin_ok(q):
                return self._send(401, {'ok': False, 'error': 'unauthorized'})
            secret = CFG.get('webhook_secret', '')
            origin = PUBLIC_WEBHOOK_BASE or ('http://%s:%s' % (HOST, PORT))
            # Prefer HTTPS public base for SePay
            hook = origin.rstrip('/') + '/v1/webhook/bank'
            return self._send(200, {
                'ok': True,
                'bank': self._bank(),
                'webhook_secret': secret,
                'webhook_url': hook,
                'sepay_api_configured': bool(CFG.get('sepay_api_key')),
            })
        if path == '/admin/orders':
            if not self._admin_ok(q):
                return self._send(401, {'ok': False, 'error': 'unauthorized'})
            conn = db()
            rows = conn.execute('SELECT * FROM shop_orders ORDER BY created_at DESC '
                                'LIMIT 300').fetchall()
            conn.close()
            return self._send(200, {'ok': True, 'orders': [dict(r) for r in rows]})
        if path == '/admin/list':
            if not self._admin_ok(q):
                return self._send(401, {'ok': False, 'error': 'unauthorized'})
            conn = db()
            rows = conn.execute('SELECT * FROM keys ORDER BY created_at DESC').fetchall()
            conn.close()
            return self._send(200, {'ok': True, 'keys': [dict(r) for r in rows]})
        if path == '/admin/plans':
            if not self._admin_ok(q):
                return self._send(401, {'ok': False, 'error': 'unauthorized'})
            conn = db()
            rows = conn.execute('SELECT * FROM plans ORDER BY days').fetchall()
            conn.close()
            return self._send(200, {'ok': True, 'plans': [dict(r) for r in rows]})
        if path.startswith('/pay/'):
            oid = path[len('/pay/'):]
            return self._send(200,
                              '<h3>Thanh toan don ' + re.sub(r'[^0-9a-zA-Z_-]', '', oid) +
                              '</h3><p>Cong thanh toan online se tich hop sau.</p>',
                              ctype='text/html')
        return self._send(404, {'ok': False, 'error': 'not_found'})

    def _static_asset(self, path):
        name = urllib.parse.unquote(path[len('/assets/'):])
        if not name or '/' in name or '\\' in name or name.startswith('.'):
            return self._send(404, {'ok': False, 'error': 'not_found'})
        return self._static_file('assets/' + name)

    def _static_file(self, rel):
        rel = urllib.parse.unquote(rel or '')
        parts = [x for x in rel.split('/') if x]
        if not parts or any(x == '..' or x.startswith('.') for x in parts):
            return self._send(404, {'ok': False, 'error': 'not_found'})
        fp = os.path.join(ROOT, *parts)
        if not os.path.isfile(fp) or not os.path.abspath(fp).startswith(ROOT + os.sep):
            return self._send(404, {'ok': False, 'error': 'not_found'})
        ctype = mimetypes.guess_type(fp)[0] or 'application/octet-stream'
        with open(fp, 'rb') as f:
            return self._send(200, f.read(), ctype=ctype)

    # --- POST ---
    def do_POST(self):
        path, q = self._query()
        body = self._body()

        if path == '/v1/activate':
            return self._activate(body)
        if path == '/v1/check':
            return self._check(body)
        if path == '/checkDeviceLicense' or path == '/v1/app/check-device-license':
            return self._check_device_license(body, q)
        if path == '/v1/deactivate':
            return self._deactivate(body)
        if path == '/v1/order' or path == '/v1/shop/order':
            return self._shop_order(body)
        m = re.match(r'^/v1/webhook/([A-Za-z0-9_-]+)$', path)
        if m or path in ('/webhook', '/v1/webhooks/sepay', '/v1/shop/webhook'):
            return self._webhook(body, m.group(1) if m else 'default', q)

        # admin
        if path.startswith('/admin/'):
            if not self._admin_ok(q):
                return self._send(401, {'ok': False, 'error': 'unauthorized'})
            if path == '/admin/create':
                return self._admin_create(body)
            if path == '/admin/disable':
                return self._admin_setstatus(body, 'disabled')
            if path == '/admin/enable':
                return self._admin_setstatus(body, 'active')
            if path == '/admin/unbind':
                return self._admin_unbind(body)
            if path == '/admin/delete':
                return self._admin_delete(body)
            if path == '/admin/plans':
                return self._admin_plans(body)
            if path == '/admin/bank':
                return self._admin_bank_set(body)
            m = re.match(r'^/admin/order/([A-Za-z0-9]+)/paid$', path)
            if m:
                return self._admin_mark_paid(m.group(1))

        return self._send(404, {'ok': False, 'error': 'not_found'})

    # ============================================================ app api ===
    def _activate(self, b):
        key = norm_key(b.get('key'))
        device = (b.get('device') or '').strip()
        if not key or not device:
            return self._send(400, {'ok': False, 'error': 'missing_params'})
        conn = db()
        r = conn.execute('SELECT * FROM keys WHERE key=?', (key,)).fetchone()
        if not r:
            conn.close()
            return self._send(200, {'ok': False, 'error': 'key_not_found'})
        if r['status'] == 'disabled':
            conn.close()
            return self._send(200, {'ok': False, 'error': 'disabled'})
        if r['device'] and r['device'] != device:
            conn.close()
            return self._send(200, {'ok': False, 'error': 'bound_other'})
        if is_expired(r):
            conn.close()
            return self._send(200, {'ok': False, 'error': 'expired'})
        # gan may + tinh han (lan dau kich hoat)
        activated_at = r['activated_at'] or now()
        if r['expires_at']:
            expires_at = r['expires_at']
        elif r['days'] and r['days'] > 0:
            expires_at = activated_at + r['days'] * 86400
        else:
            expires_at = 0  # vinh vien
        conn.execute(
            'UPDATE keys SET status=?, device=?, activated_at=?, expires_at=? WHERE key=?',
            ('active', device, activated_at, expires_at, key),
        )
        conn.commit()
        conn.close()
        return self._send(200, {
            'ok': True, 'key': key, 'plan': r['plan'],
            'expires_at': expires_at, 'device': device,
        })

    def _check(self, b):
        key = norm_key(b.get('key'))
        device = (b.get('device') or '').strip()
        if not key or not device:
            return self._send(400, {'ok': False, 'error': 'missing_params'})
        conn = db()
        r = conn.execute('SELECT * FROM keys WHERE key=?', (key,)).fetchone()
        conn.close()
        if not r:
            return self._send(200, {'ok': False, 'error': 'key_not_found'})
        if r['status'] == 'disabled':
            return self._send(200, {'ok': False, 'error': 'disabled'})
        if r['device'] != device:
            return self._send(200, {'ok': False, 'error': 'bound_other'})
        if is_expired(r):
            return self._send(200, {'ok': False, 'error': 'expired'})
        return self._send(200, {'ok': True, 'key': key, 'expires_at': r['expires_at'] or 0})

    def _deactivate(self, b):
        key = norm_key(b.get('key'))
        device = (b.get('device') or '').strip()
        if not key:
            return self._send(400, {'ok': False, 'error': 'missing_params'})
        conn = db()
        r = conn.execute('SELECT * FROM keys WHERE key=?', (key,)).fetchone()
        if not r:
            conn.close()
            return self._send(200, {'ok': False, 'error': 'key_not_found'})
        # chi go neu dung may (hoac khong gui device -> cho phep go)
        if device and r['device'] and r['device'] != device:
            conn.close()
            return self._send(200, {'ok': False, 'error': 'bound_other'})
        conn.execute('UPDATE keys SET device=NULL, status=? WHERE key=?', ('unused', key))
        conn.commit()
        conn.close()
        return self._send(200, {'ok': True, 'key': key})

    def _check_device_license(self, b, q):
        data = b.get('data') if isinstance(b.get('data'), dict) else b
        submitted = norm_key(data.get('key') or data.get('licenseKey') or q.get('key') or '')
        device = (data.get('device') or data.get('deviceUuid') or data.get('installUuid') or '').strip()
        valid_uuid = bool(device)
        conn = db()
        r = conn.execute('SELECT * FROM keys WHERE key=?', (submitted,)).fetchone() if submitted else None
        conn.close()
        active = bool(r and r['status'] != 'disabled' and not is_expired(r)
                      and (not r['device'] or not device or r['device'] == device))
        return self._send(200, {
            'result': {
                'validUuid': valid_uuid,
                'licenseActive': active,
                'reason': 'ok' if active else 'license-inactive',
                'key': submitted if active else None,
                'expiresAt': (r['expires_at'] or None) if active else None,
            }
        })

    # ============================================================== shop ===
    def _bank(self):
        return {'bin': CFG.get('bank_bin', ''), 'account': CFG.get('bank_account', ''),
                'name': CFG.get('bank_name', '')}

    def _shop_order(self, b):
        """Tao don mua key: chon goi -> ma don (noi dung CK) + QR VietQR."""
        plan = (b.get('plan') or '').strip()
        contact = (b.get('contact') or b.get('email') or '').strip()[:120]
        if not contact:
            return self._send(400, {'ok': False, 'error': 'contact_required'})
        conn = db()
        p = conn.execute('SELECT * FROM plans WHERE name=? AND COALESCE(published,1)=1', (plan,)).fetchone()
        if not p:
            conn.close()
            return self._send(400, {'ok': False, 'error': 'plan_not_found'})
        code = gen_order_code()
        while conn.execute('SELECT 1 FROM shop_orders WHERE code=?', (code,)).fetchone():
            code = gen_order_code()
        amount = p['price']
        conn.execute('INSERT INTO shop_orders(code,plan,amount,contact,status,created_at) '
                     'VALUES(?,?,?,?,?,?)', (code, plan, amount, contact, 'pending', now()))
        conn.commit()
        conn.close()
        return self._send(200, {
            'ok': True, 'code': code, 'plan': plan, 'amount': amount,
            'days': p['days'], 'content': code, 'status': 'pending',
            'bank': self._bank(), 'qr_url': qr_url(amount, code),
        })

    def _shop_get(self, code):
        """Tra cuu don: dang cho / da tra (kem key)."""
        code = re.sub(r'[^A-Za-z0-9]', '', code or '').upper()
        conn = db()
        o = conn.execute('SELECT * FROM shop_orders WHERE code=?', (code,)).fetchone()
        conn.close()
        if not o:
            return self._send(404, {'ok': False, 'error': 'order_not_found'})
        # Auto-accept: neu dang pending, hoi SePay API xem tien da vao chua
        if o['status'] != 'paid':
            hit = sepay_has_payment(code, o['amount'])
            if hit:
                self._fulfill(code, txn_id=hit.get('txn_id'), paid_amount=hit.get('amount'))
                conn = db()
                o = conn.execute('SELECT * FROM shop_orders WHERE code=?', (code,)).fetchone()
                conn.close()
        resp = {'ok': True, 'code': o['code'], 'plan': o['plan'],
                'amount': o['amount'], 'status': o['status']}
        if o['status'] == 'paid':
            resp['key'] = o['key']
        else:
            resp['bank'] = self._bank()
            resp['content'] = o['code']
            resp['qr_url'] = qr_url(o['amount'], o['code'])
        return self._send(200, resp)

    def _fulfil(self, code, txn_id=None, paid_amount=None):
        """Sinh key cho don + danh dau da tra. Tra ve key (str) hoac None."""
        conn = db()
        o = conn.execute('SELECT * FROM shop_orders WHERE code=?', (code,)).fetchone()
        if not o:
            conn.close()
            return None
        if paid_amount is not None and paid_amount < int(o['amount'] or 0):
            conn.close()
            return False
        if o['status'] == 'paid':
            k = o['key']
            conn.close()
            return k
        p = conn.execute('SELECT * FROM plans WHERE name=?', (o['plan'],)).fetchone()
        if not p:
            conn.close()
            return None
        k = gen_key()
        while conn.execute('SELECT 1 FROM keys WHERE key=?', (k,)).fetchone():
            k = gen_key()
        conn.execute('INSERT INTO keys(key,plan,price,days,status,note,created_at) '
                     'VALUES(?,?,?,?,?,?,?)',
                     (k, o['plan'], p['price'], p['days'], 'unused', 'don ' + code, now()))
        conn.execute("UPDATE shop_orders SET status='paid', key=?, txn_id=COALESCE(?, txn_id), paid_at=? WHERE code=?",
                     (k, txn_id, now(), code))
        conn.commit()
        conn.close()
        return k

    def _admin_mark_paid(self, code):
        code = re.sub(r'[^A-Za-z0-9]', '', code or '').upper()
        k = self._fulfil(code)
        if k is None:
            return self._send(400, {'ok': False, 'error': 'cannot_fulfil'})
        return self._send(200, {'ok': True, 'code': code, 'key': k})

    def _webhook(self, b, provider, q=None):
        """Nhan giao dich tu ngan hang/SePay/Casso -> khop don theo ma trong noi
        dung -> sinh key. HIEN CHUA DAU vao bank nao; dau sau (dat webhook_secret).
        """
        q = q or {}
        auth = str(self.headers.get('Authorization') or '')
        auth_secret = ''
        for prefix in ('Apikey ', 'Bearer ', 'APIKey '):
            if auth.lower().startswith(prefix.lower()):
                auth_secret = auth[len(prefix):].strip()
                break
        secret = (q.get('secret') or self.headers.get('X-Webhook-Secret')
                  or auth_secret
                  or (b.get('secret') if isinstance(b, dict) else '') or '')
        want = CFG.get('webhook_secret', '')
        if want and not hmac.compare_digest(str(secret), want):
            return self._send(401, {'ok': False, 'error': 'bad_secret'})
        desc = ''
        amount = None
        txn_id = None
        if isinstance(b, dict):
            desc = str(b.get('description') or b.get('content') or b.get('addInfo')
                       or b.get('memo') or b.get('transferContent')
                       or b.get('transaction_content') or b.get('remark') or b.get('des') or '')
            amount = b.get('amount') or b.get('transferAmount') or b.get('amount_in') or b.get('transfer_amount')
            txn_id = b.get('id') or b.get('transaction_id') or b.get('referenceCode') or b.get('code')
            data = b.get('data')
            if isinstance(data, dict):
                if not desc:
                    desc = str(data.get('description') or data.get('content')
                               or data.get('addInfo') or data.get('memo')
                               or data.get('transferContent') or data.get('transaction_content')
                               or data.get('remark') or data.get('des') or '')
                amount = amount or data.get('amount') or data.get('transferAmount') or data.get('amount_in') or data.get('transfer_amount')
                txn_id = txn_id or data.get('id') or data.get('transaction_id') or data.get('referenceCode') or data.get('code')
        m = re.search(r'CT[0-9A-Z]{6}', desc.upper())
        code = m.group(0) if m else (b.get('code') if isinstance(b, dict) else '')
        if not code:
            return self._send(200, {'ok': False, 'error': 'no_order_code'})
        k = self._fulfil(code, txn_id=txn_id, paid_amount=parse_amount(amount))
        if k is None:
            return self._send(200, {'ok': False, 'error': 'order_not_found'})
        if k is False:
            return self._send(200, {'ok': False, 'error': 'amount_too_low', 'code': code})
        return self._send(200, {'ok': True, 'code': code, 'key': k})

    def _admin_bank_set(self, b):
        CFG['bank_bin'] = str(b.get('bin') or '').strip()
        CFG['bank_account'] = str(b.get('account') or '').strip()
        CFG['bank_name'] = str(b.get('name') or '').strip()
        save_config(CFG)
        return self._send(200, {'ok': True, 'bank': self._bank()})

    # ============================================================== admin ===
    def _admin_create(self, b):
        plan = (b.get('plan') or '').strip()
        try:
            count = max(1, min(500, int(b.get('count') or 1)))
        except (TypeError, ValueError):
            count = 1
        note = (b.get('note') or '').strip()
        conn = db()
        p = conn.execute('SELECT * FROM plans WHERE name=?', (plan,)).fetchone()
        if not p:
            conn.close()
            return self._send(400, {'ok': False, 'error': 'plan_not_found'})
        made = []
        for _ in range(count):
            k = gen_key()
            while conn.execute('SELECT 1 FROM keys WHERE key=?', (k,)).fetchone():
                k = gen_key()
            conn.execute(
                'INSERT INTO keys(key,plan,price,days,status,note,created_at) '
                'VALUES(?,?,?,?,?,?,?)',
                (k, plan, p['price'], p['days'], 'unused', note, now()),
            )
            made.append(k)
        conn.commit()
        conn.close()
        return self._send(200, {'ok': True, 'created': made, 'plan': plan})

    def _admin_setstatus(self, b, status):
        key = norm_key(b.get('key'))
        conn = db()
        r = conn.execute('SELECT * FROM keys WHERE key=?', (key,)).fetchone()
        if not r:
            conn.close()
            return self._send(200, {'ok': False, 'error': 'key_not_found'})
        # enable: neu chua gan may -> ve 'unused', neu da gan -> 'active'
        if status == 'active' and not r['device']:
            status = 'unused'
        conn.execute('UPDATE keys SET status=? WHERE key=?', (status, key))
        conn.commit()
        conn.close()
        return self._send(200, {'ok': True, 'key': key, 'status': status})

    def _admin_unbind(self, b):
        key = norm_key(b.get('key'))
        conn = db()
        r = conn.execute('SELECT * FROM keys WHERE key=?', (key,)).fetchone()
        if not r:
            conn.close()
            return self._send(200, {'ok': False, 'error': 'key_not_found'})
        conn.execute('UPDATE keys SET device=NULL, status=? WHERE key=?', ('unused', key))
        conn.commit()
        conn.close()
        return self._send(200, {'ok': True, 'key': key})

    def _admin_delete(self, b):
        key = norm_key(b.get('key'))
        conn = db()
        conn.execute('DELETE FROM keys WHERE key=?', (key,))
        conn.commit()
        conn.close()
        return self._send(200, {'ok': True, 'key': key})

    def _admin_plans(self, b):
        # b: {plans:[{name,price,days,published}, ...]}  -> ghi de toan bo
        plans = b.get('plans')
        if not isinstance(plans, list):
            return self._send(400, {'ok': False, 'error': 'bad_plans'})
        conn = db()
        keep = []
        for p in plans:
            name = (p.get('name') or '').strip()
            if not name:
                continue
            price = int(p.get('price') or 0)
            days = int(p.get('days') or 0)
            published = 1 if p.get('published', True) else 0
            conn.execute(
                'INSERT INTO plans(name,price,days,published) VALUES(?,?,?,?) '
                'ON CONFLICT(name) DO UPDATE SET price=excluded.price, days=excluded.days, published=excluded.published',
                (name, price, days, published),
            )
            keep.append(name)
        # Dong bo: xoa cac goi KHONG con trong danh sach gui len (goi da xoa o UI).
        # Key da tao khong bi anh huong (chung luu ban sao price/days rieng).
        if keep:
            placeholders = ','.join('?' * len(keep))
            conn.execute('DELETE FROM plans WHERE name NOT IN (%s)' % placeholders, keep)
        else:
            conn.execute('DELETE FROM plans')
        conn.commit()
        rows = conn.execute('SELECT * FROM plans ORDER BY days').fetchall()
        conn.close()
        return self._send(200, {'ok': True, 'plans': [dict(r) for r in rows]})

    # =============================================================== page ===
    def _admin_page(self, q):
        # Trang admin (Apple-style) doc tu admin.html.
        self._send(200, load_admin_html(), ctype='text/html')


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        # Bo qua getfqdn() cua HTTPServer (reverse-DNS lam khoi dong cham ~20s
        # khi bind 0.0.0.0). Gan ten/cong thu cong.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


CERT_DIR = os.path.join(ROOT, 'certs')


def _make_server(host, port):
    srv = ThreadingHTTPServer((host, port), Handler)
    if port == 443:
        cert = os.path.join(CERT_DIR, 'fullchain.pem')
        key = os.path.join(CERT_DIR, 'privkey.pem')
        if not (os.path.isfile(cert) and os.path.isfile(key)):
            srv.server_close()
            raise OSError('no TLS cert in %s' % CERT_DIR)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    return srv


def main():
    import threading
    # Nghe nhieu cong: 24710 (app hien dung) + 80 (domain HTTP + ACME) + 443
    # (HTTPS neu co cert). VPS inbound-only nen certbot chay o may khac roi copy
    # cert vao certs/. Thieu cert thi bo qua 443, phan con lai van chay.
    def envport(k, d):
        try:
            return int(os.environ.get(k, str(d)))
        except ValueError:
            return d
    ports = [PORT, envport('ADMIN_PORT', 80), envport('HTTPS_PORT', 443)]
    servers = []
    for p in dict.fromkeys(ports):
        try:
            servers.append(_make_server(HOST, p))
            print('CarTube key server on %s:%d  db=%s' % (HOST, p, DB_PATH))
        except OSError as e:
            print('skip port %d: %s' % (p, e))
    if not servers:
        return
    print('Admin token: %s' % ADMIN_TOKEN)
    for srv in servers[:-1]:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        servers[-1].serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
