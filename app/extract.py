"""Serbest metin (profil + menü) → doğrulanmış Business ve Menu."""
from __future__ import annotations

import json

from pydantic import ValidationError

from .llm import LocalLLM
from .schema import Business, Menu, Site

BUSINESS_SYSTEM = """Sen bir restoran web sitesi kurulum asistanısın. Sana bir işletmenin
Google Maps / Yemeksepeti profilinden kopyalanmış dağınık bilgiler verilecek.
Bunları aşağıdaki JSON şemasına dönüştür. Sadece JSON döndür, açıklama yazma.

{
  "name": "işletme adı",
  "tagline": "3-5 kelimelik vurucu slogan, büyük başlık olarak kullanılacak. Türkçe. SADECE bu işletmenin metninde geçen ürün/semt/özellik kelimelerini kullan; başka mutfaktan kelime alma, 'efsane' gibi klişe kullanma",
  "description": "2 cümlelik tanıtım (Türkçe, sen üret, abartma)",
  "cuisine": "mutfak türü, örn. burger, kebap, kasap, pide",
  "phone": "telefon",
  "whatsapp": "whatsapp numarası (yoksa telefonla aynı)",
  "address": "adres",
  "maps_url": "harita linki varsa",
  "hours": ["Pzt-Cum 11:00-23:00", ...],
  "delivery_note": "teslimat/paket notu varsa",
  "min_order": sayı veya null,
  "delivery_fee": sayı veya null,
  "platforms": ["Yemeksepeti", "Getir"] gibi geçen platformlar,
  "promo": "metinde kampanya/indirim/duyuru varsa kısa hali, yoksa boş",
  "about": "Hakkımızda paragrafı, 2-3 cümle, SADECE metindeki bilgilerle; yoksa boş",
  "instagram": "instagram linki veya kullanıcı adı varsa",
  "delivery_time": "teslimat süresi geçiyorsa örn. 30-45 dk, yoksa boş",
  "rating": "puan ve yorum sayısı geçiyorsa örn. 4,6 (312 yorum), yoksa boş",
  "theme": {
    "style": "warm | dark | fresh | classic",
    "primary": "#hex ana renk",
    "accent": "#hex vurgu rengi"
  }
}

Tema kuralı: burger/pizza/fast food → dark; kasap/kebap/ızgara → warm;
salata/kahvaltı/kafe → fresh; lokanta/ev yemeği/pide → classic.

ÇOK ÖNEMLİ: description ve tagline'da SADECE metinde geçen bilgileri kullan (konum, ürün, yorum).
Kuruluş yılı, "24 saat", "efsane", köken, ödül gibi metinde olmayan hiçbir şey ekleme.
Bilgi yoksa alanı boş string / boş liste / null bırak."""

MENU_SYSTEM = """Sen bir menü dijitalleştirme asistanısın. Sana dağınık bir menü metni verilecek
(fiyatlar farklı biçimlerde olabilir: 250, 250 TL, 250,00 ₺, 1.250).
Aşağıdaki JSON şemasına dönüştür. Sadece JSON döndür.

{
  "categories": [
    {
      "name": "kategori adı",
      "icon": "kategoriyi temsil eden TEK emoji (🍔 🥩 🍟 🥤 🍰 🥗 🍕 🌯 ☕ 🍗 🍞 gibi)",
      "items": [
        {"name": "ürün adı (gramaj/adet hariç)", "price": 250.0, "old_price": null, "portion": "130 gr / 8 adet / 1 kg gibi varsa, yoksa boş", "description": "varsa kısa açıklama, yoksa boş", "tags": ["acı", "vejetaryen", "yeni", "popüler"] gibi metinde geçenler}
      ]
    }
  ]
}

old_price: metinde üstü çizili / "yerine" / iki fiyat varsa büyük olanı old_price, küçük olanı price yap; tek fiyat varsa null.
Kurallar: fiyatı olmayan ürünü atla ama kategoriyi atlama (bir kategoride fiyatsız bir not satırı
olabilir; kategori yine de fiyatlı ürünleriyle listelenir). Fiyat sayı olsun (TL yazma). Metindeki
büyük harfli, parantezli veya boş satırla ayrılmış başlıklar kategoridir; HEPSİNİ koru, birleştirme.
Kategori sayısı metindeki başlık sayısına eşit olmalı. Kategori hiç yoksa "Menü" adlı tek
kategori kullan. Ürün adını metindeki gibi yaz, kelime ekleme. description alanına SADECE metinde
o ürünün yanında yazan açıklamayı koy; yoksa boş string. tags alanına sadece metinde parantez içinde
veya açıkça geçen etiketi koy; tahmin etme."""


def _words(s: str) -> set[str]:
    return {w for w in "".join(ch if ch.isalnum() else " " for ch in s.lower()).split() if len(w) > 3}


def ground(site_or_menu, source: str):
    """Kaynak metinde dayanağı olmayan serbest metni siler. Küçük modeller açıklama uydurur;
    şema doğrulaması bunu yakalayamaz, bu kontrol yakalar."""
    src = _words(source)
    if isinstance(site_or_menu, Menu):
        for c in site_or_menu.categories:
            for it in c.items:
                if it.description and not (_words(it.description) & src):
                    it.description = ""
                it.tags = [t for t in it.tags if t.lower() in source.lower()]
    elif isinstance(site_or_menu, Business):
        b = site_or_menu
        for field in ("description", "tagline", "about", "promo"):
            val = getattr(b, field)
            if val:
                w = _words(val)
                if w and len(w & src) / len(w) < (0.3 if field == "tagline" else 0.5):
                    setattr(b, field, "")
    return site_or_menu


def extract_business(llm: LocalLLM, profile_text: str) -> Business:
    b = _extract(llm, BUSINESS_SYSTEM, profile_text, Business)
    b.theme.apply_preset()
    b = ground(b, profile_text)
    b.tagline = tighten_tagline(llm, b, profile_text)
    return b


TAGLINE_SYSTEM = """Restoran sitesi için büyük başlık yazıyorsun. Kural: EN FAZLA 5 kelime, Türkçe, nokta yok,
tırnak yok, sadece sloganın kendisi. Sadece verilen metindeki semt/ürün/özellik kelimelerini kullan;
'efsane', 'en iyi', 'eşsiz' gibi klişe ve başka mutfaklara ait kelime (ör. kasap için 'smash') yasak.
Örnek biçim: 'Közde pişen kuzu pirzola' / 'Kadıköy'de smash burger' / 'Taze kesim, anında ızgara'."""


def tighten_tagline(llm: LocalLLM, b: Business, source: str, max_words: int = 5) -> str:
    """Küçük modeller 'kısa yaz' kuralını sık atlar; ayrı ve sert bir çağrıyla kısaltır, yine olmazsa
    kaynağa dayalı güvenli bir başlık üretir."""
    cur = b.tagline.strip()
    if 0 < len(cur.split()) <= max_words:
        return cur
    for _ in range(2):
        prompt = f"İşletme: {b.name}\nMutfak: {b.cuisine}\nMetin:\n{source[:1200]}\n\nUzun hali (kısalt): {cur}"
        out = llm.chat(TAGLINE_SYSTEM, prompt, temperature=0.3, max_tokens=30)
        out = out.strip().strip("\"'.*#").splitlines()[0].strip("*# ").strip()
        banned = ("efsane", "en iyi", "eşsiz", "muhteşem")
        if out and len(out.split()) <= max_words and (_words(out) & _words(source)) and not any(w in out.lower() for w in banned):
            return out
    city = (b.address.split("/")[-1] if "/" in b.address else "").strip()
    return f"{b.cuisine.capitalize() or 'Lezzet'}{' · ' + city if city else ''}"


def extract_menu(llm: LocalLLM, menu_text: str) -> Menu:
    return ground(_extract(llm, MENU_SYSTEM, menu_text, Menu, max_tokens=6000), menu_text)


def extract_site(llm: LocalLLM, profile_text: str, menu_text: str) -> Site:
    return Site(business=extract_business(llm, profile_text), menu=extract_menu(llm, menu_text))


def _extract(llm, system, text, model_cls, max_tokens=4096):
    """Bir deneme; şema hatası olursa hatayı modele gösterip bir kez daha dener."""
    try:
        data = llm.json(system, text, max_tokens=max_tokens)
    except ValueError as e:  # bozuk JSON: bir kez daha, daha sert uyarıyla
        retry = f"{text}\n\n---\nÖnceki cevabın geçerli JSON değildi ({e}). Sadece geçerli, eksiksiz bir JSON nesnesi döndür."
        data = llm.json(system, retry, max_tokens=max_tokens)
    try:
        return model_cls.model_validate(data)
    except ValidationError as e:
        retry = (
            f"{text}\n\n---\nÖnceki cevabın şu hatalarla reddedildi, düzeltip sadece JSON döndür:\n"
            f"{e.errors()[:5]}\nÖnceki cevap:\n{json.dumps(data, ensure_ascii=False)[:2000]}"
        )
        data = llm.json(system, retry, max_tokens=max_tokens)
        return model_cls.model_validate(data)
