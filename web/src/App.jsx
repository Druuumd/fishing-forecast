import { useEffect, useMemo, useState } from "react";

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

const fmtSigned = (v, digits = 2) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(digits)}`;

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

function ForecastDayCard({ day }) {
  const hasGate = (day.factors || []).some((f) => f.name.endsWith("_gate"));
  const hot = day.score >= 3.5;
  const cold = day.score <= 1.8;
  const cls = ["day-card", hot ? "hot" : "", cold ? "cold" : "", hasGate ? "gated" : ""].join(" ").trim();
  const widthPct = Math.max(0, Math.min(100, (day.score / 5) * 100));
  return (
    <div className={cls}>
      <div className="day-head">
        <span className="day-date">{fmtDate(day.date)}</span>
        <span className="day-score">{day.score.toFixed(2)}</span>
      </div>
      <div className="score-bar"><span style={{ width: `${widthPct}%` }} /></div>
      <div className="day-conf">уверенность {(day.confidence * 100).toFixed(0)}% · {SPECIES_LABEL[day.species]}</div>
      <dl className="day-meta">
        <dt>воздух</dt><dd>{day.air_temp_c.toFixed(1)} °C</dd>
        <dt>вода</dt><dd>{day.water_temp_c.toFixed(1)} °C</dd>
        <dt>P (MSL)</dt><dd>{day.pressure_hpa.toFixed(0)} hPa</dd>
        <dt>P (surface)</dt><dd>{day.surface_pressure_hpa != null ? `${day.surface_pressure_hpa.toFixed(0)} hPa` : "—"}</dd>
        <dt>ΔP/24h</dt><dd>{fmtSigned(day.pressure_trend_24h_hpa, 1)} hPa</dd>
        <dt>ветер</dt><dd>{day.wind_speed_m_s.toFixed(1)} м/с {Math.round(day.wind_direction_deg)}°</dd>
        <dt>облачность</dt><dd>{Math.round(day.cloud_cover_pct)}%</dd>
        <dt>осадки</dt><dd>{day.precipitation_mm.toFixed(1)} мм</dd>
      </dl>
      <ThermoclineBanner day={day} />
      <div className="factors">
        {(day.factors || []).map((f, i) => <FactorRow key={i} f={f} />)}
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
      const r = await request("/v1/water-temp-readings");
      setWtPoints(r.points || []);
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
      <header className="card">
        <h1>KVH Forecast</h1>
        <p className="muted">Прогноз клёва на Красноярском водохранилище</p>
        {!isOnline && (
          <div className="offline-banner">
            📵 Нет сети. Показан последний загруженный прогноз — данные могут быть устаревшими.
          </div>
        )}
        <div className="row">
          <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
          <button onClick={persistBase}>Сохранить URL API</button>
          <button className="secondary" onClick={async () => setOutput(setReadyOut, await request("/v1/ready"))}>
            Проверить /ready
          </button>
        </div>
        {readyOut && <pre className="out">{readyOut}</pre>}
      </header>

      <section className="card">
        <div className="tabs">
          {withTab("forecast", "Прогноз")}
          {withTab("history", "История")}
          {withTab("catch", "Улов")}
          {withTab("water_temp", "Замеры воды")}
          {withTab("push", "Уведомления")}
          {withTab("dashboard", "Профиль")}
          {withTab("consent", "Согласия")}
          {withTab("privacy", "Приватность")}
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
                  <ForecastDayCard key={i} day={d} />
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
          {historySummary && (
            <div className="history-summary">
              <div className="stat"><div className="k">записей</div><div className="v">{historySummary.n}</div></div>
              <div className="stat"><div className="k">текущий</div><div className="v">{historySummary.last.toFixed(2)} м</div></div>
              <div className="stat"><div className="k">Δ за период</div><div className="v">{fmtSigned(historySummary.delta, 2)} м</div></div>
              <div className="stat"><div className="k">мин / макс</div><div className="v">{historySummary.min.toFixed(2)} / {historySummary.max.toFixed(2)}</div></div>
            </div>
          )}

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
                    <div className="hint">пока ни одного условия — добавьте хотя бы одно ниже.</div>
                  )}
                  <ul className="catch-list">
                    {pushForm.conditions.map((c, idx) => {
                      const tdef = pushTypes.find((t) => t.type === c.type);
                      return (
                        <li key={idx}>
                          <div style={{ flex: 1 }}>
                            <strong>{tdef?.label || c.type}</strong>
                            {(tdef?.params_schema || []).length > 0 && (
                              <div className="row" style={{ marginTop: 4 }}>
                                {tdef.params_schema.map((p) => (
                                  <label key={p.name}>
                                    {p.label}
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
                          <button className="danger" onClick={() => removeCondition(idx)}>
                            Удалить
                          </button>
                        </li>
                      );
                    })}
                  </ul>

                  <div className="row">
                    <select value={pushNewType} onChange={(e) => setPushNewType(e.target.value)}>
                      {pushTypes.map((t) => (
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

      {activeTab === "dashboard" && (
        <section className="card">
          <h2>Профиль</h2>
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
          <h2>Записать улов</h2>
          <div className="grid">
            <label>
              Вид
              <select
                value={catchForm.species}
                onChange={(e) => setCatchForm((x) => ({ ...x, species: e.target.value }))}
              >
                <option value="pike">щука</option>
                <option value="perch">окунь</option>
                <option value="bream">лещ</option>
              </select>
            </label>
            <label>
              Оценка (0–5)
              <input
                type="number"
                min="0"
                max="5"
                step="0.1"
                value={catchForm.score}
                onChange={(e) => setCatchForm((x) => ({ ...x, score: Number(e.target.value) }))}
              />
            </label>
            <label>
              Широта
              <input
                type="number"
                value={catchForm.latitude}
                onChange={(e) => setCatchForm((x) => ({ ...x, latitude: Number(e.target.value) }))}
              />
            </label>
            <label>
              Долгота
              <input
                type="number"
                value={catchForm.longitude}
                onChange={(e) => setCatchForm((x) => ({ ...x, longitude: Number(e.target.value) }))}
              />
            </label>
          </div>
          <label>
            Заметка
            <input value={catchForm.note} onChange={(e) => setCatchForm((x) => ({ ...x, note: e.target.value }))} />
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
            <button className="secondary" onClick={syncQueue}>Sync очередь</button>
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
              Где я (GPS)
            </button>
            <button className="secondary" onClick={() => setProvider("yandex")}>Yandex</button>
            <button className="secondary" onClick={() => setProvider("openstreetmap")}>OpenStreetMap</button>
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
          {mapLoadError ? (
            <div className="hint">{mapLoadError}. Переключено на доступный провайдер.</div>
          ) : (
            <div className="hint">Активный провайдер карты: {mapProvider}.</div>
          )}
          <pre className="out">{mapOut || catchOut}</pre>
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
