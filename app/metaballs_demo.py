"""2D metaballs: shaded blobs that merge, over a glowing field."""

import gc

import display

# The display first: see voxel_demo.py. The scratch SRAM holds the kernel's
# args and lighting tables (14 KB).
gc.collect()
screen = display.Display(scratch=14336)

# pylint: disable=wrong-import-position,wrong-import-order
import time

import blobs
import metafield

REPORT_SECONDS = 2

space = metafield.Metaballs(display.WIDTH, display.BACK_HEIGHT, "/metaballs.bin", scratch=screen.scratch)
gc.collect()
print("metaballs: %d balls, free heap %d" % (len(blobs.PATHS), gc.mem_free()))

start = time.monotonic()
frames = 0
render_ns = 0
report_at = time.monotonic_ns() + REPORT_SECONDS * 1_000_000_000
while True:
    space.set_balls(blobs.positions(time.monotonic() - start, display.WIDTH, display.BACK_HEIGHT))
    t0 = time.monotonic_ns()
    space.render(screen.back)
    t1 = time.monotonic_ns()
    screen.flip()
    frames += 1
    render_ns += t1 - t0
    if t1 >= report_at:
        print("%.1f fps | render %.1f ms" % (frames / REPORT_SECONDS, render_ns / frames / 1e6))
        frames = render_ns = 0
        report_at += REPORT_SECONDS * 1_000_000_000
