"""3D models: the Utah teapot and the Stanford bunny, spinning slowly.

Button 1 switches the model, button 2 the rendering: wireframe, Lambert
(flat), Phong and Blinn (per-pixel lighting).
"""

import gc

import display

# The display first: see voxel_demo.py. A 240-wide back buffer leaves SRAM
# for the transformed vertices, drawing order and lighting table.
gc.collect()
screen = display.Display(scratch=44032, back_width=240)

# pylint: disable=wrong-import-position,wrong-import-order
import time

import board
import keypad

import meshview

SPIN = 0.5  # radians per second
REPORT_SECONDS = 2

viewer = meshview.MeshView(("/teapot.bin", "/bunny.bin"), "/mesh_luts.bin", screen.scratch)
buttons = keypad.Keys((board.BUTTON1, board.BUTTON2), value_when_pressed=False, pull=True)
gc.collect()
print("meshes: free heap %d" % gc.mem_free())
NAMES = ("teapot", "bunny")

start = time.monotonic()
frames = 0
render_ns = 0
report_at = time.monotonic_ns() + REPORT_SECONDS * 1_000_000_000
while True:
    event = buttons.events.get()
    if event and event.pressed:
        if event.key_number == 0:
            viewer.show_model((viewer.model + 1) % len(viewer.models))
            print("model", NAMES[viewer.model])
        else:
            viewer.show_mode((viewer.mode + 1) % len(meshview.MODES))
            print("mode", meshview.MODES[viewer.mode])
    viewer.set_rotation(meshview.rotation((time.monotonic() - start) * SPIN))
    t0 = time.monotonic_ns()
    viewer.render(screen.back)
    t1 = time.monotonic_ns()
    screen.flip()
    frames += 1
    render_ns += t1 - t0
    if t1 >= report_at:
        print("%.1f fps | render %.1f ms" % (frames / REPORT_SECONDS, render_ns / frames / 1e6))
        frames = render_ns = 0
        report_at += REPORT_SECONDS * 1_000_000_000
