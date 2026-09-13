"""Desktop bell receiver -- native OS notification, no browser tab needed.

Run it on any computer on the same WiFi:

    python bell_client.py http://192.168.0.105:5000

It stays connected, reconnects automatically, and fires a native notification
plus a beep every time someone presses the button.
"""

from __future__ import annotations

import json
import platform
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request

TITLE = "Home Calling Bell"
SYSTEM = platform.system()


def notify(message: str) -> None:
    try:
        if SYSTEM == "Darwin":
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{message}" with title "{TITLE}" sound name "Submarine"',
                ],
                check=False,
            )
        elif SYSTEM == "Windows":
            ps = (
                "[reflection.assembly]::loadwithpartialname('System.Windows.Forms')|Out-Null;"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;"
                "$n.BalloonTipTitle='" + TITLE + "';"
                "$n.BalloonTipText='" + message.replace("'", "") + "';"
                "$n.Visible=$true;$n.ShowBalloonTip(10000);Start-Sleep -s 10"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps]
            )
        else:  # Linux / BSD
            if shutil.which("notify-send"):
                subprocess.run(
                    ["notify-send", "-u", "critical", f"\U0001F514 {TITLE}", message],
                    check=False,
                )
    except Exception as exc:
        print(f"[notify] {exc}")


def beep() -> None:
    try:
        if SYSTEM == "Windows":
            import winsound

            for freq in (880, 660, 990):
                winsound.Beep(freq, 300)
        elif SYSTEM == "Darwin":
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Submarine.aiff"], check=False
            )
        else:
            for player, args in (
                ("paplay", ["/usr/share/sounds/freedesktop/stereo/complete.oga"]),
                ("aplay", ["/usr/share/sounds/alsa/Front_Center.wav"]),
            ):
                if shutil.which(player):
                    subprocess.run([player, *args], check=False)
                    break
            else:
                print("\a", end="", flush=True)
    except Exception:
        print("\a", end="", flush=True)


def listen(base_url: str) -> None:
    url = base_url.rstrip("/") + "/api/events"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # self-signed LAN certs are fine here
    ctx.verify_mode = ssl.CERT_NONE

    while True:
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=None, context=ctx) as stream:
                print(f"Connected to {url} -- waiting for the bell. Ctrl+C to quit.")
                event = None
                for raw in stream:
                    line = raw.decode("utf-8", "replace").rstrip("\n")
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data = line.split(":", 1)[1].strip()
                        if event == "ring":
                            try:
                                message = json.loads(data).get(
                                    "message", "Someone is at the door!"
                                )
                            except Exception:
                                message = "Someone is at the door!"
                            stamp = time.strftime("%H:%M:%S")
                            print(f"[{stamp}] RING -- {message}")
                            notify(message)
                            beep()
                    elif line == "":
                        event = None
        except KeyboardInterrupt:
            print("\nBye.")
            return
        except Exception as exc:
            print(f"[client] disconnected ({exc}); retrying in 3s")
            time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python bell_client.py http://<server-ip>:5000")
    listen(sys.argv[1])
