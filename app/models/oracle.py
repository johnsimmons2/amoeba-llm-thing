"""Oracle — cloud model escalation for when local agents are stuck."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

STATE_PATH = DATA_DIR / "oracle_state.json"


class Oracle:
    """
    Sends prompts to a configurable cloud API when agents are stuck.

    Tracks daily usage and enforces a hard request cap.
    Supports any OpenAI-compatible API (Claude, Copilot, OpenAI, etc.).
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model: str = "",
        daily_limit: int = 20,
        timeout: float = 120.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.daily_limit = daily_limit
        self.timeout = timeout

        # Persistent state
        self._today: str = ""
        self._used_today: int = 0
        self._load_state()

    @property
    def enabled(self) -> bool:
        return bool(self.api_url and self.api_key and self.model)

    @property
    def remaining(self) -> int:
        self._roll_day()
        return max(0, self.daily_limit - self._used_today)

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    async def ask(self, prompt: str, context: list[dict] | None = None) -> str:
        """Send a question to the cloud model. Returns the response text."""
        if not self.enabled:
            return "Oracle is not configured. Set ORACLE_API_URL, ORACLE_API_KEY, and ORACLE_MODEL."

        self._roll_day()
        if self._used_today >= self.daily_limit:
            return f"Oracle daily limit reached ({self.daily_limit} requests/day). Try again tomorrow."

        messages = []
        messages.append({
            "role": "system",
            "content": (
                "You are a senior expert assistant helping a smaller AI agent that is stuck. "
                "Give clear, actionable advice. Be concise but thorough."
            ),
        })
        if context:
            # Include recent agent history for context
            for m in context[-20:]:
                messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                resp = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": 4096,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            logger.error("Oracle HTTP %d: %s", exc.response.status_code, exc.response.text[:200])
            return f"Oracle error: HTTP {exc.response.status_code}"
        except httpx.RequestError as exc:
            logger.error("Oracle unreachable: %s", exc)
            return f"Oracle unreachable: {exc}"
        except (KeyError, IndexError):
            return "Oracle returned an unexpected response format."

        self._used_today += 1
        self._save_state()
        logger.info("Oracle used (%d/%d today)", self._used_today, self.daily_limit)
        return reply

    # ------------------------------------------------------------------
    # Stuck detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def detect_stuck(history: list[dict], error_window: int = 6, similarity_window: int = 8) -> str | None:
        """
        Analyze agent history to detect stuck patterns.
        Returns a reason string if stuck, None otherwise.
        """
        if len(history) < error_window:
            return None

        recent = history[-error_window * 2:]

        # Pattern 1: consecutive errors
        error_count = 0
        for m in recent:
            content = m.get("content", "")
            if isinstance(content, str) and content.startswith("Error"):
                error_count += 1
        if error_count >= error_window:
            return f"Detected {error_count} errors in the last {len(recent)} messages"

        # Pattern 2: repetitive tool calls (same tool + similar args)
        tool_calls = []
        for m in recent:
            for tc in m.get("tool_calls", []):
                fn = tc.get("function", {})
                tool_calls.append(f"{fn.get('name', '')}:{json.dumps(fn.get('arguments', ''), sort_keys=True)}")
        if len(tool_calls) >= similarity_window:
            last_n = tool_calls[-similarity_window:]
            unique = set(last_n)
            if len(unique) <= 2:
                return f"Repetitive tool calls: {unique}"

        # Pattern 3: circular thoughts (assistant messages too similar)
        thoughts = [
            m["content"][:100]
            for m in recent
            if m.get("role") == "assistant" and m.get("content")
        ]
        if len(thoughts) >= 4:
            last_4 = thoughts[-4:]
            if len(set(last_4)) <= 2:
                return "Circular reasoning detected (repeating same thoughts)"

        return None

    # ------------------------------------------------------------------
    # Daily state persistence
    # ------------------------------------------------------------------

    def _roll_day(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if self._today != today:
            self._today = today
            self._used_today = 0
            self._save_state()

    def _load_state(self) -> None:
        try:
            data = json.loads(STATE_PATH.read_text())
            self._today = data.get("date", "")
            self._used_today = data.get("used", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        self._roll_day()

    def _save_state(self) -> None:
        STATE_PATH.write_text(json.dumps({
            "date": self._today,
            "used": self._used_today,
            "limit": self.daily_limit,
        }))
