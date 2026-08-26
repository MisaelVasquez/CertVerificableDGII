#!/usr/bin/env bash
# set-network.sh — re-apunta la demo Verifiably a la IP Wi-Fi actual y redespliega.
#
# Úsalo cada vez que cambies de red (casa, hotspot del teléfono, venue del bootcamp):
#
#   ./set-network.sh                  # auto-detecta la IP Wi-Fi de Windows
#   ./set-network.sh 192.168.43.100   # o fuérzala tú (si la auto-detección falla)
#
# Requiere: WSL con acceso a ipconfig.exe (Windows) y a docker (Docker Desktop).
set -uo pipefail

ENV_FILE="/home/triageuser/CertVerificableDGII/verifiably/verifiably-go/.env"
GO_DIR="/home/triageuser/CertVerificableDGII/verifiably/verifiably-go"

# --- 1) Determinar la IP -----------------------------------------------------
if [[ "${1:-}" != "" ]]; then
  IP="$1"
else
  # Extrae el IPv4 del bloque "Wireless LAN adapter Wi-Fi" de ipconfig.
  # (Ignora vEthernet/WSL y los adaptadores "Local Area Connection*".)
  IP="$(ipconfig.exe 2>/dev/null | tr -d '\r' | awk '
    /[Ww]ireless LAN adapter Wi-Fi/ {inwifi=1; next}
    /^[A-Za-z].*adapter/            {inwifi=0}
    inwifi && /IPv4 Address/ { n=split($0,a,":"); gsub(/ /,"",a[n]); print a[n]; exit }')"
fi

if ! [[ "${IP:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "✗ No pude detectar una IP Wi-Fi válida (obtuve: '${IP:-}')." >&2
  echo "  IPs candidatas en este equipo:" >&2
  ipconfig.exe 2>/dev/null | tr -d '\r' | grep -iE "adapter|IPv4" >&2
  echo "  Pásala a mano:  ./set-network.sh <IP>" >&2
  exit 1
fi

# --- 2) Actualizar .env (solo la línea real, no el comentario) ---------------
OLD="$(grep -E '^VERIFIABLY_PUBLIC_HOST=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
if [[ "$OLD" == "$IP" ]]; then
  echo "VERIFIABLY_PUBLIC_HOST ya es ${IP}. Redesplegando de todos modos para asegurar…"
else
  cp "$ENV_FILE" "${ENV_FILE}.bak"
  sed -i -E "s|^VERIFIABLY_PUBLIC_HOST=.*|VERIFIABLY_PUBLIC_HOST=${IP}|" "$ENV_FILE"
  echo "VERIFIABLY_PUBLIC_HOST: ${OLD:-<vacío>} -> ${IP}   (.env respaldado en .env.bak)"
fi

# --- 3) Redesplegar ----------------------------------------------------------
echo "▶ Redesplegando el escenario inji (un par de minutos)…"
cd "$GO_DIR" || { echo "✗ No existe $GO_DIR" >&2; exit 1; }
./deploy.sh up inji

echo
echo "✅ Listo. Desde tu móvil (misma WiFi o tu hotspot) abre:"
echo "      http://${IP}:8080"
echo "   eSignet (login holder): UIN 5500000002 / PIN 123456"
