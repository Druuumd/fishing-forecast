const byId = (id) => document.getElementById(id);

const state = {
  token: localStorage.getItem("ff_token") || "",
  baseUrl: localStorage.getItem("ff_base_url") || "http://84.22.146.195:8000",
  queue: JSON.parse(localStorage.getItem("ff_catch_queue") || "[]"),
  pushEnabled: localStorage.getItem("ff_push_enabled") === "true",
};

const out = (id, value) => {
  byId(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
};

const setToken = (token) => {
  state.token = token || "";
  localStorage.setItem("ff_token", state.token);
};

const saveQueue = () => localStorage.setItem("ff_catch_queue", JSON.stringify(state.queue));
const hasAndroidBridge = () => typeof window.AndroidBridge !== "undefined";

const api = async (path, options = {}) => {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(`${state.baseUrl}${path}`, { ...options, headers });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!res.ok) throw new Error(JSON.stringify(data));
  return data;
};

const payloadFromForm = () => ({
  species: byId("catchSpecies").value,
  score: Number(byId("catchScore").value),
  latitude: Number(byId("catchLat").value),
  longitude: Number(byId("catchLon").value),
  note: `${byId("catchNote").value}-${Date.now()}`,
});

byId("baseUrl").value = state.baseUrl;
byId("mapFrame").src = "https://www.openstreetmap.org/export/embed.html?bbox=92.75%2C55.9%2C93.0%2C56.08&layer=mapnik";

byId("btnSaveBase").onclick = () => {
  state.baseUrl = byId("baseUrl").value.trim();
  localStorage.setItem("ff_base_url", state.baseUrl);
  out("readyOut", { status: "saved", baseUrl: state.baseUrl });
};

const mapUrlFor = (lat, lon) => {
  const minLon = lon - 0.05;
  const minLat = lat - 0.03;
  const maxLon = lon + 0.05;
  const maxLat = lat + 0.03;
  return `https://www.openstreetmap.org/export/embed.html?bbox=${minLon}%2C${minLat}%2C${maxLon}%2C${maxLat}&layer=mapnik&marker=${lat}%2C${lon}`;
};

byId("btnCheckReady").onclick = async () => {
  try { out("readyOut", await api("/v1/ready")); } catch (e) { out("readyOut", e.message); }
};

byId("btnLogin").onclick = async () => {
  try {
    const data = await api("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: byId("username").value, password: byId("password").value }),
    });
    setToken(data.access_token);
    out("loginOut", { status: "ok", expires_at: data.expires_at });
  } catch (e) { out("loginOut", e.message); }
};

byId("btnLogout").onclick = () => {
  setToken("");
  out("loginOut", { status: "logged_out" });
};

byId("btnForecast").onclick = async () => {
  try { out("forecastOut", await api(`/v1/forecast?species=${byId("species").value}`)); }
  catch (e) { out("forecastOut", e.message); }
};

byId("btnCatch").onclick = async () => {
  try { out("catchOut", await api("/v1/catch", { method: "POST", body: JSON.stringify(payloadFromForm()) })); }
  catch (e) { out("catchOut", e.message); }
};

byId("btnQueueCatch").onclick = () => {
  state.queue.push(payloadFromForm());
  saveQueue();
  out("catchOut", { status: "queued", queue_size: state.queue.length });
};

byId("btnSyncQueue").onclick = async () => {
  const results = [];
  const pending = [...state.queue];
  state.queue = [];
  saveQueue();
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
  out("catchOut", { status: "sync_done", results, queue_left: state.queue.length });
};

byId("btnLoadConsent").onclick = async () => {
  try {
    const data = await api("/v1/consent/me");
    byId("geoAllowed").checked = !!data.geo_allowed;
    byId("pushAllowed").checked = !!data.push_allowed;
    byId("analyticsAllowed").checked = !!data.analytics_allowed;
    out("consentOut", data);
  } catch (e) { out("consentOut", e.message); }
};

byId("btnSaveConsent").onclick = async () => {
  try {
    const data = await api("/v1/consent", {
      method: "PUT",
      body: JSON.stringify({
        geo_allowed: byId("geoAllowed").checked,
        push_allowed: byId("pushAllowed").checked,
        analytics_allowed: byId("analyticsAllowed").checked,
      }),
    });
    out("consentOut", data);
  } catch (e) { out("consentOut", e.message); }
};

byId("btnExportData").onclick = async () => {
  try { out("dsarOut", await api("/v1/me/data")); }
  catch (e) { out("dsarOut", e.message); }
};

byId("btnDeleteData").onclick = async () => {
  if (!confirm("Delete all your data?")) return;
  try { out("dsarOut", await api("/v1/me/data", { method: "DELETE" })); }
  catch (e) { out("dsarOut", e.message); }
};

byId("btnLegalInfo").onclick = async () => {
  try {
    const data = await api("/v1/legal/info", { headers: {} });
    out("legalOut", data);
    const links = byId("legalLinks");
    links.innerHTML = "";
    [
      ["Privacy", data.privacy_url],
      ["Terms", data.terms_url],
      ["Data deletion", data.data_deletion_url],
      ["Cookie tracking", data.cookie_tracking_url],
    ].forEach(([name, href]) => {
      const li = document.createElement("li");
      li.innerHTML = `<a href="${href}" target="_blank" rel="noreferrer">${name}</a>`;
      links.appendChild(li);
    });
  } catch (e) { out("legalOut", e.message); }
};

byId("btnOpenMap").onclick = () => {
  const lat = Number(byId("catchLat").value);
  const lon = Number(byId("catchLon").value);
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    out("mapOut", { status: "invalid_coords" });
    return;
  }
  byId("mapFrame").src = mapUrlFor(lat, lon);
  out("mapOut", { status: "ok", lat, lon });
};

byId("btnUseCurrentLocation").onclick = () => {
  if (!navigator.geolocation) {
    out("mapOut", { status: "geolocation_not_supported" });
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = Number(pos.coords.latitude.toFixed(5));
      const lon = Number(pos.coords.longitude.toFixed(5));
      byId("catchLat").value = String(lat);
      byId("catchLon").value = String(lon);
      byId("mapFrame").src = mapUrlFor(lat, lon);
      out("mapOut", { status: "ok", lat, lon, source: "gps" });
    },
    (err) => out("mapOut", { status: "error", message: err.message }),
    { enableHighAccuracy: true, timeout: 10000 }
  );
};

byId("btnEnablePush").onclick = async () => {
  if (hasAndroidBridge()) {
    try {
      const granted = !!window.AndroidBridge.requestNotificationPermission();
      state.pushEnabled = granted;
      localStorage.setItem("ff_push_enabled", String(state.pushEnabled));
      if (state.pushEnabled) {
        byId("pushAllowed").checked = true;
        try {
          await api("/v1/consent", {
            method: "PUT",
            body: JSON.stringify({
              geo_allowed: byId("geoAllowed").checked,
              push_allowed: true,
              analytics_allowed: byId("analyticsAllowed").checked,
            }),
          });
        } catch {
          // best-effort consent sync
        }
      }
      out("pushOut", { status: "ok", permission: granted ? "granted" : "pending_or_denied", enabled: state.pushEnabled });
    } catch (e) {
      out("pushOut", String(e));
    }
    return;
  }

  if (!("Notification" in window)) {
    out("pushOut", { status: "notifications_not_supported" });
    return;
  }
  try {
    const perm = await Notification.requestPermission();
    state.pushEnabled = perm === "granted";
    localStorage.setItem("ff_push_enabled", String(state.pushEnabled));
    if (state.pushEnabled) {
      byId("pushAllowed").checked = true;
      try {
        await api("/v1/consent", {
          method: "PUT",
          body: JSON.stringify({
            geo_allowed: byId("geoAllowed").checked,
            push_allowed: true,
            analytics_allowed: byId("analyticsAllowed").checked,
          }),
        });
      } catch {
        // best-effort consent sync
      }
    }
    out("pushOut", { status: "ok", permission: perm, enabled: state.pushEnabled });
  } catch (e) {
    out("pushOut", String(e));
  }
};

byId("btnTestPush").onclick = () => {
  if (hasAndroidBridge()) {
    window.AndroidBridge.sendTestNotification();
    out("pushOut", { status: "sent_native" });
    return;
  }

  if (!state.pushEnabled || Notification.permission !== "granted") {
    out("pushOut", { status: "push_not_enabled" });
    return;
  }
  new Notification("KVH Forecast", {
    body: "Push test successful",
    tag: "kvh-push-test",
  });
  out("pushOut", { status: "sent" });
};

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
