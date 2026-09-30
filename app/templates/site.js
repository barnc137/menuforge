/* Sepet + sipariş: tüm sayfalarda ortak. Ürün kataloğu window.SITE.items içinde. */
(function () {
  const S = window.SITE, $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const fmt = n => n.toLocaleString("tr-TR", { maximumFractionDigits: 0 }) + " ₺";
  let cart = {}; try { cart = JSON.parse(localStorage.getItem(S.key) || "{}"); } catch (e) {}
  for (const k in cart) if (!S.items[k]) delete cart[k];

  const save = () => { try { localStorage.setItem(S.key, JSON.stringify(cart)); } catch (e) {} paint(); };
  const count = () => Object.values(cart).reduce((a, b) => a + b, 0);
  const sub = () => Object.entries(cart).reduce((a, [k, q]) => a + S.items[k].price * q, 0);
  const pickup = () => ($("input[name=mode]:checked") || {}).value === "Gel-al";
  const grand = () => sub() + (pickup() ? 0 : S.fee);

  window.add = k => { cart[k] = (cart[k] || 0) + 1; save(); toast(S.items[k].name + " sepete eklendi"); };
  window.chg = (k, d) => { cart[k] = (cart[k] || 0) + d; if (cart[k] <= 0) delete cart[k]; save(); lines(); };
  window.openCart = () => { lines(); $("#dim").classList.add("on"); $("#drawer").classList.add("on"); document.body.style.overflow = "hidden"; };
  window.closeCart = () => { $("#dim").classList.remove("on"); $("#drawer").classList.remove("on"); document.body.style.overflow = ""; };
  window.modeChg = () => { $("#addrWrap").style.display = pickup() ? "none" : "block"; lines(); };

  function paint() {
    const n = count();
    $("#bar").classList.toggle("on", n > 0); $("#cartn").classList.toggle("on", n > 0); $("#cartn").textContent = n;
    $("#barTot").textContent = fmt(sub()); $("#barN").textContent = n + " ürün";
    $$("[data-key]").forEach(el => { const q = cart[el.dataset.key] || 0; el.classList.toggle("inCart", q > 0); const b = el.querySelector(".qtyc b"); if (b) b.textContent = q; });
  }
  function lines() {
    const e = Object.entries(cart);
    $("#lines").innerHTML = e.length ? e.map(([k, q]) => `<div class="line"><div class="nm"><b>${S.items[k].name}</b><span>${fmt(S.items[k].price)}</span></div><div class="q"><button onclick="chg(${JSON.stringify(k)},-1)">−</button><b>${q}</b><button onclick="chg(${JSON.stringify(k)},1)">+</button></div><div class="tot">${fmt(S.items[k].price * q)}</div></div>`).join("")
      : '<p class="empty">Sepetin boş. <a href="menu.html" style="color:var(--primary);font-weight:700">Menüye git →</a></p>';
    $("#sub").textContent = fmt(sub()); $("#grand").textContent = fmt(grand()); $("#send").disabled = !e.length;
    const d = $("#delRow"); if (d) d.style.display = pickup() ? "none" : "flex";
  }
  let tt; function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("on"), 1400); }
  const v = id => $("#" + id).value.trim();

  window.sendWA = () => {
    if (!count()) return;
    if (S.min && sub() < S.min) return toast("Minimum sipariş " + fmt(S.min));
    const name = v("f-name"), phone = v("f-phone"), addr = v("f-addr"), note = v("f-note");
    const mode = $("input[name=mode]:checked").value, pay = $("input[name=pay]:checked").value;
    if (!name || !phone) return toast("Ad ve telefon gerekli");
    if (!pickup() && !addr) return toast("Adres gerekli");
    let m = `*Yeni Sipariş — ${S.name}*\n\n`;
    for (const [k, q] of Object.entries(cart)) m += `• ${q} × ${S.items[k].name} — ${fmt(S.items[k].price * q)}\n`;
    m += `\nAra toplam: ${fmt(sub())}`; if (!pickup() && S.fee) m += `\nTeslimat: ${fmt(S.fee)}`;
    m += `\n*Toplam: ${fmt(grand())}*\n\n👤 ${name}\n📞 ${phone}\n🚚 ${mode}`;
    if (!pickup()) m += `\n📍 ${addr}`; m += `\n💳 ${pay}`; if (note) m += `\n📝 ${note}`;
    window.open("https://wa.me/" + S.wa + "?text=" + encodeURIComponent(m), "_blank");
  };

  /* menü sayfası: arama + aktif kategori */
  const q = $("#q");
  if (q) q.addEventListener("input", e => {
    const t = e.target.value.toLowerCase().trim(); let any = false;
    $$(".item").forEach(el => { const ok = !t || el.dataset.q.includes(t); el.style.display = ok ? "" : "none"; any = any || ok; });
    $$("section.cat").forEach(s => s.style.display = [...s.querySelectorAll(".item")].some(i => i.style.display !== "none") ? "" : "none");
    $("#noRes").hidden = any;
  });
  const links = $$("#catrow a");
  if (links.length) {
    const spy = new IntersectionObserver(es => { es.forEach(en => { if (!en.isIntersecting) return;
      links.forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#" + en.target.id));
      const a = $("#catrow a.on"); a && a.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" }); }); }, { rootMargin: "-132px 0px -70% 0px" });
    $$("section.cat").forEach(s => spy.observe(s));
  }

  /* açık/kapalı: ilk "11:00-23:30" biçimli aralıktan */
  const pill = $("#pill");
  if (pill) { const t = (S.hours.join(" ").match(/(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})/)); if (t) {
    const now = new Date(), m = now.getHours() * 60 + now.getMinutes(); let o = +t[1] * 60 + +t[2], c = +t[3] * 60 + +t[4]; if (c <= o) c += 1440;
    const open = (m >= o && m < c) || (m + 1440 >= o && m + 1440 < c);
    pill.classList.toggle("off", !open); $("#openTxt").textContent = open ? "Şu an açığız · sipariş verebilirsiniz" : "Şu an kapalıyız · siparişiniz açılışta hazırlanır"; } }
  paint();
})();
