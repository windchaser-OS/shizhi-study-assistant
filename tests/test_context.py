import json
from pathlib import Path
import tempfile
import unittest

from study_app.server import StudyApplication
from study_app.storage import StudyStorage


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = StudyStorage(root / 'vault', root / 'data')
        self.app = StudyApplication(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_plan_excludes_unrelated_recent_content_and_local_paths(self):
        from unittest.mock import patch
        self.store.save_note('unrelated.md', '# Private unrelated note\nSHOULD_NOT_BE_SENT')
        self.app.start_job = lambda operation: operation()
        with patch('study_app.server.codex_bridge.generate', return_value='plan') as generate:
            self.app.generate({'kind': 'plan', 'text': '复习导数，每天半小时'})
        prompt = generate.call_args.args[0]
        self.assertNotIn('SHOULD_NOT_BE_SENT', prompt)
        self.assertNotIn(str(self.store.vault), prompt)
        self.assertNotIn('vault_path', prompt)

    def test_long_generation_is_bounded_and_disclosed(self):
        from unittest.mock import patch
        self.app.start_job = lambda operation: operation()
        with patch('study_app.server.codex_bridge.generate', return_value='summary') as generate:
            result = self.app.generate({'kind': 'summary', 'text': '\\"' * 50000})['job_id']
        self.assertLess(len(generate.call_args.args[0]), 95000)
        self.assertIn('32000', result['warning'])


if __name__ == '__main__':
    unittest.main()
