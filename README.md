# HAOS 多平台额度看板

一个页面里同时查看 **阿里云百炼**、**MiniMax**、**DeepSeek** 的余额 / 额度余量。
每个平台都支持配置**多个账号**，分别查询、管理、显示。

- 后端：Python 3.12 + FastAPI + httpx + SQLite
- 前端：原生 HTML / CSS / ES Module，零构建
- 密钥：Fernet 加密后落库，接口只返回掩码

---

## 快速开始

```bash
cd ai-usage-dashboard
./run.sh                 # 首次会自动建 venv、装依赖
```

打开 <http://127.0.0.1:8787>，切到「配置」页添加账号，再回到「概览」查看。

自定义端口：

```bash
PORT=9000 ./run.sh
```

跑测试：

```bash
.venv/bin/python -m pytest -q
```

---

## 数据来源（全部为官方接口）

| 平台 / 模式 | 接口 | 认证 | 展示内容 |
|---|---|---|---|
| 阿里云百炼 · 按量付费 | `GET modelstudio.<region>.aliyuncs.com/modelstudio/billing/overview`<br>`GET .../modelstudio/billing/trend`<br>`POST business.aliyuncs.com/?Action=QueryAccountBalance` | AccessKey + **ACS3-HMAC-SHA256** 签名 | 账户可用额度、现金余额、账单费用、税额；**按账期 + 维度筛选**：账单费用构成环形图、账单趋势堆叠柱形图 |
| 阿里云百炼 · 订阅 Token Plan | `GET modelstudio.<region>.aliyuncs.com/tokenplan/subscription/stats`<br>`.../seat-detail`　`.../shared-packages` | 同上 | 剩余 / 已用 Credits、使用率、席位（已分配/总量）、订阅到期、下周期刷新、逐席位与共享包明细 |
| MiniMax · M Plan | `GET www.minimax.cn/v1/token_plan/remains` | `Authorization: Bearer <订阅 Key>` | 剩余额度、额度上限、窗口重置时间（官方未公开响应结构，解析器自适应 + 始终可展开原始 JSON） |
| DeepSeek · 按量付费 | `GET api.deepseek.com/user/balance` | `Authorization: Bearer <API Key>` | 总余额、赠金余额、充值余额、币种 |

> 百炼的 `sk-` 形式 API Key **不能**用于账单 / Token Plan 接口：这些是阿里云 OpenAPI，需要
> AccessKey ID + AccessKey Secret 签名。详见[签名机制](https://help.aliyun.com/zh/sdk/product-overview/v3-request-structure-and-signature)。

---

## 各平台凭据怎么拿

### 阿里云百炼（按量付费 / 订阅 Token Plan 都要 AccessKey）

1. 登录[阿里云 RAM 控制台](https://ram.console.aliyun.com/)，创建或使用一个 RAM 用户。
2. 为它创建 AccessKey（AccessKey ID + AccessKey Secret），保存好 Secret。
3. 授权（最小权限）：
   - 账单概览 / 趋势：`AliyunBSSReadOnlyAccess` 或自定义 `bss:DescribeAcccount`
   - Token Plan 席位与额度：`AliyunModelStudioFullAccess`（或含 `modelstudio:*` 的策略）
4. 在「配置 → 新增账号 → 阿里云百炼」中填写，地域默认 `cn-beijing`。
   - Token Plan 目前仅支持 **华北 2（北京）**。

参考：
- [获取与配置 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)
- [查询账单概览 GetBillingOverview](https://docs.bailian.console.aliyun.com/zh/model-studio/api-modelstudio-2026-02-10-getbillingoverview)
- [查询账单趋势 GetBillingTrend](https://docs.bailian.console.aliyun.com/zh/model-studio/api-modelstudio-2026-02-10-getbillingtrend)
- [获取订阅席位与额度统计](https://help.aliyun.com/zh/model-studio/get-subscription-stats)
- [查询订阅席位明细](https://help.aliyun.com/zh/model-studio/get-subscription-seat-details)
- [查询共享包明细](https://help.aliyun.com/zh/model-studio/list-subscription-shared-packages)
- [Token Plan 概述](https://help.aliyun.com/zh/model-studio/token-plan-overview)

### MiniMax（M Plan 订阅 Key）

1. 登录 [MiniMax 开放平台](https://platform.minimax.cn/)，进入 **订阅管理 > M Plan** 购买套餐。
2. 复制 **订阅 Key**（不是按量计费用的普通 API Key）。
3. 在「配置 → 新增账号 → MiniMax」中粘贴。

额度受 **5 小时窗口 + 周窗口** 双重限制，窗口从首次使用时开始计时；未用完的额度不结转。

参考：[M Plan 常见问题](https://platform.minimax.cn/docs/m-plan/faq)

### DeepSeek（API Key）

1. 登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，在「API Keys」中创建 Key。
2. 在「配置 → 新增账号 → DeepSeek」中粘贴。

参考：[查询余额](https://api-docs.deepseek.com/zh-cn/api/get-user-balance)

---

## 验证签名是否正确

配置好 AccessKey 后，用真实凭据跑一次自检（这是判断签名实现对错的唯一可靠方式）：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID=...
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
.venv/bin/python scripts/verify_acs3.py
```

只想确认「签名格式」被网关接受（不需要真实 AK）：

```bash
.venv/bin/python scripts/verify_acs3.py --dry-run
```

三个接口都应显示「签名格式正确」。

---

## 目录结构

```
app/
  main.py         FastAPI 装配、静态资源、安全响应头
  config.py       路径与全局设置
  crypto.py       Fernet 主密钥 + 加解密
  db.py           SQLite 账号表
  signing.py      ACS3-HMAC-SHA256 签名
  snapshot.py     统一快照数据结构
  service.py      抓取 + 缓存
  scheduler.py    后台定时刷新
  http_client.py  带白名单与重试的 HTTP 封装
  api/            accounts / dashboard / settings 路由
  providers/      aliyun / minimax / deepseek
static/           前端（无构建步骤）
tests/            pytest 用例 + 官方示例 JSON fixtures
scripts/          签名自检脚本
data/             运行时产物（app.db），已 git 忽略
```

## HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/platforms` | 平台 / 模式 / 凭据字段定义（前端表单由此驱动） |
| GET | `/api/accounts` | 账号列表（掩码密钥） |
| POST | `/api/accounts` | 新建账号 |
| PUT | `/api/accounts/{id}` | 更新账号 |
| DELETE | `/api/accounts/{id}` | 删除账号 |
| POST | `/api/accounts/{id}/test` | 连通性测试 |
| GET | `/api/dashboard?refresh=1` | 汇总快照 |
| POST | `/api/accounts/{id}/refresh` | 按当前筛选条件重新抓取并返回完整快照 |
| GET / PUT | `/api/settings` | 全局设置 |

## 安全说明

- 凭据用 Fernet 加密后写入 `data/app.db`（权限 0600），主密钥在 `~/.config/ai-usage-dashboard/key`（权限 0600）。
- 任何接口响应都不含明文凭据，只返回掩码。
- 默认只监听 `127.0.0.1`。
- 外部请求域名走白名单，不接受用户自定义 URL。
- 前端全部走 JSON API + `textContent` 渲染，不做字符串拼接。
