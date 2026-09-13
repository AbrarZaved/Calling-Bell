# 🔔 Home Calling Bell (FastAPI)

One page rings the bell; the people inside get a real notification + sound —
**even if the receiver page is closed.** Everything stays on your home WiFi.

## Delivery channels

One button press fans out to all of these at once:

| # | Channel | Works when page is closed? | Setup |
|---|---------|---------------------------|-------|
| 1 | Open `/receive` tab (SSE + Web Audio beep) | No | none |
| 2 | **Web Push** (service worker) | **Yes** — tab and browser closed | HTTPS + `gen_vapid_keys.py` |
| 3 | **`bell_client.py`** desktop client | **Yes** — no browser at all | run one command |
| 4 | **ntfy** phone app | **Yes** — app closed, phone locked | set `NTFY_TOPIC` |

Pick whichever fits your devices. Phone → channel 2 or 4. PC/laptop → channel 3
is the simplest and most reliable.

---

## Basic setup (2 minutes)

1. Install Python 3.9+, then:

   ```
   pip install -r requirements.txt
   ```

2. Run the server:

   ```
   python app.py
   ```

3. Find this computer's local IP (must be on your home WiFi):
   - Linux: `hostname -I`
   - Mac: `ipconfig getifaddr en0`
   - Windows: `ipconfig` (IPv4 Address)

   It'll look like `192.168.x.x`.

4. Inside the room, open `http://<that-ip>:5000/receive` and tap
   “Enable notifications + sound” once.

5. At the door, open `http://<that-ip>:5000/ring` and tap the big red button.

At this point ringing works only while the `/receive` tab is open. Add one of
the channels below to get notified with it closed.

---

## 6. Web Push — notifications with the page closed

Browsers only allow background push in a **secure context**, so you need HTTPS
(plain `http://192.168.x.x` won't do it).

**a) Generate the push keypair (once):**

```
python gen_vapid_keys.py
```

**b) Get an HTTPS certificate your phone trusts.** Recommended: [mkcert](https://github.com/FiloSottile/mkcert)

```
mkcert -install
mkcert -cert-file certs/cert.pem -key-file certs/key.pem 192.168.0.105 localhost 127.0.0.1
```

Then install mkcert's root CA on the phone (`mkcert -CAROOT` shows the folder;
copy `rootCA.pem` to the phone and install it as a trusted certificate). Android
and Chrome refuse to run service workers behind an untrusted certificate, so
this step is what makes push actually work.

Quick-and-dirty alternative (fine on a desktop, usually rejected by phones):

```
./make_certs.sh 192.168.0.105
```

**c) Restart the server** — it auto-detects `certs/` and switches to HTTPS:

```
python app.py
```

**d) On the receiver device**, open `https://<ip>:5000/receive` and tap
“Also notify when this tab is closed”. Allow notifications. Now close the tab
and press the bell — you get an OS notification.

On **iPhone/iPad** you must first add the page to the Home Screen
(Share → Add to Home Screen) and open it from there; iOS only allows Web Push
for installed web apps.

Notes:
- Subscriptions are stored in `subscriptions.json`. Delete it if you regenerate
  the VAPID keys.
- Push delivery is relayed by the browser vendor's push service, so the
  receiving device needs internet. If you want strictly LAN-only, use channel
  3 or self-hosted ntfy.

---

## 7. Desktop client — no browser needed

On any computer on the same WiFi:

```
python bell_client.py http://192.168.0.105:5000
```

It connects to the event stream and fires a **native** notification plus a beep
(`notify-send` on Linux, Notification Center on macOS, balloon tip on Windows).
It reconnects automatically. Leave it running in `tmux`, `screen`, or minimized.
This needs zero certificates and works entirely on the LAN.

---

## 8. ntfy — phone push with the app closed

Install the free **ntfy** app (Android/iOS), subscribe to a hard-to-guess topic
name, then start the server with:

```
NTFY_TOPIC=my-home-bell-7f3a2b python app.py
```

Windows PowerShell:

```
$env:NTFY_TOPIC="my-home-bell-7f3a2b"; python app.py
```

Every ring now arrives as a high-priority phone notification, app closed and
phone locked. Pick a random topic name — public ntfy.sh topics are readable by
anyone who guesses them.

To stay fully on your home network, self-host ntfy (Docker) and point at it:

```
NTFY_SERVER=http://192.168.0.105:8080 NTFY_TOPIC=bell python app.py
```

(Self-hosted ntfy still needs an internet path for instant delivery to phones
when they're off WiFi; on WiFi the app talks to your server directly.)

---

## Why this is home-network only

The server binds to your local network and is never exposed to the public
internet (no port forwarding, no tunneling). Devices not on the same WiFi can't
reach that IP at all. The only outbound traffic is the optional push relay in
channels 2 and 4.

## Files

```
app.py                      FastAPI server (run this)
gen_vapid_keys.py            one-time Web Push keypair generator
bell_client.py               desktop receiver, native notifications
make_certs.sh                quick self-signed HTTPS certs
requirements.txt             fastapi, uvicorn, pywebpush
static/index.html            landing page with both links
static/ring.html             big red RING button
static/receive.html          live receiver + background push opt-in
static/sw.js                 service worker (shows closed-tab notifications)
static/manifest.webmanifest  lets you install it as a home-screen app
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/ring` | fan out to every channel |
| GET | `/api/events` | SSE stream for tabs and the desktop client |
| GET | `/api/receivers` | live receiver count + channel status |
| GET | `/api/vapid-public-key` | public push key for the browser |
| POST | `/api/subscribe` / `/api/unsubscribe` | manage push subscriptions |

## Troubleshooting

- **“Background push needs HTTPS”** — you're on `http://`. Do step 6.
- **“Server has no VAPID keys”** — run `python gen_vapid_keys.py`, restart.
- **Push registers but nothing arrives** — check the server log for `[push]`
  lines; expired subscriptions are dropped automatically, just re-register.
- **No sound on iPhone** — tap “Enable notifications + sound” once per tab; iOS
  blocks audio until a user gesture. Check the mute switch too.
- **Phone can't load the page** — same WiFi (not guest network), and allow
  inbound port 5000 in your OS firewall.
- **Port already in use** — `BELL_PORT=5001 python app.py`.
