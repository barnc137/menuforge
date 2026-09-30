"""Site (business + menu) → out/<slug>/ çok sayfalı, yayına hazır statik site.
index.html (landing) · menu.html (sipariş) · hakkimizda.html · iletisim.html · site.css · site.js · site.json"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .schema import Site, slugify

TEMPLATES = Path(__file__).parent / "templates"
OUT = Path(__file__).resolve().parent.parent / "out"
PAGES = ["index", "menu", "hakkimizda", "iletisim"]

# Ürün markası: site altbilgisinde "… ile üretildi" olarak görünür.
BRAND = {"name": "Menuforge", "url": "#"}

# Stil paletleri. Hero her stilde koyu (yemek görseli ve büyük başlık için); gövde stile göre.
THEMES = {
    "dark": {
        "bg": "#0d0d0f", "surface": "#18181b", "surface2": "#232327", "text": "#fafafa", "muted": "#a1a1aa",
        "line": "rgba(255,255,255,.08)", "hero": "#09090b", "hero_text": "#ffffff",
        "display": "'Bebas Neue', 'Oswald', Impact, sans-serif", "body": "'Manrope', 'Segoe UI', system-ui, sans-serif",
        "fonts": "family=Bebas+Neue&family=Manrope:wght@400;500;700;800", "upper": True,
    },
    "warm": {
        "bg": "#fbf6ef", "surface": "#ffffff", "surface2": "#f3eadf", "text": "#1c1512", "muted": "#7a6a60",
        "line": "rgba(28,21,18,.08)", "hero": "#1a100b", "hero_text": "#fff7ed",
        "display": "'Bebas Neue', 'Oswald', Impact, sans-serif", "body": "'Manrope', 'Segoe UI', system-ui, sans-serif",
        "fonts": "family=Bebas+Neue&family=Manrope:wght@400;500;700;800", "upper": True,
    },
    "fresh": {
        "bg": "#f6fbf7", "surface": "#ffffff", "surface2": "#e9f5ec", "text": "#0f2e1c", "muted": "#5b7566",
        "line": "rgba(15,46,28,.08)", "hero": "#0b1f14", "hero_text": "#f0fdf4",
        "display": "'Manrope', 'Segoe UI', system-ui, sans-serif", "body": "'Manrope', 'Segoe UI', system-ui, sans-serif",
        "fonts": "family=Manrope:wght@400;500;700;800", "upper": False,
    },
    "classic": {
        "bg": "#f8f4ec", "surface": "#fffdf8", "surface2": "#efe7d8", "text": "#2a211b", "muted": "#7a6e63",
        "line": "rgba(42,33,27,.1)", "hero": "#1c1410", "hero_text": "#fbf3e4",
        "display": "'Playfair Display', Georgia, serif", "body": "'Manrope', 'Segoe UI', system-ui, sans-serif",
        "fonts": "family=Playfair+Display:wght@600;700&family=Manrope:wght@400;500;700;800", "upper": False,
    },
}

PLATFORM_COLORS = {"yemeksepeti": "#fa0050", "getir": "#5d3ebc", "trendyol": "#f27a1a", "migros": "#ff6f00",
                   "google": "#4285f4", "instagram": "#e1306c"}
FEATURED_TAGS = ("popüler", "populer", "imza", "yeni", "çok satan")


def _platform_color(name: str) -> str:
    n = name.lower()
    return next((v for k, v in PLATFORM_COLORS.items() if k in n), "#6b7280")


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters["slug"] = slugify
    env.filters["pcolor"] = _platform_color
    return env


def _context(site: Site) -> dict:
    b, menu = site.business, site.menu
    catalog = {f"{c.name}|{i.name}": {"name": i.name, "price": i.price} for c in menu.categories for i in c.items}
    # Öne çıkanlar: etiketli ürünler, yoksa görselli olanlar, yoksa her kategoriden ilk ürün.
    feat = [(c, i) for c in menu.categories for i in c.items if any(t.lower().startswith(FEATURED_TAGS) for t in i.tags)]
    if len(feat) < 4:
        feat += [(c, i) for c in menu.categories for i in c.items if i.image and (c, i) not in feat]
    if len(feat) < 4:
        feat += [(c, c.items[0]) for c in menu.categories if c.items and (c, c.items[0]) not in feat]
    featured = [{"key": f"{c.name}|{i.name}", "item": i, "icon": c.icon} for c, i in feat[:8]]
    icons = [c.icon for c in menu.categories] or ["🍽️"]
    pattern = (f"<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
               f"<text x='10' y='60' font-size='44'>{icons[0]}</text>"
               f"<text x='100' y='150' font-size='44'>{icons[1] if len(icons) > 1 else '🥤'}</text></svg>")
    return dict(b=b, menu=menu, palette=THEMES[b.theme.style], wa=b.whatsapp_digits, brand=BRAND,
                item_count=menu.item_count, catalog=catalog, featured=featured, pattern_svg=pattern,
                schema_json=json.dumps(_schema_org(site), ensure_ascii=False))


def render(site: Site, page: str = "index") -> str:
    return _env().get_template(f"{page}.html.j2").render(**_context(site))


def _schema_org(site: Site) -> dict:
    b = site.business
    data = {
        "@context": "https://schema.org", "@type": "Restaurant", "name": b.name,
        "servesCuisine": b.cuisine, "telephone": b.phone, "address": b.address, "priceRange": "₺₺",
        "hasMenu": {"@type": "Menu", "hasMenuSection": [
            {"@type": "MenuSection", "name": c.name, "hasMenuItem": [
                {"@type": "MenuItem", "name": i.name, "description": i.description,
                 "offers": {"@type": "Offer", "price": i.price, "priceCurrency": "TRY"}} for i in c.items]}
            for c in site.menu.categories]},
    }
    if b.hours:
        data["openingHours"] = b.hours
    if b.source_url:
        data["sameAs"] = [b.source_url]
    return data


def build(site: Site, out_dir: Path | None = None, images_from: Path | None = None) -> Path:
    """Siteyi yazar. images_from verilirse görseller out/<slug>/images/ altına kopyalanır ve dosya adı
    ürün adıyla eşleşenler karta bağlanır; hero.jpg/png kapak olur. Dönüş: index.html yolu."""
    out_dir = out_dir or OUT / site.business.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    if images_from and images_from.exists():
        attach_images(site, images_from, out_dir)
    env, ctx = _env(), _context(site)
    for page in PAGES:
        (out_dir / f"{page}.html").write_text(env.get_template(f"{page}.html.j2").render(**ctx), encoding="utf-8")
    for asset in ("site.css", "site.js"):
        shutil.copy(TEMPLATES / asset, out_dir / asset)
    (out_dir / "site.json").write_text(site.model_dump_json(indent=2), encoding="utf-8")
    return out_dir / "index.html"


def attach_images(site: Site, images_from: Path, out_dir: Path) -> int:
    """Dosya adı → ürün eşlemesi. Tam slug eşleşmesi öncelikli; sonra içerme. Uzak (http) görseller korunur."""
    img_dir = out_dir / "images"
    img_dir.mkdir(exist_ok=True)
    files = {slugify(p.stem): p for p in images_from.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}
    matched = 0
    for k in ("hero", "kapak", "cover"):
        if k in files:
            shutil.copy(files[k], img_dir / files[k].name)
            site.business.hero_image = f"images/{files[k].name}"
            files.pop(k)
            break
    for c in site.menu.categories:
        for it in c.items:
            if it.image.startswith("http"):
                continue
            key = slugify(it.name)
            hit = files.get(key) or next((p for k, p in files.items() if len(k) > 3 and (k in key or key in k)), None)
            if hit:
                shutil.copy(hit, img_dir / hit.name)
                it.image = f"images/{hit.name}"
                matched += 1
    return matched
