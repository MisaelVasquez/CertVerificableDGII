#!/usr/bin/env bash
# down.sh — APAGA TODO: API/portales OFV + stack walt.id.
#
#   ./down.sh
set -uo pipefail

GO_DIR="/home/triageuser/CertVerificableDGII/verifiably/verifiably-go"
OFV_PID="/tmp/ofv-dgii.pid"

say(){ printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok(){ printf '\033[1;32m✓ %s\033[0m\n' "$*"; }

# 1) OFV (:8092)
say "Deteniendo la OFV (:8092)"
stopped=0
if [ -f "$OFV_PID" ]; then
  kill "$(cat "$OFV_PID")" 2>/dev/null && stopped=1
  rm -f "$OFV_PID"
fi
# respaldo: matar cualquier uvicorn de :8092 por su línea de comando
for p in $(pgrep -f 'uvicorn app.main' 2>/dev/null); do
  if tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q 'port 8092'; then
    kill "$p" 2>/dev/null && stopped=1
  fi
done
[ "$stopped" = 1 ] && ok "OFV detenida" || ok "OFV no estaba corriendo"

# 2) Stack walt.id
say "Bajando el stack walt.id (deploy.sh down waltid)"
( cd "$GO_DIR" && ./deploy.sh down waltid ) && ok "Stack walt.id detenido" \
  || printf '\033[1;33m! revisa: %s/deploy.sh down waltid\033[0m\n' "$GO_DIR"

printf '\n\033[1;32m✓ Todo apagado.\033[0m\n'
