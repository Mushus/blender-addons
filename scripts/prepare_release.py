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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extension_manifest import (  # noqa: E402
    build_manifest_dict,
    index_entry_from_manifest,
    package_website,
    parse_bl_info,
    sha256_file,
)


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


def force_push_tag(tag_name: str, target_sha: str) -> None:
    """Move tag to target_sha and force-push to origin (CI recovery path)."""
    run_command(["git", "tag", "-f", tag_name, target_sha])
    run_command(["git", "push", "--force", "origin", f"refs/tags/{tag_name}"])
    print(f"Force-pushed tag {tag_name} -> {target_sha}")


def _tag_number(tag: str, base: str) -> int | None:
    if tag == base:
        return 0
    if tag.startswith(base + "."):
        suffix = tag[len(base) + 1 :]
        if suffix.isdigit():
            return int(suffix)
    return None


def _list_today_tags(base: str) -> list[str]:
    try:
        output = run_command(["git", "tag", "--list", f"{base}*"])
    except subprocess.CalledProcessError:
        return []
    tags = [line.strip() for line in output.splitlines() if line.strip()]
    return [t for t in tags if _tag_number(t, base) is not None]


def _query_is_draft(tag: str, gh_bin: str, env: dict[str, str]) -> str | None:
    res = subprocess.run(
        [gh_bin, "release", "view", tag, "--json", "isDraft", "--jq", ".isDraft"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if res.returncode == 0:
        return res.stdout.strip()
    return None


def _resolve_auto_tag(
    today: str,
    gh_bin: str | None,
    env: dict[str, str] | None,
    is_regenerate: bool,
    no_draft: bool,
) -> str:
    base = f"release-{today}"
    today_tags = _list_today_tags(base)
    if not today_tags:
        return base
    today_tags_sorted = sorted(today_tags, key=lambda t: _tag_number(t, base) or 0)
    latest = today_tags_sorted[-1]
    if is_regenerate:
        return latest
    if no_draft or gh_bin is None or env is None:
        num = _tag_number(latest, base)
        assert num is not None
        return f"{base}.{num + 1}"
    is_draft = _query_is_draft(latest, gh_bin, env)
    if is_draft == "true":
        return latest
    if is_draft == "false":
        num = _tag_number(latest, base)
        assert num is not None
        return f"{base}.{num + 1}"
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare draft release assets and upload to GitHub.")
    parser.add_argument("--no-draft", action="store_true", help="Skip GitHub release draft creation/upload.")
    parser.add_argument(
        "--tag-name", default="", help="Tag name for release (default: release-YYYY.MM.DD, auto .N for same-day repeats)."
    )
    parser.add_argument("--blender-target", default="", help="Blender target version suffix.")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Delete the target release (latest for today if no --tag-name), force-push the tag to HEAD, and recreate a draft.",
    )
    args = parser.parse_args()

    catalog_path = PROJECT_ROOT / "release" / "packages.json"
    with catalog_path.open("r", encoding="utf-8") as f:
        catalog = json.load(f)
    extension_defaults = catalog.get("extension_defaults") or {}
    if not isinstance(extension_defaults, dict):
        raise SystemExit("release/packages.json extension_defaults must be an object")

    blender_target = args.blender_target
    if not blender_target:
        target_path = PROJECT_ROOT / "release" / "blender-target.txt"
        blender_target = target_path.read_text(encoding="utf-8").strip()

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y.%m.%d")
    if args.tag_name:
        tag_name = args.tag_name
    else:
        gh_bin_early = shutil.which("gh") if not args.no_draft else None
        env_early: dict[str, str] | None = None
        if gh_bin_early is not None:
            env_early = os.environ.copy()
            env_early["GH_PROMPT_DISABLED"] = "true"
        tag_name = _resolve_auto_tag(today, gh_bin_early, env_early, args.regenerate, args.no_draft)

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
            "scripts/extension_manifest.py",
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

    # Regenerating a same-day release must rebuild everything so Docs republish
    # still works even when only CI/workflow files changed.
    if args.regenerate:
        changed_ids = list(all_ids)
        suite_changed = True
    elif not changed_ids and not suite_changed:
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
        extension_listing = None
        if is_changed:
            source_zip = dist_dir / f"{package['id']}.zip"
            filename = f"{package['id']}-{version}-blender{blender_target}.zip"
            dest_zip = release_dir / filename
            shutil.copy(source_zip, dest_zip)
            archive_size, archive_hash = sha256_file(dest_zip)
            extension_meta = package.get("extension")
            if not isinstance(extension_meta, dict):
                raise SystemExit(f"{package['id']}: missing extension metadata in release/packages.json")
            bl_info = parse_bl_info(PROJECT_ROOT / package["source"] / "__init__.py")
            manifest = build_manifest_dict(
                package_id=package["id"],
                bl_info=bl_info,
                extension_meta=extension_meta,
                defaults=extension_defaults,
                website=package_website(package["id"]),
            )
            extension_listing = index_entry_from_manifest(
                manifest,
                archive_url="",  # filled by the docs site from the Release asset URL
                archive_size=archive_size,
                archive_hash=archive_hash,
            )
            del extension_listing["archive_url"]

        entry = {
            "id": package["id"],
            "version": version,
            "group_id": package.get("group_id"),
            "group_label": package.get("group_label"),
            "blender_target": blender_target,
            "changed": is_changed,
            "file": filename,
        }
        if extension_listing is not None:
            entry["extension"] = extension_listing
        manifest_packages.append(entry)

    suite_file = None
    if suite_changed:
        tag_suffix = tag_name.removeprefix("release-")
        suite_file = f"blender_addon_suite-{tag_suffix}-blender{blender_target}.zip"
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
        tag_suffix = tag_name.removeprefix("release-")
        body_lines.append(f"- blender_addon_suite ({tag_suffix})")
    for item in manifest_packages:
        if item["changed"]:
            body_lines.append(f"- {item['id']} {item['version']}")
    body_lines.extend(
        [
            "",
            "## Included Downloads",
            "",
            "- GitHub Pages hosts the download list and the Extensions repository index:",
            "- https://mushus.github.io/blender-addons/index.json",
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

        existing_is_draft = _query_is_draft(tag_name, gh_bin, env)

        release_target = run_command(["git", "rev-parse", "HEAD"])
        assets = [str(p) for p in release_dir.iterdir() if p.is_file()]

        if args.regenerate:
            # Drop the GitHub Release object, then force-move the git tag to HEAD
            # so a later publish runs workflow YAML from the retargeted commit.
            if existing_is_draft is not None:
                print(f"Regenerating: deleting existing release {tag_name}")
                subprocess.run(
                    [gh_bin, "release", "delete", tag_name, "--yes"],
                    cwd=PROJECT_ROOT,
                    check=True,
                    env=env,
                )
            print(f"Regenerating: force-pushing tag {tag_name} -> {release_target}")
            force_push_tag(tag_name, release_target)
            subprocess.run(
                [
                    gh_bin,
                    "release",
                    "create",
                    tag_name,
                    "--draft",
                    "--target",
                    release_target,
                    "--title",
                    tag_name,
                    "--notes-file",
                    str(body_path),
                    *assets,
                ],
                cwd=PROJECT_ROOT,
                check=True,
                env=env,
            )
        elif existing_is_draft == "true":
            subprocess.run([gh_bin, "release", "upload", tag_name, *assets, "--clobber"], cwd=PROJECT_ROOT, check=True, env=env)
            subprocess.run([gh_bin, "release", "edit", tag_name, "--title", tag_name, "--notes-file", str(body_path)], cwd=PROJECT_ROOT, check=True, env=env)
        else:
            subprocess.run(
                [
                    gh_bin,
                    "release",
                    "create",
                    tag_name,
                    "--draft",
                    "--target",
                    release_target,
                    "--title",
                    tag_name,
                    "--notes-file",
                    str(body_path),
                    *assets,
                ],
                cwd=PROJECT_ROOT,
                check=True,
                env=env,
            )

    print(f"Release assets: {release_dir}")


if __name__ == "__main__":
    main()
