"""API OFV — simula el servicio de la DGII que emite la "Certificación de Impuestos al Día".

Flujo (POST /ofv/certificaciones):
  1. Valida el RNC contra el CSV (estadoCumplimiento == AL_DIA).
  2. Emite la credencial verificable vía verifiably (oferta OpenID4VCI).
  3. Envía el offer_uri + QR por correo (Graph) si OFV_EMAIL_ENABLED=true.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.contribuyentes import (
    Contribuyentes,
    ContribuyenteNoAlDia,
    ContribuyenteNoEncontrado,
)
from app.audit import AuditLog
from app.email_graph import EmailError, EmailSender
from app.models import (
    CertificacionRequest,
    CertificacionResponse,
    ReinstalacionResponse,
    RevocacionResponse,
)
from app.qr import qr_data_uri, qr_png_bytes
from app.recipients import RecipientStore
from app.verifiably import VerifiablyClient, VerifiablyError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ofv")

app = FastAPI(
    title="OFV DGII — Certificación de Impuestos al Día",
    description="Servicio simulado de la DGII que emite certificaciones como credenciales verificables.",
    version="0.1.0",
)


def _contribuyentes(settings: Settings) -> Contribuyentes:
    if not hasattr(app.state, "contribuyentes"):
        app.state.contribuyentes = Contribuyentes(settings.contribuyentes_path)
    return app.state.contribuyentes


def _verifiably(settings: Settings) -> VerifiablyClient:
    if not hasattr(app.state, "verifiably"):
        app.state.verifiably = VerifiablyClient(
            base_url=settings.verifiably_base_url,
            api_key=settings.verifiably_api_key,
            schema_id=settings.verifiably_schema_id,
            schema_name=settings.verifiably_schema_name,
            issuer_dpg=settings.verifiably_issuer_dpg,
        )
    return app.state.verifiably


def _email(settings: Settings) -> EmailSender:
    if not hasattr(app.state, "email"):
        app.state.email = EmailSender(
            enabled=settings.ofv_email_enabled,
            tenant_id=settings.graph_tenant_id,
            client_id=settings.graph_client_id,
            client_secret=settings.graph_client_secret,
            sender=settings.graph_sender,
            emitter_display=settings.ofv_emitter_display,
        )
    return app.state.email


def _recipients(settings: Settings) -> RecipientStore:
    if not hasattr(app.state, "recipients"):
        app.state.recipients = RecipientStore(settings.recipients_path)
    return app.state.recipients


def _audit(settings: Settings) -> AuditLog:
    if not hasattr(app.state, "audit"):
        app.state.audit = AuditLog(settings.audit_path)
    return app.state.audit


def _razon_social(settings: Settings, rnc: str | None) -> str:
    """Nombre del contribuyente por RNC (para las notificaciones), o cadena vacía."""
    if not rnc:
        return ""
    try:
        return _contribuyentes(settings).buscar(rnc).get("razonSocial") or ""
    except ContribuyenteNoEncontrado:
        return ""


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_UI_HTML = _STATIC_DIR / "index.html"
_HUB_HTML = _STATIC_DIR / "hub.html"

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _serve(path: Path) -> HTMLResponse:
    if not path.exists():
        return HTMLResponse("<h1>UI no encontrada</h1>", status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
async def hub() -> HTMLResponse:
    """Página de inicio (hub): enlaza el emisor DGII y el verificador (banco)."""
    return _serve(_HUB_HTML)


@app.get("/dgii", response_class=HTMLResponse)
async def ui() -> HTMLResponse:
    """Portal Oficina Virtual DGII — demo (emisor)."""
    return _serve(_UI_HTML)


@app.get("/ofv/contribuyentes/{rnc}")
async def consultar_contribuyente(rnc: str) -> dict[str, object]:
    """Consulta el estado de cumplimiento de un RNC contra el CSV (sin emitir)."""
    settings = get_settings()
    try:
        row = _contribuyentes(settings).buscar(rnc)
    except ContribuyenteNoEncontrado:
        raise HTTPException(status_code=404, detail=f"RNC no encontrado: {rnc}")
    estado = (row.get("estadoCumplimiento") or "").strip().upper()
    return {
        "rnc": row.get("rnc"),
        "razon_social": row.get("razonSocial"),
        "nombre_comercial": row.get("nombreComercial"),
        "estado_cumplimiento": estado,
        "al_dia": estado == "AL_DIA",
        "estado_rnc": row.get("estadoRNC"),
        "obligaciones_activas": row.get("obligacionesActivas"),
    }


@app.get("/ofv/certificaciones")
async def listar_certificaciones() -> dict[str, object]:
    """Lista las certificaciones DGII emitidas (con estado active/revoked)."""
    settings = get_settings()
    try:
        items = await _verifiably(settings).listar_dgii(settings.verifiably_schema_id)
    except VerifiablyError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo listar: {e}")
    return {"items": items}


_VERIFY_HTML = _STATIC_DIR / "verificador.html"


@app.get("/verificador", response_class=HTMLResponse)
async def verificador_ui() -> HTMLResponse:
    """Sirve el portal del verificador (el 'banco')."""
    if not _VERIFY_HTML.exists():
        return HTMLResponse("<h1>UI no encontrada</h1>", status_code=404)
    return HTMLResponse(_VERIFY_HTML.read_text(encoding="utf-8"))


@app.post("/verificador/solicitud")
async def verificador_solicitud(body: dict | None = None) -> dict[str, object]:
    """Crea una solicitud de presentación (QR/enlace) para la Impuestos al Día."""
    settings = get_settings()
    fields = (body or {}).get("fields") or ["estadoCumplimiento", "rnc"]
    try:
        res = await _verifiably(settings).solicitar_verificacion(
            settings.verifiably_schema_id, fields
        )
    except VerifiablyError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo crear la solicitud: {e}")
    if res.get("request_uri"):
        res["qr_data_uri"] = qr_data_uri(res["request_uri"])
    return res


@app.get("/verificador/resultado/{state}")
async def verificador_resultado(state: str) -> dict[str, object]:
    """Consulta el resultado de la presentación (+ estado vigente en el registro)."""
    settings = get_settings()
    try:
        res = await _verifiably(settings).resultado_verificacion(state)
    except VerifiablyError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo consultar el resultado: {e}")
    # Enriquecer con el estado ACTUAL del contribuyente en el registro DGII
    # (por el RNC revelado). Distingue "lo que declara la credencial" del
    # "estado vigente" — clave cuando la credencial fue revocada por mora.
    disc = res.get("disclosed")
    rnc = disc.get("rnc") if isinstance(disc, dict) else None
    if rnc:
        try:
            row = _contribuyentes(settings).buscar(rnc)
            est = (row.get("estadoCumplimiento") or "").strip().upper()
            res["estado_actual"] = est
            res["estado_actual_al_dia"] = est == "AL_DIA"
        except ContribuyenteNoEncontrado:
            pass
        # Registrar la verificación en la bitácora de la credencial (una vez por state).
        await _registrar_verificacion(settings, state, rnc, disc)
    return res


async def _registrar_verificacion(
    settings: Settings, state: str, rnc: str, disclosed: dict
) -> None:
    """Anota un evento 'verificada' en la credencial de ese RNC (dedupe por state)."""
    logged: set[str] = getattr(app.state, "verif_logged", None)
    if logged is None:
        logged = app.state.verif_logged = set()
    if state in logged:
        return
    try:
        items = await _verifiably(settings).listar_dgii(settings.verifiably_schema_id)
    except VerifiablyError:
        return
    match = next((i for i in items if i.get("rnc") == rnc and i.get("status") == "active"), None)
    match = match or next((i for i in items if i.get("rnc") == rnc), None)
    if not match:
        return
    logged.add(state)
    campos = ", ".join(k for k in disclosed.keys()) or "—"
    _audit(settings).registrar(
        match.get("credential_id"),
        "verificada",
        f"Presentada a un verificador. Campos revelados: {campos}.",
    )


@app.post("/ofv/certificaciones/{credential_id}/reinstalar", response_model=ReinstalacionResponse)
async def reinstalar_certificacion(credential_id: str) -> ReinstalacionResponse:
    """Des-revoca una certificación (vuelve a vigente) y notifica al contribuyente."""
    settings = get_settings()
    rnc = await _rnc_de_credencial(settings, credential_id)
    try:
        await _verifiably(settings).reinstalar(credential_id)
    except VerifiablyError as e:
        raise HTTPException(status_code=502, detail=f"Reinstalación falló: {e}")
    _marcar_estado(settings, rnc, "AL_DIA")

    # Notificar al mismo correo al que se envió la credencial (si se recordó).
    correo_enviado = False
    enviado_a = None
    email_sender = _email(settings)
    to = _recipients(settings).get(credential_id)
    if email_sender.enabled and to:
        try:
            await email_sender.send_reinstatement(
                to=to,
                razon_social=_razon_social(settings, rnc),
                subject=settings.ofv_reinstatement_subject,
            )
            correo_enviado = True
            enviado_a = to
        except EmailError as e:
            # La reinstalación ya ocurrió; no la perdemos por un fallo de correo.
            logger.error("reinstalación ok pero envío de notificación falló: %s", e)

    _audit(settings).registrar(
        credential_id,
        "reinstalada",
        "Certificación reinstalada (vuelve a vigente)."
        + (f" Notificada a {enviado_a}." if correo_enviado else ""),
    )

    return ReinstalacionResponse(
        estado="activa",
        credential_id=credential_id,
        enviado_a=enviado_a,
        correo_enviado=correo_enviado,
    )


@app.get("/ofv/certificaciones/{credential_id}/historial")
async def historial_certificacion(credential_id: str) -> dict[str, object]:
    """Bitácora de auditoría de una credencial (emitida/revocada/reinstalada/verificada)."""
    settings = get_settings()
    return {
        "credential_id": credential_id,
        "eventos": _audit(settings).historial(credential_id),
    }


@app.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    csv_ok = settings.contribuyentes_path.exists()
    return {
        "status": "ok" if csv_ok else "degraded",
        "csv": str(settings.contribuyentes_path),
        "csv_encontrado": csv_ok,
        "email_habilitado": settings.ofv_email_enabled,
        "verifiably": settings.verifiably_base_url,
    }


@app.post("/ofv/certificaciones", response_model=CertificacionResponse)
async def emitir_certificacion(req: CertificacionRequest) -> CertificacionResponse:
    settings = get_settings()

    # 1. Validar contra el CSV
    try:
        row = _contribuyentes(settings).validar_al_dia(req.rnc)
    except ContribuyenteNoEncontrado:
        raise HTTPException(status_code=404, detail=f"RNC no encontrado: {req.rnc}")
    except ContribuyenteNoAlDia as e:
        raise HTTPException(
            status_code=409,
            detail=f"El contribuyente no está al día (estado={e.estado}); no se emite certificación.",
        )

    razon_social = row.get("razonSocial") or ""
    subject_data = Contribuyentes.to_subject_data(row)

    # 2. Emitir la credencial verificable vía verifiably
    try:
        oferta = await _verifiably(settings).emitir(subject_data)
    except VerifiablyError as e:
        raise HTTPException(status_code=502, detail=f"Emisión en verifiably falló: {e}")

    # 3. Enviar por correo (si está habilitado)
    correo_enviado = False
    enviado_a = None
    email_sender = _email(settings)
    if email_sender.enabled:
        try:
            await email_sender.send_credential(
                to=req.email,
                razon_social=razon_social,
                offer_uri=oferta.offer_uri,
                qr_png=qr_png_bytes(oferta.offer_uri),
                subject=settings.ofv_email_subject,
                pin=oferta.pin,
            )
            correo_enviado = True
            enviado_a = req.email
            # Recordar a qué correo se envió, para poder notificar una futura revocación.
            _recipients(settings).set(oferta.credential_id, req.email)
        except EmailError as e:
            # La credencial ya se emitió; reportamos el fallo de correo sin perderla.
            logger.error("emisión ok pero envío de correo falló: %s", e)
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Credencial emitida (id={oferta.credential_id}) pero el envío de "
                    f"correo falló: {e}"
                ),
            )

    _audit(settings).registrar(
        oferta.credential_id,
        "emitida",
        f"Certificación emitida para {razon_social or req.rnc}."
        + (f" Enviada a {enviado_a}." if correo_enviado else " Correo no enviado."),
    )

    return CertificacionResponse(
        estado="emitida",
        rnc=req.rnc,
        razon_social=razon_social,
        credential_id=oferta.credential_id,
        enviado_a=enviado_a,
        offer_uri=oferta.offer_uri,
        qr_data_uri=qr_data_uri(oferta.offer_uri),
        pin=oferta.pin,
        correo_enviado=correo_enviado,
    )


async def _rnc_de_credencial(settings: Settings, credential_id: str) -> str | None:
    """Devuelve el RNC del contribuyente de una credencial emitida."""
    try:
        for it in await _verifiably(settings).listar_dgii(settings.verifiably_schema_id):
            if it.get("credential_id") == credential_id:
                return it.get("rnc")
    except VerifiablyError:
        return None
    return None


def _marcar_estado(settings: Settings, rnc: str | None, estado: str) -> None:
    """Best-effort: refleja el estado en el registro (CSV) para el demo."""
    if not rnc:
        return
    try:
        _contribuyentes(settings).set_estado(rnc, estado)
    except Exception as e:  # noqa: BLE001 - no debe tumbar la revocación
        logger.warning("no se pudo actualizar el registro CSV (%s -> %s): %s", rnc, estado, e)


@app.post("/ofv/certificaciones/{credential_id}/revocar", response_model=RevocacionResponse)
async def revocar_certificacion(credential_id: str) -> RevocacionResponse:
    """Simula la caída en morosidad: revoca la credencial y marca EN_MORA en el registro."""
    settings = get_settings()
    rnc = await _rnc_de_credencial(settings, credential_id)
    try:
        await _verifiably(settings).revocar(credential_id)
    except VerifiablyError as e:
        raise HTTPException(status_code=502, detail=f"Revocación falló: {e}")
    _marcar_estado(settings, rnc, "EN_MORA")

    # Notificar al mismo correo al que se envió la credencial (si se recordó).
    motivo = "Caída en morosidad / incumplimiento de obligaciones fiscales"
    correo_enviado = False
    enviado_a = None
    email_sender = _email(settings)
    to = _recipients(settings).get(credential_id)
    if email_sender.enabled and to:
        try:
            await email_sender.send_revocation(
                to=to,
                razon_social=_razon_social(settings, rnc),
                subject=settings.ofv_revocation_subject,
                motivo=motivo,
            )
            correo_enviado = True
            enviado_a = to
        except EmailError as e:
            # La credencial ya se revocó; no perdemos la revocación por un fallo de correo.
            logger.error("revocación ok pero envío de notificación falló: %s", e)

    _audit(settings).registrar(
        credential_id,
        "revocada",
        f"Revocada ({motivo})."
        + (f" Notificada a {enviado_a}." if correo_enviado else ""),
    )

    return RevocacionResponse(
        estado="revocada",
        credential_id=credential_id,
        enviado_a=enviado_a,
        correo_enviado=correo_enviado,
    )


@app.exception_handler(FileNotFoundError)
async def _fnf(_req, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"estado": "error", "detalle": str(exc)})
