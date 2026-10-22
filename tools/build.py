#!/usr/bin/env python3
"""Compile src/*.py to build/lib/*.mpy for the Fruit Jam, and optionally deploy.

    python3 tools/build.py            # compile only
    python3 tools/build.py --deploy   # compile, then copy lib/*.mpy, app/* and assets/*.bin, *.bmp to CIRCUITPY
    python3 tools/build.py --bundle   # compile, then zip what CIRCUITPY needs: build/cg-turbo-demos.zip

The first deploy saves the board's existing code.py to backup/ before
replacing it. Source .py files are never copied to the board, so they can't
shadow the compiled .mpy modules.

The bundle is laid out like the CIRCUITPY drive, with the one library the
demos need (adafruit_display_text, for the menu, as .py so it loads on any
firmware), so installing is copying its contents to the drive. The compiled
modules are .mpy v6.3 for armv7emsp: they load on any CircuitPython with that
.mpy version and Turbo loading (RP2xxx, 10.3.1 on).
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
MPY_CROSS = ROOT / "tools" / "mpy-cross"
ARCH = "armv7emsp"
SRC = ROOT / "src"
APP = ROOT / "app"
BUILD_LIB = ROOT / "build" / "lib"
ASSETS = ROOT / "assets"
BACKUP = ROOT / "backup"
DOWNLOADS = ROOT / "build" / "downloads"
BUNDLE = ROOT / "build" / "cg-turbo-demos.zip"
LIBRARIES = (("Adafruit_CircuitPython_Display_Text", "adafruit_display_text"),)  # (repo, package)
BUNDLE_README = """cg-turbo-demos for the Adafruit Fruit Jam
https://github.com/adafruit/cg-turbo-demos

Needs CircuitPython 10.3.1 or later on the Fruit Jam (built for .mpy v6.3).
Copy everything in this folder to the CIRCUITPY drive, replacing code.py
(save yours first), then plug in HDMI. The menu starts: button 3 up,
button 2 down, button 1 starts a demo; reset comes back to the menu.
"""


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


def board_files(outputs):
    """(path on CIRCUITPY, source) for everything deploy and the bundle copy:
    code.py last, so the auto-reload it triggers sees the new modules."""
    files = [("lib/" + output.name, output) for output in outputs]
    files += [(path.name, path) for path in sorted(ASSETS.glob("*.bin")) + sorted(ASSETS.glob("*.bmp"))]
    files += [(path.name, path) for path in sorted(APP.glob("*.py"), key=lambda p: p.name == "code.py")]
    return files


def library(repo, package):
    """The latest release of an Adafruit library, as .py files: (path in lib/, bytes)."""
    cached = DOWNLOADS / (repo + "-py.zip")
    if not cached.exists():
        with urllib.request.urlopen("https://api.github.com/repos/adafruit/%s/releases/latest" % repo) as response:
            release = json.load(response)
        asset = next(a for a in release["assets"] if a["name"].endswith("-py-%s.zip" % release["tag_name"]))
        print("downloading", asset["browser_download_url"])
        cached.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(asset["browser_download_url"], cached)
    files = []
    with zipfile.ZipFile(cached) as archive:
        for name in archive.namelist():
            parts = name.split("/")
            # <release folder>/lib/<package>/...: only the package's own files
            if len(parts) >= 4 and parts[1] == "lib" and parts[2] == package and not name.endswith("/"):
                files.append(("/".join(parts[2:]), archive.read(name)))
    if not files:
        sys.exit("no %s in %s" % (package, cached))
    return files


def bundle(outputs):
    folder = "cg-turbo-demos/"
    with zipfile.ZipFile(BUNDLE, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(folder + "README.txt", BUNDLE_README)
        for path, source in board_files(outputs):
            archive.write(source, folder + path)
        for repo, package in LIBRARIES:
            for path, data in library(repo, package):
                archive.writestr(folder + "lib/" + path, data)
    print("wrote", BUNDLE.relative_to(ROOT), BUNDLE.stat().st_size, "bytes")


def deploy(mount, outputs):
    if not (mount / "boot_out.txt").exists():
        sys.exit("no CIRCUITPY drive at %s" % mount)
    existing = mount / "code.py"
    saved = BACKUP / "code.py.orig"
    if existing.exists() and not saved.exists():
        BACKUP.mkdir(exist_ok=True)
        shutil.copyfile(existing, saved)
        print("saved board's code.py to", saved.relative_to(ROOT))
    (mount / "lib").mkdir(exist_ok=True)
    for path, source in board_files(outputs):
        copy_if_changed(source, mount / path, "lib/" if path.startswith("lib/") else "/")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--deploy", action="store_true", help="copy to the CIRCUITPY drive")
    parser.add_argument("--bundle", action="store_true", help="zip what CIRCUITPY needs into build/cg-turbo-demos.zip")
    parser.add_argument("--mount", default="/Volumes/CIRCUITPY", type=pathlib.Path)
    options = parser.parse_args()
    outputs = compile_all()
    if options.deploy:
        deploy(options.mount, outputs)
    if options.bundle:
        bundle(outputs)


if __name__ == "__main__":
    main()
