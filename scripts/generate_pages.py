from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


def get_json(url: str):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


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
    rows = []
    for package_id in sorted(latest):
        item = latest[package_id]
        rows.append(f'<tr><td>{item["group_label"]}</td><td>{package_id}</td><td>{item["version"]}</td><td>Blender {item["blender_target"]}</td><td><a href="{item["url"]}">Download ZIP</a></td></tr>')
    html = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Blender Add-on Tools</title><style>body{font-family:system-ui;max-width:1000px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:10px;text-align:left}</style><h1>Blender Add-on Tools</h1><p>Each tool is independently installable and grouped in Blender by purpose.</p><table><thead><tr><th>Group</th><th>Tool</th><th>Version</th><th>Target</th><th></th></tr></thead><tbody>""" + "".join(rows) + "</tbody></table></html>"
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "packages.json").write_text(json.dumps({"packages": list(latest.values()), "suite": suite}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

