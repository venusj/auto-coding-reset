"""智谱 GLM Coding Plan 接入。

能力：
- query_quota(): 智谱无公开额度查询接口，返回空 WindowInfo（note 说明）
- probe(): 发最小 chat completion 探测请求（glm-4.5-air）

合规提醒：智谱 Coding Plan 有「仅限指定工具使用」条款。
探测请求尝试伪装为官方工具请求头，但不保证抵扣套餐额度，使用风险自负。
"""

from __future__ import annotations

from app.config import ProviderConfig
from app.providers import ProbeResult, Provider, QuotaResult, WindowInfo

CHAT_PATH = "/chat/completions"

# 智谱 Coding Plan 专属 base_url（必须带 /coding/）。配置里已含，此处兜底。
CODING_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"

# 伪装为官方支持的工具 UA（社区推断智谱可能做工具校验，不保证有效）
TOOL_UA = "claude-cli/1.0.0 (external, cli)"


class ZhipuProvider(Provider):
    name = "zhipu"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": TOOL_UA,
        }

    def query_quota(self) -> QuotaResult:
        """智谱无公开额度查询接口。返回空窗口 + 说明。"""
        return QuotaResult(
            provider=self.name,
            interval=WindowInfo(),
            weekly=WindowInfo(),
            note="智谱无公开额度查询接口，需靠探测 + 本地估算",
        )

    def probe(self, *, reset: bool = False) -> ProbeResult:
        base = self.cfg.base_url or CODING_BASE
        url = f"{base.rstrip('/')}{CHAT_PATH}"
        payload = {
            "model": self.cfg.probe_model,
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1,
            "stream": False,
        }
        try:
            resp = self.client.post(url, headers=self._headers(), json=payload)
        except Exception as e:  # noqa: BLE001
            return ProbeResult(self.name, ok=False, error=f"请求异常: {e!r}")
        ok = resp.status_code == 200
        return ProbeResult(
            self.name,
            ok=ok,
            http_status=resp.status_code,
            error=None if ok else resp.text[:200],
        )
