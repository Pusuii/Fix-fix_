"""Uji konfigurasi penyebaran (Vercel: filesystem read-only, hanya /tmp yang bisa ditulis)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from learnova import paths  # noqa: E402


class DeployPathsTest(unittest.TestCase):
    def test_vercel_uses_tmp(self):
        with mock.patch.dict(os.environ, {"VERCEL": "1"}, clear=False):
            os.environ.pop("LEARNOVA_INSTANCE_PATH", None)
            self.assertEqual(paths.instance_path(), os.path.join(tempfile.gettempdir(), "learnova"))

    def test_explicit_instance_path_wins(self):
        with mock.patch.dict(os.environ, {"VERCEL": "1", "LEARNOVA_INSTANCE_PATH": "/data/x"}):
            self.assertEqual(paths.instance_path(), "/data/x")

    def test_local_uses_project_instance(self):
        env = {k: v for k, v in os.environ.items() if k not in ("VERCEL", "LEARNOVA_INSTANCE_PATH")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(paths.instance_path(), os.path.join(paths.ROOT, "instance"))

    def test_static_assets_in_public(self):
        for rel in ("css/app.css", "css/landing.css", "js/app.js", "img/logo-icon.png", "img/favicon.png"):
            self.assertTrue(os.path.isfile(os.path.join(paths.ROOT, "public", "static", rel)), rel)


class TemplateReferenceTest(unittest.TestCase):
    """Semua template yang dirujuk kode/template harus ada, dan tidak ada folder bernama 'public' di templates/
    (Vercel memperlakukan public/ khusus sehingga bisa tidak ikut terbundel)."""

    def test_all_referenced_templates_exist(self):
        import re
        root = paths.ROOT
        tpl_dir = os.path.join(root, "templates")
        refs = set()
        for base, _dirs, files in os.walk(os.path.join(root, "learnova")):
            for f in files:
                if f.endswith(".py"):
                    src = open(os.path.join(base, f), encoding="utf-8").read()
                    refs.update(re.findall(r'render_template\(\s*"([^"]+)"', src))
        for base, _dirs, files in os.walk(tpl_dir):
            for f in files:
                if f.endswith(".html"):
                    src = open(os.path.join(base, f), encoding="utf-8").read()
                    refs.update(re.findall(r'{%-?\s*(?:extends|include|import|from)\s+"([^"]+)"', src))
        self.assertGreater(len(refs), 20)
        missing = sorted(r for r in refs if not os.path.isfile(os.path.join(tpl_dir, r)))
        self.assertEqual(missing, [])

    def test_no_public_dir_inside_templates_or_package(self):
        for top in ("templates", "learnova"):
            for base, dirs, _files in os.walk(os.path.join(paths.ROOT, top)):
                self.assertNotIn("public", dirs, base)


class StartupFailSoftTest(unittest.TestCase):
    def test_startup_failure_shows_traceback_not_crash(self):
        import subprocess
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "import app\n"
            "c = app.app.test_client()\n"
            "r = c.get('/'); print(r.status_code); print(r.get_data(as_text=True))\n"
        ) % paths.ROOT
        env = {**os.environ, "LEARNOVA_INSTANCE_PATH": "/proc/learnova-tidak-bisa-ditulis"}
        out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, timeout=60)
        self.assertTrue(out.stdout.startswith("500"), out.stdout + out.stderr)
        self.assertIn("Learnova gagal start", out.stdout)
        self.assertIn("Traceback", out.stdout)


class IntegrityTest(unittest.TestCase):
    def test_manifest_complete_and_current(self):
        from learnova import integrity
        sys.path.insert(0, os.path.join(paths.ROOT, "tools"))
        import make_manifest
        import json
        with open(os.path.join(paths.ROOT, "learnova", "manifest.json"), encoding="utf-8") as fh:
            listed = set(json.load(fh)["files"])
        self.assertEqual(integrity.missing_files(), [])
        self.assertEqual(sorted(set(make_manifest.collect()) - listed), [],
                         "manifest.json usang: jalankan python tools/make_manifest.py")

    def test_missing_file_is_reported(self):
        from learnova import integrity
        with mock.patch.object(integrity.os.path, "isfile", side_effect=lambda p: not p.endswith("login.html")):
            self.assertIn("templates/site/login.html", integrity.missing_files())


class BootstrapTest(unittest.TestCase):
    def _make(self, tmp, **extra):
        from learnova import create_app
        cfg = {"DATABASE": os.path.join(tmp, "t.db"), "UPLOAD_DIR": os.path.join(tmp, "up"), "TESTING": False}
        cfg.update(extra)
        return create_app(cfg)

    def test_concurrent_start_does_not_crash_or_duplicate(self):
        import sqlite3
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            errors = []

            def start():
                try:
                    self._make(tmp)
                except Exception as exc:  # noqa: BLE001
                    errors.append(repr(exc))
            threads = [threading.Thread(target=start) for _ in range(3)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(errors, [])
            conn = sqlite3.connect(os.path.join(tmp, "t.db"))
            total, distinct = conn.execute("SELECT COUNT(*), COUNT(DISTINCT email) FROM users").fetchone()
            conn.close()
            self.assertGreater(total, 0)
            self.assertEqual(total, distinct)

    def test_interrupted_seed_is_redone(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            self._make(tmp)
            db = os.path.join(tmp, "t.db")
            conn = sqlite3.connect(db)
            conn.execute("DELETE FROM classes")  # simulasi seeding setengah jadi
            conn.commit()
            conn.close()
            open(db + ".seeding", "w").close()  # penanda: proses sebelumnya mati saat seeding
            self._make(tmp)
            conn = sqlite3.connect(db)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0], 0)
            conn.close()
            self.assertFalse(os.path.exists(db + ".seeding"))

    def test_healthz_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make(tmp)
            r = app.test_client().get("/healthz")
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["templates_missing"], [])
            self.assertGreater(data["users"], 0)

    def test_500_shows_short_detail_on_vercel_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make(tmp, SEED_DEMO=False)

            @app.route("/_boom2")
            def boom2():
                raise RuntimeError("kaboom-short")
            c = app.test_client()
            env = {k: v for k, v in os.environ.items() if k not in ("VERCEL", "LEARNOVA_DEBUG_ERRORS")}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertNotIn("kaboom-short", c.get("/_boom2").get_data(as_text=True))
            with mock.patch.dict(os.environ, {**env, "VERCEL": "1"}, clear=True):
                body = c.get("/_boom2").get_data(as_text=True)
                self.assertIn("RuntimeError: kaboom-short", body)
                self.assertNotIn("Traceback", body)

    def test_500_page_hides_traceback_unless_debug(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make(tmp, SEED_DEMO=False)

            @app.route("/_boom")
            def boom():
                raise RuntimeError("kaboom-xyz")
            c = app.test_client()
            r = c.get("/_boom")
            self.assertEqual(r.status_code, 500)
            self.assertNotIn("kaboom-xyz", r.get_data(as_text=True))
            with mock.patch.dict(os.environ, {"LEARNOVA_DEBUG_ERRORS": "1"}):
                r = c.get("/_boom")
            self.assertIn("kaboom-xyz", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
