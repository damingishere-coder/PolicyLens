from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "reports" / "dependency-licenses.json"
PYTHON_DIRECT = {
    canonicalize_name(name): purpose
    for name, purpose in {
        "alembic": "数据库迁移",
        "argon2-cffi": "恢复密码 KDF",
        "cryptography": "AES-256-GCM 加密",
        "fastapi": "本地 API",
        "httpx": "官方公开网页与 PDF 的受限 HTTPS 抓取",
        "pydantic": "严格请求与响应契约",
        "pypdf": "文本型 PDF 提取",
        "python-multipart": "本地 PDF 表单解析",
        "sqlalchemy": "SQLite 数据访问",
        "uvicorn": "RunDock 托管的回环 Web 服务",
    }.items()
}
NODE_ENTRYPOINTS = {
    "@policylens/contracts": "内部 API 与 AI 契约",
    "@policylens/ui": "内部 UI 基础组件",
    "lucide-react": "界面图标",
    "react": "界面运行时",
    "react-dom": "界面渲染",
}
FORBIDDEN_LICENSE_MARKERS = ("AGPL", "GPL-", "LGPL", "SSPL", "BUSL", "PROPRIETARY")


def python_components() -> list[dict[str, object]]:
    queue = list(PYTHON_DIRECT)
    seen: set[str] = set()
    components: list[dict[str, object]] = []
    while queue:
        requested = queue.pop(0)
        canonical = canonicalize_name(requested)
        if canonical in seen:
            continue
        seen.add(canonical)
        try:
            package = distribution(requested)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"缺少 Python 依赖：{requested}") from exc
        name = package.metadata.get("Name", requested)
        license_name = package.metadata.get(
            "License-Expression"
        ) or package.metadata.get("License")
        components.append(
            {
                "ecosystem": "PyPI",
                "name": name,
                "version": package.version,
                "license": (license_name or "UNKNOWN").strip(),
                "direct": canonical in PYTHON_DIRECT,
                "purpose": PYTHON_DIRECT.get(canonical, "传递运行时依赖"),
                "source": package.metadata.get("Home-page")
                or package.metadata.get("Project-URL"),
            }
        )
        for raw in package.requires or []:
            requirement = Requirement(raw)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            queue.append(requirement.name)
    return components


def find_node_package(name: str, from_directory: Path) -> Path:
    current = from_directory
    while current != current.parent:
        candidate = current / "node_modules" / Path(*name.split("/")) / "package.json"
        if candidate.exists():
            return candidate.resolve()
        current = current.parent
    raise RuntimeError(f"缺少 Node 依赖：{name}")


def node_components() -> list[dict[str, object]]:
    web = ROOT / "apps" / "web"
    queue = [(name, web) for name in NODE_ENTRYPOINTS]
    seen: set[tuple[str, str]] = set()
    components: list[dict[str, object]] = []
    while queue:
        requested, from_directory = queue.pop(0)
        manifest_path = find_node_package(requested, from_directory)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = str(manifest.get("name", requested))
        version = str(manifest.get("version", "0.0.0"))
        identity = (name, version)
        if identity in seen:
            continue
        seen.add(identity)
        internal = name.startswith("@policylens/")
        license_value = manifest.get(
            "license", "INTERNAL-NOT-LICENSED" if internal else "UNKNOWN"
        )
        if isinstance(license_value, dict):
            license_value = license_value.get("type", "UNKNOWN")
        repository = manifest.get("repository")
        if isinstance(repository, dict):
            repository = repository.get("url")
        components.append(
            {
                "ecosystem": "npm",
                "name": name,
                "version": version,
                "license": str(license_value),
                "direct": name in NODE_ENTRYPOINTS,
                "purpose": NODE_ENTRYPOINTS.get(name, "传递运行时依赖"),
                "source": manifest.get("homepage") or repository,
            }
        )
        package_directory = manifest_path.parent
        for dependency in {
            **manifest.get("dependencies", {}),
            **manifest.get("optionalDependencies", {}),
        }:
            if dependency.startswith("@policylens/") or not internal:
                queue.append((dependency, package_directory))
    return components


def validate(components: list[dict[str, object]]) -> None:
    failures: list[str] = []
    for component in components:
        name = str(component["name"])
        license_name = str(component["license"]).upper()
        if license_name == "UNKNOWN" or any(
            marker in license_name for marker in FORBIDDEN_LICENSE_MARKERS
        ):
            failures.append(f"{name}: {component['license']}")
    if failures:
        raise RuntimeError("依赖许可证门槛失败：" + ", ".join(failures))


def main() -> int:
    components = sorted(
        python_components() + node_components(),
        key=lambda item: (
            str(item["ecosystem"]),
            str(item["name"]).lower(),
            str(item["version"]),
        ),
    )
    validate(components)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "format": "PolicyLens dependency license report v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "component_count": len(components),
        "components": components,
    }
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Dependency license scan passed for {len(components)} runtime components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
