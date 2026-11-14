"""The few HTML pages a person sees: login, confirm, refusals. Phone-first, light and dark, AI Makeover style."""
from __future__ import annotations

import html
from importlib import resources

from starlette.responses import HTMLResponse, Response

# AI Makeover design system tokens (aim-design-system v1): Figtree, paper/surface neutrals, orange with purpose.
STYLE = """
@font-face{font-family:'Figtree';font-style:normal;font-weight:300 900;font-display:swap;src:url('/static/figtree.ttf') format('truetype')}
:root{--paper:#f7f8fa;--surface:#fff;--inset:#f4f4f7;--ink:#24242e;--text:#363644;--muted:#70707d;--line:#eaeaf0;--line-strong:#d1d1dc;--orange:#e8590c;--action:#bf4809;--action-hover:#a83c05;--on-action:#fff;--warning:#956000;--warning-wash:#fff4db;--warning-line:#eed8a1}
@media (prefers-color-scheme:dark){:root{--paper:#17171d;--surface:#202027;--inset:#2a2a32;--ink:#f5f5f7;--text:#dddde3;--muted:#aaaab5;--line:#32323d;--line-strong:#50505f;--orange:#f47839;--action:#e8590c;--action-hover:#f47839;--on-action:#15100d;--warning:#e8bd76;--warning-wash:#3a3121;--warning-line:#6a5631}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--text);font:15px/24px 'Figtree',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:34rem;margin:0 auto;padding:24px 16px 48px}
.brand{display:flex;align-items:center;gap:12px;margin:8px 0 20px}
.brand img{width:40px;height:40px;border-radius:10px;border:1px solid var(--line)}
.brand .name{color:var(--ink);font-size:17px;line-height:22px;font-weight:500;letter-spacing:-.01em}
.brand .by{color:var(--muted);font-size:13px;line-height:18px}
h1{color:var(--ink);font-size:20px;line-height:28px;font-weight:400;letter-spacing:-.025em;margin:0 0 12px}
p{margin:0 0 12px} p:last-child{margin-bottom:0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:24px}
.k{color:var(--muted);font-size:13px;line-height:20px} .v{color:var(--ink);font-size:17px;font-weight:500;margin:2px 0 14px}
pre{white-space:pre-wrap;word-break:break-word;font:inherit;color:var(--ink);margin:2px 0 0;padding:14px;border-radius:8px;border:1px solid var(--line);background:var(--inset)}
.warn{color:var(--warning);background:var(--warning-wash);border:1px solid var(--warning-line);border-radius:8px;padding:10px 12px;font-size:14px;margin-top:12px}
.row{display:flex;gap:10px;margin-top:20px}
label.k{display:block;margin-bottom:6px}
input[type=password]{width:100%;font:inherit;color:var(--ink);padding:10px 12px;min-height:44px;border-radius:8px;border:1px solid var(--line-strong);background:var(--surface)}
button{flex:1;font:inherit;font-weight:500;min-height:44px;padding:10px 18px;border-radius:999px;border:1px solid var(--line-strong);background:var(--inset);color:var(--ink);cursor:pointer;transition:background .1s cubic-bezier(.2,.7,.2,1)}
button.go{background:var(--action);border-color:var(--action);color:var(--on-action)}
button.go:hover{background:var(--action-hover);border-color:var(--action-hover)}
:focus-visible{outline:2px solid var(--orange);outline-offset:3px}
footer{color:var(--muted);font-size:12px;line-height:20px;text-align:center;margin-top:24px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

HEAD_LINKS = ('<link rel="icon" href="/favicon.ico" sizes="any">'
              '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
              '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
              '<meta name="theme-color" content="#f7f8fa">')

BRAND = ('<div class="brand"><img src="/favicon.svg" alt="" width="40" height="40">'
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
    "static/figtree.ttf": ("figtree.ttf", "font/ttf"),
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
           f'{HEAD_LINKS}<style>{STYLE}</style></head><body><main>{BRAND}{body}'
           f'<footer>Your private WhatsApp connector for Claude</footer></main></body></html>')
    resp = HTMLResponse(doc, status_code=status)
    resp.headers.update({
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; font-src 'self'; form-action 'self' https: http://localhost:* http://127.0.0.1:*; frame-ancestors 'none'",
    })
    return resp


def message(title: str, text: str, status: int = 200) -> HTMLResponse:
    return page(title, f'<div class="card"><h1>{html.escape(title)}</h1><p>{html.escape(text)}</p></div>', status)
