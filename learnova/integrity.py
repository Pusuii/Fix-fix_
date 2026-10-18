"""Pemeriksaan kelengkapan berkas proyek (mis. unggahan GitHub terpotong atau bundel Vercel yang tidak lengkap)."""
import json
import os

from . import paths


def missing_files():
    """Daftar berkas di manifest.json yang tidak ada di disk. Kosong bila lengkap (atau manifest tidak ada)."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "manifest.json"), encoding="utf-8") as fh:
            files = json.load(fh)["files"]
    except (OSError, ValueError, KeyError):
        return []
    return [f for f in files if not os.path.isfile(os.path.join(paths.ROOT, f))]
