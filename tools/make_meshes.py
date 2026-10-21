#!/usr/bin/env python3
"""Make the 3D models: assets/teapot.bin and assets/bunny.bin.

    python3 tools/make_meshes.py

Downloads the sources into build/downloads (once):
  the Utah teapot: Martin Newell's 32 Bezier patches, from three.js's
      TeapotGeometry.js (MIT), tessellated here
  the Stanford bunny: bun_zipper_res3.ply from the Stanford 3D Scanning
      Repository (https://graphics.stanford.edu/data/3Dscanrep/)

Each model is centered, scaled to fit the unit sphere, y up, triangles wound
counterclockwise seen from outside. File format (little-endian):
  u16 vertices, u16 triangles, u16 focal length (pixels per unit at distance
  1: as large as keeps the model inside the demo's window through a whole
  turn), u16 0
  vertices x 3 f32 positions, vertices x 3 f32 normals (smooth),
  triangles x 3 f32 face normals, triangles x 3 u16 vertex indices,
  triangles x u16 edge masks for the quad wireframe (bit 0 a-b, 1 b-c,
      2 c-a; 0 for the diagonal of a quad), apart from the indices so the
      other modes read only 6 bytes a triangle
"""

import argparse
import pathlib
import re
import tarfile
import urllib.request

import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools" / "host"), str(ROOT / "src"), str(ROOT / "app")]

import meshview  # noqa: E402  (the demo's view: window, distance, tilt)

MARGIN = 4  # pixels kept clear at the window's edges
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
    positions, triangles, parts = [], [], []
    for index, patch in enumerate(patches):
        # the spout and handle meet the body: smaller triangles there sort
        # better back to front
        n_seg = segments * FINE if PART[index] in ("spout", "handle") else segments
        t = np.linspace(0, 1, n_seg + 1)
        p = control[patch]  # [r][c] -> xyz
        base = len(positions)
        for u in t:
            for v in t:
                positions.append(np.einsum("r,c,rcx->x", bernstein(u), bernstein(v), p))
        n = n_seg + 1
        for i in range(n_seg):
            for j in range(n_seg):
                a, b = base + i * n + j, base + i * n + j + 1
                c, d = base + (i + 1) * n + j, base + (i + 1) * n + j + 1
                triangles += [(a, c, b), (b, c, d)]
                parts += [PART[index]] * 2
    positions = np.array(positions)[:, [0, 2, 1]] * [1, 1, -1]  # z up -> y up, keeping handedness
    return positions, np.array(triangles), np.array(parts)


FINE = 2  # the spout's and handle's subdivision, times the rest's
# three.js's patch order: rim 4, body 8, handle 4, spout 4, lid 8, bottom 4
PART = ["rim"] * 4 + ["body"] * 8 + ["handle"] * 4 + ["spout"] * 4 + ["lid"] * 8 + ["bottom"] * 4


def trim_inside_body(positions, triangles, parts):
    """Drop the spout's and handle's triangles inside the body: the original
    data runs them into it, and drawing back to front can't sort surfaces
    that cut through each other (dark jagged patches at the spout's base).
    The body is a surface of revolution about y: inside means nearer the axis
    than the body's radius at that height."""
    body = positions[np.unique(triangles[parts == "body"])]
    heights = np.unique(np.round(body[:, 1], 6))
    radius = np.array([np.hypot(body[:, 0], body[:, 2])[np.abs(body[:, 1] - h) < 1e-6].max() for h in heights])
    center = positions[triangles].mean(axis=1)
    inside = np.hypot(center[:, 0], center[:, 2]) < np.interp(center[:, 1], heights, radius) - 1e-3
    drop = np.isin(parts, ("spout", "handle")) & inside
    print("  teapot: %d spout and handle triangles inside the body dropped" % drop.sum())
    return triangles[~drop], parts[~drop]


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


def weld(positions, triangles, tolerance=1e-6, parts=None):
    """Merge vertices at the same place (the teapot's patch seams), drop
    triangles that collapse."""
    keys = np.round(positions / tolerance).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    triangles = inverse.reshape(-1)[triangles]
    positions = positions[first]
    keep = (triangles[:, 0] != triangles[:, 1]) & (triangles[:, 1] != triangles[:, 2]) & (triangles[:, 0] != triangles[:, 2])
    if parts is not None:
        return positions, triangles[keep], parts[keep]
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


def focal(positions):
    """The largest focal length (pixels per unit at distance 1) that keeps
    the model's projection inside the demo's window, with MARGIN, through a
    whole turn of the spin."""
    reach_x = reach_y = 0.0
    for degrees in range(360):
        m = np.array(meshview.rotation(np.radians(degrees))).reshape(3, 3)
        r = positions @ m.T
        z = r[:, 2] + meshview.DISTANCE
        reach_x = max(reach_x, np.abs(r[:, 0] / z).max())
        reach_y = max(reach_y, np.abs(r[:, 1] / z).max())
    half_w = meshview.WIDTH / 2 - MARGIN
    half_h = meshview.HEIGHT / 2 - MARGIN
    return int(min(half_w / reach_x, half_h / reach_y))


def quad_edges(positions, triangles, face_normals):
    """Pair triangles into quads for the quad wireframe: two triangles that
    share an edge pair up when it is the longest edge of both and they are
    nearly flat together, best pairs first; the shared edge, the quad's
    diagonal, is left out of both masks. The teapot was tessellated from quads
    and comes back as them; the scanned bunny becomes mostly quads."""
    from collections import defaultdict  # pylint: disable=import-outside-toplevel

    p = positions[triangles]  # (t, 3, xyz)
    lengths = np.stack([np.linalg.norm(p[:, (e + 1) % 3] - p[:, e], axis=1) for e in range(3)], axis=1)
    longest = lengths.argmax(axis=1)
    users = defaultdict(list)
    for t, tri in enumerate(triangles):
        for e in range(3):
            u, v = tri[e], tri[(e + 1) % 3]
            users[(min(u, v), max(u, v))].append((t, e))
    candidates = []
    for pair in users.values():
        if len(pair) != 2:
            continue
        (t1, e1), (t2, e2) = pair
        flat = float(face_normals[t1] @ face_normals[t2])
        if longest[t1] == e1 and longest[t2] == e2 and flat > 0.9:
            candidates.append((flat, t1, e1, t2, e2))
    masks = np.full(len(triangles), 7, dtype=np.uint16)
    paired = np.zeros(len(triangles), dtype=bool)
    for _, t1, e1, t2, e2 in sorted(candidates, reverse=True):
        if not paired[t1] and not paired[t2]:
            masks[t1] &= 7 ^ (1 << e1)
            masks[t2] &= 7 ^ (1 << e2)
            paired[t1] = paired[t2] = True
    print("  quads: %d of %d triangles paired" % (paired.sum(), len(triangles)))
    return masks


def write(path, positions, normals, face_normals, triangles):
    f = focal(positions)
    masks = quad_edges(positions, triangles, face_normals)
    header = np.array([len(positions), len(triangles), f, 0], dtype="<u2").tobytes()
    data = header + b"".join(
        a.astype(t).tobytes()
        for a, t in ((positions, "<f4"), (normals, "<f4"), (face_normals, "<f4"), (triangles, "<u2"), (masks, "<u2"))
    )
    path.write_bytes(data)
    print(
        "wrote %s: %d vertices, %d triangles, focal %d, %d bytes"
        % (path.relative_to(ROOT), len(positions), len(triangles), f, len(data))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--segments", type=int, default=6, help="teapot patch subdivision")
    options = parser.parse_args()
    positions, triangles, parts = teapot(options.segments)
    positions, triangles, parts = weld(positions, triangles, parts=parts)
    triangles, parts = trim_inside_body(positions, triangles, parts)
    positions, triangles = orient(positions, triangles)
    write(ROOT / "assets" / "teapot.bin", *finish(positions, triangles))
    positions, triangles = orient(*bunny())
    write(ROOT / "assets" / "bunny.bin", *finish(positions, triangles))


if __name__ == "__main__":
    main()
