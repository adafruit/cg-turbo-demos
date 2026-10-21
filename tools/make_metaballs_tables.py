#!/usr/bin/env python3
"""Lighting tables for the 2D metaballs: assets/metaballs.bin.

    python3 tools/make_metaballs_tables.py

Three little-endian u16 tables, back to back:
  256 glow colors (rgb565) for outside the blobs, indexed by field value
      (with contour bands)
  64 x 64 shades (rgb565) for inside, indexed by the surface slope
      (sy * 64 + sx, each offset by 32): the color of a lit 3D surface with
      that slope, so the flat 2D field shades like a blob
  256 slope scales, indexed by (field - threshold) >> 3: the surface shaded
      is z = sqrt(field - threshold), whose slope is gradient / (2 sqrt(...)),
      steepening to edge-on at the rim like a sphere's; slope = gradient *
      scale >> 12
Made here, not on the board, so both sides use the same bits.
"""

import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent

BASE = np.array([0.10, 0.55, 0.80])  # blob color
LIGHT = np.array([-0.5, -0.6, 0.62])  # toward the upper left, out of the screen
SLOPE = 1 / 8  # surface slope per shading table step
SCALE = 120  # surface slope: gradient * SCALE / sqrt(field - threshold), in table steps


def rgb565(c):
    c = np.clip(np.asarray(c) * 255 + 0.5, 0, 255).astype(np.uint32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def glow():
    f = np.arange(256) / 255.0
    color = np.stack([0.02 + 0.30 * f**1.5, 0.02 + 0.10 * f, 0.08 + 0.45 * f**0.8], axis=-1)
    band = (np.arange(256) % 32) < 3  # a bright contour line every 32 steps
    color[band] += np.array([0.10, 0.12, 0.25]) * f[band, None] + 0.04
    return rgb565(color)


def shade():
    g = np.arange(64) - 32
    gx, gy = np.meshgrid(g, g)
    # the kernel's gradient sums grow away from a ball's center, the way the
    # surface's normal tilts
    n = np.stack([gx * SLOPE, gy * SLOPE, np.ones_like(gx, dtype=float)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    light = LIGHT / np.linalg.norm(LIGHT)
    diffuse = np.clip(n @ light, 0, 1)
    half = light + np.array([0, 0, 1.0])
    half /= np.linalg.norm(half)
    specular = np.clip(n @ half, 0, 1) ** 40
    rim = (1 - n[..., 2]) ** 2
    color = BASE * (0.18 + 0.82 * diffuse[..., None]) + specular[..., None] * 0.9 + rim[..., None] * np.array(
        [0.05, 0.10, 0.25]
    )
    return rgb565(color)


def slope_scales():
    t = np.arange(256) * 8 + 4
    return np.clip(np.round(4096 * SCALE / np.sqrt(t + 16) / 256), 0, 65535).astype(np.uint32)


def main():
    out = ROOT / "assets" / "metaballs.bin"
    data = b"".join(t.astype("<u2").tobytes() for t in (glow(), shade(), slope_scales()))
    out.write_bytes(data)
    print("wrote", out.relative_to(ROOT), len(data), "bytes")


if __name__ == "__main__":
    main()
