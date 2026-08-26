"""Envío de la credencial por correo vía Microsoft Graph (app-only / client-credentials).

Adaptado del patrón MSAL usado en ../../../llm-triage/app/ingestion/outlook.py.
Requiere un app registration con el permiso de APLICACIÓN Mail.Send (+ consentimiento
admin) y una Application Access Policy que cubra el buzón GRAPH_SENDER.

Si OFV_EMAIL_ENABLED=false, EmailSender.enabled es False y send_credential() no se llama
(el endpoint devuelve el offer_uri/QR para inspección manual).
"""

from __future__ import annotations

import base64
import html
import logging
from pathlib import Path

import httpx
import msal

logger = logging.getLogger(__name__)

_LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "logo.png"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_AUTHORITY = "https://login.microsoftonline.com/{tenant}"


class EmailError(Exception):
    pass


class EmailSender:
    def __init__(
        self,
        *,
        enabled: bool,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        sender: str,
        emitter_display: str,
    ) -> None:
        self.enabled = enabled
        self._sender = sender
        self._emitter = emitter_display
        self._msal_app: msal.ConfidentialClientApplication | None = None
        if enabled:
            missing = [
                n
                for n, v in [
                    ("GRAPH_TENANT_ID", tenant_id),
                    ("GRAPH_CLIENT_ID", client_id),
                    ("GRAPH_CLIENT_SECRET", client_secret),
                    ("GRAPH_SENDER", sender),
                ]
                if not v
            ]
            if missing:
                raise EmailError(
                    "OFV_EMAIL_ENABLED=true pero falta configuración: " + ", ".join(missing)
                )
            self._msal_app = msal.ConfidentialClientApplication(
                client_id,
                authority=_AUTHORITY.format(tenant=tenant_id),
                client_credential=client_secret,
            )

    def _token(self) -> str:
        assert self._msal_app is not None
        result = self._msal_app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise EmailError(
                "MSAL falló: " + str(result.get("error_description", result.get("error")))
            )
        return result["access_token"]

    async def send_credential(
        self,
        *,
        to: str,
        razon_social: str,
        offer_uri: str,
        qr_png: bytes,
        subject: str,
        pin: str | None = None,
    ) -> None:
        if not self.enabled:
            raise EmailError("email deshabilitado (OFV_EMAIL_ENABLED=false)")
        token = self._token()
        logo_b64 = _logo_b64()
        body_html = _build_html(razon_social, offer_uri, pin, has_logo=logo_b64 is not None)
        attachments = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": "credencial-qr.png",
                "contentType": "image/png",
                "isInline": True,
                "contentId": "credqr",
                "contentBytes": base64.b64encode(qr_png).decode("ascii"),
            }
        ]
        if logo_b64:
            attachments.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "dgii-logo.png",
                    "contentType": "image/png",
                    "isInline": True,
                    "contentId": "dgiilogo",
                    "contentBytes": logo_b64,
                }
            )
        await self._send(token, to=to, subject=subject, body_html=body_html, attachments=attachments)
        logger.info("credencial enviada por correo a %s", to)

    async def send_revocation(
        self,
        *,
        to: str,
        razon_social: str,
        subject: str,
        motivo: str | None = None,
    ) -> None:
        """Notifica al contribuyente que su certificación fue revocada (invalidada)."""
        if not self.enabled:
            raise EmailError("email deshabilitado (OFV_EMAIL_ENABLED=false)")
        token = self._token()
        logo_b64 = _logo_b64()
        body_html = _build_revocation_html(razon_social, motivo, has_logo=logo_b64 is not None)
        attachments = []
        if logo_b64:
            attachments.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "dgii-logo.png",
                    "contentType": "image/png",
                    "isInline": True,
                    "contentId": "dgiilogo",
                    "contentBytes": logo_b64,
                }
            )
        await self._send(token, to=to, subject=subject, body_html=body_html, attachments=attachments)
        logger.info("notificación de revocación enviada por correo a %s", to)

    async def send_reinstatement(
        self,
        *,
        to: str,
        razon_social: str,
        subject: str,
    ) -> None:
        """Notifica al contribuyente que su certificación volvió a estar vigente."""
        if not self.enabled:
            raise EmailError("email deshabilitado (OFV_EMAIL_ENABLED=false)")
        token = self._token()
        logo_b64 = _logo_b64()
        body_html = _build_reinstatement_html(razon_social, has_logo=logo_b64 is not None)
        attachments = []
        if logo_b64:
            attachments.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "dgii-logo.png",
                    "contentType": "image/png",
                    "isInline": True,
                    "contentId": "dgiilogo",
                    "contentBytes": logo_b64,
                }
            )
        await self._send(token, to=to, subject=subject, body_html=body_html, attachments=attachments)
        logger.info("notificación de reinstalación enviada por correo a %s", to)

    async def _send(
        self,
        token: str,
        *,
        to: str,
        subject: str,
        body_html: str,
        attachments: list[dict],
    ) -> None:
        message = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": to}}],
                "attachments": attachments,
            },
            "saveToSentItems": True,
        }
        url = f"{_GRAPH_BASE}/users/{self._sender}/sendMail"
        async with httpx.AsyncClient(timeout=30.0) as c:
            resp = await c.post(
                url, headers={"Authorization": f"Bearer {token}"}, json=message
            )
        if resp.status_code not in (200, 202):
            raise EmailError(f"Graph sendMail falló ({resp.status_code}): {resp.text}")


def _logo_b64() -> str | None:
    try:
        return base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
    except OSError:
        return None


def _build_html(razon_social: str, offer_uri: str, pin: str | None, has_logo: bool) -> str:
    rs = html.escape(razon_social or "contribuyente")
    href = html.escape(offer_uri, quote=True)
    link = html.escape(offer_uri)
    logo = (
        '<img src="cid:dgiilogo" alt="Impuestos Internos — DGII" width="240" '
        'style="display:block;height:auto;border:0;">'
        if has_logo
        else '<div style="font-family:Georgia,serif;font-size:20px;color:#16386f;'
        'font-weight:bold;">Impuestos Internos · DGII</div>'
    )
    pin_block = (
        f'<tr><td align="center" style="padding:2px 0 6px;font-size:14px;color:#1b2620;">'
        f'Al reclamarla, ingrese el PIN: <b style="color:#16386f;letter-spacing:2px;">{html.escape(pin)}</b>'
        f'</td></tr>'
        if pin
        else ""
    )
    return f"""\
<div style="margin:0;padding:24px 12px;background:#eef2ea;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" align="center"
    style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #dbe4d4;border-radius:12px;overflow:hidden;">
    <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:22px 30px 18px;">{logo}</td></tr>
    <tr><td bgcolor="#2f7a1c" style="height:5px;background:#2f7a1c;font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:28px 30px 8px;color:#1b2620;font-size:15px;line-height:1.6;">
      <div style="color:#2f7a1c;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;font-weight:bold;margin-bottom:6px;">Certificación de Impuestos al Día</div>
      <h1 style="margin:0 0 16px;font-size:21px;color:#16386f;font-weight:bold;">Su certificación ha sido emitida</h1>
      <p style="margin:0 0 12px;">Estimado(a) contribuyente <b>{rs}</b>,</p>
      <p style="margin:0 0 4px;">Su <b>Certificación de Cumplimiento de Obligaciones Fiscales</b> ha sido
        emitida como una <b>credencial verificable</b>. Escanee el código con su billetera digital para
        recibirla, o utilice el botón.</p>
    </td></tr>
    <tr><td align="center" style="padding:14px 30px 2px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td bgcolor="#f5f9f1" style="background:#f5f9f1;border:1px solid #dbe4d4;border-radius:12px;padding:16px;">
          <img src="cid:credqr" alt="Código QR de la credencial" width="204" height="204" style="display:block;border:0;">
        </td>
      </tr></table>
    </td></tr>
    {pin_block}
    <tr><td align="center" style="padding:16px 30px 6px;">
      <a href="{href}" style="background:#2f7a1c;color:#ffffff;text-decoration:none;font-weight:bold;
        font-size:15px;padding:13px 30px;border-radius:8px;display:inline-block;">Reclamar credencial</a>
    </td></tr>
    <tr><td style="padding:6px 30px 24px;color:#5d6b5e;font-size:11px;line-height:1.5;word-break:break-all;">
      Si el botón no funciona, copie este enlace en su billetera:<br>{link}
    </td></tr>
    <tr><td bgcolor="#f5f9f1" style="background:#f5f9f1;border-top:1px solid #dbe4d4;padding:16px 30px;color:#5d6b5e;font-size:11px;line-height:1.5;">
      <b>Demo educativa</b> del bootcamp de credenciales verificables (CDPI). Entorno de prueba —
      no es un servicio real de la Dirección General de Impuestos Internos ni está afiliado a ella. Datos ficticios.
    </td></tr>
  </table>
</div>"""


def _build_revocation_html(razon_social: str, motivo: str | None, has_logo: bool) -> str:
    rs = html.escape(razon_social or "contribuyente")
    logo = (
        '<img src="cid:dgiilogo" alt="Impuestos Internos — DGII" width="240" '
        'style="display:block;height:auto;border:0;">'
        if has_logo
        else '<div style="font-family:Georgia,serif;font-size:20px;color:#16386f;'
        'font-weight:bold;">Impuestos Internos · DGII</div>'
    )
    motivo_block = (
        f'<p style="margin:0 0 12px;">Motivo: <b>{html.escape(motivo)}</b>.</p>'
        if motivo
        else ""
    )
    return f"""\
<div style="margin:0;padding:24px 12px;background:#f3eeee;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" align="center"
    style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e4d4d4;border-radius:12px;overflow:hidden;">
    <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:22px 30px 18px;">{logo}</td></tr>
    <tr><td bgcolor="#b3261e" style="height:5px;background:#b3261e;font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:28px 30px 8px;color:#1b2620;font-size:15px;line-height:1.6;">
      <div style="color:#b3261e;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;font-weight:bold;margin-bottom:6px;">Certificación de Impuestos al Día</div>
      <h1 style="margin:0 0 16px;font-size:21px;color:#16386f;font-weight:bold;">Su certificación ha sido revocada</h1>
      <p style="margin:0 0 12px;">Estimado(a) contribuyente <b>{rs}</b>,</p>
      <p style="margin:0 0 12px;">Le informamos que su <b>Certificación de Cumplimiento de Obligaciones
        Fiscales</b>, emitida como credencial verificable, ha sido <b>revocada</b> y ya no es válida.
        Cualquier verificador que la consulte la encontrará como <b>no vigente</b>.</p>
      {motivo_block}
      <p style="margin:0 0 4px;">Si considera que se trata de un error o desea regularizar su situación,
        contacte a la Dirección General de Impuestos Internos.</p>
    </td></tr>
    <tr><td bgcolor="#faf3f3" style="background:#faf3f3;border-top:1px solid #e4d4d4;padding:16px 30px;color:#5d6b5e;font-size:11px;line-height:1.5;">
      <b>Demo educativa</b> del bootcamp de credenciales verificables (CDPI). Entorno de prueba —
      no es un servicio real de la Dirección General de Impuestos Internos ni está afiliado a ella. Datos ficticios.
    </td></tr>
  </table>
</div>"""


def _build_reinstatement_html(razon_social: str, has_logo: bool) -> str:
    rs = html.escape(razon_social or "contribuyente")
    logo = (
        '<img src="cid:dgiilogo" alt="Impuestos Internos — DGII" width="240" '
        'style="display:block;height:auto;border:0;">'
        if has_logo
        else '<div style="font-family:Georgia,serif;font-size:20px;color:#16386f;'
        'font-weight:bold;">Impuestos Internos · DGII</div>'
    )
    return f"""\
<div style="margin:0;padding:24px 12px;background:#eef2ea;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" align="center"
    style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #dbe4d4;border-radius:12px;overflow:hidden;">
    <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:22px 30px 18px;">{logo}</td></tr>
    <tr><td bgcolor="#2f7a1c" style="height:5px;background:#2f7a1c;font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:28px 30px 8px;color:#1b2620;font-size:15px;line-height:1.6;">
      <div style="color:#2f7a1c;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;font-weight:bold;margin-bottom:6px;">Certificación de Impuestos al Día</div>
      <h1 style="margin:0 0 16px;font-size:21px;color:#16386f;font-weight:bold;">Su certificación vuelve a estar vigente</h1>
      <p style="margin:0 0 12px;">Estimado(a) contribuyente <b>{rs}</b>,</p>
      <p style="margin:0 0 12px;">Le informamos que su <b>Certificación de Cumplimiento de Obligaciones
        Fiscales</b> ha sido <b>reinstalada</b> y vuelve a ser válida. Los verificadores la aceptarán
        nuevamente como <b>vigente</b>.</p>
      <p style="margin:0 0 4px;">No es necesario que realice ninguna acción; su credencial verificable
        existente vuelve a ser aceptada automáticamente.</p>
    </td></tr>
    <tr><td bgcolor="#f5f9f1" style="background:#f5f9f1;border-top:1px solid #dbe4d4;padding:16px 30px;color:#5d6b5e;font-size:11px;line-height:1.5;">
      <b>Demo educativa</b> del bootcamp de credenciales verificables (CDPI). Entorno de prueba —
      no es un servicio real de la Dirección General de Impuestos Internos ni está afiliado a ella. Datos ficticios.
    </td></tr>
  </table>
</div>"""
