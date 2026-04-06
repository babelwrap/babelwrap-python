# BabelWrap Python SDK

The official Python client for the [BabelWrap](https://babelwrap.com) API — the web, as an API, for your agents.

BabelWrap lets AI agents interact with any website through a simple API. This SDK provides sync and async Python clients.

## Installation

```bash
pip install babelwrap
```

## Quick Start

```python
from babelwrap import BabelWrap

with BabelWrap(api_key="bw_...") as bw:
    with bw.create_session() as session:
        snap = session.navigate("https://example.com")
        print(snap.title)

        # Interact with the page
        session.click("the Login button")
        session.fill("Email address field", "user@example.com")
        session.submit()

        # Extract structured data
        data = session.extract("all product names and prices")
        print(data)
```

## Async Usage

```python
from babelwrap import AsyncBabelWrap

async with AsyncBabelWrap(api_key="bw_...") as bw:
    async with await bw.create_session() as session:
        snap = await session.navigate("https://example.com")
        print(snap.title)

        data = await session.extract("all links on the page")
```

## Features

- **Sync and async** clients
- **Automatic retries** with exponential backoff on transient errors
- **Context managers** for automatic session cleanup
- **Typed snapshots** with attribute access (`snap.title`, `snap.inputs`, `snap.actions`)
- **Site mapping** — discover and generate tools for any website

## API Reference

### `BabelWrap` / `AsyncBabelWrap`

| Method | Description |
|---|---|
| `create_session()` | Create a new browser session |
| `usage()` | Get current usage statistics |
| `health()` | Check API health |
| `map_site(url)` | Map a website and generate tools |
| `list_sites()` | List all mapped sites |
| `site_tools(site_id)` | List tools for a mapped site |
| `execute_tool(site_id, tool, params)` | Execute a generated site tool |

### `Session` / `AsyncSession`

| Method | Description |
|---|---|
| `navigate(url)` | Navigate to a URL |
| `click(target)` | Click an element |
| `fill(target, value)` | Fill a form field |
| `submit(target?)` | Submit a form |
| `extract(query)` | Extract structured data |
| `press(key)` | Press a keyboard key |
| `scroll(direction, amount)` | Scroll the page |
| `hover(target)` | Hover over an element |
| `screenshot()` | Take a screenshot (base64 PNG) |
| `upload(target, file_path)` | Upload a file |
| `back()` / `forward()` | Browser history navigation |
| `snapshot()` | Get current page state |
| `wait_for(text?, selector?, url_contains?)` | Wait for a condition |

## Documentation

Full documentation at [babelwrap.com/docs](https://babelwrap.com/docs/quickstart)

## License

MIT
