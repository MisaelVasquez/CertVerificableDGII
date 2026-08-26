# CertVerificableDGII

Demo end-to-end de **credencial verificable** para el caso de uso DGII (República Dominicana):
*Certificación de Impuestos al Día*.

> ⚠️ **DEMO / SIMULACIÓN.** No está afiliado ni respaldado por la Dirección General de
> Impuestos Internos. No hay integración con sistemas reales de la DGII: los datos son
> **sintéticos** (18 contribuyentes ficticios en un CSV). No usar en producción — ver
> "Estado" más abajo.

Ciclo probado: **emitir → sostener → verificar (con revelación selectiva) → revocar**,
sobre SD-JWT VC + OpenID4VCI/OpenID4VP y una IETF Token Status List real.

## Estructura

| Ruta | Qué es |
|---|---|
| `dgii-demo/ofv-api/` | La **OFV**: API FastAPI que simula el servicio de la DGII. Lee el CSV, emite vía verifiably, envía la oferta OID4VCI por correo (Graph) y sirve los portales web. |
| `dgii-demo/data/` | CSV sintético de contribuyentes (la fuente que simula el core tributario). |
| `dgii-demo/*.sh` | `up.sh` / `down.sh` (encender y apagar), `switch-network.sh` (cambiar de red). |
| `dgii-demo/DEMO-RUNBOOK.md` | Guion completo de la demostración. |
| `verifiably-state/` | El estado DGII que vive **dentro** del clone de verifiably en archivos que upstream tiene gitignoreados. Ver abajo. |
| `bootstrap.sh` | Deja una máquina nueva lista. |

## Por qué `verifiably/` no está en este repo

El demo corre sobre [`centre-for-dpi/verifiably`](https://github.com/centre-for-dpi/verifiably),
la plataforma de referencia de CDPI. Es un repo ajeno de ~116 MB: no tiene sentido
vendorearlo, `bootstrap.sh` lo clona al commit fijado (`b571e62`).

El detalle que no es obvio: **tres archivos dentro de ese clone contienen todo el estado
DGII y upstream los tiene gitignoreados**, así que un clone limpio no los trae:

- `config/custom-schemas.user.json` — los 4 esquemas, incluido el pineado `custom-dk017rvq43zd`
- `deploy/k8s/config/issuer/credential-issuer-metadata.conf` — el catálogo walt.id con la
  entrada `ImpuestosAlDiaCredential_vc+sd-jwt` y su `vct`
- `.env` — de donde sólo importan dos ajustes no-secretos

Sin ellos walt.id no anuncia la credencial y la emisión falla con
`Invalid Credential Configuration Id`. Por eso viven aquí, en `verifiably-state/`, y
`bootstrap.sh` los copia en su sitio **antes** del primer despliegue (`deploy.sh` sólo
siembra el catálogo si el archivo aún no existe).

## Puesta en marcha

```bash
git clone <este-repo> CertVerificableDGII
cd CertVerificableDGII
./bootstrap.sh                    # clona verifiably, instala el estado, crea el venv
# rellena dgii-demo/ofv-api/.env con los secretos (ver más abajo)
cd dgii-demo && ./switch-network.sh
```

Portales en `http://localhost:8092/` (hub, DGII, verificador) y la UI de verifiably en
`http://localhost:8080` (Holder: `holder/holder`).

### Lo que NO viene en el repo

Por diseño, ningún secreto está versionado. Tras el bootstrap hay que rellenar
`dgii-demo/ofv-api/.env` (plantilla en `.env.example`):

- `VERIFIABLY_API_KEY` — por defecto el stack arranca con `change-me-provision-key`
- `VERIFIABLY_SCHEMA_ID=custom-dk017rvq43zd`
- `GRAPH_*` y `OFV_EMAIL_ENABLED=true` — **sólo** si quieres envío de correo. Requiere un
  app registration propio en Entra con permiso de aplicación `Mail.Send`, consentimiento de
  administrador y un buzón emisor.

Tampoco se versionan `data/credencial-correos.json` ni `data/credencial-bitacora.json`:
son estado de ejecución y contienen direcciones de correo reales. Se regeneran solos.

## Trampa conocida: el `vct` y la IP

El `vct` del SD-JWT queda fijado en el catálogo con la IP de la máquina donde se registró
el esquema. Al mover el demo a otra red u otra máquina, el verificador recalcula el `vct`
desde la IP actual, deja de coincidir y la presentación falla con *"your wallet has no
credential matching this request"*.

`switch-network.sh` lo resuelve: detecta la IP, la escribe en `.env`, despliega y
**normaliza el `vct` del catálogo**, reiniciando `waltid-issuer-api-1` para que recargue.
Córrelo siempre tras cambiar de red o de máquina. Ojo: una credencial ya reclamada
conserva el `vct` viejo — hay que re-emitir y re-reclamar.

## Estado

Es un **demo funcional**, no un producto. El diseño (SD-JWT VC, OID4VCI/OID4VP, status
lists, revelación selectiva) es la misma pila que usa la EUDI Wallet europea y el ciclo
completo está probado. Pero llevarlo a un servicio público real exige, como mínimo: base
legal para la validez de la credencial, firma en HSM (hoy es un `did:jwk` autogenerado que
el verificador reporta como `trust: not trusted`), una lista de confianza publicada por una
autoridad, integración real con SIT/OFV en vez del CSV, particionado de las status lists
con privacidad de rebaño, TLS, y endurecimiento de credenciales (hoy hay `admin/admin`
sembrado). No es una lista de pendientes: es un programa aparte.

## Créditos

Construido sobre [verifiably](https://github.com/centre-for-dpi/verifiably) (Centre for
Digital Public Infrastructure) como material de un bootcamp de credenciales verificables.
