# OFV DGII — API de Certificación "Impuestos al Día"

API que **simula el servicio de la DGII (Oficina Virtual / OFV)**: recibe una solicitud
de certificación, valida al contribuyente contra un CSV (el "core tributario" mock) y,
si está al día, **emite una credencial verificable** vía [verifiably](../../verifiably)
y la **envía por correo** como una oferta OpenID4VCI (enlace + QR).

Es la capa DGII sobre el stack verifiably — ver `dgii-demo/` y la memoria del proyecto.

## Flujo

```
POST /ofv/certificaciones   { rnc, email }
   1. Busca el RNC en contribuyentes-impuestos-al-dia.csv
   2. estadoCumplimiento == AL_DIA ?  ── no ─► 409
   3. POST verifiably /api/v1/credentials/issue  ◄─ { offer_uri, credential_id }
   4. Graph sendMail (si OFV_EMAIL_ENABLED=true) → offer_uri + QR al correo
   5. 200 { credential_id, offer_uri, qr_data_uri, correo_enviado }

POST /ofv/certificaciones/{credential_id}/revocar   → simula la morosidad (revoca)
```

## Requisitos previos

- El stack **verifiably corriendo** (escenario `waltid`) con su API habilitada:
  arranca con `VERIFIABLY_API_KEYS="ofv:<secret>"` en el `.env` del stack.
- El schema **"Certificación de Impuestos al Día"** cargado en verifiably
  (`dgii-demo/schema/impuestos-al-dia.schema.json`).
- (Para correo) un **app registration** en el tenant con permiso de aplicación
  **`Mail.Send`** + consentimiento admin + Application Access Policy al buzón emisor.

## Uso

```bash
cd dgii-demo/ofv-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # edita VERIFIABLY_API_KEY (y GRAPH_* si vas a enviar correo)

uvicorn app.main:app --reload --port 8092
```

Emitir una certificación (correo deshabilitado devuelve el QR en la respuesta):

```bash
curl -s localhost:8092/ofv/certificaciones \
  -H 'content-type: application/json' \
  -d '{"rnc":"131000001","email":"contribuyente@example.com"}' | jq
```

Docs interactivas: http://localhost:8092/docs

## Correo

`OFV_EMAIL_ENABLED=false` (por defecto) **no envía correo**: la respuesta incluye el
`offer_uri` y `qr_data_uri` para inspección/QR manual — útil hasta tener el app
registration listo. Pon `true` y completa `GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET/SENDER`
para enviar vía Microsoft Graph (app-only). El cliente MSAL sigue el mismo patrón que
`llm-triage/app/ingestion/outlook.py`.

## Tests

```bash
pytest -q     # mockea verifiably con respx; no requiere el stack
```
