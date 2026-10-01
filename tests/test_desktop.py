import http.client
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from study_app.desktop import (DesktopWindow, InstanceController, InstanceLock, LocalService, main,
                               reopen_instance, save_vault, selected_vault, smoke_test)


class DesktopTests(unittest.TestCase):
    def test_lock_prevents_another_process_then_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "desktop.lock"
            owner = InstanceLock(path)
            self.assertTrue(owner.acquire())
            code = ("from pathlib import Path; import sys; from study_app.desktop import InstanceLock; "
                    "lock = InstanceLock(Path(sys.argv[1])); "
                    "sys.exit(0 if lock.acquire() else 7)")
            try:
                result = subprocess.run([sys.executable, "-c", code, str(path)], timeout=10, capture_output=True)
                self.assertEqual(result.returncode, 7, result.stderr.decode(errors="replace"))
            finally:
                owner.close()
            result = subprocess.run([sys.executable, "-c", code, str(path)], timeout=10, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_instance_reopen_uses_authenticated_lightweight_channel(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = queue.Queue()
            controller = InstanceController(root, events)
            try:
                with socket.create_connection(controller.server.server_address, timeout=2) as connection:
                    connection.sendall(b'{"action":"open","token":"wrong"}\n')
                    self.assertEqual(connection.recv(32), b"DENIED\n")
                self.assertTrue(events.empty())
                self.assertTrue(reopen_instance(root, timeout=1))
                self.assertEqual(events.get(timeout=2), "open")
            finally:
                controller.close()
            self.assertFalse((root / "desktop-instance.json").exists())
            self.assertFalse(reopen_instance(root, timeout=0))

    def test_occupied_port_falls_back_to_loopback_and_closes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            occupied = socket.socket()
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            port = occupied.getsockname()[1]
            try:
                service = LocalService(root / "vault", root / "data", port)
                actual_port = service.server.server_port
                try:
                    self.assertNotEqual(actual_port, port)
                    self.assertEqual(service.server.server_address[0], "127.0.0.1")
                    connection = http.client.HTTPConnection("127.0.0.1", actual_port, timeout=5)
                    connection.request("GET", "/api/notes")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read())["notes"], [])
                    connection.close()
                finally:
                    service.close()
                with self.assertRaises(OSError):
                    socket.create_connection(("127.0.0.1", actual_port), timeout=.1)
            finally:
                occupied.close()

    def test_vault_selection_is_saved_and_missing_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            root = Path(temporary)
            vault = root / "my-existing-vault"
            vault.mkdir()
            save_vault(root / "data", vault)
            self.assertEqual(selected_vault(root / "data"), vault)
            vault.rmdir()
            with self.assertRaisesRegex(ValueError, "之前选择的笔记目录无法访问"):
                selected_vault(root / "data")
            self.assertEqual(selected_vault(root / "data", root / "override"), root / "override")

    def test_smoke_uses_only_temporary_user_data_and_extracts_real_pdf(self):
        with tempfile.TemporaryDirectory() as temporary:
            sentinel = Path(temporary) / "uncreated-personal-data"
            with patch.dict(os.environ, {"STUDY_DATA_DIR": str(sentinel), "STUDY_VAULT": str(sentinel)}):
                result = smoke_test()
            self.assertTrue(result["ok"])
            self.assertIn("pdf-extraction", result["checks"])
            self.assertIn("sqlite-write", result["checks"])
            self.assertIn("origin-guard", result["checks"])
            self.assertFalse(sentinel.exists())

    def test_unwritable_data_path_produces_readable_startup_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "a-file"
            path.write_text("not a directory", encoding="utf-8")
            with patch("study_app.desktop._startup_error") as show_error, self.assertLogs("study.desktop", level="ERROR"):
                self.assertEqual(main(["--data-dir", str(path)]), 1)
            self.assertIn("无法启动拾知", show_error.call_args.args[0])

    def test_exit_waits_for_ai_and_prevents_new_jobs_during_shutdown(self):
        window = DesktopWindow.__new__(DesktopWindow)
        window.root = Mock()
        app_lock = threading.Lock()
        service = Mock()
        service.server.app = SimpleNamespace(_ai_lock=app_lock)
        window.service = service
        app_lock.acquire()
        with patch("tkinter.messagebox.showinfo") as show_info:
            window.quit()
        service.close.assert_not_called()
        window.root.destroy.assert_not_called()
        self.assertIn("请等待完成后再退出", show_info.call_args.args[1])
        app_lock.release()

        def shutdown():
            self.assertFalse(app_lock.acquire(blocking=False), "new AI work must be rejected while stopping")

        service.close.side_effect = shutdown
        window.quit()
        service.close.assert_called_once()
        window.root.destroy.assert_called_once()
        self.assertIsNone(window.service)


if __name__ == "__main__":
    unittest.main()
