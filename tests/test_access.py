import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from werkzeug.security import generate_password_hash

from access import install_access


class AccessTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        app.testing = True
        env = {'NETMON_AUTH': '1', 'SECRET_KEY': 'a' * 40}
        for role in ('admin', 'viewer'):
            env[f'NETMON_{role.upper()}_HASH'] = generate_password_hash(role + '-password', 'pbkdf2:sha256:1000')
        with patch.dict(os.environ, env, clear=True):
            install_access(app)
        app.add_url_rule('/', 'index', lambda: 'home')
        app.add_url_rule('/api/nodes', 'nodes', lambda: 'nodes')
        app.add_url_rule('/edit/1', 'edit_node', lambda: 'edit')
        app.add_url_rule('/api/logs/clear', 'clear', lambda: 'cleared', methods=['POST'])
        self.client = app.test_client()

    def login(self, role):
        page = self.client.get('/login').get_data(as_text=True)
        token = re.search('name="csrf_token" value="([^"]+)"', page)[1]
        response = self.client.post('/login', data={
            'username': role, 'password': role + '-password', 'csrf_token': token})
        self.assertEqual(response.status_code, 302)

    def csrf_headers(self):
        with self.client.session_transaction() as session:
            session['csrf_token'] = 'test-token'
        return {'X-CSRF-Token': 'test-token'}

    def test_anonymous_cannot_read_private_data(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.get('/api/nodes').status_code, 401)

    def test_viewer_can_read_but_not_edit_or_clear(self):
        self.login('viewer')
        self.assertEqual(self.client.get('/api/nodes').status_code, 200)
        self.assertEqual(self.client.get('/edit/1').status_code, 403)
        self.assertEqual(self.client.post('/api/logs/clear', headers=self.csrf_headers()).status_code, 403)

    def test_admin_mutation_requires_csrf_and_logout_removes_access(self):
        self.login('admin')
        self.assertEqual(self.client.post('/api/logs/clear').status_code, 403)
        headers = self.csrf_headers()
        self.assertEqual(self.client.post('/api/logs/clear', headers=headers).status_code, 200)
        self.assertEqual(self.client.post('/logout', headers=headers).status_code, 302)
        self.assertEqual(self.client.get('/api/nodes').status_code, 401)
