/** 应用模板：独立部署与 Home Assistant 面板共用同一份结构。 */

export const APP_HTML = `
<div class="aurora" aria-hidden="true"></div>

  <header class="topbar">
    <div class="topbar__brand">
      <span class="brand__mark" aria-hidden="true"></span>
      <div>
        <h1>大模型额度看板</h1>
      </div>
    </div>

    <nav class="tabs" role="tablist">
      <button class="tab is-active" data-view="dashboard" role="tab" aria-selected="true">概览</button>
      <button class="tab" data-view="settings" role="tab" aria-selected="false">配置</button>
    </nav>

    <div class="topbar__stats">
      <div class="stat">
        <span class="stat__label">账号</span>
        <span class="stat__value" id="stat-total">--</span>
      </div>
      <div class="stat">
        <span class="stat__label">正常</span>
        <span class="stat__value stat__value--ok" id="stat-ok">--</span>
      </div>
      <div class="stat">
        <span class="stat__label">异常</span>
        <span class="stat__value stat__value--bad" id="stat-failed">--</span>
      </div>
      <div class="stat">
        <span class="stat__label">更新</span>
        <span class="stat__value stat__value--sm" id="stat-updated">--</span>
      </div>
    </div>

    <div class="topbar__actions">
      <label class="switch" title="自动刷新">
        <input type="checkbox" id="auto-refresh" />
        <span class="switch__track"><span class="switch__thumb"></span></span>
      </label>
      <button class="btn btn--ghost" id="btn-refresh" type="button">
        <span class="btn__icon">↻</span> 刷新
      </button>
    </div>
  </header>

  <main>
    <!-- ============================ 概览 ============================ -->
    <section class="view is-active" id="view-dashboard" role="tabpanel">
      <div class="legend" id="platform-legend" hidden></div>

      <div id="platform-sections" class="platforms"></div>

      <div class="empty" id="dashboard-empty" hidden>
        <div class="empty__icon">◍</div>
        <h3>还没有接入任何账号</h3>
        <p>前往「配置」添加阿里云百炼、MiniMax 或 DeepSeek 的访问凭据，即可在这里统一查看余额与额度余量。</p>
        <button class="btn btn--primary" data-goto="settings" type="button">去配置</button>
      </div>
    </section>

    <!-- ============================ 配置 ============================ -->
    <section class="view" id="view-settings" role="tabpanel">
      <div class="panel">
        <div class="panel__head">
          <h2>全局设置</h2>
          <p>影响所有账号的默认行为。</p>
        </div>
        <form class="settings-form" id="settings-form">
          <label class="field">
            <span class="field__label">自动刷新间隔（秒）</span>
            <input type="number" name="auto_refresh_seconds" min="0" max="86400" step="30" />
            <span class="field__hint">填 0 关闭后台自动刷新；前端仍可手动刷新。</span>
          </label>
          <label class="field">
            <span class="field__label">默认账期月份</span>
            <input type="text" name="bill_month" placeholder="留空 = 当前账期" />
            <span class="field__hint">格式 YYYY-MM，用于百炼账单概览与趋势。</span>
          </label>
          <label class="field">
            <span class="field__label">返回语言</span>
            <select name="locale">
              <option value="zh-CN">中文 (zh-CN)</option>
              <option value="en-US">English (en-US)</option>
            </select>
          </label>
          <label class="field">
            <span class="field__label">MiniMax 接口域名</span>
            <input type="text" name="minimax_base_url" placeholder="https://www.minimax.cn" />
            <span class="field__hint">国内站保持默认；国际站可改为 https://api.minimax.chat</span>
          </label>
          <div class="settings-form__actions">
            <button class="btn btn--primary" type="submit">保存设置</button>
            <span class="form-msg" id="settings-msg"></span>
          </div>
        </form>
      </div>

      <div class="panel">
        <div class="panel__head panel__head--row">
          <div>
            <h2>账号管理</h2>
            <p>每个平台可添加多个账号，分别查询与展示。</p>
          </div>
          <button class="btn btn--primary" id="btn-add-account" type="button">+ 新增账号</button>
          <p class="panel__hint" id="ha-hint" hidden>在 Home Assistant 中请通过 「设置 → 设备与服务 → 添加集成 → 大模型额度看板」添加账号。</p>
        </div>
        <div id="account-list" class="account-list"></div>
      </div>
    </section>
  </main>

  <!-- ============================ 账号弹窗 ============================ -->
  <div class="modal" id="account-modal" hidden>
    <div class="modal__backdrop" data-close></div>
    <div class="modal__panel" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <header class="modal__head">
        <h3 id="modal-title">新增账号</h3>
        <button class="icon-btn" type="button" data-close aria-label="关闭">✕</button>
      </header>
      <form class="modal__body" id="account-form">
        <input type="hidden" name="id" />
        <label class="field">
          <span class="field__label">平台</span>
          <select name="platform" id="account-platform"></select>
        </label>
        <label class="field">
          <span class="field__label">账号类型</span>
          <select name="mode" id="account-mode"></select>
          <span class="field__hint" id="mode-hint"></span>
        </label>
        <label class="field">
          <span class="field__label">备注名称</span>
          <input type="text" name="label" placeholder="例如：主力账号 / 备用 Key" maxlength="64" required />
        </label>
        <div id="credential-fields" class="credential-fields"></div>
        <div class="modal__actions">
          <button class="btn btn--ghost" type="button" data-close>取消</button>
          <button class="btn btn--primary" type="submit" id="account-submit">保存</button>
          <span class="form-msg" id="account-msg"></span>
        </div>
      </form>
    </div>
  </div>

  <div class="toasts" id="toasts" aria-live="polite"></div>
`;
