"""Foundry Local istemcisi. Model tamamen yerel çalışır; dışarı veri çıkmaz."""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

from openai import OpenAI

DEFAULT_MODEL = os.environ.get("FOUNDRY_MODEL", "ministral-3-3b-instruct-2512")


@dataclass
class LocalLLM:
    client: OpenAI
    model_id: str
    alias: str

    @classmethod
    def connect(cls, alias: str = DEFAULT_MODEL) -> "LocalLLM":
        endpoint, model_id = _resolve(alias)
        client = OpenAI(base_url=endpoint, api_key="local")
        return cls(client=client, model_id=model_id, alias=alias)

    def chat(self, system: str, user: str, *, temperature: float = 0.1, max_tokens: int = 4096) -> str:
        resp = self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def json(self, system: str, user: str, **kw) -> dict:
        """JSON döndürmesi istenen çağrı. Kod bloğu veya açıklama gelirse ayıklar."""
        text = self.chat(system, user, **kw)
        return parse_json(text)


def parse_json(text: str) -> dict:
    """Küçük modeller JSON'u kod bloğuna sarar, yorum satırı ekler, sonda virgül bırakır;
    hepsini toleranslı okur. Başarısız olursa ham metni hatayla birlikte döndürür."""
    raw = text
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON bulunamadı: {text[:200]!r}")
    text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    text = re.sub(r"(?m)//[^\n\"]*$", "", text)            # satır sonu yorumları
    text = re.sub(r",\s*([}\]])", r"\1", text)              # sondaki virgüller
    text = re.sub(r"(?m)^\s*\.\.\.\s*$", "", text)          # "..." yer tutucu satırlar
    text = text.replace("null veya", "null").replace("sayı veya null", "null")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if os.environ.get("LLM_DEBUG"):
            print("---- ham çıktı ----\n" + raw + "\n-------------------")
        raise ValueError(f"JSON çözülemedi ({e.msg} @ {e.pos}): {text[max(0, e.pos-80):e.pos+40]!r}") from e


def _resolve(alias: str) -> tuple[str, str]:
    """Ortam değişkeni varsa onu, yoksa Foundry CLI'yı kullanır (sunucuyu başlatır, modeli yükler)."""
    env = os.environ.get("FOUNDRY_ENDPOINT")
    if env:
        return env.rstrip("/"), os.environ.get("FOUNDRY_MODEL_ID", alias)
    status = _cli_json("server", "status")
    if not status.get("running"):
        subprocess.run(["foundry", "server", "start"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        status = _cli_json("server", "status")
    urls = status.get("webUrls") or []
    if not urls:
        raise RuntimeError("Foundry Local sunucusu bulunamadı. `foundry server start` deneyin.")
    subprocess.run(["foundry", "model", "load", alias], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for m in _cli_json("cache", "list").get("models", []):
        if m.get("alias") == alias:
            return urls[0].rstrip("/") + "/v1", m["id"]
    return urls[0].rstrip("/") + "/v1", alias


def _cli_json(*args: str) -> dict:
    out = subprocess.run(["foundry", *args, "-o", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return parse_json(out.stdout)
    except (ValueError, json.JSONDecodeError):
        return {}
