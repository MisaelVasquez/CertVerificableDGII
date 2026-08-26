#!/usr/bin/env bash
# bootstrap.sh — deja una máquina nueva lista para correr el demo DGII.
#
#   ./bootstrap.sh
#
# Este repo NO versiona el clone de verifiably (es un repo ajeno, ~116 MB).
# Lo que sí versiona es el ESTADO DGII que vive dentro de él en archivos que
# upstream tiene gitignoreados — sin ese estado, un clone limpio de verifiably
# no anuncia la credencial "Impuestos al Día" y la emisión falla.
#
# Qué hace, en orden:
#   1. clona verifiably al commit fijado
#   2. .env desde el ejemplo + los 2 ajustes que el demo necesita
#   3. copia los esquemas DGII y el catálogo walt.id ANTES del primer deploy
#      (deploy.sh sólo siembra el catálogo si el archivo no existe todavía —
#       ver seed_credential_issuer_catalog en scripts/gen-caddy.sh)
#   4. venv del OFV + .env desde el ejemplo
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFIABLY_REPO="https://github.com/centre-for-dpi/verifiably.git"
# Commit validado con este demo (2026-08-25). Cambiarlo exige re-probar el ciclo.
VERIFIABLY_COMMIT="b571e62"
GO_DIR="$ROOT/verifiably/verifiably-go"
STATE="$ROOT/verifiably-state"

say(){ printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok(){ printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn(){ printf '\033[1;33m! %s\033[0m\n' "$*"; }
die(){ printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "falta git"
command -v python3 >/dev/null || die "falta python3"
docker info >/dev/null 2>&1 || warn "Docker no responde — lo necesitarás para levantar el stack (abre Docker Desktop)"

# --- 1) clone de verifiably ---------------------------------------------------
if [ -d "$ROOT/verifiably/.git" ]; then
  ok "verifiably ya está clonado (no lo toco)"
else
  say "Clonando verifiably en $VERIFIABLY_COMMIT"
  git clone "$VERIFIABLY_REPO" "$ROOT/verifiably" || die "falló el clone"
  ( cd "$ROOT/verifiably" && git checkout -q "$VERIFIABLY_COMMIT" ) || die "no pude fijar el commit"
  ok "verifiably @ $VERIFIABLY_COMMIT"
fi

# --- 2) .env del stack --------------------------------------------------------
say "Configurando verifiably-go/.env"
if [ -f "$GO_DIR/.env" ]; then
  ok ".env ya existe (no lo sobrescribo)"
else
  cp "$GO_DIR/.env.example" "$GO_DIR/.env" || die "no pude crear .env"
  # Los 2 únicos ajustes no-secretos que el demo necesita sobre el ejemplo.
  # El resto de secretos los autogenera deploy.sh en el primer up.
  # holder es imprescindible: sin él no aparece el rol Holder en la UI.
  sed -i -E 's|^#?\s*VERIFIABLY_ROLES=.*|VERIFIABLY_ROLES=issuer,verifier,holder,schemas|' "$GO_DIR/.env"
  grep -q '^VERIFIABLY_ROLES=' "$GO_DIR/.env" || echo 'VERIFIABLY_ROLES=issuer,verifier,holder,schemas' >> "$GO_DIR/.env"
  ok ".env creado (VERIFIABLY_PUBLIC_HOST se fija en el paso 5)"
fi

# --- 3) estado DGII dentro de verifiably -------------------------------------
say "Instalando el estado DGII (esquemas + catálogo walt.id)"
mkdir -p "$GO_DIR/config" "$GO_DIR/deploy/k8s/config/issuer"
cp "$STATE/config/custom-schemas.user.json" "$GO_DIR/config/" || die "faltan los esquemas"
ok "4 esquemas DGII instalados (el pineado es custom-dk017rvq43zd)"

CATALOG="$GO_DIR/deploy/k8s/config/issuer/credential-issuer-metadata.conf"
if [ -f "$CATALOG" ]; then
  warn "el catálogo ya existía — lo dejo como está"
else
  cp "$STATE/catalog/credential-issuer-metadata.conf" "$CATALOG" || die "falta el catálogo"
  ok "catálogo walt.id instalado con la entrada ImpuestosAlDiaCredential_vc+sd-jwt"
fi

# Parche opcional: ajustes de config del escenario inji (ruta abandonada) y
# dos .conf que deploy.sh re-renderiza solo. Casi nunca hace falta.
if [ "${APPLY_LOCAL_PATCH:-0}" = "1" ]; then
  ( cd "$ROOT/verifiably" && git apply "$STATE/local-config.patch" ) \
    && ok "local-config.patch aplicado" || warn "no se pudo aplicar local-config.patch"
fi

# --- 4) OFV -------------------------------------------------------------------
say "Preparando la OFV (FastAPI)"
OFV="$ROOT/dgii-demo/ofv-api"
[ -d "$OFV/.venv" ] || python3 -m venv "$OFV/.venv" || die "no pude crear el venv"
# shellcheck disable=SC1091
. "$OFV/.venv/bin/activate" && pip -q install -r "$OFV/requirements.txt" || die "falló pip install"
ok "venv listo"
if [ -f "$OFV/.env" ]; then
  ok "ofv-api/.env ya existe"
else
  cp "$OFV/.env.example" "$OFV/.env"
  warn "creé ofv-api/.env desde el ejemplo — SIN secretos"
fi

cat <<EOF

============================================================
  ✅ BOOTSTRAP LISTO
============================================================
  Falta lo que NO puede venir en el repo:

  1) ofv-api/.env  ->  rellena los secretos:
       VERIFIABLY_API_KEY   (por defecto del stack: change-me-provision-key)
       VERIFIABLY_SCHEMA_ID=custom-dk017rvq43zd
       GRAPH_* + OFV_EMAIL_ENABLED=true  (sólo si quieres envío de correo;
       requiere su propio app registration con Mail.Send + consentimiento admin)

  2) Fija la red y levanta todo:
       cd dgii-demo && ./switch-network.sh

     Ese script detecta la IP, la escribe en .env, despliega, y NORMALIZA el
     vct del catálogo a la IP nueva. Es imprescindible: el vct viene fijado a
     la IP de la máquina anterior y si no coincide, la presentación falla con
     "your wallet has no credential matching this request".

  3) Portales:  http://localhost:8092/  (hub, DGII, verificador)
     verifiably UI: http://localhost:8080  (Holder: holder/holder)

  Runbook completo: dgii-demo/DEMO-RUNBOOK.md
============================================================
EOF
