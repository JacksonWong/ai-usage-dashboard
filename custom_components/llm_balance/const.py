"""集成常量。"""

from __future__ import annotations

DOMAIN = "llm_balance"
NAME = "大模型额度看板"
VERSION = "1.0.1"

# 侧边栏面板
PANEL_URL_PATH = DOMAIN
PANEL_TITLE = "大模型额度"
PANEL_ICON = "mdi:chart-donut"

# 静态资源前缀
STATIC_URL = f"/{DOMAIN}_static"

# 自动刷新间隔（秒）：固定 6 小时，用户可随时手动刷新
REFRESH_INTERVAL = 6 * 3600
DEFAULT_REFRESH_INTERVAL = REFRESH_INTERVAL
MIN_REFRESH_INTERVAL = REFRESH_INTERVAL

# 面板 API 路径前缀（homeassistant 的 callApi 用不带前导斜杠的写法）
API_PREFIX = DOMAIN
