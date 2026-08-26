"""Registro local de destinatarios: recuerda a qué correo se envió cada credencial.

verifiably no guarda el correo del contribuyente (solo los subjectFields del schema),
y el CSV se indexa por RNC. Para poder notificar una revocación "al mismo correo al que
se envió la credencial" persistimos un mapa credential_id -> correo al momento de emitir.

Es un JSON best-effort para el demo (no una base de datos): si el archivo no existe o no
se puede leer, simplemente no hay correo recordado y la notificación se omite.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class RecipientStore:
    """Mapa persistente credential_id -> correo, respaldado por un archivo JSON."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.warning("no se pudo leer el registro de correos (%s): %s", self._path, e)
            return {}

    def set(self, credential_id: str, email: str) -> None:
        """Recuerda el correo al que se envió una credencial."""
        with self._lock:
            data = self._load()
            data[credential_id] = email
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError as e:  # no debe tumbar la emisión
                logger.warning("no se pudo guardar el registro de correos: %s", e)

    def get(self, credential_id: str) -> str | None:
        """Devuelve el correo recordado para una credencial, o None."""
        with self._lock:
            return self._load().get(credential_id)
