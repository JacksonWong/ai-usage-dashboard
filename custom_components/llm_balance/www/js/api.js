/**
 * 后端适配层。
 *
 * 独立部署模式走 fetch + /api/*；Home Assistant 面板模式走 hass.callApi。
 * 两种模式暴露完全相同的方法，上层无需区分。
 */

async function readError(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const detail = payload?.detail || payload?.Message || payload?.message;
  return new Error(
    typeof detail === "string" ? detail : `HTTP ${response.status}`
  );
}

function standaloneBackend() {
  const call = async (method, path, body) => {
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) throw await readError(response);
    return response.json();
  };
  return {
    mode: "standalone",
    canManageAccounts: true,
    platforms: () => call("GET", "/api/platforms"),
    dashboard: (refresh) => call("GET", `/api/dashboard?refresh=${refresh ? 1 : 0}`),
    accounts: () => call("GET", "/api/accounts"),
    createAccount: (body) => call("POST", "/api/accounts", body),
    updateAccount: (id, body) => call("PUT", `/api/accounts/${id}`, body),
    deleteAccount: (id) => call("DELETE", `/api/accounts/${id}`),
    testAccount: (id) => call("POST", `/api/accounts/${id}/test`),
    refreshAccount: (id) => call("POST", `/api/accounts/${id}/refresh`),
    settings: () => call("GET", "/api/settings"),
    saveSettings: (body) => call("PUT", "/api/settings", body),
  };
}

function haBackend(hass) {
  const call = async (method, path, body) => {
    if (body === undefined) return hass.callApi(method, path);
    return hass.callApi(method, path, body);
  };
  return {
    mode: "ha",
    // Home Assistant 侧新增账号走原生配置流（设置 → 设备与服务）
    canManageAccounts: false,
    platforms: () => call("GET", "llm_balance/platforms"),
    dashboard: (refresh) => call("GET", `llm_balance/dashboard?refresh=${refresh ? 1 : 0}`),
    accounts: () => call("GET", "llm_balance/accounts"),
    createAccount: (body) => call("POST", "llm_balance/accounts", body),
    updateAccount: (id, body) => call("PUT", `llm_balance/accounts/${id}`, body),
    deleteAccount: (id) => call("DELETE", `llm_balance/accounts/${id}`),
    testAccount: async (id) => {
      const snapshot = await call("POST", `llm_balance/accounts/${id}/refresh`);
      return {
        ok: snapshot.status === "ok",
        error: snapshot.error,
        latency_ms: snapshot.latency_ms,
        metrics: snapshot.metrics,
      };
    },
    refreshAccount: (id) => call("POST", `llm_balance/accounts/${id}/refresh`),
    settings: () => call("GET", "llm_balance/settings"),
    saveSettings: (body) => call("PUT", "llm_balance/settings", body),
  };
}

export { standaloneBackend, haBackend };
