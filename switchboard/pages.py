"""The few HTML pages a person sees: login, confirm, refusals. Phone-first, light and dark."""
from __future__ import annotations

import html

from starlette.responses import HTMLResponse

STYLE = """
:root{--bg:#f6f6f4;--card:#fff;--ink:#1b1b1b;--mute:#6b6b6b;--line:#e3e3df;--go:#0a7d3b;--warn:#9a5b00}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--ink:#ededed;--mute:#9a9a9a;--line:#333;--go:#2fbf6c;--warn:#e0a040}}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:34rem;margin:0 auto;padding:24px 16px}
h1{font-size:1.25rem;margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.k{color:var(--mute);font-size:14px} .v{font-size:19px;font-weight:600;margin:2px 0 12px}
pre{white-space:pre-wrap;word-break:break-word;font:inherit;margin:0;padding:14px;border-radius:10px;border:1px solid var(--line);background:var(--bg)}
.warn{color:var(--warn);font-size:15px;margin-top:10px}
.row{display:flex;gap:10px;margin-top:18px}
input[type=password]{width:100%;box-sizing:border-box;font:inherit;padding:12px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
button{flex:1;font:inherit;font-weight:600;padding:14px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
button.go{background:var(--go);border-color:var(--go);color:#fff}
"""


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (f'<!doctype html><html><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
           f'<style>{STYLE}</style></head><body><main>{body}</main></body></html>')
    resp = HTMLResponse(doc, status_code=status)
    resp.headers.update({
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https: http://localhost:* http://127.0.0.1:*; frame-ancestors 'none'",
    })
    return resp


def message(title: str, text: str, status: int = 200) -> HTMLResponse:
    return page(title, f'<div class="card"><h1>{html.escape(title)}</h1><p>{html.escape(text)}</p></div>', status)
