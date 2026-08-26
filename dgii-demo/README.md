# DGII · Certificación de Impuestos al Día — artefactos del demo

Capa DGII sobre la plataforma **verifiably** (escenario `inji`). Flujo estrella: **A**
(ciudadano-iniciado, SD-JWT vía Inji Certify Auth-Code + eSignet, wallet en navegador).

## ⚠️ Datos sintéticos

Todo en `data/` es **fabricado para pruebas**. Los RNC/cédulas usan bloques
deliberadamente ficticios (jurídica `1310000XX`, física `402990000XX`) para **no
parecerse a contribuyentes reales**; los nombres de empresas y personas son
inventados. No validados contra la DGII. No usar como datos reales.

## Archivos

- `data/contribuyentes-impuestos-al-dia.csv` — 18 contribuyentes sintéticos
  (14 `AL_DIA`, 4 `EN_MORA` → para el demo de revocación). Encabezados = nombres
  de campo del schema (camelCase, sensible a mayúsculas: así lo exige el bulk-issuer).
- `schema/impuestos-al-dia.schema.json` — cuerpo para `POST /api/v1/schemas`.

## Schema (creado en vivo)

- **id:** `custom-djzbpg5yivzy` · **std:** `sd_jwt_vc (IETF)` · **type:** `ImpuestosAlDiaCredential`
- **issuer:** Dirección General de Impuestos Internos (DGII) · **DPG:** Inji Certify · Auth-Code
- Recrear: `curl -s -X POST http://localhost:8080/api/v1/schemas -H "Authorization: Bearer change-me-provision-key" -H "Content-Type: application/json" --data @schema/impuestos-al-dia.schema.json`

## Campos (investigados sobre la certificación real de la DGII)

Base real: la Certificación de Cumplimiento de Obligaciones Fiscales certifica RNC/
número de registro, razón social, domicilio fiscal, estado del contribuyente,
concepto, referencia y fecha. Se añadió taxonomía DGII (tipo/categoría, régimen,
actividad económica, obligaciones).

| Campo | Req | Nota |
|---|---|---|
| `rnc` | ✔ | Nº de registro. Sensible → oculto por defecto en la presentación |
| `razonSocial` | ✔ | Nombre / razón social |
| `nombreComercial` | | Nombre comercial |
| `tipoContribuyente` | ✔ | PERSONA_FISICA \| PERSONA_JURIDICA |
| `categoriaContribuyente` | | NORMAL \| GRAN_CONTRIBUYENTE \| MIPYME |
| `regimenTributario` | | ORDINARIO \| RST |
| `actividadEconomica` | | Actividad principal |
| `estadoRNC` | ✔ | ACTIVO \| SUSPENDIDO \| DADO_DE_BAJA |
| `estadoCumplimiento` | ✔ | **AL_DIA \| EN_MORA — el claim que pide el banco** |
| `obligacionesActivas` | | Lista `;` (ISR;ITBIS;…). Sensible |
| `domicilioFiscal` | | Dirección. Sensible |
| `provincia` / `municipio` | | Ubicación |
| `concepto` | | Concepto de la certificación |
| `numeroReferencia` | | Nº de referencia del documento |
| `fechaEmision` / `fechaVencimiento` | ✔ | Vigencia 90 días |
| `individualId` | ✔ | = `rnc`; casa al holder en eSignet |

**Revelación selectiva:** el schema solo lista los campos; qué se divulga se decide
en la plantilla OID4VP del verificador (paso "banco"). Objetivo: el banco pide solo
`estadoCumplimiento` (+ `razonSocial`) sin exponer `rnc`, `domicilioFiscal` ni
`obligacionesActivas`.

## Pendiente / siguiente

- [ ] Validar que el cableado Certify + scope eSignet se aplicó (al reclamar la
      credencial en el flujo de humo). El schema quedó registrado en verifiably-go;
      falta confirmar la parte Certify/eSignet.
- [ ] Cargar el CSV como data provider de Certify (CSV o `citizens-postgres`).
- [ ] Emitir a la wallet de navegador (Inji Web) → verificar con revelación selectiva → revocar un `EN_MORA`.
