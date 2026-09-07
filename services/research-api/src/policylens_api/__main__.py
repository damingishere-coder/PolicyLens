from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from .app import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PolicyLens localhost browser service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--static-dir", type=Path, required=True)
    parser.add_argument("--manager", default=os.environ.get("POLICYLENS_MANAGER", "manual"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("PolicyLens only supports the loopback host")
    app = create_app(
        args.data_dir,
        browser_mode=True,
        static_dir=args.static_dir,
        bound_port=args.port,
        manager=args.manager,
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="warning",
        server_header=False,
    )


if __name__ == "__main__":
    main()
