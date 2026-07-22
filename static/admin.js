/* Отдельная админ-панель. Самодостаточна (не зависит от app.js). */

/* Inline SVG icon set (stroke = currentColor). Static/trusted markup. */
const ICONS = {
  refresh:
    '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
  key:
    '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
  trash:
    '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
};

let CSRF_TOKEN = "";
let ME = null;

function getCookie(name) {
  const m = document.cookie.match(
    "(?:^|; )" + name.replace(/([.$?*|{}()\[\]\\\/\+^])/g, "\\$1") + "=([^;]*)"
  );
  return m ? decodeURIComponent(m[1]) : "";
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const method = (opts.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers["X-CSRF-Token"] = CSRF_TOKEN || getCookie("csrf");
  }
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("401");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

let toastTimer;
function toast(msg, kind = "") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast show " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), 2600);
}

function fmtDate(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

// ─── Модалка (переиспользует стили style.css) ────────────────────────────
const modalRoot = document.getElementById("modal-root");
function openModal(title, bodyHtml, footHtml) {
  modalRoot.innerHTML = `
    <div class="backdrop"></div>
    <div class="modal">
      <div class="modal-head">
        <span class="modal-title">${escapeHtml(title)}</span>
        <button class="btn outline small" data-act="cancel" aria-label="close">×</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
      <div class="modal-foot">${footHtml}</div>
    </div>`;
  modalRoot.classList.add("active");
  modalRoot.querySelector(".backdrop").addEventListener("click", closeModal);
}
function closeModal() {
  modalRoot.classList.remove("active");
  modalRoot.innerHTML = "";
}

// ─── Данные ────────────────────────────────────────────────────────────
async function loadMe() {
  const data = await api("/api/auth/me");
  ME = data.user;
  CSRF_TOKEN = data.csrf || "";
  if (ME.role !== "admin") {
    window.location.href = "/";
    throw new Error("not admin");
  }
  document.getElementById("me-badge").textContent = ME.username + " · admin";
}

async function reloadAll() {
  const [users, status] = await Promise.all([
    api("/api/admin/users"),
    api("/api/admin/backup/status"),
  ]);
  renderUsers(users);
  const sEl = document.getElementById("admin-backup-status");
  sEl.textContent = status.configured
    ? `Telegram-бэкапы включены (каждые ${status.interval_hours}ч; accounts.json: ${status.include_accounts ? "да" : "нет"})`
    : "Telegram-бэкапы не настроены — задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID";
  sEl.classList.toggle("warn", !status.configured);
  await reloadAudit();
}

async function refreshCampaignCatalog() {
  const button = document.getElementById("campaign-catalog-refresh");
  const status = document.getElementById("campaign-catalog-status");
  button.disabled = true;
  button.textContent = "Обновление…";
  try {
    const data = await api("/api/admin/campaigns/refresh", { method: "POST" });
    status.textContent = `${data.campaigns?.length || 0} кампаний · ${fmtDate(data.fetched_at)}`;
    toast("Каталог кампаний обновлён", "success");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    button.disabled = false;
    button.innerHTML = ICONS.refresh + " Обновить";
  }
}

async function reloadCampaignCatalogStatus() {
  try {
    const data = await api("/api/campaigns");
    document.getElementById("campaign-catalog-status").textContent =
      `${data.campaigns?.length || 0} кампаний · ${fmtDate(data.fetched_at)}`;
  } catch (_) {}
}

function subCell(u) {
  if (u.role === "admin") return { text: "∞", cls: "" };
  if (!u.subscription_until) return { text: "нет", cls: "sub-expired" };
  const left = u.subscription_until * 1000 - Date.now();
  if (left <= 0) return { text: "истекла " + fmtDate(u.subscription_until), cls: "sub-expired" };
  const days = Math.floor(left / 86400000);
  return { text: `${fmtDate(u.subscription_until)} (${days} дн.)`, cls: days <= 3 ? "sub-warn" : "" };
}

function renderUsers(users) {
  const body = document.getElementById("admin-body");
  body.innerHTML = "";
  for (const u of users) {
    const tr = document.createElement("tr");
    const sub = subCell(u);
    const active = u.role === "admin" || u.subscription_active;
    tr.innerHTML = `
      <td>${u.id}</td>
      <td>${escapeHtml(u.username)}</td>
      <td>${escapeHtml(u.role)}</td>
      <td>${u.proxy_mode === "pool" ? "наш пул" : "свой пул"}</td>
      <td class="num">${u.accounts_count || 0}</td>
      <td class="num">${u.proxy_mode === "pool" ? "общий" : (u.proxy_count || 0)}</td>
      <td><span class="cell-status"><span class="dot ${u.farming ? "ok" : "off"}"></span>${u.farming ? (u.farming_accounts || 0) : 0}/${u.accounts_count || 0}</span></td>
      <td class="num">${u.thread_limit}</td>
      <td><span class="cell-status"><span class="dot ${u.enabled ? (active ? "ok" : "err") : "off"}"></span>${u.enabled ? (active ? "активен" : "остановлен") : "выключен"}</span></td>
      <td>${u.totp_enabled ? "🔐" : "—"}</td>
      <td></td>`;
    const actions = document.createElement("div");
    actions.className = "row gap";
    const editBtn = document.createElement("button");
    editBtn.className = "btn outline small";
    editBtn.textContent = "Изменить";
    editBtn.addEventListener("click", () => openEditModal(u));
    const pwBtn = document.createElement("button");
    pwBtn.className = "btn accent small icon";
    pwBtn.innerHTML = ICONS.key;
    pwBtn.title = "Сбросить пароль";
    pwBtn.setAttribute("aria-label", "Сбросить пароль");
    pwBtn.addEventListener("click", () => openPasswordModal(u));
    const delBtn = document.createElement("button");
    delBtn.className = "btn danger small icon";
    delBtn.innerHTML = ICONS.trash;
    delBtn.title = "Удалить";
    delBtn.setAttribute("aria-label", "Удалить");
    delBtn.addEventListener("click", () => deleteUser(u));
    actions.append(editBtn, pwBtn, delBtn);
    tr.lastElementChild.appendChild(actions);
    body.appendChild(tr);
  }
}

async function reloadAudit() {
  try {
    const rows = await api("/api/admin/audit");
    document.getElementById("admin-audit").innerHTML = rows
      .map((r) => `<div class="log-line"><span class="log-ts">${fmtDate(r.ts)}</span> <b>${escapeHtml(r.event)}</b> ${escapeHtml(r.username || "")} <span class="muted">${escapeHtml(r.ip || "")}</span> ${escapeHtml(r.detail || "")}</div>`)
      .join("");
  } catch (_) {}
}

// ─── Модалки CRUD ────────────────────────────────────────────────────────
function openCreateModal() {
  openModal("Новый пользователь", `
    <div class="fieldset">
      <div class="field"><label>Логин</label><input class="input" id="u-name" maxlength="32" autocomplete="off"/></div>
      <div class="field"><label>Пароль</label><input class="input" id="u-pass" type="text" maxlength="256" autocomplete="new-password"/></div>
      <div class="field"><label>Роль</label>
        <select class="input" id="u-role"><option value="user">user</option><option value="admin">admin</option></select>
      </div>
      <div class="field"><label>Тип прокси / подписки</label>
        <select class="input" id="u-proxy-mode">
          <option value="own">свой пул</option><option value="pool">наш пул</option>
        </select>
      </div>
      <div class="field"><label>Лимит потоков</label><input class="input" id="u-threads" type="number" min="0" value="1"/></div>
      <div class="field"><label>Длительность подписки (дней, 0 = без)</label><input class="input" id="u-days" type="number" min="0" value="30"/></div>
    </div>`,
    `<button class="btn outline" data-act="cancel">Отмена</button><button class="btn primary" data-act="save">Создать</button>`);
  const m = modalRoot.querySelector(".modal");
  m.querySelectorAll("[data-act=cancel]").forEach((b) => b.addEventListener("click", closeModal));
  m.querySelector("[data-act=save]").addEventListener("click", async () => {
    const days = parseFloat(m.querySelector("#u-days").value || "0");
    const payload = {
      username: m.querySelector("#u-name").value.trim(),
      password: m.querySelector("#u-pass").value,
      role: m.querySelector("#u-role").value,
      proxy_mode: m.querySelector("#u-proxy-mode").value,
      thread_limit: parseInt(m.querySelector("#u-threads").value || "0", 10) || 0,
      subscription_days: days > 0 ? days : null,
      enabled: true,
    };
    try {
      await api("/api/admin/users", { method: "POST", body: JSON.stringify(payload) });
      closeModal(); await reloadAll(); toast("Пользователь создан", "success");
    } catch (e) { toast(e.message, "error"); }
  });
}

function openEditModal(u) {
  openModal("Изменить: " + u.username, `
    <div class="fieldset">
      <div class="field"><label>Роль</label>
        <select class="input" id="u-role">
          <option value="user" ${u.role === "user" ? "selected" : ""}>user</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
        </select>
      </div>
      <div class="field"><label>Тип прокси / подписки</label>
        <select class="input" id="u-proxy-mode">
          <option value="own" ${u.proxy_mode !== "pool" ? "selected" : ""}>свой пул</option>
          <option value="pool" ${u.proxy_mode === "pool" ? "selected" : ""}>наш пул</option>
        </select>
      </div>
      <div class="field"><label>Лимит потоков</label><input class="input" id="u-threads" type="number" min="0" value="${u.thread_limit}"/></div>
      <div class="field"><label>Включён</label>
        <select class="input" id="u-enabled"><option value="1" ${u.enabled ? "selected" : ""}>да</option><option value="0" ${!u.enabled ? "selected" : ""}>нет</option></select>
      </div>
      <div class="field"><label>Подписка сейчас: ${escapeHtml(u.role === "admin" ? "∞" : fmtDate(u.subscription_until))}</label></div>
      <div class="field"><label>Установить подписку (дней от сейчас; пусто = без изменений)</label><input class="input" id="u-setdays" type="number" min="0" placeholder=""/></div>
      <div class="field"><label>Продлить на (дней)</label><input class="input" id="u-adddays" type="number" min="0" placeholder="0"/></div>
    </div>`,
    `<button class="btn outline" data-act="cancel">Отмена</button><button class="btn primary" data-act="save">Сохранить</button>`);
  const m = modalRoot.querySelector(".modal");
  m.querySelectorAll("[data-act=cancel]").forEach((b) => b.addEventListener("click", closeModal));
  m.querySelector("[data-act=save]").addEventListener("click", async () => {
    const payload = {
      role: m.querySelector("#u-role").value,
      proxy_mode: m.querySelector("#u-proxy-mode").value,
      thread_limit: parseInt(m.querySelector("#u-threads").value || "0", 10) || 0,
      enabled: m.querySelector("#u-enabled").value === "1",
    };
    const setDays = m.querySelector("#u-setdays").value;
    const addDays = m.querySelector("#u-adddays").value;
    if (setDays !== "") payload.subscription_days = parseFloat(setDays) || 0;
    if (addDays !== "" && parseFloat(addDays) > 0) payload.add_subscription_days = parseFloat(addDays);
    try {
      await api(`/api/admin/users/${u.id}`, { method: "PUT", body: JSON.stringify(payload) });
      closeModal(); await reloadAll(); toast("Сохранено", "success");
    } catch (e) { toast(e.message, "error"); }
  });
}

function openPasswordModal(u) {
  openModal("Сброс пароля: " + u.username,
    `<div class="fieldset"><div class="field" style="grid-column:1/span 2"><label>Новый пароль</label><input class="input" id="u-newpass" type="text" maxlength="256" autocomplete="new-password"/></div></div>`,
    `<button class="btn outline" data-act="cancel">Отмена</button><button class="btn primary" data-act="save">Сбросить</button>`);
  const m = modalRoot.querySelector(".modal");
  m.querySelectorAll("[data-act=cancel]").forEach((b) => b.addEventListener("click", closeModal));
  m.querySelector("[data-act=save]").addEventListener("click", async () => {
    try {
      await api(`/api/admin/users/${u.id}/password`, {
        method: "POST", body: JSON.stringify({ password: m.querySelector("#u-newpass").value }),
      });
      closeModal(); toast("Пароль обновлён", "success");
    } catch (e) { toast(e.message, "error"); }
  });
}

async function deleteUser(u) {
  if (!confirm(`Удалить пользователя '${u.username}'?`)) return;
  try {
    await api(`/api/admin/users/${u.id}`, { method: "DELETE" });
    await reloadAll(); toast("Удалён", "success");
  } catch (e) { toast(e.message, "error"); }
}

async function triggerBackup() {
  try {
    const r = await api("/api/admin/backup", { method: "POST" });
    toast(r.ok ? "Бэкап отправлен" : ("Бэкап: " + (r.detail || "ошибка")), r.ok ? "success" : "error");
  } catch (e) { toast(e.message, "error"); }
}

let poolProxies = [];
const poolSelected = new Set();

function poolStatusText(status) {
  return {
    valid: "Рабочий",
    invalid: "Недоступен",
    unsupported: "Не поддерживается",
    unknown: "Неизвестно",
  }[status || "unknown"] || status;
}

function renderPool() {
  const body = document.getElementById("pool-body");
  const empty = document.getElementById("pool-empty");
  body.innerHTML = "";
  empty.style.display = poolProxies.length ? "none" : "";
  poolProxies.forEach((proxy) => {
    const tr = document.createElement("tr");
    tr.dataset.raw = proxy.raw;
    tr.innerHTML = `
      <td class="col-chk"><input type="checkbox" ${poolSelected.has(proxy.raw) ? "checked" : ""}></td>
      <td class="proxy-raw">${escapeHtml(proxy.raw)}</td>
      <td>${escapeHtml(proxy.host)}</td>
      <td>${proxy.port}</td>
      <td>${escapeHtml(proxy.username || "")}</td>
      <td><span class="proxy-status ${escapeHtml(proxy.status || "unknown")}">${escapeHtml(poolStatusText(proxy.status))}</span></td>
      <td>${proxy.latency_ms == null ? "—" : proxy.latency_ms}</td>`;
    tr.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) poolSelected.add(proxy.raw);
      else poolSelected.delete(proxy.raw);
    });
    body.appendChild(tr);
  });
}

async function reloadPool() {
  poolProxies = await api("/api/admin/proxy-pool");
  for (const raw of [...poolSelected]) {
    if (!poolProxies.some((proxy) => proxy.raw === raw)) poolSelected.delete(raw);
  }
  renderPool();
}

function openPoolImportModal() {
  openModal("Импорт общего прокси-пула", `
    <div class="fieldset">
      <div class="field" style="grid-column:1/span 2">
        <label>Список прокси</label>
        <textarea class="ta" rows="10" id="pool-data" placeholder="1.2.3.4:8080&#10;user:pass@host:3128"></textarea>
      </div>
    </div>`,
    `<button class="btn outline" data-act="cancel">Отмена</button><button class="btn primary" data-act="save">Импортировать</button>`);
  const modal = modalRoot.querySelector(".modal");
  modal.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  modal.querySelector("[data-act=save]").addEventListener("click", async () => {
    try {
      const result = await api("/api/admin/proxy-pool/import", {
        method: "POST",
        body: JSON.stringify({ data: modal.querySelector("#pool-data").value }),
      });
      closeModal(); await reloadPool();
      toast(`Импортировано: ${result.imported}`, "success");
    } catch (e) { toast(e.message, "error"); }
  });
}

async function deletePoolSelected() {
  const keys = [...poolSelected];
  if (!keys.length) { toast("Выберите прокси", "error"); return; }
  if (!confirm(`Удалить выбранные прокси (${keys.length})?`)) return;
  try {
    await api("/api/admin/proxy-pool/bulk-delete", {
      method: "POST", body: JSON.stringify({ keys }),
    });
    poolSelected.clear(); await reloadPool(); toast("Удалено", "success");
  } catch (e) { toast(e.message, "error"); }
}

async function checkPool() {
  const button = document.getElementById("pool-check");
  button.disabled = true;
  try {
    poolProxies = await api("/api/admin/proxy-pool/check", {
      method: "POST",
      body: JSON.stringify({ keys: [...poolSelected] }),
    });
    renderPool(); toast("Проверка прокси завершена", "success");
  } catch (e) { toast(e.message, "error"); }
  finally { button.disabled = false; }
}

let convertPoolProxies = [];
const convertPoolSelected = new Set();

function renderConvertPool() {
  const body = document.getElementById("convert-pool-body");
  const empty = document.getElementById("convert-pool-empty");
  body.innerHTML = "";
  empty.style.display = convertPoolProxies.length ? "none" : "";
  convertPoolProxies.forEach((proxy) => {
    const tr = document.createElement("tr");
    tr.dataset.raw = proxy.raw;
    tr.innerHTML = `
      <td class="col-chk"><input type="checkbox" ${convertPoolSelected.has(proxy.raw) ? "checked" : ""}></td>
      <td class="proxy-raw">${escapeHtml(proxy.raw)}</td>
      <td>${escapeHtml(proxy.host)}</td>
      <td>${proxy.port}</td>
      <td>${escapeHtml(proxy.username || "")}</td>
      <td><span class="proxy-status ${escapeHtml(proxy.status || "unknown")}">${escapeHtml(poolStatusText(proxy.status))}</span></td>
      <td>${proxy.latency_ms == null ? "—" : proxy.latency_ms}</td>`;
    tr.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) convertPoolSelected.add(proxy.raw);
      else convertPoolSelected.delete(proxy.raw);
    });
    body.appendChild(tr);
  });
}

async function reloadConvertPool() {
  convertPoolProxies = await api("/api/admin/convert-proxy-pool");
  for (const raw of [...convertPoolSelected]) {
    if (!convertPoolProxies.some((proxy) => proxy.raw === raw)) convertPoolSelected.delete(raw);
  }
  renderConvertPool();
}

function openConvertPoolImportModal() {
  openModal("Импорт прокси для конвертации", `
    <div class="fieldset">
      <div class="field" style="grid-column:1/span 2">
        <label>Список прокси</label>
        <textarea class="ta" rows="10" id="convert-pool-data" placeholder="1.2.3.4:8080&#10;user:pass@host:3128"></textarea>
      </div>
    </div>`,
    `<button class="btn outline" data-act="cancel">Отмена</button><button class="btn primary" data-act="save">Импортировать</button>`);
  const modal = modalRoot.querySelector(".modal");
  modal.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  modal.querySelector("[data-act=save]").addEventListener("click", async () => {
    try {
      const result = await api("/api/admin/convert-proxy-pool/import", {
        method: "POST",
        body: JSON.stringify({ data: modal.querySelector("#convert-pool-data").value }),
      });
      closeModal(); await reloadConvertPool();
      toast(`Импортировано: ${result.imported}`, "success");
    } catch (e) { toast(e.message, "error"); }
  });
}

async function deleteConvertPoolSelected() {
  const keys = [...convertPoolSelected];
  if (!keys.length) { toast("Выберите прокси", "error"); return; }
  if (!confirm(`Удалить выбранные прокси (${keys.length})?`)) return;
  try {
    await api("/api/admin/convert-proxy-pool/bulk-delete", {
      method: "POST", body: JSON.stringify({ keys }),
    });
    convertPoolSelected.clear();
    await reloadConvertPool();
    toast("Удалено", "success");
  } catch (e) { toast(e.message, "error"); }
}

async function checkConvertPool() {
  const button = document.getElementById("convert-pool-check");
  button.disabled = true;
  try {
    convertPoolProxies = await api("/api/admin/convert-proxy-pool/check", {
      method: "POST",
      body: JSON.stringify({ keys: [...convertPoolSelected] }),
    });
    renderConvertPool();
    toast("Проверка прокси завершена", "success");
  } catch (e) { toast(e.message, "error"); }
  finally { button.disabled = false; }
}

// ─── Глобальные настройки ────────────────────────────────────────────────
async function loadSettings() {
  const input = document.getElementById("setting-convert-concurrency");
  if (!input) return;
  try {
    const data = await api("/api/admin/settings");
    input.value = String(data.convert_concurrency);
  } catch (e) {
    toast(e.message, "error");
  }
}

async function saveSettings() {
  const input = document.getElementById("setting-convert-concurrency");
  const status = document.getElementById("settings-status");
  const value = Math.max(1, Math.min(32, Number(input.value) || 3));
  try {
    const data = await api("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify({ convert_concurrency: value }),
    });
    input.value = String(data.convert_concurrency);
    if (status) status.textContent = "Сохранено";
    toast("Сохранено", "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

// ─── Init ──────────────────────────────────────────────────────────────
async function init() {
  try {
    await loadMe();
  } catch (e) {
    return; // редирект уже произошёл
  }
  document.getElementById("admin-main").style.display = "";
  document.getElementById("logout-btn").addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {}
    window.location.href = "/login";
  });
  document.getElementById("admin-new-user").addEventListener("click", openCreateModal);
  document.getElementById("admin-backup-btn").addEventListener("click", triggerBackup);
  document.getElementById("admin-refresh").addEventListener("click", reloadAll);
  document.getElementById("campaign-catalog-refresh").addEventListener("click", refreshCampaignCatalog);
  document.getElementById("admin-audit-refresh").addEventListener("click", reloadAudit);
  document.getElementById("pool-refresh").addEventListener("click", reloadPool);
  document.getElementById("pool-import").addEventListener("click", openPoolImportModal);
  document.getElementById("pool-delete").addEventListener("click", deletePoolSelected);
  document.getElementById("pool-check").addEventListener("click", checkPool);
  document.getElementById("pool-th-chk").addEventListener("change", (e) => {
    poolSelected.clear();
    if (e.target.checked) poolProxies.forEach((proxy) => poolSelected.add(proxy.raw));
    renderPool();
  });
  document.getElementById("convert-pool-refresh").addEventListener("click", reloadConvertPool);
  document.getElementById("convert-pool-import").addEventListener("click", openConvertPoolImportModal);
  document.getElementById("convert-pool-delete").addEventListener("click", deleteConvertPoolSelected);
  document.getElementById("convert-pool-check").addEventListener("click", checkConvertPool);
  document.getElementById("convert-pool-th-chk").addEventListener("change", (e) => {
    convertPoolSelected.clear();
    if (e.target.checked) {
      convertPoolProxies.forEach((proxy) => convertPoolSelected.add(proxy.raw));
    }
    renderConvertPool();
  });
  document.getElementById("settings-save").addEventListener("click", saveSettings);
  try { await reloadAll(); } catch (e) { toast(e.message, "error"); }
  await loadSettings();
  await reloadCampaignCatalogStatus();
  try { await reloadPool(); } catch (e) { toast(e.message, "error"); }
  try { await reloadConvertPool(); } catch (e) { toast(e.message, "error"); }
}
init();
