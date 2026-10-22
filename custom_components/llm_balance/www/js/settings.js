import { all, el, getBackend } from "./context.js";
import { invalidatePlatformCache, loadPlatforms } from "./dashboard.js";
import { relativeTime } from "./format.js";
import { toast } from "./toast.js";

const ACCENT_TEXT = {
  aliyun: "var(--accent-aliyun)",
  minimax: "var(--accent-minimax)",
  deepseek: "var(--accent-deepseek)",
};

const modal = () => el("account-modal");
const form = () => el("account-form");
const platformSelect = () => el("account-platform");
const modeSelect = () => el("account-mode");
const credentialHost = () => el("credential-fields");
const messageBox = () => el("account-msg");
const titleNode = () => el("modal-title");

let platforms = [];
let editingId = null;

function text(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = String(content);
  return node;
}

function currentPlatform() {
  return platforms.find((item) => item.key === platformSelect().value);
}

function currentMode() {
  const platform = currentPlatform();
  return platform?.modes.find((mode) => mode.key === modeSelect().value);
}

function renderModeOptions() {
  const platform = currentPlatform();
  modeSelect().textContent = "";
  for (const mode of platform.modes) {
    const option = document.createElement("option");
    option.value = mode.key;
    option.textContent = mode.label;
    modeSelect().appendChild(option);
  }
  el("mode-hint").textContent = currentMode()?.description || "";
}

function renderCredentialFields() {
  const mode = currentMode();
  credentialHost().textContent = "";
  if (!mode) return;

  for (const field of mode.fields) {
    const label = text("label", "field");
    label.appendChild(text("span", "field__label", field.label + (field.required ? " *" : "")));

    const input = document.createElement("input");
    input.type = field.secret ? "password" : "text";
    input.name = `cred:${field.name}`;
    input.placeholder = editingId && field.secret
      ? `留空表示不修改（当前 ${field.name}）`
      : field.placeholder || "";
    input.autocomplete = "off";
    label.appendChild(input);

    if (field.help) label.appendChild(text("span", "field__hint", field.help));
    credentialHost().appendChild(label);
  }

  if (mode.docs?.length) {
    const docs = text("div", "credential-doc");
    for (const url of mode.docs) {
      const link = text("a", "doc-link", "查看官方接口文档 ↗");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      docs.appendChild(link);
    }
    credentialHost().appendChild(docs);
  }
}

export function openAccountModal(account = null) {
  editingId = account?.id ?? null;
  titleNode().textContent = account ? "编辑账号" : "新增账号";
  messageBox().textContent = "";
  messageBox().className = "form-msg";

  platformSelect().textContent = "";
  for (const platform of platforms) {
    const option = document.createElement("option");
    option.value = platform.key;
    option.textContent = platform.label;
    platformSelect().appendChild(option);
  }
  platformSelect().value = account?.platform ?? platforms[0].key;
  platformSelect().disabled = Boolean(account);

  renderModeOptions();
  if (account) {
    modeSelect().value = account.mode;
    el("mode-hint").textContent = currentMode()?.description || "";
  }
  renderCredentialFields();

  form().querySelector('[name="id"]').value = account?.id ?? "";
  form().querySelector('[name="label"]').value = account?.label ?? "";

  modal().hidden = false;
  setTimeout(() => form().querySelector('[name="label"]')?.focus(), 60);
}

export function closeAccountModal() {
  modal().hidden = true;
  editingId = null;
}

async function submitAccount(event) {
  event.preventDefault();
  const credentials = {};
  for (const input of form().querySelectorAll('input[name^="cred:"]')) {
    const value = input.value.trim();
    if (value) credentials[input.name.slice(5)] = value;
  }

  const body = {
    platform: platformSelect().value,
    mode: modeSelect().value,
    label: form().querySelector('[name="label"]').value.trim(),
    credentials,
  };

  if (!body.label) {
    messageBox().textContent = "请填写备注名称";
    messageBox().className = "form-msg is-error";
    return;
  }

  const submit = el("account-submit");
  submit.disabled = true;
  try {
    if (editingId) {
      await getBackend().updateAccount(editingId, body);
      toast("账号已更新", "ok");
    } else {
      await getBackend().createAccount(body);
      toast("账号已添加", "ok");
    }
    closeAccountModal();
    await renderAccounts();
    window.dispatchEvent(new CustomEvent("aidas:reload"));
  } catch (error) {
    messageBox().textContent = error.message;
    messageBox().className = "form-msg is-error";
  } finally {
    submit.disabled = false;
  }
}

function accountRow(account, platform) {
  const row = text("div", "account-row");
  if (!account.enabled) row.classList.add("is-off");

  const main = text("div", "account-row__main");
  const name = text("div", "account-row__name");
  const badge = text("span", "badge", platform?.short || account.platform);
  badge.style.color = ACCENT_TEXT[account.platform] || "var(--info)";
  badge.style.background = `color-mix(in srgb, ${ACCENT_TEXT[account.platform] || "var(--info)"} 18%, transparent)`;
  badge.style.borderColor = `color-mix(in srgb, ${ACCENT_TEXT[account.platform] || "var(--info)"} 32%, transparent)`;
  name.appendChild(badge);
  name.appendChild(text("span", null, account.label));
  const modeLabel = platform?.modes.find((mode) => mode.key === account.mode)?.label || account.mode;
  name.appendChild(text("span", "pill pill--off", modeLabel));
  main.appendChild(name);

  const masked = Object.entries(account.credential_mask || {})
    .map(([key, value]) => `${key}=${value}`)
    .join("  ");
  const meta = text("div", "account-row__meta");
  meta.appendChild(text("span", null, masked || "—"));
  if (account.last_ok_at) meta.appendChild(text("span", null, `最近成功 ${relativeTime(account.last_ok_at)}`));
  if (account.last_error) meta.appendChild(text("span", null, `错误：${account.last_error}`));
  main.appendChild(meta);
  row.appendChild(main);

  const actions = text("div", "account-row__actions");

  const testBtn = text("button", "btn btn--sm", "测试");
  testBtn.type = "button";
  testBtn.addEventListener("click", async () => {
    testBtn.disabled = true;
    testBtn.textContent = "测试中…";
    try {
      const result = await getBackend().testAccount(account.id);
      if (result.ok) {
        toast(`「${account.label}」连接正常（${result.latency_ms} ms）`, "ok");
      } else {
        toast(`「${account.label}」失败：${result.error || "未知错误"}`, "error");
      }
      await renderAccounts();
      window.dispatchEvent(new CustomEvent("aidas:reload"));
    } catch (error) {
      toast(`测试失败：${error.message}`, "error");
    } finally {
      testBtn.disabled = false;
      testBtn.textContent = "测试";
    }
  });
  actions.appendChild(testBtn);

  const editBtn = text("button", "btn btn--sm", "编辑");
  editBtn.type = "button";
  editBtn.addEventListener("click", () => openAccountModal(account));
  actions.appendChild(editBtn);

  const toggleBtn = text("button", "btn btn--sm", account.enabled ? "停用" : "启用");
  toggleBtn.type = "button";
  toggleBtn.addEventListener("click", async () => {
    try {
      await getBackend().updateAccount(account.id, { enabled: !account.enabled });
      await renderAccounts();
    } catch (error) {
      toast(`操作失败：${error.message}`, "error");
    }
  });
  actions.appendChild(toggleBtn);

  const deleteBtn = text("button", "btn btn--sm btn--danger", "删除");
  deleteBtn.type = "button";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`确定删除账号「${account.label}」？该操作不可撤销。`)) return;
    try {
      await getBackend().deleteAccount(account.id);
      toast("账号已删除", "ok");
      await renderAccounts();
      window.dispatchEvent(new CustomEvent("aidas:reload"));
    } catch (error) {
      toast(`删除失败：${error.message}`, "error");
    }
  });
  actions.appendChild(deleteBtn);

  row.appendChild(actions);
  return row;
}

export async function renderAccounts() {
  const host = el("account-list");
  const payload = await getBackend().accounts();
  host.textContent = "";

  if (!payload.items.length) {
    const empty = text("div", "empty");
    empty.appendChild(text("div", "empty__icon", "◍"));
    empty.appendChild(text("h3", null, "尚未添加账号"));
    empty.appendChild(text("p", null, "点击右上角「新增账号」，为每个平台添加一个或多个访问凭据。"));
    host.appendChild(empty);
    return;
  }

  for (const platform of platforms) {
    const owned = payload.items.filter((item) => item.platform === platform.key);
    if (!owned.length) continue;
    const group = text("div", "mode-group");
    group.appendChild(text("div", "mode-group__label", platform.label));
    for (const account of owned) group.appendChild(accountRow(account, platform));
    host.appendChild(group);
  }
}

export async function initSettings() {
  platforms = await loadPlatforms();

  platformSelect().addEventListener("change", () => {
    renderModeOptions();
    renderCredentialFields();
  });
  modeSelect().addEventListener("change", renderCredentialFields);
  form().addEventListener("submit", submitAccount);

  el("btn-add-account").addEventListener("click", () => openAccountModal(null));
  for (const button of all("[data-close]")) {
    button.addEventListener("click", closeAccountModal);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal().hidden) closeAccountModal();
  });

  const settingsForm = el("settings-form");
  const settingsMsg = el("settings-msg");
  const settings = await getBackend().settings();
  settingsForm.elements.auto_refresh_seconds.value = settings.auto_refresh_seconds ?? 300;
  settingsForm.elements.bill_month.value = settings.bill_month ?? "";
  settingsForm.elements.locale.value = settings.locale ?? "zh-CN";
  settingsForm.elements.minimax_base_url.value = settings.minimax_base_url ?? "https://www.minimax.cn";

  settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      auto_refresh_seconds: Number(settingsForm.elements.auto_refresh_seconds.value) || 0,
      bill_month: settingsForm.elements.bill_month.value.trim(),
      locale: settingsForm.elements.locale.value,
      minimax_base_url: settingsForm.elements.minimax_base_url.value.trim(),
    };
    try {
      await getBackend().saveSettings(body);
      settingsMsg.textContent = "已保存";
      settingsMsg.className = "form-msg is-ok";
      window.dispatchEvent(new CustomEvent("aidas:reload"));
    } catch (error) {
      settingsMsg.textContent = error.message;
      settingsMsg.className = "form-msg is-error";
    }
  });

  if (!getBackend().canManageAccounts) {
    const addButton = el("btn-add-account");
    if (addButton) addButton.hidden = true;
    const hint = el("ha-hint");
    if (hint) hint.hidden = false;
  }

  await renderAccounts();
}

export { invalidatePlatformCache };
