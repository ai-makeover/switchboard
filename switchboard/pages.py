"""Every HTML page a person sees: sign-in, confirm, and the status pages after it. Phone-first, light and dark.

Styled with the AI Makeover design system, Ledger White variation A (locked 14 Nov 2026): grey shell, one
white sheet, Alte Haas Grotesk (Bold headings, Regular body), ink primary buttons and focus ring, orange for
graphics only, green as a hint. Icons are Lucide (1.5px stroke), inlined so the pages need no scripts.
"""
from __future__ import annotations

import html
from importlib import resources

from starlette.responses import HTMLResponse, Response

STYLE = """
@font-face{font-family:'Alte Haas Grotesk';font-style:normal;font-weight:400;font-display:swap;src:url('/static/alte-haas-regular.ttf') format('truetype')}
@font-face{font-family:'Alte Haas Grotesk';font-style:normal;font-weight:700;font-display:swap;src:url('/static/alte-haas-bold.ttf') format('truetype')}
:root{--paper:#f4f4f2;--surface:#fff;--inset:#f6f6f4;--hover:#f0f0ed;--ink:#16161a;--text:#2e2e33;--muted:#6e6e74;--faint:#9a9aa1;--line:#ebebe8;--line-strong:#d8d8d3;
--orange:#ff8a1f;--orange-ink:#a35300;--orange-wash:#fff2e5;--action:#16161a;--action-hover:#2e2e33;--on-action:#fff;--green-hint:#7fae6a;--green-hint-wash:#f0f6eb;
--success:#2f7a4a;--success-wash:#e9f5ee;--success-line:#bddfc9;--warning:#956000;--warning-wash:#fff4db;--warning-line:#eed8a1;--danger:#b42318;--danger-wash:#fff1f0;--danger-line:#f5c5c0;
--sans:'Alte Haas Grotesk','Helvetica Neue',Arial,system-ui,sans-serif;--ease:cubic-bezier(.22,1,.36,1)}
@media (prefers-color-scheme:dark){:root{--paper:#0f0f12;--surface:#17171b;--inset:#1f1f24;--hover:#232329;--ink:#f4f4f5;--text:#d4d4d8;--muted:#8b8b93;--faint:#62626b;--line:#26262c;--line-strong:#34343c;
--orange-ink:#ffb26b;--orange-wash:#2e1f12;--action:#f4f4f5;--action-hover:#d4d4d8;--on-action:#16161a;--green-hint:#a8c98a;--green-hint-wash:#1c2618;
--success:#5fd39a;--success-wash:#14261d;--success-line:#365b43;--warning:#e8bd76;--warning-wash:#3a3121;--warning-line:#6a5631;--danger:#ffaaa0;--danger-wash:#3c2624;--danger-line:#75433c}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--text);font:400 14px/22px var(--sans);-webkit-font-smoothing:antialiased}
button,input{font:inherit}
main{max-width:30rem;margin:0 auto;padding:8px}
.brand{display:flex;align-items:center;gap:10px;padding:8px 8px 0}
.brand img{width:32px;height:32px;border-radius:8px;display:block}
.brand .name{color:var(--ink);font-size:15px;line-height:22px;font-weight:700;letter-spacing:-.01em}
.brand .by{color:var(--muted);font-size:12px;line-height:18px}
.sheet{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:24px;margin-top:8px}
h1{color:var(--ink);font-size:24px;line-height:30px;font-weight:700;letter-spacing:-.025em;margin:0 0 8px}
p{margin:0 0 12px}p:last-child{margin-bottom:0}
.lead{color:var(--muted);font-size:13px;line-height:20px}
b,strong{color:var(--ink);font-weight:700}
.icon{width:17px;height:17px;flex-shrink:0;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.tile{width:44px;height:44px;border-radius:12px;display:inline-flex;align-items:center;justify-content:center;background:var(--inset);color:var(--muted);margin-bottom:16px}
.tile .icon{width:22px;height:22px}
.tile.success{background:var(--success-wash);color:var(--success)}.tile.warning{background:var(--warning-wash);color:var(--warning)}
.tile.danger{background:var(--danger-wash);color:var(--danger)}.tile.ai{background:var(--green-hint-wash);color:var(--success)}
.field{display:flex;flex-direction:column;gap:6px;margin-top:16px}
.field label{color:var(--muted);font-size:13px;line-height:20px}
input[type=password]{width:100%;color:var(--ink);background:var(--surface);border:1px solid var(--line-strong);border-radius:8px;padding:9px 12px;min-height:40px}
input[aria-invalid=true]{border-color:var(--danger)}
.error{display:flex;gap:6px;align-items:flex-start;color:var(--danger);font-size:13px;line-height:20px}
.error .icon{width:15px;height:15px;margin-top:2px}
dl{margin:16px 0 0}dt{color:var(--muted);font-size:13px;line-height:20px}
dd{margin:2px 0 16px;color:var(--ink);font-size:15px;line-height:22px;font-weight:700}
.message{white-space:pre-wrap;word-break:break-word;color:var(--ink);margin:4px 0 0;padding:12px 14px;border-radius:8px;border:1px solid var(--line);background:var(--inset);font:inherit}
.notice{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--inset);font-size:13px;line-height:20px;margin-top:12px}
.notice .icon{width:16px;height:16px;margin-top:2px}
.notice.warning{color:var(--warning);background:var(--warning-wash);border-color:var(--warning-line)}
.notice.danger{color:var(--danger);background:var(--danger-wash);border-color:var(--danger-line)}
.notice b{color:inherit}
.health-label{display:inline-flex;align-items:center;gap:4px;font-size:12px;line-height:18px;padding:3px 8px;border-radius:6px;color:var(--muted);background:var(--inset);vertical-align:2px;margin-left:6px;font-weight:400}
.health-label .icon{width:13px;height:13px}
.actions{display:flex;gap:8px;margin-top:24px}
.actions form{flex:1;display:flex;margin:0}
.btn{flex:1;display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:40px;padding:8px 16px;border-radius:8px;border:1px solid var(--line-strong);background:var(--inset);color:var(--ink);font-weight:700;cursor:pointer;transition:background .15s var(--ease),border-color .15s var(--ease)}
.btn:hover{background:var(--hover)}
.btn.primary{background:var(--action);border-color:var(--action);color:var(--on-action)}
.btn.primary:hover{background:var(--action-hover);border-color:var(--action-hover)}
.btn .icon{width:16px;height:16px}
:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
footer{display:flex;align-items:center;justify-content:center;gap:8px;color:var(--muted);font-size:12px;line-height:18px;padding:16px 8px}
footer .live{width:6px;height:6px;border-radius:9999px;background:var(--green-hint)}
@media (min-width:600px){main{padding:32px 16px}.btn,input[type=password]{min-height:36px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

# Lucide 0.468 paths, drawn with the .icon class (24px grid, 1.5px stroke, currentColor).
ICONS = {
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "send": '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "x": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "key": '<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/>',
}


def icon(name: str) -> str:
    return f'<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


HEAD_LINKS = ('<link rel="icon" href="/favicon.ico" sizes="any">'
              '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
              '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
              '<link rel="preload" href="/static/alte-haas-bold.ttf" as="font" type="font/ttf" crossorigin>'
              '<meta name="theme-color" content="#f4f4f2">')

BRAND = ('<header class="brand"><img src="/favicon.svg" alt="" width="32" height="32">'
         '<div><div class="name">Switchboard</div><div class="by">By AI Makeover</div></div></header>')

# Served from switchboard/static. Names here are the only files reachable.
STATIC = {
    "favicon.ico": ("favicon.ico", "image/x-icon"),
    "favicon.svg": ("icon.svg", "image/svg+xml"),
    "icon.svg": ("icon.svg", "image/svg+xml"),
    "favicon-32.png": ("favicon-32.png", "image/png"),
    "apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "icon-192.png": ("icon-192.png", "image/png"),
    "icon-512.png": ("icon-512.png", "image/png"),
    "static/alte-haas-regular.ttf": ("alte-haas-regular.ttf", "font/ttf"),
    "static/alte-haas-bold.ttf": ("alte-haas-bold.ttf", "font/ttf"),
}


def static_file(name: str) -> Response:
    if name not in STATIC:
        return Response(status_code=404)
    fname, ctype = STATIC[name]
    data = resources.files("switchboard").joinpath("static", fname).read_bytes()
    return Response(data, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · Switchboard</title>'
           f'{HEAD_LINKS}<style>{STYLE}</style></head><body><main>{BRAND}<div class="sheet">{body}</div>'
           f'<footer><span class="live" aria-hidden="true"></span>Your private WhatsApp connector for Claude</footer>'
           f'</main></body></html>')
    resp = HTMLResponse(doc, status_code=status)
    resp.headers.update({
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; font-src 'self'; form-action 'self' https: http://localhost:* http://127.0.0.1:*; frame-ancestors 'none'",
    })
    return resp


# A status page: icon tile, bold title, one line. Tone picks the tile colour; the title always says it in words.
TONE_FOR_STATUS = {401: ("danger", "lock"), 403: ("danger", "lock"), 404: ("neutral", "info"),
                   429: ("warning", "clock"), 502: ("danger", "x")}


def status(title: str, text_html: str, http_status: int = 200, tone: str | None = None,
           icon_name: str | None = None) -> HTMLResponse:
    d_tone, d_icon = TONE_FOR_STATUS.get(http_status, ("warning", "alert") if http_status >= 400 else ("success", "check"))
    tone, icon_name = tone or d_tone, icon_name or d_icon
    cls = "" if tone == "neutral" else f" {tone}"
    body = f'<div class="tile{cls}">{icon(icon_name)}</div><h1>{html.escape(title)}</h1><p class="lead">{text_html}</p>'
    return page(title, body, http_status)


def message(title: str, text: str, status_code: int = 200, tone: str | None = None,
            icon_name: str | None = None) -> HTMLResponse:
    return status(title, html.escape(text), status_code, tone, icon_name)
