"""CLI for Vantage FRC Phase 4: Web Dashboard."""

import argparse
import asyncio
import subprocess
import sys

import uvicorn

from vantage.config.settings import get_settings
from vantage.core.logging import configure_logging


def cmd_init(args) -> None:
    configure_logging()
    from vantage.db.session import init_db

    asyncio.run(init_db())
    print("Database initialized successfully.")


def cmd_serve(args) -> None:
    settings = get_settings()
    host = args.host or "127.0.0.1"
    port = args.port or 8000
    print(f"Vantage FRC dashboard → http://{host}:{port}")
    uvicorn.run(
        "vantage.web.app:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )


def cmd_open(args) -> None:
    port = args.port or 8000
    url = f"http://127.0.0.1:{port}"
    print(f"Opening {url} …")
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "", url])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="phase4", description="Vantage FRC web dashboard"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="ensure database tables exist").set_defaults(
        func=cmd_init
    )

    serve = sub.add_parser("serve", help="run the dashboard web server")
    serve.add_argument("--host", default=None, help="bind host (127.0.0.1)")
    serve.add_argument("--port", type=int, default=None, help="bind port (8000)")
    serve.add_argument(
        "--reload", action="store_true", help="auto reload on code change"
    )
    serve.set_defaults(func=cmd_serve)

    opn = sub.add_parser("open", help="open the dashboard in your browser")
    opn.add_argument("--port", type=int, default=None)
    opn.set_defaults(func=cmd_open)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()