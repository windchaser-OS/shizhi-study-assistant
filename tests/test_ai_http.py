"""Exercise the connection API and actual HTTP routing with a local fake provider."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from study_app.server import StudyApplication, StudyHTTPServer
from study_app.storage import StudyStorage


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.requests.append((self.path, None))
        self.respond({'data': [{'id': 'model-first'}, {'id': 'model-second'}]})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path, payload))
        self.respond({'choices': [{'message': {'content': self.server.answer}}]})


class AIHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = StudyStorage(root / 'vault', root / 'data')
        self.app = StudyApplication(self.store)
        self.server = StudyHTTPServer(('127.0.0.1', 0), self.app)
        self.provider = ThreadingHTTPServer(('127.0.0.1', 0), ProviderHandler)
        self.provider.requests = []
        self.provider.answer = '# 测试笔记\n资料来自 API。'
        self.workers = []
        for server in (self.server, self.provider):
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            self.workers.append(worker)

    def tearDown(self):
        for server in (self.server, self.provider):
            server.shutdown()
            server.server_close()
        for worker in self.workers:
            worker.join()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request('POST' if data is not None else 'GET', path,
                           json.dumps(data).encode('utf-8') if data is not None else None,
                           {'Content-Type': 'application/json', **(headers or {})})
        response = connection.getresponse()
        status, payload = response.status, json.loads(response.read())
        connection.close()
        return status, payload

    def wait_job(self, identifier):
        for _ in range(100):
            status, job = self.request('/api/jobs?id=' + identifier)
            self.assertEqual(status, 200)
            if job['status'] in ('completed', 'failed'):
                self.assertEqual(job['status'], 'completed', job.get('error'))
                return job['result']
            time.sleep(.01)
        self.fail('AI job did not complete')

    def save_profile(self):
        status, settings = self.request('/api/ai/settings', {
            'action': 'save', 'name': '本地测试服务', 'protocol': 'openai-chat',
            'base_url': f'http://127.0.0.1:{self.provider.server_port}/v1',
            'model': 'model-first', 'api_key': 'test-secret-only',
        })
        self.assertEqual(status, 200, settings)
        self.assertNotIn('test-secret-only', json.dumps(settings))
        return settings['profiles'][0]['id']

    def select_profile(self, identifier):
        status, settings = self.request('/api/ai/settings', {'action': 'select', 'id': identifier})
        self.assertEqual(status, 200, settings)
        self.assertEqual(settings['mode'], 'api')
        return settings

    def test_profiles_persist_without_returning_keys_and_api_status_skips_cli(self):
        identifier = self.save_profile()
        self.select_profile(identifier)
        with patch('study_app.server.codex_bridge.get_status', side_effect=AssertionError('API mode must not probe CLI')):
            status, dashboard = self.request('/api/status')
        self.assertEqual(status, 200)
        self.assertEqual(dashboard['ai']['mode'], 'api')
        self.assertEqual(dashboard['ai']['model'], 'model-first')
        self.assertNotIn('test-secret-only', json.dumps(dashboard))
        settings = self.request('/api/ai/settings')[1]
        self.assertTrue(settings['profiles'][0]['has_api_key'])
        self.assertNotIn('api_key', settings['profiles'][0])
        reopened = StudyApplication(StudyStorage(self.store.vault, self.store.data_dir))
        self.assertEqual(reopened.ai.settings()['active_profile_id'], identifier)
        self.assertEqual(reopened.ai.settings()['mode'], 'api')

    def test_model_list_and_changed_model_reach_provider(self):
        identifier = self.save_profile()
        status, pending = self.request('/api/ai/models', {'id': identifier})
        self.assertEqual(status, 202)
        models = self.wait_job(pending['job_id'])['models']
        self.assertEqual([item['id'] for item in models], ['model-first', 'model-second'])
        profile = self.request('/api/ai/settings')[1]['profiles'][0]
        status, settings = self.request('/api/ai/settings', {**profile, 'action': 'save', 'model': 'model-second', 'api_key': ''})
        self.assertEqual(status, 200, settings)
        self.select_profile(identifier)
        with patch('study_app.server.codex_bridge.generate', side_effect=AssertionError('API mode must not call CLI')):
            status, pending = self.request('/api/chat', {'question': '测试模型选择'})
            self.assertEqual(status, 202)
            answer = self.wait_job(pending['job_id'])
        self.assertIn('API', answer['answer'])
        path, payload = self.provider.requests[-1]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(payload['model'], 'model-second')
        self.assertEqual(len(self.store.history()), 2)

    def test_models_can_be_discovered_before_saving_a_profile_or_choosing_a_model(self):
        status, pending = self.request('/api/ai/models', {
            'protocol': 'openai-chat',
            'base_url': f'http://127.0.0.1:{self.provider.server_port}/v1',
            'api_key': 'unsaved-secret-only',
        })
        self.assertEqual(status, 202, pending)
        result = self.wait_job(pending['job_id'])
        self.assertEqual([item['id'] for item in result['models']], ['model-first', 'model-second'])
        self.assertNotIn('unsaved-secret-only', json.dumps(result))
        self.assertEqual(self.app.ai.settings()['profiles'], [])
        self.assertFalse((self.store.data_dir / 'ai-connections.json').exists())

    def test_all_learning_features_use_selected_api(self):
        identifier = self.save_profile()
        self.select_profile(identifier)
        tiny_png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1EAAAAASUVORK5CYII='
        cases = [
            ('/api/generate', {'kind': 'summary', 'text': '导数资料'}, '# 摘要\n测试', 'text'),
            ('/api/classify-note', {'content': '导数资料'},
             '{"category":"note","subject":"数学","tags":["导数"],"reason":"数学知识"}', 'classification'),
            ('/api/draft-note', {'files': [{'filename': '资料.txt', 'data': base64.b64encode('导数资料'.encode()).decode()}]},
             '---\ncategory: note\nsubject: 数学\ntags: ["导数"]\n---\n# 导数笔记\n测试', 'text'),
            ('/api/transcribe', {'filename': '板书.png', 'data': tiny_png}, '图片转录结果', 'text'),
        ]
        with patch('study_app.server.codex_bridge.generate', side_effect=AssertionError('API mode must not call CLI')):
            for endpoint, data, answer, field in cases:
                with self.subTest(endpoint=endpoint):
                    self.provider.answer = answer
                    status, pending = self.request(endpoint, data)
                    self.assertEqual(status, 202, pending)
                    result = self.wait_job(pending['job_id'])
                    self.assertIn(field, result)
                    self.assertEqual(self.provider.requests[-1][1]['model'], 'model-first')
        self.assertEqual(self.store.notes(), [])
        self.assertEqual(self.store.cards()['cards'], [])
        self.assertFalse(list(self.store.data_dir.glob('note-draft-*')))

    def test_connection_testing_is_explicit_and_uses_saved_profile(self):
        identifier = self.save_profile()
        self.assertEqual(self.provider.requests, [])
        status, pending = self.request('/api/ai/test', {'id': identifier})
        self.assertEqual(status, 202)
        self.assertTrue(self.wait_job(pending['job_id'])['ok'])
        self.assertEqual(self.provider.requests[-1][1]['model'], 'model-first')
        self.assertEqual(self.store.history(), [])
        self.assertEqual(self.app.ai.settings()['mode'], 'codex')

    def test_new_endpoints_enforce_origin_validation_and_unknown_profile_errors(self):
        for endpoint in ('/api/ai/settings', '/api/ai/test', '/api/ai/models'):
            self.assertEqual(self.request(endpoint, {'id': 'unknown'}, {'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/ai/settings', {'action': 'save', 'name': 'bad'})[0], 400)
        self.assertEqual(self.request('/api/ai/test', {'id': 'unknown'})[0], 404)
        self.assertEqual(self.request('/api/ai/models', {'id': []})[0], 400)
        self.assertEqual(self.provider.requests, [])

    def test_configuration_cannot_change_during_jobs_and_codex_switch_works(self):
        identifier = self.save_profile()
        self.select_profile(identifier)
        self.app._ai_lock.acquire()
        try:
            status, failure = self.request('/api/ai/settings', {'action': 'mode', 'mode': 'codex'})
            self.assertEqual(status, 409)
            self.assertIn('任务', failure['error'])
            self.assertEqual(self.app.ai.settings()['mode'], 'api')
        finally:
            self.app._ai_lock.release()
        self.assertEqual(self.request('/api/ai/settings', {'action': 'mode', 'mode': 'codex'})[0], 200)
        with patch('study_app.server.codex_bridge.generate', return_value='Codex 回答'):
            status, pending = self.request('/api/generate', {'kind': 'summary', 'text': '资料'})
            self.assertEqual(status, 202)
            self.assertEqual(self.wait_job(pending['job_id'])['text'], 'Codex 回答')
        self.assertEqual(self.request('/api/ai/settings', {'action': 'delete', 'id': identifier})[0], 200)
        self.assertEqual(self.app.ai.settings()['profiles'], [])


if __name__ == '__main__':
    unittest.main()
