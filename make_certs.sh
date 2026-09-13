#!/usr/bin/env bash
# Creates a self-signed HTTPS certificate for your LAN IP.
# Background Web Push only works in a secure context (HTTPS or localhost).
#
# Usage:  ./make_certs.sh 192.168.0.105

set -euo pipefail

IP="${1:-}"
if [ -z "$IP" ]; then
  echo "Usage: ./make_certs.sh <your-lan-ip>   e.g. ./make_certs.sh 192.168.0.105"
  exit 1
fi

mkdir -p certs

openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout certs/key.pem -out certs/cert.pem \
  -subj "/CN=$IP" \
  -addext "subjectAltName=IP:$IP,DNS:localhost,IP:127.0.0.1"

echo
echo "Created certs/cert.pem and certs/key.pem for $IP"
echo "Restart the server; it will now serve https://$IP:5000"
echo
echo "Your browser will warn about the self-signed certificate."
echo "Chrome/Android blocks service workers on untrusted certs, so for"
echo "reliable background push install mkcert instead (see README step 6)."
