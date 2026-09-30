"""Menü çıkarım doğruluğu: her örnek için beklenen (ürün, fiyat) çiftleri ile karşılaştırır.

python eval/run_eval.py --model ministral-3-3b-instruct-2512
Beklenen dosya: examples/<ad>/expected.json  → {"items": [["Klasik Smash", 285], ...]}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extract import extract_menu  # noqa: E402
from app.llm import DEFAULT_MODEL, LocalLLM  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def norm(s: str) -> str:
    return " ".join(s.lower().replace("i̇", "i").split())


def score(expected: list, got: list) -> dict:
    exp = {norm(n): float(p) for n, p in expected}
    out = {norm(i.name): i.price for c in got for i in c.items}

    def match(name):  # "Klasik Smash" ↔ "Klasik Smash Burger" gibi ekleri tolere et
        if name in out:
            return name
        cands = [o for o in out if o.startswith(name) or name.startswith(o)]
        return min(cands, key=len) if cands else None

    hits = {n: match(n) for n in exp}
    found = sum(1 for m in hits.values() if m)
    price_ok = sum(1 for n, m in hits.items() if m and abs(out[m] - exp[n]) < 0.01)
    extra = len(set(out) - {m for m in hits.values() if m})
    return {"beklenen": len(exp), "bulunan": found, "fiyat_dogru": price_ok, "fazla": extra,
            "recall": round(found / len(exp), 2), "fiyat_isabet": round(price_ok / max(found, 1), 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()
    llm = LocalLLM.connect(args.model)
    rows = []
    for folder in sorted(EXAMPLES.iterdir()):
        exp_file = folder / "expected.json"
        if not exp_file.exists():
            continue
        expected = json.loads(exp_file.read_text(encoding="utf-8"))["items"]
        text = (folder / "menu.txt").read_text(encoding="utf-8")
        for r in range(args.runs):
            t0 = time.perf_counter()
            try:
                menu = extract_menu(llm, text)
                s = score(expected, menu.categories)
            except Exception as e:  # şema/JSON hatası da bir sonuçtur
                s = {"hata": type(e).__name__}
            s.update(ornek=folder.name, sure_sn=round(time.perf_counter() - t0, 1))
            rows.append(s)
            print(json.dumps(s, ensure_ascii=False))
    ok = [r for r in rows if "recall" in r]
    if ok:
        print(f"\nmodel={args.model} ortalama recall={sum(r['recall'] for r in ok)/len(ok):.2f} "
              f"fiyat_isabet={sum(r['fiyat_isabet'] for r in ok)/len(ok):.2f} "
              f"sure={sum(r['sure_sn'] for r in ok)/len(ok):.1f} sn hata={len(rows)-len(ok)}")
    (Path(__file__).parent / f"sonuc-{args.model}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
