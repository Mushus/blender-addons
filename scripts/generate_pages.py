from __future__ import annotations

import json
import os
import urllib.request
from html import escape
from pathlib import Path


def get_json(url: str):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def render_page(latest: dict, *, japanese: bool) -> str:
    if japanese:
        language = "ja"
        title = "Blenderアドオンツール"
        description = "各ツールは個別にインストールでき、目的別にBlenderのUI内でグループ化されています。"
        group_heading = "グループ"
        tool_heading = "ツール"
        version_heading = "バージョン"
        target_heading = "対応Blender"
        download_label = "ZIPをダウンロード"
        language_link = '<a href="../">English</a>'
    else:
        language = "en"
        title = "Blender Add-on Tools"
        description = "Each tool is independently installable and grouped in Blender by purpose."
        group_heading = "Group"
        tool_heading = "Tool"
        version_heading = "Version"
        target_heading = "Target"
        download_label = "Download ZIP"
        language_link = '<a href="ja/">日本語</a>'

    rows = []
    for package_id in sorted(latest):
        item = latest[package_id]
        group_label = escape(str(item["group_label"]))
        safe_package_id = escape(package_id)
        version = escape(str(item["version"]))
        blender_target = escape(str(item["blender_target"]))
        url = escape(str(item.get("url") or "#"), quote=True)
        rows.append(
            f'<tr><td>{group_label}</td><td>{safe_package_id}</td><td>{version}</td>'
            f'<td>Blender {blender_target}</td><td><a href="{url}">{download_label}</a></td></tr>'
        )

    return (
        f'<!doctype html><html lang="{language}"><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title>"
        '<style>body{font-family:system-ui;max-width:1000px;margin:40px auto;padding:0 20px}'
        'nav{text-align:right;margin-bottom:20px}table{border-collapse:collapse;width:100%}'
        'td,th{border-bottom:1px solid #ddd;padding:10px;text-align:left}</style>'
        f"<nav>{language_link}</nav><h1>{title}</h1><p>{description}</p>"
        f"<table><thead><tr><th>{group_heading}</th><th>{tool_heading}</th><th>{version_heading}</th>"
        f"<th>{target_heading}</th><th></th></tr></thead><tbody>{''.join(rows)}</tbody></table></html>"
    )


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    releases = get_json(f"https://api.github.com/repos/{repository}/releases?per_page=100")
    latest = {}
    suite = None
    for release in releases:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            if asset["name"] == "release-manifest.json":
                manifest = get_json(asset["browser_download_url"])
                if manifest.get("suite", {}).get("file"):
                    suite = {
                        "version": manifest.get("generated_at", ""),
                        "url": next((item["browser_download_url"] for item in release["assets"] if item["name"] == manifest["suite"]["file"]), None),
                    }
                for package in manifest.get("packages", []):
                    if package.get("file") and package["id"] not in latest:
                        asset_url = next((item["browser_download_url"] for item in release["assets"] if item["name"] == package["file"]), None)
                        latest[package["id"]] = {**package, "url": asset_url}
                break

    output = Path("site/_generated")
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(render_page(latest, japanese=False), encoding="utf-8")
    japanese_output = output / "ja"
    japanese_output.mkdir(parents=True, exist_ok=True)
    (japanese_output / "index.html").write_text(render_page(latest, japanese=True), encoding="utf-8")
    (output / "packages.json").write_text(json.dumps({"packages": list(latest.values()), "suite": suite}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
