#!/usr/bin/env bash
# switch-network.sh — reapunta la demo (walt.id + OFV) a la red actual y deja
# lista una oferta nueva con su QR. Pensado para cuando cambies a un HOTSPOT.
#
#   ./switch-network.sh            # auto-detecta la IP Wi-Fi/hotspot de Windows
#   ./switch-network.sh 172.20.10.2   # o fuérzala tú
#
# Qué hace: .env PUBLIC_HOST -> IP nueva; ./deploy.sh up waltid; verifica que
# walt.id anuncie el config de "Impuestos al Día"; asegura la OFV; emite una
# credencial fresca; genera claim.html con el QR. NO re-registra el schema (el
# catálogo sobrevive al redeploy), así que no crea duplicados.
set -uo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DEMO_DIR/.." && pwd)"
GO_DIR="$ROOT_DIR/verifiably/verifiably-go"
OFV_DIR="$DEMO_DIR/ofv-api"
ENV_FILE="$GO_DIR/.env"
APIKEY="change-me-provision-key"
RNC="131000001"
OFFER_JSON="$DEMO_DIR/offer.json"
CLAIM_HTML="$DEMO_DIR/claim.html"
CFG_ID="ImpuestosAlDiaCredential_vc+sd-jwt"
ISSUER_META="http://localhost:7002/draft13/.well-known/openid-credential-issuer"

say()  { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1) IP -------------------------------------------------------------------
# La detección vive en lib/detect-ip.sh porque set-network.sh la necesita igual
# y porque tiene que cubrir WSL, Git Bash y Linux nativo.
# shellcheck source=lib/detect-ip.sh
. "$DEMO_DIR/lib/detect-ip.sh"

say "Detectando IP de la red actual"
if [[ "${1:-}" != "" ]]; then
  IP="$1"
else
  IP="$(detect_lan_ip)"
fi
[[ "${IP:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  warn "No detecté una IP válida. Candidatas:"
  show_ip_candidates
  die "Pásala a mano:  ./switch-network.sh <IP>"
}
ok "IP a usar: $IP"

# --- 2) .env -----------------------------------------------------------------
OLD="$(grep -E '^VERIFIABLY_PUBLIC_HOST=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
if [[ "$OLD" != "$IP" ]]; then
  cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%s)"
  sed -i -E "s|^VERIFIABLY_PUBLIC_HOST=.*|VERIFIABLY_PUBLIC_HOST=${IP}|" "$ENV_FILE"
  ok "VERIFIABLY_PUBLIC_HOST: ${OLD:-<vacío>} -> ${IP}"
else
  ok "VERIFIABLY_PUBLIC_HOST ya era ${IP}"
fi

# --- 3) redeploy walt.id -----------------------------------------------------
say "Redesplegando walt.id (un par de minutos)…"
( cd "$GO_DIR" && ./deploy.sh up waltid ) || die "deploy.sh falló"

# --- 4) esperar issuer-api y verificar el catálogo ---------------------------
say "Esperando a que walt.id issuer-api quede listo"
for _ in $(seq 1 60); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$ISSUER_META" 2>/dev/null)" == "200" ]] && break
  sleep 3
done
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$ISSUER_META" 2>/dev/null)" == "200" ]] || die "issuer-api no respondió"
ok "issuer-api arriba"

# El vct del schema custom queda HARDCODEADO con el host de cuando se registró
# (VERIFIABLY_PUBLIC_URL/credentials/<id>). Si cambió la IP, el verifier calcula
# el vct con la IP nueva y NO coincide con la credencial emitida → "no credential
# matching". Normalizamos el host del vct al IP actual y recargamos issuer-api.
CATALOG="$GO_DIR/deploy/k8s/config/issuer/credential-issuer-metadata.conf"
if grep -qE "http://[0-9.]+:8080/credentials/custom-" "$CATALOG" 2>/dev/null; then
  cp "$CATALOG" "$CATALOG.bak.$(date +%s)"
  sed -i -E "s|http://[0-9.]+:8080/credentials/custom-|http://${IP}:8080/credentials/custom-|g" "$CATALOG"
  ok "vct del catálogo normalizado a http://${IP}:8080/credentials/custom-…"
fi

# Siempre reiniciamos issuer-api tras el redeploy para recargar el catálogo
# (el auto-restart de SaveCustomSchema no dispara en este entorno) + aplicar el vct.
warn "Reiniciando issuer-api para recargar el catálogo (config + vct)…"
docker restart waltid-issuer-api-1 >/dev/null
for _ in $(seq 1 40); do
  curl -s "$ISSUER_META" 2>/dev/null | grep -q "$CFG_ID" && break
  sleep 3
done
if curl -s "$ISSUER_META" | grep -q "$CFG_ID"; then
  ok "walt.id anuncia $CFG_ID"
else
  die "walt.id no anuncia $CFG_ID — pídele ayuda a Claude (posible re-registro de schema)"
fi

# --- 5) asegurar la OFV corriendo -------------------------------------------
say "Asegurando la API OFV en :8092"
if ! curl -s -o /dev/null http://localhost:8092/health 2>/dev/null; then
  # --host 0.0.0.0: sin esto uvicorn escucha sólo en 127.0.0.1 y los portales
  # no son alcanzables desde otra máquina. Debe coincidir con up.sh.
  ( cd "$OFV_DIR" && . .venv/bin/activate && \
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8092 --log-level warning >/tmp/ofv.log 2>&1 & disown )
  for _ in $(seq 1 20); do curl -s -o /dev/null http://localhost:8092/health && break; sleep 1; done
fi
curl -s -o /dev/null http://localhost:8092/health || die "la OFV no levantó (mira /tmp/ofv.log)"
ok "OFV arriba"

# --- 6) emitir oferta fresca + QR -------------------------------------------
say "Emitiendo credencial fresca (RNC $RNC)"
curl -s http://localhost:8092/ofv/certificaciones -H 'content-type: application/json' \
  -d "{\"rnc\":\"$RNC\",\"email\":\"contribuyente@example.com\"}" > "$OFFER_JSON"
python3 -c "import json,sys; d=json.load(open('$OFFER_JSON')); sys.exit(0 if d.get('estado')=='emitida' else 1)" \
  || die "la emisión falló: $(cat "$OFFER_JSON")"
python3 "$DEMO_DIR/make-claim-page.py" "$OFFER_JSON" "$CLAIM_HTML" "http://${IP}:7002/draft13"
ok "Oferta emitida y QR generado"

# --- 7) resumen --------------------------------------------------------------
WINPATH="$(wslpath -w "$CLAIM_HTML" 2>/dev/null || echo "$CLAIM_HTML")"
cat <<EOF

============================================================
  LISTO — la demo está reapuntada a la red actual
============================================================
  IP de esta laptop:   ${IP}

  1) PRUEBA DE ALCANCE (desde Safari en el iPhone):
        http://${IP}:8080
     Debe cargar la página "Verifiably". Si no carga, el
     iPhone no está alcanzando la laptop (revisa que ambos
     estén en el MISMO hotspot y el firewall de Windows).

  2) ESCANEA EL QR para reclamar en Inji Wallet:
        abre en el navegador de la laptop:
        ${CLAIM_HTML}
        (en Windows:  ${WINPATH} )

  La oferta apunta a:  http://${IP}:7002/draft13
============================================================
EOF
