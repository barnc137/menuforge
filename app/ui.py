"""Sihirbaz arayüzü: 3 adımda profil + menü (+ fotoğraf) → yayına hazır çok sayfalı site.
Çalıştır: streamlit run app/ui.py"""
from __future__ import annotations

import base64
import io
import mimetypes
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extract import extract_business, extract_menu  # noqa: E402
from app.generate import BRAND, OUT, build  # noqa: E402
from app.llm import LocalLLM  # noqa: E402
from app.schema import Business, Category, Menu, MenuItem, Site  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
MODELS = {
    "ministral 3B — hızlı, sıradan laptopta çalışır": "ministral-3-3b-instruct-2512",
    "mistral 7B — karşılaştırma": "mistral-7b-v0.2",
}
STYLES = {"dark": "Koyu · burger, pizza, fast food", "warm": "Sıcak · kasap, kebap, ızgara",
          "fresh": "Taze · kafe, kahvaltı, salata", "classic": "Klasik · lokanta, ev yemeği, pide"}
PAGES = [("index", "Ana sayfa"), ("menu", "Menü"), ("hakkimizda", "Hakkımızda"), ("iletisim", "İletişim")]


def inline_page(folder: Path, page: str) -> str:
    """Önizleme için sayfayı tek belgeye çevirir: css/js gömülür, görseller base64, sayfa linkleri kapatılır."""
    html = (folder / f"{page}.html").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="site.css">', "<style>" + (folder / "site.css").read_text(encoding="utf-8") + "</style>")
    html = html.replace('<script src="site.js"></script>', "<script>" + (folder / "site.js").read_text(encoding="utf-8") + "</script>")

    def b64(m: re.Match) -> str:
        p = folder / "images" / m.group(1)
        if not p.exists():
            return m.group(0)
        mt = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        return m.group(0).replace("images/" + m.group(1), f"data:{mt};base64," + base64.b64encode(p.read_bytes()).decode())

    html = re.sub(r"images/([^'\")]+)", b64, html)
    return re.sub(r'href="(index|menu|hakkimizda|iletisim)\.html(#[^"]*)?"', 'href="#" onclick="return false"', html)


def load_example(name: str) -> None:
    st.session_state["ex_profile"] = (EXAMPLES / name / "profil.txt").read_text(encoding="utf-8")
    st.session_state["ex_menu"] = (EXAMPLES / name / "menu.txt").read_text(encoding="utf-8")


st.set_page_config(page_title=f"{BRAND['name']} — Sipariş Sitesi Üreteci", page_icon="🍽️", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""
<style>
#MainMenu,footer,header[data-testid="stHeader"]{visibility:hidden;height:0}
.block-container{padding-top:1.2rem;padding-bottom:3rem;max-width:1140px}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.brand .m{width:40px;height:40px;border-radius:12px;background:#f26b1d;color:#fff;display:grid;place-items:center;font-weight:900;font-size:20px}
.brand h1{font-size:26px;margin:0;line-height:1.1}
.brand small{color:#888;font-size:13px}
.steps{display:flex;gap:8px;margin:14px 0 22px}
.steps div{flex:1;padding:10px 14px;border-radius:12px;background:rgba(127,127,127,.12);font-size:13px;font-weight:600;color:#888;border:1px solid transparent}
.steps div.on{background:rgba(242,107,29,.14);color:#f26b1d;border-color:rgba(242,107,29,.4)}
.steps div.done{color:#22c55e}
.hint{font-size:13px;color:#888;margin-top:-6px}
div[data-testid="stExpander"] summary{font-weight:600}
</style>""", unsafe_allow_html=True)

step = st.session_state.setdefault("step", 1)

st.markdown(f"""<div class="brand"><div class="m">{BRAND['name'][:1]}</div>
  <div><h1>{BRAND['name']}</h1><small>Yemeksepeti / Google profilini yapıştır → 2 dakikada komisyonsuz sipariş siten. Her şey bu bilgisayarda çalışır.</small></div></div>""",
            unsafe_allow_html=True)
_names = ["1 · İşletme", "2 · Menü & görünüm", "3 · Kontrol et & yayınla"]
st.markdown('<div class="steps">' + "".join(
    f'<div class="{"done" if i + 1 < step else "on" if i + 1 == step else ""}">{"✓ " if i + 1 < step else ""}{n}</div>'
    for i, n in enumerate(_names)) + "</div>", unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Ayarlar")
    alias = MODELS[st.radio("Yerel model", list(MODELS))]
    st.caption("Foundry Local üzerinde çalışır; internet gerekmez, veri dışarı çıkmaz.")

# ------------------------------------------------------------------ 1
if step == 1:
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.subheader("İşletme bilgin")
        st.markdown('<p class="hint">Google Maps veya Yemeksepeti sayfandaki metni olduğu gibi kopyala-yapıştır: ad, adres, telefon, saatler, yorumlar… Düzenleme yapma, model ayıklar.</p>', unsafe_allow_html=True)
        profile = st.text_area("Profil metni", value=st.session_state.get("ex_profile", ""), height=300, label_visibility="collapsed",
                               placeholder="Köşe Burger\n4,6 ★ (312 yorum) · Hamburger restoranı\nAdres: …\nTelefon: …\nAçık · Kapanış 23:30 …")
        exs = sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir())
        cols = st.columns(len(exs) + 1)
        cols[0].markdown('<p class="hint" style="padding-top:8px">Örnekle dene:</p>', unsafe_allow_html=True)
        for i, name in enumerate(exs):
            if cols[i + 1].button(f"🍽️ {name}", key=f"ex_{name}", use_container_width=True):
                load_example(name)
                st.rerun()
        if st.button("Devam →", type="primary", disabled=not profile.strip(), use_container_width=True):
            with st.spinner("Yerel model işletme bilgisini ayıklıyor…"):
                llm = LocalLLM.connect(alias)
                st.session_state["business"] = extract_business(llm, profile)
            st.session_state["step"] = 2
            st.rerun()
    with c2:
        st.subheader("Ne olacak?")
        st.markdown("""
- **Ayıklama:** ad, adres, saat, WhatsApp, kampanya, sipariş kanalları
- **Tasarım:** mutfak türüne göre tema ve renk paleti
- **Metin:** slogan ve hakkımızda — sadece senin verdiğin bilgiyle, uydurma yok
- **Sipariş:** sepet → WhatsApp'a hazır mesaj; ödeme kapıda
- **Çıktı:** 4 sayfalık site (ana sayfa, menü, hakkımızda, iletişim), istediğin yerde yayınla
""")
        st.info("Sipariş platformlarında komisyon %18-30. Kendi siten için komisyon yok; sadece kurye.", icon="💡")

# ------------------------------------------------------------------ 2
elif step == 2:
    b: Business = st.session_state["business"]
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.subheader("Menünü yapıştır")
        st.markdown('<p class="hint">Kategori başlıkları, ürünler, fiyatlar — biçim önemli değil. "250", "250 TL", "1.250,00 ₺" hepsi olur. İndirimliyse iki fiyatı da yaz.</p>', unsafe_allow_html=True)
        menu_text = st.text_area("Menü metni", value=st.session_state.get("ex_menu", ""), height=330, label_visibility="collapsed",
                                 placeholder="BURGERLER\nKlasik Smash 100 gr dana, cheddar 285\n…")
        st.subheader("Fotoğraflar (isteğe bağlı)")
        st.markdown('<p class="hint">Dosya adı ürün adıyla eşleşenler otomatik bağlanır (örn. <code>klasik-smash.jpg</code>); eşleşmeyenleri son adımda elle seçersin. <code>hero.jpg</code> kapak olur.</p>', unsafe_allow_html=True)
        photos = st.file_uploader("Fotoğraflar", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, label_visibility="collapsed")
    with c2:
        st.subheader("Kontrol et")
        b.name = st.text_input("İşletme adı", b.name)
        b.tagline = st.text_input("Slogan (büyük başlık, 3-5 kelime)", b.tagline)
        b.whatsapp = st.text_input("WhatsApp numarası", b.whatsapp or b.phone)
        b.phone = st.text_input("Telefon", b.phone)
        b.address = st.text_input("Adres", b.address)
        b.promo = st.text_input("Kampanya (boş bırakılabilir)", b.promo, placeholder="Online siparişe %10 indirim")
        style_keys = list(STYLES)
        new_style = st.selectbox("Tema", style_keys, index=style_keys.index(b.theme.style), format_func=lambda k: STYLES[k])
        if new_style != b.theme.style:
            b.theme.style, b.theme.custom_colors = new_style, False
            b.theme.apply_preset()
        cc1, cc2 = st.columns(2)
        p = cc1.color_picker("Ana renk", b.theme.primary)
        a = cc2.color_picker("Vurgu", b.theme.accent)
        if (p, a) != (b.theme.primary, b.theme.accent):
            b.theme.primary, b.theme.accent, b.theme.custom_colors = p, a, True
        pm = st.multiselect("Ödeme", ["Kapıda Nakit", "Kapıda Kredi Kartı", "Havale/EFT", "Yemek Kartı"], b.payment_methods)
        b.payment_methods = pm or b.payment_methods
        mo, df_ = st.columns(2)
        b.min_order = mo.number_input("Min. sipariş ₺", value=float(b.min_order or 0), step=50.0) or None
        b.delivery_fee = df_.number_input("Kurye ücreti ₺", value=float(b.delivery_fee or 0), step=10.0) or None

    col_a, col_b = st.columns([1, 4])
    if col_a.button("← Geri", use_container_width=True):
        st.session_state["step"] = 1
        st.rerun()
    if col_b.button("Siteyi üret →", type="primary", disabled=not menu_text.strip(), use_container_width=True):
        with st.spinner("Yerel model menüyü dijitalleştiriyor…"):
            llm = LocalLLM.connect(alias)
            menu: Menu = extract_menu(llm, menu_text)
        site = Site(business=b, menu=menu)
        images_dir = None
        if photos:
            images_dir = OUT / "_uploads" / site.business.slug
            images_dir.mkdir(parents=True, exist_ok=True)
            for f in photos:
                (images_dir / f.name).write_bytes(f.getbuffer())
        st.session_state["site"] = site
        st.session_state["images_dir"] = images_dir
        st.session_state["out"] = build(site, images_from=images_dir)
        st.session_state["step"] = 3
        st.rerun()

# ------------------------------------------------------------------ 3
else:
    site: Site = st.session_state["site"]
    out: Path = st.session_state["out"]
    images_dir: Path | None = st.session_state.get("images_dir")
    img_files = sorted(p.name for p in images_dir.iterdir()) if images_dir and images_dir.exists() else []
    n_img = sum(1 for c in site.menu.categories for i in c.items if i.image)

    st.subheader(f"{site.business.name} hazır 🎉")
    st.markdown(f'<p class="hint">{len(site.menu.categories)} kategori · {site.menu.item_count} ürün · {n_img} fotoğraf · tema: {STYLES[site.business.theme.style].split(" · ")[0]} · 4 sayfa</p>', unsafe_allow_html=True)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in out.parent.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(out.parent))
    d1, d2, d3 = st.columns([2, 1, 1])
    d1.download_button("⬇ Siteyi indir (zip · 4 sayfa + görseller)", zbuf.getvalue(), file_name=f"{site.business.slug}.zip", mime="application/zip", use_container_width=True, type="primary")
    d2.download_button("site.json", site.model_dump_json(indent=2), file_name="site.json", mime="application/json", use_container_width=True)
    if d3.button("Baştan başla", use_container_width=True):
        for k in ("step", "business", "site", "out", "images_dir"):
            st.session_state.pop(k, None)
        st.rerun()

    # ---- son kontrol
    st.markdown("### Son kontrol — bir şey yanlışsa burada düzelt")
    st.markdown('<p class="hint">Model yüzde yüz değildir. Türkçe karakter, gramaj, fiyat, eski fiyat, açıklama ve fotoğraf eşlemesini gözden geçir. Hücreye tıkla, düzelt, en altta <b>Yeniden üret</b>.</p>', unsafe_allow_html=True)
    rows = [{"Kategori": c.name, "Ürün": i.name, "Porsiyon": i.portion, "Fiyat": i.price,
             "Eski fiyat": i.old_price or None, "Açıklama": i.description, "Etiketler": ", ".join(i.tags),
             "Görsel": Path(i.image).name if i.image else "", "Sil": False}
            for c in site.menu.categories for i in c.items]
    edited = st.data_editor(
        pd.DataFrame(rows), num_rows="dynamic", use_container_width=True, hide_index=True,
        height=min(560, 60 + 36 * max(len(rows), 1)),
        column_config={
            "Kategori": st.column_config.TextColumn(width="medium"),
            "Ürün": st.column_config.TextColumn(width="medium", required=True),
            "Porsiyon": st.column_config.TextColumn(width="small", help="130 gr, 1 kg, 8 adet"),
            "Fiyat": st.column_config.NumberColumn(format="%.0f ₺", min_value=0, required=True),
            "Eski fiyat": st.column_config.NumberColumn(format="%.0f ₺", min_value=0, help="İndirim varsa üstü çizili gösterilir"),
            "Açıklama": st.column_config.TextColumn(width="large"),
            "Etiketler": st.column_config.TextColumn(width="small", help="virgülle: acı, vejetaryen, popüler, imza"),
            "Görsel": st.column_config.SelectboxColumn(options=[""] + img_files, width="medium", help="Yüklediğin fotoğraflardan seç"),
            "Sil": st.column_config.CheckboxColumn(width="small"),
        },
        key="editor",
    )
    e1, e2, e3 = st.columns([2, 2, 1])
    new_tagline = e1.text_input("Büyük başlık (slogan)", site.business.tagline, help="Ana sayfadaki dev başlık. 3-5 kelime.")
    new_about = e2.text_input("Hakkımızda metni", site.business.about)
    hero_opts = [""] + img_files
    cur_hero = Path(site.business.hero_image).name if site.business.hero_image else ""
    hero_pick = e3.selectbox("Kapak fotoğrafı", hero_opts, index=hero_opts.index(cur_hero) if cur_hero in hero_opts else 0)
    more_photos = st.file_uploader("Fotoğraf ekle (ürün adıyla adlandır ya da tabloda seç)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="more_photos")

    if st.button("🔁 Yeniden üret", type="primary", use_container_width=True):
        if more_photos:
            images_dir = images_dir or (OUT / "_uploads" / site.business.slug)
            images_dir.mkdir(parents=True, exist_ok=True)
            for f in more_photos:
                (images_dir / f.name).write_bytes(f.getbuffer())
            st.session_state["images_dir"] = images_dir
        icons = {c.name: c.icon for c in site.menu.categories}
        cats: dict[str, Category] = {}
        for _, r in edited.iterrows():
            if bool(r.get("Sil")) or not str(r["Ürün"]).strip() or pd.isna(r["Fiyat"]):
                continue
            cat = str(r["Kategori"]).strip() or "Menü"
            cats.setdefault(cat, Category(name=cat, icon=icons.get(cat, "🍽️"), items=[]))
            txt = lambda k: str(r[k]).strip() if isinstance(r[k], str) else ""  # noqa: E731
            old = r["Eski fiyat"]
            cats[cat].items.append(MenuItem(
                name=txt("Ürün"), price=float(r["Fiyat"]),
                old_price=None if pd.isna(old) or not old else float(old),
                portion=txt("Porsiyon"), description=txt("Açıklama"),
                tags=[t.strip() for t in txt("Etiketler").split(",") if t.strip()],
                image=f"images/{txt('Görsel')}" if txt("Görsel") else ""))
        site.menu = Menu(categories=list(cats.values()))
        site.business.tagline, site.business.about = new_tagline, new_about
        site.business.hero_image = f"images/{hero_pick}" if hero_pick else ""
        st.session_state["out"] = build(site, images_from=images_dir)
        st.session_state["site"] = site
        st.rerun()

    with st.expander("Nasıl yayınlarım?"):
        st.markdown("""
Zip'i aç, klasörü herhangi bir statik hosta at: **Netlify Drop** (sürükle-bırak), **Cloudflare Pages**, **GitHub Pages** ya da mevcut hosting'inin `public_html` klasörü.
Alan adını bağla, bitti. Sunucu, veritabanı, abonelik yok. Menü değişince buraya gelip yeniden üret.
""")

    st.markdown("### Önizleme")
    for tab, (page, _) in zip(st.tabs([t for _, t in PAGES]), PAGES):
        with tab:
            components.html(inline_page(out.parent, page), height=900, scrolling=True)
