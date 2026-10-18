"""Titik masuk Learnova.

Lokal:      python app.py
Reset data: python app.py --reset      (hapus database & unggahan, buat ulang data demo)
Vercel:     variabel `app` di bawah dikenali otomatis (Flask zero-config).

Jika aplikasi gagal start (mis. berkas hilang), `app` berganti menjadi halaman teks berisi penyebabnya,
sehingga Vercel tidak hanya menampilkan "FUNCTION_INVOCATION_FAILED".
"""
import os
import shutil
import sys
import traceback

_import_tb = None
try:
    from learnova import create_app as _create_app, paths
except Exception:  # noqa: BLE001
    _import_tb = traceback.format_exc()


def _fallback_app(tb):
    """Aplikasi minimal yang hanya menampilkan penyebab kegagalan start."""
    from flask import Flask, Response

    fallback = Flask("learnova-startup-error")

    @fallback.route("/", defaults={"path": ""})
    @fallback.route("/<path:path>")
    def _startup_error(path):
        if os.environ.get("LEARNOVA_DEBUG_ERRORS") == "0":
            body = "Learnova gagal start. Lihat Runtime Logs di Vercel untuk rinciannya.\n"
        else:
            body = ("Learnova gagal start.\n"
                    "Kirim teks di bawah ini untuk diperbaiki "
                    "(set LEARNOVA_DEBUG_ERRORS=0 untuk menyembunyikannya).\n\n" + tb)
        return Response(body, status=500, mimetype="text/plain")

    return fallback


def create_app():
    if _import_tb:
        sys.stderr.write("LEARNOVA GAGAL IMPORT\n" + _import_tb)
        if __name__ == "__main__":
            raise SystemExit(_import_tb)
        return _fallback_app(_import_tb)
    try:
        return _create_app()
    except Exception:  # noqa: BLE001 - sengaja menangkap semua agar penyebab terlihat
        tb = traceback.format_exc()
        sys.stderr.write("LEARNOVA GAGAL START\n" + tb)
        if __name__ == "__main__":
            raise
        return _fallback_app(tb)


if "--reset" in sys.argv and not _import_tb:
    inst = paths.instance_path()
    for name in ("learnova.db", "learnova.db-wal", "learnova.db-shm"):
        path = os.path.join(inst, name)
        if os.path.exists(path):
            os.remove(path)
    shutil.rmtree(os.path.join(inst, "uploads"), ignore_errors=True)
    print("Database dan unggahan direset.")

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print("\n  Learnova berjalan di http://%s:%d\n" % (host, port))
    app.run(host=host, port=port, debug=debug)
