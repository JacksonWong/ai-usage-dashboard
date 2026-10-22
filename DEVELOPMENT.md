# 开发环境手册

本文件记录**在这台机器上**开发与验证本项目所需的全部环境事实与命令。
代码层面的设计见 `README.md`；每次迭代的结论见 `README.md` 的「变更记录」与各 commit 正文。

> 新会话冷启动时，先读本文件 + `README.md`，再读 `tests/test_ha_integration.py`
> （它同时是集成行为的活文档）。

---

## 一、机器与网络事实（WSL2 / Ubuntu）

| 事实 | 说明 |
|---|---|
| **没有 sudo** | 不能 `apt install`；缺系统库时下载 `.deb` 用 `dpkg-deb -x` 解到本地目录，靠 `LD_LIBRARY_PATH` 使用 |
| **Python 包管理用 `uv`** | 位于 `~/.local/bin/uv`。系统 `python3`(3.12) 没有 pip/ensurepip；项目 `.venv` 由 uv 创建 |
| **git 全局代理是死的** | `~/.gitconfig` 里 `http.proxy=http://127.0.0.1:7892`，该端口未监听。**HTTPS 方式的 git 操作会失败**；需要时加 `-c http.proxy= -c https.proxy=` 绕过，或走 SSH |
| **github.com 网页不可达** | `https://github.com`（含 `/login/device` 设备流）超时。**`api.github.com` 正常**（~0.3s），**SSH 到 github 正常**（密钥已认证为 `JacksonWong`） |
| 因此 | 建仓/建 Release 只能在用户浏览器里做；推送走 SSH；查 GitHub 元数据走 api.github.com |
| 中文字体 | 已装 Noto CJK 到 `~/.local/share/fonts`（持久）。无头浏览器截图中文正常 |
| Playwright 浏览器 | 已装在 `~/.cache/ms-playwright`（持久）。但**缺系统共享库**，见下文 |

---

## 二、三套环境

### 1. 项目虚拟环境（持久，在仓库内）

```bash
cd ai-usage-dashboard
uv venv .venv
uv pip install --python .venv/bin/python fastapi "uvicorn[standard]" httpx cryptography pytest pytest-asyncio
```

或直接 `./run.sh`（会自动建 venv、装依赖、起服务）。

### 2. Home Assistant 集成测试环境（在 /tmp，重启即失，需重建）

```bash
export PATH="$HOME/.local/bin:$PATH"
uv venv /tmp/haenv --python 3.12
uv pip install --python /tmp/haenv/bin/python pytest-homeassistant-custom-component==0.13.199
# 若报 "module 'josepy' has no attribute 'ComparableX509'"（acme/josepy 不兼容）：
uv pip install --python /tmp/haenv/bin/python josepy==1.14.0
```

运行（**必须在仓库根目录**，harness 从根目录的 `custom_components/` 发现集成）：

```bash
cd ai-usage-dashboard
/tmp/haenv/bin/python -m pytest tests/test_ha_integration.py -q
```

注意：`pyproject.toml` 已设 `asyncio_mode = auto`，harness 的 `hass` / `hass_client` /
`enable_custom_integrations` 夹具依赖它；改动 pytest 配置时别丢。

### 3. 无头浏览器验证环境（部分持久）

Chromium 缺 `libnspr4 / libnss3 / libasound2t64`。无 sudo 的装法：

```bash
mkdir -p /tmp/chromedeps/root && cd /tmp/chromedeps
base=http://archive.ubuntu.com/ubuntu/pool/main
curl -sLO $base/n/nspr/libnspr4_4.35-1.1build1_amd64.deb
curl -sLO $base/n/nss/libnss3_3.98-1build1_amd64.deb
curl -sLO $base/a/alsa-lib/libasound2t64_1.2.14-1ubuntu1_amd64.deb
for d in *.deb; do dpkg-deb -x "$d" root; done
export LD_LIBRARY_PATH=/tmp/chromedeps/root/usr/lib/x86_64-linux-gnu
```

Node 侧（`/tmp/uitest` 也是临时的，脚本本体已入库）：

```bash
mkdir -p /tmp/uitest && cd /tmp/uitest && npm init -y && npm i playwright
npx playwright install chromium          # 浏览器落在 ~/.cache/ms-playwright（持久）
node /path/to/ai-usage-dashboard/scripts/ui/verify.js http://127.0.0.1:8787
```

`scripts/ui/verify.js` 会按 4 种视口断言栅格列数、无横向溢出、图表渲染、无 console 报错，
并截图到 `/tmp/aidash-shots/`。

---

## 三、测试入口速查

```bash
# 单元 / 解析 / 独立部署 API（HA 用例自动跳过）
.venv/bin/python -m pytest -q

# HA 集成运行时测试（需环境 2）
/tmp/haenv/bin/python -m pytest tests/test_ha_integration.py -q

# 签名算法的线上自检（假 AK，验证网关接受签名格式）
.venv/bin/python scripts/verify_acs3.py --dry-run
# 带真实 AK 的完整自检
ALIBABA_CLOUD_ACCESS_KEY_ID=... ALIBABA_CLOUD_ACCESS_KEY_SECRET=... \
  .venv/bin/python scripts/verify_acs3.py

# 签名用例打真实网关（可选）
AIDASH_NETWORK_TESTS=1 .venv/bin/python -m pytest tests/test_signing.py -q

# 浏览器验证（需环境 3 + 独立部署服务在跑）
node scripts/ui/verify.js
```

---

## 四、独立部署服务管理

```bash
cd ai-usage-dashboard
# 停（按端口找 PID，别用 pkill 匹配命令行，会误杀自己的 shell）
PID=$(ss -lptn 'sport = :8787' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$PID" ] && kill "$PID"
# 起（脱离会话）
setsid nohup .venv/bin/python -m uvicorn standalone.main:app --host 127.0.0.1 --port 8787 \
  > /tmp/aidash.log 2>&1 < /dev/null &
```

数据与密钥：

- 账号库 `data/app.db`（0600），全局设置 `data/settings.json`
- Fernet 主密钥 `~/.config/ai-usage-dashboard/key`（0600）——**删了它所有凭据就解不开了**

---

## 五、踩过的坑（HA / 平台 API）

改 HA 侧代码前先看这里，多数是花真金白银的时间换回来的：

**Home Assistant**

1. `frontend_url_path` **不能带前导斜杠**。前端按 `/{url_path}` 拼路由，`/llm_balance` 会变成
   `//llm_balance`，被浏览器当协议相对 URL 解析成 `http://llm_balance/`。
2. `module_url` 必须指向**真实存在**的文件（`www/js/panel.js`，不是 `www/panel.js`）。
   见 `tests/test_ha_integration.py::test_panel_module_url_points_at_real_file`。
3. 选项流（OptionsFlow）的 `async_create_entry(data=...)` 会**整体替换** `entry.options`，
   返回空 dict 会清空凭据。
4. 2025.1+ 的 `OptionsFlow` 由框架关联 config entry（`self.handler` = entry_id），
   构造函数**不接参数**；2025.12 起手动赋值 `self.config_entry` 会报错。
   兼容写法见 `config_flow.py::_entry`。
5. `SensorEntity` 只要设了单位或 `state_class`，状态就必须能 `float()`。
   格式化文案放属性，别放 `native_value`。
6. `httpx.AsyncClient()` 构造会同步加载 CA 证书 → 阻塞调用告警。必须在 executor 线程里建。
7. 多个 config entry **并发** setup：注册面板/静态路径要加锁，否则 `Overwriting panel`。
8. `async_config_entry_first_refresh` 失败会让配置项进重试状态、面板消失；
   网络型集成用 `async_refresh()` 更稳。
9. 视图里取 hass 用 `homeassistant.helpers.http.KEY_HASS`；URL 参数由 HA 以关键字参数传入
   （`async def get(self, request, account_id: str)`），别自己切 path。

**平台 API**

10. 百炼账单/Token Plan 接口是阿里云 OpenAPI，**只认 AccessKey + ACS3-HMAC-SHA256 签名**，
    `sk-` 形式的 API Key 会被网关拒（`MissingAccessKeyId`）。签名实现见 `core/signing.py`。
11. `filter` / `timePeriod` 这类嵌套参数的序列化官方没写死；代码里用「JSON 形式优先、
    400 时降级扁平形式」的双变体兜底（`AliyunProvider._call_variants`）。别简化掉。
12. MiniMax `/v1/token_plan/remains` **官方未公开响应结构**。已知稳定形态是
    `model_remains[]`（general/video × 5 小时窗口/周窗口）；解析器对该形态专用解析，
    其余形态走自适应兜底，且永远保留原始 JSON 供展开查看。
13. 百炼 `GetBillingTrend` 的 `groupByTotal` + `resultByTime.periodDetails` 一次就能给出
    「按维度月度合计」和「按天按维度明细」，环形图与堆叠柱形图都取自它，不要再多加 overview 调用。

---

## 六、发布流程

1. 改 `custom_components/llm_balance/manifest.json` 与 `const.py` 的 `VERSION`（保持一致）
2. `git tag -a vX.Y.Z && git push origin main vX.Y.Z`（SSH 可用）
3. **Release 只能在用户浏览器建**（github.com 网页从这里不可达）：
   Releases → Draft a new release → 选 tag → Publish。HACS 靠 Release 识别版本
4. 用户在 HAOS 上：HACS → 更新 → 重启 Home Assistant

仅文档/测试改动不需要新版本号与 Release。
