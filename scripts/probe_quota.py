"""
额度/重置时间探测脚本（本地一次性测试，不入库）

安全约定：
- API Key 只从环境变量读取，脚本本身绝不硬编码 Key。
- 本脚本所在 scripts/probe_*.py 已加入 .gitignore，且不依赖任何机密文件。

用法：
    export $(grep -v '^#' .env | xargs)   # 或用 dotenv 加载 .env
    python scripts/probe_quota.py

探测目标：
1. 智谱 GLM Coding Plan：chat completions 响应头/体是否含额度信息
2. MiniMax Token Plan：社区接口 coding_plan/remains 是否可用 + chat 响应
3. 对比：哪家能拿到「剩余额度」与「重置时间」
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx


def _mask(s: str | None, keep: int = 8) -> str:
    """打码 key，日志安全。"""
    if not s:
        return "<未设置>"
    if len(s) <= keep:
        return "***"
    return s[:4] + "..." + s[-4:]


def dump_headers(resp: httpx.Response, label: str) -> None:
    print(f"  [{label}] HTTP {resp.status_code}")
    print(f"  [{label}] 响应头（全量）:")
    for k, v in resp.headers.items():
        print(f"      {k}: {v}")


def probe_zhipu() -> None:
    print("\n" + "=" * 60)
    print("探测：智谱 GLM Coding Plan")
    print("=" * 60)
    key = os.environ.get("ZHIPU_API_KEY")
    print(f"ZHIPU_API_KEY = {_mask(key)}")
    if not key:
        print("  ✗ 未设置 ZHIPU_API_KEY，跳过")
        return

    # Coding Plan 专属 base_url，必须带 /coding/
    base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    # 最小探测请求
    payload = {
        "model": "glm-4.5-air",
        "messages": [{"role": "user", "content": "1"}],
        "max_tokens": 1,
        "stream": False,
    }
    url = f"{base_url}/chat/completions"
    print(f"  → POST {url}")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"  ✗ 请求异常: {e!r}")
        return

    dump_headers(resp, "智谱")
    print(f"  [智谱] 响应体:")
    try:
        body = resp.json()
        print("      " + json.dumps(body, ensure_ascii=False, indent=2).replace("\n", "\n      "))
    except Exception:
        print("      " + (resp.text[:2000] if resp.text else "<空>"))

    # 关键：扫描响应头里是否有额度/重置相关字段
    print("\n  ★ 额度相关响应头扫描:")
    interesting = []
    for k, v in resp.headers.items():
        lk = k.lower()
        if any(w in lk for w in ("quota", "remain", "limit", "reset", "ratelimit", "x-rate", "x-quota", "window")):
            interesting.append(f"      {k}: {v}")
    if interesting:
        print("\n".join(interesting))
    else:
        print("      （响应头中未发现 quota/remain/reset/ratelimit 等字段）")


def probe_minimax() -> None:
    print("\n" + "=" * 60)
    print("探测：MiniMax Token Plan")
    print("=" * 60)
    key = os.environ.get("MINIMAX_API_KEY")
    print(f"MINIMAX_API_KEY = {_mask(key)}")
    if not key:
        print("  ✗ 未设置 MINIMAX_API_KEY，跳过")
        return

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    # 1) 先试社区接口 coding_plan/remains
    print("\n  --- (1) 社区接口 GET coding_plan/remains ---")
    remains_url = "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains"
    print(f"  → GET {remains_url}")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(remains_url, headers=headers)
        dump_headers(resp, "MiniMax-remains")
        print(f"  [MiniMax-remains] 响应体:")
        try:
            body = resp.json()
            print("      " + json.dumps(body, ensure_ascii=False, indent=2).replace("\n", "\n      "))
        except Exception:
            print("      " + (resp.text[:2000] if resp.text else "<空>"))
    except Exception as e:
        print(f"  ✗ 请求异常: {e!r}")

    # 2) chat completions 探测
    print("\n  --- (2) OpenAI 兼容 chat completions ---")
    chat_url = "https://api.minimaxi.com/v1/chat/completions"
    payload = {
        "model": "MiniMax-M2.5",
        "messages": [{"role": "user", "content": "1"}],
        "max_tokens": 1,
        "stream": False,
    }
    print(f"  → POST {chat_url}")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(chat_url, headers=headers, json=payload)
        dump_headers(resp, "MiniMax-chat")
        print(f"  [MiniMax-chat] 响应体:")
        try:
            body = resp.json()
            print("      " + json.dumps(body, ensure_ascii=False, indent=2).replace("\n", "\n      "))
        except Exception:
            print("      " + (resp.text[:2000] if resp.text else "<空>"))

        print("\n  ★ 额度相关响应头扫描:")
        interesting = []
        for k, v in resp.headers.items():
            lk = k.lower()
            if any(w in lk for w in ("quota", "remain", "limit", "reset", "ratelimit", "x-rate", "x-quota", "window")):
                interesting.append(f"      {k}: {v}")
        if interesting:
            print("\n".join(interesting))
        else:
            print("      （响应头中未发现 quota/remain/reset/ratelimit 等字段）")
    except Exception as e:
        print(f"  ✗ 请求异常: {e!r}")


if __name__ == "__main__":
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S %z')}")
    probe_zhipu()
    probe_minimax()
    print("\n" + "=" * 60)
    print("探测完成")
