"""Modelos de request/response de la API OFV."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class CertificacionRequest(BaseModel):
    rnc: str = Field(..., description="RNC/cédula del contribuyente a certificar")
    email: EmailStr = Field(..., description="Correo donde se enviará la credencial")


class CertificacionResponse(BaseModel):
    estado: str  # "emitida"
    rnc: str
    razon_social: str | None = None
    credential_id: str
    enviado_a: str | None = None  # correo si se envió; None si OFV_EMAIL_ENABLED=false
    offer_uri: str
    qr_data_uri: str | None = None
    pin: str | None = None
    correo_enviado: bool = False


class RevocacionResponse(BaseModel):
    estado: str  # "revocada"
    credential_id: str
    enviado_a: str | None = None  # correo notificado si se recordó y el envío está habilitado
    correo_enviado: bool = False


class ReinstalacionResponse(BaseModel):
    estado: str  # "activa"
    credential_id: str
    enviado_a: str | None = None
    correo_enviado: bool = False


class ErrorResponse(BaseModel):
    estado: str  # "rechazada" | "error"
    detalle: str
