"""Storefront and private order desk. No external payment processing."""
from functools import wraps
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from datetime import timedelta
from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from . import store


def create_app(config=None):
    app=Flask(__name__)
    app.config.update(DATABASE=os.environ.get('SHOP_DATABASE','.local/shop.sqlite3'),MAX_CONTENT_LENGTH=128*1024,
                      SESSION_COOKIE_NAME='reserve_cart_session',SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_SECURE=os.environ.get('SHOP_HTTPS')=='1',PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      RESERVATION_SECONDS=1800,CLOCK=lambda:int(time.time()))
    if config:app.config.update(config)
    store.initialize(app.config['DATABASE'])
    if not app.config.get('SECRET_KEY'):
        keypath=Path(app.config['DATABASE']).parent/'session.key'
        try:fd=os.open(keypath,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:app.secret_key=keypath.read_text()
        else:
            with os.fdopen(fd,'w') as f:app.secret_key=secrets.token_hex(32);f.write(app.secret_key)
    attempts={};lock=threading.Lock()
    def now():return app.config['CLOCK']()
    def owner():
        session.setdefault('owner',secrets.token_urlsafe(32));return session['owner']
    def token():
        value=request.headers.get('Authorization','')
        if not value.startswith('Bearer ') or not 30<=len(value[7:])<=100:raise store.Error('A private order link is required',401)
        return value[7:]
    def admin(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not session.get('admin'):raise store.Error('Sign in to the order desk',401)
            db=store.connect(app.config['DATABASE'])
            try:exists=db.execute('SELECT 1 FROM admins WHERE username=?',(session['admin'],)).fetchone()
            finally:db.close()
            if not exists:raise store.Error('Sign in again',401)
            return fn(*args,**kwargs)
        return wrapped
    @app.before_request
    def csrf_check():
        if request.method in ('POST','PATCH','DELETE','PUT'):
            if not request.is_json:raise store.Error('Use application/json',415)
            expected=session.get('csrf','');provided=request.headers.get('X-CSRF-Token','')
            if not expected or not secrets.compare_digest(expected,provided):raise store.Error('Reload the page and try again',403)
            if not isinstance(request.get_json(silent=True),dict):raise store.Error('A JSON object is required')
    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers['Referrer-Policy']='no-referrer';response.headers['X-Content-Type-Options']='nosniff'
        if request.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response
    @app.errorhandler(store.Error)
    def invalid(error):return jsonify(error=str(error)),error.status
    @app.errorhandler(ValueError)
    def bad_value(error):return jsonify(error='Invalid input value'),400
    @app.errorhandler(413)
    def too_large(error):return jsonify(error='Request is too large'),413
    @app.errorhandler(sqlite3.OperationalError)
    def database_busy(error):
        app.logger.error('Database operation failed: %s',error)
        return jsonify(error='The shop is busy. Retry using the same request.'),503
    @app.get('/')
    def home():return render_template('shop.html')
    @app.get('/admin')
    def admin_page():return render_template('admin.html')
    @app.get('/api/session')
    def session_info():
        session.setdefault('csrf',secrets.token_urlsafe(32));owner()
        return jsonify(csrf=session['csrf'],admin=session.get('admin'),reservation_seconds=app.config['RESERVATION_SECONDS'])
    @app.get('/api/products')
    def products():return jsonify(products=store.catalog(app.config['DATABASE'],now()),currency='USD')
    @app.post('/api/checkout')
    def checkout():
        result=store.reserve(app.config['DATABASE'],owner(),request.get_json(),now(),app.config['RESERVATION_SECONDS'])
        return jsonify(result),201
    @app.get('/api/order')
    def order():return jsonify(store.get_order(app.config['DATABASE'],token(),now()))
    @app.post('/api/order/cancel')
    def cancel():
        payload=request.get_json()
        if payload.get('action')!='cancel':raise store.Error('Only cancellation is allowed here',403)
        return jsonify(store.transition(app.config['DATABASE'],payload,'customer',token=token(),now=now()))
    @app.post('/api/admin/login')
    def login():
        payload=request.get_json();username=store.text(payload.get('username'),'username',60);password=payload.get('password')
        if not isinstance(password,str) or len(password)>1000:raise store.Error('Invalid credentials',401)
        ip=request.remote_addr or 'local';stamp=time.monotonic()
        with lock:
            for address in list(attempts):
                attempts[address]=[t for t in attempts[address] if stamp-t<300]
                if not attempts[address]:attempts.pop(address)
            if len(attempts.get(ip,[]))>=5:raise store.Error('Try again in five minutes',429)
        db=store.connect(app.config['DATABASE'])
        try:row=db.execute('SELECT password_hash FROM admins WHERE username=?',(username,)).fetchone()
        finally:db.close()
        if not row or not check_password_hash(row[0],password):
            with lock:attempts.setdefault(ip,[]).append(stamp)
            raise store.Error('Invalid credentials',401)
        with lock:attempts.pop(ip,None)
        previous_owner=owner();session.clear();session.permanent=True;session['owner']=previous_owner;session['admin']=username;session['csrf']=secrets.token_urlsafe(32)
        return jsonify(admin=username,csrf=session['csrf'])
    @app.post('/api/admin/logout')
    def logout():session.clear();return jsonify(ok=True)
    @app.get('/api/admin/state')
    @admin
    def dashboard():return jsonify(store.admin_state(app.config['DATABASE'],now()))
    @app.post('/api/admin/orders/<int:order_id>')
    @admin
    def order_action(order_id):return jsonify(store.transition(app.config['DATABASE'],request.get_json(),session['admin'],order_id=order_id,now=now()))
    @app.post('/api/admin/products')
    @admin
    def product_create():return jsonify(store.save_product(app.config['DATABASE'],request.get_json())),201
    @app.post('/api/admin/products/<int:product_id>')
    @admin
    def product_edit(product_id):return jsonify(store.save_product(app.config['DATABASE'],request.get_json(),product_id))
    @app.post('/api/admin/products/<int:product_id>/stock')
    @admin
    def stock_adjust(product_id):return jsonify(store.adjust_stock(app.config['DATABASE'],product_id,request.get_json()))
    return app


def create_admin(path,password):
    if len(password)<12:raise ValueError('Use a password with at least 12 characters')
    with store.transaction(path) as db:
        if db.execute('SELECT 1 FROM admins').fetchone():raise ValueError('An administrator already exists')
        db.execute('INSERT INTO admins VALUES(?,?)',('admin',generate_password_hash(password)))
