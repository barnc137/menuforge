"""Veri modelleri: LLM çıktısı bu şemalara göre doğrulanır."""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ThemeStyle = Literal["warm", "dark", "fresh", "classic"]


class Tolerant(BaseModel):
    """Küçük modeller boş alan için null döndürür; şemayı bozmadan varsayılana çevir."""

    @model_validator(mode="before")
    @classmethod
    def _none_to_default(cls, data):
        if not isinstance(data, dict):
            return data
        out = {}
        for k, v in data.items():
            f = cls.model_fields.get(k)
            if v is None and f is not None and not f.is_required() and f.default is not None:
                v = f.default
            elif v is None and f is not None and f.annotation is str:
                v = ""
            out[k] = v
        return out


_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.translate(_TR))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "isletme"


def normalize_phone(raw: str) -> str:
    """WhatsApp için ülke kodlu, sadece rakam: 905xxxxxxxxx."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0"):
        digits = "90" + digits[1:]
    elif len(digits) == 10:
        digits = "90" + digits
    return digits


PRESETS: dict[str, tuple[str, str]] = {
    "warm": ("#b45309", "#fbbf24"),
    "dark": ("#c2410c", "#fde68a"),
    "fresh": ("#15803d", "#bef264"),
    "classic": ("#7f1d1d", "#d4a373"),
}


class Theme(Tolerant):
    style: ThemeStyle = "warm"
    primary: str = Field("#b45309", description="Ana renk, hex")
    accent: str = Field("#fbbf24", description="Vurgu rengi, hex")
    custom_colors: bool = Field(False, description="Kullanıcı rengi elle seçtiyse True; aksi halde stil paleti kullanılır")

    def apply_preset(self) -> "Theme":
        if not self.custom_colors:
            self.primary, self.accent = PRESETS[self.style]
        return self

    @field_validator("primary", "accent")
    @classmethod
    def _hex(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("hex renk bekleniyor, örn. #b45309")
        return v.lower()


class Business(Tolerant):
    name: str
    tagline: str = ""
    description: str = ""
    cuisine: str = ""
    phone: str = ""
    whatsapp: str = ""
    address: str = ""
    maps_url: str = ""
    hours: list[str] = []
    delivery_note: str = ""
    min_order: float | None = None
    delivery_fee: float | None = None
    platforms: list[str] = []
    payment_methods: list[str] = ["Kapıda Nakit", "Kapıda Kredi Kartı"]
    theme: Theme = Theme()
    promo: str = Field("", description="Kampanya/duyuru metni varsa")
    about: str = Field("", description="Hakkımızda paragrafı; sadece kaynaktaki bilgiyle")
    instagram: str = ""
    hero_image: str = Field("", description="images/ altındaki kapak görseli yolu; boşsa tasarımlı yer tutucu")
    delivery_time: str = Field("", description="Örn. 30-45 dk")
    source_url: str = Field("", description="Verinin alındığı profil adresi (Yemeksepeti/Google)")
    rating: str = Field("", description="Örn. 4,6 (312 yorum)")

    @property
    def slug(self) -> str:
        return slugify(self.name)

    @property
    def whatsapp_digits(self) -> str:
        return normalize_phone(self.whatsapp or self.phone)


class MenuItem(Tolerant):
    name: str
    price: float
    old_price: float | None = Field(None, description="Üstü çizili eski fiyat; indirim varsa")
    portion: str = Field("", description="Gramaj/porsiyon: 130 gr, 1 kg, 8 adet")
    description: str = ""
    tags: list[str] = []
    image: str = Field("", description="images/ altındaki görsel yolu; boşsa kategori ikonu")

    @field_validator("price", "old_price", mode="before")
    @classmethod
    def _price(cls, v):
        if v is None or v == "":
            return 0.0  # fiyatsız ürün Category doğrulayıcısında elenir; old_price 0 = yok
        if isinstance(v, str):
            v = v.replace("TL", "").replace("₺", "").replace(".", "").replace(",", ".").strip()
        return float(v)


class Category(Tolerant):
    name: str
    icon: str = Field("🍽️", description="Kategoriyi temsil eden tek emoji")
    items: list[MenuItem]

    @field_validator("items")
    @classmethod
    def _priced(cls, items: list[MenuItem]) -> list[MenuItem]:
        """Model bazen "her porsiyona dahil" gibi not satırlarını 0 fiyatla ürün yapar; at."""
        return [i for i in items if i.price > 0]


class Menu(BaseModel):
    categories: list[Category]

    @property
    def item_count(self) -> int:
        return sum(len(c.items) for c in self.categories)


class Site(BaseModel):
    business: Business
    menu: Menu
