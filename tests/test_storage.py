import os
from pathlib import Path
import tempfile
import unittest

from study_app.storage import StorageError, StudyStorage


class StudyStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.storage = StudyStorage(root / "vault", root / "data")

    def tearDown(self):
        self.temp.cleanup()

    def test_create_edit_and_external_conflict(self):
        note = self.storage.save_note("数学/极限.md", "# 极限\n\n函数极限的定义。")
        with self.assertRaises(StorageError) as conflict:
            self.storage.save_note(note["path"], "不允许覆盖")
        self.assertEqual(conflict.exception.status, 409)
        revised = self.storage.save_note(note["path"], "# 极限\n新的定义", note["mtime"])
        path = self.storage.vault / note["path"]
        path.write_text("# 外部编辑\n函数极限", encoding="utf-8")
        os.utime(path, ns=(int(revised["mtime"]) + 10_000_000, int(revised["mtime"]) + 10_000_000))
        with self.assertRaises(StorageError):
            self.storage.save_note(note["path"], "旧版本覆盖", revised["mtime"])
        self.assertEqual(self.storage.notes()[0]["title"], "外部编辑")

    def test_confinement_and_symlinks(self):
        for bad in ("../bad.md", "a/../../bad.md", "C:/bad.md", "/bad.md", "a.md:extra", ".obsidian/test.md", "nul.md", "a/./b.md"):
            with self.subTest(path=bad), self.assertRaises(StorageError):
                self.storage.save_note(bad, "secret")
        external = Path(self.temp.name) / "outside"
        external.mkdir()
        try:
            (self.storage.vault / "linked").symlink_to(external, target_is_directory=True)
        except OSError:
            return
        with self.assertRaises(StorageError):
            self.storage.save_note("linked/escaped.md", "secret")
        self.assertFalse((external / "escaped.md").exists())

    def test_chinese_search_tags_and_backlinks(self):
        self.storage.save_note("微积分.md", "---\ntags:\n  - 数学\n  - 高数\n---\n# 微积分基础\n\n函数极限与导数的关系。")
        self.storage.save_note("错题/复习.md", "# 复习\n检查 [[微积分]] 中的函数极限定义。 #易错")
        note = self.storage.note("微积分.md")
        self.assertEqual(note["tags"], ["数学", "高数"])
        self.assertEqual(note["backlinks"][0]["path"], "错题/复习.md")
        self.assertTrue(self.storage.search("函数极限"))
        self.assertEqual(self.storage.dashboard()["counts"]["mistakes"], 1)
        (self.storage.vault / "外部.md").write_text("# 外部新笔记\n线性代数矩阵", encoding="utf-8")
        self.assertEqual(self.storage.search("线性代数")[0]["path"], "外部.md")

    def test_import_does_not_overwrite(self):
        first = self.storage.import_note("讲义.txt", "第一版")
        with self.assertRaises(StorageError) as conflict:
            self.storage.import_note("讲义.md", "第二版")
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(self.storage.note(first["path"])["content"], "第一版")

    def test_reviews_and_persistence(self):
        card = self.storage.add_card("极限是什么？", "趋近的值", "微积分.md", "极限")
        self.assertEqual(len(self.storage.cards()["due"]), 1)
        again = self.storage.review(card["id"], "again")
        self.assertEqual(again["lapses"], 1)
        self.assertAlmostEqual(again["interval"], 10 / 1440)
        good = self.storage.review(card["id"], "good")
        self.assertEqual(good["interval"], 1)
        easy = self.storage.review(card["id"], "easy")
        self.assertGreaterEqual(easy["interval"], 4)
        reopened = StudyStorage(self.storage.vault, self.storage.data_dir)
        self.assertEqual(reopened.cards()["cards"][0]["lapses"], 1)
        self.assertEqual(sum(x["count"] for x in reopened.dashboard()["activity"]), 3)
        with self.assertRaises(StorageError):
            self.storage.review(card["id"], "invalid")

    def test_jobs_and_history(self):
        self.storage.add_message("user", "测试")
        self.storage.add_message("assistant", "回答", [{"path": "a.md"}])
        self.assertEqual(self.storage.history()[-1]["sources"], [{"path": "a.md"}])
        identifier = self.storage.create_job()
        self.storage.update_job(identifier, "completed", {"text": "完成"})
        self.assertEqual(self.storage.job(identifier)["result"]["text"], "完成")
        interrupted = self.storage.create_job()
        reopened = StudyStorage(self.storage.vault, self.storage.data_dir)
        self.assertEqual(reopened.job(interrupted)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
