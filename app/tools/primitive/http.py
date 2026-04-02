from __future__ import annotations

import httpx

from app.tools import Tool

_MAX = 8192


def make_http_tools() -> list[Tool]:
    async def http_get(url: str, headers: dict | None = None) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
            resp = await c.get(url, headers=headers or {})
            text = resp.text
            if len(text) > _MAX:
                text = text[:_MAX] + f"\n... (truncated, {len(text)} bytes)"
            return text

    async def http_post(url: str, body: dict | None = None, headers: dict | None = None) -> str:
        async with httpx.AsyncClient(timeout=30.0) as c:
            resp = await c.post(url, json=body or {}, headers=headers or {})
            text = resp.text
            if len(text) > _MAX:
                text = text[:_MAX] + f"\n... (truncated, {len(text)} bytes)"
            return text

    return [
        Tool("http_get", "HTTP GET request — returns response body.", {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "headers": {"type": "object", "description": "Optional headers"},
            },
            "required": ["url"],
        }, http_get),
        Tool("http_post", "HTTP POST with JSON body — returns response body.", {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "body": {"type": "object", "description": "JSON body"},
                "headers": {"type": "object", "description": "Optional headers"},
            },
            "required": ["url"],
        }, http_post),
    ]
