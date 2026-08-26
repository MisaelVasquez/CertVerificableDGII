"""Configuración de la API OFV, leída de variables de entorno / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).resolve().parent.parent  # dgii-demo/ofv-api/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_HERE / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Fuente de datos del contribuyente
    ofv_contribuyentes_csv: str = "../data/contribuyentes-impuestos-al-dia.csv"

    # Registro local de destinatarios (credential_id -> correo) para notificar revocaciones
    ofv_recipients_path: str = "../data/credencial-correos.json"

    # Bitácora de auditoría por credencial (eventos del ciclo de vida)
    ofv_audit_path: str = "../data/credencial-bitacora.json"

    # Backend verifiably
    verifiably_base_url: str = "http://localhost:8080"
    verifiably_api_key: str = ""
    verifiably_schema_id: str = ""
    verifiably_schema_name: str = "Certificación de Impuestos al Día"
    verifiably_issuer_dpg: str = ""

    # Entrega por correo (Microsoft Graph, app-only)
    ofv_email_enabled: bool = False
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_sender: str = ""

    # Presentación
    ofv_emitter_display: str = "Dirección General de Impuestos Internos (DGII)"
    ofv_email_subject: str = "Su Certificación de Impuestos al Día (credencial verificable)"
    ofv_revocation_subject: str = "Su Certificación de Impuestos al Día ha sido revocada"
    ofv_reinstatement_subject: str = "Su Certificación de Impuestos al Día ha sido reinstalada"

    @property
    def contribuyentes_path(self) -> Path:
        p = Path(self.ofv_contribuyentes_csv)
        return p if p.is_absolute() else (_HERE / p).resolve()

    @property
    def recipients_path(self) -> Path:
        p = Path(self.ofv_recipients_path)
        return p if p.is_absolute() else (_HERE / p).resolve()

    @property
    def audit_path(self) -> Path:
        p = Path(self.ofv_audit_path)
        return p if p.is_absolute() else (_HERE / p).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
