"""Home Calling Bell -- FastAPI edition.

Three delivery channels, all fired by one press of the button:

1. Live SSE  -> any /receive tab that is currently open (in-page flash + beep)
2. Web Push  -> real OS notification even when /receive is CLOSED
                (needs HTTPS + VAPID keys; see README)
3. ntfy      -> push to the ntfy phone app, works with the app fully closed
                (set NTFY_TOPIC; self-host ntfy to stay LAN-only)
4. Desktop client (bell_client.py) -> native notification on a PC, no browser

Run:  python app.py
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CERT_DIR = BASE_DIR / "certs"
SUBS_FILE = BASE_DIR / "subscriptions.json"
VAPID_PRIVATE = BASE_DIR / "vapid_private.pem"
VAPID_PUBLIC = BASE_DIR / "vapid_public.txt"

PORT = int(os.environ.get("BELL_PORT", "5000"))
HOST = "0.0.0.0"  # LAN only -- never expose this to the public internet.

# Optional ntfy push (works even when the phone app is closed).
# Self-host ntfy on your LAN to keep everything on the home network.
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "").strip()

# Contact address embedded in VAPID claims (any mailto: works).
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:bell@home.local")

app = FastAPI(title="Home Calling Bell", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Live listeners: every open /receive tab and desktop client holds one Queue.
# ---------------------------------------------------------------------------
_listeners: set[asyncio.Queue] = set()
_lock = asyncio.Lock()


async def _broadcast(payload: dict) -> int:
    async with _lock:
        targets = list(_listeners)
    for queue in targets:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass
    return len(targets)


# ---------------------------------------------------------------------------
# Web Push subscription storage (a small JSON file; no database needed)
# ---------------------------------------------------------------------------
def _load_subs() -> list[dict]:
    if not SUBS_FILE.exists():
        return []
    try:
        data = json.loads(SUBS_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_subs(subs: list[dict]) -> None:
    SUBS_FILE.write_text(json.dumps(subs, indent=2))


def _vapid_public_key() -> str:
    if VAPID_PUBLIC.exists():
        return VAPID_PUBLIC.read_text().strip()
    return ""


def _push_ready() -> bool:
    return VAPID_PRIVATE.exists() and bool(_vapid_public_key())


def _send_web_push(payload: dict) -> int:
    """Blocking; called in a thread. Returns number of successful pushes."""
    if not _push_ready():
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        print("[push] pywebpush not installed -- skipping Web Push")
        return 0

    subs = _load_subs()
    if not subs:
        return 0

    body = json.dumps(payload)
    sent, survivors = 0, []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=body,
                vapid_private_key=str(VAPID_PRIVATE),
                vapid_claims={"sub": VAPID_SUBJECT},
                ttl=60,
            )
            sent += 1
            survivors.append(sub)
        except WebPushException as exc:  # type: ignore[misc]
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                print("[push] dropping expired subscription")
                continue  # subscription is dead -- forget it
            print(f"[push] failed ({status}): {exc}")
            survivors.append(sub)
        except Exception as exc:
            print(f"[push] error: {exc}")
            survivors.append(sub)

    if len(survivors) != len(subs):
        _save_subs(survivors)
    return sent


def _send_ntfy(payload: dict) -> bool:
    """Blocking; called in a thread."""
    if not NTFY_TOPIC:
        return False
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    headers = {
        "Title": "Home Calling Bell",
        "Priority": "urgent",
        "Tags": "bell",
        "Content-Type": "text/plain; charset=utf-8",
    }
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
    req = urllib.request.Request(
        url,
        data=str(payload.get("message", "Someone is at the door!")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        print(f"[ntfy] failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Pages / assets
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/ring")
async def ring_page():
    return FileResponse(STATIC_DIR / "ring.html")


@app.get("/receive")
async def receive_page():
    return FileResponse(STATIC_DIR / "receive.html")


@app.get("/sw.js")
async def service_worker():
    # Must be served from the root path so its scope covers the whole site.
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json"
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.post("/api/ring")
async def api_ring(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = str(body.get("message") or "Someone is at the door!")[:200]
    payload = {
        "type": "ring",
        "message": message,
        "at": time.time(),
        "from": request.client.host if request.client else "unknown",
    }

    live = await _broadcast(payload)
    pushed, ntfy_ok = await asyncio.gather(
        asyncio.to_thread(_send_web_push, payload),
        asyncio.to_thread(_send_ntfy, payload),
    )

    return JSONResponse(
        {
            "ok": True,
            "receivers": live,
            "pushed": pushed,
            "ntfy": bool(ntfy_ok),
            "total": live + pushed + (1 if ntfy_ok else 0),
        }
    )


@app.get("/api/receivers")
async def api_receivers():
    async with _lock:
        live = len(_listeners)
    return {
        "receivers": live,
        "subscriptions": len(_load_subs()),
        "pushEnabled": _push_ready(),
        "ntfyEnabled": bool(NTFY_TOPIC),
    }


@app.get("/api/vapid-public-key")
async def api_vapid_public_key():
    return {"key": _vapid_public_key(), "enabled": _push_ready()}


@app.post("/api/subscribe")
async def api_subscribe(request: Request):
    sub = await request.json()
    endpoint = sub.get("endpoint")
    if not endpoint:
        return JSONResponse({"ok": False, "error": "missing endpoint"}, status_code=400)
    subs = [s for s in _load_subs() if s.get("endpoint") != endpoint]
    subs.append(sub)
    _save_subs(subs)
    print(f"[push] subscription saved ({len(subs)} total)")
    return {"ok": True, "subscriptions": len(subs)}


@app.post("/api/unsubscribe")
async def api_unsubscribe(request: Request):
    body = await request.json()
    endpoint = body.get("endpoint")
    subs = [s for s in _load_subs() if s.get("endpoint") != endpoint]
    _save_subs(subs)
    return {"ok": True, "subscriptions": len(subs)}


@app.get("/api/events")
async def api_events(request: Request):
    """Server-Sent Events stream consumed by /receive and bell_client.py."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=32)
    async with _lock:
        _listeners.add(queue)

    async def event_stream():
        try:
            yield "retry: 2000\n\n"
            yield f"event: hello\ndata: {json.dumps({'ok': True})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: ring\ndata: {json.dumps(payload)}\n\n"
        finally:
            async with _lock:
                _listeners.discard(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    cert, key = CERT_DIR / "cert.pem", CERT_DIR / "key.pem"
    use_ssl = cert.exists() and key.exists()
    scheme = "https" if use_ssl else "http"

    print(f"\n  Home Calling Bell on port {PORT} ({scheme})")
    print(f"  Receiver : {scheme}://<this-computer-ip>:{PORT}/receive")
    print(f"  Ring     : {scheme}://<this-computer-ip>:{PORT}/ring")
    print(f"  Web Push : {'enabled' if _push_ready() else 'off (run gen_vapid_keys.py)'}")
    print(f"  ntfy     : {NTFY_TOPIC or 'off (set NTFY_TOPIC)'}")
    if not use_ssl:
        print("  Note     : closed-tab Web Push needs HTTPS -- see README step 6")
    print()

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
        ssl_certfile=str(cert) if use_ssl else None,
        ssl_keyfile=str(key) if use_ssl else None,
    )
