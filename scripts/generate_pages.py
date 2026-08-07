from __future__ import annotations

import ast
import json
import os
import urllib.request
from pathlib import Path


def get_json(url: str):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def parse_bl_info(init_path: Path) -> dict:
    """addons/<package_id>/__init__.py から bl_info を解析するフォールバック関数"""
    content = init_path.read_text(encoding="utf-8")
    parsed = ast.parse(content)
    bl_info = {}
    for node in parsed.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "bl_info" and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values, strict=True):
                        if isinstance(k, ast.Constant):
                            val = ast.literal_eval(v)
                            bl_info[k.value] = val
    return bl_info


def get_local_fallback_packages(repo_url: str) -> tuple[dict[str, dict], dict | None]:
    """ローカルのアドオンからパッケージ情報を生成するフォールバック"""
    addons_dir = Path(__file__).resolve().parent.parent / "addons"
    latest = {}
    if addons_dir.exists():
        for item in sorted(addons_dir.iterdir()):
            init_file = item / "__init__.py"
            if item.is_dir() and init_file.exists():
                bl_info = parse_bl_info(init_file)
                pkg_id = item.name
                version_str = ".".join(map(str, bl_info.get("version", (1, 0, 0))))
                blender_str = ".".join(map(str, bl_info.get("blender", (4, 0, 0))))
                name = bl_info.get("name", pkg_id)
                latest[pkg_id] = {
                    "id": pkg_id,
                    "name": name,
                    "group_label": bl_info.get("category", "General"),
                    "version": version_str,
                    "blender_target": blender_str,
                    "url": None,
                    "doc_link": f"/addons/{pkg_id.replace('_', '-')}/",
                }
    return latest, None


def get_package_ids() -> set[str]:
    packages_path = Path(__file__).resolve().parent.parent / "release" / "packages.json"
    packages = json.loads(packages_path.read_text(encoding="utf-8"))
    return {package["id"] for package in packages["packages"]}


def main():
    repository = os.environ.get("GITHUB_REPOSITORY", "Mushus/blender-addons")
    repo_url = f"https://github.com/{repository}"
    package_ids = get_package_ids()
    latest = {}
    suite = None

    try:
        releases = get_json(f"https://api.github.com/repos/{repository}/releases?per_page=100")
        for release in releases:
            if release.get("draft"):
                continue
            for asset in release.get("assets", []):
                if asset["name"] == "release-manifest.json":
                    manifest = get_json(asset["browser_download_url"])
                    if manifest.get("suite", {}).get("file") and not suite:
                        suite = {
                            "version": manifest.get("generated_at", ""),
                            "url": next(
                                (item["browser_download_url"] for item in release["assets"] if item["name"] == manifest["suite"]["file"]), None
                            ),
                        }
                    for package in manifest.get("packages", []):
                        if package["id"] in package_ids and package.get("file") and package["id"] not in latest:
                            asset_url = next(
                                (item["browser_download_url"] for item in release["assets"] if item["name"] == package["file"]), None
                            )
                            latest[package["id"]] = {
                                **package,
                                "url": asset_url,
                                "doc_link": f"/addons/{package['id'].replace('_', '-')}/",
                            }
                    break
    except Exception as e:
        print(f"Warning: Failed to fetch GitHub Releases: {e}. Falling back to local addons data.")

    if not latest:
        latest, suite = get_local_fallback_packages(repo_url)

    latest = {package_id: package for package_id, package in latest.items() if package_id in package_ids}

    data = {
        "packages": list(latest.values()),
        "suite": suite,
    }

    root_dir = Path(__file__).resolve().parent.parent
    targets = [
        root_dir / "site" / "src" / "data" / "packages.json",
        root_dir / "site" / "public" / "packages.json",
        root_dir / "site" / "_generated" / "packages.json",
    ]

    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Generated {target}")


if __name__ == "__main__":
    main()
