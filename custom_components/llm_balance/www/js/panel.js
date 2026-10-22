/**
 * Home Assistant 侧边栏面板组件。
 *
 * 面板内容与独立部署模式完全一致（同一份模板、同一份图表代码），
 * 只是数据来源换成 hass.callApi。
 */

import { haBackend } from "./api.js";
import { mountApp } from "./app.js";

const STATIC_BASE = "/llm_balance_static";

class LlmBalancePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._mounted = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    this._render();
  }

  async _render() {
    if (!this._hass || this._mounted) return;
    this._mounted = true;

    const style = document.createElement("style");
    try {
      const response = await fetch(`${STATIC_BASE}/css/app.css`);
      style.textContent = await response.text();
    } catch (error) {
      style.textContent = `:host{display:block;padding:16px;font-family:sans-serif}`;
    }
    this.shadowRoot.appendChild(style);

    const shell = document.createElement("div");
    shell.className = "app-shell";
    this.shadowRoot.appendChild(shell);

    await mountApp(shell, haBackend(this._hass));
  }
}

if (!customElements.get("llm-balance-panel")) {
  customElements.define("llm-balance-panel", LlmBalancePanel);
}
