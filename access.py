"""Optional session authentication for reverse-proxied shared deployments."""
import hmac
import os
import secrets
from datetime import timedelta

from flask import abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


def install_access(app):
    hashes = {role: os.environ.get(f'NETMON_{role.upper()}_HASH')
              for role in ('admin', 'viewer')}
    enabled = os.environ.get('NETMON_AUTH') == '1' or any(hashes.values())
    if enabled:
        secret = os.environ.get('SECRET_KEY', '')
        if len(secret) < 32 or not all(hashes.values()):
            raise RuntimeError('Shared access requires both password hashes and a random SECRET_KEY of at least 32 characters')
        app.config.update(SECRET_KEY=secret, SESSION_COOKIE_SECURE=True,
                          SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_HTTPONLY=True,
                          PERMANENT_SESSION_LIFETIME=timedelta(hours=8))

    def csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return session['csrf_token']

    @app.context_processor
    def access_context():
        return dict(auth_enabled=enabled, csrf_token=csrf_token,
                    can_manage=not enabled or session.get('role') == 'admin')

    @app.before_request
    def enforce_access():
        if not enabled or request.endpoint == 'static':
            return None
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            expected = session.get('csrf_token')
            supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
                abort(403)
        role = session.get('role')
        if request.endpoint == 'login':
            return None
        if role not in hashes:
            if request.path.startswith('/api/'):
                abort(401)
            return redirect(url_for('login'))
        if role != 'admin' and (request.endpoint in {'add_node', 'edit_node', 'upload_csv'} or
                                (request.method not in ('GET', 'HEAD', 'OPTIONS') and request.endpoint != 'logout')):
            abort(403)
        return None

    @app.after_request
    def prevent_private_caching(response):
        if enabled and request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if not enabled:
            return redirect(url_for('index'))
        if request.method == 'POST':
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            password_hash = hashes.get(username) or hashes['admin']
            if len(password) <= 1024 and check_password_hash(password_hash, password) and username in hashes:
                session.clear()
                session.permanent = True
                session['role'] = username
                return redirect(url_for('index'))
            return render_template('login.html', invalid=True), 401
        return render_template('login.html')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))
