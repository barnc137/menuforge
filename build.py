"""Komut satırı: python build.py examples/burger [--model alias]"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from app.extract import extract_site
from app.generate import build
from app.llm import DEFAULT_MODEL, LocalLLM


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="profil.txt ve menu.txt içeren klasör")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    folder = Path(args.folder)
    profile = (folder / "profil.txt").read_text(encoding="utf-8")
    menu = (folder / "menu.txt").read_text(encoding="utf-8")

    t0 = time.perf_counter()
    llm = LocalLLM.connect(args.model)
    print(f"model: {llm.model_id} @ {llm.client.base_url}")

    site = extract_site(llm, profile, menu)
    t1 = time.perf_counter()
    out = build(site)
    print(f"işletme: {site.business.name} | tema: {site.business.theme.style} "
          f"| {len(site.menu.categories)} kategori, {site.menu.item_count} ürün | {t1 - t0:.1f} sn")
    print(f"site: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
