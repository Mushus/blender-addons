import argparse
import pathlib
import subprocess
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Blender commands or tests inside a Docker container.")
    parser.add_argument("--image", default="blender-addon-tools:blender-5.1.2", help="Docker image tag.")
    parser.add_argument("--build", action="store_true", help="Build the Docker image before running.")
    parser.add_argument("--exec", action="store_true", help="Run the command directly inside the container without 'blender' prefix.")
    parser.add_argument("container_args", nargs=argparse.REMAINDER, help="Arguments passed to container execution.")

    args = parser.parse_args()

    if args.build:
        build_cmd = [
            "docker", "build",
            "--build-arg", "BLENDER_MAJOR=5.1",
            "--build-arg", "BLENDER_VERSION=5.1.2",
            "--tag", args.image,
            str(PROJECT_ROOT)
        ]
        res = subprocess.run(build_cmd, cwd=PROJECT_ROOT)
        if res.returncode != 0:
            sys.exit(res.returncode)

    # Clean up container args (strip leading '--' if present from REMAINDER)
    cmd_args = args.container_args
    if cmd_args and cmd_args[0] == "--":
        cmd_args = cmd_args[1:]

    run_cmd = [
        "docker", "run", "--rm",
        "--volume", f"{PROJECT_ROOT}:/workspace",
        "--workdir", "/workspace",
        args.image
    ]

    if not args.exec:
        run_cmd.append("blender")

    run_cmd.extend(cmd_args)

    res = subprocess.run(run_cmd, cwd=PROJECT_ROOT)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
