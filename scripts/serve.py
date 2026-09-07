from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "apps" / "web"
WEB_INDEX = WEB_DIR / "dist" / "index.html"
SERVICE_SRC = ROOT / "services" / "research-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

import uvicorn
from policylens_api.app import create_app


def frontend_inputs() -> list[Path]:
    inputs = [
        ROOT / "package.json",
        ROOT / "pnpm-lock.yaml",
        WEB_DIR / "index.html",
        WEB_DIR / "package.json",
        WEB_DIR / "tsconfig.json",
        WEB_DIR / "vite.config.ts",
    ]
    inputs.extend(path for path in (WEB_DIR / "src").rglob("*") if path.is_file())
    return [path for path in inputs if path.exists()]


def ensure_frontend_build() -> None:
    latest_source = max(
        (path.stat().st_mtime_ns for path in frontend_inputs()), default=0
    )
    built_at = WEB_INDEX.stat().st_mtime_ns if WEB_INDEX.exists() else 0
    if built_at >= latest_source:
        return
    if not (ROOT / "node_modules").exists():
        raise SystemExit("前端依赖尚未安装，请先在项目根目录运行 corepack pnpm install")
    corepack = shutil.which("corepack.cmd") or shutil.which("corepack")
    if corepack is None:
        raise SystemExit("检测到网页资源需要构建，但未找到 Corepack")
    print("检测到 PolicyLens 网页资源已更新，正在生成本地页面…", flush=True)
    try:
        subprocess.run(
            [corepack, "pnpm", "--filter", "@policylens/web", "build"],
            cwd=ROOT,
            check=True,
            shell=False,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"PolicyLens 网页构建失败（退出码 {exc.returncode}）") from exc
    if not WEB_INDEX.exists():
        raise SystemExit("网页构建结束，但未生成 apps/web/dist/index.html")


def default_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise SystemExit("未找到 LOCALAPPDATA，无法确定 PolicyLens 私有数据目录")
    return Path(local_app_data) / "PolicyLens" / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 PolicyLens localhost 浏览器服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--manager", default=os.environ.get("POLICYLENS_MANAGER", "manual")
    )
    parser.add_argument("--log-level", default="warning")
    parser.add_argument("--skip-frontend-build", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("PolicyLens 只允许监听 127.0.0.1 或 localhost")
    if not 1 <= args.port <= 65535:
        parser.error("端口必须位于 1 到 65535")
    if not args.skip_frontend_build:
        ensure_frontend_build()
    data_dir = (args.data_dir or default_data_dir()).resolve()
    app = create_app(
        data_dir,
        browser_mode=True,
        static_dir=WEB_DIR / "dist",
        bound_port=args.port,
        manager=args.manager,
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level=args.log_level,
        server_header=False,
    )


if __name__ == "__main__":
    main()
