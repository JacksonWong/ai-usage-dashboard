# 大模型额度看板（HAOS / Home Assistant）

在一个页面里同时查看 **阿里云百炼**、**MiniMax**、**DeepSeek** 的余额与额度余量。
每个平台都支持配置**多个账号**，分别查询、管理、显示。

- 既可以作为 **HACS 自定义集成**装进 Home Assistant（左侧边栏出现「大模型额度」面板）
- 也可以**独立部署**（一条命令起一个 uvicorn 服务），两种模式共用同一份核心代码

---

## 一、装到 Home Assistant（HAOS）

### 前置条件

- Home Assistant OS 2024.10 或更高版本
- 已安装 **HACS**（[Home Assistant Community Store](https://hacs.xyz)）

### 安装步骤

1. **添加自定义仓库**

   HACS → 侧边栏 **HACS** → 右上角三个点 → **自定义存储库**（Custom repositories）
   → 填入本仓库地址：

   ```
   https://github.com/JacksonWong/ai-usage-dashboard
   ```

   → 类型选择 **集成**（Integration）→ **添加**。

   > 本仓库为公开仓库，HACS 可直接通过搜索安装；如果你的 HACS 里搜不到「大模型额度看板」，
   > 用上面的「自定义存储库」方式添加即可。

2. **安装集成**

   HACS → **集成** → 搜索「大模型额度看板」→ **下载**。
   下载完成后按提示**重启 Home Assistant**。

3. **添加账号**

   设置 → **设备与服务** → 右下角 **添加集成** → 搜索「大模型额度看板」→ 选择它。

   配置向导分三步，与独立部署的账号表单字段完全一致：

   1. **选择平台**：阿里云百炼 / MiniMax / DeepSeek
   2. **选择账号类型**：
      - 阿里云百炼 → 按量付费 / 订阅 Token Plan
      - MiniMax → M Plan（订阅）
      - DeepSeek → 按量付费
   3. **填写访问凭据**：备注名称 + 该平台对应的凭据字段

4. **打开面板**

   重启后，HAOS 左侧边栏底部会出现 **大模型额度** 面板，点开即是完整看板：
   平台分区、环形图、堆叠柱形图、账期与维度筛选都在里面。

5. **自动刷新**

   默认 **6 小时**自动刷新一次，也可以在面板右上角随时点「刷新」手动更新。

### 各平台凭据怎么拿

#### 阿里云百炼（两种模式都要 AccessKey）

账单概览和 Token Plan 都是**阿里云 OpenAPI**，需要 AccessKey ID + AccessKey Secret
做 ACS3-HMAC-SHA256 签名，**不能用 `sk-` 形式的 API Key**。

1. 登录 [RAM 控制台](https://ram.console.aliyun.com/)，创建 RAM 用户并创建 AccessKey
2. 授权（最小权限）：
   - 账单概览 / 趋势 / 账户额度：`AliyunBSSReadOnlyAccess`
   - Token Plan 席位与额度：含 `modelstudio:*` 的策略
3. 在配置向导里填 AccessKey ID / AccessKey Secret，地域默认 `cn-beijing`

参考：[获取与配置 API Key](https://help.aliyun.com/zh/model-studio/get-api-key) ·
[查询账单概览](https://docs.bailian.console.aliyun.com/zh/model-studio/api-modelstudio-2026-02-10-getbillingoverview) ·
[获取订阅席位与额度统计](https://help.aliyun.com/zh/model-studio/get-subscription-stats)

#### MiniMax（M Plan 订阅 Key）

1. 登录 [MiniMax 开放平台](https://platform.minimax.cn/)，**订阅管理 → M Plan** 购买套餐
2. 复制**订阅 Key**（不是按量计费用的普通 API Key）

参考：[M Plan 常见问题](https://platform.minimax.cn/docs/m-plan/faq)

#### DeepSeek（API Key）

1. 登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，在 API Keys 中创建 Key

参考：[查询余额](https://api-docs.deepseek.com/zh-cn/api/get-user-balance)

### 在面板里能做什么

- **环形图**：所选账期内「账单费用」按当前维度（模型 / API Key）的占比
- **堆叠柱形图**：所选账期内按天的费用堆叠，同样跟随当前维度
- **筛选**：卡片头部可直接改账期（YYYY-MM，可调起原生月份选择器）和维度，切换后自动重取数
- **传感器**：每个账号同时也是一个 HA 实体（`sensor.*`），主指标为状态值，
  完整明细在属性里，可直接用于自动化与告警

---

## 二、独立部署

```bash
git clone https://github.com/JacksonWong/ai-usage-dashboard.git
cd ai-usage-dashboard
./run.sh                 # 首次会自动建 venv、装依赖
```

打开 <http://127.0.0.1:8787>，切到「配置」页添加账号，再回到「概览」查看。

自定义端口：

```bash
PORT=9000 ./run.sh
```

独立模式下：

- 账号保存在 `data/app.db`（SQLite，权限 0600）
- 凭据用 Fernet 加密后落库，主密钥在 `~/.config/ai-usage-dashboard/key`（权限 0600）
- 接口只返回掩码密钥，服务默认只监听 `127.0.0.1`

跑测试：

```bash
.venv/bin/python -m pytest -q
```

### 独立部署 vs HAOS 的差异

| | 独立部署 | Home Assistant |
|---|---|---|
| 添加账号 | 页内「配置」弹窗 | HA 原生配置流（设置 → 设备与服务） |
| 存储 | 本地 SQLite（Fernet 加密） | HA config entry（.storage） |
| 访问 | http://127.0.0.1:8787 | HA 侧边栏「大模型额度」面板 |
| 凭据字段 | 同一份 `PLATFORM_SPECS` 驱动 | 同一份 `PLATFORM_SPECS` 驱动 |

两边的账号表单由同一份 `custom_components/llm_balance/core/models.py` 中的
`PLATFORM_SPECS` 驱动，字段、校验、说明文案完全一致。

---

## 三、目录结构

```
custom_components/llm_balance/     HACS 集成（HAOS 安装的就是这一份）
├── manifest.json                  集成清单
├── config_flow.py                 HA 原生配置流
├── coordinator.py / sensor.py     定时刷新与传感器实体
├── panel.py                       侧边栏面板 + JSON API
├── store.py                       以 config entry 为准的账号存储
├── core/                          与 HA 解耦的核心（两种模式共用）
│   ├── models.py                  账号模型 + 平台/凭据规格
│   ├── providers/                 aliyun / minimax / deepseek
│   ├── signing.py                 ACS3-HMAC-SHA256 签名
│   └── snapshot.py                统一快照结构
└── www/                           前端（面板与独立部署共用）
standalone/                        独立部署入口（uvicorn）
tests/                             pytest 用例 + 官方示例 JSON fixtures
scripts/verify_acs3.py             签名自检脚本
```

---

## 四、数据来源（全部为官方接口）

| 平台 / 模式 | 接口 | 认证 | 展示内容 |
|---|---|---|---|
| 百炼 · 按量付费 | `modelstudio/billing/overview`、`modelstudio/billing/trend`、账务中心 `QueryAccountBalance` | AccessKey + **ACS3-HMAC-SHA256** 签名 | 账户可用额度、现金余额、账单费用、税费；按账期 + 维度筛选，环形图 + 堆叠柱形图 |
| 百炼 · 订阅 Token Plan | `tokenplan/subscription/stats`、`seat-detail`、`shared-packages` | 同上 | 剩余 / 已用 Credits、使用率、席位分配、订阅到期、逐席位明细 |
| MiniMax · M Plan | `GET /v1/token_plan/remains` | `Authorization: Bearer <订阅 Key>` | 剩余额度、额度上限、窗口重置时间（5 小时窗口 + 周窗口） |
| DeepSeek · 按量付费 | `GET /user/balance` | `Authorization: Bearer <API Key>` | 总余额 / 赠金 / 充值 |

验证签名实现是否正确（用真实 AccessKey 打一次线上接口）：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID=...
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
.venv/bin/python scripts/verify_acs3.py
```

---

## 五、安全说明

- 凭据加密后存储；独立模式为 Fernet + 本地主密钥，HA 模式由 HA 的 config entry 机制托管
- 任何接口响应都不含明文凭据，只返回掩码
- 默认只监听 `127.0.0.1`
- 外部请求域名走白名单，不接受用户自定义 URL
- 前端全部走 JSON API + `textContent` 渲染，不做字符串拼接
