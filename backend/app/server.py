"""Portable production entrypoint for Cloud Run and local containers."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    try:
        port = int(os.getenv("PORT", "8000"))
    except ValueError:
        port = 8000

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*" if os.getenv("TRUST_PROXY_HEADERS", "false").lower() in {"1", "true", "yes"} else "127.0.0.1",
    )


if __name__ == "__main__":
    main()
