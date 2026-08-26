"""Genera un QR del offer_uri (OpenID4VCI) como PNG en memoria y como data URI."""

from __future__ import annotations

import base64
import io

import segno


def qr_png_bytes(data: str, scale: int = 6) -> bytes:
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()


def qr_data_uri(data: str, scale: int = 6) -> str:
    b64 = base64.b64encode(qr_png_bytes(data, scale=scale)).decode("ascii")
    return f"data:image/png;base64,{b64}"
