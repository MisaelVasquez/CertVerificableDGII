"""Bitácora de auditoría por credencial: registra el ciclo de vida de cada certificación.

Guarda, por credential_id, una lista de eventos (emitida, revocada, reinstalada, verificada)
con marca de tiempo y un detalle legible. Respaldada por un JSON best-effort (como
[[recipients]]); si no se puede leer/escribir, la operación de negocio no se ve afectada.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditLog:
    """Historial de eventos por credential_id, persistido en un archivo JSON."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, list[dict]]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.warning("no se pudo leer la bitácora (%s): %s", self._path, e)
            return {}

    def registrar(self, credential_id: str, evento: str, detalle: str = "") -> None:
        """Añade un evento al historial de una credencial (best-effort)."""
        if not credential_id:
            return
        entrada = {
            "evento": evento,
            "detalle": detalle,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            data = self._load()
            data.setdefault(credential_id, []).append(entrada)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError as e:  # no debe tumbar la operación de negocio
                logger.warning("no se pudo guardar la bitácora: %s", e)

    def historial(self, credential_id: str) -> list[dict]:
        """Devuelve los eventos de una credencial, del más reciente al más antiguo."""
        with self._lock:
            eventos = list(self._load().get(credential_id, []))
        eventos.sort(key=lambda e: e.get("ts") or "", reverse=True)
        return eventos
