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


def list_local_tags_set() -> set[str]:
    try:
        output = run_command(["git", "tag", "--list"])
        return {line.strip() for line in output.splitlines() if line.strip()}
    except subprocess.CalledProcessError:
        return set()


def get_release_is_draft(tag_name: str, gh_bin: str, env: dict) -> str | None:
    """Return 'true'/'false' if GitHub Release exists, else None."""
    res = subprocess.run(
        [gh_bin, "release", "view", tag_name, "--json", "isDraft", "--jq", ".isDraft"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if res.returncode == 0:
        val = res.stdout.strip()
        if val in ("true", "false"):
            return val
    return None


def resolve_tag_name(
    today: str,
    explicit_tag: str,
    is_regenerate: bool,
    gh_bin: str | None,
    env: dict | None,
) -> str:
    """Resolve next release tag allowing multiple releases per day.

    Scheme: first release of the day is ``release-YYYY.MM.DD``,
    subsequent ones are ``release-YYYY.MM.DD-2``, ``-3`` ...
    - If ``explicit_tag`` is given, return it verbatim.
    - If ``is_regenerate``, return the latest existing tag for today
      (so ``--regenerate`` recreates the most recent one, not a new suffix).
    - Otherwise return the first free tag, reusing a Draft tag if present.
    """
    if explicit_tag:
        return explicit_tag

    base = f"release-{today}"
    local_tags = list_local_tags_set()

    if is_regenerate:
        candidates = [t for t in local_tags if t == base or t.startswith(base + "-")]
        if not candidates:
            if gh_bin and env is not None and get_release_is_draft(base, gh_bin, env) is not None:
                return base
            return base

        def suffix_key(t: str) -> int:
            if t == base:
                return 1
            suffix = t[len(base) + 1 :]
            try:
                return int(suffix)
            except ValueError:
                return 0

        return max(candidates, key=suffix_key)

    candidate = base
    n = 1
    while True:
        exists_local = candidate in local_tags
        exists_remote = False
        draft: str | None = None
        if gh_bin and env is not None:
            draft = get_release_is_draft(candidate, gh_bin, env)
            exists_remote = draft is not None
        exists = exists_local or exists_remote

        if not exists:
            return candidate

        if draft == "true":
            return candidate
        if gh_bin is not None and draft is None and exists_local and not exists_remote:
            return candidate
        n += 1
        if n > 99:
            raise SystemExit(f"Too many releases for {today}, suffix overflow")
        candidate = f"{base}-{n}" if n > 1 else base


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare draft release assets and upload to GitHub.")
    parser.add_argument("--no-draft", action="store_true", help="Skip GitHub release draft creation/upload.")
    parser.add_argument("--tag-name", default="", help="Tag name for release (default: release-YYYY.MM.DD).")
    parser.add_argument("--blender-target", default="", help="Blender target version suffix.")
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Delete today's release, force-push the tag to HEAD, and recreate a draft (recovery path).",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from package_catalog import load_catalog  # noqa: E402

    catalog = load_catalog(PROJECT_ROOT)
    extension_defaults = catalog.get("extension_defaults") or {}
    if not isinstance(extension_defaults, dict):
        raise SystemExit("pyproject.toml [tool.blender-addons.extension_defaults] must be a table")

    blender_target = args.blender_target
    if not blender_target:
        blender_target = str(catalog.get("blender_target") or "4.2")

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y.%m.%d")
    gh_bin_early = None
    env_early: dict | None = None
    if not args.no_draft:
        gh_bin_early = shutil.which("gh")
        if gh_bin_early:
            env_early = os.environ.copy()
            env_early["GH_PROMPT_DISABLED"] = "true"
    tag_name = resolve_tag_name(today, args.tag_name, args.regenerate, gh_bin_early, env_early)
    if tag_name != (args.tag_name if args.tag_name else f"release-{today}"):
        print(f"Resolved tag: {tag_name} (base: release-{today})")

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
            "scaffold/embedded_host/*",
            "scripts/scaffold_bundle.py",
            "scripts/make_zip.py",
            "scripts/extension_manifest.py",
            "scripts/prepare_release.py",
            "scripts/package_catalog.py",
            "pyproject.toml",
            "addons/*/addon.json",
        ]
        import fnmatch

        for f in changed_files:
            if any(fnmatch.fnmatch(f, pat) for pat in suite_trigger_patterns):
                changed_ids = list(all_ids)
                break

    # Suite is always released; individual packages only when changed.
    # Regenerating a same-day release must rebuild everything so Docs republish
    # still works even when only CI/workflow files changed.
    if args.regenerate:
        changed_ids = list(all_ids)
    elif not changed_ids and not any(
        f == "__init__.py" or f.startswith("scripts/") for f in changed_files
    ):
        # No package changes and no root triggers -> nothing to release
        print("No releasable package changes detected.")
        sys.exit(0)
    suite_changed = True

    # Call make_zip.py — suite always included, packages only when changed
    make_zip_cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "make_zip.py")]
    for pkg_id in changed_ids:
        make_zip_cmd.extend(["--package-id", pkg_id])
    for pkg_id in all_ids:
        make_zip_cmd.extend(["--suite-package-id", pkg_id])

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
                raise SystemExit(f"{package['id']}: missing extension metadata in addon.json")
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

        existing_is_draft = get_release_is_draft(tag_name, gh_bin, env)

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
