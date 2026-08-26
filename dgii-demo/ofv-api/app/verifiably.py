"""Cliente del backend verifiably — emite/revoca la credencial verificable vía su API JSON.

Endpoints usados (auth: Authorization: Bearer <VERIFIABLY_API_KEY>):
  GET  /api/v1/schemas                     -> resolver schema_id por nombre
  POST /api/v1/credentials/issue           -> { credential_id, offer_uri, pin, flow }
  POST /api/v1/credentials/{id}/revoke     -> revoca (simulación de morosidad)
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class VerifiablyError(Exception):
    pass


@dataclass
class OfertaCredencial:
    credential_id: str
    offer_uri: str
    pin: str | None
    flow: str | None


class VerifiablyClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        schema_id: str = "",
        schema_name: str = "",
        issuer_dpg: str = "",
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise VerifiablyError("VERIFIABLY_API_KEY no configurada")
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._schema_id = schema_id
        self._schema_name = schema_name
        self._issuer_dpg = issuer_dpg
        self._timeout = timeout

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, headers=self._headers, timeout=self._timeout)

    async def resolver_schema_id(self) -> str:
        """Devuelve el schema_id configurado, o lo resuelve por nombre vía /api/v1/schemas."""
        if self._schema_id:
            return self._schema_id
        async with await self._client() as c:
            resp = await c.get("/api/v1/schemas")
        if resp.status_code != 200:
            raise VerifiablyError(f"listar schemas falló ({resp.status_code}): {resp.text}")
        payload = resp.json()
        items = payload if isinstance(payload, list) else payload.get("schemas", payload.get("items", []))
        for s in items:
            name = s.get("name") or s.get("schema_name") or s.get("title")
            if name and name.strip() == self._schema_name.strip():
                sid = s.get("id") or s.get("schema_id")
                if sid:
                    self._schema_id = sid
                    return sid
        raise VerifiablyError(
            f"no se encontró el schema por nombre: {self._schema_name!r}. "
            "Configura VERIFIABLY_SCHEMA_ID explícitamente."
        )

    async def emitir(self, subject_data: dict[str, str]) -> OfertaCredencial:
        schema_id = await self.resolver_schema_id()
        body: dict[str, object] = {"schema_id": schema_id, "subject_data": subject_data}
        if self._issuer_dpg:
            body["issuer_dpg"] = self._issuer_dpg
        async with await self._client() as c:
            resp = await c.post("/api/v1/credentials/issue", json=body)
        if resp.status_code != 200:
            raise VerifiablyError(f"emisión falló ({resp.status_code}): {resp.text}")
        data = resp.json()
        return OfertaCredencial(
            credential_id=data["credential_id"],
            offer_uri=data["offer_uri"],
            pin=data.get("pin"),
            flow=data.get("flow"),
        )

    async def revocar(self, credential_id: str) -> None:
        async with await self._client() as c:
            resp = await c.post(f"/api/v1/credentials/{credential_id}/revoke")
        if resp.status_code not in (200, 204):
            raise VerifiablyError(f"revocación falló ({resp.status_code}): {resp.text}")

    async def reinstalar(self, credential_id: str) -> None:
        async with await self._client() as c:
            resp = await c.post(f"/api/v1/credentials/{credential_id}/reinstate")
        if resp.status_code not in (200, 204):
            raise VerifiablyError(f"reinstalación falló ({resp.status_code}): {resp.text}")

    async def solicitar_verificacion(
        self, schema_id: str, fields: list[str]
    ) -> dict:
        """Crea una solicitud de presentación OID4VP. Devuelve {request_uri, state}."""
        body: dict[str, object] = {"schema_id": schema_id}
        if fields:
            body["fields"] = fields
        async with await self._client() as c:
            resp = await c.post("/api/v1/verify/request", json=body)
        if resp.status_code != 200:
            raise VerifiablyError(f"solicitud de verificación falló ({resp.status_code}): {resp.text}")
        return resp.json()

    async def resultado_verificacion(self, state: str) -> dict:
        """Consulta el resultado de una presentación por su `state`."""
        async with await self._client() as c:
            resp = await c.get(f"/api/v1/verify/result/{state}")
        if resp.status_code != 200:
            raise VerifiablyError(f"resultado de verificación falló ({resp.status_code}): {resp.text}")
        return resp.json()

    async def _listar_estado(self, estado: str) -> list[dict]:
        async with await self._client() as c:
            resp = await c.get("/api/v1/credentials", params={"state": estado})
        if resp.status_code != 200:
            raise VerifiablyError(f"listar falló ({resp.status_code}): {resp.text}")
        return resp.json().get("items", [])

    async def listar_dgii(self, schema_id: str) -> list[dict]:
        """Lista las credenciales del schema DGII, cada una etiquetada active/revoked."""
        out: list[dict] = []
        for estado in ("active", "revoked"):
            for it in await self._listar_estado(estado):
                if schema_id and it.get("schemaId") != schema_id:
                    continue
                subj = it.get("subjectFields", {})
                out.append(
                    {
                        "credential_id": it.get("id"),
                        "rnc": subj.get("rnc") or it.get("holderHint"),
                        "razon_social": subj.get("razonSocial"),
                        "estado_cumplimiento": subj.get("estadoCumplimiento"),
                        "numero_referencia": subj.get("numeroReferencia"),
                        "issued_at": it.get("issuedAt"),
                        "status": estado,
                    }
                )
        out.sort(key=lambda x: x.get("issued_at") or "", reverse=True)
        return out
