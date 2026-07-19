/* ResetX Web UI */
"use strict";

const $ = (id) => document.getElementById(id);
let api = null;

// ─────────────────────────── bootstrap ───────────────────────────
window.addEventListener("pywebviewready", () => {
  api = window.pywebview.api;
  init();
});
// Fallback por si el evento ya disparó
setTimeout(() => {
  if (!api && window.pywebview) { api = window.pywebview.api; init(); }
}, 800);

let booted = false;
async function init() {
  if (booted || !api) return;
  booted = true;

  const v = await api.get_version();
  $("version").textContent = "v" + v.version;

  initNav();
  initDashboard();
  initOptimizer();
  initHub();
  initMas();
  checkAdmin();
  checkUpdates();
}

// ─────────────────────────── navegación ───────────────────────────
function initNav() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".view").forEach((vw) => vw.classList.remove("active"));
      btn.classList.add("active");
      $("view-" + btn.dataset.view).classList.add("active");
    });
  });
}

async function checkAdmin() {
  const r = await api.is_admin();
  const pill = $("admin-pill");
  pill.classList.add(r.admin ? "yes" : "no");
  $("admin-text").textContent = r.admin ? "Administrador" : "Sin permisos admin";
  if (!r.admin) {
    const btn = $("btn-admin");
    btn.hidden = false;
    btn.addEventListener("click", () => api.restart_admin());
  }
}

// ─────────────────────────── dashboard ───────────────────────────
const sparkData = [];

function initDashboard() {
  loadSpecs();
  loadPowerPlans();
  tickMetrics();
  setInterval(tickMetrics, 2000);
}

async function loadSpecs() {
  const r = await api.get_specs();
  if (!r.ok) return;
  const s = r.specs;
  $("spec-cpu").textContent = s.CPU || "—";
  $("spec-gpu").textContent = s.GPU || "—";
  $("spec-ram").textContent = s.RAM_GB && s.RAM_GB !== "N/A" ? s.RAM_GB + " GB · " + (s.RAM_Type || "RAM") : "—";
  if ((s.CPU || "").includes("Cargando")) setTimeout(loadSpecs, 3000);
}

async function loadPowerPlans() {
  const r = await api.get_power_plans();
  if (!r.ok) return;
  const wrap = $("power-plans");
  wrap.innerHTML = "";
  r.plans.forEach((name) => {
    const b = document.createElement("button");
    b.className = "plan-btn" + (name === r.active ? " active" : "");
    b.textContent = name;
    b.addEventListener("click", async () => {
      await api.set_power_plan(name);
      setTimeout(loadPowerPlans, 600);
    });
    wrap.appendChild(b);
  });
}

function setGauge(id, pct, color) {
  const c = $(id);
  const circ = 263.9;
  c.style.strokeDashoffset = circ - (circ * Math.min(100, Math.max(0, pct))) / 100;
  c.style.stroke = color || "#4c9aff";
}

function setBar(id, pct, text) {
  $(id).style.width = Math.min(100, Math.max(0, pct)) + "%";
  $(id + "-v").textContent = text;
}

async function tickMetrics() {
  if (!document.getElementById("view-dashboard").classList.contains("active")) return;
  let m;
  try { m = await api.get_metrics(); } catch { return; }
  if (!m || !m.ok) return;

  // Salud
  const score = m.score;
  $("health-score").textContent = score;
  $("health-label").textContent = score >= 85 ? "Excelente" : score >= 65 ? "Bueno" : score >= 45 ? "Regular" : "Necesita atención";
  const ring = $("health-ring");
  const circHealth = 213.6;
  ring.style.strokeDashoffset = circHealth - (circHealth * score) / 100;
  ring.style.stroke = score >= 85 ? "#34d399" : score >= 65 ? "#4c9aff" : score >= 45 ? "#fbbf24" : "#f87171";
  $("uptime").textContent = "Uptime: " + m.uptime;

  const live = m.live || {};
  const gpuPct = live.gpu_percent || 0;

  // Gauges
  setGauge("g-cpu", m.cpu, "#4c9aff"); $("g-cpu-v").textContent = Math.round(m.cpu) + "%";
  setGauge("g-gpu", gpuPct, "#34d399"); $("g-gpu-v").textContent = Math.round(gpuPct) + "%";
  setGauge("g-ram", m.ram.percent, "#a78bfa"); $("g-ram-v").textContent = Math.round(m.ram.percent) + "%";
  setGauge("g-disk", m.disk.percent, "#fb923c"); $("g-disk-v").textContent = Math.round(m.disk.percent) + "%";

  // Specs live
  $("spec-cpu-live").textContent = (live.cpu_ghz ? live.cpu_ghz.toFixed(2) + " GHz · " : "") + Math.round(m.cpu) + "% uso" + (live.cpu_temp_c ? " · " + Math.round(live.cpu_temp_c) + "°C" : "");
  $("spec-gpu-live").textContent = Math.round(gpuPct) + "% uso" + (live.gpu_temp_c ? " · " + Math.round(live.gpu_temp_c) + "°C" : "") + (live.gpu_power_w ? " · " + Math.round(live.gpu_power_w) + " W" : "");
  $("spec-ram-live").textContent = m.ram.used_gb + " / " + m.ram.total_gb + " GB en uso";

  // Telemetría
  setBar("t-cpu", m.cpu, Math.round(m.cpu) + "%" + (live.cpu_ghz ? " · " + live.cpu_ghz.toFixed(1) + "GHz" : ""));
  setBar("t-gpu", gpuPct, Math.round(gpuPct) + "%");
  const net = (live.net_dl_mbs || 0) + (live.net_ul_mbs || 0);
  setBar("t-net", Math.min(100, net * 8), "↓" + (live.net_dl_mbs || 0).toFixed(1) + " ↑" + (live.net_ul_mbs || 0).toFixed(1) + " MB/s");
  const dsk = (live.disk_read_mbs || 0) + (live.disk_write_mbs || 0);
  setBar("t-disk", Math.min(100, dsk / 3), dsk.toFixed(1) + " MB/s");
  setBar("t-pwr", Math.min(100, (live.total_power_w || 0) / 5), live.total_power_w ? Math.round(live.total_power_w) + " W" : "—");
  setBar("t-tcpu", live.cpu_temp_c || 0, live.cpu_temp_c ? Math.round(live.cpu_temp_c) + "°C" : "—");
  setBar("t-tgpu", live.gpu_temp_c || 0, live.gpu_temp_c ? Math.round(live.gpu_temp_c) + "°C" : "—");

  // Sparkline CPU
  sparkData.push(m.cpu);
  if (sparkData.length > 90) sparkData.shift();
  drawSpark();

  // Discos
  renderDrives(m.drives || {});
}

function drawSpark() {
  const cv = $("spark");
  const ctx = cv.getContext("2d");
  const w = (cv.width = cv.clientWidth * 2);
  const h = (cv.height = 120);
  ctx.clearRect(0, 0, w, h);
  if (sparkData.length < 2) return;
  const step = w / 89;
  ctx.beginPath();
  sparkData.forEach((v, i) => {
    const x = i * step;
    const y = h - 6 - (v / 100) * (h - 12);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#4c9aff";
  ctx.lineWidth = 2.5;
  ctx.lineJoin = "round";
  ctx.stroke();
  ctx.lineTo((sparkData.length - 1) * step, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "rgba(76,154,255,.25)");
  grad.addColorStop(1, "rgba(76,154,255,0)");
  ctx.fillStyle = grad;
  ctx.fill();
}

let lastDrivesJson = "";
function renderDrives(drives) {
  const json = JSON.stringify(drives);
  if (json === lastDrivesJson) return;
  lastDrivesJson = json;
  const wrap = $("drives");
  wrap.innerHTML = "";
  Object.entries(drives).sort(([a], [b]) => a.localeCompare(b)).forEach(([letter, d]) => {
    const el = document.createElement("div");
    el.className = "drive";
    const color = d.percent > 90 ? "#f87171" : d.percent > 75 ? "#fbbf24" : "#4c9aff";
    const typeLabel = d.type === "removable" ? "USB" : d.type === "network" ? "Red" : d.type === "ramdisk" ? "RAM" : "Local";
    el.innerHTML = `
      <div class="drive-head"><b>${letter}</b><span>${d.free_gb} GB libres · <span class="drive-type">${typeLabel}</span></span></div>
      <div class="track"><div class="fill" style="width:${d.percent}%; --c:${color}"></div></div>
      <div class="drive-head" style="margin-top:6px; margin-bottom:0">
        <span>${d.used_gb} / ${d.total_gb} GB</span><span>${d.percent}%</span>
      </div>`;
    wrap.appendChild(el);
  });
}

// ─────────────────────────── optimizador ───────────────────────────
const selTweaks = new Set();
const selReverts = new Set();
let tweaksCache = [];
let optPolling = null;

function initOptimizer() {
  loadTweaks();
  $("btn-select-all").addEventListener("click", () => {
    const selectable = tweaksCache.filter((t) => !t.applied);
    const allSel = selectable.every((t) => selTweaks.has(t.id));
    selTweaks.clear();
    if (!allSel) selectable.forEach((t) => selTweaks.add(t.id));
    renderTweaks();
  });
  $("btn-apply").addEventListener("click", applyTweaks);
  $("btn-revert").addEventListener("click", revertTweaks);
  $("btn-clear-log").addEventListener("click", () => ($("opt-log").innerHTML = ""));
}

async function loadTweaks() {
  const r = await api.get_tweaks();
  tweaksCache = r.tweaks;
  $("tweak-count").textContent = r.tweaks.length;
  renderTweaks();
  renderRevertPanel();
}

function renderTweaks() {
  const grid = $("tweaks-grid");
  grid.innerHTML = "";
  tweaksCache.forEach((t) => {
    const el = document.createElement("div");
    el.className = "tweak" + (selTweaks.has(t.id) ? " selected" : "") + (t.applied ? " applied" : "");
    el.innerHTML = `
      <div class="tweak-check"></div>
      <div class="tweak-body">
        <div class="tweak-title">${t.label}
          ${t.admin ? '<span class="tag admin">ADMIN</span>' : ""}
          ${t.applied ? '<span class="tag applied">APLICADO</span>' : ""}
        </div>
        <div class="tweak-desc">${t.desc}</div>
      </div>
      <div class="tweak-status" data-tid="${t.id}"></div>`;
    if (!t.applied) {
      el.addEventListener("click", () => {
        selTweaks.has(t.id) ? selTweaks.delete(t.id) : selTweaks.add(t.id);
        el.classList.toggle("selected");
      });
    }
    grid.appendChild(el);
  });
  updateApplyBtn();
}

function updateApplyBtn() {
  const n = selTweaks.size;
  $("btn-apply").textContent = n > 0 ? `Aplicar ${n} tweak${n > 1 ? "s" : ""}` : "Aplicar tweaks";
}

function renderRevertPanel() {
  const applied = tweaksCache.filter((t) => t.applied && t.revertable);
  const panel = $("revert-panel");
  panel.hidden = applied.length === 0;
  const list = $("revert-list");
  list.innerHTML = "";
  applied.forEach((t) => {
    const chip = document.createElement("button");
    chip.className = "revert-chip" + (selReverts.has(t.id) ? " selected" : "");
    chip.textContent = t.label;
    chip.addEventListener("click", () => {
      selReverts.has(t.id) ? selReverts.delete(t.id) : selReverts.add(t.id);
      chip.classList.toggle("selected");
    });
    list.appendChild(chip);
  });
}

function appendLog(el, msg) {
  const cls = msg.includes("[OK]") ? "ok" : msg.includes("[ERROR]") || msg.includes("[X]") ? "err" : msg.includes("[WARN]") ? "warn" : "";
  const line = document.createElement("span");
  if (cls) line.className = cls;
  line.textContent = msg + "\n";
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

async function applyTweaks() {
  if (selTweaks.size === 0) return;
  const r = await api.start_tweaks([...selTweaks]);
  if (!r.ok) return;
  startOptPolling();
}

async function revertTweaks() {
  if (selReverts.size === 0) return;
  const r = await api.start_revert([...selReverts]);
  if (!r.ok) return;
  selReverts.clear();
  startOptPolling();
}

function startOptPolling() {
  $("opt-progress").hidden = false;
  $("btn-apply").disabled = true;
  $("btn-revert").disabled = true;
  let logIdx = 0;
  optPolling = setInterval(async () => {
    const job = await api.get_tweak_job();
    // logs incrementales
    for (; logIdx < job.logs.length; logIdx++) appendLog($("opt-log"), job.logs[logIdx]);
    // progreso
    const pct = job.total > 0 ? Math.round((job.current / job.total) * 100) : 0;
    $("opt-progress-fill").style.width = pct + "%";
    $("opt-progress-pct").textContent = pct + "%";
    $("opt-progress-label").textContent = job.label || (job.done ? "Completado" : "Procesando…");
    // estados por tweak
    Object.entries(job.statuses).forEach(([tid, st]) => {
      const el = document.querySelector(`.tweak-status[data-tid="${tid}"]`);
      if (el) el.textContent = st === "ok" ? "✅" : st === "error" ? "❌" : st === "running" ? "⏳" : st === "skipped" ? "⚠️" : "";
    });
    if (job.done) {
      clearInterval(optPolling);
      $("btn-apply").disabled = false;
      $("btn-revert").disabled = false;
      selTweaks.clear();
      setTimeout(() => { $("opt-progress").hidden = true; loadTweaks(); }, 1500);
    }
  }, 400);
}

// ─────────────────────────── software hub ───────────────────────────
const selApps = new Set();
let appCatalog = {};
let categories = [];
let activeCat = null;
let appsCache = [];
let statusesCache = {};
let searchTerm = "";
let lastInstallResults = [];

function initHub() {
  loadAppCatalog();
  loadCategories();
  $("search").addEventListener("input", (e) => {
    searchTerm = e.target.value.toLowerCase().trim();
    renderApps();
  });
  $("btn-clear-sel").addEventListener("click", () => { selApps.clear(); renderApps(); updateActionBar(); });
  $("btn-install-sel").addEventListener("click", () => installApps([...selApps], "Instalando " + selApps.size + " aplicaciones"));
  $("btn-select-pending").addEventListener("click", () => {
    appsCache.forEach((a) => {
      const st = statusesCache[a.id];
      if (!st || !st.installed || st.update_available) selApps.add(a.id);
    });
    renderApps();
    updateActionBar();
  });
  $("btn-install-cat").addEventListener("click", () => {
    appsCache.forEach((a) => {
      const st = statusesCache[a.id];
      if (!st || !st.installed || st.update_available) selApps.add(a.id);
    });
    renderApps();
    updateActionBar();
  });
  $("modal-cancel").addEventListener("click", async () => { await api.cancel_install(); });
  $("modal-close").addEventListener("click", closeInstallModal);
}

async function loadAppCatalog() {
  try {
    const r = await api.get_app_catalog();
    appCatalog = r.apps || {};
  } catch {}
}

async function loadCategories() {
  const r = await api.get_categories();
  categories = r.categories;
  const wrap = $("cat-chips");
  wrap.innerHTML = "";
  categories.forEach((c, i) => {
    const chip = document.createElement("button");
    chip.className = "chip" + (i === 0 ? " active" : "");
    chip.dataset.cid = c.id;
    chip.innerHTML = `${c.nombre} <span style="opacity:.6">${c.count}</span>` + (c.updates > 0 ? ` <span class="up">${c.updates}↑</span>` : "");
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach((x) => x.classList.remove("active"));
      chip.classList.add("active");
      selectCategory(c.id);
    });
    wrap.appendChild(chip);
  });
  if (categories.length) selectCategory(categories[0].id);
  pollHubBadge();
}

async function selectCategory(cid) {
  activeCat = cid;
  const r = await api.get_apps(cid);
  appsCache = r.apps;
  appsCache.forEach((a) => {
    if (!appCatalog[a.id]) appCatalog[a.id] = { nombre: a.nombre, categoria: "" };
  });
  renderApps();
  refreshStatuses();
  updateActionBar();
  if (appsCache.some((a) => !a.icon)) {
    setTimeout(async () => {
      if (activeCat !== cid) return;
      const r2 = await api.get_apps(cid);
      appsCache = r2.apps;
      renderApps();
      updateActionBar();
    }, 4000);
  }
}

async function refreshStatusesForIds(ids) {
  if (!ids.length) return;
  const r = await api.get_app_statuses(ids);
  if (r.loaded) {
    window.__hubLoaded = true;
    statusesCache = { ...statusesCache, ...r.statuses };
    renderApps();
    updateActionBar();
  }
}

async function refreshStatuses() {
  if (!appsCache.length) return;
  const ids = appsCache.map((a) => a.id);
  const r = await api.get_app_statuses(ids);
  if (r.loaded) {
    window.__hubLoaded = true;
    statusesCache = { ...statusesCache, ...r.statuses };
    renderApps();
  } else {
    setTimeout(refreshStatuses, 2500);
  }
}

function renderApps() {
  const grid = $("apps-grid");
  grid.innerHTML = "";
  const filtered = appsCache.filter(
    (a) => !searchTerm || a.nombre.toLowerCase().includes(searchTerm) || a.desc.toLowerCase().includes(searchTerm)
  );
  $("hub-empty").hidden = filtered.length > 0;

  filtered.forEach((a) => {
    const st = statusesCache[a.id];
    const installed = st && st.installed;
    const hasUpdate = st && st.update_available;

    const el = document.createElement("div");
    el.className = "app-card" + (selApps.has(a.id) ? " selected" : "") + (installed && !hasUpdate ? " disabled" : "") + (a.unavailable ? " unavailable" : "");

    const iconHtml = a.icon
      ? `<img class="app-icon" src="${a.icon}" alt="">`
      : `<div class="app-icon">${a.nombre.charAt(0).toUpperCase()}</div>`;

    let statusHtml;
    if (!st && !window.__hubLoaded) statusHtml = '<div class="app-status no">Comprobando…</div>';
    else if (hasUpdate) statusHtml = `<div class="app-status upd">⭮ Actualización</div><div class="app-ver">${st.version || ""} → ${st.available_version || ""}</div>`;
    else if (installed) statusHtml = `<div class="app-status ok">✓ Instalado</div><div class="app-ver">${st.version || ""}</div>`;
    else statusHtml = '<div class="app-status no">No instalado</div>';

    el.innerHTML = `
      <div class="app-check"></div>
      ${installed ? `<div class="app-actions">${hasUpdate ? '<button class="mini-btn" data-act="upd" title="Actualizar">⭮</button>' : ""}<button class="mini-btn del" data-act="del" title="Desinstalar">🗑</button></div>` : ""}
      ${iconHtml}
      <div class="app-name">${a.nombre}</div>
      <div class="app-desc">${a.desc}</div>
      <div class="app-meta">${a.size}${a.rating ? " · ★ " + a.rating : ""}</div>
      ${statusHtml}`;

    el.addEventListener("click", (e) => {
      const act = e.target.closest && e.target.closest(".mini-btn");
      if (act) {
        e.stopPropagation();
        if (act.dataset.act === "del") {
          uninstallApp(a);
        } else if (act.dataset.act === "upd") {
          installApps([a.id], "Actualizando " + a.nombre, true);
        }
        return;
      }
      if (installed && !hasUpdate) return;
      if (a.unavailable) return;
      selApps.has(a.id) ? selApps.delete(a.id) : selApps.add(a.id);
      el.classList.toggle("selected");
      updateActionBar();
    });

    grid.appendChild(el);
  });
}

function updateActionBar() {
  const n = selApps.size;
  $("action-bar").hidden = n === 0;
  $("action-bar-text").textContent = n + " seleccionada" + (n !== 1 ? "s" : "") + " (todas las categorías)";
  $("btn-install-sel").textContent = "Instalar (" + n + ")";

  const chips = $("sel-chips");
  chips.innerHTML = "";
  const visibleIds = new Set(appsCache.map((a) => a.id));
  const selected = [...selApps];
  const show = selected.slice(0, 8);
  show.forEach((id) => {
    const meta = appCatalog[id] || { nombre: id };
    const chip = document.createElement("span");
    chip.className = "sel-chip" + (visibleIds.has(id) ? "" : " other");
    chip.textContent = meta.nombre;
    chip.title = meta.categoria || "Otra categoría";
    chips.appendChild(chip);
  });
  if (selected.length > 8) {
    const more = document.createElement("span");
    more.className = "sel-chip other";
    more.textContent = "+" + (selected.length - 8) + " más";
    chips.appendChild(more);
  }
}

async function pollHubBadge() {
  try {
    const r = await api.get_outdated_count();
    const badge = $("hub-badge");
    badge.hidden = r.count === 0;
    badge.textContent = r.count;
  } catch {}
  setTimeout(pollHubBadge, 30000);
}

// ─── instalación con modal ───
let installPolling = null;

async function installApps(ids, title, isUpgrade = false) {
  if (!ids.length) return;
  const r = isUpgrade ? await api.start_upgrade(ids) : await api.start_install(ids);
  if (!r.ok) return;
  openInstallModal(title);
}

async function uninstallApp(a) {
  const r = await api.start_uninstall(a.id);
  if (!r.ok) return;
  openInstallModal("Desinstalando " + a.nombre);
}

function openInstallModal(title) {
  lastInstallResults = [];
  $("modal-title").textContent = title;
  $("modal-sub").textContent = "Preparando…";
  $("modal-fill").style.width = "0%";
  $("modal-log").innerHTML = "";
  $("modal-close").disabled = true;
  $("modal-cancel").disabled = false;
  $("install-modal").hidden = false;

  let logIdx = 0;
  installPolling = setInterval(async () => {
    const job = await api.get_install_job();
    for (; logIdx < job.logs.length; logIdx++) appendLog($("modal-log"), job.logs[logIdx]);
    const pct = job.total > 0 ? Math.round((job.current / job.total) * 100) : 0;
    $("modal-fill").style.width = pct + "%";
    $("modal-sub").textContent = job.done
      ? "Completado"
      : job.label
      ? `${job.label} (${Math.min(job.current + 1, job.total)}/${job.total})`
      : "Preparando…";
    if (job.done) {
      clearInterval(installPolling);
      lastInstallResults = job.results || [];
      const ok = lastInstallResults.filter((r) => r.ok).length;
      const fail = lastInstallResults.length - ok;
      $("modal-fill").style.width = "100%";
      $("modal-sub").textContent = fail
        ? `Completado: ${ok} OK, ${fail} fallidas`
        : `Completado: ${ok} instaladas correctamente`;
      $("modal-close").disabled = false;
      $("modal-cancel").disabled = true;
      lastInstallResults.forEach((r) => { if (r.ok) selApps.delete(r.id); });
      updateActionBar();
      renderApps();
    }
  }, 500);
}

async function closeInstallModal() {
  $("install-modal").hidden = true;
  const ids = [...selApps, ...lastInstallResults.map((r) => r.id)];
  await refreshStatusesForIds([...new Set(ids)]);
  if (appsCache.length) refreshStatuses();
  loadCategories();
}

// ─────────────────────────── massgrave / MAS ───────────────────────────
function initMas() {
  loadMas();
  $("btn-mas-refresh").addEventListener("click", loadMasStatus);
  $("btn-mas-open").addEventListener("click", () => launchMas("online_console", "PowerShell MAS"));
  $("btn-mas-copy").addEventListener("click", () => {
    const t = $("mas-cmd-text").textContent;
    navigator.clipboard.writeText(t).then(() => {
      $("btn-mas-copy").textContent = "¡Copiado!";
      setTimeout(() => ($("btn-mas-copy").textContent = "Copiar comando"), 1500);
    });
  });
}

async function loadMas() {
  try {
    const info = await api.get_mas_info();
    const hint = $("mas-auto-hint");
    if (info.commands && info.commands.online) {
      $("mas-cmd-text").textContent = info.commands.online;
    }
    if (!info.admin) {
      hint.textContent = "⚠ Ejecuta ResetX como administrador. Se pedirá elevación UAC al abrir MAS.";
    } else {
      hint.textContent = "Se abrirá una ventana externa. Elige opciones VERDES en el menú de MAS.";
    }
    const wrap = $("mas-methods");
    wrap.innerHTML = "";
    (info.methods || []).forEach((m) => {
      const card = document.createElement("div");
      card.className = "mas-card";
      card.innerHTML = `<h4>${m.title}</h4><p>${m.desc}</p>`;
      const btn = document.createElement("button");
      btn.className = "btn-primary";
      btn.textContent = "Ejecutar";
      btn.addEventListener("click", () => launchMas(m.id, m.title));
      card.appendChild(btn);
      wrap.appendChild(card);
    });
    const notes = $("mas-notes");
    notes.innerHTML = "";
    (info.notes || []).forEach((n) => {
      const li = document.createElement("li");
      li.textContent = n;
      notes.appendChild(li);
    });
    loadMasStatus();
  } catch (e) {
    $("mas-status-text").textContent = "Error cargando MAS: " + e;
  }
}

async function loadMasStatus() {
  try {
    const st = await api.get_mas_status();
    const el = $("mas-status-text");
    el.textContent = st.text || "—";
    el.className = "mas-status-text" + (st.licensed ? " ok" : st.trial ? " warn" : "");
  } catch {
    $("mas-status-text").textContent = "No se pudo comprobar el estado.";
  }
}

async function launchMas(method, title) {
  const admin = await api.is_admin();
  if (!admin.admin) {
    appendLog($("mas-log"), "[WARN] Se recomienda ejecutar ResetX como administrador.\n");
  }
  appendLog($("mas-log"), "[+] Lanzando: " + title + "\n");
  const r = await api.launch_mas(method);
  if (!r.ok) {
    appendLog($("mas-log"), "[ERROR] " + (r.error || "No se pudo lanzar") + "\n");
    return;
  }
  pollMasJob();
}

function pollMasJob() {
  let logIdx = 0;
  const poll = setInterval(async () => {
    const job = await api.get_mas_job();
    for (; logIdx < job.logs.length; logIdx++) appendLog($("mas-log"), job.logs[logIdx] + "\n");
    if (job.done) {
      clearInterval(poll);
      if (job.error) appendLog($("mas-log"), "[ERROR] " + job.error + "\n");
      setTimeout(loadMasStatus, 2000);
    }
  }, 500);
}

// ─────────────────────────── updates ───────────────────────────
async function checkUpdates() {
  try {
    const r = await api.check_update();
    if (r.update && r.update.available) {
      $("update-ver").textContent = "v" + r.update.version + " lista para instalar";
      $("update-toast").hidden = false;
      $("btn-update").addEventListener("click", async () => {
        $("btn-update").textContent = "Descargando…";
        $("btn-update").disabled = true;
        await api.start_app_update(r.update.url);
      });
      $("btn-update-later").addEventListener("click", () => ($("update-toast").hidden = true));
    }
  } catch {}
}
