"""Filesystem notes and local SQLite study state (standard library only)."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import threading
import uuid

from .classification import SUBJECTS, apply_classification


MAX_NOTE_BYTES = 2 * 1024 * 1024
MAX_NOTES = 20_000


class StorageError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def tokens(text: str) -> list[str]:
    """English words plus Chinese bigrams; deliberately lexical, not vectors."""
    result = re.findall(r"[a-z0-9_]+", text.lower())
    for part in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend(part[i:i + 2] for i in range(len(part) - 1))
        if len(part) == 1:
            result.append(part)
    return result


def _frontmatter(content: str) -> tuple[dict, str]:
    metadata: dict = {}
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return metadata, content
    end = next((i for i, line in enumerate(lines[1:101], 1) if line.strip() == "---"), None)
    if end is None:
        return metadata, content
    active = None
    for line in lines[1:end]:
        match = re.match(r"^([\w-]+):\s*(.*?)\s*$", line)
        if match:
            active, value = match.groups()
            if active == "tags":
                metadata[active] = [x.strip().strip("'\"") for x in re.split(r"[,，]", value.strip("[]")) if x.strip()]
            else:
                metadata[active] = value.strip("'\"")
        elif active == "tags" and re.match(r"^\s*-\s+", line):
            metadata[active].append(re.sub(r"^\s*-\s+", "", line).strip().strip("'\""))
    return metadata, "\n".join(lines[end + 1:])


def parse_note(path: str, content: str, stat: os.stat_result) -> dict:
    metadata, body = _frontmatter(content)
    heading = re.search(r"^#\s+(.+)$", body, re.M)
    title = str(metadata.get("title") or (heading.group(1).strip() if heading else PurePosixPath(path).stem))
    inline_tags = re.findall(r"(?<![\w#])#([\w\u3400-\u9fff][\w\u3400-\u9fff/-]*)", body)
    tags = sorted(set(metadata.get("tags", []) + inline_tags))[:40]
    parts = PurePosixPath(path).parts
    section = re.match(r"^(00|01|02|03|04|05|90)_", parts[0])
    default_category = {"00": "inbox", "01": "note", "02": "mistake", "03": "plan",
                        "04": "card", "05": "profile", "90": "template"}.get(section.group(1) if section else "")
    category = str(metadata.get("category") or default_category or
                   ("mistake" if "错题" in path or "mistake" in path.lower() else "note"))
    if category in ("错题", "mistakes"):
        category = "mistake"
    subject = str(metadata.get("subject") or (parts[1] if section and len(parts) > 2 and parts[1] in SUBJECTS else ""))
    if subject not in SUBJECTS:
        subject = ""
    preview = re.sub(r"[#>*`\[\]]", "", re.sub(r"\s+", " ", body)).strip()[:180]
    return {"path": path, "title": title, "tags": tags, "preview": preview,
            "modified": iso(datetime.fromtimestamp(stat.st_mtime, timezone.utc)),
            "category": category, "subject": subject, "mtime": str(stat.st_mtime_ns), "content": content}


class StudyStorage:
    def __init__(self, vault: str | Path, data_dir: str | Path):
        self.vault = Path(vault).resolve()
        self.vault.mkdir(parents=True, exist_ok=True)
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "study.sqlite3"
        self._note_lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL,
                    answer TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '', due TEXT NOT NULL,
                    interval REAL NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
                    ease REAL NOT NULL DEFAULT 2.5, reviews INTEGER NOT NULL DEFAULT 0,
                    created TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL,
                    rating TEXT NOT NULL, created TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL,
                    sources TEXT NOT NULL DEFAULT '[]', created TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, result TEXT,
                    error TEXT, created TEXT NOT NULL
                );
            """)
            db.execute("UPDATE jobs SET status='failed', error=? WHERE status IN ('queued','running')",
                       ("服务重启，中断的任务请重新提交。",))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _path(self, relative: str, *, suffix: str = ".md") -> Path:
        if not isinstance(relative, str) or not relative or len(relative) > 500:
            raise StorageError("笔记路径不能为空且不能超过 500 字符。")
        relative = relative.replace("\\", "/")
        parts = PurePosixPath(relative).parts
        if (relative.startswith("/") or any(p in ("..", ".") for p in relative.split("/"))
                or any(c in relative for c in ':\x00<>"|?*') or any(ord(c) < 32 for c in relative)
                or any(not p or p.startswith(".") or p.endswith((" ", ".")) for p in relative.split("/"))
                or any(re.match(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", p, re.I) for p in parts)):
            raise StorageError("笔记路径不合法。")
        target = self.vault.joinpath(*parts)
        if target.suffix.lower() != suffix:
            raise StorageError("笔记须使用 .md 扩展名。")
        cursor = self.vault
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
                raise StorageError("不允许通过符号链接访问笔记。", 403)
        if not target.resolve().is_relative_to(self.vault):
            raise StorageError("路径必须位于笔记仓库中。", 403)
        return target

    def _read(self, target: Path) -> dict:
        stat = target.stat()
        if stat.st_size > MAX_NOTE_BYTES:
            raise StorageError("笔记超过 2 MB，暂不支持读取。", 413)
        try:
            content = target.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            raise StorageError("笔记须使用 UTF-8 编码。") from exc
        return parse_note(target.relative_to(self.vault).as_posix(), content, stat)

    def all_notes(self) -> list[dict]:
        """Scan disk on every request so external Obsidian edits are immediately visible."""
        result = []
        with self._note_lock:
            for folder, dirs, files in os.walk(self.vault, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith(".") and not (Path(folder) / d).is_symlink()
                           and not (hasattr(Path(folder) / d, "is_junction") and (Path(folder) / d).is_junction())]
                for filename in files:
                    if not filename.lower().endswith(".md") or filename.startswith("."):
                        continue
                    relative = (Path(folder) / filename).relative_to(self.vault).as_posix()
                    try:
                        result.append(self._read(self._path(relative)))
                    except (OSError, StorageError):
                        continue
                    if len(result) >= MAX_NOTES:
                        return result
        return sorted(result, key=lambda n: n["modified"], reverse=True)

    @staticmethod
    def summary(note: dict) -> dict:
        return {key: value for key, value in note.items() if key not in ("content", "mtime")}

    def notes(self, query: str = "") -> list[dict]:
        query = query.strip().lower()
        return [self.summary(n) for n in self.all_notes()
                if not query or query in (n["title"] + n["path"] + " ".join(n["tags"]) + n["content"]).lower()]

    def note(self, relative: str) -> dict:
        target = self._path(relative)
        try:
            note = self._read(target)
        except FileNotFoundError as exc:
            raise StorageError("笔记不存在。", 404) from exc
        note["links"] = list(dict.fromkeys(re.findall(r"(?<!!)\[\[([^\]|#]+)(?:[^\]]*)\]\]", note["content"])))
        identifiers = {note["path"].casefold(), str(PurePosixPath(note["path"]).with_suffix("")).casefold(),
                       PurePosixPath(note["path"]).stem.casefold()}
        backlinks = []
        for other in self.all_notes():
            if other["path"] == note["path"]:
                continue
            links = re.findall(r"(?<!!)\[\[([^\]|#]+)(?:[^\]]*)\]\]", other["content"])
            if any(link.strip().casefold() in identifiers for link in links):
                backlinks.append({"path": other["path"], "title": other["title"]})
        note["backlinks"] = backlinks
        return note

    def save_note(self, relative: str, content: str, mtime: str | None = None, classification: dict | None = None) -> dict:
        if not isinstance(content, str):
            raise StorageError("笔记内容必须为文本。")
        if mtime is not None and (not isinstance(mtime, (str, int)) or isinstance(mtime, bool)):
            raise StorageError("笔记版本号不合法。")
        if classification is not None:
            try:
                content = apply_classification(content, classification)
            except ValueError as exc:
                raise StorageError(str(exc)) from exc
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_NOTE_BYTES:
            raise StorageError("笔记内容不能超过 2 MB。", 413)
        with self._note_lock:
            target = self._path(relative)
            exists = target.exists()
            if exists and (mtime is None or str(target.stat().st_mtime_ns) != str(mtime)):
                raise StorageError("笔记已存在或被其他应用修改，请重新打开后再保存。", 409)
            if not exists and mtime is not None:
                raise StorageError("原笔记已被移动或删除，请另存为新笔记。", 409)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._path(relative)
            if not exists:
                try:
                    with target.open("xb") as stream:
                        stream.write(encoded)
                except FileExistsError as exc:
                    raise StorageError("同名笔记已存在，请更换名称。", 409) from exc
            else:
                temporary = target.parent / (".study-" + uuid.uuid4().hex + ".tmp")
                try:
                    temporary.write_bytes(encoded)
                    self._path(relative)
                    if str(target.stat().st_mtime_ns) != str(mtime):
                        raise StorageError("笔记已被其他应用修改，请重新打开后再保存。", 409)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
        return self.note(relative)

    def import_note(self, filename: str, content: str) -> dict:
        if not isinstance(filename, str) or "/" in filename or "\\" in filename:
            raise StorageError("导入文件名不合法。")
        source = PurePosixPath(filename)
        if source.suffix.lower() not in (".md", ".txt"):
            raise StorageError("目前可导入 Markdown 或 TXT 文件。")
        return self.save_note("00_收集箱/" + source.stem + ".md", content)

    def search(self, query: str, limit: int = 12) -> list[dict]:
        query = query.strip()[:500]
        if not query:
            return []
        terms = Counter(tokens(query))
        matches = []
        for note in self.all_notes():
            if note["category"] == "template" or note["path"].startswith("90_模板/"):
                continue
            body = _frontmatter(note["content"])[1]
            title_terms = Counter(tokens(note["title"] + " " + " ".join(note["tags"])))
            for start in range(0, max(len(body), 1), 750):
                excerpt = body[start:start + 900]
                counts = Counter(tokens(excerpt))
                score = sum((1 + math.log(counts[t])) * min(n, 2) for t, n in terms.items() if counts[t])
                score += sum(2.5 * min(title_terms[t], 2) for t in terms if title_terms[t])
                if query.lower() in excerpt.lower():
                    score += 5
                if query.lower() in note["title"].lower():
                    score += 8
                if score:
                    matches.append({"path": note["path"], "title": note["title"], "excerpt": excerpt,
                                    "score": round(score, 3)})
        matches.sort(key=lambda item: item["score"], reverse=True)
        selected = []
        per_note: Counter = Counter()
        for match in matches:
            if per_note[match["path"]] < 2:
                selected.append(match)
                per_note[match["path"]] += 1
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _card(row: sqlite3.Row) -> dict:
        return {key: row[key] for key in ("id", "question", "answer", "source", "topic", "due", "interval", "lapses")}

    def cards(self) -> dict:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM cards ORDER BY due, id").fetchall()
        cards = [self._card(row) for row in rows]
        now = iso(utcnow())
        return {"cards": cards, "due": [card for card in cards if card["due"] <= now]}

    def add_card(self, question: str, answer: str, source: str = "", topic: str = "") -> dict:
        for value, limit, name in ((question, 2000, "问题"), (answer, 12000, "答案"),
                                   (source, 500, "来源"), (topic, 200, "主题")):
            if not isinstance(value, str) or len(value) > limit:
                raise StorageError(f"{name}格式不正确或超过长度限制。")
        if not question.strip() or not answer.strip():
            raise StorageError("卡片问题和答案不能为空。")
        now = iso(utcnow())
        with self.connect() as db:
            cursor = db.execute("INSERT INTO cards(question,answer,source,topic,due,created) VALUES(?,?,?,?,?,?)",
                                (question.strip(), answer.strip(), source.strip(), topic.strip(), now, now))
            row = db.execute("SELECT * FROM cards WHERE id=?", (cursor.lastrowid,)).fetchone()
        return self._card(row)

    def review(self, card_id: int, rating: str) -> dict:
        if rating not in ("again", "hard", "good", "easy"):
            raise StorageError("复习评价须为 again、hard、good 或 easy。")
        if not isinstance(card_id, int) or isinstance(card_id, bool):
            raise StorageError("卡片编号不合法。")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            if row is None:
                raise StorageError("卡片不存在。", 404)
            old = row["interval"]
            ease = row["ease"]
            lapses = row["lapses"]
            if rating == "again":
                interval, ease, lapses = 10 / 1440, max(1.3, ease - .2), lapses + 1
            elif rating == "hard":
                interval, ease = max(1, old * 1.2), max(1.3, ease - .15)
            elif rating == "good":
                interval = 1 if old < 1 else (3 if row["reviews"] <= 1 else old * ease)
            else:
                interval, ease = max(4, old * ease * 1.3), min(3.5, ease + .15)
            interval = min(interval, 3650)
            now = utcnow()
            due = iso(now + timedelta(days=interval))
            db.execute("UPDATE cards SET interval=?,ease=?,lapses=?,due=?,reviews=reviews+1 WHERE id=?",
                       (interval, ease, lapses, due, card_id))
            db.execute("INSERT INTO reviews(card_id,rating,created) VALUES(?,?,?)", (card_id, rating, iso(now)))
            updated = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return self._card(updated)

    def history(self, limit: int = 60) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"role": r["role"], "content": r["content"], "sources": json.loads(r["sources"]),
                 "created": r["created"]} for r in reversed(rows)]

    def add_message(self, role: str, content: str, sources: list | None = None) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO messages(role,content,sources,created) VALUES(?,?,?,?)",
                       (role, content[:50000], json.dumps(sources or [], ensure_ascii=False), iso(utcnow())))
            db.execute("DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT 200)")

    def create_job(self) -> str:
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO jobs(id,status,created) VALUES(?,'queued',?)", (identifier, iso(utcnow())))
            db.execute("DELETE FROM jobs WHERE status IN ('completed','failed') AND id NOT IN (SELECT id FROM jobs ORDER BY created DESC LIMIT 100)")
        return identifier

    def update_job(self, identifier: str, status: str, result: dict | None = None, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?, result=?, error=? WHERE id=?",
                       (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error, identifier))

    def job(self, identifier: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise StorageError("任务不存在。", 404)
        job = {"id": row["id"], "status": row["status"]}
        if row["result"] is not None:
            job["result"] = json.loads(row["result"])
        if row["error"]:
            job["error"] = row["error"]
        return job

    def dashboard(self) -> dict:
        notes = self.all_notes()
        cards = self.cards()
        weak: Counter = Counter()
        for note in notes:
            if note["category"] == "mistake":
                weak.update(note["tags"] or [note["title"]])
        for card in cards["cards"]:
            if card["lapses"]:
                weak[card["topic"] or "未分类"] += card["lapses"]
        with self.connect() as db:
            rows = db.execute("SELECT created FROM reviews").fetchall()
        activity = Counter(str(datetime.fromisoformat(row["created"]).astimezone().date()) for row in rows)
        today = datetime.now().date()
        return {"vault_path": str(self.vault),
                "counts": {"notes": len(notes), "cards": len(cards["cards"]), "due": len(cards["due"]),
                           "mistakes": sum(n["category"] == "mistake" for n in notes)},
                "recent_notes": [self.summary(n) for n in notes[:6]],
                "activity": [{"date": str(today - timedelta(days=i)), "count": activity.get(str(today - timedelta(days=i)), 0)}
                             for i in reversed(range(14))],
                "weak_topics": [{"topic": topic, "count": count} for topic, count in weak.most_common(8)]}
