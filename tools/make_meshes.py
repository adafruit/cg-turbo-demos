#!/usr/bin/env python3
"""Make the 3D models: assets/teapot.bin and assets/bunny.bin.

    python3 tools/make_meshes.py

Downloads the sources into build/downloads (once):
  the Utah teapot: Martin Newell's 32 Bezier patches, from three.js's
      TeapotGeometry.js (MIT), tessellated here
  the Stanford bunny: bun_zipper_res3.ply from the Stanford 3D Scanning
      Repository (https://graphics.stanford.edu/data/3Dscanrep/). Stanford
      asks for acknowledgment and allows research use; assets/bunny.bin is
      therefore made at build time and not committed.

Each model is centered, scaled to fit the unit sphere, y up, triangles wound
counterclockwise seen from outside. File format (little-endian):
  u16 vertices, u16 triangles, u32 0
  vertices x 3 f32 positions, vertices x 3 f32 normals (smooth),
  triangles x 3 f32 face normals, triangles x 3 u16 vertex indices
"""

import argparse
import pathlib
import re
import tarfile
import urllib.request

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "build" / "downloads"
TEAPOT_URL = "https://raw.githubusercontent.com/mrdoob/three.js/r160/examples/jsm/geometries/TeapotGeometry.js"
BUNNY_URL = "http://graphics.stanford.edu/pub/3Dscanrep/bunny.tar.gz"
BUNNY_MEMBER = "bunny/reconstruction/bun_zipper_res3.ply"


def fetch(url, path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print("downloading", url)
        urllib.request.urlretrieve(url, path)
    return path


def js_numbers(text, name):
    """The numbers in `const name = [ ... ];` of the three.js source."""
    match = re.search(r"const %s = \[(.*?)\];" % name, text, re.S)
    body = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)
    return [float(n.replace(" ", "")) for n in re.findall(r"-?\s*[\d.]+", body)]


def bernstein(t):
    s = 1 - t
    return np.array([s * s * s, 3 * t * s * s, 3 * t * t * s, t * t * t])


def teapot(segments):
    text = fetch(TEAPOT_URL, DOWNLOADS / "teapot" / "TeapotGeometry.js").read_text()
    patches = np.array(js_numbers(text, "teapotPatches"), dtype=int).reshape(-1, 4, 4)
    control = np.array(js_numbers(text, "teapotVertices")).reshape(-1, 3)
    positions, triangles = [], []
    t = np.linspace(0, 1, segments + 1)
    for patch in patches:
        p = control[patch]  # [r][c] -> xyz
        base = len(positions)
        for u in t:
            for v in t:
                positions.append(np.einsum("r,c,rcx->x", bernstein(u), bernstein(v), p))
        n = segments + 1
        for i in range(segments):
            for j in range(segments):
                a, b = base + i * n + j, base + i * n + j + 1
                c, d = base + (i + 1) * n + j, base + (i + 1) * n + j + 1
                triangles += [(a, c, b), (b, c, d)]
    positions = np.array(positions)[:, [0, 2, 1]] * [1, 1, -1]  # z up -> y up, keeping handedness
    return positions, np.array(triangles)


def bunny():
    archive = fetch(BUNNY_URL, DOWNLOADS / "stanford" / "bunny.tar.gz")
    with tarfile.open(archive) as tar:
        lines = tar.extractfile(BUNNY_MEMBER).read().decode().splitlines()
    end = lines.index("end_header")
    vertices = int(next(l for l in lines if l.startswith("element vertex")).split()[2])
    faces = int(next(l for l in lines if l.startswith("element face")).split()[2])
    positions = np.array([[float(x) for x in l.split()[:3]] for l in lines[end + 1 : end + 1 + vertices]])
    triangles = np.array([[int(x) for x in l.split()[1:4]] for l in lines[end + 1 + vertices : end + 1 + vertices + faces]])
    return positions, triangles


def weld(positions, triangles, tolerance=1e-6):
    """Merge vertices at the same place (the teapot's patch seams), drop
    triangles that collapse."""
    keys = np.round(positions / tolerance).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    triangles = inverse.reshape(-1)[triangles]
    positions = positions[first]
    keep = (triangles[:, 0] != triangles[:, 1]) & (triangles[:, 1] != triangles[:, 2]) & (triangles[:, 0] != triangles[:, 2])
    return positions, triangles[keep]


def orient(positions, triangles):
    """Make neighbors agree on winding (walking across edges shared by exactly
    two triangles), then turn each piece outside out by its signed volume.
    The decimated bunny has many triangles wound the wrong way."""
    from collections import defaultdict, deque

    triangles = triangles.copy()
    by_edge = defaultdict(list)
    for t, (a, b, c) in enumerate(triangles):
        for u, v in ((a, b), (b, c), (c, a)):
            by_edge[(min(u, v), max(u, v))].append(t)
    seen = np.zeros(len(triangles), dtype=bool)
    flips = 0
    for start in range(len(triangles)):
        if seen[start]:
            continue
        seen[start] = True
        piece, queue = [start], deque([start])
        while queue:
            t = queue.popleft()
            a, b, c = triangles[t]
            for u, v in ((a, b), (b, c), (c, a)):
                sharing = by_edge[(min(u, v), max(u, v))]
                if len(sharing) != 2:
                    continue
                other = sharing[0] if sharing[1] == t else sharing[1]
                if seen[other]:
                    continue
                oa, ob, oc = triangles[other]
                if (u, v) in ((oa, ob), (ob, oc), (oc, oa)):  # same direction: wound the other way
                    triangles[other] = (oa, oc, ob)
                    flips += 1
                seen[other] = True
                piece.append(other)
                queue.append(other)
        p = positions[triangles[piece]]
        volume = np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum()
        if volume < 0:
            triangles[piece] = triangles[piece][:, [0, 2, 1]]
    print("  winding: %d triangles flipped to agree with their neighbors" % flips)
    return positions, triangles


def finish(positions, triangles):
    lo, hi = positions.min(axis=0), positions.max(axis=0)
    positions = positions - (lo + hi) / 2
    positions /= np.linalg.norm(positions, axis=1).max()
    a, b, c = (positions[triangles[:, k]] for k in range(3))
    cross = np.cross(b - a, c - a)
    area = np.linalg.norm(cross, axis=1)
    keep = area > 1e-9
    triangles, cross, area = triangles[keep], cross[keep], area[keep]
    face_normals = cross / area[:, None]
    normals = np.zeros_like(positions)
    for k in range(3):
        np.add.at(normals, triangles[:, k], cross)  # area-weighted
    used = np.linalg.norm(normals, axis=1) > 0
    normals[used] /= np.linalg.norm(normals[used], axis=1)[:, None]
    return positions, normals, face_normals, triangles


def write(path, positions, normals, face_normals, triangles):
    header = np.array([len(positions), len(triangles), 0, 0], dtype="<u2").tobytes()
    data = header + b"".join(
        a.astype(t).tobytes() for a, t in ((positions, "<f4"), (normals, "<f4"), (face_normals, "<f4"), (triangles, "<u2"))
    )
    path.write_bytes(data)
    print("wrote %s: %d vertices, %d triangles, %d bytes" % (path.relative_to(ROOT), len(positions), len(triangles), len(data)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--segments", type=int, default=6, help="teapot patch subdivision")
    options = parser.parse_args()
    positions, triangles = orient(*weld(*teapot(options.segments)))
    write(ROOT / "assets" / "teapot.bin", *finish(positions, triangles))
    positions, triangles = orient(*bunny())
    write(ROOT / "assets" / "bunny.bin", *finish(positions, triangles))


if __name__ == "__main__":
    main()
