"""Generate the VAPID keypair used for Web Push.

Run once:  python gen_vapid_keys.py

Creates:
  vapid_private.pem  -- kept on the server, used to sign pushes
  vapid_public.txt   -- base64url public key handed to the browser
"""

from __future__ import annotations

import base64
from pathlib import Path

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    raise SystemExit(
        "Missing dependency. Run:  pip install -r requirements.txt\n"
        "(this needs the 'cryptography' package, installed with pywebpush)"
    )

BASE = Path(__file__).resolve().parent
PRIV = BASE / "vapid_private.pem"
PUB = BASE / "vapid_public.txt"

if PRIV.exists():
    answer = input(f"{PRIV.name} already exists. Overwrite? [y/N] ").strip().lower()
    if answer != "y":
        raise SystemExit("Kept existing keys.")

key = ec.generate_private_key(ec.SECP256R1())

PRIV.write_bytes(
    key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)

raw_public = key.public_key().public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)
public_b64 = base64.urlsafe_b64encode(raw_public).decode("ascii").rstrip("=")
PUB.write_text(public_b64 + "\n")

print(f"Wrote {PRIV.name} and {PUB.name}")
print("Public key:", public_b64)
print("\nNow restart the server. Delete subscriptions.json if it exists,")
print("because old subscriptions were tied to the previous key.")
