"""BabelWrap Python SDK — typed client for the BabelWrap API.

Usage:
    from babelwrap import BabelWrap

    with BabelWrap(api_key="bw_...") as bw:
        with bw.create_session() as session:
            snap = session.navigate("https://example.com")
            print(snap.title)
            for inp in snap.inputs:
                print(f"  {inp.label} ({inp.type}, required={inp.required})")
            data = session.extract("all product names and prices")
        # session auto-closed

Async usage:
    from babelwrap import AsyncBabelWrap

    async with AsyncBabelWrap(api_key="bw_...") as bw:
        async with await bw.create_session() as session:
            snap = await session.navigate("https://example.com")
            print(snap.title)
        # session auto-closed
"""

from __future__ import annotations

import asyncio
import base64
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

T = TypeVar("T")

_RETRYABLE_STATUS = (429, 500, 502, 503, 504)


# ---------------------------------------------------------------------------
# Typed snapshot wrapper — gives attribute access to API response dicts
# ---------------------------------------------------------------------------


class _DictProxy:
    """Wraps a dict so fields are accessible as attributes."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            val = self._data[name]
        except KeyError:
            raise AttributeError(f"No field '{name}'")
        if isinstance(val, dict):
            return _DictProxy(val)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return [_DictProxy(item) for item in val]
        return val

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"Snapshot({self._data.get('url', '')})"

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def to_dict(self) -> dict:
        """Return the raw dict."""
        return self._data


class Snapshot(_DictProxy):
    """Typed snapshot returned by BabelWrap actions.

    Access fields as attributes:
        snap.url, snap.title, snap.content, snap.content_truncated
        snap.inputs[0].label, snap.inputs[0].disabled, snap.inputs[0].required
        snap.actions[0].label, snap.actions[0].primary, snap.actions[0].disabled
        snap.tables[0].headers, snap.tables[0].total_rows
        snap.forms, snap.alerts, snap.navigation, snap.lists, snap.frames

    Or as a dict:
        snap["url"], snap["inputs"][0]["label"]
    """

    pass


class BabelWrapError(Exception):
    """Raised when the BabelWrap API returns an error."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{code}] {message}")


def _check_response(resp: httpx.Response) -> dict:
    """Check response and raise BabelWrapError on failure."""
    if resp.status_code >= 400:
        try:
            data = resp.json()
            err = data.get("error", {})
            raise BabelWrapError(
                code=err.get("code", "unknown"),
                message=err.get("message", resp.text),
                status_code=resp.status_code,
            )
        except (ValueError, KeyError):
            raise BabelWrapError("http_error", resp.text, resp.status_code)
    return resp.json()


def _retry_sync(fn: Callable[[], T], max_retries: int) -> T:
    """Retry with exponential backoff on transient errors."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except BabelWrapError as e:
            if e.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                time.sleep((2**attempt) + random.uniform(0, 1))
                continue
            raise
        except httpx.TransportError:
            if attempt < max_retries:
                time.sleep((2**attempt) + random.uniform(0, 1))
                continue
            raise


async def _retry_async(fn: Callable, max_retries: int) -> Any:
    """Async retry with exponential backoff on transient errors."""
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except BabelWrapError as e:
            if e.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                await asyncio.sleep((2**attempt) + random.uniform(0, 1))
                continue
            raise
        except httpx.TransportError:
            if attempt < max_retries:
                await asyncio.sleep((2**attempt) + random.uniform(0, 1))
                continue
            raise


# ---------------------------------------------------------------------------
# Sync SDK
# ---------------------------------------------------------------------------


class Session:
    """A BabelWrap browser session (sync). Use as a context manager to auto-close."""

    def __init__(self, client: httpx.Client, session_id: str, max_retries: int = 3) -> None:
        self._client = client
        self.session_id = session_id
        self._max_retries = max_retries

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _do(self, method: str, path: str, **kwargs: Any) -> dict:
        """Make an HTTP request with retry."""

        def _call() -> dict:
            resp = self._client.request(method, f"/sessions/{self.session_id}{path}", **kwargs)
            return _check_response(resp)

        return _retry_sync(_call, self._max_retries)

    def navigate(self, url: str) -> Snapshot:
        """Navigate to a URL. Returns the page snapshot."""
        return Snapshot(self._do("POST", "/navigate", json={"url": url}).get("snapshot", {}))

    def click(self, target: str) -> Snapshot:
        """Click an element by natural language description or element ID from the snapshot."""
        return Snapshot(self._do("POST", "/click", json={"target": target}).get("snapshot", {}))

    def fill(self, target: str, value: str) -> Snapshot:
        """Fill a form field."""
        return Snapshot(
            self._do("POST", "/fill", json={"target": target, "value": value}).get("snapshot", {})
        )

    def submit(self, target: str | None = None) -> Snapshot:
        """Submit a form."""
        return Snapshot(self._do("POST", "/submit", json={"target": target}).get("snapshot", {}))

    def extract(self, query: str) -> list[dict] | dict:
        """Extract structured data from the current page."""
        return self._do("POST", "/extract", json={"query": query}).get("data", [])

    def press(self, key: str) -> Snapshot:
        """Press a keyboard key (Enter, Escape, Tab, ArrowDown, etc.)."""
        return Snapshot(self._do("POST", "/press", json={"key": key}).get("snapshot", {}))

    def scroll(self, direction: str = "down", amount: str = "page") -> Snapshot:
        """Scroll the page."""
        return Snapshot(
            self._do("POST", "/scroll", json={"direction": direction, "amount": amount}).get(
                "snapshot", {}
            )
        )

    def hover(self, target: str) -> Snapshot:
        """Hover over an element."""
        return Snapshot(self._do("POST", "/hover", json={"target": target}).get("snapshot", {}))

    def screenshot(self) -> str:
        """Take a screenshot. Returns base64-encoded PNG."""
        return self._do("POST", "/screenshot", json={}).get("image", "")

    def upload(self, target: str, file_path: str) -> Snapshot:
        """Upload a file to a file input field."""
        path = Path(file_path)
        file_b64 = base64.b64encode(path.read_bytes()).decode()
        return Snapshot(
            self._do(
                "POST",
                "/upload",
                json={
                    "target": target,
                    "file_base64": file_b64,
                    "filename": path.name,
                },
            ).get("snapshot", {})
        )

    def back(self) -> Snapshot:
        """Go back to the previous page."""
        return Snapshot(self._do("POST", "/back", json={}).get("snapshot", {}))

    def forward(self) -> Snapshot:
        """Go forward to the next page."""
        return Snapshot(self._do("POST", "/forward", json={}).get("snapshot", {}))

    def snapshot(self) -> Snapshot:
        """Get the current page state without performing any action."""
        return Snapshot(self._do("POST", "/snapshot", json={}).get("snapshot", {}))

    def wait_for(
        self,
        text: str | None = None,
        selector: str | None = None,
        url_contains: str | None = None,
        timeout_ms: int = 10000,
    ) -> dict:
        """Wait for a condition on the page. Returns snapshot + timed_out boolean."""
        body: dict = {"timeout_ms": timeout_ms}
        if text:
            body["text"] = text
        if selector:
            body["selector"] = selector
        if url_contains:
            body["url_contains"] = url_contains
        return self._do("POST", "/wait_for", json=body)

    def history(self) -> list[dict]:
        """Get the action history for this session."""
        return self._do("GET", "/history").get("history", [])

    def batch(self, actions: list[dict], continue_on_error: bool = False) -> dict:
        """Execute a sequence of actions in one call."""
        return self._do(
            "POST", "/batch", json={"actions": actions, "continue_on_error": continue_on_error}
        )

    def close(self) -> None:
        """Close the session and free browser resources."""
        try:
            self._client.delete(f"/sessions/{self.session_id}")
        except Exception:
            pass  # Best-effort cleanup


class BabelWrap:
    """BabelWrap API client (sync).

    Usage:
        with BabelWrap(api_key="bw_...") as bw:
            with bw.create_session() as session:
                session.navigate("https://example.com")
                data = session.extract("all links")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.babelwrap.com",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        self._max_retries = max_retries

    def __enter__(self) -> BabelWrap:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def create_session(
        self, cookies: list[dict] | None = None, metadata: dict | None = None
    ) -> Session:
        """Create a new browser session. Use as a context manager to auto-close."""
        body: dict[str, Any] = {}
        if cookies:
            body["cookies"] = cookies
        if metadata:
            body["metadata"] = metadata

        def _call() -> dict:
            resp = self._client.post("/sessions", json=body)
            return _check_response(resp)

        data = _retry_sync(_call, self._max_retries)
        return Session(self._client, data["session_id"], self._max_retries)

    def usage(self) -> dict:
        """Get current usage statistics."""

        def _call() -> dict:
            return _check_response(self._client.get("/usage"))

        return _retry_sync(_call, self._max_retries)

    def health(self) -> dict:
        """Check API health."""

        def _call() -> dict:
            return _check_response(self._client.get("/health"))

        return _retry_sync(_call, self._max_retries)

    def map_site(self, start_url: str, auth_cookies: list[dict] | None = None) -> dict:
        """Map a website and generate tools."""
        body: dict[str, Any] = {"start_url": start_url}
        if auth_cookies:
            body["auth_cookies"] = auth_cookies

        def _call() -> dict:
            return _check_response(self._client.post("/sites/map", json=body, timeout=600))

        return _retry_sync(_call, self._max_retries)

    def list_sites(self) -> list[dict]:
        """List all mapped sites."""

        def _call() -> dict:
            return _check_response(self._client.get("/sites"))

        return _retry_sync(_call, self._max_retries)

    def site_tools(self, site_id: str) -> dict:
        """List tools for a mapped site."""

        def _call() -> dict:
            return _check_response(self._client.get(f"/sites/{site_id}/tools"))

        return _retry_sync(_call, self._max_retries)

    def execute_tool(self, site_id: str, tool_name: str, params: dict | None = None) -> dict:
        """Execute a generated site tool."""

        def _call() -> dict:
            return _check_response(
                self._client.post(
                    f"/sites/{site_id}/tools/{tool_name}",
                    json={"params": params or {}},
                    timeout=120,
                )
            )

        return _retry_sync(_call, self._max_retries)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()


# ---------------------------------------------------------------------------
# Async SDK
# ---------------------------------------------------------------------------


class AsyncSession:
    """A BabelWrap browser session (async). Use as a context manager to auto-close."""

    def __init__(self, client: httpx.AsyncClient, session_id: str, max_retries: int = 3) -> None:
        self._client = client
        self.session_id = session_id
        self._max_retries = max_retries

    async def __aenter__(self) -> AsyncSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _do(self, method: str, path: str, **kwargs: Any) -> dict:
        """Make an HTTP request with retry."""

        async def _call() -> dict:
            resp = await self._client.request(
                method, f"/sessions/{self.session_id}{path}", **kwargs
            )
            return _check_response(resp)

        return await _retry_async(_call, self._max_retries)

    async def navigate(self, url: str) -> Snapshot:
        return Snapshot(
            (await self._do("POST", "/navigate", json={"url": url})).get("snapshot", {})
        )

    async def click(self, target: str) -> Snapshot:
        return Snapshot(
            (await self._do("POST", "/click", json={"target": target})).get("snapshot", {})
        )

    async def fill(self, target: str, value: str) -> Snapshot:
        return Snapshot(
            (await self._do("POST", "/fill", json={"target": target, "value": value})).get(
                "snapshot", {}
            )
        )

    async def submit(self, target: str | None = None) -> Snapshot:
        return Snapshot(
            (await self._do("POST", "/submit", json={"target": target})).get("snapshot", {})
        )

    async def extract(self, query: str) -> list[dict] | dict:
        return (await self._do("POST", "/extract", json={"query": query})).get("data", [])

    async def press(self, key: str) -> Snapshot:
        return Snapshot((await self._do("POST", "/press", json={"key": key})).get("snapshot", {}))

    async def scroll(self, direction: str = "down", amount: str = "page") -> Snapshot:
        return Snapshot(
            (
                await self._do("POST", "/scroll", json={"direction": direction, "amount": amount})
            ).get("snapshot", {})
        )

    async def hover(self, target: str) -> Snapshot:
        return Snapshot(
            (await self._do("POST", "/hover", json={"target": target})).get("snapshot", {})
        )

    async def screenshot(self) -> str:
        return (await self._do("POST", "/screenshot", json={})).get("image", "")

    async def upload(self, target: str, file_path: str) -> Snapshot:
        path = Path(file_path)
        file_b64 = base64.b64encode(path.read_bytes()).decode()
        return Snapshot(
            (
                await self._do(
                    "POST",
                    "/upload",
                    json={
                        "target": target,
                        "file_base64": file_b64,
                        "filename": path.name,
                    },
                )
            ).get("snapshot", {})
        )

    async def back(self) -> Snapshot:
        return Snapshot(await self._do("POST", "/back", json={}).get("snapshot", {}))

    async def forward(self) -> Snapshot:
        return Snapshot(await self._do("POST", "/forward", json={}).get("snapshot", {}))

    async def snapshot(self) -> Snapshot:
        return Snapshot(await self._do("POST", "/snapshot", json={}).get("snapshot", {}))

    async def wait_for(
        self,
        text: str | None = None,
        selector: str | None = None,
        url_contains: str | None = None,
        timeout_ms: int = 10000,
    ) -> dict:
        body: dict = {"timeout_ms": timeout_ms}
        if text:
            body["text"] = text
        if selector:
            body["selector"] = selector
        if url_contains:
            body["url_contains"] = url_contains
        return await self._do("POST", "/wait_for", json=body)

    async def history(self) -> list[dict]:
        return (await self._do("GET", "/history")).get("history", [])

    async def batch(self, actions: list[dict], continue_on_error: bool = False) -> dict:
        return await self._do(
            "POST", "/batch", json={"actions": actions, "continue_on_error": continue_on_error}
        )

    async def close(self) -> None:
        try:
            await self._client.delete(f"/sessions/{self.session_id}")
        except Exception:
            pass  # Best-effort cleanup


class AsyncBabelWrap:
    """BabelWrap API client (async).

    Usage:
        async with AsyncBabelWrap(api_key="bw_...") as bw:
            async with await bw.create_session() as session:
                await session.navigate("https://example.com")
                data = await session.extract("all links")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.babelwrap.com",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        self._max_retries = max_retries

    async def __aenter__(self) -> AsyncBabelWrap:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def create_session(
        self, cookies: list[dict] | None = None, metadata: dict | None = None
    ) -> AsyncSession:
        body: dict[str, Any] = {}
        if cookies:
            body["cookies"] = cookies
        if metadata:
            body["metadata"] = metadata

        async def _call() -> dict:
            resp = await self._client.post("/sessions", json=body)
            return _check_response(resp)

        data = await _retry_async(_call, self._max_retries)
        return AsyncSession(self._client, data["session_id"], self._max_retries)

    async def usage(self) -> dict:
        async def _call() -> dict:
            return _check_response(await self._client.get("/usage"))

        return await _retry_async(_call, self._max_retries)

    async def health(self) -> dict:
        async def _call() -> dict:
            return _check_response(await self._client.get("/health"))

        return await _retry_async(_call, self._max_retries)

    async def map_site(self, start_url: str, auth_cookies: list[dict] | None = None) -> dict:
        body: dict[str, Any] = {"start_url": start_url}
        if auth_cookies:
            body["auth_cookies"] = auth_cookies

        async def _call() -> dict:
            return _check_response(await self._client.post("/sites/map", json=body, timeout=600))

        return await _retry_async(_call, self._max_retries)

    async def list_sites(self) -> list[dict]:
        async def _call() -> dict:
            return _check_response(await self._client.get("/sites"))

        return await _retry_async(_call, self._max_retries)

    async def site_tools(self, site_id: str) -> dict:
        async def _call() -> dict:
            return _check_response(await self._client.get(f"/sites/{site_id}/tools"))

        return await _retry_async(_call, self._max_retries)

    async def execute_tool(self, site_id: str, tool_name: str, params: dict | None = None) -> dict:
        async def _call() -> dict:
            return _check_response(
                await self._client.post(
                    f"/sites/{site_id}/tools/{tool_name}",
                    json={"params": params or {}},
                    timeout=120,
                )
            )

        return await _retry_async(_call, self._max_retries)

    async def close(self) -> None:
        await self._client.aclose()
