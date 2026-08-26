"""Tests del flujo OFV con el backend verifiably mockeado (respx). Email deshabilitado."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.recipients import RecipientStore


def _csv_al_dia(tmp_path, monkeypatch, rnc="131000001"):
    """CSV aislado con un contribuyente AL_DIA, para no depender del data/ mutable."""
    csv = tmp_path / "c.csv"
    csv.write_text(
        "rnc,razonSocial,estadoCumplimiento,numeroReferencia,fechaEmision,fechaVencimiento,individualId\n"
        f"{rnc},Ferretería El Yunque SRL,AL_DIA,CERT-1,2026-07-15,2026-10-13,{rnc}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OFV_CONTRIBUYENTES_CSV", str(csv))
    get_settings.cache_clear()
    if hasattr(app.state, "contribuyentes"):
        del app.state.contribuyentes
    return csv


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch, tmp_path_factory):
    # Email off; api key presente para que VerifiablyClient no falle al construirse.
    monkeypatch.setenv("OFV_EMAIL_ENABLED", "false")
    monkeypatch.setenv("VERIFIABLY_API_KEY", "test-key")
    monkeypatch.setenv("VERIFIABLY_SCHEMA_ID", "impuestos-al-dia")
    # Aísla los registros persistentes (correos / bitácora) fuera de data/.
    tmp = tmp_path_factory.mktemp("stores")
    monkeypatch.setenv("OFV_RECIPIENTS_PATH", str(tmp / "correos.json"))
    monkeypatch.setenv("OFV_AUDIT_PATH", str(tmp / "bitacora.json"))
    get_settings.cache_clear()
    for attr in ("contribuyentes", "verifiably", "email", "recipients", "audit", "verif_logged"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    yield
    get_settings.cache_clear()


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["csv_encontrado"] is True
    assert body["email_habilitado"] is False


@respx.mock
def test_emision_al_dia(tmp_path, monkeypatch):
    _csv_al_dia(tmp_path, monkeypatch)
    respx.post("http://localhost:8080/api/v1/credentials/issue").mock(
        return_value=httpx.Response(
            200,
            json={
                "credential_id": "cred-123",
                "offer_uri": "openid-credential-offer://?credential_offer_uri=https://x/y",
                "pin": "4321",
                "flow": "pre_auth",
            },
        )
    )
    with TestClient(app) as client:
        r = client.post(
            "/ofv/certificaciones",
            json={"rnc": "131000001", "email": "contribuyente@example.com"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "emitida"
    assert body["credential_id"] == "cred-123"
    assert body["offer_uri"].startswith("openid-credential-offer://")
    assert body["qr_data_uri"].startswith("data:image/png;base64,")
    assert body["correo_enviado"] is False
    assert body["enviado_a"] is None


def test_rnc_no_encontrado():
    with TestClient(app) as client:
        r = client.post(
            "/ofv/certificaciones",
            json={"rnc": "000000000", "email": "x@example.com"},
        )
    assert r.status_code == 404


def test_no_al_dia(tmp_path, monkeypatch):
    # CSV con un contribuyente moroso.
    csv = tmp_path / "c.csv"
    csv.write_text(
        "rnc,razonSocial,estadoCumplimiento,fechaEmision,fechaVencimiento,individualId\n"
        "999,Moroso SRL,MOROSO,2026-01-01,2026-04-01,999\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OFV_CONTRIBUYENTES_CSV", str(csv))
    get_settings.cache_clear()
    if hasattr(app.state, "contribuyentes"):
        del app.state.contribuyentes
    with TestClient(app) as client:
        r = client.post(
            "/ofv/certificaciones", json={"rnc": "999", "email": "x@example.com"}
        )
    assert r.status_code == 409


@respx.mock
def test_revocar():
    # listar_dgii consulta las credenciales active/revoked para resolver el RNC.
    respx.get("http://localhost:8080/api/v1/credentials").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    respx.post("http://localhost:8080/api/v1/credentials/cred-123/revoke").mock(
        return_value=httpx.Response(200, json={})
    )
    with TestClient(app) as client:
        r = client.post("/ofv/certificaciones/cred-123/revocar")
    assert r.status_code == 200
    body = r.json()
    assert body["estado"] == "revocada"
    # Email deshabilitado en tests: no se notifica.
    assert body["correo_enviado"] is False
    assert body["enviado_a"] is None


@respx.mock
def test_historial_emitida(tmp_path, monkeypatch):
    _csv_al_dia(tmp_path, monkeypatch)
    respx.post("http://localhost:8080/api/v1/credentials/issue").mock(
        return_value=httpx.Response(
            200,
            json={
                "credential_id": "cred-hist",
                "offer_uri": "openid-credential-offer://?x=1",
                "pin": "0001",
                "flow": "pre_auth",
            },
        )
    )
    with TestClient(app) as client:
        client.post(
            "/ofv/certificaciones",
            json={"rnc": "131000001", "email": "c@example.com"},
        )
        r = client.get("/ofv/certificaciones/cred-hist/historial")
    assert r.status_code == 200
    eventos = r.json()["eventos"]
    assert len(eventos) == 1
    assert eventos[0]["evento"] == "emitida"
    assert eventos[0]["ts"]


def test_recipient_store_roundtrip(tmp_path):
    store = RecipientStore(tmp_path / "sub" / "correos.json")
    assert store.get("cred-1") is None
    store.set("cred-1", "a@example.com")
    store.set("cred-2", "b@example.com")
    # Una instancia nueva lee lo persistido en disco.
    reloaded = RecipientStore(tmp_path / "sub" / "correos.json")
    assert reloaded.get("cred-1") == "a@example.com"
    assert reloaded.get("cred-2") == "b@example.com"
