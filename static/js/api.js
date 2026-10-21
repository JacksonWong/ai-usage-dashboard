const JSON_HEADERS = { "Content-Type": "application/json" };

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body ? JSON_HEADERS : undefined,
    ...options,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload?.detail || payload?.Message || `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

export const api = {
  platforms: () => request("/api/platforms"),
  dashboard: (refresh = false) => request(`/api/dashboard?refresh=${refresh ? 1 : 0}`),
  accounts: () => request("/api/accounts"),
  createAccount: (body) => request("/api/accounts", { method: "POST", body: JSON.stringify(body) }),
  updateAccount: (id, body) => request(`/api/accounts/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteAccount: (id) => request(`/api/accounts/${id}`, { method: "DELETE" }),
  testAccount: (id) => request(`/api/accounts/${id}/test`, { method: "POST" }),
  refreshAccount: (id) => request(`/api/accounts/${id}/refresh`, { method: "POST" }),
  settings: () => request("/api/settings"),
  saveSettings: (body) => request("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
};
