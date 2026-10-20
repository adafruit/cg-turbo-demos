"""Cornell box path tracer: the image refines with every pass.

Button 1 starts over from zero samples.
"""

import gc

import display

# The display first: see voxel_demo.py. No back buffer: passes draw straight
# to the screen, a row at a time.
gc.collect()
screen = display.Display(scratch=1024, back=False)

# pylint: disable=wrong-import-position,wrong-import-order
import time

import board
import keypad

import cornell
import cornell_scene as scene

box = cornell.Cornell(screen, screen.scratch)
buttons = keypad.Keys((board.BUTTON1,), value_when_pressed=False, pull=True)
gc.collect()
print("Cornell box: %dx%d, free heap %d" % (scene.SIZE, scene.SIZE, gc.mem_free()))

started = time.monotonic()
while True:
    t0 = time.monotonic_ns()
    box.begin_pass()
    restart = False
    for row in range(scene.SIZE):
        box.trace_row(row)
        event = buttons.events.get()
        if event and event.pressed and event.key_number == 0:
            restart = True
            break
    if restart:
        box.reset()
        started = time.monotonic()
        print("restarted")
        continue
    box.end_pass()
    print(
        "%d samples | pass %.2f s | %.0f s total"
        % (box.passes, (time.monotonic_ns() - t0) / 1e9, time.monotonic() - started)
    )
