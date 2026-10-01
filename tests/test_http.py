import base64
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import quote
from unittest.mock import patch

from study_app.server import StudyHTTPServer, StudyApplication
from study_app.storage import StudyStorage


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = StudyStorage(root / 'vault', root / 'data')
        self.server = StudyHTTPServer(('127.0.0.1', 0), StudyApplication(self.store))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        options = {'Content-Type': 'application/json'}
        options.update(headers or {})
        connection.request('POST' if data is not None else 'GET', path,
                           json.dumps(data).encode() if data is not None else None, options)
        response = connection.getresponse()
        body = response.read()
        status = response.status
        content_type = response.getheader('Content-Type') or ''
        connection.close()
        return status, json.loads(body) if 'application/json' in content_type else body

    def wait_job(self, identifier):
        for _ in range(100):
            status, job = self.request('/api/jobs?id=' + identifier)
            self.assertEqual(status, 200)
            if job['status'] in ('completed', 'failed'):
                return job
            time.sleep(.01)
        self.fail('job did not complete')

    def test_notes_conflict_and_path_safety(self):
        status, note = self.request('/api/note', {'path': '知识/导数.md', 'content': '# 导数\n变化率与极限。'})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/note', {'path': note['path'], 'content': '不应覆盖'})[0], 409)
        status, saved = self.request('/api/note', {'path': note['path'], 'content': '# 导数\n更新', 'mtime': note['mtime']})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/note', {'path': note['path'], 'content': '旧版本', 'mtime': note['mtime']})[0], 409)
        self.assertEqual(self.request('/api/note?path=' + quote(note['path']))[1]['content'], '# 导数\n更新')
        self.assertIn(self.request('/api/note', {'path': '../outside.md', 'content': 'bad'})[0], (400, 403))
        self.assertEqual(self.request('/.study-data/study.sqlite3')[0], 404)
        self.assertEqual(self.request('/../README.md')[0], 404)

    def test_origin_host_and_body_guards(self):
        self.assertEqual(self.request('/api/cards', {'question': 'q', 'answer': 'a'}, {'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/status', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/cards', [], {})[0], 400)
        self.assertEqual(self.request('/api/chat', {'question': {'bad': True}})[0], 400)
        self.assertEqual(self.request('/api/cards', {'question': 'q', 'answer': 'a'}, {'Content-Type': 'text/plain'})[0], 415)

    def test_card_review_is_persisted(self):
        status, card = self.request('/api/cards', {'question': '连续一定可导吗？', 'answer': '不一定', 'topic': '可导性'})
        self.assertEqual(status, 200)
        self.assertEqual(len(self.request('/api/cards')[1]['due']), 1)
        status, reviewed = self.request('/api/review', {'id': card['id'], 'rating': 'again'})
        self.assertEqual(status, 200)
        self.assertEqual(reviewed['lapses'], 1)
        self.assertEqual(self.request('/api/cards')[1]['due'], [])
        reopened = StudyStorage(self.store.vault, self.store.data_dir)
        self.assertEqual(reopened.cards()['cards'][0]['lapses'], 1)

    def test_chat_cites_retrieved_notes(self):
        self.store.save_note('导数.md', '# 导数\n导数表示瞬时变化率。')
        with patch('study_app.server.codex_bridge.generate', return_value='导数表示瞬时变化率。[[导数.md]]') as generate:
            status, result = self.request('/api/chat', {'question': '导数是什么？'})
            self.assertEqual(status, 202)
            job = self.wait_job(result['job_id'])
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['result']['sources'][0]['path'], '导数.md')
        self.assertIn('导数表示瞬时变化率', generate.call_args.args[0])
        self.assertEqual(len(self.request('/api/history')[1]['messages']), 2)

    def test_generated_cards_require_explicit_save(self):
        reply = json.dumps({'cards': [{'question': 'q', 'answer': 'a', 'source': '', 'topic': 't'}]})
        with patch('study_app.server.codex_bridge.generate', return_value=reply):
            status, result = self.request('/api/generate', {'kind': 'cards', 'text': '测试资料'})
            job = self.wait_job(result['job_id'])
        self.assertEqual(status, 202)
        self.assertEqual(job['result']['cards'][0]['question'], 'q')
        self.assertEqual(self.request('/api/cards')[1]['cards'], [])

    def test_ai_jobs_are_serialized_across_endpoints(self):
        started = threading.Event()
        release = threading.Event()

        def held_generation(prompt):
            started.set()
            if not release.wait(5):
                raise RuntimeError('test did not release blocked generation')
            return '# 草稿\n测试结果'

        result = None
        with patch('study_app.server.codex_bridge.generate', side_effect=held_generation) as generate:
            try:
                status, result = self.request('/api/generate', {'kind': 'summary', 'text': '学习资料'})
                self.assertEqual(status, 202)
                self.assertTrue(started.wait(2), 'AI job did not start')
                self.assertEqual(self.request('/api/jobs?id=' + result['job_id'])[1]['status'], 'running')
                status, rejected = self.request('/api/chat', {'question': '第二个 AI 任务'})
                self.assertEqual(status, 409)
                self.assertIn('error', rejected)
                self.assertNotIn('job_id', rejected)
                self.assertEqual(self.request('/api/history')[1]['messages'], [])
                self.assertEqual(generate.call_count, 1)
            finally:
                release.set()
                if result and 'job_id' in result:
                    finished = self.wait_job(result['job_id'])
            self.assertEqual(finished['status'], 'completed')
        self.assertEqual(self.store.notes(), [])

    def test_failed_job_releases_slot_without_saving_generated_content(self):
        reply = json.dumps({'cards': [{'question': '检查问题', 'answer': '检查答案', 'topic': '主题', 'source': ''}]})
        with patch('study_app.server.codex_bridge.generate', side_effect=[RuntimeError('模拟临时失败'), reply]) as generate:
            status, result = self.request('/api/generate', {'kind': 'cards', 'text': '第一次生成'})
            self.assertEqual(status, 202)
            failed = self.wait_job(result['job_id'])
            self.assertEqual(failed['status'], 'failed')
            self.assertTrue(failed['error'])
            self.assertNotIn('result', failed)
            self.assertEqual(self.request('/api/cards')[1]['cards'], [])
            self.assertEqual(self.store.notes(), [])

            status, retry = self.request('/api/generate', {'kind': 'cards', 'text': '重试生成'})
            self.assertEqual(status, 202)
            completed = self.wait_job(retry['job_id'])
            self.assertEqual(completed['status'], 'completed')
            self.assertEqual(completed['result']['cards'][0]['question'], '检查问题')
            self.assertEqual(generate.call_count, 2)
        self.assertEqual(self.request('/api/cards')[1]['cards'], [])
        self.assertEqual(self.store.notes(), [])

    def test_chat_uses_explicit_note_even_without_lexical_match(self):
        selected_path = '生物/细胞能量.md'
        selected_text = '# 细胞能量\n专属标记：线粒体通过氧化磷酸化合成 ATP。'
        self.store.save_note(selected_path, selected_text)
        self.store.save_note('解释材料.md', '# 解释材料\n请解释这篇材料，但这篇不是用户选中的笔记。')
        with patch('study_app.server.codex_bridge.generate', return_value='根据所选笔记进行说明。') as generate:
            status, result = self.request('/api/chat', {'question': '请解释这篇材料', 'path': selected_path})
            self.assertEqual(status, 202)
            completed = self.wait_job(result['job_id'])
        self.assertEqual(completed['status'], 'completed')
        sources = completed['result']['sources']
        self.assertIn(selected_path, [source['path'] for source in sources])
        selected_source = next(source for source in sources if source['path'] == selected_path)
        self.assertIn('氧化磷酸化', selected_source['excerpt'])
        self.assertIn('氧化磷酸化', generate.call_args.args[0])
        with patch('study_app.server.codex_bridge.generate') as generate:
            self.assertIn(self.request('/api/chat', {'question': '解释', 'path': '../outside.md'})[0], (400, 403))
            self.assertEqual(self.request('/api/chat', {'question': '解释', 'path': '不存在.md'})[0], 404)
            generate.assert_not_called()

    def test_image_only_pdf_reports_missing_text_without_saving(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DictionaryObject, NameObject, NumberObject, DecodedStreamObject
        except ImportError:
            self.skipTest('optional pypdf not installed')
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        picture = DecodedStreamObject()
        picture.set_data(b'\xff\xff\xff')
        picture.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                        NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/Width'): NumberObject(1),
                        NameObject('/Height'): NumberObject(1), NameObject('/BitsPerComponent'): NumberObject(8)})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Im0'): writer._add_object(picture)})})
        drawing = DecodedStreamObject()
        drawing.set_data(b'q 100 0 0 100 20 100 cm /Im0 Do Q')
        page[NameObject('/Contents')] = writer._add_object(drawing)
        buffer = io.BytesIO()
        writer.write(buffer)
        with patch('study_app.server.codex_bridge.generate') as generate:
            status, result = self.request('/api/import-pdf', {'filename': 'scan.pdf', 'data': base64.b64encode(buffer.getvalue()).decode()})
            self.assertEqual(status, 400)
            self.assertIn('未提取到文字', result['error'])
            generate.assert_not_called()
        self.assertEqual(self.store.notes(), [])

    def test_pdf_text_import_and_image_cleanup(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        except ImportError:
            self.skipTest('optional pypdf not installed')
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 20 200 Td (Derivative study notes) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        buffer = io.BytesIO()
        writer.write(buffer)
        status, result = self.request('/api/import-pdf', {'filename': 'test.pdf', 'data': base64.b64encode(buffer.getvalue()).decode()})
        self.assertEqual(status, 200)
        self.assertIn('Derivative study notes', result['text'])
        self.assertEqual(self.store.notes(), [])
        # Valid tiny PNG; model itself is mocked here, transfer and cleanup are real.
        tiny_png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1EAAAAASUVORK5CYII='
        with patch('study_app.server.codex_bridge.generate', return_value='# 转录') as generate:
            status, result = self.request('/api/transcribe', {'filename': 'note.png', 'data': tiny_png})
            job = self.wait_job(result['job_id'])
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['result']['text'], '# 转录')
        self.assertFalse(Path(generate.call_args.kwargs['image_path']).exists())


if __name__ == '__main__':
    unittest.main()
