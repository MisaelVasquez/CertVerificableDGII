# detect-ip.sh — detección de la IP LAN, portable entre WSL, Git Bash y Linux.
#
# Se hace `source` desde switch-network.sh y set-network.sh. No ejecutar suelto.
#
# Por qué existe: el demo publica el issuer y el verifier en una IP concreta y
# esa IP se hornea en el `vct` del catálogo walt.id. Cada vez que cambia la red
# —o la máquina— hay que redetectarla. Antes esto era `ipconfig.exe` a secas, o
# sea WSL-sobre-Windows y nada más.
#
# Orden de intento:
#   1. ipconfig.exe  -> funciona IGUAL desde WSL y desde Git Bash (es el binario
#      nativo de Windows en ambos), así que un solo camino cubre los dos.
#      Prioriza el adaptador del Mobile Hotspot (192.168.137.x) sobre el Wi-Fi
#      normal, porque cuando el hotspot está activo es la IP que ve el móvil.
#   2. ip route get  -> Linux nativo. Pregunta por la ruta hacia un destino
#      público y toma el `src`, que es la IP de la interfaz por defecto. Elegido
#      sobre `hostname -I` a propósito: ignora docker0, veth y demás interfaces
#      virtuales, que son precisamente las que ensucian la respuesta.
#
# Si nada funciona, el llamador debe pedir la IP a mano. Todos los scripts
# aceptan `<IP>` como primer argumento — esa es la vía de escape universal.

detect_lan_ip() {
  local ip=""

  # --- Windows (WSL o Git Bash) ---
  if command -v ipconfig.exe >/dev/null 2>&1; then
    local all
    all="$(ipconfig.exe 2>/dev/null | tr -d '\r')"
    # (a) Mobile Hotspot de Windows
    ip="$(printf '%s\n' "$all" | awk '/IPv4 Address/{n=split($0,a,":");gsub(/ /,"",a[n]); if(a[n] ~ /^192\.168\.137\./){print a[n]; exit}}')"
    # (b) adaptador Wi-Fi normal
    if [ -z "$ip" ]; then
      ip="$(printf '%s\n' "$all" | awk '
        /[Ww]ireless LAN adapter Wi-Fi/ {inwifi=1; next}
        /^[A-Za-z].*adapter/            {inwifi=0}
        inwifi && /IPv4 Address/ { n=split($0,a,":"); gsub(/ /,"",a[n]); print a[n]; exit }')"
    fi
    # (c) cualquier IPv4 privada, por si el adaptador se llama distinto
    if [ -z "$ip" ]; then
      ip="$(printf '%s\n' "$all" | awk '/IPv4 Address/{n=split($0,a,":");gsub(/ /,"",a[n]); if(a[n] ~ /^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)/){print a[n]; exit}}')"
    fi
  fi

  # --- Linux nativo ---
  if [ -z "$ip" ] && command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  fi

  printf '%s' "$ip"
}

# Vuelca las candidatas cuando la detección falla, para que el usuario elija.
show_ip_candidates() {
  if command -v ipconfig.exe >/dev/null 2>&1; then
    ipconfig.exe 2>/dev/null | tr -d '\r' | grep -iE "adapter|IPv4" >&2
  elif command -v ip >/dev/null 2>&1; then
    ip -4 -o addr show scope global 2>/dev/null | awk '{print $2, $4}' >&2
  else
    printf '  (sin ipconfig.exe ni ip: no puedo listar interfaces)\n' >&2
  fi
}
