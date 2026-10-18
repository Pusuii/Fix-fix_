"""Buat ulang learnova/manifest.json (daftar berkas runtime). Jalankan setelah menambah/menghapus berkas:
    python tools/make_manifest.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDE = ("app.py", "requirements.txt", "learnova", "templates", "public")
SKIP_DIRS = {"__pycache__", "instance", ".vercel"}
SKIP_FILES = {"manifest.json"}


def collect():
    out = []
    for item in INCLUDE:
        full = os.path.join(ROOT, item)
        if os.path.isfile(full):
            out.append(item)
            continue
        for base, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f in SKIP_FILES or f.endswith(".pyc"):
                    continue
                out.append(os.path.relpath(os.path.join(base, f), ROOT).replace(os.sep, "/"))
    return sorted(out)


if __name__ == "__main__":
    files = collect()
    with open(os.path.join(ROOT, "learnova", "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"files": files}, fh, indent=1)
    print("manifest.json: %d berkas" % len(files))
