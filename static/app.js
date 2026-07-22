/* Twitch Farmer — frontend logic.
   Pure vanilla JS, no external deps. */

// ─── i18n ────────────────────────────────────────────────────────────────
const LANG = {
  en: {
    brand: "Twitch Farmer",
    admin: "Admin", logout: "Logout", panel_users: "Panel users",
    backup_now: "Backup now", new_user: "User", thread_limit: "Threads",
    subscription_until: "Subscription", security_log: "Security log",
    all_accounts: "Accounts", proxies: "Proxies", campaigns_tab: "Campaigns", farm: "Farm",
    convert_tab: "Convert", convert_all: "Convert all web tokens",
    convert_selected: "Convert selected", stop: "Stop",
    web_needs_convert: "token type: web — conversion required",
    mobile_tag: "mobile", invalid_tag: "invalid", check_btn: "Check",
    check_campaigns: "Campaigns", check_drops_states: "Drops (farmed/received/connected)",
    check_drops_note: "Shows farmed, received and connected states.",
    check_token_type: "Token type", scope_selected: "Selected accounts",
    scope_all: "All accounts", run: "Run", drop_connected: "Connected",
    drop_farmed: "Farmed", drop_received: "Received",
    convert_minted: "Minted", convert_bad_password: "Bad password",
    convert_timeout: "Timeout", convert_progress_label: "Conversion progress",
    convert_2fa: "2FA required",
    convert_started: "Conversion started…",
    reason_proxy: "proxy", reason_network: "network", reason_flow: "flow",
    checking_label: "Check progress", convert_info: "Convert web tokens to mobile tokens using Twitch device authorization.",
    convert_accounts: "Web-token accounts", convert_results: "Results",
    search: "Search", login_ph: "Login", token_ph: "Token", season_ph: "Season",
    filters: "Filters", clear: "Clear",
    role: "Role", campaign: "Campaign", progress: "Progress", season: "Season",
    actions: "Actions",
    select_all: "Select All", deselect_all: "Deselect All",
    import_accounts: "Import", export_selected: "Export",
    set_role_selected: "Set Role", accounts: "accounts",
    import_proxies: "Import", check_proxies: "Check",
    proxies_import_title: "Import Proxies", proxy_data: "Proxy list",
    proxy_status_unknown: "Unknown", proxy_status_valid: "Valid",
    proxy_status_invalid: "Invalid", proxy_status_unsupported: "Unsupported",
    index: "#", proxy: "Proxy", host: "Host", port: "Port",
    auth_user: "Auth user", status: "Status", latency: "Latency (ms)",
    no_proxies_hint: "No proxies yet — click Import.",
    confirm_delete_proxies: "Delete selected proxies?",
    confirm_delete_accounts: "Delete selected accounts?",
    proxies_checked: "Proxy check complete", proxies_imported: "Imported {} proxies",
    selected: "selected", details: "Details",
    credentials: "Credentials", campaign_progress: "Progress",
    copy_login_pass_token: "Copy login:password:token",
    copy_login_pass: "Copy login:password",
    check_drops: "Check drops",
    checking_drops: "Checking drops…",
    drops_checked: "Drops checked",
    drop_claimed: "Claimed",
    drop_ready: "Ready to claim",
    drop_in_progress: "In progress",
    drop_awarded: "Awarded",
    token_invalid: "Token is invalid",
    edit: "Edit", delete: "Delete",
    edit_account: "Edit Account", save_changes: "Save", cancel: "Cancel",
    login: "Login", password: "Password", token: "Token",
    name: "Name",
    import_title: "Import Accounts",
    format_presets: "Presets", custom_template: "Template",
    data_label: "Data", load_from_file: "Load from File",
    import_btn: "Import",
    bulk_role_title: "Set Role",
    bulk_role_desc: "Set role for", bulk_role_desc2: "accounts",
    apply: "Apply", export_format: "Format",
    placeholders: "Placeholders",
    export_btn: "Export",
    progress_filter: "Progress Filter",
    comparison: "Comparison", value: "Value",
    none_disabled: "None", greater_than: "Greater than",
    less_than: "Less than", equal_to: "Equal",
    confirm_delete: "Confirm delete",
    delete_account_q: "Delete '{}'?",
    warning: "Warning", no_accounts_selected: "No accounts selected",
    success: "Done", exported: "Exported {} accounts",
    error: "Error", save_failed: "Save failed: {}",
    export_failed: "Export failed: {}",
    import_complete: "Import complete",
    imported: "Imported {} accounts",
    duplicates_skipped: "{} duplicates skipped",
    no_parsed: "Nothing parsed",
    add_nicknames: "Add nicknames", paste_nicknames: "One per line",
    streamer_ph: "streamer1\nstreamer2",
    add: "Add", clear_input: "Clear",
    import_from_file: "From File", load_txt: "Load TXT",
    current_list: "List", search_ph: "Search",
    delete_selected: "Delete Selected",
    clear_all: "Clear All", save: "Save",
    streamer_singular: "streamer", streamer_plural: "streamers",
    confirm_clear: "Clear all?",
    added_nicks: "Added {}.\n{} duplicates.",
    nickname: "Nickname", lang_btn: "RU",
    set_role: "Set Role", drops: "Drops",
    start_farm: "Start Farm", stop_farm: "Stop Farm",
    stagger_delay: "Stagger (s)",
    farm_running: "Running", farm_stopped: "Stopped",
    farm_active_summary: "Farm active · {} accounts · {} campaigns",
    farm_stopped_summary: "Farm stopped",
    farm_converting: "Converting web tokens… ({})",
    farm_conversion_progress: "Converting web tokens… ({} / {})",
    farm_auto_started: "Farm started after conversion ({} accounts)",
    convert_concurrency: "Conversion threads",
    convert_stage_auth_started: "auth flow started",
    convert_stage_authorization_received: "authorization received",
    convert_stage_token_received: "token received",
    over_limit: "Out of limit", over_limit_hint: "not started (thread limit)",
    farmed: "Farmed",
    over_limit_toast: "Thread limit {limit} — {n} account(s) out of limit, not started",
    farm_log: "Log", no_logs: "No logs yet", showing: "showing {} of {}",
    starting_farm: "Starting farm…", checking_proxies: "Checking…",
    watched_min: "min",
    configs: "Configs", new_config: "New",
    rename: "Rename", delete_config: "Delete config",
    config_name_q: "Config name",
    confirm_delete_cfg: "Delete '{}'?",
    activate: "Activate", active_config: "Active",
    campaigns_popup: "Campaigns",
    campaign_catalog: "Active campaign catalog",
    campaigns_updated: "Updated: {}",
    campaigns_search_ph: "Search campaigns, games, owners or rewards",
    no_campaigns: "No active campaigns found.",
    campaign_owner: "Owner",
    campaign_game: "Game",
    campaign_ends: "Ends",
    campaign_linked: "Account linked",
    campaign_selected: "Selected",
    rewards: "Rewards",
    no_accounts_hint: "No accounts yet — click Import to add some.",
    copied: "Copied",
  },
  ru: {
    brand: "Twitch Farmer",
    admin: "Админ", logout: "Выход", panel_users: "Пользователи панели",
    backup_now: "Бэкап сейчас", new_user: "Пользователь", thread_limit: "Потоки",
    subscription_until: "Подписка", security_log: "Журнал безопасности",
    all_accounts: "Аккаунты", proxies: "Прокси", campaigns_tab: "Кампании", farm: "Фарм",
    convert_tab: "Конвертация", convert_all: "Конвертировать все web-токены",
    convert_selected: "Конвертировать выбранные", stop: "Остановить",
    web_needs_convert: "тип токена: веб — нужна конвертация",
    mobile_tag: "mobile", invalid_tag: "невалиден", check_btn: "Проверить",
    check_campaigns: "Кампании", check_drops_states: "Дропы (отфармлены/получены/подключены)",
    check_drops_note: "Показывает отфармленные, полученные и подключенные состояния.",
    check_token_type: "Тип токена", scope_selected: "Выбранные аккаунты",
    scope_all: "Все аккаунты", run: "Запустить", drop_connected: "Подключен",
    drop_farmed: "Отфармлен", drop_received: "Получен",
    convert_minted: "Получено токенов", convert_bad_password: "Неверный пароль",
    convert_timeout: "Таймаут", convert_progress_label: "Прогресс конвертации",
    convert_2fa: "Нужен 2FA код",
    convert_started: "Конвертация запущена…",
    reason_proxy: "прокси", reason_network: "сеть", reason_flow: "поток",
    checking_label: "Прогресс проверки", convert_info: "Конвертация web-токенов в мобильные через авторизацию Twitch.",
    convert_accounts: "Аккаунты с web-токенами", convert_results: "Результаты",
    search: "Поиск", login_ph: "Логин", token_ph: "Токен", season_ph: "Сезон",
    filters: "Фильтры", clear: "Сброс",
    role: "Роль", campaign: "Кампания", progress: "Прогресс", season: "Сезон",
    actions: "Действия",
    select_all: "Выделить всё", deselect_all: "Снять",
    import_accounts: "Импорт", export_selected: "Экспорт",
    set_role_selected: "Роль", accounts: "аккаунтов",
    import_proxies: "Импорт", check_proxies: "Проверить",
    proxies_import_title: "Импорт прокси", proxy_data: "Список прокси",
    proxy_status_unknown: "Неизвестно", proxy_status_valid: "Рабочий",
    proxy_status_invalid: "Недоступен", proxy_status_unsupported: "Не поддерживается",
    index: "#", proxy: "Прокси", host: "Хост", port: "Порт",
    auth_user: "Пользователь", status: "Статус", latency: "Задержка (мс)",
    no_proxies_hint: "Прокси пока нет — нажмите «Импорт».",
    confirm_delete_proxies: "Удалить выбранные прокси?",
    confirm_delete_accounts: "Удалить выбранные аккаунты?",
    proxies_checked: "Проверка прокси завершена", proxies_imported: "Импортировано прокси: {}",
    selected: "выбрано", details: "Детали",
    credentials: "Данные", campaign_progress: "Прогресс",
    copy_login_pass_token: "Копировать логин:пароль:токен",
    copy_login_pass: "Копировать логин:пароль",
    check_drops: "Проверить дропы",
    checking_drops: "Проверяю дропы…",
    drops_checked: "Дропы проверены",
    drop_claimed: "Заклеймлено",
    drop_ready: "Готово к клейму",
    drop_in_progress: "Качается",
    drop_awarded: "Получено",
    token_invalid: "Токен невалиден",
    edit: "Изменить", delete: "Удалить",
    edit_account: "Редактирование", save_changes: "Сохранить", cancel: "Отмена",
    login: "Логин", password: "Пароль", token: "Токен",
    name: "Название",
    import_title: "Импорт",
    format_presets: "Пресеты", custom_template: "Шаблон",
    data_label: "Данные", load_from_file: "Загрузить из файла",
    import_btn: "Импортировать",
    bulk_role_title: "Установить роль",
    bulk_role_desc: "Для", bulk_role_desc2: "аккаунтов",
    apply: "Применить", export_format: "Формат",
    placeholders: "Плейсхолдеры",
    export_btn: "Экспортировать",
    progress_filter: "Фильтр прогресса",
    comparison: "Сравнение", value: "Значение",
    none_disabled: "Нет", greater_than: "Больше",
    less_than: "Меньше", equal_to: "Равно",
    confirm_delete: "Удалить?",
    delete_account_q: "Удалить '{}'?",
    warning: "Внимание", no_accounts_selected: "Не выбрано",
    success: "Готово", exported: "Экспортировано {}",
    error: "Ошибка", save_failed: "Ошибка: {}",
    export_failed: "Ошибка: {}",
    import_complete: "Импорт",
    imported: "Импортировано {}",
    duplicates_skipped: "Пропущено {} дубликатов",
    no_parsed: "Не распознано",
    add_nicknames: "Добавить ники", paste_nicknames: "Один на строку",
    streamer_ph: "стример1\nстример2",
    add: "Добавить", clear_input: "Очистить",
    import_from_file: "Из файла", load_txt: "Загрузить TXT",
    current_list: "Список", search_ph: "Поиск",
    delete_selected: "Удалить выбранное",
    clear_all: "Очистить", save: "Сохранить",
    streamer_singular: "стример", streamer_plural: "стримеров",
    confirm_clear: "Очистить всё?",
    added_nicks: "Добавлено {}.\n{} дубликатов.",
    nickname: "Ник", lang_btn: "EN",
    set_role: "Роль", drops: "Дропы",
    start_farm: "Запустить", stop_farm: "Остановить",
    stagger_delay: "Задержка (с)",
    farm_running: "Работает", farm_stopped: "Остановлен",
    farm_active_summary: "Фарм активен · {} аккаунтов · кампаний: {}",
    farm_stopped_summary: "Фарм остановлен",
    farm_converting: "Конвертация web-токенов… ({} шт)",
    farm_conversion_progress: "Конвертация web-токенов… ({} / {})",
    farm_auto_started: "Фарм запущен после конвертации ({} аккаунтов)",
    convert_concurrency: "Потоки конвертации",
    convert_stage_auth_started: "аутх флоу запущен",
    convert_stage_authorization_received: "авторизация получена",
    convert_stage_token_received: "токен получен",
    over_limit: "Вне лимита", over_limit_hint: "не запущен (лимит потоков)",
    farmed: "Отфармлено",
    over_limit_toast: "Лимит потоков {limit} — {n} аккаунт(ов) вне лимита, не запущены",
    farm_log: "Лог", no_logs: "Нет логов", showing: "показано {} из {}",
    starting_farm: "Запуск фарма…", checking_proxies: "Проверка…",
    watched_min: "мин",
    configs: "Конфиги", new_config: "Новый",
    rename: "Переименовать", delete_config: "Удалить конфиг",
    config_name_q: "Название",
    confirm_delete_cfg: "Удалить '{}'?",
    activate: "Активировать", active_config: "Активный",
    campaigns_popup: "Кампании",
    campaign_catalog: "Активные кампании",
    campaigns_updated: "Обновлено: {}",
    campaigns_search_ph: "Поиск по играм, кампаниям, владельцам и наградам",
    no_campaigns: "Активные кампании не найдены.",
    campaign_owner: "Владелец",
    campaign_game: "Игра",
    campaign_ends: "До",
    campaign_linked: "Аккаунт привязан",
    campaign_selected: "Выбрано",
    rewards: "Награды",
    no_accounts_hint: "Аккаунтов пока нет — нажмите «Импорт».",
    copied: "Скопировано",
  },
};

let currentLang = localStorage.getItem("lang") || "en";
const t = (k, ...args) => {
  let s = (LANG[currentLang] && LANG[currentLang][k]) || k;
  for (const a of args) s = s.replace("{}", a);
  return s;
};

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    const value = t(el.dataset.i18nPh);
    el.setAttribute("placeholder", value);
    el.setAttribute("data-i18n-ph-value", value);
  });
  document.documentElement.lang = currentLang;
}

// ─── Toast ──────────────────────────────────────────────────────────────
const toastEl = document.getElementById("toast");
let toastTimer = null;
function toast(msg, kind = "") {
  toastEl.textContent = msg;
  toastEl.className = "toast show " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastEl.className = "toast"), 2200);
}

// ─── API ────────────────────────────────────────────────────────────────
let CSRF_TOKEN = "";

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
    // предпочитаем токен из /api/auth/me, cookie — как запасной вариант
    headers["X-CSRF-Token"] = CSRF_TOKEN || getCookie("csrf");
  }
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    // сессия истекла / нет входа → на страницу логина
    window.location.href = "/login";
    throw new Error("401: authentication required");
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

// ─── State ──────────────────────────────────────────────────────────────
const state = {
  accounts: [],
  proxies: [],
  proxySelected: new Set(),
  filtered: [],
  selected: new Set(),       // logins
  detailLogin: null,
  dropCheck: { login: null, loading: false, result: null },
  filters: {
    login: "", token: "",
    seasonText: "",
    role: new Set(), camp: new Set(), sea: new Set(),
    prog: { op: null, v: 50 },
  },
  campaigns: {
    fetched_at: 0, campaigns: [], selected: new Set(), expandedGames: new Set(),
  },
  check: { running: false, done: 0, total: 0 },
  convert: {
    running: false, done: 0, total: 0, minted: 0,
    bad_password: 0, twofa: 0, timeout: 0, error: 0, results: [],
  },
  farm: { running: false, starting: false, converting: false, launchCount: null, cards: new Map(), logs: [], cardStartedAt: new Map(), overLimit: new Set() },
  ws: null,
};

const CONVERT_CONCURRENCY_KEY = "convertConcurrency";

function clampConvertConcurrency(value) {
  return Math.max(1, Math.min(32, Number(value) || 3));
}

function getConvertConcurrency() {
  const input = document.getElementById("convert-concurrency");
  const value = clampConvertConcurrency(
    input ? input.value : localStorage.getItem(CONVERT_CONCURRENCY_KEY)
  );
  if (input) input.value = String(value);
  localStorage.setItem(CONVERT_CONCURRENCY_KEY, String(value));
  return value;
}

function bestCampaign(acc) {
  const camps = acc.campaigns || [];
  const named = camps.filter((c) => (c.name || "").trim());
  if (!named.length) return camps[0] || { name: "", progress: 0, season: "", drops: {} };
  return named.reduce((a, b) => ((b.progress || 0) > (a.progress || 0) ? b : a));
}

function pctClass(p) { return p < 33 ? "pct-r" : p < 66 ? "pct-a" : "pct-g"; }
function pctColor(p) {
  p = Math.max(0, Math.min(100, Number(p) || 0));
  const v = getComputedStyle(document.documentElement);
  return p < 33 ? v.getPropertyValue("--red") : p < 66 ? v.getPropertyValue("--amber") : v.getPropertyValue("--green");
}

// ─── Tabs ───────────────────────────────────────────────────────────────
function switchTab(name) {
  if (name === "proxies" && ME && ME.role !== "admin" && ME.proxy_mode === "pool") {
    name = "accounts";
  }
  localStorage.setItem("activeTab", name);
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  document.querySelectorAll(".page").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.page !== name)
  );
  const showAccountControls = name === "accounts";
  document.querySelectorAll(
    ".sidebar .search-section, .sidebar .filters-section, .sidebar .acct-actions"
  ).forEach((s) => {
    s.style.display = showAccountControls ? "" : "none";
  });
  document.getElementById("status").style.display = showAccountControls ? "" : "none";
  const titleEl = document.getElementById("page-title");
  const activeTab = document.querySelector(`.tab[data-tab="${name}"]`);
  if (titleEl && activeTab) {
    const label = activeTab.querySelector(".rail-label");
    titleEl.textContent = (label ? label.textContent : activeTab.textContent).trim();
  }
  if (name === "convert") {
    renderConvertAccounts();
    loadConvertState();
  }
}

function applyProxyModeVisibility() {
  const hide = ME && ME.role !== "admin" && ME.proxy_mode === "pool";
  const tab = document.querySelector('.tab[data-tab="proxies"]');
  const page = document.querySelector('.page[data-page="proxies"]');
  if (tab) tab.classList.toggle("hidden", !!hide);
  if (page) page.classList.toggle("hidden", !!hide);
  if (hide && localStorage.getItem("activeTab") === "proxies") {
    localStorage.setItem("activeTab", "accounts");
  }
}

document.querySelectorAll(".tab").forEach((b) =>
  b.addEventListener("click", () => switchTab(b.dataset.tab))
);

// ─── Accounts table ─────────────────────────────────────────────────────
function applyFilters() {
  const f = state.filters;
  const fl = (f.login || "").toLowerCase();
  const ft = (f.token || "").toLowerCase();
  state.filtered = state.accounts.filter((a) => {
    if (fl && !(a.login || "").toLowerCase().includes(fl)) return false;
    if (ft && !(a.token || "").toLowerCase().includes(ft)) return false;
    if (f.role.size && !f.role.has(a.role || "")) return false;
    const c = bestCampaign(a);
    const campaigns = a.campaigns || [];
    if (f.seasonText && !campaigns.some((x) =>
      String(x.season || "").toLowerCase().includes(f.seasonText)
    )) return false;
    if (f.camp.size && !campaigns.some((x) => f.camp.has(x.name || ""))) return false;
    if (f.sea.size && !campaigns.some((x) => f.sea.has(x.season || ""))) return false;
    if (f.prog.op) {
      const p = c.progress || 0;
      if (f.prog.op === ">" && !(p > f.prog.v)) return false;
      if (f.prog.op === "<" && !(p < f.prog.v)) return false;
      if (f.prog.op === "=" && !(p === f.prog.v)) return false;
    }
    return true;
  });
  renderTable();
  updateStatus();
  updateFilterUI();
}

function renderTable() {
  const body = document.getElementById("acc-body");
  const emptyEl = document.getElementById("acc-empty");
  body.innerHTML = "";
  emptyEl.classList.toggle("hidden", state.filtered.length > 0);
  for (const a of state.filtered) {
    const c = bestCampaign(a);
    const p = Math.max(0, Math.min(100, Number(c.progress) || 0));
    const tr = document.createElement("tr");
    tr.dataset.login = a.login;
    if (a.login === state.detailLogin) tr.classList.add("selected");
    const checked = state.selected.has(a.login) ? "checked" : "";
    const tokenTag = a.token_type === "web"
      ? `<span class="token-tag token-web" data-i18n="web_needs_convert">${escapeHtml(t("web_needs_convert"))}</span>`
      : a.token_type === "mobile"
        ? `<span class="token-tag token-mobile">${escapeHtml(t("mobile_tag"))}</span>`
        : a.token_type === "invalid"
          ? `<span class="token-tag token-invalid">${escapeHtml(t("invalid_tag"))}</span>`
          : "";
    const summary = a.check_snapshot?.drops_summary || {};
    const dropSummary = summary.farmed || summary.received || summary.in_progress
      ? `<span class="drop-summary">${t("drop_farmed")}: ${summary.farmed || 0} · ${t("drop_received")}: ${summary.received || 0}</span>`
      : a.check_snapshot?.valid
        ? `<span class="drop-summary">${escapeHtml(t("drop_connected"))}</span>`
        : "";
    tr.innerHTML = `
      <td class="col-chk"><input type="checkbox" data-act="chk" ${checked}></td>
      <td class="login-cell">${escapeHtml(a.login)}${tokenTag}${dropSummary}</td>
      <td>${a.role ? `<span class="role-pill">${escapeHtml(a.role)}</span>` : "—"}</td>
      <td>${escapeHtml(c.name || "—")}</td>
      <td class="num">
        <span class="pct-cell ${pctClass(p)}">
          <span class="pct-bar"><span style="width:${p}%; background:${pctColor(p)};"></span></span>
          ${p}%
        </span>
      </td>
      <td>${escapeHtml(c.season || "")}</td>
    `;
    body.appendChild(tr);
  }
  updateSelBtn();
  updateFarmLaunchCount();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function normDrop(value) {
  if (value && typeof value === "object") {
    return {
      current: Number(value.current) || 0,
      required: Number(value.required) || 0,
      progress: Number(value.progress) || 0,
    };
  }
  return { current: Number(value) || 0, required: 0, progress: 0 };
}

document.getElementById("acc-body").addEventListener("click", (e) => {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const login = tr.dataset.login;
  if (e.target.dataset.act === "chk") {
    if (e.target.checked) state.selected.add(login);
    else state.selected.delete(login);
    updateStatus();
    updateSelBtn();
    updateFarmLaunchCount();
    return;
  }
  state.detailLogin = login;
  document.querySelectorAll("#acc-body tr").forEach((r) =>
    r.classList.toggle("selected", r.dataset.login === login)
  );
  showDetail();
});

document.getElementById("acc-body").addEventListener("dblclick", (e) => {
  const tr = e.target.closest("tr");
  if (!tr || e.target.dataset.act === "chk") return;
  const acc = state.accounts.find((a) => a.login === tr.dataset.login);
  if (acc && (acc.campaigns || []).filter((c) => c.name).length > 0) {
    openCampaignsModal(acc);
  }
});

document.getElementById("acc-body").addEventListener("contextmenu", (e) => {
  const tr = e.target.closest("tr");
  if (!tr) return;
  e.preventDefault();
  state.detailLogin = tr.dataset.login;
  showDetail();
  const acc = state.accounts.find((a) => a.login === tr.dataset.login);
  if (!acc) return;
  openMenu(e.clientX, e.clientY, [
    { label: t("edit"), onClick: () => openEditModal(acc) },
    ...((acc.campaigns || []).filter((c) => c.name).length
      ? [{ label: `↗ ${t("campaigns_popup")}`, onClick: () => openCampaignsModal(acc) }]
      : []),
    { sep: true },
    { label: t("delete"), danger: true, onClick: () => deleteAccount(acc) },
  ]);
});

document.getElementById("th-chk").addEventListener("change", (e) => {
  const on = e.target.checked;
  for (const a of state.filtered) {
    if (on) state.selected.add(a.login);
    else state.selected.delete(a.login);
  }
  renderTable();
  updateStatus();
  updateFarmLaunchCount();
});

function updateStatus() {
  const n = state.filtered.length;
  const total = state.accounts.length;
  const sel = state.selected.size;
  const parts = [`<b>${n}</b>${n !== total ? ` / ${total}` : ""} ${t("accounts")}`];
  if (sel) parts.push(`<b>${sel}</b> ${t("selected")}`);
  document.getElementById("status").innerHTML = parts.join(" · ");
}

function updateSelBtn() {
  const btn = document.getElementById("sel-btn");
  const n = state.filtered.length;
  if (!n) { btn.textContent = t("select_all"); return; }
  const allOn = state.filtered.every((a) => state.selected.has(a.login));
  btn.textContent = allOn ? `${t("deselect_all")} (${n})` : `${t("select_all")} (${n})`;
  btn.classList.toggle("primary", allOn);
  btn.classList.toggle("outline", !allOn);
}

document.getElementById("sel-btn").addEventListener("click", () => {
  const allOn = state.filtered.every((a) => state.selected.has(a.login));
  for (const a of state.filtered) {
    if (allOn) state.selected.delete(a.login);
    else state.selected.add(a.login);
  }
  renderTable();
  updateStatus();
  updateFarmLaunchCount();
});

// ─── Detail panel ───────────────────────────────────────────────────────
function dropStatusLabel(status) {
  return {
    claimed: t("drop_received"),
    ready: t("drop_farmed"),
    in_progress: t("drop_in_progress"),
    awarded: t("drop_awarded"),
  }[status] || status;
}

function renderCheckedDrop(drop) {
  const status = drop.status || "in_progress";
  const progress = status === "in_progress"
    ? ` ${drop.current || 0}/${drop.required || 0} ${t("watched_min")}`
    : "";
  return `<span class="d-drop-status ${escapeHtml(status)}">` +
    `<span>${escapeHtml(dropStatusLabel(status))}</span>` +
    `<span>${escapeHtml(progress)}</span></span>`;
}

function showDetail() {
  const acc = state.accounts.find((a) => a.login === state.detailLogin);
  if (!acc) return clearDetail();
  if (state.dropCheck.login !== acc.login) {
    state.dropCheck = { login: acc.login, loading: false, result: null };
  }
  const c = bestCampaign(acc);
  const p = Math.max(0, Math.min(100, Number(c.progress) || 0));
  document.getElementById("d-login").textContent = acc.login || "—";
  const roleEl = document.getElementById("d-role");
  if (acc.role) { roleEl.textContent = acc.role; roleEl.classList.remove("hidden"); }
  else roleEl.classList.add("hidden");
  document.getElementById("d-pct").textContent = `${p}%`;
  document.getElementById("d-pct").style.color = pctColor(p);
  const fill = document.getElementById("d-bar");
  fill.style.width = p + "%";
  fill.style.background = pctColor(p);
  document.getElementById("d-cname").textContent = c.name || "—";
  const seaEl = document.getElementById("d-sea");
  if (c.season) { seaEl.textContent = c.season; seaEl.classList.remove("hidden"); }
  else seaEl.classList.add("hidden");
  const password = acc.password || "";
  const token = acc.token || "";
  document.getElementById("d-pass").textContent = password || "—";
  document.getElementById("d-pass").dataset.raw = password;
  document.getElementById("d-tok").textContent = token || "—";
  document.getElementById("d-tok").dataset.raw = token;
  document.getElementById("d-copy-login-pass-token-value").textContent =
    `${acc.login || "—"}:${password}:${token}`;
  document.getElementById("d-copy-login-pass-value").textContent =
    `${acc.login || "—"}:${password}`;

  const checked = state.dropCheck.result;
  const camps = (acc.campaigns || []).filter((x) => x.name).map((x) => ({ ...x }));
  const campKey = (name) => String(name || "").trim().toLowerCase();
  const checkedMatchesCampaign = (checkedCampaign, campaign) => {
    const name = campKey(checkedCampaign.name);
    if (!name) return false;
    if (name === campKey(campaign.name)) return true;
    if (name === campKey(campaign.season)) return true;
    return Object.keys(campaign.drops || {}).some((key) => campKey(key) === name);
  };
  for (const checkedCampaign of checked?.campaigns || []) {
    if (!camps.some((campaign) => checkedMatchesCampaign(checkedCampaign, campaign))) {
      camps.push({ name: checkedCampaign.name, progress: 0, season: "", drops: {} });
    }
  }
  document.getElementById("all-camps-btn").classList.toggle("hidden", camps.length < 1);
  const campaignsBox = document.getElementById("d-campaigns-box");
  const campaignsList = document.getElementById("d-campaigns-list");
  campaignsList.innerHTML = "";
  if (camps.length) {
    campaignsBox.classList.remove("hidden");
    for (const campaign of camps) {
      const campaignProgress = Math.max(0, Math.min(100, Number(campaign.progress) || 0));
      const campaignRow = document.createElement("div");
      campaignRow.className = "d-campaign";
      const drops = Object.entries(campaign.drops || {});
      const checkedCampaign = checked?.campaigns?.find(
        (item) => checkedMatchesCampaign(item, campaign)
      );
      const awardedNames = new Set(checked?.awarded || []);
      const statusDrops = (checkedCampaign?.drops || []).map((drop) =>
        awardedNames.has(drop.name) ? { ...drop, status: "awarded" } : drop
      );
      campaignRow.innerHTML = `
        <div class="d-campaign-head">
          <span>${escapeHtml(campaign.name)}</span>
          <span class="${pctClass(campaignProgress)}">${campaignProgress}%</span>
        </div>
        ${campaign.season ? `<div class="d-campaign-season">${escapeHtml(campaign.season)}</div>` : ""}
        <div class="d-bar"><div class="d-bar-fill" style="width:${campaignProgress}%; background:${pctColor(campaignProgress)};"></div></div>
        ${statusDrops.length
          ? `<div class="d-campaign-drops">${statusDrops.map((drop) =>
              `<div class="d-drop-row"><span>${escapeHtml(drop.name)}</span>` +
              `${renderCheckedDrop(drop)}</div>`
            ).join("")}</div>`
          : drops.length ? `<div class="d-campaign-drops">${
              drops.map(([name, value]) => {
                const d = normDrop(value);
                const amount = d.required
                  ? `${d.current}/${d.required} ${t("watched_min")}`
                  : `${d.current} ${t("watched_min")}`;
                return `<div class="d-drop-row"><span>${escapeHtml(name)}</span><span>` +
                  `${escapeHtml(amount)}${d.required ? ` · ${d.progress}%` : ""}</span>` +
                  `${d.required ? `<div class="d-bar"><div class="d-bar-fill" style="width:${Math.min(100, Math.max(0, d.progress))}%; background:${pctColor(d.progress)};"></div></div>` : ""}</div>`;
              }
              ).join("")
            }</div>` : ""}
      `;
      campaignsList.appendChild(campaignRow);
    }
    if (checked?.awarded?.length) {
      const awarded = document.createElement("div");
      awarded.className = "d-awarded";
      awarded.innerHTML = `<span class="d-drop-status awarded">${escapeHtml(t("drop_awarded"))}</span> ` +
        checked.awarded.map((name) => escapeHtml(name)).join(", ");
      campaignsList.appendChild(awarded);
    }
  } else {
    campaignsBox.classList.add("hidden");
  }

  const dropsBox = document.getElementById("drops-box");
  const dropsList = document.getElementById("drops-list");
  dropsList.innerHTML = "";
  const drops = c.drops || {};
  if (Object.keys(drops).length) {
    dropsBox.classList.remove("hidden");
    for (const [k, v] of Object.entries(drops)) {
      const d = normDrop(v);
      const row = document.createElement("div");
      row.className = "drop-row";
      const amount = d.required
        ? `${d.current}/${d.required} ${t("watched_min")}`
        : `${d.current} ${t("watched_min")}`;
      row.innerHTML = `<span>${escapeHtml(k)}</span><span class="v">${escapeHtml(amount)}${d.required ? ` · ${d.progress}%` : ""}</span>`;
      dropsList.appendChild(row);
    }
  } else dropsBox.classList.add("hidden");
}
function clearDetail() {
  document.getElementById("d-login").textContent = "—";
  document.getElementById("d-role").classList.add("hidden");
  document.getElementById("d-pct").textContent = "0%";
  document.getElementById("d-bar").style.width = "0%";
  document.getElementById("d-cname").textContent = "—";
  document.getElementById("d-sea").classList.add("hidden");
  document.getElementById("d-campaigns-box").classList.add("hidden");
  document.getElementById("d-campaigns-list").innerHTML = "";
  document.getElementById("drops-box").classList.add("hidden");
  document.getElementById("d-pass").textContent = "—";
  document.getElementById("d-pass").dataset.raw = "";
  document.getElementById("d-tok").textContent = "—";
  document.getElementById("d-tok").dataset.raw = "";
  document.getElementById("d-copy-login-pass-token-value").textContent = "—";
  document.getElementById("d-copy-login-pass-value").textContent = "—";
  state.dropCheck = { login: null, loading: false, result: null };
  document.getElementById("all-camps-btn").classList.add("hidden");
}
document.getElementById("d-pass-copy").addEventListener("click", () => copyEl("d-pass"));
document.getElementById("d-tok-copy").addEventListener("click", () => copyEl("d-tok"));
function copyEl(id) {
  const v = document.getElementById(id).dataset.raw || "";
  copyText(v);
}
function copyText(v) {
  if (!v) return;
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(v).then(
      () => toast(t("copied"), "success"),
      () => toast(t("error"), "error")
    );
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = v;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (_) {}
  textarea.remove();
  toast(copied ? t("copied") : t("error"), copied ? "success" : "error");
}
function copySelectedAccount(format) {
  const acc = state.accounts.find((a) => a.login === state.detailLogin);
  if (!acc) return;
  const password = acc.password || "";
  const token = acc.token || "";
  copyText(
    format === "login-pass-token"
      ? `${acc.login}:${password}:${token}`
      : `${acc.login}:${password}`
  );
}
document.getElementById("d-copy-login-pass-token-btn").addEventListener(
  "click", () => copySelectedAccount("login-pass-token")
);
document.getElementById("d-copy-login-pass-btn").addEventListener(
  "click", () => copySelectedAccount("login-pass")
);
document.getElementById("edit-btn").addEventListener("click", () => {
  const acc = state.accounts.find((a) => a.login === state.detailLogin);
  if (acc) openEditModal(acc);
});
document.getElementById("del-btn").addEventListener("click", () => {
  const acc = state.accounts.find((a) => a.login === state.detailLogin);
  if (acc) deleteAccount(acc);
});
document.getElementById("all-camps-btn").addEventListener("click", () => {
  const acc = state.accounts.find((a) => a.login === state.detailLogin);
  if (acc) openCampaignsModal(acc);
});

// ─── Filters ────────────────────────────────────────────────────────────
document.getElementById("f-login").addEventListener("input", (e) => {
  state.filters.login = e.target.value; applyFilters();
});
document.getElementById("f-token").addEventListener("input", (e) => {
  state.filters.token = e.target.value; applyFilters();
});
document.getElementById("f-season").addEventListener("input", (e) => {
  state.filters.seasonText = e.target.value.trim().toLowerCase();
  applyFilters();
});
document.getElementById("clear-filters").addEventListener("click", () => {
  state.filters.role.clear(); state.filters.camp.clear(); state.filters.sea.clear();
  state.filters.seasonText = "";
  document.getElementById("f-season").value = "";
  state.filters.prog = { op: null, v: 50 };
  applyFilters();
});
document.getElementById("btn-role").addEventListener("click", (e) =>
  openMultiFilter(e.currentTarget, [...new Set(state.accounts.map(a => a.role || ""))], state.filters.role)
);
document.getElementById("btn-camp").addEventListener("click", (e) =>
  openMultiFilter(e.currentTarget, [...new Set(state.accounts.flatMap(a => (a.campaigns || []).map(c => c.name || "")))], state.filters.camp)
);
document.getElementById("btn-sea").addEventListener("click", (e) =>
  openMultiFilter(e.currentTarget, [...new Set(state.accounts.flatMap(a => (a.campaigns || []).map(c => c.season || "")))], state.filters.sea)
);
document.getElementById("btn-prog").addEventListener("click", () => openProgressModal());

function openMultiFilter(anchor, vals, fset) {
  const sorted = vals.sort();
  const items = sorted.map((v) => ({
    checkbox: true,
    checked: fset.has(v),
    label: v || "(empty)",
    onToggle: (on) => {
      if (on) fset.add(v); else fset.delete(v);
      applyFilters();
    },
  }));
  const r = anchor.getBoundingClientRect();
  openMenu(r.right - 200, r.bottom + 4, items, true);
}

function updateFilterUI() {
  const f = state.filters;
  const any = f.role.size + f.camp.size + f.sea.size
    + (f.seasonText ? 1 : 0) + (f.prog.op ? 1 : 0);
  document.getElementById("clear-filters").classList.toggle("hidden", any === 0);
  document.getElementById("btn-role").classList.toggle("on", f.role.size > 0);
  document.getElementById("btn-camp").classList.toggle("on", f.camp.size > 0);
  document.getElementById("btn-sea").classList.toggle("on", f.sea.size > 0);
  document.getElementById("btn-prog").classList.toggle("on", !!f.prog.op);
}

// ─── Generic menu ───────────────────────────────────────────────────────
let openMenuEl = null;
function onDocClickForMenu(e) {
  if (openMenuEl && !openMenuEl.contains(e.target)) closeMenu();
}
function closeMenu() {
  if (openMenuEl) { openMenuEl.remove(); openMenuEl = null; }
  document.removeEventListener("click", onDocClickForMenu);
}
function openMenu(x, y, items, persist = false) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "menu";
  for (const it of items) {
    if (it.sep) {
      const s = document.createElement("div");
      s.className = "sep"; m.appendChild(s); continue;
    }
    const b = document.createElement("button");
    b.type = "button"; b.className = "item"; if (it.danger) b.classList.add("danger");
    if (it.checkbox) {
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !!it.checked;
      cb.addEventListener("change", () => it.onToggle(cb.checked));
      b.appendChild(cb);
      const sp = document.createElement("span"); sp.textContent = it.label;
      b.appendChild(sp);
      b.addEventListener("click", (e) => { if (e.target !== cb) { cb.checked = !cb.checked; it.onToggle(cb.checked); } });
    } else {
      b.textContent = it.label;
      b.addEventListener("click", () => { closeMenu(); it.onClick && it.onClick(); });
    }
    m.appendChild(b);
  }
  document.body.appendChild(m);
  const w = Math.min(window.innerWidth - 12, 240);
  m.style.minWidth = w + "px";
  m.style.left = Math.min(x, window.innerWidth - w - 8) + "px";
  m.style.top = y + "px";
  openMenuEl = m;
  setTimeout(() => document.addEventListener("click", onDocClickForMenu), 0);
  if (persist) {
    // prevent close-on-click outside while interacting with checkboxes
    m.addEventListener("click", (e) => e.stopPropagation());
  }
}

// ─── Modals ─────────────────────────────────────────────────────────────
const modalRoot = document.getElementById("modal-root");
function openModal(content, opts = {}) {
  closeModal();
  modalRoot.innerHTML = "";
  modalRoot.classList.add("active");
  const back = document.createElement("div");
  back.className = "backdrop";
  back.addEventListener("click", () => closeModal());
  const m = document.createElement("div");
  m.className = "modal" + (opts.wide ? " wide" : "");
  m.appendChild(content);
  modalRoot.appendChild(back);
  modalRoot.appendChild(m);
  setTimeout(() => m.querySelector("input,textarea,select,button")?.focus(), 50);
  return m;
}
function closeModal() {
  modalRoot.classList.remove("active");
  modalRoot.innerHTML = "";
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeModal(); closeMenu(); }
});

function modalShell(title, bodyHtml, footer) {
  const wrap = document.createElement("div");
  wrap.style.display = "contents";
  wrap.innerHTML = `
    <div class="modal-head">
      <span class="modal-title">${escapeHtml(title)}</span>
      <button class="icon-btn" data-act="close">×</button>
    </div>
    <div class="modal-body">${bodyHtml}</div>
    <div class="modal-foot"></div>
  `;
  wrap.querySelector("[data-act=close]").addEventListener("click", closeModal);
  if (footer) wrap.querySelector(".modal-foot").appendChild(footer);
  return wrap;
}

function openCheckModal() {
  const body = `
    <div class="field">
      <label>${t("scope_selected")}</label>
      <div class="check-scope">
        <label><input type="radio" name="check-scope" value="selected" checked> ${t("scope_selected")}</label>
        <label><input type="radio" name="check-scope" value="all"> ${t("scope_all")}</label>
      </div>
    </div>
    <div class="field">
      <label>${t("checks") || t("check_btn")}</label>
      <label><input id="check-campaigns" type="checkbox" checked> ${t("check_campaigns")}</label>
      <label><input id="check-drops" type="checkbox" checked> ${t("check_drops_states")}</label>
      <div class="muted">${t("check_drops_note")}</div>
      <label><input id="check-token-type" type="checkbox" checked> ${t("check_token_type")}</label>
    </div>
  `;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `
    <button class="btn outline" data-act="cancel">${t("cancel")}</button>
    <button class="btn primary" data-act="run">${t("run")}</button>
  `;
  const wrap = modalShell(t("check_btn"), body, foot);
  openModal(wrap);
  const modal = modalRoot.querySelector(".modal");
  modal.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  modal.querySelector("[data-act=run]").addEventListener("click", async () => {
    const selected = modal.querySelector("input[name=check-scope]:checked").value;
    const logins = selected === "selected" ? [...state.selected] : null;
    if (selected === "selected" && !logins.length) {
      toast(t("no_accounts_selected"), "error");
      return;
    }
    try {
      const result = await api("/api/accounts/check-bulk", {
        method: "POST",
        body: JSON.stringify({
          logins,
          checks: {
            campaigns: modal.querySelector("#check-campaigns").checked,
            drops: modal.querySelector("#check-drops").checked,
            token_type: modal.querySelector("#check-token-type").checked,
          },
        }),
      });
      state.check = { ...state.check, ...result };
      closeModal();
      renderCheckProgress();
    } catch (error) {
      toast(error.message, "error");
    }
  });
}

function renderCheckProgress() {
  const label = document.getElementById("check-progress-label");
  if (label) label.textContent = `${state.check.done} / ${state.check.total}`;
}

async function loadCheckState() {
  try {
    state.check = { ...state.check, ...(await api("/api/accounts/check/state")) };
    renderCheckProgress();
  } catch (_) {}
}

function renderConvertAccounts() {
  const box = document.getElementById("convert-accounts");
  if (!box) return;
  box.innerHTML = "";
  for (const account of state.accounts.filter((item) => item.token_type === "web")) {
    const row = document.createElement("label");
    row.className = "convert-account";
    row.innerHTML = `<input type="checkbox" value="${escapeHtml(account.login)}">` +
      `<span>${escapeHtml(account.login)}</span>`;
    box.appendChild(row);
  }
}

function renderConvertState() {
  const c = state.convert;
  const fill = document.getElementById("convert-progress-fill");
  const label = document.getElementById("convert-progress-label");
  const counters = document.getElementById("convert-counters");
  const status = document.getElementById("convert-status");
  const startButtons = [
    document.getElementById("convert-all-btn"),
    document.getElementById("convert-selected-btn"),
  ];
  const stopButton = document.getElementById("convert-stop-btn");
  const concurrencyInput = document.getElementById("convert-concurrency");
  if (!fill || !label || !counters) return;
  if (concurrencyInput && c.running && c.concurrency) {
    concurrencyInput.value = String(clampConvertConcurrency(c.concurrency));
  }
  startButtons.forEach((button) => {
    if (button) button.disabled = !!c.running;
  });
  if (stopButton) stopButton.disabled = !c.running;
  if (status) {
    status.textContent = c.running ? t("convert_started") : "";
    status.classList.toggle("hidden", !c.running);
  }
  const pct = c.total ? Math.min(100, Math.max(0, c.done / c.total * 100)) : 0;
  fill.style.width = `${pct}%`;
  label.textContent = `${c.done} / ${c.total}`;
  counters.textContent = [
    `${t("convert_minted")}: ${c.minted}`,
    `${t("convert_bad_password")}: ${c.bad_password}`,
    `${t("convert_2fa")}: ${c.twofa ?? c["2fa"] ?? 0}`,
    `${t("convert_timeout")}: ${c.timeout}`,
    `${t("error")}: ${c.error}`,
  ].join(" · ");
  const results = document.getElementById("convert-results");
  if (results) {
    const labels = {
      minted: t("convert_minted"),
      bad_password: t("convert_bad_password"),
      "2fa": t("convert_2fa"),
      timeout: t("convert_timeout"),
      error: t("error"),
    };
    const reasons = {
      proxy: t("reason_proxy"),
      network: t("reason_network"),
      flow: t("reason_flow"),
    };
    results.innerHTML = (c.results || []).slice(-200).map((item) =>
      `<div class="convert-result result-${escapeHtml(item.status)}">` +
      `<span>${escapeHtml(item.login)}</span><span>${escapeHtml(labels[item.status] || item.status)}` +
      `${item.reason ? ` · ${escapeHtml(reasons[item.reason] || item.reason)}` : ""}</span></div>`
    ).join("");
  }
}

async function loadConvertState() {
  try {
    state.convert = { ...state.convert, ...(await api("/api/convert/state")) };
    renderConvertState();
  } catch (_) {}
}

async function startConversion(logins) {
  try {
    state.convert = { ...state.convert, ...(await api("/api/accounts/convert", {
      method: "POST",
      body: JSON.stringify({ logins }),
    })) };
    state.convert.results = [];
    renderConvertState();
  } catch (error) {
    toast(error.message, "error");
  }
}

document.getElementById("check-btn").addEventListener("click", openCheckModal);
document.getElementById("convert-all-btn").addEventListener("click", () => startConversion(null));
document.getElementById("convert-selected-btn").addEventListener("click", () => {
  const logins = [...document.querySelectorAll("#convert-accounts input:checked")].map((input) => input.value);
  if (!logins.length) {
    toast(t("no_accounts_selected"), "error");
    return;
  }
  startConversion(logins);
});
document.getElementById("convert-stop-btn").addEventListener("click", async () => {
  try {
    state.convert = { ...state.convert, ...(await api("/api/accounts/convert/stop", { method: "POST" })) };
    renderConvertState();
  } catch (error) {
    toast(error.message, "error");
  }
});

// ─── Edit account modal ───────────────────────────────────────────────
function openEditModal(acc) {
  const c = bestCampaign(acc);
  const body = `
    <div class="fieldset">
      <div class="field"><label>${t("login")}</label><input class="input" id="e-login" value="${escapeHtml(acc.login || "")}"/></div>
      <div class="field"><label>${t("role")}</label><input class="input" id="e-role" value="${escapeHtml(acc.role || "")}"/></div>
      <div class="field"><label>${t("password")}</label><input class="input" id="e-pass" value="${escapeHtml(acc.password || "")}"/></div>
      <div class="field"><label>${t("token")}</label><input class="input" id="e-tok" value="${escapeHtml(acc.token || "")}"/></div>
      <div class="field"><label>${t("campaign")}</label><input class="input" id="e-cname" value="${escapeHtml(c.name || "")}"/></div>
      <div class="field"><label>${t("season")}</label><input class="input" id="e-sea" value="${escapeHtml(c.season || "")}"/></div>
      <div class="field"><label>${t("progress")} (%)</label><input class="input" id="e-prog" type="number" min="0" max="100" value="${c.progress || 0}"/></div>
    </div>
  `;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `
    <button class="btn outline" data-act="cancel">${t("cancel")}</button>
    <button class="btn primary" data-act="save">${t("save_changes")}</button>
  `;
  const wrap = modalShell(t("edit_account"), body, foot);
  openModal(wrap);

  const m = modalRoot.querySelector(".modal");
  m.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  m.querySelector("[data-act=save]").addEventListener("click", async () => {
    const updated = {
      login: m.querySelector("#e-login").value.trim() || acc.login,
      password: m.querySelector("#e-pass").value,
      token: m.querySelector("#e-tok").value,
      role: m.querySelector("#e-role").value,
      campaigns: [{
        name: m.querySelector("#e-cname").value,
        season: m.querySelector("#e-sea").value,
        progress: Math.max(0, Math.min(100, parseInt(m.querySelector("#e-prog").value || "0", 10) || 0)),
        drops: c.drops || {},
      }, ...(acc.campaigns || []).slice(1)],
      token_type: acc.token_type || null,
      check_snapshot: acc.check_snapshot || null,
    };
    try {
      await api(`/api/accounts/${encodeURIComponent(acc.login)}`, {
        method: "PUT",
        body: JSON.stringify(updated),
      });
      await reloadAccounts();
      closeModal();
      toast(t("success"), "success");
    } catch (e) {
      toast(t("save_failed", e.message), "error");
    }
  });
}

// ─── Import modal ─────────────────────────────────────────────────────
function openImportModal() {
  const presets = [
    { v: "{login}:{password}:{token}", label: "login:password:token" },
    { v: "{login}:{password}", label: "login:password" },
    { v: "{login}:{password}:{token}:{role}", label: "login:password:token:role" },
    { v: "{token}", label: "token only" },
    { v: "", label: "Custom" },
  ];
  const body = `
    <div class="field"><label>${t("format_presets")}</label>
      <select id="i-preset">${presets.map((p,i) => `<option value="${i}">${escapeHtml(p.label)}</option>`).join("")}</select>
    </div>
    <div class="field"><label>${t("custom_template")}</label>
      <input class="input" id="i-tmpl" value="${presets[0].v}"/>
    </div>
    <div class="field"><label>${t("data_label")}</label>
      <textarea class="ta" rows="8" id="i-data" placeholder="user1:pass1:tok1\nuser2:pass2:tok2"></textarea>
    </div>
    <div class="field">
      <label class="btn accent" for="i-file">📂 ${t("load_from_file")}</label>
      <input type="file" id="i-file" class="hidden" accept=".txt,.csv,text/plain"/>
    </div>
  `;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `
    <button class="btn outline" data-act="cancel">${t("cancel")}</button>
    <button class="btn primary" data-act="import">${t("import_btn")}</button>
  `;
  openModal(modalShell(t("import_title"), body, foot), { wide: true });

  const m = modalRoot.querySelector(".modal");
  const tmpl = m.querySelector("#i-tmpl");
  m.querySelector("#i-preset").addEventListener("change", (e) => {
    const p = presets[Number(e.target.value)];
    if (p && p.v) tmpl.value = p.v;
  });
  m.querySelector("#i-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const txt = await file.text();
    m.querySelector("#i-data").value = txt;
  });
  m.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  m.querySelector("[data-act=import]").addEventListener("click", async () => {
    try {
      const r = await api("/api/accounts/import", {
        method: "POST",
        body: JSON.stringify({ template: tmpl.value, data: m.querySelector("#i-data").value }),
      });
      if (!r.imported && !r.duplicates) {
        toast(t("no_parsed"), "error");
        return;
      }
      let msg = t("imported", r.imported);
      if (r.duplicates) msg += " · " + t("duplicates_skipped", r.duplicates);
      toast(msg, "success");
      await reloadAccounts();
      closeModal();
    } catch (e) {
      toast(t("error") + ": " + e.message, "error");
    }
  });
}

// ─── Export modal ─────────────────────────────────────────────────────
function openExportModal() {
  const sel = state.filtered.filter((a) => state.selected.has(a.login));
  if (!sel.length) { toast(t("no_accounts_selected"), "error"); return; }
  const body = `
    <div class="field"><label>${t("export_format")}</label>
      <input class="input" id="e-tmpl" value="{login}:{password}:{token}"/>
    </div>
    <div class="field"><label>${t("placeholders")}</label>
      <div style="font-family:ui-monospace,monospace;font-size:11px;color:var(--txt-dim);line-height:1.7">
        {login}, {password}, {token}, {role},<br/>
        {campaign_name}, {campaign_progress}, {campaign_season}
      </div>
    </div>
    <div style="font-size:12px; color: var(--txt-2);">${sel.length} ${t("accounts")}</div>
  `;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `
    <button class="btn outline" data-act="cancel">${t("cancel")}</button>
    <button class="btn primary" data-act="export">${t("export_btn")}</button>
  `;
  openModal(modalShell(t("export_selected"), body, foot));
  const m = modalRoot.querySelector(".modal");
  m.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  m.querySelector("[data-act=export]").addEventListener("click", async () => {
    try {
      const r = await api("/api/accounts/export", {
        method: "POST",
        body: JSON.stringify({
          logins: sel.map((a) => a.login),
          template: m.querySelector("#e-tmpl").value,
        }),
      });
      const blob = new Blob([r.text + "\n"], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "accounts_export.txt"; a.click();
      URL.revokeObjectURL(url);
      toast(t("exported", r.count), "success");
      closeModal();
    } catch (e) {
      toast(t("export_failed", e.message), "error");
    }
  });
}

// ─── Bulk role modal ───────────────────────────────────────────────────
function openBulkRoleModal() {
  const sel = [...state.selected];
  if (!sel.length) { toast(t("no_accounts_selected"), "error"); return; }
  const roles = [...new Set(state.accounts.map(a => a.role).filter(Boolean))];
  const body = `
    <p style="margin:0;color:var(--txt-2);font-size:12px;">
      ${t("bulk_role_desc")} <b>${sel.length}</b> ${t("bulk_role_desc2")}.
    </p>
    <div class="field"><label>${t("role")}</label>
      <input class="input" id="r-role" list="role-list" autocomplete="off"/>
      <datalist id="role-list">
        ${roles.map((r) => `<option value="${escapeHtml(r)}">`).join("")}
      </datalist>
    </div>
  `;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `
    <button class="btn outline" data-act="cancel">${t("cancel")}</button>
    <button class="btn primary" data-act="apply">${t("apply")}</button>
  `;
  openModal(modalShell(t("bulk_role_title"), body, foot));
  const m = modalRoot.querySelector(".modal");
  m.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  m.querySelector("[data-act=apply]").addEventListener("click", async () => {
    const role = m.querySelector("#r-role").value.trim();
    try {
      await api("/api/accounts/bulk-role", {
        method: "POST",
        body: JSON.stringify({ logins: sel, role }),
      });
      await reloadAccounts();
      closeModal();
      toast(t("success"), "success");
    } catch (e) {
      toast(t("error") + ": " + e.message, "error");
    }
  });
}

// ─── Progress filter modal ─────────────────────────────────────────────
function openProgressModal() {
  const f = state.filters.prog;
  const opts = [
    { v: "", label: t("none_disabled") },
    { v: ">", label: t("greater_than") + " (>)" },
    { v: "<", label: t("less_than") + " (<)" },
    { v: "=", label: t("equal_to") + " (=)" },
  ];
  const body = `
    <div class="field"><label>${t("comparison")}</label>
      <select id="p-op">
        ${opts.map(o => `<option value="${o.v}" ${o.v === (f.op || "") ? "selected" : ""}>${escapeHtml(o.label)}</option>`).join("")}
      </select>
    </div>
    <div class="field"><label>${t("value")} (%)</label>
      <input type="number" min="0" max="100" class="input" id="p-v" value="${f.v}"/>
    </div>
  `;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `
    <button class="btn outline" data-act="cancel">${t("cancel")}</button>
    <button class="btn primary" data-act="apply">${t("apply")}</button>
  `;
  openModal(modalShell(t("progress_filter"), body, foot));
  const m = modalRoot.querySelector(".modal");
  m.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  m.querySelector("[data-act=apply]").addEventListener("click", () => {
    const op = m.querySelector("#p-op").value;
    state.filters.prog = {
      op: op || null,
      v: Math.max(0, Math.min(100, parseInt(m.querySelector("#p-v").value || "50", 10) || 0)),
    };
    applyFilters();
    closeModal();
  });
}

// ─── Campaigns popup ───────────────────────────────────────────────────
function openCampaignsModal(acc) {
  const camps = (acc.campaigns || []).filter((c) => c.name);
  let body = `<div style="display:flex;flex-direction:column;gap:8px">`;
  if (!camps.length) body += `<div style="color:var(--txt-dim);text-align:center;padding:20px;">—</div>`;
  for (const c of camps) {
    const p = Math.max(0, Math.min(100, Number(c.progress) || 0));
    const cls = pctClass(p);
    body += `
      <div style="background:var(--bg-elevated);border:1px solid var(--border);border-radius:6px;padding:10px;">
        <div style="display:flex;justify-content:space-between;font-weight:600;margin-bottom:6px;">
          <span>${escapeHtml(c.name)}</span>
          <span class="${cls}">${p}%</span>
        </div>
        <div class="d-bar"><div class="d-bar-fill" style="width:${p}%; background:${pctColor(p)};"></div></div>
        ${c.season ? `<div style="font-size:11px;color:var(--txt-dim);margin-top:4px">${escapeHtml(c.season)}</div>` : ""}
        ${Object.keys(c.drops || {}).length ? `<div style="margin-top:6px;display:flex;flex-direction:column;gap:2px;font-size:12px;">${
          Object.entries(c.drops).map(([k, v]) => {
            const d = normDrop(v);
            const amount = d.required
              ? `${d.current}/${d.required} ${t("watched_min")} · ${d.progress}%`
              : `${d.current} ${t("watched_min")}`;
            return `<div style="display:flex;justify-content:space-between"><span>${escapeHtml(k)}</span><b>${escapeHtml(amount)}</b></div>`;
          }).join("")
        }</div>` : ""}
      </div>`;
  }
  body += `</div>`;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `<button class="btn primary" data-act="ok">${t("cancel")}</button>`;
  openModal(modalShell(`${t("campaigns_popup")} — ${acc.login}`, body, foot));
  modalRoot.querySelector("[data-act=ok]").addEventListener("click", closeModal);
}

// ─── Account CRUD ──────────────────────────────────────────────────────
async function deleteAccount(acc) {
  if (!confirm(t("delete_account_q", acc.login))) return;
  try {
    await api(`/api/accounts/${encodeURIComponent(acc.login)}`, { method: "DELETE" });
    state.selected.delete(acc.login);
    if (state.detailLogin === acc.login) {
      state.detailLogin = null;
      clearDetail();
    }
    await reloadAccounts();
    toast(t("success"), "success");
  } catch (e) {
    toast(t("error") + ": " + e.message, "error");
  }
}

async function reloadAccounts() {
  state.accounts = await api("/api/accounts");
  applyFilters();
  updateFarmLaunchCount();
  if (state.detailLogin && state.accounts.find((a) => a.login === state.detailLogin)) {
    showDetail();
  } else {
    state.detailLogin = null;
    clearDetail();
  }
}

async function reloadProxies() {
  state.proxies = await api("/api/proxies");
  state.proxySelected = new Set(
    [...state.proxySelected].filter((raw) => state.proxies.some((p) => p.raw === raw))
  );
  renderProxies();
}

function proxyStatusText(status) {
  return t(`proxy_status_${status || "unknown"}`);
}

function renderProxies() {
  const body = document.getElementById("proxy-body");
  const empty = document.getElementById("proxy-empty");
  body.innerHTML = "";
  empty.classList.toggle("hidden", state.proxies.length > 0);
  state.proxies.forEach((proxy, index) => {
    const tr = document.createElement("tr");
    tr.dataset.raw = proxy.raw;
    if (state.proxySelected.has(proxy.raw)) tr.classList.add("selected");
    tr.innerHTML = `
      <td class="col-chk"><input type="checkbox" ${state.proxySelected.has(proxy.raw) ? "checked" : ""}></td>
      <td>${index + 1}</td>
      <td class="proxy-raw">${escapeHtml(proxy.raw)}</td>
      <td>${escapeHtml(proxy.host)}</td>
      <td>${proxy.port}</td>
      <td>${escapeHtml(proxy.username || "")}</td>
      <td><span class="proxy-status ${escapeHtml(proxy.status || "unknown")}">${escapeHtml(proxyStatusText(proxy.status))}</span></td>
      <td>${proxy.latency_ms == null ? "—" : proxy.latency_ms}</td>
    `;
    tr.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) state.proxySelected.add(proxy.raw);
      else state.proxySelected.delete(proxy.raw);
      tr.classList.toggle("selected", e.target.checked);
      updateProxySelection();
    });
    body.appendChild(tr);
  });
  updateProxySelection();
}

function updateProxySelection() {
  const all = state.proxies.length > 0 && state.proxies.every((p) => state.proxySelected.has(p.raw));
  const header = document.getElementById("proxy-th-chk");
  header.checked = all;
  const button = document.getElementById("proxy-sel-btn");
  button.textContent = all ? t("deselect_all") : t("select_all");
}

function openProxyImportModal() {
  const body = `
    <div class="field">
      <label>${t("proxy_data")}</label>
      <textarea class="ta" rows="10" id="proxy-data" placeholder="1.2.3.4:8080&#10;user:pass@host:3128"></textarea>
    </div>
  `;
  const foot = document.createElement("div");
  foot.style.display = "contents";
  foot.innerHTML = `
    <button class="btn outline" data-act="cancel">${t("cancel")}</button>
    <button class="btn primary" data-act="import">${t("import_btn")}</button>
  `;
  openModal(modalShell(t("proxies_import_title"), body, foot), { wide: true });
  const modal = modalRoot.querySelector(".modal");
  modal.querySelector("[data-act=cancel]").addEventListener("click", closeModal);
  modal.querySelector("[data-act=import]").addEventListener("click", async () => {
    try {
      const result = await api("/api/proxies/import", {
        method: "POST",
        body: JSON.stringify({ data: modal.querySelector("#proxy-data").value }),
      });
      await reloadProxies();
      closeModal();
      toast(t("proxies_imported", result.imported), "success");
    } catch (e) {
      toast(t("error") + ": " + e.message, "error");
    }
  });
}

async function deleteSelectedAccounts() {
  const logins = [...state.selected];
  if (!logins.length || !confirm(t("confirm_delete_accounts"))) return;
  try {
    await api("/api/accounts/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ logins }),
    });
    state.selected.clear();
    await reloadAccounts();
    toast(t("success"), "success");
  } catch (e) {
    toast(t("error") + ": " + e.message, "error");
  }
}

async function deleteSelectedProxies() {
  const keys = [...state.proxySelected];
  if (!keys.length || !confirm(t("confirm_delete_proxies"))) return;
  try {
    await api("/api/proxies/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ keys }),
    });
    state.proxySelected.clear();
    await reloadProxies();
    toast(t("success"), "success");
  } catch (e) {
    toast(t("error") + ": " + e.message, "error");
  }
}

document.getElementById("bulk-del-btn").addEventListener("click", deleteSelectedAccounts);
document.getElementById("proxy-sel-btn").addEventListener("click", () => {
  const all = state.proxies.length > 0 && state.proxies.every((p) => state.proxySelected.has(p.raw));
  state.proxySelected.clear();
  if (!all) state.proxies.forEach((p) => state.proxySelected.add(p.raw));
  renderProxies();
});
document.getElementById("proxy-th-chk").addEventListener("change", (e) => {
  state.proxySelected.clear();
  if (e.target.checked) state.proxies.forEach((p) => state.proxySelected.add(p.raw));
  renderProxies();
});
document.getElementById("proxy-imp-btn").addEventListener("click", openProxyImportModal);
document.getElementById("proxy-del-btn").addEventListener("click", deleteSelectedProxies);
document.getElementById("proxy-check-btn").addEventListener("click", async () => {
  const button = document.getElementById("proxy-check-btn");
  const keys = [...state.proxySelected];
  button.disabled = true;
  button.textContent = t("checking_proxies");
  try {
    state.proxies = await api("/api/proxies/check", {
      method: "POST",
      body: JSON.stringify({ keys }),
    });
    renderProxies();
    toast(t("proxies_checked"), "success");
  } catch (e) {
    toast(t("error") + ": " + e.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = t("check_proxies");
  }
});

// ─── Campaign catalog ───────────────────────────────────────────────────
function campaignDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

async function saveCampaignSelection() {
  await api("/api/campaigns/selected", {
    method: "PUT",
    body: JSON.stringify({ ids: [...state.campaigns.selected] }),
  });
}

function renderCampaigns() {
  const list = document.getElementById("campaigns-list");
  const empty = document.getElementById("campaigns-empty");
  const deselect = document.getElementById("campaigns-deselect-all");
  if (!list || !empty) return;
  list.innerHTML = "";
  if (deselect) deselect.classList.toggle("hidden", state.campaigns.selected.size === 0);
  const query = (document.getElementById("campaigns-search")?.value || "").toLowerCase().trim();
  const matching = (state.campaigns.campaigns || []).filter((campaign) => {
    if (!query) return true;
    const rewards = (campaign.drops || []).map((drop) => drop.name || "").join(" ");
    return [campaign.game_name, campaign.name, campaign.owner, rewards]
      .join(" ").toLowerCase().includes(query);
  });
  const groups = new Map();
  for (const campaign of matching) {
    const key = campaign.game_name || "—";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(campaign);
  }
  const grouped = [...groups.values()];
  if (!query) {
    grouped.sort((a, b) => {
      const aSelected = a.some((campaign) => state.campaigns.selected.has(campaign.id));
      const bSelected = b.some((campaign) => state.campaigns.selected.has(campaign.id));
      return Number(bSelected) - Number(aSelected);
    });
  }
  empty.classList.toggle("hidden", groups.size > 0);
  for (const campaigns of grouped) {
    if (!query) {
      campaigns.sort((a, b) =>
        Number(state.campaigns.selected.has(b.id)) -
        Number(state.campaigns.selected.has(a.id))
      );
    }
    const first = campaigns[0];
    const section = document.createElement("section");
    section.className = "campaign-game-section";
    const gameKey = first.game_name || "—";
    const expanded = state.campaigns.expandedGames.has(gameKey);
    const gameCampaigns = state.campaigns.campaigns.filter(
      (campaign) => (campaign.game_name || "—") === gameKey
    );
    const allSelected = gameCampaigns.length > 0 &&
      gameCampaigns.every((campaign) => state.campaigns.selected.has(campaign.id));
    section.innerHTML = `
      <div class="campaign-game-header${expanded ? "" : " collapsed"}" role="button" tabindex="0">
        <div class="campaign-game-title">
          <span class="campaign-game-caret" aria-hidden="true">⌄</span>
          ${first.box_art ? `<img src="${escapeHtml(first.box_art)}" alt="">` : ""}
          <span><strong>${escapeHtml(first.game_name || "—")}</strong>
          <small>${escapeHtml(first.owner || "—")}</small></span>
        </div>
        <label class="campaign-game-select">
          <input type="checkbox" ${allSelected ? "checked" : ""}>
          <span>${escapeHtml(t("campaign_selected"))}</span>
        </label>
      </div>
      <div class="campaign-game-campaigns${expanded ? "" : " collapsed"}"></div>`;
    const header = section.querySelector(".campaign-game-header");
    const toggleExpanded = () => {
      if (state.campaigns.expandedGames.has(gameKey)) {
        state.campaigns.expandedGames.delete(gameKey);
      } else {
        state.campaigns.expandedGames.add(gameKey);
      }
      renderCampaigns();
    };
    header.addEventListener("click", (event) => {
      if (event.target.closest(".campaign-game-select")) return;
      toggleExpanded();
    });
    header.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleExpanded();
      }
    });
    const gameSelect = section.querySelector(".campaign-game-select");
    gameSelect.addEventListener("click", (event) => event.stopPropagation());
    gameSelect.querySelector("input").addEventListener("change", async (event) => {
      const previous = new Set(state.campaigns.selected);
      if (event.target.checked) {
        gameCampaigns.forEach((campaign) => state.campaigns.selected.add(campaign.id));
      } else {
        gameCampaigns.forEach((campaign) => state.campaigns.selected.delete(campaign.id));
      }
      try {
        await saveCampaignSelection();
        renderCampaigns();
      } catch (e) {
        state.campaigns.selected = previous;
        renderCampaigns();
        toast(t("error") + ": " + e.message, "error");
      }
    });
    const campaignList = section.querySelector(".campaign-game-campaigns");
    for (const campaign of campaigns) {
      const row = document.createElement("article");
      row.className = "campaign-card" + (
        state.campaigns.selected.has(campaign.id) ? " selected" : ""
      );
      const drops = campaign.drops || [];
      row.innerHTML = `
        <div class="campaign-card-head">
          <label><input type="checkbox" ${state.campaigns.selected.has(campaign.id) ? "checked" : ""}>
          <strong>${escapeHtml(campaign.name || "—")}</strong></label>
          ${campaign.is_account_connected
            ? `<span class="campaign-linked">✓ ${escapeHtml(t("campaign_linked"))}</span>`
            : ""}
        </div>
        <div class="campaign-card-end">${escapeHtml(t("campaign_ends"))}: ${escapeHtml(campaignDate(campaign.ends_at))}</div>
        <div class="campaign-rewards-title">${escapeHtml(t("rewards"))}</div>
        <div class="campaign-rewards">
          ${drops.length ? drops.map((drop) => `
            <div class="campaign-reward">
              ${drop.image ? `<img src="${escapeHtml(drop.image)}" alt="">` : ""}
              <span>${escapeHtml(drop.name || "")}</span>
              <small>${Number(drop.required_minutes || 0)} ${t("watched_min")}</small>
            </div>`).join("") : ""}
        </div>`;
      row.querySelector("input").addEventListener("change", async (event) => {
        const previous = new Set(state.campaigns.selected);
        if (event.target.checked) state.campaigns.selected.add(campaign.id);
        else state.campaigns.selected.delete(campaign.id);
        try {
          await saveCampaignSelection();
          renderCampaigns();
        } catch (e) {
          state.campaigns.selected = previous;
          renderCampaigns();
          toast(t("error") + ": " + e.message, "error");
        }
      });
      campaignList.appendChild(row);
    }
    list.appendChild(section);
  }
  const updated = document.getElementById("campaigns-updated");
  if (updated) {
    updated.textContent = state.campaigns.fetched_at
      ? t("campaigns_updated", campaignDate(state.campaigns.fetched_at * 1000))
      : "";
  }
}

async function reloadCampaigns() {
  const data = await api("/api/campaigns");
  const expandedGames = state.campaigns.expandedGames;
  state.campaigns = {
    fetched_at: data.fetched_at || 0,
    campaigns: data.campaigns || [],
    selected: new Set(data.selected || []),
    expandedGames,
  };
  renderCampaigns();
}

document.getElementById("campaigns-search").addEventListener("input", renderCampaigns);
document.getElementById("campaigns-deselect-all").addEventListener("click", async () => {
  const previous = new Set(state.campaigns.selected);
  state.campaigns.selected.clear();
  try {
    await saveCampaignSelection();
    renderCampaigns();
  } catch (e) {
    state.campaigns.selected = previous;
    renderCampaigns();
    toast(t("error") + ": " + e.message, "error");
  }
});

// sidebar buttons
document.getElementById("imp-btn").addEventListener("click", openImportModal);
document.getElementById("exp-btn").addEventListener("click", openExportModal);
document.getElementById("role-btn").addEventListener("click", openBulkRoleModal);

// ─── Farm ──────────────────────────────────────────────────────────────
function fmtDuration(start) {
  if (!start) return "00:00:00";
  const e = Math.max(0, Math.floor(Date.now() / 1000 - start));
  const h = String(Math.floor(e / 3600)).padStart(2, "0");
  const m = String(Math.floor((e % 3600) / 60)).padStart(2, "0");
  const s = String(e % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function farmCacheKey() {
  const owner = ME && (ME.id || ME.username);
  return owner ? `twitch-farm-state:${owner}` : null;
}

const FARM_RENDER_CAP = 120;
const FARM_REPAINT_INTERVAL = 500;
const FARM_LOG_DOM_CAP = 100;
const FARM_CACHE_INTERVAL = 5000;
let farmRepaintTimer = null;
let farmLastPaintAt = 0;
let farmLastCacheSaveAt = 0;
const pendingFarmLogins = new Set();

function saveFarmCache(force = false) {
  const now = Date.now();
  if (!force && now - farmLastCacheSaveAt < FARM_CACHE_INTERVAL) return;
  const key = farmCacheKey();
  if (!key) return;
  const cards = [...state.farm.cards.entries()].map(([login, card]) => [login, card]);
  try {
    sessionStorage.setItem(key, JSON.stringify({
      running: state.farm.running,
      cards,
      cardStartedAt: Object.fromEntries(state.farm.cardStartedAt),
      overLimit: [...state.farm.overLimit],
    }));
    farmLastCacheSaveAt = now;
  } catch (_) {}
}

function restoreFarmCache() {
  const key = farmCacheKey();
  if (!key) return;
  try {
    const cached = JSON.parse(sessionStorage.getItem(key) || "null");
    if (!cached) return;
    state.farm.running = !!cached.running;
    state.farm.cards = new Map(Array.isArray(cached.cards) ? cached.cards : []);
    state.farm.cardStartedAt = new Map(
      Object.entries(cached.cardStartedAt || {}).map(([login, started]) => [login, started])
    );
    state.farm.overLimit = new Set(cached.overLimit || []);
    renderFarmCards();
    setFarmRunning(state.farm.running);
  } catch (_) {
    sessionStorage.removeItem(key);
  }
}

function mergeCardCampaigns(login, campaigns) {
  if (!Array.isArray(campaigns)) return false;
  const account = state.accounts.find((a) => a.login === login);
  if (!account) return false;
  const before = JSON.stringify(account.campaigns || []);
  account.campaigns = campaigns;
  return before !== JSON.stringify(campaigns);
}

function refreshManagerFromCards(cards) {
  let changed = false;
  for (const card of cards) {
    if (card && card.login) changed = mergeCardCampaigns(card.login, card.campaigns) || changed;
  }
  if (!changed) return;
  if (state.detailLogin) showDetail();
  if (document.querySelector('.page[data-page="accounts"]:not(.hidden)')) applyFilters();
}

function updateFarmStatus() {
  const el = document.getElementById("farm-status-bar");
  if (!el) return;
  if (!state.farm.running) {
    el.textContent = t("farm_stopped_summary");
    el.className = "farm-status stopped";
    return;
  }
  const campaigns = new Set(
    [...state.farm.cards.values()]
      .map((card) => (card.campaign || "").trim())
      .filter((name) => name && name !== "—")
  );
  el.textContent = t(
    "farm_active_summary",
    state.farm.cards.size,
    campaigns.size
  );
  el.className = "farm-status active";
}

function setFarmConvertStatus(message = "", converting = Boolean(message)) {
  return;
}

function setFarmConverting(count) {
  state.farm.converting = true;
  state.farm.starting = false;
  const btn = document.getElementById("farm-btn");
  const label = document.getElementById("farm-btn-label");
  btn.disabled = false;
  btn.classList.remove("starting", "primary");
  btn.classList.add("danger");
  if (label) label.textContent = t("stop_farm");
  else btn.textContent = t("stop_farm");
  appendLog({
    ts: Date.now() / 1000,
    login: "",
    level: "info",
    message: t("farm_converting", count),
  });
  updateFarmLaunchCount();
}

function runFarmRepaint() {
  farmLastPaintAt = Date.now();
  if (pendingFarmLogins.size) {
    const cards = [...pendingFarmLogins]
      .map((login) => {
        const card = state.farm.cards.get(login);
        return card ? { login, campaigns: card.campaigns } : null;
      })
      .filter(Boolean);
    pendingFarmLogins.clear();
    refreshManagerFromCards(cards);
  }
  renderFarmCards();
  flushLogs();
  saveFarmCache();
}

function scheduleFarmRepaint(immediate = false) {
  if (immediate) {
    if (farmRepaintTimer) clearTimeout(farmRepaintTimer);
    farmRepaintTimer = null;
    runFarmRepaint();
    return;
  }
  if (farmRepaintTimer) return;
  const delay = Math.max(0, FARM_REPAINT_INTERVAL - (Date.now() - farmLastPaintAt));
  farmRepaintTimer = setTimeout(() => {
    farmRepaintTimer = null;
    runFarmRepaint();
  }, delay);
}

function renderFarmCards() {
  const w = document.getElementById("farm-cards");
  w.innerHTML = "";
  // сначала активные, затем отфармленные (100%) — уходят вниз
  const entries = [...state.farm.cards.entries()];
  const active = entries.filter(([, c]) => (c.progress || 0) < 100);
  const farmed = entries.filter(([, c]) => (c.progress || 0) >= 100);
  const ordered = [...active, ...farmed].map(([login, c]) => ({ login, c }));
  for (const login of state.farm.overLimit) {
    if (!state.farm.cards.has(login)) ordered.push({ login, overLimit: true });
  }
  const visible = ordered.slice(0, FARM_RENDER_CAP);
  if (ordered.length > FARM_RENDER_CAP) {
    const summary = document.createElement("div");
    summary.className = "farm-summary";
    summary.textContent = t("showing", visible.length, ordered.length);
    w.appendChild(summary);
  }
  for (const item of visible) {
    const { login, c, overLimit } = item;
    if (overLimit) {
      const div = document.createElement("div");
      div.className = "f-card over-limit";
      div.dataset.login = login;
      div.innerHTML = `
        <div class="f-login">${escapeHtml(login)}</div>
        <div class="f-time">—</div>
        <div class="f-camp">${t("over_limit")}</div>
        <div class="f-pct">—</div>
        <div class="f-bar"><span style="width:0%"></span></div>
        <div class="f-log">${t("over_limit_hint")}</div>
      `;
      w.appendChild(div);
      continue;
    }
    const done = (c.progress || 0) >= 100;
    const div = document.createElement("div");
    div.className = done ? "f-card farmed" : "f-card";
    const p = Math.max(0, Math.min(100, Number(c.progress) || 0));
    const col = pctColor(p);
    const start = state.farm.cardStartedAt.get(login);
    div.dataset.login = login;
    div.innerHTML = `
      <div class="f-login">${escapeHtml(login)}</div>
      <div class="f-time" data-start="${start || 0}">${fmtDuration(start)}</div>
      <div class="f-camp">${done ? t("farmed") : escapeHtml(c.campaign || "—")}</div>
      <div class="f-pct" style="color:${col}">${p}%</div>
      <div class="f-bar"><span style="width:${p}%; background:${col};"></span></div>
      <div class="f-log">${escapeHtml(c.log || "")}</div>
    `;
    div.addEventListener("click", () => {
      const acc = state.accounts.find((a) => a.login === login);
      if (acc) openCampaignsModal(acc);
    });
    w.appendChild(div);
  }
  updateFarmStatus();
}

function tickFarmTimers() {
  document.querySelectorAll(".f-time[data-start]").forEach((el) => {
    const s = parseFloat(el.dataset.start) || 0;
    if (s) el.textContent = fmtDuration(s);
  });
}

function appendLog(entry) {
  state.farm.logs.push(entry);
  if (state.farm.logs.length > 150) state.farm.logs = state.farm.logs.slice(-150);
  scheduleFarmRepaint();
}

function flushLogs() {
  const box = document.getElementById("log-box");
  box.innerHTML = "";
  for (const entry of state.farm.logs.slice(-FARM_LOG_DOM_CAP)) {
    const line = document.createElement("div");
    line.className = "l-line l-" + (entry.level || "info");
    const ts = new Date((entry.ts || Date.now() / 1000) * 1000);
    const hh = String(ts.getHours()).padStart(2, "0");
    const mm = String(ts.getMinutes()).padStart(2, "0");
    const ss = String(ts.getSeconds()).padStart(2, "0");
    const message = LANG[currentLang] && LANG[currentLang][entry.message]
      ? t(entry.message)
      : (entry.message || "");
    line.innerHTML = `<span class="l-time">${hh}:${mm}:${ss}</span><span class="l-login">${escapeHtml(entry.login || "")}</span><span class="l-msg">${escapeHtml(message)}</span>`;
    box.appendChild(line);
  }
  box.scrollTop = box.scrollHeight;
}

function updateFarmLaunchCount() {
  const count = document.getElementById("farm-launch-count");
  if (!count) return;
  const running = state.farm.running || state.farm.starting || state.farm.converting;
  const total = state.accounts.length;
  const selected = state.selected.size ? state.selected.size : total;
  const isAdmin = Boolean(ME && (ME.is_admin || ME.role === "admin"));
  const limit = Number(ME && ME.thread_limit);
  const launchable = Number.isFinite(state.farm.launchCount)
    ? state.farm.launchCount
    : isAdmin || !Number.isFinite(limit)
      ? selected
      : Math.min(selected, Math.max(0, limit));
  count.textContent = String(Math.max(0, launchable));
  count.classList.toggle("hidden", running);
}

function setFarmRunning(on) {
  state.farm.running = on;
  state.farm.starting = false;
  if (!on) {
    state.farm.converting = false;
    setFarmConvertStatus();
  }
  const btn = document.getElementById("farm-btn");
  const label = document.getElementById("farm-btn-label");
  const badge = document.getElementById("farm-badge");
  if (label) label.textContent = on ? t("stop_farm") : t("start_farm");
  else btn.textContent = on ? t("stop_farm") : t("start_farm");
  btn.disabled = false;
  btn.classList.remove("starting");
  btn.classList.toggle("danger", on);
  btn.classList.toggle("primary", !on);
  if (badge) {
    badge.textContent = on ? t("farm_running") : t("farm_stopped");
    badge.className = "badge " + (on ? "green" : "red");
  }
  updateFarmLaunchCount();
  updateFarmStatus();
}

document.getElementById("farm-btn").addEventListener("click", async () => {
  if (state.farm.starting) return;
  try {
    if (!state.farm.running && !state.farm.converting) {
      state.farm.starting = true;
      switchTab("farm");
      const btn = document.getElementById("farm-btn");
      const label = document.getElementById("farm-btn-label");
      btn.disabled = true;
      btn.classList.add("starting");
      if (label) label.textContent = `${t("start_farm")}…`;
      updateFarmLaunchCount();
      document.getElementById("farm-cards").innerHTML =
        `<div class="farm-starting">${escapeHtml(t("starting_farm"))}</div>`;
      const res = await api("/api/farm/start", {
        method: "POST",
        body: JSON.stringify({
          logins: [...state.selected],
          stagger: Math.max(
            0,
            Math.min(120, Number(document.getElementById("farm-stagger").value) || 0)
          ),
        }),
      });
      state.farm.overLimit = new Set(res && res.over_limit ? res.over_limit : []);
      state.farm.launchCount = Number.isFinite(Number(res?.launched))
        ? Number(res.launched) : null;
      state.farm.starting = false;
      setFarmRunning(!!res?.running);
      if (state.farm.overLimit.size) {
        toast(
          t("over_limit_toast")
            .replace("{limit}", res.limit)
            .replace("{n}", state.farm.overLimit.size),
          "warn"
        );
      }
      scheduleFarmRepaint(true);
    } else {
      const btn = document.getElementById("farm-btn");
      btn.disabled = true;
      const res = await api("/api/farm/stop", { method: "POST" });
      // Reflect the stop immediately from the HTTP response instead of waiting
      // for the WebSocket broadcast (which may be slow or disconnected).
      state.farm.converting = false;
      setFarmConvertStatus();
      setFarmRunning(!!(res && res.running));
      state.farm.launchCount = null;
      state.farm.cards.clear();
      state.farm.cardStartedAt.clear();
      state.farm.overLimit.clear();
      pendingFarmLogins.clear();
      scheduleFarmRepaint(true);
      saveFarmCache(true);
    }
  } catch (e) {
    state.farm.starting = false;
    const btn = document.getElementById("farm-btn");
    const label = document.getElementById("farm-btn-label");
    btn.disabled = false;
    btn.classList.remove("starting");
    btn.classList.remove("danger");
    btn.classList.add("primary");
    state.farm.converting = false;
    setFarmConvertStatus();
    if (label) label.textContent = t("start_farm");
    else btn.textContent = t("start_farm");
    updateFarmLaunchCount();
    toast(e.message, "error");
  }
});

document.getElementById("log-clear").addEventListener("click", () => {
  state.farm.logs = [];
  flushLogs();
  saveFarmCache(true);
});

function connectWS() {
  if (state.ws) try { state.ws.close(); } catch (_) {}
  const url = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws/farm";
  const ws = new WebSocket(url);
  state.ws = ws;
  ws.onmessage = (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch (_) { return; }
    if (data.type === "init") {
      const s = data.state || {};
      setFarmRunning(!!s.running);
      state.farm.cards = new Map();
      state.farm.cardStartedAt = new Map();
      pendingFarmLogins.clear();
      for (const c of (s.cards || [])) {
        state.farm.cards.set(c.login, {
          campaign: c.campaign,
          progress: c.progress,
          season: c.season,
          drops: c.drops,
          campaigns: c.campaigns,
          log: c.log,
        });
        if (c.started_at) state.farm.cardStartedAt.set(c.login, c.started_at);
        pendingFarmLogins.add(c.login);
      }
      state.farm.logs = Array.isArray(s.logs) ? s.logs.slice(-150) : [];
      scheduleFarmRepaint(true);
    } else if (data.type === "running") {
      setFarmRunning(!!data.running);
      if (!data.running) {
        state.farm.cards.clear();
        state.farm.cardStartedAt.clear();
        state.farm.overLimit.clear();
        pendingFarmLogins.clear();
        scheduleFarmRepaint(true);
        saveFarmCache(true);
      } else {
        scheduleFarmRepaint();
      }
    } else if (data.type === "snapshot") {
      if (state.farm.starting) setFarmRunning(true);
      state.farm.cards = new Map();
      state.farm.cardStartedAt = new Map();
      pendingFarmLogins.clear();
      for (const [login, c] of (data.cards || [])) {
        state.farm.cards.set(login, c);
        if (c.started_at) state.farm.cardStartedAt.set(login, c.started_at);
        pendingFarmLogins.add(login);
      }
      scheduleFarmRepaint(true);
    } else if (data.type === "card") {
      const cur = state.farm.cards.get(data.login) || {};
      for (const field of ["started_at", "campaign", "progress", "season", "drops", "campaigns", "log"]) {
        if (Object.prototype.hasOwnProperty.call(data, field)) cur[field] = data[field];
      }
      if (Object.prototype.hasOwnProperty.call(data, "started_at")) {
        state.farm.cardStartedAt.set(data.login, data.started_at);
      }
      state.farm.cards.set(data.login, cur);
      pendingFarmLogins.add(data.login);
      scheduleFarmRepaint();
    } else if (data.type === "log") {
      appendLog(data);
    } else if (data.type === "check_progress") {
      state.check = {
        ...state.check,
        running: true,
        done: Number(data.done) || 0,
        total: Number(data.total) || 0,
      };
      renderCheckProgress();
    } else if (data.type === "check_result") {
      const account = state.accounts.find((item) => item.login === data.login);
      if (account) {
        account.token_type = data.token_type || "invalid";
        account.check_snapshot = {
          valid: !!data.valid,
          token_type: data.token_type,
          campaigns: data.campaigns || [],
          drops_summary: data.drops_summary || {},
          awarded: data.awarded || [],
        };
        state.dropCheck = {
          login: data.login,
          loading: false,
          result: account.check_snapshot,
        };
      }
      renderTable();
      if (state.detailLogin === data.login) showDetail();
    } else if (data.type === "check_done") {
      state.check = {
        ...state.check,
        running: false,
        done: Number(data.total) || state.check.done,
        total: Number(data.total) || state.check.total,
      };
      renderCheckProgress();
    } else if (data.type === "farm_auto_started") {
      state.farm.converting = false;
      setFarmRunning(!!data.running);
      appendLog({
        ts: Date.now() / 1000,
        login: "",
        level: "info",
        message: t("farm_auto_started", Number(data.launched) || 0),
      });
      switchTab("farm");
      scheduleFarmRepaint(true);
    } else if (data.type === "convert_state") {
      state.convert = { ...state.convert, ...data };
      renderConvertState();
    } else if (data.type === "convert_progress") {
      state.convert = {
        ...state.convert,
        running: true,
        done: Number(data.done) || 0,
        total: Number(data.total) || 0,
      };
      renderConvertState();
    } else if (data.type === "convert_result") {
      state.convert.results = [...state.convert.results, {
        login: data.login,
        status: data.status,
        reason: data.reason,
      }];
      if (data.status === "2fa") state.convert.twofa += 1;
      if (data.status === "minted") {
        const account = state.accounts.find((item) => item.login === data.login);
        if (account) account.token_type = "mobile";
        renderConvertAccounts();
        renderTable();
      }
      renderConvertState();
    } else if (data.type === "convert_done") {
      state.convert = {
        ...state.convert,
        ...data,
        running: false,
      };
      if (Object.prototype.hasOwnProperty.call(data, "2fa")) {
        state.convert.twofa = Number(data["2fa"]) || 0;
      }
      renderConvertAccounts();
      renderConvertState();
    }
  };
  ws.onclose = () => setTimeout(connectWS, 1500);
  ws.onerror = () => ws.close();
}

setInterval(tickFarmTimers, 1000);

// ─── Language toggle ───────────────────────────────────────────────────
document.getElementById("lang-btn").addEventListener("click", () => {
  currentLang = currentLang === "en" ? "ru" : "en";
  localStorage.setItem("lang", currentLang);
  applyI18n();
  applyFilters();
  setFarmRunning(state.farm.running);
  renderCampaigns();
});

// ─── Init ──────────────────────────────────────────────────────────────
// ─── Auth / current user ─────────────────────────────────────────────────
let ME = null;

function fmtDate(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

function subInfo(u) {
  // возвращает {text, cls} про подписку текущего юзера
  if (u.role === "admin") return { text: "∞ (admin)", cls: "" };
  if (!u.subscription_until) return { text: "нет подписки", cls: "sub-expired" };
  const left = u.subscription_until * 1000 - Date.now();
  if (left <= 0) return { text: "истекла " + fmtDate(u.subscription_until), cls: "sub-expired" };
  const days = Math.floor(left / 86400000);
  const hours = Math.floor((left % 86400000) / 3600000);
  const when = days >= 1 ? `${days} дн.` : `${hours} ч.`;
  return { text: `до ${fmtDate(u.subscription_until)} (${when})`, cls: days <= 3 ? "sub-warn" : "" };
}

async function loadMe() {
  const data = await api("/api/auth/me");
  ME = data.user;
  CSRF_TOKEN = data.csrf || CSRF_TOKEN;
  const badge = document.getElementById("me-badge");
  if (badge) {
    badge.textContent = ME.username + (ME.role === "admin" ? " · admin" : "");
  }
  const sub = document.getElementById("sub-badge");
  if (sub) {
    const info = subInfo(ME);
    sub.textContent = `Потоки: ${ME.thread_limit} · Подписка: ${info.text}`;
    sub.className = "me-badge " + info.cls;
  }
  const adminLink = document.getElementById("admin-link");
  if (adminLink) adminLink.classList.toggle("hidden", ME.role !== "admin");
}

async function doLogout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {}
  window.location.href = "/login";
}

function wireTopbar() {
  const lo = document.getElementById("logout-btn");
  if (lo) lo.addEventListener("click", doLogout);
}

async function init() {
  applyI18n();
  wireTopbar();
  try {
    await loadMe();
  } catch (e) {
    window.location.href = "/login";
    return;
  }
  applyProxyModeVisibility();
  restoreFarmCache();
  try {
    await reloadAccounts();
    if (ME.role === "admin" || ME.proxy_mode !== "pool") await reloadProxies();
    await reloadCampaigns();
  } catch (e) {
    toast("init: " + e.message, "error");
  }
  connectWS();
  loadCheckState();
  loadConvertState();
  let tab = localStorage.getItem("activeTab") || "accounts";
  // защита от устаревшего значения (напр. удалённая вкладка "admin")
  if (!document.querySelector(`.page[data-page="${tab}"]`)) tab = "accounts";
  switchTab(tab);
  hideAppLoader();
}

function hideAppLoader() {
  const loader = document.getElementById("app-loader");
  if (!loader || loader.classList.contains("is-hidden")) return;
  loader.classList.add("is-hidden");
  window.setTimeout(() => loader.remove(), 400);
}

window.setTimeout(hideAppLoader, 8000);
init();
