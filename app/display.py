"""320x240 RGB565 HDMI (pixel-doubled to 640x480) with a 320x200 back buffer.

The back buffer has to be in internal SRAM, which only has about 147 KB left
after the framebuffer: create the Display before allocating anything else big.
`scratch` reserves a little more SRAM, ahead of the back buffer, for a demo's
hot per-frame data.
"""

import array

import board
import displayio
import picodvi

import mem

WIDTH = 320
HEIGHT = 240
BACK_HEIGHT = 200


class Display:
    def __init__(self, scratch=0, back=True, back_width=WIDTH):
        """back=False: no back buffer, for demos that draw straight to the
        screen. back_width < WIDTH: a narrower back buffer (less SRAM),
        shown in the middle of the screen."""
        displayio.release_displays()
        self.framebuffer = picodvi.Framebuffer(
            WIDTH,
            HEIGHT,
            clk_dp=board.CKP,
            clk_dn=board.CKN,
            red_dp=board.D0P,
            red_dn=board.D0N,
            green_dp=board.D1P,
            green_dn=board.D1N,
            blue_dp=board.D2P,
            blue_dn=board.D2N,
            color_depth=16,
        )
        self.screen = memoryview(self.framebuffer).cast("B")
        self.scratch = bytearray(scratch)
        self.back_width = back_width
        self.back = bytearray(back_width * BACK_HEIGHT * 2 if back else 0)
        for name in ("scratch", "back"):
            if not len(getattr(self, name)):
                continue
            where = mem.address(getattr(self, name))
            if 0 < where < mem.SRAM:
                print("warning: %s buffer is in PSRAM (0x%08x): rendering will be slow" % (name, where))
        top = (HEIGHT - BACK_HEIGHT) // 2 * WIDTH * 2
        self.letterbox = self.screen[top : top + len(self.back)] if back else None
        if back and back_width < WIDTH:
            # rows of the narrow back buffer go to the middle of each screen row
            left = (WIDTH - back_width) // 2 * 2
            self.letterbox = None
            self.window = mem.address(self.screen) + top + left
            self.layout = array.array("i", (back_width // 2, WIDTH // 2))
        self.wait_for_vblank = getattr(self.framebuffer, "wait_for_vblank", None)
        row = bytes(WIDTH * 2)
        for y in range(HEIGHT):
            self.screen[y * WIDTH * 2 : (y + 1) * WIDTH * 2] = row

    def flip(self):
        """Show the back buffer: starts at vblank and outruns the beam, so no tearing."""
        if self.wait_for_vblank:
            self.wait_for_vblank()
        if self.letterbox is not None:
            self.letterbox[:] = self.back
        else:
            mem.copy_rows(self.window, self.back, BACK_HEIGHT, self.layout)
