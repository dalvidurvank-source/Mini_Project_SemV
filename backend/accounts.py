"""Password authentication, opaque sessions and server-owned account roles."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from http.cookies import SimpleCookie

from backend.database import connect

COOKIE='agrolink_session'
ITERATIONS=600000
LIFETIME=7*24*3600


class AppError(Exception):
    def __init__(self,status,message):
        super().__init__(message)
        self.status=status


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def password_matches(password,stored):
    scheme,iterations,salt,expected=stored.split('$')
    actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations)).hex()
    return scheme=='pbkdf2_sha256' and hmac.compare_digest(actual,expected)


def public_user(row):
    return {k:row[k] for k in ('id','email','name','role')}


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def current(headers,required=True):
    cookies=SimpleCookie()
    try:
        cookies.load(headers.get('Cookie',''))
        token=cookies[COOKIE].value if COOKIE in cookies else ''
    except Exception:
        token=''
    if len(token)>200:
        token=''
    with connect() as db:
        row=db.execute('''SELECT u.*,s.csrf,s.token_hash FROM app_sessions s
                          JOIN app_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?''',
                       (token_hash(token),time.time())).fetchone() if token else None
    if row is None:
        if required: raise AppError(401,'Please sign in to continue.')
        return None
    return {**public_user(row),'csrf':row['csrf'],'session_hash':row['token_hash']}


def require(headers,role=None,mutation=False):
    user=current(headers)
    if role and user['role']!=role:
        raise AppError(403,f'This action is available only to {role} accounts.')
    if mutation and not hmac.compare_digest(str(headers.get('X-CSRF-Token','')),user['csrf']):
        raise AppError(403,'Session protection failed. Refresh the page and try again.')
    return user


def check_origin(handler):
    import os
    configured=os.environ.get('AGROLINK_FRONTEND_ORIGIN','http://localhost:5173')
    allowed={configured,'http://localhost:5173','http://127.0.0.1:5173'}
    origin=handler.headers.get('Origin')
    if origin and origin not in allowed:
        raise AppError(403,'This website origin is not allowed.')
    # JSON custom headers block form-based login CSRF, including absent Origin.
    if handler.headers.get('X-Agrolink-Client')!='1':
        raise AppError(403,'Use the AgroLink application to submit this request.')


def cookie_header(token,clear=False):
    import os
    secure='; Secure' if os.environ.get('AGROLINK_COOKIE_SECURE')=='1' else ''
    return f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={0 if clear else LIFETIME}{secure}'


def new_session(db,user_id):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    db.execute('DELETE FROM app_sessions WHERE expires_at<=?',(time.time(),))
    db.execute('INSERT INTO app_sessions VALUES (?,?,?,?)',(token_hash(token),user_id,csrf,time.time()+LIFETIME))
    return token,csrf


def credentials(payload):
    email=payload.get('email');password=payload.get('password')
    if not isinstance(email,str) or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email.strip()):
        raise AppError(422,'Enter a valid email address.')
    if not isinstance(password,str) or not 12<=len(password)<=128:
        raise AppError(422,'Use a password between 12 and 128 characters.')
    return email.strip().casefold(),password


def register(payload,ip=None):
    if ip:
        key=token_hash('register|'+ip)
        with connect() as db:
            db.execute('DELETE FROM app_login_failures WHERE attempted_at<?',(time.time()-900,))
            if db.execute('SELECT count(*) FROM app_login_failures WHERE key=?',(key,)).fetchone()[0]>=20:
                raise AppError(429,'Too many registration attempts. Try again in 15 minutes.')
            db.execute('INSERT INTO app_login_failures VALUES (?,?)',(key,time.time()))
    email,password=credentials(payload)
    name=payload.get('name');role=payload.get('role')
    if not isinstance(name,str) or not 2<=len(name.strip())<=100:
        raise AppError(422,'Enter a name between 2 and 100 characters.')
    if role not in ('farmer','buyer'):
        raise AppError(422,'Choose Farmer or Buyer. Account roles cannot be changed through profile requests.')
    user={'id':uuid.uuid4().hex,'email':email,'name':name.strip(),'role':role}
    hashed=password_hash(password)
    try:
        with connect() as db:
            db.execute('INSERT INTO app_users VALUES (?,?,?,?,?,?)',
                       (user['id'],email,user['name'],role,hashed,timestamp()))
            token,csrf=new_session(db,user['id'])
    except sqlite3.IntegrityError:
        raise AppError(409,'An account already uses this email address. Sign in instead.')
    return {'user':user,'csrf':csrf},cookie_header(token)


def login(payload,ip):
    email,password=credentials(payload)
    keys=(token_hash(ip),token_hash(ip+'|'+email))
    with connect() as db:
        db.execute('DELETE FROM app_login_failures WHERE attempted_at<?',(time.time()-900,))
        counts=[db.execute('SELECT count(*) FROM app_login_failures WHERE key=?',(k,)).fetchone()[0] for k in keys]
        if counts[0]>=60 or counts[1]>=5:
            raise AppError(429,'Too many sign-in attempts. Try again in 15 minutes.')
        row=db.execute('SELECT * FROM app_users WHERE email=?',(email,)).fetchone()
    # Missing accounts still run the password derivation to reduce timing leakage.
    stored=row['password_hash'] if row else f'pbkdf2_sha256${ITERATIONS}${"00"*16}${"00"*32}'
    valid=password_matches(password,stored)
    if row is None or not valid:
        with connect() as db:
            db.executemany('INSERT INTO app_login_failures VALUES (?,?)',[(k,time.time()) for k in keys])
        raise AppError(401,'Email or password is incorrect.')
    with connect() as db:
        db.execute('DELETE FROM app_login_failures WHERE key=?',(keys[1],))
        token,csrf=new_session(db,row['id'])
    return {'user':public_user(row),'csrf':csrf},cookie_header(token)


def logout(user):
    with connect() as db:
        db.execute('DELETE FROM app_sessions WHERE token_hash=?',(user['session_hash'],))
    return {'user':None,'csrf':''},cookie_header('',True)
