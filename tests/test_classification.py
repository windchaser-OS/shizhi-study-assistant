import http.client
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from study_app.server import StudyApplication, StudyHTTPServer
from study_app.storage import StudyStorage


CLASSIFICATION = {
    'category': 'mistake', 'subject': '数学', 'tags': ['导数', '易错'],
    'reason': '包含求导的错误原因和改正步骤。'
}


class NoteClassificationTests(unittest.TestCase):
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
        self.fail('classification job did not complete')

    def test_existing_note_classification_is_a_preview_and_cannot_move_files(self):
        path = '00_收集箱/课堂错题.md'
        original = '# 课堂错题\n专属错题标记：求导时忘记链式法则。\n参见 [[关联]]。'
        note = self.store.save_note(path, original)
        self.store.save_note('关联.md', '# 关联\n见 [[00_收集箱/课堂错题]]。')
        malicious_folder = {**CLASSIFICATION, 'folder': '../../outside'}
        with patch('study_app.server.codex_bridge.generate', return_value=json.dumps(malicious_folder, ensure_ascii=False)) as model:
            status, response = self.request('/api/classify-note', {'path': path})
            self.assertEqual(status, 202)
            job = self.wait_job(response['job_id'])
            model.assert_called_once()
        self.assertEqual(job['status'], 'completed')
        classification = job['result']['classification']
        self.assertEqual(classification['category'], 'mistake')
        self.assertEqual(classification['subject'], '数学')
        self.assertEqual(classification['tags'], ['导数', '易错'])
        self.assertEqual(classification['folder'], '02_错题本/数学')
        self.assertIn('专属错题标记', model.call_args.args[0])
        self.assertEqual(self.store.note(path)['content'], original)
        self.assertEqual(self.store.note(path)['mtime'], note['mtime'])
        self.assertEqual(self.store.note(path)['backlinks'][0]['path'], '关联.md')
        self.assertEqual(self.store.note(path)['links'], ['关联'])
        self.assertFalse((self.store.vault / '02_错题本').exists())
        self.assertEqual(sorted(n['path'] for n in self.store.notes()), ['00_收集箱/课堂错题.md', '关联.md'])

    def test_unsaved_content_can_be_classified_without_becoming_a_note(self):
        with patch('study_app.server.codex_bridge.generate', return_value=json.dumps({'classification': CLASSIFICATION}, ensure_ascii=False)) as model:
            status, response = self.request('/api/classify-note', {
                'title': '草稿错题', 'content': '# 尚未保存\n专属草稿标记：求导步骤的订正。'
            })
            self.assertEqual(status, 202)
            job = self.wait_job(response['job_id'])
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['result']['classification']['category'], 'mistake')
        self.assertIn('草稿错题', model.call_args.args[0])
        self.assertIn('专属草稿标记', model.call_args.args[0])
        self.assertEqual(self.store.notes(), [])
        self.assertEqual(self.store.history(), [])

    def test_invalid_model_classifications_fail_without_persisting_metadata(self):
        cases = [
            {**CLASSIFICATION, 'category': '../mistake'},
            {**CLASSIFICATION, 'subject': '数学\ncategory: profile'},
            {**CLASSIFICATION, 'tags': ['../secret']},
            {**CLASSIFICATION, 'tags': ['导数\nsubject: 医学']},
            {**CLASSIFICATION, 'tags': [False]},
            {**CLASSIFICATION, 'tags': ['一', '二', '三', '四', '五', '六']},
            {**CLASSIFICATION, 'tags': '导数'},
        ]
        original = '# 导数\n正文必须保留。'
        self.store.save_note('导数.md', original)
        for candidate in cases:
            with self.subTest(candidate=candidate), patch('study_app.server.codex_bridge.generate', return_value=json.dumps(candidate, ensure_ascii=False)):
                status, response = self.request('/api/classify-note', {'path': '导数.md'})
                self.assertEqual(status, 202)
                job = self.wait_job(response['job_id'])
                self.assertEqual(job['status'], 'failed')
                self.assertTrue(job['error'])
                self.assertNotIn('result', job)
                self.assertEqual(self.store.note('导数.md')['content'], original)

    def test_invalid_classification_requests_do_not_start_ai(self):
        cases = [({}, 400), ({'content': []}, 400), ({'title': False, 'content': '内容'}, 400),
                 ({'path': '../escaped.md'}, 400), ({'path': '不存在.md'}, 404)]
        with patch('study_app.server.codex_bridge.generate') as model:
            for data, expected in cases:
                with self.subTest(data=data):
                    status, response = self.request('/api/classify-note', data)
                    self.assertEqual(status, expected)
                    self.assertNotIn('job_id', response)
            model.assert_not_called()

    def test_save_classification_preserves_body_unmanaged_metadata_and_links(self):
        body = '# 导数错题\n\n公式 $f\'(x)$ 与 [[关联]] 必须完整保留。\n'
        original = ('---\ntitle: 原有标题\nauthor: 甲\ncustom:\n  difficulty: high\n'
                    'category: note\ncategory: plan\nsubject: 物理\n'
                    'tags:\n  - 旧标签\ntags: [重复标签]\n---\n' + body)
        note = self.store.save_note('原目录/导数.md', original)
        self.store.save_note('关联.md', '# 关联\n见 [[原目录/导数]]。')
        status, saved = self.request('/api/note', {
            'path': note['path'], 'content': original, 'mtime': note['mtime'],
            'classification': {**CLASSIFICATION, 'folder': '02_错题本/数学'}
        })
        self.assertEqual(status, 200)
        self.assertEqual(saved['path'], '原目录/导数.md')
        self.assertEqual(saved['subject'], '数学')
        self.assertEqual(saved['category'], 'mistake')
        self.assertEqual(saved['tags'], ['导数', '易错'])
        self.assertEqual(saved['title'], '原有标题')
        self.assertIn('author: 甲\ncustom:\n  difficulty: high\n', saved['content'])
        self.assertTrue(saved['content'].endswith(body))
        metadata = saved['content'].split('---', 2)[1]
        for key in ('category', 'subject', 'tags'):
            self.assertEqual(len(re.findall(r'^' + key + r':', metadata, re.M)), 1)
        self.assertNotIn('旧标签', metadata)
        self.assertNotIn('重复标签', metadata)
        self.assertEqual(saved['links'], ['关联'])
        self.assertEqual(saved['backlinks'][0]['path'], '关联.md')
        self.assertFalse((self.store.vault / '02_错题本').exists())
        listed = next(item for item in self.request('/api/notes')[1]['notes'] if item['path'] == note['path'])
        self.assertEqual(listed['subject'], '数学')

    def test_save_rejects_invalid_classification_and_keeps_conflict_guard(self):
        path = '01_知识笔记/导数.md'
        note = self.store.save_note(path, '# 导数\n第一版')
        cases = [False, [], {**CLASSIFICATION, 'category': 'admin'},
                 {**CLASSIFICATION, 'subject': '不支持的学科'},
                 {**CLASSIFICATION, 'tags': ['a/b']}, {**CLASSIFICATION, 'tags': ['x' * 41]}]
        for candidate in cases:
            with self.subTest(candidate=candidate):
                status, response = self.request('/api/note', {
                    'path': path, 'content': '# 不应写入', 'mtime': note['mtime'], 'classification': candidate
                })
                self.assertEqual(status, 400)
                self.assertIn('error', response)
                self.assertEqual(self.store.note(path)['content'], '# 导数\n第一版')
        updated = self.store.save_note(path, '# 导数\n外部新版本', note['mtime'])
        status, _ = self.request('/api/note', {
            'path': path, 'content': '# 过期草稿', 'mtime': note['mtime'], 'classification': CLASSIFICATION
        })
        self.assertEqual(status, 409)
        self.assertEqual(self.store.note(path)['mtime'], updated['mtime'])
        self.assertEqual(self.store.note(path)['content'], '# 导数\n外部新版本')
        status, _ = self.request('/api/note', {
            'path': '02_错题本/数学/导数.md', 'content': '# 改名不应移动',
            'mtime': updated['mtime'], 'classification': CLASSIFICATION
        })
        self.assertEqual(status, 409)
        self.assertFalse((self.store.vault / '02_错题本/数学/导数.md').exists())

    def test_directory_defaults_and_imported_metadata_remain_available(self):
        directories = {'00_收集箱': 'inbox', '01_知识笔记': 'note', '02_错题本': 'mistake',
                       '03_学习计划': 'plan', '04_复习卡片': 'card', '05_学习档案': 'profile', '90_模板': 'template'}
        for folder, category in directories.items():
            with self.subTest(folder=folder):
                note = self.store.save_note(folder + '/示范.md', '# 示例\n正文')
                self.assertEqual(note['category'], category)
                self.assertEqual(note['subject'], '')
        with patch('study_app.server.codex_bridge.generate') as model:
            content = '---\ncategory: note\nsubject: 物理\ntags: [力学]\n---\n# 牛顿定律\n原文'
            status, imported = self.request('/api/import', {'filename': '课件.md', 'content': content})
            self.assertEqual(status, 200)
            self.assertEqual(imported['path'], '00_收集箱/课件.md')
            self.assertEqual(imported['content'], content)
            self.assertEqual(imported['category'], 'note')
            self.assertEqual(imported['subject'], '物理')
            status, plain = self.request('/api/import', {'filename': '待整理.txt', 'content': '课堂原文'})
            self.assertEqual(status, 200)
            self.assertEqual(plain['category'], 'inbox')
            model.assert_not_called()

    def test_draft_generates_text_and_classification_in_one_ai_call(self):
        reply = ('---\ncategory: note\nsubject: 数学\ntags: [导数, 微积分]\n---\n'
                 '# 导数笔记\n\n导数表示瞬时变化率。')
        with patch('study_app.server.codex_bridge.generate', return_value=reply) as model:
            status, response = self.request('/api/draft-note', {
                'files': [], 'draft': '# 课堂记录\n导数表示瞬时变化率。'
            })
            self.assertEqual(status, 202)
            job = self.wait_job(response['job_id'])
            model.assert_called_once()
        self.assertEqual(job['status'], 'completed')
        result = job['result']
        self.assertEqual(result['text'], '# 导数笔记\n\n导数表示瞬时变化率。')
        self.assertEqual(result['title'], '导数笔记')
        self.assertEqual(result['classification']['category'], 'note')
        self.assertEqual(result['classification']['subject'], '数学')
        self.assertEqual(result['classification']['tags'], ['导数', '微积分'])
        self.assertEqual(result['classification']['folder'], '01_知识笔记/数学')
        self.assertEqual(result['warnings'], [])
        self.assertEqual(self.store.notes(), [])

    def test_draft_missing_or_unsafe_classification_keeps_body_and_warns(self):
        for reply in ('# 没有分类\n正文应该可供校对。',
                      '---\ncategory: note\nsubject: 数学\ntags: [../unsafe]\n---\n# 无效分类\n正文保留。'):
            with self.subTest(reply=reply), patch('study_app.server.codex_bridge.generate', return_value=reply):
                status, response = self.request('/api/draft-note', {'files': [], 'draft': '# 原始记录\n学习内容'})
                self.assertEqual(status, 202)
                job = self.wait_job(response['job_id'])
                self.assertEqual(job['status'], 'completed')
                result = job['result']
                self.assertTrue(result['warnings'])
                self.assertIsNone(result.get('classification'))
                self.assertIn('正文', result['text'])
                self.assertEqual(self.store.notes(), [])


if __name__ == '__main__':
    unittest.main()
