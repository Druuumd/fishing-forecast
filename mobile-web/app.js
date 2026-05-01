/* KVH Forecast mobile PWA — vanilla JS, no build step.
 *
 * Mirrors the React `web/` client at feature parity:
 *   - tab navigation (forecast / history / catch / push / profile / etc.)
 *   - zone selector with all 13 named bays
 *   - rich forecast cards (factors + gates highlighted, water banner, surface pressure)
 *   - history charts (SVG sparklines for water level, temps, pressure, wind/precip)
 *   - push notification constructor (catalog-driven, multi-condition)
 *   - online/offline indicator
 *   - service worker registered for offline fallback + Web Push delivery
 *
 * Layout choices:
 *   - One IIFE; helpers and per-tab renderers grouped below.
 *   - DOM updates via createElement / setText (no innerHTML for user data).
 *   - State persisted to localStorage with `ff_` prefix (kept compatible
 *     with previous mobile-web revision so nothing gets lost on update).
 */
(function () {
  "use strict";

  // ---- Constants -------------------------------------------------------

  const SPECIES_LABEL = { pike: "щука", perch: "окунь", bream: "лещ" };

  // Bays grouped by thermal/depth archetype. Mirrors web/ ZONE_OPTION_GROUPS
  // so the user picks by fishing intent ("warm shallow spawning bay" /
  // "deep cool trolling water") rather than memorising 13 names.
  const ZONE_GROUPS = [
    { label: "—", options: [{ value: "", label: "вся акватория" }] },
    {
      label: "Мелководные тёплые (нерест, лещ, прибрежный)",
      options: [
        { value: "syda", label: "Сыдинский (р. Сыда)" },
        { value: "ubey", label: "Убейский (р. Убей)" },
        { value: "karasug", label: "Карасугский (р. Карасуг)" },
        { value: "yezagash", label: "Езагашский (р. Езагаш, заболоченный)" },
      ],
    },
    {
      label: "Узкие мелкие (рыбалка)",
      options: [
        { value: "anash", label: "Анашский (р. Анаша)" },
        { value: "koma", label: "Комский (р. Кома)" },
      ],
    },
    {
      label: "Средняя глубина (универсальные)",
      options: [
        { value: "ogur", label: "Огурский (р. Огур)" },
        { value: "izhul", label: "Ижульский (р. Ижуль)" },
        { value: "derbino", label: "Дербинский (р. Дербина)" },
      ],
    },
    {
      label: "Глубокие прохладные (щука/окунь, троллинг)",
      options: [
        { value: "sisim", label: "Сисимский (р. Сисим)" },
        { value: "biryusa", label: "Бирюсинский (р. Бирюса)" },
        { value: "tubinsky", label: "Тубинский (р. Туба)" },
      ],
    },
    {
      label: "Открытая вода",
      options: [{ value: "main_channel", label: "Главное русло" }],
    },
  ];
  const ALL_ZONE_VALUES = ZONE_GROUPS.flatMap((g) => g.options.map((o) => o.value));

  // Populates a <select> with grouped zones via <optgroup>. The
  // first "—" group with a single empty value renders as a plain
  // option (no group label) so the dropdown looks natural.
  function populateZoneSelect(sel) {
    sel.innerHTML = "";
    for (const group of ZONE_GROUPS) {
      if (group.options.length === 1 && !group.options[0].value) {
        sel.append(el("option", { value: "", text: group.options[0].label }));
        continue;
      }
      const og = document.createElement("optgroup");
      og.label = group.label;
      for (const opt of group.options) {
        const o = document.createElement("option");
        o.value = opt.value;
        o.textContent = opt.label;
        og.append(o);
      }
      sel.append(og);
    }
  }

  function inferDefaultBaseUrl() {
    if (typeof window === "undefined") return "https://kvh-forecast.ru";
    const h = window.location.hostname;
    if (
      h === "localhost" || h === "127.0.0.1" ||
      h.endsWith("kvh-forecast.ru") ||
      h === "192.168.0.250" || h === "84.22.146.195"
    ) {
      return window.location.origin;
    }
    return "https://kvh-forecast.ru";
  }

  // ---- State -----------------------------------------------------------

  const state = {
    token: localStorage.getItem("ff_token") || "",
    baseUrl: localStorage.getItem("ff_base_url") || inferDefaultBaseUrl(),
    zone: localStorage.getItem("ff_zone") || "",
    species: localStorage.getItem("ff_species") || "pike",
    queue: JSON.parse(localStorage.getItem("ff_catch_queue") || "[]"),
    activeTab: "forecast",
    forecastRes: null,
    waterHistory: [],
    weatherHistory: [],
    myCatches: [],
    pushVapid: null,
    pushTypes: [],
    pushSubs: [],
    pushForm: {
      name: "",
      scope_zone: "",
      scope_species: "pike",
      conditions: [{ type: "score_min", params: { min: 3.5 } }],
    },
    pushNewType: "score_min",
    online: typeof navigator === "undefined" ? true : navigator.onLine,
    warnings: [],
    warningsDismissed: {}, // populated in init() to use loadDismissedWarnings()
    zoneCenters: [],
    wtPoints: [],
    wtMap: null,
    wtMarkerLayer: null,
  };

  // ---- DOM helpers -----------------------------------------------------

  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs, ...children) => {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k === "html") node.innerHTML = v;
        else if (k.startsWith("on") && typeof v === "function") {
          node.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (k === "data") {
          for (const [dk, dv] of Object.entries(v)) node.dataset[dk] = dv;
        } else {
          node.setAttribute(k, v);
        }
      }
    }
    for (const c of children) {
      if (c == null || c === false) continue;
      node.append(typeof c === "string" || typeof c === "number" ? String(c) : c);
    }
    return node;
  };
  // SVG elements need to be created in the SVG namespace; the regular
  // `el` helper would emit HTML elements that won't render inside <svg>.
  const SVG_NS = "http://www.w3.org/2000/svg";
  const elNS = (tag, attrs, ...children) => {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        node.setAttribute(k, String(v));
      }
    }
    for (const c of children) {
      if (c == null || c === false) continue;
      node.append(typeof c === "string" || typeof c === "number" ? String(c) : c);
    }
    return node;
  };

  // Lazy-load Leaflet from CDN; resolves to window.L. Cached promise so
  // multiple tab opens don't spawn duplicate <script> tags.
  const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
  const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  let _leafletPromise = null;
  function loadLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    if (_leafletPromise) return _leafletPromise;
    _leafletPromise = new Promise((resolve, reject) => {
      if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = LEAFLET_CSS;
        document.head.appendChild(css);
      }
      const s = document.createElement("script");
      s.src = LEAFLET_JS;
      s.onload = () => resolve(window.L);
      s.onerror = () => reject(new Error("leaflet load failed"));
      document.head.appendChild(s);
    });
    return _leafletPromise;
  }
  function tempColor(t) {
    if (t == null || Number.isNaN(t)) return "#94a3b8";
    if (t < 5) return "#0c4a6e";
    if (t < 10) return "#0ea5e9";
    if (t < 15) return "#22d3ee";
    if (t < 20) return "#84cc16";
    if (t < 25) return "#fb923c";
    return "#dc2626";
  }

  const showOut = (id, value) => {
    const node = $(id);
    if (!node) return;
    node.hidden = false;
    node.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  };
  const hide = (id) => { const n = $(id); if (n) n.hidden = true; };
  const fmtDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", weekday: "short" });
  };
  const fmtDateFriendly = (iso) => {
    if (!iso) return "—";
    const target = new Date(`${iso}T12:00:00`);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const t = new Date(target); t.setHours(0, 0, 0, 0);
    const days = Math.round((t - today) / 86400000);
    if (days === 0) return "Сегодня";
    if (days === 1) return "Завтра";
    if (days === -1) return "Вчера";
    return target.toLocaleDateString("ru-RU", { day: "numeric", month: "short", weekday: "short" });
  };
  function scoreVerdict(score) {
    if (score >= 4.3) return { tier: "excellent", label: "Отличный день — пора собираться!", emoji: "🔥" };
    if (score >= 3.5) return { tier: "good", label: "Хороший день для ловли", emoji: "👍" };
    if (score >= 2.5) return { tier: "fair", label: "Средний клёв, шансы есть", emoji: "🤔" };
    if (score >= 1.5) return { tier: "weak", label: "Слабый день, не лучшее время", emoji: "🙁" };
    return { tier: "bad", label: "Сегодня клёва не ждите", emoji: "🚫" };
  }
  // ---- Loading skeletons (mirrors web/ DayCardSkeleton + ChartSkeleton)
  function renderDayCardSkeleton(hero) {
    const cls = ["day-card", "skeleton"];
    if (hero) cls.push("today");
    const headLeft = el("div", { class: "day-head-left" },
      el("div", { class: "sk-line sk-w-40", style: `height:${hero ? 22 : 16}px` }),
      el("div", { class: "sk-line sk-w-70", style: "height:13px;margin-top:6px" }),
    );
    const headRight = el("div", { class: "day-head-right" },
      el("div", { class: "sk-line sk-w-50", style: `height:${hero ? 22 : 16}px;width:90px` }),
      el("div", { class: "sk-line sk-w-30", style: "height:13px" }),
    );
    const meta = el("div", { class: "sk-meta-grid" });
    for (let i = 0; i < 6; i++) {
      meta.append(el("div", { class: "sk-meta-row" },
        el("span", { class: "sk-line sk-w-30" }),
        el("span", { class: "sk-line sk-w-50" }),
      ));
    }
    return el("div", { class: cls.join(" ") },
      el("div", { class: "day-head" }, headLeft, headRight),
      el("div", { class: "sk-block", style: "height:28px" }),
      meta,
      el("div", { class: "sk-block", style: "height:12px" }),
      el("div", { class: "sk-block", style: "height:12px;width:70%" }),
      el("div", { class: "sk-block", style: "height:12px;width:85%" }),
    );
  }
  function renderForecastSkeleton(host) {
    host.innerHTML = "";
    host.append(renderDayCardSkeleton(true));
    host.append(renderDayCardSkeleton(false));
    host.append(renderDayCardSkeleton(false));
  }
  function renderHistorySkeleton(host) {
    host.innerHTML = "";
    const summary = el("div", { class: "history-summary" });
    for (let i = 0; i < 4; i++) {
      summary.append(el("div", { class: "stat skeleton" },
        el("div", { class: "sk-line sk-w-50" }),
        el("div", { class: "sk-line sk-w-70", style: "height:16px;margin-top:4px" }),
      ));
    }
    host.append(summary);
    for (const label of ["Уровень воды (м)", "Температура воды и воздуха (°C)", "Давление (hPa)", "Ветер (м/с) и осадки (мм)"]) {
      host.append(el("div", { class: "chart-block" },
        el("h3", { text: label }),
        el("div", { class: "sk-chart" }),
      ));
    }
  }

  function renderScoreFish(score) {
    const wrap = el("div", { class: "score-fish", title: `${score.toFixed(2)}/5` });
    const filled = Math.max(0, Math.min(5, score));
    for (let i = 1; i <= 5; i++) {
      const portion = Math.max(0, Math.min(1, filled - (i - 1)));
      const cell = el("span", { class: "score-fish-cell", style: `--fill:${portion * 100}%` }, "🐟");
      wrap.append(cell);
    }
    return wrap;
  }
  const fmtSigned = (v, digits = 2) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(digits)}`;

  // ---- API client ------------------------------------------------------

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let res;
    try {
      res = await fetch(`${state.baseUrl}${path}`, { ...options, headers });
    } catch (err) {
      throw new Error(JSON.stringify({
        status: 0, code: "NETWORK_ERROR",
        message: `Failed to fetch ${state.baseUrl}${path}`, retryable: true,
      }));
    }
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
    if (!res.ok) {
      const err = body?.error || {};
      throw new Error(JSON.stringify({
        status: res.status, code: err.code || "HTTP_ERROR",
        message: err.message || "request failed", retryable: !!err.retryable,
        details: err.details || null,
      }));
    }
    return body;
  }

  // ---- Tab switching ---------------------------------------------------

  function switchTab(name) {
    state.activeTab = name;
    document.querySelectorAll(".tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll(".tab-pane").forEach((p) => {
      p.hidden = p.dataset.pane !== name;
    });
    if (name === "forecast") loadForecast();
    if (name === "history") { loadHistory(); if (state.token) loadMyCatches(); }
    if (name === "push") loadPush();
    if (name === "water_temp") loadWaterTempPoints();
  }

  // ---- Water-temp readings (user-submitted thermal profile) ------------

  async function submitWaterTempReading() {
    clearWtFieldErrors();
    const body = {
      measured_at: new Date($("wtMeasuredAt").value).toISOString(),
      latitude: Number($("wtLat").value),
      longitude: Number($("wtLon").value),
      surface_temp_c: Number($("wtSurface").value),
      thermocline_depth_m: $("wtDepth").value === "" ? null : Number($("wtDepth").value),
      below_thermocline_temp_c: $("wtBelow").value === "" ? null : Number($("wtBelow").value),
      instrument: $("wtInstrument").value || null,
      note: $("wtNote").value || null,
    };
    try {
      const r = await api("/v1/water-temp-readings", { method: "POST", body: JSON.stringify(body) });
      showOut("wtOut", { status: "saved", id: r.id, zone: r.zone });
      loadWaterTempPoints();
    } catch (e) {
      try {
        const parsed = JSON.parse(e.message);
        if (parsed?.details?.field_errors) {
          for (const [field, msg] of Object.entries(parsed.details.field_errors)) {
            const id = ({
              measured_at: "wtMeasuredAt",
              latitude: "wtLat", longitude: "wtLon",
              surface_temp_c: "wtSurface",
              thermocline_depth_m: "wtDepth",
              below_thermocline_temp_c: "wtBelow",
            })[field];
            const node = id ? $(id) : null;
            if (node) {
              node.classList.add("input-bad");
              const err = el("div", { class: "field-error", text: msg });
              node.parentNode.append(err);
            }
          }
        }
        showOut("wtOut", parsed);
      } catch {
        showOut("wtOut", e.message);
      }
    }
  }

  function clearWtFieldErrors() {
    document.querySelectorAll(".tab-pane[data-pane=water_temp] .input-bad").forEach((n) => {
      n.classList.remove("input-bad");
    });
    document.querySelectorAll(".tab-pane[data-pane=water_temp] .field-error").forEach((n) => n.remove());
  }

  async function loadWaterTempPoints() {
    try {
      const [pointsRes, zonesRes] = await Promise.all([
        api("/v1/water-temp-readings"),
        state.zoneCenters && state.zoneCenters.length
          ? Promise.resolve({ zones: state.zoneCenters })
          : api("/v1/zones/centers"),
      ]);
      state.zoneCenters = zonesRes.zones || state.zoneCenters || [];
      state.wtPoints = pointsRes.points || [];

      // List
      const list = $("wtList");
      list.innerHTML = "";
      if (state.wtPoints.length === 0) {
        list.append(el("li", { class: "hint", text: "пока нет замеров" }));
      } else {
        for (const p of state.wtPoints) {
          const therm = p.thermocline_depth_m != null
            ? ` · термоклин ${p.thermocline_depth_m}м · ниже ${p.below_thermocline_temp_c}°C`
            : "";
          const main = el("div", null,
            el("strong", { text: p.zone || "?" }),
            ` · поверхность `,
            el("strong", { text: `${p.surface_temp_c.toFixed(1)}°C` }),
            therm,
            el("div", { class: "meta", text: `${fmtDate(p.measured_at)} · ${p.latitude.toFixed(3)},${p.longitude.toFixed(3)}${p.instrument ? ` · ${p.instrument}` : ""}` }),
          );
          list.append(el("li", null, main));
        }
      }
      // Map
      await renderWaterTempMap();
    } catch (e) {
      showOut("wtOut", e.message);
    }
  }

  // Initialise (or refresh) the Leaflet map inside #wtMap. Markers come
  // from state.zoneCenters (gray) and state.wtPoints (color by Tw).
  async function renderWaterTempMap() {
    const mount = $("wtMap");
    if (!mount) return;
    let L;
    try {
      L = await loadLeaflet();
    } catch (_) {
      mount.textContent = "Не удалось загрузить карту (нет доступа к unpkg.com).";
      return;
    }
    if (!state.wtMap) {
      state.wtMap = L.map(mount).setView([54.7, 91.7], 8);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap",
        maxZoom: 18,
      }).addTo(state.wtMap);
      state.wtMap.on("click", (e) => {
        const lat = Number(e.latlng.lat.toFixed(5));
        const lon = Number(e.latlng.lng.toFixed(5));
        $("wtLat").value = String(lat);
        $("wtLon").value = String(lon);
      });
    } else {
      // Tab may have been hidden; tell Leaflet to recompute its size.
      setTimeout(() => state.wtMap.invalidateSize(), 50);
    }
    if (state.wtMarkerLayer) state.wtMap.removeLayer(state.wtMarkerLayer);
    const layer = L.layerGroup();
    for (const z of state.zoneCenters || []) {
      const m = L.circleMarker([z.lat, z.lon], {
        color: "#94a3b8", radius: 6, weight: 2, fillOpacity: 0.25,
      });
      m.bindPopup(`<strong>${z.label}</strong>`);
      layer.addLayer(m);
    }
    for (const p of state.wtPoints || []) {
      const c = tempColor(p.surface_temp_c);
      const m = L.circleMarker([p.latitude, p.longitude], {
        color: c, radius: 8, weight: 2, fillColor: c, fillOpacity: 0.7,
      });
      const therm = p.thermocline_depth_m != null
        ? `<br/>термоклин ${p.thermocline_depth_m}м · ниже ${p.below_thermocline_temp_c}°C`
        : "";
      m.bindPopup(
        `<strong>${p.zone || "?"}</strong><br/>` +
        `Tw поверхность: <strong>${Number(p.surface_temp_c).toFixed(1)}°C</strong>${therm}<br/>` +
        `<small>${new Date(p.measured_at).toLocaleString("ru-RU")}</small>`
      );
      layer.addLayer(m);
    }
    layer.addTo(state.wtMap);
    state.wtMarkerLayer = layer;
  }

  function useGeoForWaterTemp() {
    if (!navigator.geolocation) {
      showOut("wtOut", { status: "geolocation_not_supported" });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => {
        $("wtLat").value = p.coords.latitude.toFixed(5);
        $("wtLon").value = p.coords.longitude.toFixed(5);
        showOut("wtOut", { status: "ok", source: "gps" });
      },
      (err) => showOut("wtOut", { status: "error", message: err.message }),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  // ---- Forecast tab ----------------------------------------------------

  async function loadForecast() {
    const params = new URLSearchParams({ species: state.species });
    if (state.zone) params.set("zone", state.zone);
    const wParams = new URLSearchParams();
    if (state.zone) wParams.set("zone", state.zone);
    // Show skeleton placeholders while we wait, but only on the very
    // first load — subsequent refreshes keep the previous data visible
    // to avoid flicker (stale-while-revalidate pattern).
    if (!state.forecastRes) {
      renderForecastSkeleton($("forecastDays"));
    }
    try {
      // Forecast + warnings in parallel — warnings are a soft addition,
      // never block the forecast on their failure.
      const [r, w] = await Promise.all([
        api(`/v1/forecast?${params.toString()}`),
        api(`/v1/warnings${wParams.toString() ? "?" + wParams.toString() : ""}`).catch(() => ({ warnings: [] })),
      ]);
      state.forecastRes = r;
      state.warnings = w.warnings || [];
      renderForecast(r);
      renderWarnings();
    } catch (e) {
      showOut("forecastOut", e.message);
    }
  }

  // -- Warnings panel: dismissed codes persisted with 24h TTL.
  function loadDismissedWarnings() {
    try {
      const raw = JSON.parse(localStorage.getItem("ff_warnings_dismissed") || "{}");
      const now = Date.now();
      const valid = {};
      for (const [code, ts] of Object.entries(raw)) {
        if (now - ts < 24 * 3600 * 1000) valid[code] = ts;
      }
      return valid;
    } catch { return {}; }
  }
  function dismissWarningCode(code) {
    state.warningsDismissed[code] = Date.now();
    localStorage.setItem("ff_warnings_dismissed", JSON.stringify(state.warningsDismissed));
    renderWarnings();
  }
  const SEVERITY_ICON = { danger: "❗", warn: "⚠️", info: "ℹ️" };
  const SEVERITY_ORDER = { danger: 0, warn: 1, info: 2 };
  function renderWarnings() {
    const host = $("warningsPanel");
    if (!host) return;
    host.innerHTML = "";
    const items = (state.warnings || [])
      .filter((w) => !state.warningsDismissed[w.code])
      .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
    for (const w of items) {
      const close = el("button", { class: "warning-dismiss", title: "Скрыть" }, "×");
      close.addEventListener("click", () => dismissWarningCode(w.code));
      const head = el("div", { class: "warning-head" },
        el("span", { class: "warning-icon", text: SEVERITY_ICON[w.severity] || "" }),
        el("strong", { class: "warning-title", text: w.title }),
        close,
      );
      const body = el("div", { class: "warning-body", text: w.body });
      const when = (w.valid_from || w.valid_to)
        ? el("div", { class: "warning-when", text:
            (w.valid_from ? `с ${fmtDate(w.valid_from)}` : "") +
            (w.valid_to && w.valid_to !== w.valid_from ? ` · по ${fmtDate(w.valid_to)}` : "")
          })
        : null;
      host.append(el("div", { class: `warning warning-${w.severity}` }, head, body, when));
    }
  }

  function renderForecast(r) {
    // Zone label
    const lbl = $("forecastZoneLabel");
    if (r.zone_label) {
      lbl.hidden = false;
      lbl.innerHTML = `зона: <strong>${r.zone_label}</strong>`;
    } else {
      lbl.hidden = true;
    }

    // Water banner
    const wb = $("waterBanner");
    wb.innerHTML = "";
    if (r.water_level_m != null) {
      const trend = r.water_level_trend_7d_m || 0;
      const trendClass = trend > 0.05 ? "up" : trend < -0.05 ? "down" : "";
      const src = r.water_level_source || "";
      const isAuto = /^(allrivers|rushydro|favr|auto)/i.test(src);
      const isClim = src === "climatology";
      const srcLabel = isAuto ? `${src} (auto)` :
        isClim ? "climatology (модель)" :
        src ? `${src} (manual)` : "—";
      const banner = el("div", { class: "water-banner" },
        el("div", { class: "stat" },
          el("span", { class: "k", text: "Уровень водохранилища" }),
          el("span", { class: "v", text: `${r.water_level_m.toFixed(2)} м` })),
        el("div", { class: "stat" },
          el("span", { class: "k", text: "Δ за 7 дней" }),
          el("span", { class: `v ${trendClass}`, text: `${fmtSigned(trend, 2)} м` })),
        el("div", { class: "stat" },
          el("span", { class: "k", text: "источник" }),
          el("span", { class: "v", text: `${srcLabel}${r.water_level_is_fresh ? "" : " · стар."}` })),
      );
      wb.append(banner);
    }

    // Day cards
    const grid = $("forecastDays");
    grid.innerHTML = "";
    r.days.forEach((d, i) => grid.append(renderDayCard(d, i === 0)));
    hide("forecastOut");
  }

  function renderDayCard(d, isToday) {
    const factors = d.factors || [];
    const hasGate = factors.some((f) => f.name.endsWith("_gate"));
    const verdict = scoreVerdict(d.score);
    const cls = ["day-card", `day-${verdict.tier}`];
    if (hasGate) cls.push("gated");
    if (isToday) cls.push("today");

    const dlMeta = el("dl", { class: "day-meta" });
    const addMeta = (k, v) => { dlMeta.append(el("dt", { text: k }), el("dd", { text: v })); };
    addMeta("воздух", `${d.air_temp_c.toFixed(1)} °C`);
    addMeta("вода", `${d.water_temp_c.toFixed(1)} °C`);
    addMeta("давление", `${d.pressure_hpa.toFixed(0)} ↦ ${d.surface_pressure_hpa != null ? d.surface_pressure_hpa.toFixed(0) : "—"} hPa`);
    addMeta("ΔP/24h", `${fmtSigned(d.pressure_trend_24h_hpa, 1)} hPa`);
    addMeta("ветер", `${d.wind_speed_m_s.toFixed(1)} м/с · ${Math.round(d.wind_direction_deg)}°`);
    addMeta("облачно", `${Math.round(d.cloud_cover_pct)}%`);

    // Collapsible factor list — only show high-impact + gates by default.
    const isImportant = (f) => f.name.endsWith("_gate") || Math.abs(f.contribution) >= 0.15;
    const importantFactors = factors.filter(isImportant);
    const restFactors = factors.filter((f) => !isImportant(f));
    const factorsBox = el("div", { class: "factors" });
    let expanded = false;
    function repaintFactors() {
      factorsBox.innerHTML = "";
      const visible = expanded ? factors : importantFactors;
      for (const f of visible) {
        const isGate = f.name.endsWith("_gate");
        const sign = f.contribution > 0 ? "pos" : f.contribution < 0 ? "neg" : "";
        factorsBox.append(
          el("div", { class: `factor ${isGate ? "gate" : ""}` },
            el("span", { class: "name", text: f.name }),
            el("span", { class: `value ${sign}`, text: fmtSigned(f.contribution, 2) }),
            f.detail ? el("span", { class: "detail", text: f.detail }) : null,
          )
        );
      }
      if (restFactors.length > 0) {
        const btn = el("button", { class: "factor-expand" },
          expanded ? "свернуть" : `+ ещё ${restFactors.length} ${restFactors.length === 1 ? "фактор" : "факторов"}`);
        btn.addEventListener("click", () => { expanded = !expanded; repaintFactors(); });
        factorsBox.append(btn);
      }
    }
    repaintFactors();

    const head = el("div", { class: "day-head" },
      el("div", { class: "day-head-left" },
        el("div", { class: "day-date", text: fmtDateFriendly(d.date) }),
        el("div", { class: "day-verdict" },
          el("span", { class: "verdict-emoji", text: verdict.emoji }),
          el("span", { text: verdict.label }))),
      el("div", { class: "day-head-right" },
        renderScoreFish(d.score),
        el("div", { class: "day-score-num" },
          d.score.toFixed(1),
          el("span", { class: "day-conf",
            text: `${SPECIES_LABEL[d.species] || d.species} · ${(d.confidence * 100).toFixed(0)}%` }))),
    );

    return el("div", { class: cls.join(" ") },
      head,
      renderBestHoursStrip(d),
      dlMeta,
      renderThermoclineDiagram(d),
      factorsBox,
    );
  }

  // -- Best-hours horizontal 24h strip ----------------------------------
  const KIND_COLOR = {
    dawn: "#fbbf24",
    dusk: "#f97316",
    lunar_major: "#a78bfa",
    lunar_minor: "#818cf8",
  };

  function renderBestHoursStrip(d) {
    const windows = d.best_hours || [];
    if (windows.length === 0) return null;
    const W = 280, H = 26;
    const dayStart = new Date(`${d.date}T00:00:00`);
    const dayEnd = new Date(dayStart.getTime() + 24 * 3600 * 1000);
    const toX = (iso) => {
      const t = new Date(iso).getTime();
      const frac = Math.max(0, Math.min(1,
        (t - dayStart.getTime()) / (dayEnd.getTime() - dayStart.getTime())));
      return frac * W;
    };
    const today = new Date();
    const isToday = today.toDateString() === dayStart.toDateString();
    const nowX = isToday ? toX(today.toISOString()) : null;

    const svg = elNS("svg", {
      class: "bh-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none",
    });
    svg.append(elNS("line", {
      x1: 0, x2: W, y1: H / 2, y2: H / 2, stroke: "#334155", "stroke-width": 1,
    }));
    for (const h of [6, 12, 18]) {
      const x = (h / 24) * W;
      svg.append(
        elNS("line", { x1: x, x2: x, y1: H / 2 - 2, y2: H / 2 + 2, stroke: "#475569", "stroke-width": 1 }),
        elNS("text", { x, y: H - 1, fill: "#64748b", "font-size": 9, "text-anchor": "middle" }, String(h)),
      );
    }
    for (const w of windows) {
      const x1 = toX(w.start);
      const x2 = toX(w.end);
      const width = Math.max(2, x2 - x1);
      const rect = elNS("rect", {
        x: x1, y: 3, width, height: H / 2 - 4,
        fill: KIND_COLOR[w.kind] || "#94a3b8",
        opacity: 0.4 + 0.6 * (w.intensity ?? 1),
        rx: 2,
      });
      const fmt = (iso) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
      rect.append(elNS("title", null, `${w.label} ${fmt(w.start)}–${fmt(w.end)}`));
      svg.append(rect);
    }
    if (nowX != null) {
      svg.append(elNS("line", {
        x1: nowX, x2: nowX, y1: 1, y2: H - 4, stroke: "#f87171", "stroke-width": 1.5,
      }));
    }

    const legend = el("div", { class: "bh-legend" });
    for (const w of windows) {
      const fmt = (iso) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
      const color = KIND_COLOR[w.kind] || "#94a3b8";
      legend.append(el("span", {
        class: "bh-pill",
        style: `background:${color}33; border-color:${color}; border-width:1px; border-style:solid;`,
        text: `${w.label}: ${fmt(w.start)}–${fmt(w.end)}`,
      }));
    }
    return el("div", { class: "best-hours" }, svg, legend);
  }

  // -- Thermocline mini-diagram -----------------------------------------
  // SVG schematic: warm epilimnion (yellow) over cold hypolimnion (blue),
  // with the thermocline line (red) and recommended-depth marker (green).
  function renderThermoclineDiagram(d) {
    const strength = d.thermocline_strength || 0;
    if (!strength || strength < 0.15) return null;
    const depth = d.thermocline_depth_m;
    const rec = d.thermocline_recommended_depth_m;
    const totalDepth = Math.max(20, (depth || 10) + 10);
    const W = 180, H = 70, colW = 14, colX = 6, surfaceY = 10;
    const cliffY = surfaceY + ((depth || 0) / totalDepth) * (H - 14);
    const recY = surfaceY + ((rec || 0) / totalDepth) * (H - 14);
    const labelX = colX + colW + 6;

    const svg = elNS("svg", {
      class: "tc-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none",
    });
    svg.append(
      elNS("rect", {
        x: colX, y: surfaceY, width: colW, height: cliffY - surfaceY,
        fill: "#fbbf24", opacity: "0.6",
      }),
      elNS("rect", {
        x: colX, y: cliffY, width: colW, height: H - cliffY - 4,
        fill: "#0ea5e9", opacity: "0.6",
      }),
      elNS("line", {
        x1: colX - 2, x2: colX + colW + 2, y1: cliffY, y2: cliffY,
        stroke: "#dc2626", "stroke-width": 2,
      }),
    );
    if (rec != null) {
      svg.append(
        elNS("line", {
          x1: colX, x2: colX + colW + 14, y1: recY, y2: recY,
          stroke: "#16a34a", "stroke-width": 1, "stroke-dasharray": "3 3",
        }),
        elNS("text", {
          x: colX + colW + 16, y: recY + 3, fill: "#4ade80", "font-size": 10,
        }, `→ ${rec}м`),
      );
    }
    svg.append(
      elNS("text", { x: labelX, y: surfaceY + 10, fill: "#fde68a", "font-size": 10 }, "тёплый верх"),
      elNS("text", { x: labelX, y: cliffY - 2, fill: "#fca5a5", "font-size": 10 }, `термоклин ~${depth}м`),
      elNS("text", { x: labelX, y: H - 6, fill: "#7dd3fc", "font-size": 10 }, "холодный низ"),
    );

    const wrap = el("div", { class: "thermocline-banner" }, svg);
    if (d.thermocline_advice) {
      wrap.append(el("div", { class: "tc-advice", text: d.thermocline_advice }));
    }
    return wrap;
  }

  // ---- History tab + SVG sparkline ------------------------------------

  function lineChart(container, data, series, refLines = []) {
    container.innerHTML = "";
    if (!data || data.length === 0) {
      container.append(el("div", { class: "hint", text: "нет данных" }));
      return;
    }
    const W = 600, H = 110, padL = 30, padR = 10, padY = 12;
    const allY = [];
    for (const s of series) for (const d of data) {
      const v = d[s.key];
      if (v != null && Number.isFinite(v)) allY.push(v);
    }
    for (const r of refLines) allY.push(r.value);
    if (allY.length === 0) {
      container.append(el("div", { class: "hint", text: "нет данных" }));
      return;
    }
    const minY = Math.min(...allY);
    const maxY = Math.max(...allY);
    const rangeY = maxY - minY || 1;
    const stepX = data.length > 1 ? (W - padL - padR) / (data.length - 1) : 0;
    const toX = (i) => padL + i * stepX;
    const toY = (v) => H - padY - ((v - minY) / rangeY) * (H - padY * 2);

    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "chart");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("preserveAspectRatio", "none");

    const svgEl = (tag, attrs) => {
      const n = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
      return n;
    };

    // y labels
    svg.append(svgEl("text", { x: 4, y: padY + 4, class: "label", "text-anchor": "start" }));
    svg.lastChild.textContent = maxY.toFixed(maxY === Math.floor(maxY) ? 0 : 1);
    const lbl2 = svgEl("text", { x: 4, y: H - padY + 4, class: "label", "text-anchor": "start" });
    lbl2.textContent = minY.toFixed(minY === Math.floor(minY) ? 0 : 1);
    svg.append(lbl2);

    svg.append(svgEl("line", { class: "axis", x1: padL, y1: padY, x2: padL, y2: H - padY }));
    svg.append(svgEl("line", { class: "axis", x1: padL, y1: H - padY, x2: W - padR, y2: H - padY }));

    for (const r of refLines) {
      svg.append(svgEl("line", {
        class: "grid",
        x1: padL, x2: W - padR,
        y1: toY(r.value), y2: toY(r.value),
        stroke: r.color || "#475569",
      }));
      if (r.label) {
        const t = svgEl("text", {
          x: W - padR - 2, y: toY(r.value) - 2,
          class: "label", "text-anchor": "end", fill: r.color,
        });
        t.textContent = r.label;
        svg.append(t);
      }
    }

    for (const s of series) {
      const cmds = [];
      let started = false;
      data.forEach((d, i) => {
        const v = d[s.key];
        if (v == null || !Number.isFinite(v)) { started = false; return; }
        cmds.push(`${started ? "L" : "M"} ${toX(i).toFixed(1)} ${toY(v).toFixed(1)}`);
        started = true;
      });
      svg.append(svgEl("path", {
        class: "line", stroke: s.color, d: cmds.join(" "),
        "stroke-dasharray": s.dashed ? "4 3" : "0",
      }));
      data.forEach((d, i) => {
        const v = d[s.key];
        if (v == null || !Number.isFinite(v)) return;
        svg.append(svgEl("circle", {
          class: "dot", cx: toX(i), cy: toY(v), r: 2.4, fill: s.color,
        }));
      });
    }
    container.append(svg);
  }

  async function loadHistory() {
    const days = Number($("historyDays").value || 30);
    // Show skeletons inside chart hosts on first load (no data yet).
    const firstLoad = state.waterHistory.length === 0 && state.weatherHistory.length === 0;
    if (firstLoad) {
      const sum = $("historySummary");
      sum.innerHTML = "";
      const sumGrid = el("div", { class: "history-summary" });
      for (let i = 0; i < 4; i++) {
        sumGrid.append(el("div", { class: "stat skeleton" },
          el("div", { class: "sk-line sk-w-50" }),
          el("div", { class: "sk-line sk-w-70", style: "height:16px;margin-top:4px" }),
        ));
      }
      sum.append(sumGrid);
      for (const id of ["chartWater", "chartTemp", "chartPressure", "chartWind"]) {
        const host = $(id);
        if (host) { host.innerHTML = ""; host.append(el("div", { class: "sk-chart" })); }
      }
    }
    try {
      const [wl, w] = await Promise.all([
        api(`/v1/water-level/history?days=${days}`),
        api(`/v1/weather/history?days=${Math.min(days, 60)}`),
      ]);
      state.waterHistory = wl.points || [];
      state.weatherHistory = w.points || [];
      renderHistory();
    } catch (e) {
      showOut("forecastOut", e.message);
    }
  }

  // Build a single stat card: latest value + period average + delta with
  // direction-coloured arrow. higherIsBetter flips the colour mapping
  // (true = warmer/higher is good, false = e.g. less wind is good, null
  // = neutral context — pressure/level changes don't have an inherent
  // "better" direction).
  function buildStatCard(spec) {
    const { icon, label, value, avg, delta, deltaSuffix, deltaPrecision = 1, higherIsBetter } = spec;
    const eps = deltaPrecision === 0 ? 0.5 : 0.05;
    const direction = delta > eps ? "up" : delta < -eps ? "down" : "flat";
    let cls = "neutral";
    if (higherIsBetter === true) cls = direction === "up" ? "good" : direction === "down" ? "bad" : "neutral";
    else if (higherIsBetter === false) cls = direction === "up" ? "bad" : direction === "down" ? "good" : "neutral";
    else cls = direction === "flat" ? "neutral" : "info";
    const arrow = direction === "up" ? "↑" : direction === "down" ? "↓" : "→";
    const sign = delta >= 0 ? "+" : "";
    return el("div", { class: "stat-card" },
      el("div", { class: "stat-card-head" },
        el("span", { class: "stat-icon", text: icon }),
        el("span", { class: "stat-label", text: label })),
      el("div", { class: "stat-value", text: value }),
      el("div", { class: "stat-footer" },
        el("span", { class: "stat-avg", text: avg }),
        el("span", { class: `stat-delta stat-delta-${cls}`,
          text: `${arrow} ${sign}${delta.toFixed(deltaPrecision)}${deltaSuffix}` })),
    );
  }

  function renderHistory() {
    const sumWrap = $("historySummary");
    sumWrap.innerHTML = "";
    if (state.waterHistory.length === 0 && state.weatherHistory.length === 0) {
      // nothing to summarise yet
    } else {
      const grid = el("div", { class: "history-summary-cards" });
      if (state.waterHistory.length > 0) {
        const last = state.waterHistory[state.waterHistory.length - 1].level_m;
        const avg = state.waterHistory.reduce((s, p) => s + p.level_m, 0) / state.waterHistory.length;
        grid.append(buildStatCard({
          icon: "💧", label: "Уровень воды",
          value: `${last.toFixed(2)} м`,
          avg: `средн. ${avg.toFixed(2)} м`,
          delta: last - avg, deltaSuffix: " м", deltaPrecision: 2,
          higherIsBetter: null,
        }));
      }
      if (state.weatherHistory.length > 0) {
        const last = state.weatherHistory[state.weatherHistory.length - 1];
        const avg = (key) => state.weatherHistory.reduce((s, p) => s + (p[key] || 0), 0) / state.weatherHistory.length;
        grid.append(buildStatCard({
          icon: "🌊", label: "Tw воды",
          value: `${last.water_temp_c.toFixed(1)}°C`,
          avg: `средн. ${avg("water_temp_c").toFixed(1)}°C`,
          delta: last.water_temp_c - avg("water_temp_c"), deltaSuffix: "°C",
          higherIsBetter: null,
        }));
        grid.append(buildStatCard({
          icon: "🌡", label: "Воздух",
          value: `${last.air_temp_c.toFixed(1)}°C`,
          avg: `средн. ${avg("air_temp_c").toFixed(1)}°C`,
          delta: last.air_temp_c - avg("air_temp_c"), deltaSuffix: "°C",
          higherIsBetter: null,
        }));
        grid.append(buildStatCard({
          icon: "📊", label: "Давление",
          value: `${last.pressure_hpa.toFixed(0)} hPa`,
          avg: `средн. ${avg("pressure_hpa").toFixed(0)}`,
          delta: last.pressure_hpa - avg("pressure_hpa"),
          deltaSuffix: " hPa", deltaPrecision: 0,
          higherIsBetter: null,
        }));
        grid.append(buildStatCard({
          icon: "💨", label: "Ветер",
          value: `${last.wind_speed_m_s.toFixed(1)} м/с`,
          avg: `средн. ${avg("wind_speed_m_s").toFixed(1)}`,
          delta: last.wind_speed_m_s - avg("wind_speed_m_s"),
          deltaSuffix: " м/с",
          higherIsBetter: false,
        }));
      }
      sumWrap.append(grid);
    }

    lineChart($("chartWater"), state.waterHistory,
      [{ key: "level_m", color: "#38bdf8" }],
      [{ value: 243, color: "#16a34a", label: "НПУ 243" },
       { value: 225, color: "#dc2626", label: "УМО 225" }]);

    lineChart($("chartTemp"), state.weatherHistory,
      [{ key: "water_temp_c", color: "#0ea5e9" },
       { key: "air_temp_c", color: "#fbbf24", dashed: true }],
      [{ value: 0, color: "#475569" }]);

    lineChart($("chartPressure"), state.weatherHistory,
      [{ key: "pressure_hpa", color: "#a78bfa" },
       { key: "surface_pressure_hpa", color: "#34d399", dashed: true }]);

    lineChart($("chartWind"), state.weatherHistory,
      [{ key: "wind_speed_m_s", color: "#f87171" },
       { key: "precipitation_mm", color: "#60a5fa", dashed: true }]);
  }

  async function loadMyCatches() {
    try {
      const r = await api("/v1/me/data");
      state.myCatches = r.catches || [];
      renderMyCatches();
    } catch (e) {
      $("catchListWrap").innerHTML = `<div class="hint">${e.message}</div>`;
    }
  }

  function renderMyCatches() {
    const wrap = $("catchListWrap");
    wrap.innerHTML = "";
    if (!state.token) {
      wrap.append(el("div", { class: "hint", text: "Войдите в «Профиль», чтобы увидеть свои записи." }));
      return;
    }
    if (state.myCatches.length === 0) {
      wrap.append(el("div", { class: "hint", text: "пока нет записей" }));
      return;
    }
    const ul = el("ul", { class: "list" });
    for (const c of state.myCatches) {
      ul.append(el("li", null,
        el("div", null,
          el("strong", { text: SPECIES_LABEL[c.species] || c.species }),
          ` · оценка `,
          el("strong", { text: c.score.toFixed(1) }),
          el("div", { class: "meta",
            text: `${fmtDate(c.caught_at)} · ${c.latitude.toFixed(3)},${c.longitude.toFixed(3)}` +
                  ` · P ${c.linked_pressure_hpa.toFixed(0)} hPa · Tw ${c.linked_water_temp_c.toFixed(1)}°C`,
          }),
        ),
      ));
    }
    wrap.append(ul);
  }

  // ---- Push constructor -----------------------------------------------

  async function loadPush() {
    const supported = "serviceWorker" in navigator && "PushManager" in window;
    if (!supported) {
      $("pushUnavailable").hidden = false;
      $("pushUnavailable").textContent = "Браузер не поддерживает Web Push.";
      $("pushForm").hidden = true;
      return;
    }
    try {
      state.pushVapid = await api("/v1/push/vapid-public-key");
      const tt = await api("/v1/push/condition-types");
      state.pushTypes = tt.types || [];
    } catch (e) {
      showOut("pushOut", e.message);
      return;
    }
    if (!state.pushVapid?.enabled) {
      $("pushUnavailable").hidden = false;
      $("pushUnavailable").textContent = "Сервер не настроен для push (нет VAPID ключей).";
      $("pushForm").hidden = true;
      return;
    }
    $("pushUnavailable").hidden = true;
    $("pushForm").hidden = false;
    populatePushSelectors();
    renderPushConditions();
    if (state.token) {
      try {
        state.pushSubs = await api("/v1/push/subscriptions/me") || [];
        renderPushSubs();
      } catch (e) { showOut("pushOut", e.message); }
    } else {
      $("pushSubs").innerHTML = "";
      $("pushSubs").append(el("li", null, el("div", { class: "hint", text: "Войдите чтобы видеть подписки." })));
    }
  }

  function populatePushSelectors() {
    const zoneSel = $("pushZone");
    populateZoneSelect(zoneSel);
    zoneSel.value = state.pushForm.scope_zone || "";
    $("pushSpecies").value = state.pushForm.scope_species || "";
    $("pushName").value = state.pushForm.name || "";

    repaintPushTypeSelect();
  }

  // Refresh the "type to add" dropdown — hides types already used so
  // the user can't accidentally add a duplicate condition. Called on
  // populate AND after every add/remove via renderPushConditions.
  function repaintPushTypeSelect() {
    const typeSel = $("pushNewType");
    if (!typeSel) return;
    const used = new Set(state.pushForm.conditions.map((c) => c.type));
    typeSel.innerHTML = "";
    const available = state.pushTypes.filter((t) => !used.has(t.type));
    if (available.length === 0) {
      typeSel.append(el("option", { value: "", text: "— все типы добавлены" }));
      typeSel.disabled = true;
      return;
    }
    typeSel.disabled = false;
    for (const t of available) {
      typeSel.append(el("option", { value: t.type, text: t.label }));
    }
    if (!available.some((t) => t.type === state.pushNewType)) {
      state.pushNewType = available[0].type;
    }
    typeSel.value = state.pushNewType;
  }

  // Render conditions as compact pill-shaped chips (mirrors web/).
  // Each chip carries the type label, inline param inputs, and a small
  // ✕ button to remove. The chip layout wraps horizontally so a recipe
  // of 3-5 conditions stays compact even on a narrow phone screen.
  function renderPushConditions() {
    const wrap = $("pushConditions");
    wrap.innerHTML = "";
    if (state.pushForm.conditions.length === 0) {
      wrap.append(el("div", { class: "hint", text: "Добавьте хотя бы одно условие — выбор ниже." }));
      return;
    }
    const chipsBox = el("div", { class: "condition-chips" });
    state.pushForm.conditions.forEach((c, idx) => {
      const tdef = state.pushTypes.find((t) => t.type === c.type);
      const params = tdef?.params_schema || [];
      const chip = el("div", { class: "condition-chip" });

      const remove = el("button", { class: "chip-remove", title: "Удалить" }, "×");
      remove.addEventListener("click", () => {
        state.pushForm.conditions.splice(idx, 1);
        renderPushConditions();
      });
      chip.append(remove);
      chip.append(el("div", { class: "chip-label", text: tdef?.label || c.type }));

      if (params.length > 0) {
        const paramsBox = el("div", { class: "chip-params" });
        for (const p of params) {
          const inp = el("input", {
            type: "number",
            min: p.min, max: p.max, step: p.step,
            value: c.params[p.name] ?? p.default,
          });
          inp.addEventListener("input", (e) => {
            c.params[p.name] = p.kind === "integer"
              ? parseInt(e.target.value || "0", 10)
              : Number(e.target.value);
          });
          paramsBox.append(el("label", { class: "chip-param" },
            el("span", { text: p.label }), inp));
        }
        chip.append(paramsBox);
      }
      chipsBox.append(chip);
    });
    wrap.append(chipsBox);
    repaintPushTypeSelect();
  }

  function renderPushSubs() {
    const ul = $("pushSubs");
    ul.innerHTML = "";
    if (state.pushSubs.length === 0) {
      ul.append(el("li", null, el("div", { class: "hint", text: "нет активных подписок" })));
      return;
    }
    for (const s of state.pushSubs) {
      const condTexts = (s.conditions || []).map((c) => {
        const tdef = state.pushTypes.find((t) => t.type === c.type);
        const paramsStr = Object.entries(c.params || {})
          .map(([k, v]) => `${k}=${v}`).join(", ");
        return (tdef?.label || c.type) + (paramsStr ? ` (${paramsStr})` : "");
      }).join(" · ");
      ul.append(el("li", null,
        el("div", { style: "flex:1" },
          el("strong", { text: s.name || "(без названия)" }),
          el("div", { class: "meta",
            text: `${s.scope_zone || "вся акватория"} · ${s.scope_species ? SPECIES_LABEL[s.scope_species] : "любой"}` }),
          el("div", { class: "meta", text: condTexts || "без условий" }),
          s.last_notified_for_day
            ? el("div", { class: "meta", text: `последнее уведомление: ${fmtDate(s.last_notified_for_day)}` })
            : null,
        ),
        el("button", {
          class: "danger", text: "Отписаться",
          onClick: () => unsubscribePush(s.id),
        }),
      ));
    }
  }

  function urlBase64ToUint8Array(b64) {
    const padding = "=".repeat((4 - (b64.length % 4)) % 4);
    const norm = (b64 + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(norm);
    const arr = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  async function subscribeToPush() {
    if (!state.pushVapid?.enabled) {
      showOut("pushOut", { status: "vapid_missing" }); return;
    }
    if (state.pushForm.conditions.length === 0) {
      showOut("pushOut", { status: "no_conditions" }); return;
    }
    try {
      const reg = await navigator.serviceWorker.ready;
      const perm = await Notification.requestPermission();
      if (perm !== "granted") {
        showOut("pushOut", { status: "permission_denied", permission: perm }); return;
      }
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(state.pushVapid.public_key),
      });
      const subJson = sub.toJSON();
      const body = {
        endpoint: subJson.endpoint,
        keys: { p256dh: subJson.keys.p256dh, auth: subJson.keys.auth },
        name: state.pushForm.name || null,
        scope_zone: state.pushForm.scope_zone || null,
        scope_species: state.pushForm.scope_species || null,
        conditions: state.pushForm.conditions,
      };
      const saved = await api("/v1/push/subscriptions", {
        method: "POST", body: JSON.stringify(body),
      });
      showOut("pushOut", { status: "subscribed", id: saved.id });
      state.pushSubs = await api("/v1/push/subscriptions/me") || [];
      renderPushSubs();
    } catch (e) {
      showOut("pushOut", e.message || String(e));
    }
  }

  async function unsubscribePush(id) {
    try {
      await api(`/v1/push/subscriptions/${id}`, { method: "DELETE" });
      const reg = await navigator.serviceWorker.ready;
      const cur = await reg.pushManager.getSubscription();
      if (cur) await cur.unsubscribe();
      state.pushSubs = await api("/v1/push/subscriptions/me") || [];
      renderPushSubs();
      showOut("pushOut", { status: "unsubscribed" });
    } catch (e) {
      showOut("pushOut", e.message || String(e));
    }
  }

  async function sendTestPush() {
    try {
      const r = await api("/v1/push/test", { method: "POST" });
      showOut("pushOut", r);
    } catch (e) {
      showOut("pushOut", e.message || String(e));
    }
  }

  // ---- Catch tab -------------------------------------------------------

  function payloadFromCatchForm() {
    return {
      species: $("catchSpecies").value,
      score: Number($("catchScore").value),
      latitude: Number($("catchLat").value),
      longitude: Number($("catchLon").value),
      note: `${$("catchNote").value}-${Date.now()}`,
    };
  }

  // Catch tab UI helpers ------------------------------------------------
  // Pill-button group for species selection: clicking a pill flips the
  // .active class and writes value into the hidden #catchSpecies input.
  function selectCatchSpecies(value) {
    $("catchSpecies").value = value;
    document.querySelectorAll("#catchSpeciesPills .species-pill").forEach((b) => {
      b.classList.toggle("active", b.dataset.species === value);
    });
  }
  // Live update of score-slider: numeric value + filled fish glyphs.
  function updateCatchScoreView() {
    const score = Number($("catchScore").value);
    $("catchScoreValue").textContent = `${score.toFixed(1)} / 5`;
    const host = $("catchScoreFish");
    host.innerHTML = "";
    const filled = Math.max(0, Math.min(5, score));
    for (let i = 1; i <= 5; i++) {
      const portion = Math.max(0, Math.min(1, filled - (i - 1)));
      host.append(el("span", { class: "score-fish-cell", style: `--fill:${portion * 100}%` }, "🐟"));
    }
  }
  // Queue badge near the section heading + sync button visibility.
  function updateCatchQueueBadge() {
    const badge = $("catchQueueBadge");
    if (!badge) return;
    if (state.queue.length === 0) {
      badge.hidden = true;
      $("btnSyncQueue").hidden = true;
    } else {
      badge.hidden = false;
      badge.textContent = `${state.queue.length} в очереди offline`;
      $("btnSyncQueue").hidden = false;
      $("btnSyncQueue").textContent = `↻ Sync очередь (${state.queue.length})`;
    }
  }

  function mapUrlFor(lat, lon) {
    const minLon = lon - 0.05, minLat = lat - 0.03;
    const maxLon = lon + 0.05, maxLat = lat + 0.03;
    return `https://www.openstreetmap.org/export/embed.html?bbox=${minLon}%2C${minLat}%2C${maxLon}%2C${maxLat}&layer=mapnik&marker=${lat}%2C${lon}`;
  }

  function updateMapFromCatch() {
    const lat = Number($("catchLat").value);
    const lon = Number($("catchLon").value);
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      $("mapFrame").src = mapUrlFor(lat, lon);
    }
  }

  function saveQueue() {
    localStorage.setItem("ff_catch_queue", JSON.stringify(state.queue));
    $("queueStatus").textContent = `Очередь: ${state.queue.length}`;
  }

  // ---- Header / online indicator ---------------------------------------

  function updateOnlineBanner() {
    $("offlineBanner").hidden = state.online;
  }

  // ---- Bootstrap -------------------------------------------------------

  function init() {
    // Header
    $("baseUrl").value = state.baseUrl;
    $("authStatus").textContent = state.token ? "вход выполнен" : "гость";
    $("queueStatus").textContent = `Очередь: ${state.queue.length}`;

    // Tab clicks
    document.querySelectorAll(".tab").forEach((b) => {
      b.addEventListener("click", () => switchTab(b.dataset.tab));
    });

    // Forecast controls — grouped zone selector (mirrors web/).
    const zoneSel = $("zone");
    populateZoneSelect(zoneSel);
    // Drop stale zone codes from localStorage (e.g. old upper/middle/lower).
    if (state.zone && !ALL_ZONE_VALUES.includes(state.zone)) {
      state.zone = "";
      localStorage.removeItem("ff_zone");
    }
    zoneSel.value = state.zone;
    zoneSel.addEventListener("change", () => {
      state.zone = zoneSel.value;
      localStorage.setItem("ff_zone", state.zone);
      loadForecast();
    });
    $("species").value = state.species;
    $("species").addEventListener("change", () => {
      state.species = $("species").value;
      localStorage.setItem("ff_species", state.species);
      loadForecast();
    });
    $("btnForecast").addEventListener("click", loadForecast);

    // History
    $("btnHistory").addEventListener("click", loadHistory);
    $("historyDays").addEventListener("change", loadHistory);

    // Header buttons
    $("btnSaveBase").addEventListener("click", () => {
      state.baseUrl = $("baseUrl").value.trim();
      localStorage.setItem("ff_base_url", state.baseUrl);
      showOut("readyOut", { status: "saved", baseUrl: state.baseUrl });
    });
    $("btnCheckReady").addEventListener("click", async () => {
      try { showOut("readyOut", await api("/v1/ready")); }
      catch (e) { showOut("readyOut", e.message); }
    });

    // Auth
    $("btnLogin").addEventListener("click", async () => {
      try {
        const data = await api("/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({ username: $("username").value, password: $("password").value }),
        });
        state.token = data.access_token || "";
        localStorage.setItem("ff_token", state.token);
        $("authStatus").textContent = state.token ? "вход выполнен" : "гость";
        showOut("loginOut", { status: "ok", expires_at: data.expires_at });
      } catch (e) { showOut("loginOut", e.message); }
    });
    $("btnLogout").addEventListener("click", () => {
      state.token = "";
      localStorage.removeItem("ff_token");
      $("authStatus").textContent = "гость";
      showOut("loginOut", { status: "logged_out" });
    });

    // Catch
    // Catch UI: species pills + score slider live updates.
    document.querySelectorAll("#catchSpeciesPills .species-pill").forEach((b) => {
      b.addEventListener("click", () => selectCatchSpecies(b.dataset.species));
    });
    $("catchScore").addEventListener("input", updateCatchScoreView);
    updateCatchScoreView();
    updateCatchQueueBadge();

    $("btnCatch").addEventListener("click", async () => {
      try { showOut("catchOut", await api("/v1/catch", { method: "POST", body: JSON.stringify(payloadFromCatchForm()) })); }
      catch (e) { showOut("catchOut", e.message); }
    });
    $("btnQueueCatch").addEventListener("click", () => {
      state.queue.push(payloadFromCatchForm());
      saveQueue();
      updateCatchQueueBadge();
      showOut("catchOut", { status: "queued", queue_size: state.queue.length });
    });
    $("btnSyncQueue").addEventListener("click", async () => {
      const pending = [...state.queue];
      state.queue = [];
      const results = [];
      for (const item of pending) {
        try {
          const r = await api("/v1/catch", { method: "POST", body: JSON.stringify(item) });
          results.push({ ok: true, id: r.id });
        } catch (e) {
          results.push({ ok: false, error: String(e) });
          state.queue.push(item);
        }
      }
      saveQueue();
      updateCatchQueueBadge();
      showOut("catchOut", { status: "sync_done", results, queue_left: state.queue.length });
    });
    $("btnUseCurrentLocation").addEventListener("click", () => {
      if (!navigator.geolocation) { showOut("mapOut", { status: "geolocation_not_supported" }); return; }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          $("catchLat").value = String(pos.coords.latitude.toFixed(5));
          $("catchLon").value = String(pos.coords.longitude.toFixed(5));
          updateMapFromCatch();
          showOut("mapOut", { status: "ok", source: "gps" });
        },
        (err) => showOut("mapOut", { status: "error", message: err.message }),
        { enableHighAccuracy: true, timeout: 10000 },
      );
    });
    ["catchLat", "catchLon"].forEach((id) => {
      $(id).addEventListener("change", updateMapFromCatch);
    });
    updateMapFromCatch();

    // Push
    $("btnAddCondition").addEventListener("click", () => {
      const t = $("pushNewType").value;
      const tdef = state.pushTypes.find((x) => x.type === t);
      if (!tdef) return;
      const params = {};
      for (const p of tdef.params_schema || []) params[p.name] = p.default;
      state.pushForm.conditions.push({ type: tdef.type, params });
      renderPushConditions();
    });
    $("btnSavePush").addEventListener("click", subscribeToPush);
    $("btnTestPush").addEventListener("click", sendTestPush);
    $("pushZone").addEventListener("change", (e) => { state.pushForm.scope_zone = e.target.value; });
    $("pushSpecies").addEventListener("change", (e) => { state.pushForm.scope_species = e.target.value; });
    $("pushName").addEventListener("input", (e) => { state.pushForm.name = e.target.value; });

    // Consent
    $("btnLoadConsent").addEventListener("click", async () => {
      try {
        const data = await api("/v1/consent/me");
        $("geoAllowed").checked = !!data.geo_allowed;
        $("pushAllowed").checked = !!data.push_allowed;
        $("analyticsAllowed").checked = !!data.analytics_allowed;
        showOut("consentOut", data);
      } catch (e) { showOut("consentOut", e.message); }
    });
    $("btnSaveConsent").addEventListener("click", async () => {
      try {
        const data = await api("/v1/consent", {
          method: "PUT",
          body: JSON.stringify({
            geo_allowed: $("geoAllowed").checked,
            push_allowed: $("pushAllowed").checked,
            analytics_allowed: $("analyticsAllowed").checked,
          }),
        });
        showOut("consentOut", data);
      } catch (e) { showOut("consentOut", e.message); }
    });

    // Privacy
    $("btnExportData").addEventListener("click", async () => {
      try { showOut("dsarOut", await api("/v1/me/data")); }
      catch (e) { showOut("dsarOut", e.message); }
    });
    $("btnDeleteData").addEventListener("click", async () => {
      if (!confirm("Удалить все ваши данные?")) return;
      try { showOut("dsarOut", await api("/v1/me/data", { method: "DELETE" })); }
      catch (e) { showOut("dsarOut", e.message); }
    });
    $("btnLegalInfo").addEventListener("click", async () => {
      try {
        const data = await api("/v1/legal/info");
        showOut("legalOut", data);
        const links = $("legalLinks");
        links.innerHTML = "";
        [
          ["Privacy", data.privacy_url],
          ["Terms", data.terms_url],
          ["Data deletion", data.data_deletion_url],
          ["Cookie tracking", data.cookie_tracking_url],
        ].forEach(([name, href]) => {
          links.append(el("li", null, el("a", { href, target: "_blank", rel: "noreferrer", text: name })));
        });
      } catch (e) { showOut("legalOut", e.message); }
    });

    // Online/offline tracking
    window.addEventListener("online", () => { state.online = true; updateOnlineBanner(); });
    window.addEventListener("offline", () => { state.online = false; updateOnlineBanner(); });
    updateOnlineBanner();

    // SW
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    }

    // Hydrate warnings dismissed-codes (TTL-filtered).
    state.warningsDismissed = loadDismissedWarnings();

    // Water-temp readings tab.
    $("wtMeasuredAt").value = new Date().toISOString().slice(0, 16);
    $("btnWtSubmit").addEventListener("click", submitWaterTempReading);
    $("btnWtGeo").addEventListener("click", useGeoForWaterTemp);
    $("btnWtRefresh").addEventListener("click", loadWaterTempPoints);

    // Initial load
    switchTab(state.activeTab);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
