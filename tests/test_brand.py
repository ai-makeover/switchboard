"""Brand assets are public, typed, and advertised to Claude as the server icon."""
from starlette.testclient import TestClient


def anon(mcp, s):
    return TestClient(mcp.http_app(path="/mcp", stateless_http=True), base_url=s.base_url, follow_redirects=False)


async def test_icons_served_without_sign_in(harness):
    mcp, _, _, s, _ = harness()
    with anon(mcp, s) as tc:
        for path, ctype in [("/favicon.ico", "image/x-icon"), ("/favicon.svg", "image/svg+xml"),
                            ("/icon.svg", "image/svg+xml"), ("/icon-512.png", "image/png"),
                            ("/apple-touch-icon.png", "image/png"), ("/static/alte-haas-regular.ttf", "font/ttf"), ("/static/alte-haas-bold.ttf", "font/ttf")]:
            r = tc.get(path)
            assert r.status_code == 200, path
            assert r.headers["content-type"].startswith(ctype), path
            assert len(r.content) > 100, path


async def test_no_other_files_reachable(harness):
    mcp, _, _, s, _ = harness()
    with anon(mcp, s) as tc:
        for path in ["/static/../config.py", "/static/icon.svg", "/static/switchboard.db"]:
            assert tc.get(path).status_code == 404, path


async def test_server_advertises_icon(harness):
    mcp, _, _, s, _ = harness()
    srcs = [i.src for i in (mcp.icons or [])]
    assert f"{s.base_url}/icon.svg" in srcs


async def test_pages_carry_brand_and_allow_own_assets(harness):
    mcp, _, _, s, _ = harness()
    with anon(mcp, s) as tc:
        r = tc.get("/login")
    assert "By AI Makeover" in r.text and 'href="/favicon.ico"' in r.text
    csp = r.headers["content-security-policy"]
    assert "img-src 'self'" in csp and "font-src 'self'" in csp and "script-src" not in csp
