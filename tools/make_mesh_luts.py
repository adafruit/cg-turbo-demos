#!/usr/bin/env python3
"""Lighting tables for the 3D model demo: assets/mesh_luts.bin.

    python3 tools/make_mesh_luts.py

Three 64 x 64 little-endian rgb565 tables, back to back: Lambert (diffuse
only), Phong (specular from the reflected light, (R.V)^n) and Blinn (specular
from the half vector, (N.H)^n), with the same light, material and exponent,
so Phong and Blinn differ only in the specular model. Each is indexed by a
view-space normal: [iy * 64 + ix], nx = (2 ix + 1 - 64) / 63, ny likewise
(y up), facing the camera. The light is directional and the view nearly
orthographic, so a pixel's lighting depends only on its normal: these tables
are the per-pixel lighting.
"""

import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent

COLOR = np.array([0.80, 0.62, 0.45])  # glazed clay
AMBIENT = 0.12
LIGHT = np.array([-0.45, 0.55, -0.70])  # toward the light: upper left, the camera's side
SPECULAR = 0.75
SHININESS = 24
MODES = ("lambert", "phong", "blinn")


def rgb565(c):
    c = np.clip(np.asarray(c) * 255 + 0.5, 0, 255).astype(np.uint32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def table(mode):
    i = (np.arange(64) * 2 + 1 - 64) / 63  # meshview's NORMAL_SCALE
    nx, ny = np.meshgrid(i, i)
    nz = -np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))  # toward the camera, which looks along +z
    n = np.stack([nx, ny, nz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    light = LIGHT / np.linalg.norm(LIGHT)
    view = np.array([0.0, 0.0, -1.0])  # from the surface to the camera
    diffuse = np.clip(n @ light, 0, 1)
    color = COLOR * (AMBIENT + (1 - AMBIENT) * diffuse[..., None])
    if mode == "phong":
        reflected = 2 * (n @ light)[..., None] * n - light
        color = color + SPECULAR * (np.clip(reflected @ view, 0, 1) ** SHININESS)[..., None]
    elif mode == "blinn":
        half = (light + view) / np.linalg.norm(light + view)
        color = color + SPECULAR * (np.clip(n @ half, 0, 1) ** SHININESS)[..., None]
    return rgb565(color)


def main():
    out = ROOT / "assets" / "mesh_luts.bin"
    data = b"".join(table(m).astype("<u2").tobytes() for m in MODES)
    out.write_bytes(data)
    print("wrote", out.relative_to(ROOT), len(data), "bytes:", ", ".join(MODES))


if __name__ == "__main__":
    main()
