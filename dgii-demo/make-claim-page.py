#!/usr/bin/env python3
"""Construye claim.html (página con QR para escanear) a partir de la respuesta
JSON de la OFV (POST /ofv/certificaciones).

Uso:  python3 make-claim-page.py <offer.json> <salida.html> [issuer_url]
"""
import html
import json
import sys


def build(offer_path: str, out_path: str, issuer: str = "") -> None:
    d = json.load(open(offer_path, encoding="utf-8"))
    qr = d["qr_data_uri"]
    offer = d["offer_uri"]
    rnc = html.escape(str(d.get("rnc") or ""))
    razon = html.escape(d.get("razon_social") or "")
    cid = html.escape(d.get("credential_id") or "")
    issuer = html.escape(issuer or "")
    page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Reclamar credencial · Demo OFV DGII</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{ --bg:#f5f6f8; --panel:#fff; --ink:#1a2230; --muted:#5b6675; --line:#e3e7ee;
  --accent:#1f5fbf; --good:#177245; --good-bg:#e6f3ec; --warn:#8a5a00; --warn-bg:#fbf1dc;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
@media (prefers-color-scheme:dark) {{ :root {{ --bg:#0f141b; --panel:#161d27; --ink:#e7ecf3;
  --muted:#9aa6b6; --line:#26303d; --accent:#5c9bff; --good:#5bd08a; --good-bg:#12271c;
  --warn:#e8b765; --warn-bg:#2a2113; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans); line-height:1.55; }}
.wrap {{ max-width:640px; margin:0 auto; padding:32px 20px 56px; }}
.eyebrow {{ font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--accent); font-weight:600; }}
h1 {{ font-size:26px; margin:6px 0 4px; }}
.sub {{ color:var(--muted); margin:0 0 24px; font-size:15px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:24px; margin-bottom:18px; }}
.qrbox {{ display:flex; flex-direction:column; align-items:center; gap:14px; }}
.qrbox img {{ width:260px; height:260px; max-width:100%; image-rendering:pixelated; background:#fff;
  padding:12px; border-radius:12px; border:1px solid var(--line); }}
.chip {{ display:inline-flex; align-items:center; gap:6px; font-size:13px; font-weight:600;
  color:var(--good); background:var(--good-bg); padding:4px 10px; border-radius:999px; }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:8px 18px; margin:0; font-size:14px; }}
dt {{ color:var(--muted); }} dd {{ margin:0; font-weight:500; }}
dd.mono {{ font-family:var(--mono); font-size:12.5px; word-break:break-all; }}
h2 {{ font-size:15px; margin:0 0 14px; }}
ol {{ margin:0; padding-left:0; list-style:none; counter-reset:s; display:flex; flex-direction:column; gap:12px; }}
ol li {{ counter-increment:s; padding-left:38px; position:relative; font-size:14.5px; }}
ol li::before {{ content:counter(s); position:absolute; left:0; top:-1px; width:26px; height:26px; display:grid;
  place-items:center; background:var(--accent); color:#fff; border-radius:8px; font-size:13px; font-weight:700; }}
.callout {{ border-left:3px solid var(--warn); background:var(--warn-bg); padding:14px 16px;
  border-radius:0 10px 10px 0; font-size:13.5px; }}
.callout b {{ color:var(--warn); }}
.url {{ background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:10px 12px;
  font-family:var(--mono); font-size:11.5px; word-break:break-all; color:var(--muted); }}
.foot {{ color:var(--muted); font-size:12px; text-align:center; margin-top:8px; }}
</style></head><body>
<div class="wrap">
  <div class="eyebrow">Bootcamp CDPI · Demo OFV DGII (entorno local)</div>
  <h1>Reclama tu Certificación de Impuestos al Día</h1>
  <p class="sub">Escanea el código con tu wallet para recibir la credencial verificable del entorno de prueba.</p>
  <div class="card qrbox">
    <img src="{qr}" alt="Código QR de la oferta de credencial">
    <span class="chip">● Contribuyente al día</span>
  </div>
  <div class="card"><dl>
    <dt>RNC</dt><dd class="mono">{rnc}</dd>
    <dt>Razón social</dt><dd>{razon}</dd>
    <dt>Formato</dt><dd class="mono">vc+sd-jwt</dd>
    <dt>Emisor</dt><dd class="mono">{issuer}</dd>
    <dt>Credencial</dt><dd class="mono">{cid}</dd>
  </dl></div>
  <div class="card"><h2>Cómo reclamarla en el iPhone</h2><ol>
    <li>Conecta el iPhone al <b>mismo hotspot / red</b> que esta laptop.</li>
    <li>Abre <b>Inji Wallet</b> y usa <b>“Descargar credencial / escanear QR”</b>.</li>
    <li>Apunta la cámara a este código y confirma la descarga.</li>
  </ol></div>
  <div class="callout"><b>Si el wallet falla:</b> el emisor usa <b>HTTP</b> (no HTTPS); algunos wallets lo rechazan.
    Si pasa, hará falta un túnel HTTPS. La oferta además <b>caduca</b>: si expira, regénérala corriendo el script de nuevo.</div>
  <p class="foot" style="margin-top:20px">Enlace de la oferta (por si tu wallet permite pegar):</p>
  <div class="url">{html.escape(offer)}</div>
</div></body></html>"""
    open(out_path, "w", encoding="utf-8").write(page)
    print(f"claim page -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
