#!/usr/bin/env python
"""Collect and rename build outputs into a single top-level build directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROLE_BY_PROJECT = {
    "stm32f103xb_custom_f103rb_if": "interface",
    "stm32f103xb_custom_bl": "bootloader",
}

SOURCE_SUFFIXES = (
    ".elf",
    ".hex",
    ".bin",
    "_crc.hex",
    "_crc.bin",
    "_crc.txt",
)


def export_project(project: str, out_dir: Path, toolchain: str) -> int:
    if project not in ROLE_BY_PROJECT:
        known = ", ".join(sorted(ROLE_BY_PROJECT))
        raise ValueError("Unknown project '%s'. Known projects: %s" % (project, known))

    role = ROLE_BY_PROJECT[project]
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    project_build_dir = repo_root / "projectfiles" / toolchain / project / "build"

    if not project_build_dir.exists():
        raise FileNotFoundError("Build directory does not exist: %s" % project_build_dir)

    role_output_dir = out_dir / role
    role_output_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for suffix in SOURCE_SUFFIXES:
        source_file = project_build_dir / (project + suffix)
        if not source_file.exists():
            continue

        dest_name = role + suffix
        shutil.copy2(source_file, role_output_dir / dest_name)
        copied += 1

    if copied == 0:
        raise FileNotFoundError("No artifacts found for %s in %s" % (project, project_build_dir))

    print("[%s] exported %d file(s) -> %s" % (role, copied, role_output_dir))
    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export DAPLink build outputs to a clear interface/bootloader layout."
    )
    parser.add_argument(
        "--target-project",
        required=True,
        choices=sorted(ROLE_BY_PROJECT),
        help="Source project to export.",
    )
    parser.add_argument(
        "--out-dir",
        default="build",
        help="Output folder for final artifacts (default: build).",
    )
    parser.add_argument(
        "--toolchain",
        default="make_gcc_arm",
        help="Toolchain output folder under projectfiles (default: make_gcc_arm).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir

    export_project(args.target_project, out_dir, args.toolchain)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

