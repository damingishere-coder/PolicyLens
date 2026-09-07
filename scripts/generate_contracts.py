from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_SRC = ROOT / "services" / "research-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from policylens_api.app import create_app
from policylens_api.crypto import AesTestProtector


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "packages" / "contracts" / "openapi.json"
    with tempfile.TemporaryDirectory(prefix="policylens-contract-") as directory:
        app = create_app(
            Path(directory),
            "contract-generation-token",
            protector=AesTestProtector(b"C" * 32),
            testing=True,
        )
        rendered = (
            json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        app.state.service.shutdown()
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != rendered:
            print("OpenAPI contract drift detected", file=sys.stderr)
            return 1
        return 0
    target.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
