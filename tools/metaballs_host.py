#!/usr/bin/env python3
"""Render 2D metaballs frames on the desktop with the viper reference.

    python3 tools/metaballs_host.py --time 0 --out build/metaballs.png
    python3 tools/metaballs_host.py --dump frame.bin   # raw rgb565, to compare with the board

Uses the same src/metaballs.py, app/metafield.py and app/blobs.py (the
animation) as the board.
"""

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools" / "host"), str(ROOT / "src"), str(ROOT / "app"), str(ROOT / "tools")]

import blobs  # noqa: E402
import metaballs  # noqa: E402
import metafield  # noqa: E402
from voxel_host import to_image  # noqa: E402

WIDTH, HEIGHT = 320, 200


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--time", type=float, default=0.0, help="animation time, seconds")
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "build" / "metaballs.png")
    parser.add_argument("--dump", type=pathlib.Path)
    options = parser.parse_args()
    space = metafield.Metaballs(
        WIDTH, HEIGHT, str(ROOT / "assets" / "metaballs.bin"), buffer_view=lambda b: memoryview(b).cast("H")
    )
    space.kernel = metaballs.render  # the asm only runs on the board
    space.set_balls(blobs.positions(options.time, WIDTH, HEIGHT))
    back = bytearray(WIDTH * HEIGHT * 2)
    start = time.monotonic()
    space.render(memoryview(back).cast("H"))
    print("rendered in %.2f s on the host" % (time.monotonic() - start))
    options.out.parent.mkdir(exist_ok=True)
    to_image(back).save(options.out)
    print("wrote", options.out)
    if options.dump:
        options.dump.write_bytes(back)


if __name__ == "__main__":
    main()
