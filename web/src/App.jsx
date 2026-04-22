import { useMemo, useState } from "react";

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
const tabs = ["dashboard", "forecast", "catch", "consent", "privacy"];

const load = (key, fallback) => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
};

const save = (key, value) => localStorage.setItem(key, JSON.stringify(value));

function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [apiBase, setApiBase] = useState(initApiBase);
  const [token, setToken] = useState(localStorage.getItem("kvh_token") || "");
  const [queue, setQueue] = useState(load("kvh_catch_queue", []));
  const [mapProvider, setMapProvider] = useState(localStorage.getItem("kvh_map_provider") || "yandex");

  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo123");
  const [species, setSpecies] = useState("pike");
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
  const [forecastOut, setForecastOut] = useState("");
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

  const withTab = (tab, label) => (
    <button
      key={tab}
      className={activeTab === tab ? "tab active" : "tab"}
      onClick={() => setActiveTab(tab)}
    >
      {label}
    </button>
  );

  return (
    <main className="app">
      <header className="card">
        <h1>KVH Forecast Web</h1>
        <p className="muted">Full web client for kvh-forecast.ru</p>
        <div className="row">
          <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
          <button onClick={persistBase}>Save API URL</button>
        </div>
        <div className="row">
          <button onClick={async () => setOutput(setReadyOut, await request("/v1/ready"))}>Check Ready</button>
          <button className="secondary" onClick={async () => setOutput(setReadyOut, await request("/v1/health"))}>
            Check Health
          </button>
        </div>
        <pre className="out">{readyOut}</pre>
      </header>

      <section className="card">
        <div className="tabs">
          {withTab("dashboard", "Dashboard")}
          {withTab("forecast", "Forecast")}
          {withTab("catch", "Catch")}
          {withTab("consent", "Consent")}
          {withTab("privacy", "Privacy")}
        </div>
      </section>

      {activeTab === "dashboard" && (
        <section className="card">
          <h2>Login</h2>
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
            <button onClick={login}>Login</button>
            <button className="secondary" onClick={logout}>
              Logout
            </button>
          </div>
          <pre className="out">{loginOut}</pre>
        </section>
      )}

      {activeTab === "forecast" && (
        <section className="card">
          <h2>Forecast</h2>
          <div className="row">
            <select value={species} onChange={(e) => setSpecies(e.target.value)}>
              <option value="pike">pike</option>
              <option value="perch">perch</option>
            </select>
            <button
              onClick={async () => {
                try {
                  setOutput(setForecastOut, await request(`/v1/forecast?species=${species}`));
                } catch (e) {
                  setOutput(setForecastOut, e.message);
                }
              }}
            >
              Load Forecast
            </button>
          </div>
          <pre className="out">{forecastOut}</pre>
        </section>
      )}

      {activeTab === "catch" && (
        <section className="card">
          <h2>Catch + Offline Queue</h2>
          <div className="grid">
            <label>
              Species
              <select
                value={catchForm.species}
                onChange={(e) => setCatchForm((x) => ({ ...x, species: e.target.value }))}
              >
                <option value="pike">pike</option>
                <option value="perch">perch</option>
              </select>
            </label>
            <label>
              Score
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
              Latitude
              <input
                type="number"
                value={catchForm.latitude}
                onChange={(e) => setCatchForm((x) => ({ ...x, latitude: Number(e.target.value) }))}
              />
            </label>
            <label>
              Longitude
              <input
                type="number"
                value={catchForm.longitude}
                onChange={(e) => setCatchForm((x) => ({ ...x, longitude: Number(e.target.value) }))}
              />
            </label>
          </div>
          <label>
            Note
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
              Send Catch
            </button>
            <button className="secondary" onClick={enqueueCatch}>
              Queue Offline
            </button>
            <button className="secondary" onClick={syncQueue}>
              Sync Queue
            </button>
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
              Use Current Location
            </button>
            <button className="secondary" onClick={() => setProvider("yandex")}>
              Yandex Map
            </button>
            <button className="secondary" onClick={() => setProvider("openstreetmap")}>
              OpenStreetMap
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
          {mapLoadError ? (
            <div className="hint">
              {mapLoadError}. Переключено на доступный провайдер.
            </div>
          ) : (
            <div className="hint">Активный провайдер карты: {mapProvider}.</div>
          )}
          <pre className="out">{mapOut || catchOut}</pre>
        </section>
      )}

      {activeTab === "consent" && (
        <section className="card">
          <h2>Consent</h2>
          <div className="checks">
            <label>
              <input
                type="checkbox"
                checked={consent.geo_allowed}
                onChange={(e) => setConsent((x) => ({ ...x, geo_allowed: e.target.checked }))}
              />
              Geo
            </label>
            <label>
              <input
                type="checkbox"
                checked={consent.push_allowed}
                onChange={(e) => setConsent((x) => ({ ...x, push_allowed: e.target.checked }))}
              />
              Push
            </label>
            <label>
              <input
                type="checkbox"
                checked={consent.analytics_allowed}
                onChange={(e) => setConsent((x) => ({ ...x, analytics_allowed: e.target.checked }))}
              />
              Analytics
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
              Load Consent
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
              Save Consent
            </button>
          </div>
          <pre className="out">{consentOut}</pre>
        </section>
      )}

      {activeTab === "privacy" && (
        <section className="card">
          <h2>DSAR + Legal</h2>
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
              Export My Data
            </button>
            <button
              className="danger"
              onClick={async () => {
                if (!confirm("Delete all your data?")) return;
                try {
                  setOutput(setDsarOut, await request("/v1/me/data", { method: "DELETE" }));
                } catch (e) {
                  setOutput(setDsarOut, e.message);
                }
              }}
            >
              Delete My Data
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
              Load Legal Info
            </button>
          </div>
          <pre className="out">{legalOut}</pre>
          {legalInfo && (
            <ul className="links">
              <li>
                <a href={legalInfo.privacy_url} target="_blank" rel="noreferrer">
                  Privacy policy
                </a>
              </li>
              <li>
                <a href={legalInfo.terms_url} target="_blank" rel="noreferrer">
                  Terms of use
                </a>
              </li>
              <li>
                <a href={legalInfo.data_deletion_url} target="_blank" rel="noreferrer">
                  Data deletion
                </a>
              </li>
              <li>
                <a href={legalInfo.cookie_tracking_url} target="_blank" rel="noreferrer">
                  Cookie tracking
                </a>
              </li>
            </ul>
          )}
        </section>
      )}

      <footer className="footer">
        <span>Queue: {queue.length}</span>
        <span>Auth: {token ? "logged in" : "guest"}</span>
      </footer>
    </main>
  );
}

export default App;
