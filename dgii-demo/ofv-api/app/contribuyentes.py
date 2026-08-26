"""Lector del CSV de contribuyentes — simula la consulta al core tributario de la DGII.

El CSV (dgii-demo/data/contribuyentes-impuestos-al-dia.csv) tiene una fila por
contribuyente con las columnas del schema "Impuestos al Día". La regla de negocio:
un contribuyente puede certificarse si estadoCumplimiento == "AL_DIA".
"""

from __future__ import annotations

import csv
from pathlib import Path

# Campos del CSV que se envían como subject_data de la credencial.
# (individualId es el identificador del holder para el binding pre-auth.)
_SUBJECT_FIELDS = [
    "rnc",
    "razonSocial",
    "nombreComercial",
    "tipoContribuyente",
    "categoriaContribuyente",
    "regimenTributario",
    "actividadEconomica",
    "estadoRNC",
    "estadoCumplimiento",
    "obligacionesActivas",
    "domicilioFiscal",
    "provincia",
    "municipio",
    "concepto",
    "numeroReferencia",
    "fechaEmision",
    "fechaVencimiento",
    "individualId",
]

ESTADO_AL_DIA = "AL_DIA"


class ContribuyenteNoEncontrado(Exception):
    pass


class ContribuyenteNoAlDia(Exception):
    def __init__(self, estado: str) -> None:
        self.estado = estado
        super().__init__(f"contribuyente no está al día (estadoCumplimiento={estado})")


class Contribuyentes:
    """Carga el CSV en memoria e indexa por RNC. Recarga si el archivo cambia."""

    def __init__(self, csv_path: Path) -> None:
        self._path = csv_path
        self._by_rnc: dict[str, dict[str, str]] = {}
        self._mtime: float | None = None
        self.reload()

    def reload(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"CSV de contribuyentes no encontrado: {self._path}")
        with self._path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self._by_rnc = {r["rnc"].strip(): r for r in rows if r.get("rnc")}
        self._mtime = self._path.stat().st_mtime

    def _maybe_reload(self) -> None:
        if self._path.exists() and self._path.stat().st_mtime != self._mtime:
            self.reload()

    def buscar(self, rnc: str) -> dict[str, str]:
        """Devuelve la fila cruda del contribuyente o lanza ContribuyenteNoEncontrado."""
        self._maybe_reload()
        row = self._by_rnc.get(rnc.strip())
        if row is None:
            raise ContribuyenteNoEncontrado(rnc)
        return row

    def validar_al_dia(self, rnc: str) -> dict[str, str]:
        """Busca y verifica que esté al día. Lanza si no existe o no está al día."""
        row = self.buscar(rnc)
        estado = (row.get("estadoCumplimiento") or "").strip().upper()
        if estado != ESTADO_AL_DIA:
            raise ContribuyenteNoAlDia(estado or "DESCONOCIDO")
        return row

    def set_estado(self, rnc: str, estado: str) -> dict[str, str]:
        """Actualiza estadoCumplimiento de un RNC y reescribe el CSV (registro).

        Simula el cambio de estado tributario del contribuyente (p. ej. cae en
        mora al revocarse su certificación). Preserva el resto de columnas y el
        orden de filas.
        """
        row = self.buscar(rnc)  # lanza si no existe; refresca si cambió
        row["estadoCumplimiento"] = estado
        rows = list(self._by_rnc.values())
        fieldnames = list(rows[0].keys())
        with self._path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        self._mtime = self._path.stat().st_mtime
        return row

    @staticmethod
    def to_subject_data(row: dict[str, str]) -> dict[str, str]:
        """Mapea la fila del CSV al subject_data que espera verifiably."""
        data = {k: (row.get(k) or "") for k in _SUBJECT_FIELDS}
        # El schema exige rnc_id (identificador estable del sujeto); usamos el RNC.
        data["rnc_id"] = row.get("rnc", "").strip()
        return data
