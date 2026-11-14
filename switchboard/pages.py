"""The few HTML pages a person sees: login, confirm, refusals. Phone-first, light and dark, AI Makeover style."""
from __future__ import annotations

import html
from importlib import resources

from starlette.responses import HTMLResponse, Response

# AI Makeover design system, Ledger White variation A (locked 14 Nov 2026). Grey shell, one white sheet,
# ink primary buttons, orange for graphics only. Alte Haas is listed first but not shipped: its licence isn't
# cleared for public pages, so visitors without it get the documented fallback (Helvetica Neue, Arial).
STYLE = """
:root{--paper:#f4f4f2;--surface:#fff;--inset:#f6f6f4;--hover:#f0f0ed;--ink:#16161a;--text:#2e2e33;--muted:#6e6e74;--line:#ebebe8;--line-strong:#d8d8d3;--orange:#ff8a1f;--orange-ink:#a35300;--action:#16161a;--action-hover:#2e2e33;--on-action:#fff;--green-hint:#7fae6a;--warning:#956000;--warning-wash:#fff4db;--warning-line:#eed8a1}
@media (prefers-color-scheme:dark){:root{--paper:#0f0f12;--surface:#17171b;--inset:#1f1f24;--hover:#232329;--ink:#f4f4f5;--text:#d4d4d8;--muted:#8b8b93;--line:#26262c;--line-strong:#34343c;--orange-ink:#ffb26b;--action:#f4f4f5;--action-hover:#d4d4d8;--on-action:#16161a;--green-hint:#a8c98a;--warning:#e8bd76;--warning-wash:#3a3121;--warning-line:#6a5631}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--text);font:14px/22px 'Alte Haas Grotesk','Helvetica Neue',Arial,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:30rem;margin:0 auto;padding:8px}
.sheet{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:24px;margin-top:8px}
.brand{display:flex;align-items:center;gap:10px;padding:8px 8px 0}
.brand img{width:32px;height:32px;border-radius:8px}
.brand .name{color:var(--ink);font-size:15px;line-height:20px;font-weight:700;letter-spacing:-.01em}
.brand .by{color:var(--muted);font-size:12px;line-height:18px}
h1{color:var(--ink);font-size:24px;line-height:30px;font-weight:700;letter-spacing:-.025em;margin:0 0 12px}
p{margin:0 0 12px} p:last-child{margin-bottom:0}
.k{color:var(--muted);font-size:13px;line-height:20px} .v{color:var(--ink);font-size:15px;line-height:22px;font-weight:700;margin:2px 0 16px}
pre{white-space:pre-wrap;word-break:break-word;font:inherit;color:var(--ink);margin:4px 0 0;padding:12px;border-radius:8px;border:1px solid var(--line);background:var(--inset)}
.warn{color:var(--warning);background:var(--warning-wash);border:1px solid var(--warning-line);border-radius:8px;padding:10px 12px;font-size:13px;line-height:20px;margin-top:12px}
.row{display:flex;gap:8px;margin-top:20px}
label.k{display:block;margin-bottom:6px}
input[type=password]{width:100%;font:inherit;color:var(--ink);padding:9px 12px;min-height:40px;border-radius:8px;border:1px solid var(--line-strong);background:var(--surface)}
button{flex:1;font:inherit;font-weight:700;min-height:40px;padding:8px 16px;border-radius:8px;border:1px solid var(--line-strong);background:var(--inset);color:var(--ink);cursor:pointer;transition:background .12s cubic-bezier(.22,1,.36,1)}
button:hover{background:var(--hover)}
button.go{background:var(--action);border-color:var(--action);color:var(--on-action)}
button.go:hover{background:var(--action-hover);border-color:var(--action-hover)}
:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
footer{color:var(--muted);font-size:12px;line-height:18px;text-align:center;padding:16px 8px}
footer .dot{display:inline-block;width:6px;height:6px;border-radius:9999px;background:var(--green-hint);margin-right:6px;vertical-align:1px}
@media (min-width:600px){main{padding:24px 16px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

HEAD_LINKS = ('<link rel="icon" href="/favicon.ico" sizes="any">'
              '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
              '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
              '<meta name="theme-color" content="#f4f4f2">')

BRAND = ('<div class="brand"><img src="/favicon.svg" alt="" width="32" height="32">'
         '<div><div class="name">Switchboard</div><div class="by">By AI Makeover</div></div></div>')

# Served from switchboard/static. Names here are the only files reachable.
STATIC = {
    "favicon.ico": ("favicon.ico", "image/x-icon"),
    "favicon.svg": ("icon.svg", "image/svg+xml"),
    "icon.svg": ("icon.svg", "image/svg+xml"),
    "favicon-32.png": ("favicon-32.png", "image/png"),
    "apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "icon-192.png": ("icon-192.png", "image/png"),
    "icon-512.png": ("icon-512.png", "image/png"),
}


def static_file(name: str) -> Response:
    if name not in STATIC:
        return Response(status_code=404)
    fname, ctype = STATIC[name]
    data = resources.files("switchboard").joinpath("static", fname).read_bytes()
    return Response(data, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
           f'{HEAD_LINKS}<style>{STYLE}</style></head><body><main>{BRAND}<div class="sheet">{body}</div>'
           f'<footer><span class="dot"></span>Your private WhatsApp connector for Claude</footer></main></body></html>')
    resp = HTMLResponse(doc, status_code=status)
    resp.headers.update({
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; form-action 'self' https: http://localhost:* http://127.0.0.1:*; frame-ancestors 'none'",
    })
    return resp


def message(title: str, text: str, status: int = 200) -> HTMLResponse:
    return page(title, f'<div class="card"><h1>{html.escape(title)}</h1><p>{html.escape(text)}</p></div>', status)
