import { useEffect, useMemo, useRef, useState } from "react";

const inferApiDefault = () => {
  const fromEnv = import.meta.env.VITE_API_BASE_URL;
  if (fromEnv) return fromEnv;

  if (typeof window !== "undefined") {
    const { hostname, origin } = window.location;
    if (
      hostname.endsWith("kvh-forecast.ru") ||
      hostname === "84.22.146.195" ||
      hostname === "192.168.0.250"
    ) {
      return origin;
    }
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return "http://192.168.0.250:8000";
    }
  }

  return "https://api.kvh-forecast.ru";
};

const API_DEFAULT = inferApiDefault();
const initApiBase = () => {
  const saved = localStorage.getItem("kvh_api_base");
  if (!saved) return API_DEFAULT;

  if (typeof window !== "undefined") {
    const { hostname, origin } = window.location;
    const isKvhHost = hostname.endsWith("kvh-forecast.ru");
    const isLegacyApi = saved.includes("api.kvh-forecast.ru");
    if (isKvhHost && isLegacyApi) {
      localStorage.setItem("kvh_api_base", origin);
      return origin;
    }
  }

  return saved;
};

const SPECIES_LABEL = { pike: "щука", perch: "окунь", bream: "лещ" };
const SPECIES_COLOR = { pike: "#60a5fa", perch: "#fbbf24", bream: "#f472b6" };
// Bays grouped by thermal/depth archetype so the user can pick by
// fishing intent ("warm shallow spawning bay" vs "deep cool trolling
// water") rather than memorising 13 names.
const ZONE_OPTION_GROUPS = [
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

const ALL_ZONE_VALUES = ZONE_OPTION_GROUPS.flatMap((g) => g.options.map((o) => o.value));

// ---- Leaflet map (lazy CDN load, used by the water-temp tab) ------------
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
let _leafletPromise = null;
function loadLeaflet() {
  if (typeof window === "undefined") return Promise.reject(new Error("ssr"));
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

// Maps a surface temperature (°C) to a color stop covering the reservoir's
// realistic seasonal range from late-winter ice-out (≈0–4°C) to peak summer
// (≈22°C). Returns a hex string usable by both Leaflet and CSS.
function tempColor(t) {
  if (t == null || Number.isNaN(t)) return "#94a3b8";
  if (t < 5) return "#0c4a6e";
  if (t < 10) return "#0ea5e9";
  if (t < 15) return "#22d3ee";
  if (t < 20) return "#84cc16";
  if (t < 25) return "#fb923c";
  return "#dc2626";
}

function WaterTempMap({ zones, points, onPick }) {
  const mountRef = useRef(null);
  const mapRef = useRef(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let layer = null;
    (async () => {
      let L;
      try {
        L = await loadLeaflet();
      } catch (e) {
        if (!cancelled) setError("Не удалось загрузить карту (нет доступа к unpkg.com).");
        return;
      }
      if (cancelled || !mountRef.current) return;
      if (mapRef.current) {
        // Already initialised — just refresh markers below.
      } else {
        // Krasnoyarsk reservoir centred view; zoom shows the entire stretch.
        mapRef.current = L.map(mountRef.current).setView([54.7, 91.7], 8);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '© OpenStreetMap',
          maxZoom: 18,
        }).addTo(mapRef.current);
        if (onPick) {
          mapRef.current.on("click", (e) => {
            onPick(Number(e.latlng.lat.toFixed(5)), Number(e.latlng.lng.toFixed(5)));
          });
        }
      }
      // Build/refresh marker layer.
      if (mapRef.current._kvhMarkerLayer) {
        mapRef.current.removeLayer(mapRef.current._kvhMarkerLayer);
      }
      layer = L.layerGroup();
      for (const z of zones || []) {
        const m = L.circleMarker([z.lat, z.lon], {
          color: "#94a3b8", radius: 6, weight: 2, fillOpacity: 0.25,
        });
        m.bindPopup(`<strong>${z.label}</strong>`);
        layer.addLayer(m);
      }
      for (const p of points || []) {
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
      layer.addTo(mapRef.current);
      mapRef.current._kvhMarkerLayer = layer;
    })();
    return () => { cancelled = true; };
  }, [zones, points, onPick]);

  // Tear down the map only on full unmount.
  useEffect(() => () => {
    if (mapRef.current) {
      try { mapRef.current.remove(); } catch (_) {}
      mapRef.current = null;
    }
  }, []);

  return (
    <div className="map-leaflet-wrap">
      {error && <div className="hint">{error}</div>}
      <div ref={mountRef} className="map-leaflet" />
      <div className="map-legend">
        Цвет точки = температура:
        <span className="map-legend-pill" style={{ background: "#0c4a6e" }}>&lt;5°C</span>
        <span className="map-legend-pill" style={{ background: "#0ea5e9" }}>5–10</span>
        <span className="map-legend-pill" style={{ background: "#22d3ee" }}>10–15</span>
        <span className="map-legend-pill" style={{ background: "#84cc16" }}>15–20</span>
        <span className="map-legend-pill" style={{ background: "#fb923c" }}>20–25</span>
        <span className="map-legend-pill" style={{ background: "#dc2626" }}>≥25</span>
      </div>
    </div>
  );
}

// VAPID public key is base64url; convert to Uint8Array for pushManager.subscribe.
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const b64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

const load = (key, fallback) => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
};

const save = (key, value) => localStorage.setItem(key, JSON.stringify(value));

const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", weekday: "short" });
};

// Friendly date used in card heads: "Сегодня", "Завтра", "Чт 30 апр".
const fmtDateFriendly = (iso) => {
  if (!iso) return "—";
  const target = new Date(`${iso}T12:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const targetDay = new Date(target);
  targetDay.setHours(0, 0, 0, 0);
  const days = Math.round((targetDay - today) / 86400000);
  if (days === 0) return "Сегодня";
  if (days === 1) return "Завтра";
  if (days === -1) return "Вчера";
  return target.toLocaleDateString("ru-RU", { day: "numeric", month: "short", weekday: "short" });
};

const fmtSigned = (v, digits = 2) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(digits)}`;

// Per-score visual classification + headline text. Drives card border,
// verdict line, and emoji icon in the card head.
function scoreVerdict(score) {
  if (score >= 4.3) return { tier: "excellent", label: "Отличный день — пора собираться!", emoji: "🔥" };
  if (score >= 3.5) return { tier: "good", label: "Хороший день для ловли", emoji: "👍" };
  if (score >= 2.5) return { tier: "fair", label: "Средний клёв, шансы есть", emoji: "🤔" };
  if (score >= 1.5) return { tier: "weak", label: "Слабый день, не лучшее время", emoji: "🙁" };
  return { tier: "bad", label: "Сегодня клёва не ждите", emoji: "🚫" };
}

// 5 fish silhouettes filled proportionally to score / 5. Inline SVG so
// no extra image asset needed.
function ScoreFish({ score }) {
  const filled = Math.max(0, Math.min(5, score));
  return (
    <div className="score-fish" title={`${score.toFixed(2)}/5`}>
      {[1, 2, 3, 4, 5].map((i) => {
        const portion = Math.max(0, Math.min(1, filled - (i - 1)));
        return (
          <span key={i} className="score-fish-cell" style={{ ["--fill"]: `${portion * 100}%` }}>
            🐟
          </span>
        );
      })}
    </div>
  );
}

// ---- Generic SVG line chart ---------------------------------------------
function LineChart({ data, series, refLines = [], height = 110, fmt = (v) => v.toFixed(1) }) {
  if (!data || data.length === 0) {
    return <div className="hint">нет данных</div>;
  }
  const W = 600;
  const H = height;
  const padL = 30;
  const padR = 10;
  const padY = 12;

  const allY = [];
  for (const s of series) {
    for (const d of data) {
      const v = d[s.key];
      if (v != null && Number.isFinite(v)) allY.push(v);
    }
  }
  for (const r of refLines) allY.push(r.value);
  if (allY.length === 0) {
    return <div className="hint">нет данных</div>;
  }
  const minY = Math.min(...allY);
  const maxY = Math.max(...allY);
  const rangeY = maxY - minY || 1;

  const stepX = data.length > 1 ? (W - padL - padR) / (data.length - 1) : 0;
  const toX = (i) => padL + i * stepX;
  const toY = (v) => H - padY - ((v - minY) / rangeY) * (H - padY * 2);

  const buildPath = (key) => {
    const cmds = [];
    let started = false;
    data.forEach((d, i) => {
      const v = d[key];
      if (v == null || !Number.isFinite(v)) {
        started = false;
        return;
      }
      cmds.push(`${started ? "L" : "M"} ${toX(i).toFixed(1)} ${toY(v).toFixed(1)}`);
      started = true;
    });
    return cmds.join(" ");
  };

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <text x={4} y={padY + 4} className="label">{fmt(maxY)}</text>
      <text x={4} y={H - padY + 4} className="label">{fmt(minY)}</text>
      <line className="axis" x1={padL} y1={padY} x2={padL} y2={H - padY} />
      <line className="axis" x1={padL} y1={H - padY} x2={W - padR} y2={H - padY} />
      {refLines.map((r, i) => (
        <g key={`ref-${i}`}>
          <line
            className="grid"
            x1={padL}
            x2={W - padR}
            y1={toY(r.value)}
            y2={toY(r.value)}
            stroke={r.color || "#475569"}
          />
          {r.label && (
            <text className="label" x={W - padR - 2} y={toY(r.value) - 2} textAnchor="end" fill={r.color}>
              {r.label}
            </text>
          )}
        </g>
      ))}
      {series.map((s) => (
        <path
          key={s.key}
          className="line"
          stroke={s.color}
          strokeDasharray={s.dashed ? "4 3" : "0"}
          d={buildPath(s.key)}
        />
      ))}
      {series.flatMap((s) =>
        data.map((d, i) => {
          const v = d[s.key];
          if (v == null || !Number.isFinite(v)) return null;
          return (
            <circle
              key={`${s.key}-${i}`}
              className="dot"
              cx={toX(i)}
              cy={toY(v)}
              r={2.4}
              fill={s.color}
            />
          );
        })
      )}
    </svg>
  );
}

// ---- Forecast day card ---------------------------------------------------
function FactorRow({ f }) {
  const isGate = f.name.endsWith("_gate");
  const sign = f.contribution > 0 ? "pos" : f.contribution < 0 ? "neg" : "";
  return (
    <div className={`factor ${isGate ? "gate" : ""}`}>
      <span className="name">{f.name}</span>
      <span className={`value ${sign}`}>{fmtSigned(f.contribution, 2)}</span>
      {f.detail && <span className="detail">{f.detail}</span>}
    </div>
  );
}

function ForecastDayCard({ day, isToday }) {
  const factors = day.factors || [];
  const hasGate = factors.some((f) => f.name.endsWith("_gate"));
  const verdict = scoreVerdict(day.score);
  const cls = ["day-card", `day-${verdict.tier}`, hasGate ? "gated" : "", isToday ? "today" : ""].join(" ").trim();

  // Show only impactful factors by default; keep gates always visible
  // (they're decision-changing) and any factor with |contribution| ≥ 0.15.
  // The "show all" toggle reveals the rest.
  const [showAll, setShowAll] = useState(false);
  const isImportant = (f) => f.name.endsWith("_gate") || Math.abs(f.contribution) >= 0.15;
  const importantFactors = factors.filter(isImportant);
  const restFactors = factors.filter((f) => !isImportant(f));
  const visibleFactors = showAll ? factors : importantFactors;

  return (
    <div className={cls}>
      <div className="day-head">
        <div className="day-head-left">
          <div className="day-date">{fmtDateFriendly(day.date)}</div>
          <div className="day-verdict">
            <span className="verdict-emoji">{verdict.emoji}</span>
            <span>{verdict.label}</span>
          </div>
        </div>
        <div className="day-head-right">
          <ScoreFish score={day.score} />
          <div className="day-score-num">
            {day.score.toFixed(1)}
            <span className="day-conf">{SPECIES_LABEL[day.species]} · {(day.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
      </div>

      <BestHoursStrip day={day} />

      <dl className="day-meta">
        <dt>воздух</dt><dd>{day.air_temp_c.toFixed(1)} °C</dd>
        <dt>вода</dt><dd>{day.water_temp_c.toFixed(1)} °C</dd>
        <dt>давление</dt><dd>{day.pressure_hpa.toFixed(0)} ↦ {day.surface_pressure_hpa != null ? `${day.surface_pressure_hpa.toFixed(0)}` : "—"} hPa</dd>
        <dt>ΔP/24h</dt><dd>{fmtSigned(day.pressure_trend_24h_hpa, 1)} hPa</dd>
        <dt>ветер</dt><dd>{day.wind_speed_m_s.toFixed(1)} м/с · {Math.round(day.wind_direction_deg)}°</dd>
        <dt>облачно</dt><dd>{Math.round(day.cloud_cover_pct)}%</dd>
      </dl>

      <ThermoclineBanner day={day} />

      <div className="factors">
        {visibleFactors.map((f, i) => <FactorRow key={i} f={f} />)}
        {!showAll && restFactors.length > 0 && (
          <button className="factor-expand" onClick={() => setShowAll(true)}>
            + ещё {restFactors.length} {restFactors.length === 1 ? "фактор" : "факторов"}
          </button>
        )}
        {showAll && restFactors.length > 0 && (
          <button className="factor-expand" onClick={() => setShowAll(false)}>
            свернуть
          </button>
        )}
      </div>
    </div>
  );
}

// ---- Best fishing hours strip --------------------------------------------
// Horizontal 24h timeline showing dawn/dusk/lunar peak windows. A
// current-time marker is drawn only on cards whose date matches today
// (otherwise the marker would be meaningless or off-strip).
const KIND_COLOR = {
  dawn: "#fbbf24",        // yellow morning glow
  dusk: "#f97316",        // orange evening glow
  lunar_major: "#a78bfa", // purple lunar
  lunar_minor: "#818cf8",
};

function BestHoursStrip({ day }) {
  const windows = day.best_hours || [];
  if (windows.length === 0) return null;
  // The strip spans the day's local 00:00 → 24:00. Map each window's
  // start/end (UTC datetimes) to fractions of the local day.
  const dayStart = new Date(`${day.date}T00:00:00`);
  const dayEnd = new Date(dayStart.getTime() + 24 * 3600 * 1000);
  const W = 280, H = 26;

  const toX = (iso) => {
    const t = new Date(iso).getTime();
    const frac = Math.max(0, Math.min(1, (t - dayStart.getTime()) / (dayEnd.getTime() - dayStart.getTime())));
    return frac * W;
  };

  const today = new Date();
  const isToday = today.toDateString() === dayStart.toDateString();
  const nowX = isToday ? toX(today.toISOString()) : null;

  return (
    <div className="best-hours">
      <svg viewBox={`0 0 ${W} ${H}`} className="bh-svg" preserveAspectRatio="none">
        {/* Background day line */}
        <line x1="0" x2={W} y1={H / 2} y2={H / 2} stroke="#334155" strokeWidth="1" />
        {/* Hour ticks at 06, 12, 18 */}
        {[6, 12, 18].map((h) => {
          const x = (h / 24) * W;
          return (
            <g key={h}>
              <line x1={x} x2={x} y1={H / 2 - 2} y2={H / 2 + 2} stroke="#475569" strokeWidth="1" />
              <text x={x} y={H - 1} fill="#64748b" fontSize="9" textAnchor="middle">{h}</text>
            </g>
          );
        })}
        {/* Windows */}
        {windows.map((w, i) => {
          const x1 = toX(w.start);
          const x2 = toX(w.end);
          const width = Math.max(2, x2 - x1);
          return (
            <rect
              key={i} x={x1} y={3} width={width} height={H / 2 - 4}
              fill={KIND_COLOR[w.kind] || "#94a3b8"} opacity={0.4 + 0.6 * (w.intensity ?? 1)}
              rx={2}
            >
              <title>{w.label} {new Date(w.start).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}–{new Date(w.end).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</title>
            </rect>
          );
        })}
        {/* Now marker */}
        {nowX != null && (
          <line x1={nowX} x2={nowX} y1={1} y2={H - 4} stroke="#f87171" strokeWidth="1.5" />
        )}
      </svg>
      <div className="bh-legend">
        {windows.map((w, i) => (
          <span key={i} className="bh-pill" style={{ background: `${KIND_COLOR[w.kind] || "#94a3b8"}33`, borderColor: KIND_COLOR[w.kind] || "#94a3b8" }}>
            {w.label}: {new Date(w.start).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}–{new Date(w.end).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---- Thermocline mini-diagram --------------------------------------------
function ThermoclineBanner({ day }) {
  const strength = day.thermocline_strength ?? 0;
  if (!strength || strength < 0.15) return null;
  const depth = day.thermocline_depth_m;
  const rec = day.thermocline_recommended_depth_m;
  // SVG: vertical column showing surface (warm), thermocline, hypolimnion (cold).
  const W = 180, H = 70;
  const totalDepth = Math.max(20, (depth || 10) + 10);
  const padX = 6;
  const colW = 14;
  const colX = padX;
  const labelX = colX + colW + 6;
  const surfaceY = 10;
  const cliffY = surfaceY + ((depth || 0) / totalDepth) * (H - 14);
  const recY = surfaceY + ((rec || 0) / totalDepth) * (H - 14);
  return (
    <div className="thermocline-banner">
      <svg viewBox={`0 0 ${W} ${H}`} className="tc-svg" preserveAspectRatio="none">
        {/* Warm epilimnion */}
        <rect x={colX} y={surfaceY} width={colW} height={cliffY - surfaceY} fill="#fbbf24" opacity="0.6" />
        {/* Cold hypolimnion */}
        <rect x={colX} y={cliffY} width={colW} height={H - cliffY - 4} fill="#0ea5e9" opacity="0.6" />
        {/* Thermocline boundary */}
        <line x1={colX - 2} x2={colX + colW + 2} y1={cliffY} y2={cliffY} stroke="#dc2626" strokeWidth="2" />
        {/* Recommended depth marker */}
        {rec != null && (
          <>
            <line x1={colX} x2={colX + colW + 14} y1={recY} y2={recY} stroke="#16a34a" strokeWidth="1" strokeDasharray="3 3" />
            <text x={colX + colW + 16} y={recY + 3} fill="#4ade80" fontSize="10">→ {rec}м</text>
          </>
        )}
        {/* Labels */}
        <text x={labelX} y={surfaceY + 10} fill="#fde68a" fontSize="10">тёплый верх</text>
        <text x={labelX} y={cliffY - 2} fill="#fca5a5" fontSize="10">термоклин ~{depth}м</text>
        <text x={labelX} y={H - 6} fill="#7dd3fc" fontSize="10">холодный низ</text>
      </svg>
      {day.thermocline_advice && <div className="tc-advice">{day.thermocline_advice}</div>}
    </div>
  );
}

// ---- Loading skeletons ---------------------------------------------------
// Used while forecast / history data is in flight. Same visual structure
// as the real card so the layout doesn't jump when content arrives.
function DayCardSkeleton({ hero = false }) {
  return (
    <div className={`day-card skeleton ${hero ? "today" : ""}`}>
      <div className="day-head">
        <div className="day-head-left">
          <div className="sk-line sk-w-40" style={{ height: hero ? 22 : 16 }} />
          <div className="sk-line sk-w-70" style={{ height: 13, marginTop: 6 }} />
        </div>
        <div className="day-head-right">
          <div className="sk-line sk-w-50" style={{ height: hero ? 22 : 16, width: 90 }} />
          <div className="sk-line sk-w-30" style={{ height: 13 }} />
        </div>
      </div>
      <div className="sk-block" style={{ height: 28 }} />
      <div className="sk-meta-grid">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="sk-meta-row">
            <span className="sk-line sk-w-30" />
            <span className="sk-line sk-w-50" />
          </div>
        ))}
      </div>
      <div className="sk-block" style={{ height: 12 }} />
      <div className="sk-block" style={{ height: 12, width: "70%" }} />
      <div className="sk-block" style={{ height: 12, width: "85%" }} />
    </div>
  );
}

function ForecastSkeleton() {
  return (
    <div className="day-grid">
      <DayCardSkeleton hero />
      <DayCardSkeleton />
      <DayCardSkeleton />
    </div>
  );
}

// ---- History summary: latest vs period-average for each variable -------
function StatCard({ icon, label, value, avg, delta, deltaSuffix, deltaPrecision = 1, higherIsBetter }) {
  const eps = deltaPrecision === 0 ? 0.5 : 0.05;
  const direction = delta > eps ? "up" : delta < -eps ? "down" : "flat";
  let deltaClass = "neutral";
  if (higherIsBetter === true) {
    deltaClass = direction === "up" ? "good" : direction === "down" ? "bad" : "neutral";
  } else if (higherIsBetter === false) {
    deltaClass = direction === "up" ? "bad" : direction === "down" ? "good" : "neutral";
  } else {
    deltaClass = direction === "flat" ? "neutral" : "info";
  }
  const arrow = direction === "up" ? "↑" : direction === "down" ? "↓" : "→";
  const sign = delta >= 0 ? "+" : "";
  return (
    <div className="stat-card">
      <div className="stat-card-head">
        <span className="stat-icon">{icon}</span>
        <span className="stat-label">{label}</span>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-footer">
        <span className="stat-avg">{avg}</span>
        <span className={`stat-delta stat-delta-${deltaClass}`}>
          {arrow} {sign}{delta.toFixed(deltaPrecision)}{deltaSuffix}
        </span>
      </div>
    </div>
  );
}

function HistorySummary({ waterHistory, weatherHistory }) {
  if (waterHistory.length === 0 && weatherHistory.length === 0) return null;
  const cards = [];

  if (waterHistory.length > 0) {
    const last = waterHistory[waterHistory.length - 1].level_m;
    const avg = waterHistory.reduce((s, p) => s + p.level_m, 0) / waterHistory.length;
    cards.push({
      icon: "💧", label: "Уровень воды",
      value: `${last.toFixed(2)} м`,
      avg: `средн. ${avg.toFixed(2)} м`,
      delta: last - avg, deltaSuffix: " м", deltaPrecision: 2,
      higherIsBetter: null,
    });
  }
  if (weatherHistory.length > 0) {
    const last = weatherHistory[weatherHistory.length - 1];
    const avg = (key) => weatherHistory.reduce((s, p) => s + (p[key] || 0), 0) / weatherHistory.length;
    cards.push({
      icon: "🌊", label: "Tw воды",
      value: `${last.water_temp_c.toFixed(1)}°C`,
      avg: `средн. ${avg("water_temp_c").toFixed(1)}°C`,
      delta: last.water_temp_c - avg("water_temp_c"), deltaSuffix: "°C",
      higherIsBetter: null,
    });
    cards.push({
      icon: "🌡", label: "Воздух",
      value: `${last.air_temp_c.toFixed(1)}°C`,
      avg: `средн. ${avg("air_temp_c").toFixed(1)}°C`,
      delta: last.air_temp_c - avg("air_temp_c"), deltaSuffix: "°C",
      higherIsBetter: null,
    });
    cards.push({
      icon: "📊", label: "Давление",
      value: `${last.pressure_hpa.toFixed(0)} hPa`,
      avg: `средн. ${avg("pressure_hpa").toFixed(0)}`,
      delta: last.pressure_hpa - avg("pressure_hpa"),
      deltaSuffix: " hPa", deltaPrecision: 0,
      higherIsBetter: null,
    });
    cards.push({
      icon: "💨", label: "Ветер",
      value: `${last.wind_speed_m_s.toFixed(1)} м/с`,
      avg: `средн. ${avg("wind_speed_m_s").toFixed(1)}`,
      delta: last.wind_speed_m_s - avg("wind_speed_m_s"),
      deltaSuffix: " м/с",
      higherIsBetter: false,  // less wind = better for fishing
    });
  }
  return (
    <div className="history-summary-cards">
      {cards.map((c, i) => <StatCard key={i} {...c} />)}
    </div>
  );
}

function ChartSkeleton({ label }) {
  return (
    <div className="chart-block">
      {label && <h3>{label}</h3>}
      <div className="sk-chart" />
    </div>
  );
}

// ---- Warnings panel ------------------------------------------------------
const SEVERITY_LABEL = { danger: "❗", warn: "⚠️", info: "ℹ️" };
const SEVERITY_ORDER = { danger: 0, warn: 1, info: 2 };

function WarningsPanel({ items, onDismiss, dismissed }) {
  if (!items || items.length === 0) return null;
  const visible = items
    .filter((w) => !dismissed.has(w.code))
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  if (visible.length === 0) return null;
  return (
    <div className="warnings-panel">
      {visible.map((w) => (
        <div key={w.code} className={`warning warning-${w.severity}`}>
          <div className="warning-head">
            <span className="warning-icon">{SEVERITY_LABEL[w.severity] || ""}</span>
            <strong className="warning-title">{w.title}</strong>
            <button className="warning-dismiss" title="Скрыть" onClick={() => onDismiss(w.code)}>×</button>
          </div>
          <div className="warning-body">{w.body}</div>
          {(w.valid_from || w.valid_to) && (
            <div className="warning-when">
              {w.valid_from && <>с {fmtDate(w.valid_from)}</>}
              {w.valid_to && w.valid_to !== w.valid_from && <> · по {fmtDate(w.valid_to)}</>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---- Water level banner --------------------------------------------------
function WaterBanner({ res }) {
  if (!res || res.water_level_m == null) return null;
  const trend = res.water_level_trend_7d_m || 0;
  const trendClass = trend > 0.05 ? "up" : trend < -0.05 ? "down" : "";
  const src = res.water_level_source || "";
  const isAuto = /^(allrivers|rushydro|favr|auto)/i.test(src);
  const isClimatology = src === "climatology";
  const sourceLabel = isAuto
    ? `${src} (auto)`
    : isClimatology
    ? "climatology (модель)"
    : src
    ? `${src} (manual)`
    : "—";
  return (
    <div className="water-banner">
      <div className="stat">
        <span className="k">Уровень водохранилища</span>
        <span className="v">{res.water_level_m.toFixed(2)} м</span>
      </div>
      <div className="stat">
        <span className="k">Δ за 7 дней</span>
        <span className={`v ${trendClass}`}>{fmtSigned(trend, 2)} м</span>
      </div>
      <div className="stat">
        <span className="k">источник</span>
        <span className="v">{sourceLabel}{res.water_level_is_fresh ? "" : " · стар."}</span>
      </div>
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState("forecast");
  const [apiBase, setApiBase] = useState(initApiBase);
  const [token, setToken] = useState(localStorage.getItem("kvh_token") || "");
  const [queue, setQueue] = useState(load("kvh_catch_queue", []));
  const [mapProvider, setMapProvider] = useState(localStorage.getItem("kvh_map_provider") || "yandex");

  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo123");
  const [species, setSpecies] = useState("pike");
  const [zone, setZone] = useState(() => {
    const saved = localStorage.getItem("kvh_zone") || "";
    if (!ALL_ZONE_VALUES.includes(saved)) {
      localStorage.removeItem("kvh_zone");
      return "";
    }
    return saved;
  });
  const [forecastRes, setForecastRes] = useState(null);
  const [forecastErr, setForecastErr] = useState("");
  const [forecastLoading, setForecastLoading] = useState(false);

  // Warnings (adverse-condition banner). Dismissed set is persisted with
  // a 24h TTL so the user isn't badgered repeatedly about the same code.
  const [warnings, setWarnings] = useState([]);
  const [warningsDismissed, setWarningsDismissed] = useState(() => {
    try {
      const raw = JSON.parse(localStorage.getItem("kvh_warnings_dismissed") || "{}");
      const now = Date.now();
      const valid = Object.fromEntries(
        Object.entries(raw).filter(([_, ts]) => now - ts < 24 * 3600 * 1000)
      );
      return new Set(Object.keys(valid));
    } catch {
      return new Set();
    }
  });
  const dismissWarning = (code) => {
    setWarningsDismissed((prev) => {
      const next = new Set(prev);
      next.add(code);
      const obj = {};
      for (const c of next) obj[c] = Date.now();
      localStorage.setItem("kvh_warnings_dismissed", JSON.stringify(obj));
      return next;
    });
  };

  // History state
  const [waterHistory, setWaterHistory] = useState([]);
  const [weatherHistory, setWeatherHistory] = useState([]);
  const [historyDays, setHistoryDays] = useState(30);
  const [historyErr, setHistoryErr] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [myCatches, setMyCatches] = useState([]);
  const [catchHistoryErr, setCatchHistoryErr] = useState("");

  // Water-temp readings (user-submitted thermal profiles).
  const [wtForm, setWtForm] = useState(() => ({
    measured_at: new Date().toISOString().slice(0, 16),
    latitude: 55.0,
    longitude: 91.7,
    surface_temp_c: 12.0,
    thermocline_depth_m: "",
    below_thermocline_temp_c: "",
    instrument: "",
    note: "",
  }));
  const [wtFieldErrors, setWtFieldErrors] = useState({});
  const [wtOut, setWtOut] = useState("");
  const [wtPoints, setWtPoints] = useState([]);
  const [zoneCenters, setZoneCenters] = useState([]);

  const onMapPick = (lat, lon) => setWtForm((x) => ({ ...x, latitude: lat, longitude: lon }));

  const submitWaterTempReading = async () => {
    setWtFieldErrors({});
    setWtOut("");
    const body = {
      measured_at: new Date(wtForm.measured_at).toISOString(),
      latitude: Number(wtForm.latitude),
      longitude: Number(wtForm.longitude),
      surface_temp_c: Number(wtForm.surface_temp_c),
      thermocline_depth_m: wtForm.thermocline_depth_m === "" ? null : Number(wtForm.thermocline_depth_m),
      below_thermocline_temp_c: wtForm.below_thermocline_temp_c === "" ? null : Number(wtForm.below_thermocline_temp_c),
      instrument: wtForm.instrument || null,
      note: wtForm.note || null,
    };
    try {
      const r = await request("/v1/water-temp-readings", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setOutput(setWtOut, { status: "saved", id: r.id, zone: r.zone });
      loadWaterTempPoints();
    } catch (e) {
      try {
        const parsed = JSON.parse(e.message);
        if (parsed?.details?.field_errors) {
          setWtFieldErrors(parsed.details.field_errors);
        }
        setOutput(setWtOut, parsed);
      } catch {
        setOutput(setWtOut, e.message);
      }
    }
  };
  const loadWaterTempPoints = async () => {
    try {
      const [pointsRes, zonesRes] = await Promise.all([
        request("/v1/water-temp-readings"),
        zoneCenters.length === 0 ? request("/v1/zones/centers") : Promise.resolve(null),
      ]);
      setWtPoints(pointsRes.points || []);
      if (zonesRes) setZoneCenters(zonesRes.zones || []);
    } catch (e) {
      setOutput(setWtOut, e.message);
    }
  };
  const useGeoForWaterTemp = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (p) => setWtForm((x) => ({
        ...x,
        latitude: Number(p.coords.latitude.toFixed(5)),
        longitude: Number(p.coords.longitude.toFixed(5)),
      })),
      () => {},
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };

  // Online/offline indicator. SW serves last-cached forecast when offline,
  // so the app keeps working — but we surface a visible banner so the
  // user knows the data may be stale.
  const [isOnline, setIsOnline] = useState(
    typeof navigator === "undefined" ? true : navigator.onLine
  );

  // Push-notifications state
  const [pushSupported] = useState(
    typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window
  );
  const [pushVapid, setPushVapid] = useState(null);
  const [pushSubs, setPushSubs] = useState([]);
  const [pushOut, setPushOut] = useState("");
  const [pushTypes, setPushTypes] = useState([]);
  const [pushForm, setPushForm] = useState({
    name: "",
    scope_zone: "",
    scope_species: "",
    conditions: [{ type: "score_min", params: { min: 3.5 } }],
  });
  const [pushNewType, setPushNewType] = useState("score_min");

  const [catchForm, setCatchForm] = useState({
    species: "perch",
    score: 4.1,
    latitude: 55.99,
    longitude: 92.88,
    note: "web-beta",
  });
  const [consent, setConsent] = useState({
    geo_allowed: false,
    push_allowed: false,
    analytics_allowed: false,
  });

  const [readyOut, setReadyOut] = useState("");
  const [loginOut, setLoginOut] = useState("");
  const [catchOut, setCatchOut] = useState("");
  const [consentOut, setConsentOut] = useState("");
  const [dsarOut, setDsarOut] = useState("");
  const [legalOut, setLegalOut] = useState("");
  const [legalInfo, setLegalInfo] = useState(null);
  const [mapOut, setMapOut] = useState("");
  const [mapLoadError, setMapLoadError] = useState("");

  const mapUrl = useMemo(() => {
    const lat = Number(catchForm.latitude);
    const lon = Number(catchForm.longitude);
    if (mapProvider === "openstreetmap") {
      const minLon = lon - 0.05;
      const minLat = lat - 0.03;
      const maxLon = lon + 0.05;
      const maxLat = lat + 0.03;
      return `https://www.openstreetmap.org/export/embed.html?bbox=${minLon}%2C${minLat}%2C${maxLon}%2C${maxLat}&layer=mapnik&marker=${lat}%2C${lon}`;
    }
    const yandexLon = encodeURIComponent(String(lon));
    const yandexLat = encodeURIComponent(String(lat));
    return `https://yandex.ru/map-widget/v1/?ll=${yandexLon}%2C${yandexLat}&z=11&pt=${yandexLon},${yandexLat},pm2rdm`;
  }, [catchForm.latitude, catchForm.longitude, mapProvider]);

  const setProvider = (provider) => {
    setMapProvider(provider);
    localStorage.setItem("kvh_map_provider", provider);
    setMapLoadError("");
    setOutput(setMapOut, { status: "map_provider_changed", provider });
  };

  const setOutput = (setter, payload) => {
    if (typeof payload === "string") {
      setter(payload);
      return;
    }
    setter(JSON.stringify(payload, null, 2));
  };

  const request = async (path, options = {}) => {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    let res;
    let requestBase = apiBase;
    try {
      res = await fetch(`${requestBase}${path}`, { ...options, headers });
    } catch {
      if (typeof window !== "undefined") {
        const { hostname, origin } = window.location;
        const canFallback = hostname.endsWith("kvh-forecast.ru") && requestBase.includes("api.kvh-forecast.ru");
        if (canFallback) {
          try {
            requestBase = origin;
            setApiBase(origin);
            localStorage.setItem("kvh_api_base", origin);
            res = await fetch(`${requestBase}${path}`, { ...options, headers });
          } catch {
            // handled below
          }
        }
      }
    }
    if (!res) {
      throw new Error(
        JSON.stringify({
          status: 0,
          code: "NETWORK_ERROR",
          message: `Failed to fetch ${requestBase}${path}`,
          retryable: true,
          request_id: null,
          details: { api_base: requestBase },
        })
      );
    }
    const text = await res.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { raw: text };
    }
    if (!res.ok) {
      const error = body?.error || {};
      throw new Error(
        JSON.stringify({
          status: res.status,
          code: error.code || "HTTP_ERROR",
          message: error.message || "request failed",
          retryable: !!error.retryable,
          request_id: error.request_id || null,
          details: error.details || null,
        })
      );
    }
    return body;
  };

  const persistBase = () => {
    localStorage.setItem("kvh_api_base", apiBase);
    setOutput(setReadyOut, { status: "saved", apiBase });
  };

  const login = async () => {
    try {
      const result = await request("/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setToken(result.access_token || "");
      localStorage.setItem("kvh_token", result.access_token || "");
      setOutput(setLoginOut, { status: "ok", expires_at: result.expires_at });
    } catch (e) {
      setOutput(setLoginOut, e.message);
    }
  };

  const logout = () => {
    setToken("");
    localStorage.removeItem("kvh_token");
    setOutput(setLoginOut, { status: "logged_out" });
  };

  const enqueueCatch = () => {
    const item = { ...catchForm, note: `${catchForm.note}-${Date.now()}` };
    const next = [...queue, item];
    setQueue(next);
    save("kvh_catch_queue", next);
    setOutput(setCatchOut, { status: "queued", queue_size: next.length });
  };

  const syncQueue = async () => {
    const pending = [...queue];
    const nextQueue = [];
    const result = [];
    for (const item of pending) {
      try {
        const sent = await request("/v1/catch", {
          method: "POST",
          body: JSON.stringify(item),
        });
        result.push({ ok: true, id: sent.id });
      } catch (e) {
        result.push({ ok: false, error: String(e) });
        nextQueue.push(item);
      }
    }
    setQueue(nextQueue);
    save("kvh_catch_queue", nextQueue);
    setOutput(setCatchOut, { status: "sync_done", result, queue_left: nextQueue.length });
  };

  const loadForecast = async () => {
    setForecastLoading(true);
    setForecastErr("");
    try {
      const params = new URLSearchParams({ species });
      if (zone) params.set("zone", zone);
      // Warnings depend only on zone, not species, so we can fetch them
      // in parallel with the per-species forecast.
      const wParams = new URLSearchParams();
      if (zone) wParams.set("zone", zone);
      const [r, w] = await Promise.all([
        request(`/v1/forecast?${params.toString()}`),
        request(`/v1/warnings${wParams.toString() ? "?" + wParams.toString() : ""}`).catch(() => ({ warnings: [] })),
      ]);
      setForecastRes(r);
      setWarnings(w.warnings || []);
    } catch (e) {
      setForecastErr(e.message);
      setForecastRes(null);
    } finally {
      setForecastLoading(false);
    }
  };

  const loadHistory = async () => {
    setHistoryLoading(true);
    setHistoryErr("");
    try {
      const [wl, w] = await Promise.all([
        request(`/v1/water-level/history?days=${historyDays}`),
        request(`/v1/weather/history?days=${Math.min(historyDays, 60)}`),
      ]);
      setWaterHistory(wl.points || []);
      setWeatherHistory(w.points || []);
    } catch (e) {
      setHistoryErr(e.message);
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadMyCatches = async () => {
    setCatchHistoryErr("");
    try {
      const r = await request("/v1/me/data");
      setMyCatches(r.catches || []);
    } catch (e) {
      setCatchHistoryErr(e.message);
    }
  };

  // Auto-load forecast on tab open / species or zone change
  useEffect(() => {
    if (activeTab === "forecast") loadForecast();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, species, zone]);

  const setZonePersist = (z) => {
    setZone(z);
    if (z) localStorage.setItem("kvh_zone", z);
    else localStorage.removeItem("kvh_zone");
  };

  // Auto-load history when entering tab
  useEffect(() => {
    if (activeTab === "history") {
      loadHistory();
      if (token) loadMyCatches();
    }
    if (activeTab === "water_temp") loadWaterTempPoints();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, historyDays]);

  // Register service worker once at app load.
  useEffect(() => {
    if (!pushSupported) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, [pushSupported]);

  // Track online/offline transitions for the banner.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onOnline = () => setIsOnline(true);
    const onOffline = () => setIsOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  // Load push state when entering Notifications tab
  useEffect(() => {
    if (activeTab !== "push") return;
    (async () => {
      try {
        const v = await request("/v1/push/vapid-public-key");
        setPushVapid(v);
      } catch (e) {
        setPushOut(e.message);
      }
      try {
        const t = await request("/v1/push/condition-types");
        setPushTypes(t.types || []);
      } catch (e) {
        // non-fatal
      }
      if (token) {
        try {
          const subs = await request("/v1/push/subscriptions/me");
          setPushSubs(subs || []);
        } catch (e) {
          setPushOut(e.message);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, token]);

  const addCondition = () => {
    const tdef = pushTypes.find((t) => t.type === pushNewType);
    if (!tdef) return;
    const params = {};
    for (const p of tdef.params_schema || []) params[p.name] = p.default;
    setPushForm((x) => ({
      ...x,
      conditions: [...x.conditions, { type: tdef.type, params }],
    }));
  };

  const updateConditionParam = (idx, paramName, value) => {
    setPushForm((x) => {
      const next = [...x.conditions];
      next[idx] = { ...next[idx], params: { ...next[idx].params, [paramName]: value } };
      return { ...x, conditions: next };
    });
  };

  const removeCondition = (idx) => {
    setPushForm((x) => ({
      ...x,
      conditions: x.conditions.filter((_, i) => i !== idx),
    }));
  };

  const subscribeToPush = async () => {
    if (!pushSupported) {
      setOutput(setPushOut, { status: "unsupported" });
      return;
    }
    if (!pushVapid?.enabled || !pushVapid?.public_key) {
      setOutput(setPushOut, { status: "vapid_missing" });
      return;
    }
    try {
      const reg = await navigator.serviceWorker.ready;
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setOutput(setPushOut, { status: "permission_denied", permission });
        return;
      }
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(pushVapid.public_key),
      });
      const subJson = sub.toJSON();
      const body = {
        endpoint: subJson.endpoint,
        keys: { p256dh: subJson.keys.p256dh, auth: subJson.keys.auth },
        name: pushForm.name || null,
        scope_zone: pushForm.scope_zone || null,
        scope_species: pushForm.scope_species || null,
        conditions: pushForm.conditions,
      };
      const saved = await request("/v1/push/subscriptions", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setOutput(setPushOut, { status: "subscribed", id: saved.id });
      const subs = await request("/v1/push/subscriptions/me");
      setPushSubs(subs || []);
    } catch (e) {
      setOutput(setPushOut, e.message || String(e));
    }
  };

  const unsubscribePush = async (id) => {
    try {
      await request(`/v1/push/subscriptions/${id}`, { method: "DELETE" });
      const reg = await navigator.serviceWorker.ready;
      const cur = await reg.pushManager.getSubscription();
      if (cur) await cur.unsubscribe();
      const subs = await request("/v1/push/subscriptions/me");
      setPushSubs(subs || []);
      setOutput(setPushOut, { status: "unsubscribed" });
    } catch (e) {
      setOutput(setPushOut, e.message || String(e));
    }
  };

  const sendTestPush = async () => {
    try {
      const r = await request("/v1/push/test", { method: "POST" });
      setOutput(setPushOut, r);
    } catch (e) {
      setOutput(setPushOut, e.message || String(e));
    }
  };

  const withTab = (tab, label) => (
    <button
      key={tab}
      className={activeTab === tab ? "tab active" : "tab"}
      onClick={() => setActiveTab(tab)}
    >
      {label}
    </button>
  );

  // Derived stats for History summary
  const historySummary = useMemo(() => {
    if (waterHistory.length === 0) return null;
    const first = waterHistory[0].level_m;
    const last = waterHistory[waterHistory.length - 1].level_m;
    const min = Math.min(...waterHistory.map((p) => p.level_m));
    const max = Math.max(...waterHistory.map((p) => p.level_m));
    return { first, last, min, max, delta: last - first, n: waterHistory.length };
  }, [waterHistory]);

  return (
    <main className="app">
      <header className="app-header">
        <h1>🎣 KVH Forecast</h1>
        <p className="muted">Прогноз клёва на Красноярском водохранилище</p>
        {!isOnline && (
          <div className="offline-banner">
            📵 Нет сети. Показан последний загруженный прогноз — данные могут быть устаревшими.
          </div>
        )}
      </header>

      <section className="card">
        <div className="tabs">
          {withTab("forecast", "🎣 Прогноз")}
          {withTab("history", "📈 История")}
          {withTab("catch", "🐟 Улов")}
          {withTab("water_temp", "🌡 Замеры")}
          {withTab("push", "🔔 Уведомления")}
          {withTab("dashboard", "👤 Профиль")}
          {withTab("settings", "⚙️ Настройки")}
          {withTab("consent", "✅ Согласия")}
          {withTab("privacy", "🛡 Приватность")}
        </div>
      </section>

      {activeTab === "forecast" && (
        <section className="card">
          <h2>Прогноз на 7 дней</h2>
          <div className="row">
            <select value={species} onChange={(e) => setSpecies(e.target.value)}>
              <option value="pike">щука</option>
              <option value="perch">окунь</option>
              <option value="bream">лещ</option>
            </select>
            <select value={zone} onChange={(e) => setZonePersist(e.target.value)}>
              {ZONE_OPTION_GROUPS.map((group, gi) =>
                group.options.length === 1 && !group.options[0].value ? (
                  <option key={gi} value="">{group.options[0].label}</option>
                ) : (
                  <optgroup key={gi} label={group.label}>
                    {group.options.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </optgroup>
                )
              )}
            </select>
            <button onClick={loadForecast} disabled={forecastLoading}>
              {forecastLoading ? "Загрузка…" : "Обновить"}
            </button>
          </div>
          {forecastRes?.zone_label && (
            <div className="hint">зона: <strong>{forecastRes.zone_label}</strong></div>
          )}
          {forecastErr && <pre className="out">{forecastErr}</pre>}
          {forecastLoading && !forecastRes && <ForecastSkeleton />}
          {forecastRes && (
            <>
              <WarningsPanel
                items={warnings}
                onDismiss={dismissWarning}
                dismissed={warningsDismissed}
              />
              <WaterBanner res={forecastRes} />
              <div className="day-grid">
                {forecastRes.days.map((d, i) => (
                  <ForecastDayCard key={i} day={d} isToday={i === 0} />
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {activeTab === "history" && (
        <section className="card">
          <h2>История условий</h2>
          <div className="row">
            <select value={historyDays} onChange={(e) => setHistoryDays(Number(e.target.value))}>
              <option value={14}>14 дней</option>
              <option value={30}>30 дней</option>
              <option value={60}>60 дней</option>
            </select>
            <button onClick={loadHistory} disabled={historyLoading}>
              {historyLoading ? "Загрузка…" : "Обновить"}
            </button>
          </div>
          {historyErr && <pre className="out">{historyErr}</pre>}
          {historyLoading && waterHistory.length === 0 && weatherHistory.length === 0 && (
            <>
              <div className="history-summary">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="stat skeleton">
                    <div className="sk-line sk-w-50" />
                    <div className="sk-line sk-w-70" style={{ height: 16, marginTop: 4 }} />
                  </div>
                ))}
              </div>
              <ChartSkeleton label="Уровень воды (м)" />
              <ChartSkeleton label="Температура воды и воздуха (°C)" />
              <ChartSkeleton label="Давление (hPa)" />
              <ChartSkeleton label="Ветер (м/с) и осадки (мм)" />
            </>
          )}
          <HistorySummary waterHistory={waterHistory} weatherHistory={weatherHistory} />

          <div className="chart-block">
            <h3>Уровень воды (м)</h3>
            <LineChart
              data={waterHistory}
              series={[{ key: "level_m", color: "#38bdf8", label: "уровень" }]}
              refLines={[
                { value: 243, color: "#16a34a", label: "НПУ 243" },
                { value: 225, color: "#dc2626", label: "УМО 225" },
              ]}
              fmt={(v) => `${v.toFixed(0)} м`}
            />
          </div>

          <div className="chart-block">
            <h3>Температура воды и воздуха (°C)</h3>
            <LineChart
              data={weatherHistory}
              series={[
                { key: "water_temp_c", color: "#0ea5e9", label: "вода" },
                { key: "air_temp_c", color: "#fbbf24", dashed: true, label: "воздух" },
              ]}
              refLines={[{ value: 0, color: "#475569" }]}
              fmt={(v) => `${v.toFixed(0)}°`}
            />
            <div className="chart-legend">
              <span><span className="swatch" style={{ background: "#0ea5e9" }} />вода</span>
              <span><span className="swatch" style={{ background: "#fbbf24" }} />воздух</span>
            </div>
          </div>

          <div className="chart-block">
            <h3>Давление (hPa)</h3>
            <LineChart
              data={weatherHistory}
              series={[
                { key: "pressure_hpa", color: "#a78bfa", label: "MSL" },
                { key: "surface_pressure_hpa", color: "#34d399", dashed: true, label: "surface" },
              ]}
              fmt={(v) => `${v.toFixed(0)}`}
            />
            <div className="chart-legend">
              <span><span className="swatch" style={{ background: "#a78bfa" }} />MSL (приведённое к ур. моря)</span>
              <span><span className="swatch" style={{ background: "#34d399" }} />surface (на воде, h=234м)</span>
            </div>
          </div>

          <div className="chart-block">
            <h3>Ветер (м/с) и осадки (мм)</h3>
            <LineChart
              data={weatherHistory}
              series={[
                { key: "wind_speed_m_s", color: "#f87171", label: "ветер" },
                { key: "precipitation_mm", color: "#60a5fa", dashed: true, label: "осадки" },
              ]}
              fmt={(v) => v.toFixed(1)}
            />
            <div className="chart-legend">
              <span><span className="swatch" style={{ background: "#f87171" }} />ветер, м/с</span>
              <span><span className="swatch" style={{ background: "#60a5fa" }} />осадки, мм</span>
            </div>
          </div>

          <h3 style={{ marginTop: 18 }}>Мои уловы</h3>
          {!token && <div className="hint">Войдите в «Профиль», чтобы увидеть свои записи.</div>}
          {token && catchHistoryErr && <pre className="out">{catchHistoryErr}</pre>}
          {token && myCatches.length === 0 && !catchHistoryErr && (
            <div className="hint">пока нет записей</div>
          )}
          {token && myCatches.length > 0 && (
            <ul className="catch-list">
              {myCatches.map((c) => (
                <li key={c.id}>
                  <div>
                    <strong>{SPECIES_LABEL[c.species] || c.species}</strong>
                    {" "}· оценка <strong>{c.score.toFixed(1)}</strong>
                    <div className="meta">
                      {fmtDate(c.caught_at)} · {c.latitude.toFixed(3)},{c.longitude.toFixed(3)}
                      {" · "}P {c.linked_pressure_hpa.toFixed(0)} hPa · Tw {c.linked_water_temp_c.toFixed(1)}°C
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "water_temp" && (
        <section className="card">
          <h2>Замеры температуры воды</h2>
          <div className="hint">
            Делитесь замерами с эхолота или термометра — они помогают модели
            точнее предсказывать клёв и однажды обучат предсказание термоклина.
            Координаты сохраняются с привязкой к ближайшему заливу.
            {!token && <> <strong>Войдите в «Профиль»</strong>, чтобы отправлять.</>}
          </div>
          <div className="grid">
            <label className={wtFieldErrors.measured_at ? "input-bad" : ""}>
              Время замера
              <input
                type="datetime-local"
                value={wtForm.measured_at}
                onChange={(e) => setWtForm((x) => ({ ...x, measured_at: e.target.value }))}
              />
              {wtFieldErrors.measured_at && <div className="field-error">{wtFieldErrors.measured_at}</div>}
            </label>
            <label className={wtFieldErrors.surface_temp_c ? "input-bad" : ""}>
              Tw поверхность, °C
              <input
                type="number" step="0.1" min="0" max="30"
                value={wtForm.surface_temp_c}
                onChange={(e) => setWtForm((x) => ({ ...x, surface_temp_c: e.target.value }))}
              />
              {wtFieldErrors.surface_temp_c && <div className="field-error">{wtFieldErrors.surface_temp_c}</div>}
            </label>
            <label className={wtFieldErrors.latitude ? "input-bad" : ""}>
              Широта
              <input
                type="number" step="0.0001"
                value={wtForm.latitude}
                onChange={(e) => setWtForm((x) => ({ ...x, latitude: e.target.value }))}
              />
              {wtFieldErrors.latitude && <div className="field-error">{wtFieldErrors.latitude}</div>}
            </label>
            <label className={wtFieldErrors.longitude ? "input-bad" : ""}>
              Долгота
              <input
                type="number" step="0.0001"
                value={wtForm.longitude}
                onChange={(e) => setWtForm((x) => ({ ...x, longitude: e.target.value }))}
              />
              {wtFieldErrors.longitude && <div className="field-error">{wtFieldErrors.longitude}</div>}
            </label>
            <label className={wtFieldErrors.thermocline_depth_m ? "input-bad" : ""}>
              Глубина термоклина, м (опц.)
              <input
                type="number" step="0.5" min="1" max="60"
                value={wtForm.thermocline_depth_m}
                onChange={(e) => setWtForm((x) => ({ ...x, thermocline_depth_m: e.target.value }))}
              />
              {wtFieldErrors.thermocline_depth_m && <div className="field-error">{wtFieldErrors.thermocline_depth_m}</div>}
            </label>
            <label className={wtFieldErrors.below_thermocline_temp_c ? "input-bad" : ""}>
              Tw под термоклином, °C (опц.)
              <input
                type="number" step="0.1" min="1" max="10"
                value={wtForm.below_thermocline_temp_c}
                onChange={(e) => setWtForm((x) => ({ ...x, below_thermocline_temp_c: e.target.value }))}
              />
              {wtFieldErrors.below_thermocline_temp_c && <div className="field-error">{wtFieldErrors.below_thermocline_temp_c}</div>}
            </label>
          </div>
          <WaterTempMap zones={zoneCenters} points={wtPoints} onPick={onMapPick} />
          <div className="hint">Кликните по карте, чтобы подставить координаты.</div>
          <label>
            Прибор / способ
            <input
              placeholder="эхолот, термометр, GPSmap…"
              value={wtForm.instrument}
              onChange={(e) => setWtForm((x) => ({ ...x, instrument: e.target.value }))}
            />
          </label>
          <label>
            Заметка
            <input
              value={wtForm.note}
              onChange={(e) => setWtForm((x) => ({ ...x, note: e.target.value }))}
            />
          </label>
          <div className="row">
            <button onClick={submitWaterTempReading} disabled={!token}>Отправить</button>
            <button className="secondary" onClick={useGeoForWaterTemp}>📍 GPS</button>
            <button className="secondary" onClick={loadWaterTempPoints}>Обновить список</button>
          </div>
          {wtOut && <pre className="out">{wtOut}</pre>}
          <h3 style={{ marginTop: 14 }}>Недавние замеры (всех пользователей)</h3>
          {wtPoints.length === 0 ? (
            <div className="hint">пока нет замеров</div>
          ) : (
            <ul className="catch-list">
              {wtPoints.map((p) => (
                <li key={p.id}>
                  <div>
                    <strong>{p.zone || "?"}</strong>
                    {" · поверхность "}<strong>{p.surface_temp_c.toFixed(1)}°C</strong>
                    {p.thermocline_depth_m != null && (
                      <> · термоклин {p.thermocline_depth_m}м · ниже {p.below_thermocline_temp_c}°C</>
                    )}
                    <div className="meta">
                      {fmtDate(p.measured_at)} · {p.latitude.toFixed(3)},{p.longitude.toFixed(3)}
                      {p.instrument && ` · ${p.instrument}`}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {activeTab === "push" && (
        <section className="card">
          <h2>Push-уведомления — конструктор</h2>
          {!pushSupported && (
            <div className="hint">Браузер не поддерживает Web Push.</div>
          )}
          {pushSupported && pushVapid && !pushVapid.enabled && (
            <div className="hint">Сервер не настроен для push (нет VAPID ключей).</div>
          )}
          {pushSupported && pushVapid?.enabled && (
            <>
              <div className="hint">
                Соберите свой набор условий — уведомление придёт только для того дня
                в прогнозе, который удовлетворяет ВСЕМ выбранным условиям.
                Дубликаты исключены: один и тот же предсказанный день отправляется один раз.
              </div>
              {!token && <div className="hint">Сначала войдите в «Профиль».</div>}
              {token && (
                <>
                  <div className="grid">
                    <label>
                      Название (необязательно)
                      <input
                        value={pushForm.name}
                        onChange={(e) => setPushForm((x) => ({ ...x, name: e.target.value }))}
                        placeholder="например: лещ на Сыде в выходные"
                      />
                    </label>
                    <label>
                      Зона
                      <select
                        value={pushForm.scope_zone}
                        onChange={(e) => setPushForm((x) => ({ ...x, scope_zone: e.target.value }))}
                      >
                        {ZONE_OPTION_GROUPS.map((group, gi) =>
                          group.options.length === 1 && !group.options[0].value ? (
                            <option key={gi} value="">{group.options[0].label}</option>
                          ) : (
                            <optgroup key={gi} label={group.label}>
                              {group.options.map((o) => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                              ))}
                            </optgroup>
                          )
                        )}
                      </select>
                    </label>
                    <label>
                      Вид
                      <select
                        value={pushForm.scope_species}
                        onChange={(e) => setPushForm((x) => ({ ...x, scope_species: e.target.value }))}
                      >
                        <option value="">любой</option>
                        <option value="pike">щука</option>
                        <option value="perch">окунь</option>
                        <option value="bream">лещ</option>
                      </select>
                    </label>
                  </div>

                  <h3 style={{ marginTop: 14 }}>Условия</h3>
                  {pushForm.conditions.length === 0 && (
                    <div className="hint">Добавьте хотя бы одно условие — ниже dropdown.</div>
                  )}
                  <div className="condition-chips">
                    {pushForm.conditions.map((c, idx) => {
                      const tdef = pushTypes.find((t) => t.type === c.type);
                      const params = tdef?.params_schema || [];
                      return (
                        <div key={idx} className="condition-chip">
                          <button
                            className="chip-remove"
                            title="Удалить"
                            onClick={() => removeCondition(idx)}
                          >×</button>
                          <div className="chip-label">{tdef?.label || c.type}</div>
                          {params.length > 0 && (
                            <div className="chip-params">
                              {params.map((p) => (
                                <label key={p.name} className="chip-param">
                                  <span>{p.label}</span>
                                  <input
                                    type="number"
                                    min={p.min}
                                    max={p.max}
                                    step={p.step}
                                    value={c.params[p.name] ?? p.default}
                                    onChange={(e) =>
                                      updateConditionParam(
                                        idx,
                                        p.name,
                                        p.kind === "integer"
                                          ? parseInt(e.target.value || "0", 10)
                                          : Number(e.target.value)
                                      )
                                    }
                                  />
                                </label>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <div className="row" style={{ marginTop: 10 }}>
                    <select value={pushNewType} onChange={(e) => setPushNewType(e.target.value)}>
                      {pushTypes
                        .filter((t) => !pushForm.conditions.some((c) => c.type === t.type))
                        .map((t) => (
                          <option key={t.type} value={t.type}>{t.label}</option>
                        ))}
                    </select>
                    <button className="secondary" onClick={addCondition}>+ Добавить условие</button>
                  </div>

                  <div className="row" style={{ marginTop: 12 }}>
                    <button onClick={subscribeToPush} disabled={pushForm.conditions.length === 0}>
                      Сохранить подписку
                    </button>
                    <button className="secondary" onClick={sendTestPush}>Отправить тест</button>
                  </div>
                </>
              )}

              {pushSubs.length > 0 && (
                <>
                  <h3 style={{ marginTop: 18 }}>Активные подписки</h3>
                  <ul className="catch-list">
                    {pushSubs.map((s) => (
                      <li key={s.id}>
                        <div style={{ flex: 1 }}>
                          <strong>{s.name || "(без названия)"}</strong>
                          <div className="meta">
                            {s.scope_zone || "вся акватория"} ·{" "}
                            {s.scope_species ? SPECIES_LABEL[s.scope_species] || s.scope_species : "любой вид"}
                          </div>
                          <div className="meta">
                            {s.conditions.map((c, i) => {
                              const tdef = pushTypes.find((t) => t.type === c.type);
                              const paramsStr = Object.entries(c.params || {})
                                .map(([k, v]) => `${k}=${v}`)
                                .join(", ");
                              return (
                                <span key={i}>
                                  {i > 0 && " · "}
                                  {(tdef?.label || c.type)}
                                  {paramsStr ? ` (${paramsStr})` : ""}
                                </span>
                              );
                            })}
                          </div>
                          <div className="meta">
                            создана {fmtDate(s.created_at)}
                            {s.last_notified_for_day && ` · последнее уведомление за ${fmtDate(s.last_notified_for_day)}`}
                          </div>
                        </div>
                        <button className="danger" onClick={() => unsubscribePush(s.id)}>
                          Отписаться
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <pre className="out">{pushOut}</pre>
            </>
          )}
        </section>
      )}

      {activeTab === "settings" && (
        <section className="card">
          <h2>⚙️ Настройки</h2>
          <label>
            URL API
            <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
          </label>
          <div className="row">
            <button onClick={persistBase}>Сохранить URL API</button>
            <button
              className="secondary"
              onClick={async () => {
                try {
                  setOutput(setReadyOut, await request("/v1/ready"));
                } catch (e) {
                  setOutput(setReadyOut, e.message);
                }
              }}
            >
              Проверить /ready
            </button>
          </div>
          <pre className="out">{readyOut}</pre>
          <div className="hint">
            Карта: текущий провайдер — <strong>{mapProvider}</strong>.
          </div>
          <div className="row">
            <button className="secondary" onClick={() => setProvider("yandex")}>Yandex Maps</button>
            <button className="secondary" onClick={() => setProvider("openstreetmap")}>OpenStreetMap</button>
          </div>
          <pre className="out">{mapOut}</pre>
        </section>
      )}

      {activeTab === "dashboard" && (
        <section className="card">
          <h2>👤 Профиль</h2>
          <div className="row">
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              type="password"
            />
          </div>
          <div className="row">
            <button onClick={login}>Войти</button>
            <button className="secondary" onClick={logout}>Выйти</button>
          </div>
          <pre className="out">{loginOut}</pre>
        </section>
      )}

      {activeTab === "catch" && (
        <section className="card">
          <h2>🐟 Записать улов</h2>
          <div className="hint">
            После отправки модель связывает улов с погодой того дня и
            использует пары (условия → результат) для retrain.
            {queue.length > 0 && (
              <span className="queue-badge">{queue.length} в очереди offline</span>
            )}
          </div>

          {/* Species: pill-buttons with fish icons */}
          <div className="species-pills">
            {[
              { value: "pike", label: "Щука", icon: "🐊" },
              { value: "perch", label: "Окунь", icon: "🐠" },
              { value: "bream", label: "Лещ", icon: "🐟" },
            ].map((s) => (
              <button
                key={s.value}
                className={`species-pill ${catchForm.species === s.value ? "active" : ""}`}
                onClick={() => setCatchForm((x) => ({ ...x, species: s.value }))}
              >
                <span className="species-pill-icon">{s.icon}</span>
                <span>{s.label}</span>
              </button>
            ))}
          </div>

          {/* Score: slider + fish visualization */}
          <label className="score-slider-label">
            <div className="score-slider-row">
              <span className="muted">Оценка клёва</span>
              <span className="score-slider-value">{catchForm.score.toFixed(1)} / 5</span>
            </div>
            <input
              className="score-slider"
              type="range"
              min="0"
              max="5"
              step="0.1"
              value={catchForm.score}
              onChange={(e) => setCatchForm((x) => ({ ...x, score: Number(e.target.value) }))}
            />
            <ScoreFish score={catchForm.score} />
          </label>

          <div className="grid">
            <label>
              Широта
              <input
                type="number" step="0.0001"
                value={catchForm.latitude}
                onChange={(e) => setCatchForm((x) => ({ ...x, latitude: Number(e.target.value) }))}
              />
            </label>
            <label>
              Долгота
              <input
                type="number" step="0.0001"
                value={catchForm.longitude}
                onChange={(e) => setCatchForm((x) => ({ ...x, longitude: Number(e.target.value) }))}
              />
            </label>
          </div>
          <label>
            Заметка
            <input
              placeholder="приманка, время, условия…"
              value={catchForm.note}
              onChange={(e) => setCatchForm((x) => ({ ...x, note: e.target.value }))}
            />
          </label>

          <div className="row">
            <button
              onClick={async () => {
                try {
                  setOutput(
                    setCatchOut,
                    await request("/v1/catch", {
                      method: "POST",
                      body: JSON.stringify({ ...catchForm, note: `${catchForm.note}-${Date.now()}` }),
                    })
                  );
                } catch (e) {
                  setOutput(setCatchOut, e.message);
                }
              }}
            >
              Отправить
            </button>
            <button className="secondary" onClick={enqueueCatch}>В очередь (offline)</button>
            {queue.length > 0 && (
              <button className="secondary" onClick={syncQueue}>↻ Sync очередь ({queue.length})</button>
            )}
          </div>
          <div className="row">
            <button
              className="secondary"
              onClick={() => {
                if (!navigator.geolocation) {
                  setOutput(setMapOut, { status: "geolocation_not_supported" });
                  return;
                }
                navigator.geolocation.getCurrentPosition(
                  (p) => {
                    setCatchForm((x) => ({
                      ...x,
                      latitude: Number(p.coords.latitude.toFixed(5)),
                      longitude: Number(p.coords.longitude.toFixed(5)),
                    }));
                    setMapLoadError("");
                    setOutput(setMapOut, { status: "ok", source: "gps" });
                  },
                  (error) => setOutput(setMapOut, { status: "error", message: error.message }),
                  { enableHighAccuracy: true, timeout: 10000 }
                );
              }}
            >
              📍 GPS
            </button>
          </div>

          <iframe
            title="catch-map"
            className="map"
            src={mapUrl}
            onError={() => {
              const message = `Map provider unreachable: ${mapProvider}`;
              setMapLoadError(message);
              if (mapProvider === "openstreetmap") {
                setProvider("yandex");
              }
            }}
          />
          {mapLoadError && (
            <div className="hint">{mapLoadError}. Переключено на доступный провайдер.</div>
          )}

          <details className="debug-fold">
            <summary>Подробности (debug)</summary>
            <pre className="out">{mapOut || catchOut}</pre>
          </details>
        </section>
      )}

      {activeTab === "consent" && (
        <section className="card">
          <h2>Согласия</h2>
          <div className="checks">
            <label>
              <input
                type="checkbox"
                checked={consent.geo_allowed}
                onChange={(e) => setConsent((x) => ({ ...x, geo_allowed: e.target.checked }))}
              />
              Геолокация
            </label>
            <label>
              <input
                type="checkbox"
                checked={consent.push_allowed}
                onChange={(e) => setConsent((x) => ({ ...x, push_allowed: e.target.checked }))}
              />
              Push-уведомления
            </label>
            <label>
              <input
                type="checkbox"
                checked={consent.analytics_allowed}
                onChange={(e) => setConsent((x) => ({ ...x, analytics_allowed: e.target.checked }))}
              />
              Аналитика
            </label>
          </div>
          <div className="row">
            <button
              className="secondary"
              onClick={async () => {
                try {
                  const data = await request("/v1/consent/me");
                  setConsent(data);
                  setOutput(setConsentOut, data);
                } catch (e) {
                  setOutput(setConsentOut, e.message);
                }
              }}
            >
              Загрузить
            </button>
            <button
              onClick={async () => {
                try {
                  setOutput(
                    setConsentOut,
                    await request("/v1/consent", {
                      method: "PUT",
                      body: JSON.stringify(consent),
                    })
                  );
                } catch (e) {
                  setOutput(setConsentOut, e.message);
                }
              }}
            >
              Сохранить
            </button>
          </div>
          <pre className="out">{consentOut}</pre>
        </section>
      )}

      {activeTab === "privacy" && (
        <section className="card">
          <h2>Данные и приватность</h2>
          <div className="row">
            <button
              onClick={async () => {
                try {
                  setOutput(setDsarOut, await request("/v1/me/data"));
                } catch (e) {
                  setOutput(setDsarOut, e.message);
                }
              }}
            >
              Экспорт моих данных
            </button>
            <button
              className="danger"
              onClick={async () => {
                if (!confirm("Удалить все данные?")) return;
                try {
                  setOutput(setDsarOut, await request("/v1/me/data", { method: "DELETE" }));
                } catch (e) {
                  setOutput(setDsarOut, e.message);
                }
              }}
            >
              Удалить мои данные
            </button>
          </div>
          <pre className="out">{dsarOut}</pre>
          <div className="row">
            <button
              className="secondary"
              onClick={async () => {
                try {
                  const info = await request("/v1/legal/info");
                  setLegalInfo(info);
                  setOutput(setLegalOut, info);
                } catch (e) {
                  setOutput(setLegalOut, e.message);
                }
              }}
            >
              Юридическая инфо
            </button>
          </div>
          <pre className="out">{legalOut}</pre>
          {legalInfo && (
            <ul className="links">
              <li><a href={legalInfo.privacy_url} target="_blank" rel="noreferrer">Privacy policy</a></li>
              <li><a href={legalInfo.terms_url} target="_blank" rel="noreferrer">Terms of use</a></li>
              <li><a href={legalInfo.data_deletion_url} target="_blank" rel="noreferrer">Data deletion</a></li>
              <li><a href={legalInfo.cookie_tracking_url} target="_blank" rel="noreferrer">Cookie tracking</a></li>
            </ul>
          )}
        </section>
      )}

      <footer className="footer">
        <span>Очередь: {queue.length}</span>
        <span>Auth: {token ? "вход выполнен" : "гость"}</span>
      </footer>
    </main>
  );
}

export default App;
