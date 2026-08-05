import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def run_command(cmd: list[str], cwd: pathlib.Path = PROJECT_ROOT, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check)
    return result.stdout.strip()


def get_previous_tag(tag_name: str) -> str:
    try:
        output = run_command(["git", "tag", "--sort=-creatordate"])
        tags = [line.strip() for line in output.splitlines() if line.strip()]
        for tag in tags:
            if tag != tag_name:
                return tag
    except subprocess.CalledProcessError:
        pass
    return ""


def get_changed_files(previous_tag: str) -> list[str]:
    changed_files = set()
    if previous_tag:
        try:
            output = run_command(["git", "diff", "--name-only", f"{previous_tag}..HEAD"])
            for line in output.splitlines():
                if line.strip():
                    changed_files.add(line.strip().replace("\\", "/"))
        except subprocess.CalledProcessError:
            pass

    try:
        output = run_command(["git", "status", "--porcelain=v1"])
        for line in output.splitlines():
            if len(line) > 3:
                filepath = line[3:].strip().strip('"').replace("\\", "/")
                changed_files.add(filepath)
    except subprocess.CalledProcessError:
        pass

    return sorted(list(changed_files))


def parse_package_version(source_dir: str) -> str:
    init_path = PROJECT_ROOT / source_dir / "__init__.py"
    if not init_path.exists():
        raise FileNotFoundError(f"__init__.py not found at {init_path}")

    content = init_path.read_text(encoding="utf-8")
    match = re.search(r'"version"\s*:\s*\(([^)]*)\)', content)
    if not match:
        raise ValueError(f"Version not found in {init_path}")

    parts = [int(p.strip()) for p in match.group(1).split(",") if p.strip()]
    return f"{parts[0]:04d}.{parts[1]:02d}.{parts[2]:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare draft release assets and upload to GitHub.")
    parser.add_argument("--no-draft", action="store_true", help="Skip GitHub release draft creation/upload.")
    parser.add_argument("--tag-name", default="", help="Tag name for release (default: release-YYYY.MM.DD).")
    parser.add_argument("--blender-target", default="", help="Blender target version suffix.")
    args = parser.parse_args()

    catalog_path = PROJECT_ROOT / "release" / "packages.json"
    with catalog_path.open("r", encoding="utf-8") as f:
        catalog = json.load(f)

    blender_target = args.blender_target
    if not blender_target:
        target_path = PROJECT_ROOT / "release" / "blender-target.txt"
        blender_target = target_path.read_text(encoding="utf-8").strip()

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y.%m.%d")
    tag_name = args.tag_name if args.tag_name else f"release-{today}"

    previous_tag = get_previous_tag(tag_name)
    changed_files = get_changed_files(previous_tag)

    stable_packages = [p for p in catalog.get("packages", []) if p.get("status") == "stable"]
    all_ids = [p["id"] for p in stable_packages]

    changed_ids = []
    if not previous_tag:
        changed_ids = list(all_ids)
    else:
        for package in stable_packages:
            source = package["source"]
            if any(f.startswith(f"{source}/") for f in changed_files):
                changed_ids.append(package["id"])

        suite_trigger_patterns = [
            "addons/*/embedded_host/*",
            "scripts/make_zip.py",
            "scripts/prepare_release.py",
            "release/packages.json",
            "release/blender-target.txt",
        ]
        import fnmatch

        for f in changed_files:
            if any(fnmatch.fnmatch(f, pat) for pat in suite_trigger_patterns):
                changed_ids = list(all_ids)
                break

    suite_changed = (len(changed_ids) > 0) or any(
        f == "__init__.py" or f.startswith("scripts/") for f in changed_files
    )

    if not changed_ids and not suite_changed:
        print("No releasable package changes detected.")
        sys.exit(0)

    # Call make_zip.py
    make_zip_cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "make_zip.py")]
    for pkg_id in changed_ids:
        make_zip_cmd.extend(["--package-id", pkg_id])
    for pkg_id in all_ids:
        make_zip_cmd.extend(["--suite-package-id", pkg_id])
    if not suite_changed:
        make_zip_cmd.append("--skip-suite")

    subprocess.run(make_zip_cmd, cwd=PROJECT_ROOT, check=True)

    dist_dir = PROJECT_ROOT / "dist"
    release_dir = dist_dir / "release"
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    manifest_packages = []
    for package in stable_packages:
        version = parse_package_version(package["source"])
        is_changed = package["id"] in changed_ids
        filename = None
        if is_changed:
            source_zip = dist_dir / f"{package['id']}.zip"
            filename = f"{package['id']}-{version}-blender{blender_target}.zip"
            shutil.copy(source_zip, release_dir / filename)

        manifest_packages.append(
            {
                "id": package["id"],
                "version": version,
                "group_id": package.get("group_id"),
                "group_label": package.get("group_label"),
                "blender_target": blender_target,
                "changed": is_changed,
                "file": filename,
            }
        )

    suite_file = None
    if suite_changed:
        suite_file = f"blender_addon_suite-{today}-blender{blender_target}.zip"
        shutil.copy(dist_dir / "blender_addon_suite.zip", release_dir / suite_file)

    manifest = {
        "release": tag_name,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "blender_target": blender_target,
        "suite": {"changed": suite_changed, "file": suite_file},
        "packages": manifest_packages,
    }

    manifest_path = release_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    body_lines = ["## Changed", ""]
    if suite_changed:
        body_lines.append(f"- blender_addon_suite ({today})")
    for item in manifest_packages:
        if item["changed"]:
            body_lines.append(f"- {item['id']} {item['version']}")
    body_lines.extend(
        [
            "",
            "## Included Downloads",
            "",
            "- GitHub Pages contains the current download index.",
            "",
            "## Compared With",
            "",
            f"- {previous_tag}" if previous_tag else "- No previous release tag found",
        ]
    )

    body_path = release_dir / "release-body.md"
    body_path.write_text("\n".join(body_lines), encoding="utf-8")

    if not args.no_draft:
        gh_bin = shutil.which("gh")
        if not gh_bin:
            raise RuntimeError(f"GitHub CLI 'gh' is required to create a Draft Release. Assets are in {release_dir}.")

        env = os.environ.copy()
        env["GH_PROMPT_DISABLED"] = "true"

        res = subprocess.run(
            [gh_bin, "release", "view", tag_name, "--json", "isDraft", "--jq", ".isDraft"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        existing_is_draft = res.stdout.strip() if res.returncode == 0 else None

        if existing_is_draft == "false":
            print("Today's release is already published; deferring additional changes to the next day.")
            sys.exit(0)

        assets = [str(p) for p in release_dir.iterdir() if p.is_file()]

        if existing_is_draft == "true":
            subprocess.run([gh_bin, "release", "upload", tag_name, *assets, "--clobber"], cwd=PROJECT_ROOT, check=True, env=env)
            subprocess.run([gh_bin, "release", "edit", tag_name, "--title", tag_name, "--notes-file", str(body_path)], cwd=PROJECT_ROOT, check=True, env=env)
        else:
            subprocess.run([gh_bin, "release", "create", tag_name, "--draft", "--title", tag_name, "--notes-file", str(body_path), *assets], cwd=PROJECT_ROOT, check=True, env=env)

    print(f"Release assets: {release_dir}")


if __name__ == "__main__":
    main()
