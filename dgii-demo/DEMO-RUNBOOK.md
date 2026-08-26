# Demo DGII — Certificación de Impuestos al Día (runbook)

Guía para correr, de punta a punta, la demo de credencial verificable de la DGII sobre
el stack **verifiably + walt.id**. Cubre las 4 acciones: **emitir → tener → verificar → revocar**,
con un **portal web** (estilo Oficina Virtual DGII) y **envío por correo**.

## Arquitectura

```
  [ Portal web :8092/ ]  Oficina Virtual DGII (demo)
     · Solicitar certificación (contribuyente)
     · Panel del operador (listar / revocar / reinstalar)
        │  POST /ofv/certificaciones {rnc, email}
        ▼
  [API OFV  :8092]  ── valida RNC contra CSV (estadoCumplimiento == AL_DIA)
        │  al día ✓
        ├─────────────► [ Microsoft Graph ]  envía la credencial (QR + enlace) por correo
        ▼
  [verifiably :8080]  POST /api/v1/credentials/issue
        │
        ▼
  [walt.id issuer :7002]  emite SD-JWT VC → oferta OpenID4VCI (offer_uri)
        │
        ▼
  Holder (billetera)  ──presenta──►  [ Portal Banco :8092/verificador ]
                                       "Banco de las Antillas" (demo, relying party)
                                       veredicto ✓/✕ + revelación selectiva
```

- **Portal + OFV** = `dgii-demo/ofv-api/` (FastAPI). Simula la Oficina Virtual de la DGII.
  La UI (`static/index.html`, servida en `/`) llama a la propia API por `fetch` (mismo origen).
  El mismo servicio expone el **portal del verificador** ("banco") en `/verificador`
  (`static/verificador.html`) — actúa como *relying party*.
- **CSV** = `dgii-demo/data/contribuyentes-impuestos-al-dia.csv` (14 AL_DIA + 4 EN_MORA).
- **Schema** en verifiably: `custom-dk017rvq43zd`, tipo `ImpuestosAlDiaCredential`, formato `vc+sd-jwt`.

---

## Arranque rápido

```bash
cd ~/CertVerificableDGII/dgii-demo
./up.sh      # enciende TODO: stack walt.id + OFV (:8092). Imprime las URLs.
./down.sh    # apaga TODO: OFV + stack walt.id.
```

`up.sh` levanta los contenedores, recarga el catálogo de walt.id si hace falta y arranca la OFV.
Si **cambiaste de red** (Wi-Fi/hotspot), usa `./switch-network.sh` en vez de `up.sh`.
Los pasos manuales de abajo detallan cada parte por si necesitas depurar.

---

## 0. Requisitos

- Docker Desktop encendido (integración WSL). ~12 GB RAM libres.
- El stack verifiably clonado en `../verifiably`.

---

## 1. Levantar el stack walt.id

```bash
cd ~/CertVerificableDGII/verifiably/verifiably-go
./deploy.sh up waltid              # verifiably-go + 8 contenedores walt.id
```

Verifica salud:
```bash
docker ps --format '{{.Names}}\t{{.Status}}'         # verifiably-go debe estar (healthy)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer change-me-provision-key" \
  http://localhost:8080/api/v1/catalog                # 200
```

> **Gotcha de catálogo:** tras un `up waltid` fresco, walt.id issuer-api puede no anunciar
> el config de "Impuestos al Día". Si la emisión falla con *"Invalid Credential Configuration Id"*,
> reinicia una vez: `docker restart waltid-issuer-api-1` y espera a que responda
> `http://localhost:7002/draft13/.well-known/openid-credential-issuer` (200).

---

## 2. Red / cambio de Wi-Fi o hotspot

El offer y el `vct` de la credencial **hornean la IP** (`VERIFIABLY_PUBLIC_HOST`). Al cambiar
de red hay que reapuntar. Usa el script (autónomo):

```bash
cd ~/CertVerificableDGII/dgii-demo
./switch-network.sh                # auto-detecta la IP (prioriza el hotspot 192.168.137.x)
# o fuérzala:  ./switch-network.sh 192.168.137.1
```

Hace: actualiza `.env` → `deploy.sh up waltid` → **normaliza el host del `vct` en el catálogo**
→ reinicia issuer-api → asegura la OFV → emite una oferta fresca → genera `claim.html` (QR).

Comando para ver la IP actual del host (Windows Mobile Hotspot = `192.168.137.1`):
```bash
ipconfig.exe | tr -d '\r' | awk '/IPv4/{if($NF~/^192\.168\.137\./){print $NF;exit}}'
```

---

## 3. Levantar la OFV

```bash
cd ~/CertVerificableDGII/dgii-demo/ofv-api
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt   # 1ª vez
nohup uvicorn app.main:app --port 8092 --log-level warning >/tmp/ofv.log 2>&1 & disown
curl -s localhost:8092/health | python3 -m json.tool
```

> No uses `pkill -f "uvicorn...8092"` (el patrón se auto-coincide). Mata por PID.

### Correo (opcional)

Para enviar la credencial por correo, en `ofv-api/.env`:

```ini
OFV_EMAIL_ENABLED=true
GRAPH_TENANT_ID=<Directory (tenant) ID del app registration>
GRAPH_CLIENT_ID=<Application (client) ID — NO el "Secret ID">
GRAPH_CLIENT_SECRET=<Value del secreto>
GRAPH_SENDER=<UPN de un buzón con Exchange Online del tenant>
```

Requiere un app registration con permiso de **aplicación `Mail.Send`** + **admin consent**.
Con `OFV_EMAIL_ENABLED=false` (por defecto) no envía: la respuesta/portal muestran el QR/enlace igual.
Valida el token con: `python -c "..."` (ver `app/email_graph.py`). Nota: tenants **trial** de M365
suelen **bloquear el correo saliente externo** (Gmail, etc.) — usa un destinatario del mismo tenant.

---

## 4. Los portales web (UI) — la forma recomendada

Abre el **inicio (hub)** en **`http://localhost:8092/`** (o `http://<IP>:8092/`): tiene el diagrama
del flujo y enlaza los dos portales del demo — **Oficina Virtual DGII** (emisor, `/dgii`) y
**Banco de las Antillas** (verificador, `/verificador`).

El **portal DGII** (`/dgii`) está estilizado como Oficina Virtual (etiquetado como demo), con dos pestañas:

- **Solicitar certificación** (contribuyente): RNC + correo → *Consultar estado* (píldora al día/mora)
  → *Solicitar certificación*. Muestra la tarjeta con **estado, QR, enlace de oferta y aviso de correo**.
- **Panel del operador**: tabla de certificaciones emitidas con **Revocar / Reinstalar** en vivo.

Todo lo de abajo (curl) es la **alternativa por API** — el portal hace lo mismo.

---

## 5. Emitir (acción 1)

```bash
curl -s localhost:8092/ofv/certificaciones -H 'content-type: application/json' \
  -d '{"rnc":"131000001","email":"contribuyente@example.com"}' | python3 -m json.tool
```
- Al día → `estado: emitida` + `offer_uri` (OpenID4VCI) + `credential_id` (guárdalo para revocar).
- No al día (ej. `131000006`, EN_MORA) → **409** "no se emite".
- RNC inexistente → **404**.

Los offers **caducan**: emite uno fresco justo antes de reclamar.

Otros endpoints que usa el portal:
```bash
curl -s localhost:8092/ofv/contribuyentes/131000001      # consultar estado (sin emitir)
curl -s localhost:8092/ofv/certificaciones               # listar emitidas (active/revoked)
curl -s -X POST localhost:8092/ofv/certificaciones/<id>/reinstalar   # des-revocar
```

---

## 6. Tener / reclamar (acción 2) — rol Holder

> **Receta anti-CSRF (obligatoria):** ventana **incógnito**, escribe la URL con la **IP exacta**
> `http://<IP>:8080` — **nunca** `localhost` ni `127.0.0.1` — y haz el login **de un tirón**
> (sin "atrás" ni refrescar). El callback OIDC vuelve siempre a esa IP; si mezclas orígenes,
> la cookie de sesión no viaja y sale *"Auth state mismatch (CSRF?)"*.

1. `http://<IP>:8080` → rol **Holder** → login **`holder` / `holder`**.
2. **Holder → DPG** → elige **Walt Community Stack** (acepta offer URIs crudos; los DPG tipo
   Inji Web/eSignet exigen vincular cuenta y **no** sirven aquí).
3. **Holder → Wallet** → pega el `offer_uri` → **Process offer** → **Accept**.
4. La credencial queda en *held credentials*.

---

## 7. Verificar (acción 3) — "el banco"

### Opción A — Portal del verificador (recomendada)

Abre **`http://localhost:8092/verificador`** (portal "Banco de las Antillas", demo):

0. **Seleccione los datos a solicitar** (selector de revelación selectiva): marque solo lo necesario
   — `estadoCumplimiento` + `rnc` por defecto; puede añadir razón social, domicilio, etc. Mientras
   menos pida, más privacidad para el ciudadano.
1. **Solicitar presentación** → aparece un **QR + enlace OpenID4VP**.
2. El cliente **presenta** su credencial (ver abajo cómo, desde el Holder de verifiably).
3. El portal muestra el **veredicto automáticamente**: ✓ válida / ✕ no válida, con el método
   (revelación selectiva), emisor y los **datos revelados** (`estadoCumplimiento`, `rnc`).
   Detecta también **revocación** (muestra "a presented credential has been revoked").

Para presentar desde el Holder de verifiably: en su ventana → **Holder → Present** → pega el
**enlace de la solicitud** que muestra el portal del banco → **Confirm → Submit**.

### Opción B — Rol Verifier de verifiably (manual, para inspeccionar políticas)

Holder y Verifier **no conviven** en una sola ventana (cambiar de rol re-pide login). Usa una
**segunda ventana incógnito** en paralelo.

1. Nueva ventana incógnito → `http://<IP>:8080` → rol **Verifier** → login **`admin` / `admin`**.
2. **Verifier → DPG** → **walt.id** (misma familia que el holder).
3. **Verifier → Verify**:
   - Schema: **Certificación de Impuestos al Día**.
   - Disclosure: **selective** → marca solo **`estadoCumplimiento`** (+ `rnc` si quieres).
   - Políticas: deja las por defecto. **`credential-status` SÍ funciona** aquí (usamos
     *Token Status List* IETF, que walt.id 0.18.2 sabe leer).
   - **Generate request** → copia el **Request URI**.
4. En la ventana **Holder → Present**: selecciona la credencial, pega el Request URI →
   **Confirm** → **Submit**.
5. En el **Verifier → Fetch response** → ✅ **Credential valid**, revelando **solo**
   `estadoCumplimiento=AL_DIA` (+ rnc). Nada de razón social / domicilio / obligaciones.

> Verás `trust: not trusted` — el emisor es un `did:jwk` autogenerado, no está en el trust
> registry. El veredicto sigue siendo válido; es pulido pendiente (usar `did:web:dgii.gob.do`).

---

## 8. Revocar (acción 4) — simular morosidad

Desde el **Panel del operador** del portal: botón **Revocar** en la fila de la credencial.
O por API:
```bash
curl -s -X POST localhost:8092/ofv/certificaciones/<credential_id>/revocar
```

> **Coherencia del registro:** al revocar, la OFV también marca al contribuyente como **EN_MORA**
> en el CSV (reinstalar lo vuelve a AL_DIA) — sin tocar la credencial del wallet (es inmutable).
> Así el portal DGII muestra EN_MORA en "Consultar estado" y una nueva solicitud devuelve 409. En el
> **verificador**, una credencial revocada ya no muestra el `AL_DIA` en verde: lo atenúa ("revocada")
> y añade **"Estado actual en la DGII: EN MORA"** (consultado por el RNC revelado). Resuelve la
> disonancia "no válida + AL_DIA" enseñando por qué la credencial es una foto y la revocación la invalida.
Vuelve al Verifier → **Regenera el Request** (para no usar caché) → Holder re-presenta la
**misma** credencial → **Fetch response**:

```
✕ Credential invalid — Failed: credential-status
walt.id: Status validation failed: expected 0, but got 1
"a presented credential has been revoked"
```

Des-revocar (para re-ensayar el caso "al día"):
```bash
curl -s -X POST -H "Authorization: Bearer change-me-provision-key" \
  http://localhost:8080/api/v1/credentials/<credential_id>/reinstate
```

---

## Referencia rápida

| Cosa | Valor |
|---|---|
| **Inicio (hub)** | `http://localhost:8092/` — enlaza los dos portales + diagrama del flujo |
| **Portal DGII (emisor)** | `http://localhost:8092/dgii` |
| **Portal Banco (verificador)** | `http://localhost:8092/verificador` (con selector de datos a solicitar) |
| OFV API | `http://localhost:8092` (`/health`, `/docs`, `/ofv/...`, `/verificador/...`) |
| Correo | Microsoft Graph app-only · `GRAPH_*` en `ofv-api/.env` · `OFV_EMAIL_ENABLED` |
| verifiably UI/API | `http://<IP>:8080` · API key `change-me-provision-key` (Bearer) |
| walt.id issuer metadata | `http://<IP>:7002/draft13/.well-known/openid-credential-issuer` |
| Login Holder | `holder` / `holder` |
| Login Verifier | `admin` / `admin` (o `issuer`/`issuer`) |
| Schema id | `custom-dk017rvq43zd` (pineado en `ofv-api/.env`) |

## Troubleshooting

| Síntoma | Causa / arreglo |
|---|---|
| `Invalid Credential Configuration Id` al emitir | walt.id no recargó el catálogo → `docker restart waltid-issuer-api-1` |
| `Auth state mismatch (CSRF?)` en login | usaste localhost/cookies viejas → incógnito + IP exacta, login de un tirón |
| Present: *"no credential matching this request"* | `vct` con host viejo → `switch-network.sh` lo normaliza; luego re-emitir + re-reclamar |
| Offer no carga / caducó | emite uno fresco (paso 5) |
| El iPhone no alcanza la laptop | mismo hotspot; el firewall de Windows puede tratar la red como "Pública" |
| Token Graph `AADSTS700016` | pusiste el **Secret ID** en `GRAPH_CLIENT_ID` → usa el **Application (client) ID** del Overview |
| Correo "Not delivered" a Gmail | tenant **trial** bloquea correo saliente externo → usa un destinatario **del mismo tenant** |
| Portal sin estilos / logo viejo | recarga forzada (Ctrl/Cmd+Shift+R) para saltar la caché de `/static/` |
