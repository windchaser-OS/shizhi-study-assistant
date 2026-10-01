import base64
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from study_app.server import StudyApplication, StudyHTTPServer
from study_app.storage import StudyStorage


TINY_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1EAAAAASUVORK5CYII='
)


def upload(filename, content):
    return {'filename': filename, 'data': base64.b64encode(content).decode('ascii')}


class NoteDraftTests(unittest.TestCase):
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

    def request(self, path, data=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        connection.request('POST' if data is not None else 'GET', path,
                           json.dumps(data).encode('utf-8') if data is not None else None,
                           {'Content-Type': 'application/json'})
        response = connection.getresponse()
        status, body = response.status, json.loads(response.read())
        connection.close()
        return status, body

    def wait_job(self, identifier):
        for _ in range(150):
            status, job = self.request('/api/jobs?id=' + identifier)
            self.assertEqual(status, 200)
            if job['status'] in ('completed', 'failed'):
                return job
            time.sleep(.01)
        self.fail('note draft job did not complete')

    def text_pdf(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        except ImportError:
            self.skipTest('optional pypdf not installed')
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})
        })
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 20 200 Td (Unique calculus handout) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def test_mixed_materials_and_draft_reach_one_generation_without_saving(self):
        self.store.save_note('已有笔记.md', '# 原有笔记\n不能被草稿生成修改。')
        files = [upload('课件.pdf', self.text_pdf()),
                 upload('课堂记录.txt', '专属课堂标记：导数是瞬时变化率。'.encode('utf-8')),
                 upload('板书一.png', TINY_PNG), upload('板书二.png', TINY_PNG)]
        captured = {}

        def generate(prompt, *, image_paths):
            captured['prompt'] = prompt
            captured['images'] = [Path(path) for path in image_paths]
            self.assertEqual(len(captured['images']), 2)
            for image in captured['images']:
                self.assertTrue(image.is_file())
                self.assertEqual(image.read_bytes(), TINY_PNG)
            return '# 导数学习笔记\n由四份资料整理而成。'

        with patch('study_app.server.codex_bridge.generate', side_effect=generate) as model:
            status, result = self.request('/api/draft-note', {
                'files': files, 'title': '导数学习笔记',
                'instructions': '请突出例题与易错点。',
                'draft': '# 我的草稿\n专属草稿标记：补上几何意义。'
            })
            self.assertEqual(status, 202)
            job = self.wait_job(result['job_id'])
            model.assert_called_once()
        self.assertEqual(job['status'], 'completed')
        self.assertIn('由四份资料整理', job['result']['text'])
        self.assertEqual(job['result']['title'], '导数学习笔记')
        self.assertTrue(any('分类' in warning for warning in job['result']['warnings']))
        for marker in ('Unique calculus handout', '专属课堂标记', '专属草稿标记',
                       '请突出例题与易错点', '导数学习笔记', '课件.pdf', '课堂记录.txt', '板书一.png', '板书二.png'):
            self.assertIn(marker, captured['prompt'])
        self.assertTrue(all(not image.exists() for image in captured['images']))
        self.assertEqual([note['path'] for note in self.store.notes()], ['已有笔记.md'])
        self.assertEqual(self.store.note('已有笔记.md')['content'], '# 原有笔记\n不能被草稿生成修改。')
        self.assertEqual(self.store.cards()['cards'], [])
        self.assertEqual(self.store.history(), [])

    def test_invalid_uploads_are_rejected_before_ai_or_file_creation(self):
        cases = [
            {}, {'files': []}, {'files': [], 'instructions': '请整理笔记'},
            {'files': 'bad'}, {'files': [False]},
            {'files': [upload('run.exe', b'not learning material')]},
            {'files': [{'filename': 'notes.txt', 'data': 'invalid!base64'}]},
            {'files': [upload('notes.txt', b'')]},
            {'files': [upload('board.png', b'fake image')]},
            {'files': [upload('handout.pdf', b'fake pdf')]},
            {'files': [upload('board.webp', b'RIFF1234NOTP')]},
            {'files': [upload('notes.txt', b'notes')], 'instructions': []},
            {'files': [upload('notes.txt', b'notes')], 'draft': {}},
            {'files': [upload('notes.txt', b'notes')], 'title': 42},
        ]
        with patch('study_app.server.codex_bridge.generate') as model:
            for data in cases:
                with self.subTest(data=data):
                    status, result = self.request('/api/draft-note', data)
                    self.assertIn(status, (400, 413))
                    self.assertIn('error', result)
                    self.assertNotIn('job_id', result)
            model.assert_not_called()
        self.assertEqual(self.store.notes(), [])

    def test_existing_draft_can_be_organized_without_uploaded_files(self):
        with patch('study_app.server.codex_bridge.generate', return_value='# 课堂笔记\n整理后的内容。') as model:
            status, result = self.request('/api/draft-note', {
                'files': [], 'draft': '# 原始记录\n纯草稿专属标记：连续并不保证可导。',
                'instructions': '把我的课堂记录整理成概念和易错点。'
            })
            self.assertEqual(status, 202)
            job = self.wait_job(result['job_id'])
        self.assertEqual(job['status'], 'completed')
        self.assertIn('纯草稿专属标记', model.call_args.args[0])
        self.assertIn('把我的课堂记录整理成概念和易错点', model.call_args.args[0])
        self.assertEqual(model.call_args.kwargs['image_paths'], [])
        self.assertEqual(job['result']['text'], '# 课堂笔记\n整理后的内容。')
        self.assertEqual(self.store.notes(), [])

    def test_file_count_text_and_combined_size_limits(self):
        oversized_text = upload('long.txt', b'x' * (2 * 1024 * 1024 + 1))
        large_image = b'\x89PNG\r\n\x1a\n' + b'x' * (6 * 1024 * 1024)
        cases = [
            ([upload(f'{i}.txt', b'note') for i in range(7)], (400, 413)),
            ([oversized_text], (413,)),
            ([upload('one.png', large_image), upload('two.png', large_image)], (413,)),
        ]
        with patch('study_app.server.codex_bridge.generate') as model:
            for files, statuses in cases:
                with self.subTest(filenames=[item['filename'] for item in files]):
                    status, result = self.request('/api/draft-note', {'files': files})
                    self.assertIn(status, statuses)
                    self.assertNotIn('job_id', result)
            model.assert_not_called()
        self.assertEqual(self.store.notes(), [])

    def test_long_materials_warn_and_keep_later_file_context(self):
        files = [upload('长文.md', ('# 长文\n' + '内容abcd' * 10000 + 'UNSENT_END_MARKER').encode('utf-8')),
                 upload('补充.txt', '必须保留的后一份资料：链式法则。'.encode('utf-8'))]
        with patch('study_app.server.codex_bridge.generate', return_value='# 整理后的草稿') as model:
            status, result = self.request('/api/draft-note', {'files': files})
            self.assertEqual(status, 202)
            job = self.wait_job(result['job_id'])
        self.assertEqual(job['status'], 'completed')
        self.assertTrue(job['result']['warnings'])
        prompt = model.call_args.args[0]
        self.assertIn('必须保留的后一份资料', prompt)
        self.assertNotIn('UNSENT_END_MARKER', prompt)
        self.assertLess(len(prompt), 95000)
        self.assertEqual(self.store.notes(), [])

    def test_chinese_legacy_text_encoding_is_read_with_warning(self):
        files = [upload('课堂笔记.txt', '中文课堂专属标记：函数在一点连续。'.encode('gb18030'))]
        with patch('study_app.server.codex_bridge.generate', return_value='# 连续性笔记') as model:
            status, result = self.request('/api/draft-note', {'files': files})
            self.assertEqual(status, 202)
            job = self.wait_job(result['job_id'])
        self.assertEqual(job['status'], 'completed')
        self.assertIn('中文课堂专属标记', model.call_args.args[0])
        self.assertTrue(any('GB18030' in warning for warning in job['result']['warnings']))
        self.assertEqual(self.store.notes(), [])

    def test_pdf_without_extractable_text_requires_image_upload(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('optional pypdf not installed')
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        buffer = io.BytesIO()
        writer.write(buffer)
        with patch('study_app.server.codex_bridge.generate') as model:
            status, result = self.request('/api/draft-note', {
                'files': [upload('扫描课件.pdf', buffer.getvalue())]
            })
            self.assertEqual(status, 400)
            self.assertIn('未提取到文字', result['error'])
            self.assertIn('图片', result['error'])
            self.assertNotIn('job_id', result)
            model.assert_not_called()
        self.assertEqual(self.store.notes(), [])

    def test_generation_failure_cleans_images_and_releases_job_slot(self):
        captured_images = []

        def fail(prompt, *, image_paths):
            captured_images.extend(Path(path) for path in image_paths)
            self.assertTrue(captured_images and all(image.is_file() for image in captured_images))
            raise RuntimeError('模拟图片生成失败')

        with patch('study_app.server.codex_bridge.generate', side_effect=fail):
            status, result = self.request('/api/draft-note', {'files': [upload('board.png', TINY_PNG)]})
            self.assertEqual(status, 202)
            failed = self.wait_job(result['job_id'])
        self.assertEqual(failed['status'], 'failed')
        self.assertIn('模拟图片生成失败', failed['error'])
        self.assertNotIn('result', failed)
        self.assertTrue(all(not image.exists() for image in captured_images))
        with patch('study_app.server.codex_bridge.generate', return_value='# 重试成功'):
            status, retry = self.request('/api/draft-note', {'files': [upload('notes.txt', b'retry notes')]})
            self.assertEqual(status, 202)
            completed = self.wait_job(retry['job_id'])
        self.assertEqual(completed['status'], 'completed')
        self.assertEqual(completed['result']['text'], '# 重试成功')
        self.assertEqual(self.store.notes(), [])


if __name__ == '__main__':
    unittest.main()
