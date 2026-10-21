#!/usr/bin/env python3
"""The teapot's texture: assets/teapot_texture.bin, 128 x 128 little-endian
rgb565, rows top to bottom.

    python3 tools/make_teapot_texture.py [grid.png]

From the University of Utah's teapot page
(https://graphics.cs.utah.edu/teapot/): its UV test grid (A1 to H8, 1024 x
1024; reference/grid.png by default), scaled down, its grays stretched to
LOW..HIGH so the checks read on a lit, shaded teapot. tools/make_meshes.py
lays the teapot out on it.
"""

import pathlib
import sys

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SIZE = 128  # make_meshes.TEXTURE
LOW, HIGH = 70, 235  # the darkest and lightest gray, of 255


def main():
    source = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reference" / "grid.png"
    image = Image.open(source).convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)
    c = np.asarray(image).astype(np.float64)
    lo, hi = np.percentile(c, (1, 99))
    c = np.clip(LOW + (c - lo) * (HIGH - LOW) / (hi - lo) + 0.5, 0, 255).astype(np.uint32)
    texels = ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)
    out = ROOT / "assets" / "teapot_texture.bin"
    out.write_bytes(texels.astype("<u2").tobytes())
    print("wrote", out.relative_to(ROOT), out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
