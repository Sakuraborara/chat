#!/usr/bin/env bash
set -euo pipefail

CERT_FILE=${1:-cert.pem}
KEY_FILE=${2:-key.pem}

openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout "$KEY_FILE" -out "$CERT_FILE" \
  -subj "/C=CN/ST=Local/L=Local/O=LocalChat/OU=IT/CN=localhost"

echo "Generated: $CERT_FILE and $KEY_FILE"
