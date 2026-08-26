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

# --- 0) plataforma ------------------------------------------------------------
# El stack se despliega con deploy.sh de upstream, que usa `sed -i` con sintaxis
# GNU. El sed BSD de macOS lee el `-E` que le sigue como sufijo de backup y falla,
# así que macOS está descartado por upstream, no por nosotros: no tiene arreglo
# de este lado. Mejor fallar aquí que a mitad del despliegue.
case "$(uname -s)" in
  Darwin) die "macOS no está soportado: deploy.sh de upstream depende de GNU sed. Usa WSL2, Linux, o Git Bash en Windows." ;;
esac
if ! sed --version >/dev/null 2>&1; then
  warn "tu 'sed' no parece GNU sed — deploy.sh de upstream puede fallar al renderizar la config"
fi

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
  ok "ofv-api/.env ya existe (no lo toco)"
else
  cp "$OFV/.env.example" "$OFV/.env"
  # Pre-rellenamos los dos valores que NO son secretos, para que el demo arranque
  # sin edición manual. VERIFIABLY_API_KEY es el default público con el que
  # deploy.sh levanta el stack (VERIFIABLY_API_KEYS=provisioner:change-me-provision-key),
  # no una credencial real; VERIFIABLY_SCHEMA_ID es el id del esquema que viaja en
  # verifiably-state/. Sin ellos, la primera emisión aborta con
  # VerifiablyError("VERIFIABLY_API_KEY no configurada").
  sed -i -E 's|^VERIFIABLY_API_KEY=.*|VERIFIABLY_API_KEY=change-me-provision-key|' "$OFV/.env"
  sed -i -E 's|^VERIFIABLY_SCHEMA_ID=.*|VERIFIABLY_SCHEMA_ID=custom-dk017rvq43zd|' "$OFV/.env"
  ok "ofv-api/.env creado y pre-configurado (sin secretos: GRAPH_* queda vacío)"
fi

cat <<EOF

============================================================
  ✅ BOOTSTRAP LISTO
============================================================
  ofv-api/.env ya quedó configurado (API key + schema id). NO hace
  falta editarlo salvo que quieras envío de correo, que necesita
  rellenar GRAPH_* y poner OFV_EMAIL_ENABLED=true — requiere tu propio
  app registration en Entra con Mail.Send + consentimiento de admin.
  Sin eso el demo funciona igual: la respuesta trae el offer_uri y el QR.

  SIGUIENTE PASO — con Docker Desktop abierto:

       cd dgii-demo && ./switch-network.sh

     Detecta la IP, la escribe en .env, despliega, y NORMALIZA el vct
     del catálogo a la IP nueva. Es imprescindible: el vct viene fijado
     a la IP de la máquina anterior y si no coincide, la presentación
     falla con "your wallet has no credential matching this request".
     Si la detección de IP falla:  ./switch-network.sh <IP>

     La primera vez descarga varios GB de imágenes: 15-30 min.

     Ese script detecta la IP, la escribe en .env, despliega, y NORMALIZA el
     vct del catálogo a la IP nueva. Es imprescindible: el vct viene fijado a
     la IP de la máquina anterior y si no coincide, la presentación falla con
     "your wallet has no credential matching this request".

  3) Portales:  http://localhost:8092/  (hub, DGII, verificador)
     verifiably UI: http://localhost:8080  (Holder: holder/holder)

  Runbook completo: dgii-demo/DEMO-RUNBOOK.md
============================================================
EOF
