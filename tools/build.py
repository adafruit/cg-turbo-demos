#!/usr/bin/env python3
"""Compile src/*.py to build/lib/*.mpy for the Fruit Jam, and optionally deploy.

    python3 tools/build.py            # compile only
    python3 tools/build.py --deploy   # compile, then copy lib/*.mpy, app/* and assets/*.bin to CIRCUITPY

The first deploy saves the board's existing code.py to backup/ before
replacing it. Source .py files are never copied to the board, so they can't
shadow the compiled .mpy modules.
"""

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MPY_CROSS = ROOT / "tools" / "mpy-cross"
ARCH = "armv7emsp"
SRC = ROOT / "src"
APP = ROOT / "app"
BUILD_LIB = ROOT / "build" / "lib"
ASSETS = ROOT / "assets"
BACKUP = ROOT / "backup"


def copy_if_changed(source, dest, label):
    """Copy unless dest already has the same bytes (skips slow rewrites and reloads)."""
    data = source.read_bytes()
    if dest.exists() and dest.stat().st_size == len(data) and dest.read_bytes() == data:
        return
    dest.write_bytes(data)
    print("copied", source.name, "->", label)


def compile_all():
    if not MPY_CROSS.exists():
        sys.exit(
            "tools/mpy-cross is missing. Download the macOS build matching your board's firmware\n"
            "(boot_out.txt) from https://adafruit-circuit-python.s3.amazonaws.com/index.html?prefix=bin/mpy-cross/\n"
            "and save it as tools/mpy-cross (chmod +x)."
        )
    BUILD_LIB.mkdir(parents=True, exist_ok=True)
    outputs = []
    for source in sorted(SRC.glob("*.py")):
        output = BUILD_LIB / (source.stem + ".mpy")
        subprocess.run(
            [str(MPY_CROSS), "-march=" + ARCH, "-s", source.name, "-o", str(output), str(source)],
            check=True,
        )
        if "@micropython.asm_thumb" in source.read_text():
            # the stock turbo loader has no inline assembler: load asm as viper
            subprocess.run([sys.executable, str(ROOT / "tools" / "asm_to_viper.py"), str(output)], check=True)
        print("compiled", source.relative_to(ROOT), "->", output.relative_to(ROOT), output.stat().st_size, "bytes")
        outputs.append(output)
    return outputs


def deploy(mount, outputs):
    if not (mount / "boot_out.txt").exists():
        sys.exit("no CIRCUITPY drive at %s" % mount)
    existing = mount / "code.py"
    saved = BACKUP / "code.py.orig"
    if existing.exists() and not saved.exists():
        BACKUP.mkdir(exist_ok=True)
        shutil.copyfile(existing, saved)
        print("saved board's code.py to", saved.relative_to(ROOT))
    lib = mount / "lib"
    lib.mkdir(exist_ok=True)
    for output in outputs:
        copy_if_changed(output, lib / output.name, "lib/")
    for path in sorted(ASSETS.glob("*.bin")):
        copy_if_changed(path, mount / path.name, "/")
    # code.py last, so the auto-reload it triggers sees the new modules
    for path in sorted(APP.glob("*.py"), key=lambda p: p.name == "code.py"):
        copy_if_changed(path, mount / path.name, "/")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--deploy", action="store_true", help="copy to the CIRCUITPY drive")
    parser.add_argument("--mount", default="/Volumes/CIRCUITPY", type=pathlib.Path)
    options = parser.parse_args()
    outputs = compile_all()
    if options.deploy:
        deploy(options.mount, outputs)


if __name__ == "__main__":
    main()
