import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from study_app import codex_bridge as bridge


class BridgeTests(unittest.TestCase):
    def test_login_output_is_classified_not_exposed(self):
        calls = [subprocess.CompletedProcess([], 0, 'codex-cli test', ''),
                 subprocess.CompletedProcess([], 0, '', 'Logged in using ChatGPT private-diagnostic')]
        with patch.object(bridge, '_status_cache', (0, {})), patch.object(bridge, '_command', return_value=['codex']), patch.object(bridge.subprocess, 'run', side_effect=calls):
            status = bridge.get_status()
            self.assertTrue(status['authenticated'])
            self.assertNotIn('private-diagnostic', str(status))

    def test_prompt_uses_stdin_and_read_only_sandbox(self):
        captured = {}
        class Process:
            returncode = 0
            def __init__(self, command, **kwargs):
                captured['command'] = command
                captured['kwargs'] = kwargs
                self.output = Path(command[command.index('--output-last-message') + 1])
            def communicate(self, data, timeout):
                captured['stdin'] = data
                self.output.write_text('基于笔记的回答。', encoding='utf-8')
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'STUDY_DATA_DIR': temp}), patch.object(bridge, 'get_status', return_value={'authenticated': True}), patch.object(bridge, '_command', return_value=['codex.exe']), patch.object(bridge.subprocess, 'Popen', Process):
            prompt = '解释极限 $(arbitrary-shell-input)'
            self.assertEqual(bridge.generate(prompt), '基于笔记的回答。')
            self.assertNotIn(prompt, captured['command'])
            self.assertIn(prompt.encode(), captured['stdin'])
            self.assertIn('read-only', captured['command'])
            self.assertIn('--ignore-user-config', captured['command'])
            self.assertNotIn('shell', captured['kwargs'])
            self.assertFalse(list((Path(temp) / 'codex-workdir').iterdir()))

    def test_login_required(self):
        with patch.object(bridge, 'get_status', return_value={'authenticated': False}):
            with self.assertRaisesRegex(RuntimeError, 'codex login'):
                bridge.generate('解释导数')

    def test_api_login_is_not_silently_reused(self):
        calls = [subprocess.CompletedProcess([], 0, 'codex-cli test', ''),
                 subprocess.CompletedProcess([], 0, '', 'Logged in using an API key')]
        with patch.object(bridge, '_status_cache', (0, {})), patch.object(bridge, '_command', return_value=['codex']), patch.object(bridge.subprocess, 'run', side_effect=calls):
            self.assertFalse(bridge.get_status()['authenticated'])
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-placeholder', 'CODEX_API_KEY': 'test-placeholder'}):
            self.assertNotIn('OPENAI_API_KEY', bridge._process_environment())
            self.assertNotIn('CODEX_API_KEY', bridge._process_environment())

    def test_empty_prompt_rejected(self):
        with self.assertRaises(ValueError):
            bridge.generate(' ')


if __name__ == '__main__':
    unittest.main()
