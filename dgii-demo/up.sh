#!/usr/bin/env bash
# up.sh — ENCIENDE TODO el demo: stack walt.id + API/portales OFV.
#
#   ./up.sh
#
# Levanta los contenedores (verifiably-go + walt.id), recarga el catálogo si hace
# falta, y arranca la OFV en :8092. NO cambia de red: si te moviste de Wi-Fi/hotspot
# usa ./switch-network.sh en su lugar.
set -uo pipefail

DEMO_DIR="/home/triageuser/CertVerificableDGII/dgii-demo"
GO_DIR="/home/triageuser/CertVerificableDGII/verifiably/verifiably-go"
OFV_DIR="$DEMO_DIR/ofv-api"
CFG_ID="ImpuestosAlDiaCredential_vc+sd-jwt"
ISSUER_META="http://localhost:7002/draft13/.well-known/openid-credential-issuer"
OFV_PID="/tmp/ofv-dgii.pid"; OFV_LOG="/tmp/ofv-dgii.log"

say(){ printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok(){ printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn(){ printf '\033[1;33m! %s\033[0m\n' "$*"; }
die(){ printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# 0) Docker disponible
docker info >/dev/null 2>&1 || die "Docker no responde. Abre Docker Desktop y reintenta."

# 1) Stack walt.id — en 2º plano.
# NOTA: el paso final de deploy.sh "Verifying OIDC login" hace curl al PUBLIC_HOST
# (p. ej. la IP del hotspot), que NO se enruta desde WSL, así que tarda ~2-3 min y
# PARECE colgado — pero es un smoke-test NO fatal. No bloqueamos en él: lanzamos el
# deploy en 2º plano y esperamos la salud real del stack.
DEPLOY_LOG="/tmp/deploy-waltid.log"
say "Levantando el stack walt.id… (progreso en $DEPLOY_LOG)"
( cd "$GO_DIR" && ./deploy.sh up waltid ) >"$DEPLOY_LOG" 2>&1 &
DEPLOY_PID=$!
disown "$DEPLOY_PID" 2>/dev/null || true

# 2) Esperar la salud real (issuer-api + verifiably-go), sin esperar el verify lento
say "Esperando a que el stack quede operativo…"
t=0
until [ "$(curl -s -o /dev/null -w '%{http_code}' "$ISSUER_META" 2>/dev/null)" = 200 ] \
   && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^verifiably-go$'; do
  if ! kill -0 "$DEPLOY_PID" 2>/dev/null; then
    grep -qiE 'error|falló|✗|no space|cannot' "$DEPLOY_LOG" 2>/dev/null && die "deploy falló — revisa $DEPLOY_LOG"
    break
  fi
  t=$((t+4)); [ $t -ge 360 ] && die "el stack no quedó listo en ${t}s (revisa $DEPLOY_LOG)"
  sleep 4
done
[ "$(curl -s -o /dev/null -w '%{http_code}' "$ISSUER_META" 2>/dev/null)" = 200 ] || die "issuer-api no respondió"
ok "stack operativo (el smoke-test OIDC de deploy.sh puede seguir corriendo en 2º plano — es normal)"
if ! curl -s "$ISSUER_META" | grep -q "$CFG_ID"; then
  warn "Recargando catálogo de walt.id (restart issuer-api)…"
  docker restart waltid-issuer-api-1 >/dev/null
  for _ in $(seq 1 40); do curl -s "$ISSUER_META" 2>/dev/null | grep -q "$CFG_ID" && break; sleep 3; done
fi
if curl -s "$ISSUER_META" | grep -q "$CFG_ID"; then ok "walt.id anuncia $CFG_ID"
else warn "walt.id NO anuncia $CFG_ID — la emisión fallará (pídele ayuda a Claude)"; fi

# 3) OFV (API + portales)
say "Iniciando la OFV (:8092)"
if curl -s -o /dev/null http://localhost:8092/health 2>/dev/null; then
  ok "La OFV ya estaba corriendo"
else
  cd "$OFV_DIR" || die "no existe $OFV_DIR"
  [ -f .env ] || { cp .env.example .env; warn "creé ofv-api/.env desde el ejemplo (correo deshabilitado)"; }
  if [ ! -d .venv ]; then
    warn "Creando venv e instalando dependencias (solo la 1ª vez)…"
    python3 -m venv .venv && . .venv/bin/activate && pip -q install -r requirements.txt || die "falló pip install"
  else
    . .venv/bin/activate
  fi
  nohup uvicorn app.main:app --host 0.0.0.0 --port 8092 --reload --log-level warning >"$OFV_LOG" 2>&1 &
  echo $! >"$OFV_PID"; disown
  for _ in $(seq 1 25); do curl -s -o /dev/null http://localhost:8092/health && break; sleep 1; done
  curl -s -o /dev/null http://localhost:8092/health && ok "OFV arriba" || die "la OFV no levantó (mira $OFV_LOG)"
fi

IP=$(grep '^VERIFIABLY_PUBLIC_HOST=' "$GO_DIR/.env" | cut -d= -f2-)
cat <<EOF

============================================================
  ✅ TODO ENCENDIDO
============================================================
  Inicio (hub):   http://localhost:8092/
  Portal DGII:    http://localhost:8092/dgii
  Portal Banco:   http://localhost:8092/verificador
  verifiably UI:  http://localhost:8080        (rol Holder / Verifier)

  IP pública:     ${IP:-<sin definir>}
  Desde el móvil: http://${IP:-<IP>}:8092/

  ¿Cambiaste de red?   ./switch-network.sh
  Apagar todo:         ./down.sh
============================================================
EOF
