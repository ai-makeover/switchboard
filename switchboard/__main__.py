"""Run: python -m switchboard (Railway sets PORT)."""
import logging
import os
import sys

import uvicorn

from .config import ConfigError, Settings
from .server import build


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # request lines carry paths and tokens
    try:
        settings = Settings.from_env()
    except ConfigError as e:
        print(f"switchboard: config error: {e}", file=sys.stderr)
        sys.exit(2)
    mcp = build(settings)
    app = mcp.http_app(path="/mcp", stateless_http=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), access_log=False,
                proxy_headers=True, forwarded_allow_ips="*", log_level="info")


if __name__ == "__main__":
    main()
