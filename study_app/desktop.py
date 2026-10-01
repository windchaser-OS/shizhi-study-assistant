"""Desktop lifecycle for the browser-based app; also the frozen executable entry."""
from __future__ import annotations

import argparse
import base64
import hmac
import http.client
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import secrets
import socket
import socketserver
import sys
import tempfile
import threading
import time
import webbrowser

from .runtime import default_data_dir, default_vault, is_frozen, resource_root
from .server import make_server


LOG = logging.getLogger("study.desktop")
APP_NAME = "拾知 · 本地学习助手"


class InstanceLock:
    """OS-owned file lock: released even when the application crashes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.stream = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if not self.path.stat().st_size:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            return False
        self.stream = stream
        return True

    def close(self):
        if self.stream is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
            self.stream = None


def _write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict:
    if path.stat().st_size > 65536:
        raise ValueError("本地设置文件过大。")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("本地设置文件无效。")
    return value


def selected_vault(data_dir: Path, override=None) -> Path:
    if override or os.environ.get("STUDY_VAULT"):
        return Path(override or default_vault()).expanduser().resolve()
    try:
        value = _read_json(data_dir / "desktop-settings.json").get("vault")
    except FileNotFoundError:
        return default_vault()
    except (OSError, ValueError, json.JSONDecodeError):
        LOG.warning("Unable to read desktop settings; using the default vault")
        return default_vault()
    if not isinstance(value, str) or not value or len(value) > 32768:
        return default_vault()
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"之前选择的笔记目录无法访问：\n{path}\n请连接该磁盘，或使用“选择笔记目录”重新选择。")
    return path


def save_vault(data_dir: Path, vault: Path):
    _write_json(data_dir / "desktop-settings.json", {"vault": str(vault.resolve())})


class LocalService:
    def __init__(self, vault: Path, data_dir: Path, port: int = 8765):
        try:
            self.server = make_server(vault=vault, data_dir=data_dir, port=port)
        except OSError as exc:
            # Windows can deny a reserved port as well as report it in use.
            if (not port or (exc.errno not in (13, 48, 98, 10013, 10048)
                             and getattr(exc, "winerror", None) not in (10013, 10048))):
                raise
            LOG.info("Preferred port is unavailable; selecting a free loopback port")
            self.server = make_server(vault=vault, data_dir=data_dir, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .1}, name="study-http", daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class _ControlServer(socketserver.ThreadingTCPServer):
    daemon_threads = True


class _ControlHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        try:
            value = json.loads(self.rfile.readline(2049))
            token = value.get("token", "")
            if (value.get("action") != "open" or not isinstance(token, str) or not token.isascii()
                    or not hmac.compare_digest(token, self.server.token)):
                self.wfile.write(b"DENIED\n")
                return
            self.server.events.put("open")
            self.wfile.write(b"OK\n")
        except (OSError, ValueError, AttributeError):
            return


class InstanceController:
    def __init__(self, data_dir: Path, events: queue.Queue):
        self.path = data_dir / "desktop-instance.json"
        self.server = _ControlServer(("127.0.0.1", 0), _ControlHandler)
        self.server.token = secrets.token_hex(32)
        self.server.events = events
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .1}, name="study-instance", daemon=True)
        self.thread.start()
        try:
            self.publish()
        except BaseException:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            raise

    def publish(self):
        _write_json(self.path, {"port": self.server.server_address[1], "token": self.server.token})

    def close(self):
        try:
            self.path.unlink(missing_ok=True)
        finally:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)


def reopen_instance(data_dir: Path, *, timeout: float = 10) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        try:
            value = _read_json(data_dir / "desktop-instance.json")
            port, token = value.get("port"), value.get("token")
            if not isinstance(port, int) or not 1 <= port <= 65535 or not isinstance(token, str) or len(token) != 64:
                raise ValueError("无效的实例状态。")
            with socket.create_connection(("127.0.0.1", port), timeout=1) as connection:
                connection.sendall(json.dumps({"action": "open", "token": token}).encode() + b"\n")
                if connection.recv(32) == b"OK\n":
                    return True
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(.1)


class DesktopWindow:
    def __init__(self, root, data_dir: Path, vault: Path, port: int, events: queue.Queue,
                 *, startup_error: str = "", no_browser: bool = False):
        import tkinter as tk
        from tkinter import ttk

        self.root, self.data_dir, self.vault, self.port, self.events = root, data_dir, vault, port, events
        self.service = None
        self.no_browser = no_browser
        root.title(APP_NAME)
        icon = resource_root() / "app.ico"
        if icon.is_file():
            try:
                root.iconbitmap(str(icon))
            except tk.TclError:
                LOG.warning("Unable to load the desktop icon")
        root.geometry("610x365")
        root.minsize(560, 350)
        root.configure(background="#f6f5ef")
        root.protocol("WM_DELETE_WINDOW", self.quit)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
        self.status = tk.StringVar(value="正在启动…")
        self.address = tk.StringVar(value="")
        self.vault_text = tk.StringVar(value=str(vault))
        ttk.Label(frame, textvariable=self.status, wraplength=550).pack(anchor="w", pady=(18, 6))
        ttk.Label(frame, textvariable=self.address).pack(anchor="w")
        ttk.Label(frame, text="笔记目录", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(16, 4))
        ttk.Label(frame, textvariable=self.vault_text, wraplength=550).pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w", pady=(20, 14))
        self.open_button = ttk.Button(buttons, text="打开学习空间", command=self.open_browser)
        self.open_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="选择笔记目录", command=self.choose_vault).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="打开数据目录", command=self.open_data).pack(side="left")
        ttk.Label(frame, text="在浏览器中学习。退出此窗口会关闭本机服务。\n首次使用请在“学习设置”中配置 AI 连接。",
                  wraplength=550).pack(anchor="w")
        ttk.Button(frame, text="退出拾知", command=self.quit).pack(anchor="e", pady=(15, 0))
        if startup_error:
            self.status.set("请选择可访问的笔记目录。")
            self.open_button.configure(state="disabled")
            root.after(100, lambda: self.show_error(startup_error))
        else:
            self.start()
        root.after_idle(self.fit_window)
        root.after(100, self.poll)

    def fit_window(self):
        # Existing Obsidian paths can wrap. Keep the exit controls visible.
        self.root.update_idletasks()
        height = max(350, self.root.winfo_reqheight())
        self.root.minsize(560, height)
        if self.root.winfo_height() < height:
            self.root.geometry(f"{max(560, self.root.winfo_width())}x{height}")

    def show_error(self, message: str):
        from tkinter import messagebox
        messagebox.showerror(APP_NAME, message, parent=self.root)

    def start(self):
        try:
            self.service = LocalService(self.vault, self.data_dir, self.port)
        except Exception as exc:
            LOG.exception("Local service startup failed")
            self.status.set("启动失败，请检查笔记目录和数据目录。")
            self.open_button.configure(state="disabled")
            self.show_error(f"无法启动本机服务：\n{exc}\n\n日志目录：{self.data_dir}")
            return
        self.status.set("本机服务已启动" + ("，已自动改用空闲端口。" if self.service.server.server_port != self.port else "。"))
        self.address.set(self.service.url)
        self.open_button.configure(state="normal")
        if not self.no_browser:
            self.root.after(150, self.open_browser)

    def open_browser(self):
        if self.service and not webbrowser.open(self.service.url):
            self.show_error(f"未能自动打开浏览器，请手动访问：\n{self.service.url}")

    def open_data(self):
        if os.name == "nt":
            os.startfile(str(self.data_dir))
        else:
            webbrowser.open(self.data_dir.as_uri())

    def choose_vault(self):
        from tkinter import filedialog, messagebox
        selected = filedialog.askdirectory(title="选择已有笔记目录 / Obsidian 仓库", parent=self.root,
                                            initialdir=str(self.vault if self.vault.is_dir() else Path.home()), mustexist=True)
        if not selected:
            return
        vault = Path(selected).resolve()
        if vault == self.vault and self.service:
            return
        if self.service and not messagebox.askokcancel(APP_NAME, "即将切换笔记目录并重新打开学习空间。\n请先保存浏览器中尚未保存的笔记。", parent=self.root):
            return
        if not self.close_if_idle("切换笔记目录"):
            return
        previous_vault = self.vault
        try:
            save_vault(self.data_dir, vault)
            self.vault = vault
            self.vault_text.set(str(vault))
            self.start()
            self.root.after_idle(self.fit_window)
        except OSError as exc:
            self.vault = previous_vault
            self.show_error(f"无法保存笔记目录设置：\n{exc}")
            self.start()

    def poll(self):
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
            self.root.deiconify()
            self.root.lift()
            self.open_browser()
        self.root.after(100, self.poll)

    def close_if_idle(self, action: str) -> bool:
        if self.service:
            # Acquire atomically, so no request can start a new AI subprocess
            # between the idle check and HTTP shutdown. Keep this retired app's
            # lock held to reject requests already accepted by daemon handlers.
            if not self.service.server.app._ai_lock.acquire(blocking=False):
                from tkinter import messagebox
                messagebox.showinfo(APP_NAME, f"AI 任务正在运行，请等待完成后再{action}。\n响应超时会自动结束本次任务。", parent=self.root)
                return False
            self.service.close()
            self.service = None
        return True

    def quit(self):
        if not self.close_if_idle("退出拾知"):
            return
        self.root.destroy()


def smoke_test() -> dict:
    """Exercise shipped resources, SQLite, HTTP guards and real PDF extraction."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    import tkinter

    # Tcl works without opening a window and catches missing frozen GUI runtime.
    tcl_version = tkinter.Tcl().eval("info patchlevel")
    gui_checks = ["tkinter-tcl"]
    if os.name == "nt":
        # A withdrawn window also loads the actual bundled Tk DLL and themes.
        root = tkinter.Tk()
        try:
            root.withdraw()
            root.update_idletasks()
            root.tk.call("package", "require", "Tk")
        finally:
            root.destroy()
        gui_checks.append("tkinter-tk")

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 200 Td (Shizhi PDF smoke test) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    pdf = io.BytesIO()
    writer.write(pdf)
    with tempfile.TemporaryDirectory(prefix="shizhi-smoke-") as temporary:
        root = Path(temporary)
        service = LocalService(root / "vault", root / "data", port=0)
        checks = gui_checks

        def request(path: str, data=None, headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", service.server.server_port, timeout=5)
            try:
                options = {"Content-Type": "application/json"}
                options.update(headers or {})
                body = json.dumps(data).encode() if data is not None else None
                connection.request("POST" if data is not None else "GET", path, body=body, headers=options)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        def check(name: str, condition: bool):
            if not condition:
                raise RuntimeError("打包验证失败：" + name)
            checks.append(name)

        try:
            for asset in ("/", "/app.js", "/styles.css", "/readability.css", "/favicon.svg",
                          "/vendor/katex/katex.min.js", "/vendor/katex/katex.min.css", "/vendor/katex/contrib/auto-render.min.js",
                          "/vendor/katex/fonts/KaTeX_Main-Regular.woff2"):
                status, content = request(asset)
                check("web:" + asset, status == 200 and bool(content))
            check("loopback-only", service.server.server_address[0] == "127.0.0.1")
            check("host-guard", request("/api/notes", headers={"Host": "external.example"})[0] == 403)
            check("origin-guard", request("/api/cards", {"question": "Q", "answer": "A"}, {"Origin": "https://external.example"})[0] == 403)
            status, result = request("/api/import", {"filename": "smoke.txt", "content": "# Smoke test\nLocal notes"})
            check("note-write", status == 200)
            status, notes = request("/api/notes")
            check("note-read", status == 200 and len(json.loads(notes)["notes"]) == 1)
            status, card = request("/api/cards", {"question": "Q", "answer": "A"})
            check("sqlite-write", status == 200 and json.loads(card)["id"] > 0)
            status, imported = request("/api/import-pdf", {"filename": "smoke.pdf", "data": base64.b64encode(pdf.getvalue()).decode()})
            check("pdf-extraction", status == 200 and "Shizhi PDF smoke test" in json.loads(imported).get("text", ""))
        finally:
            service.close()
    return {"ok": True, "frozen": is_frozen(), "tcl_version": tcl_version, "checks": checks}


def _launch_desktop(args) -> int:
    data_dir = (args.data_dir or default_data_dir()).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["STUDY_DATA_DIR"] = str(data_dir)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(data_dir / "desktop.log", maxBytes=1_000_000,
                                                      backupCount=2, encoding="utf-8")])
    lock = InstanceLock(data_dir / "desktop.lock")
    if not lock.acquire():
        if reopen_instance(data_dir):
            return 0
        _startup_error("拾知已在运行，但暂时没有响应。\n请关闭已有窗口后重新启动。")
        return 1

    controller = None
    window = None
    try:
        startup_error = ""
        try:
            vault = selected_vault(data_dir, args.vault)
        except ValueError as exc:
            vault, startup_error = default_vault(), str(exc)
        import tkinter as tk
        root = tk.Tk()
        events = queue.Queue()
        window = DesktopWindow(root, data_dir, vault, args.port, events,
                               startup_error=startup_error, no_browser=args.no_browser)
        controller = InstanceController(data_dir, events)
        root.mainloop()
        return 0
    finally:
        try:
            if controller:
                controller.close()
            if window and window.service:
                window.service.close()
        finally:
            lock.close()


def _startup_error(message: str):
    from tkinter import Tk, messagebox
    root = Tk()
    root.withdraw()
    try:
        messagebox.showerror(APP_NAME, message, parent=root)
    finally:
        root.destroy()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--smoke-output", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.smoke_test:
        try:
            result = smoke_test()
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "frozen": is_frozen()}
        if args.smoke_output:
            _write_json(args.smoke_output.resolve(), result)
        if sys.stdout:
            print(json.dumps(result, ensure_ascii=True), flush=True)
        return 0 if result["ok"] else 1

    try:
        return _launch_desktop(args)
    except Exception as exc:
        LOG.exception("Desktop startup failed")
        _startup_error(f"无法启动拾知：\n{exc}\n\n请检查数据目录权限后重试。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
