import argparse
import os
import pathlib
import re
import urllib.request
import zipfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and extract Blender for Windows.")
    parser.add_argument("--version", required=True, help="Blender major/minor version (e.g. 5.2).")
    parser.add_argument(
        "--install-root",
        default=str(PROJECT_ROOT / ".blender-cache"),
        help="Installation root directory.",
    )
    args = parser.parse_args()

    install_root = pathlib.Path(args.install_root).resolve()
    install_root.mkdir(parents=True, exist_ok=True)

    release_dir = f"Blender{args.version}"
    url = f"https://download.blender.org/release/{release_dir}/"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")

    escaped_version = re.escape(args.version)
    pattern = rf"blender-{escaped_version}\.\d+-windows-x64\.zip"
    matches = sorted(list(set(re.findall(pattern, html))))

    if not matches:
        raise RuntimeError(f"No Blender build found for version {args.version}")

    def parse_ver(filename: str) -> tuple[int, ...]:
        m = re.search(rf"blender-({escaped_version}\.\d+)-windows-x64\.zip", filename)
        if m:
            return tuple(int(x) for x in m.group(1).split("."))
        return (0, 0, 0)

    download_name = sorted(matches, key=parse_ver)[-1]
    zip_url = f"{url}{download_name}"
    zip_path = install_root / download_name

    if not zip_path.exists():
        print(f"Downloading Blender from {zip_url} ...")
        urllib.request.urlretrieve(zip_url, zip_path)

    extract_folder_name = zip_path.stem  # Remove .zip extension
    extract_path = install_root / extract_folder_name

    if not extract_path.exists():
        print(f"Extracting {zip_path} to {install_root} ...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(install_root)

    blender_exe = None
    for p in extract_path.rglob("blender.exe"):
        blender_exe = p
        break

    if not blender_exe:
        raise RuntimeError("blender.exe was not found after extraction")

    print(f"Blender installed at: {blender_exe}")

    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        bin_dir = str(blender_exe.parent)
        with open(github_path, "a", encoding="utf-8") as f:
            f.write(bin_dir + "\n")
        print(f"Added {bin_dir} to GITHUB_PATH")


if __name__ == "__main__":
    main()
