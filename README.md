# cg-turbo-demos

Computer graphics demos in the spirit of early SIGGRAPH, running on an
[Adafruit Fruit Jam](https://www.adafruit.com/search?q=fruit+jam) (RP2350) in
CircuitPython, with the hot loops in
[CircuitPython Turbo](https://learn.adafruit.com/circuitpython-turbo): Viper
code compiled ahead of time with `mpy-cross`, plus `asm_thumb` inner loops.
Output is 320x240 RGB565, pixel-doubled to 640x480 HDMI by `picodvi`.

![VoxelSpace](docs/voxelspace.png)

## demos

**VoxelSpace** (`app/voxel_demo.py`): a Comanche-style voxel terrain
fly-over after [s-macke/VoxelSpace](https://github.com/s-macke/VoxelSpace),
on generated terrain, at a locked 30 fps (320x200, letterboxed).

| button | does |
| --- | --- |
| 1 | color map -> height map -> shaded height map |
| 2 | terrain height: full -> 1/2 -> 1/4 -> 1/8 -> flat |
| 3 | fog on / off |

![shaded height map](docs/voxelspace_shaded.png)
![height scales](docs/height_scales.png)

**Cornell box** (`app/cornell_demo.py`): a progressive path tracer, 240x240,
one sample per pixel per pass (0.73 s), refining on screen from noise to a
clean image in a minute or two. The asm kernel uses the RP2350's FPU and is
bit-identical to the numpy reference in `tools/cornell_ref.py`.

| button | does |
| --- | --- |
| 1 | side walls white / back to red and green (starts over) |
| 2 | start over from zero samples |
| 3 | the original's two boxes / back to the two spheres (starts over) |

![Cornell box](docs/cornell.png)
![Cornell box with the classic boxes](docs/cornell_boxes.png)
![Cornell box with white walls](docs/cornell_white.png)

**Metaballs** (`app/metaballs_demo.py`): six 2D metaballs gliding on
Lissajous paths, shaded as glossy 3D blobs that merge, over a glowing
contoured field. 30 fps at 320x200; the asm frame kernel is bit-identical to
the viper reference.

![Metaballs](docs/metaballs.png)

Pick the demo in `app/code.py` (`DEMO = "voxel_demo"`, `"cornell_demo"` or
`"metaballs_demo"`).

Coming: USB gamepad flying, and more Cornell box scenes. See
[NOTES.md](NOTES.md) for the plan, every measurement, and what was learned
about making Turbo code fast on this board.

## hardware and firmware

- Adafruit Fruit Jam and an HDMI display.
- Stock CircuitPython 10.3.1 or later (Turbo `.mpy` loading is built in on
  RP2xxx). Developed on `11.0.0-alpha.1-126-gea91926f34`.
- Adafruit's `mpy-cross` for the **same** firmware version, saved as
  `tools/mpy-cross`: builds are at
  `https://adafruit-circuit-python.s3.amazonaws.com/bin/mpy-cross/macos/mpy-cross-macos-<version>-arm64`
  (other platforms in the neighboring folders). Check `boot_out.txt` for the
  version.

## build and run

```sh
python3 tools/build.py --deploy        # compile src/ to lib/*.mpy, copy lib, app and assets to CIRCUITPY
python3 tools/serial_log.py --restart  # restart code.py and watch the console (frame times)
```

The first deploy saves the board's existing `code.py` to `backup/`.
`app/code.py` picks the demo (`voxel_demo`, or `fb_bench` for the
framebuffer benchmark).

## layout

- `app/`: plain Python that runs from source on the board (demo setup,
  camera, buttons).
- `src/`: Turbo modules, compiled to `.mpy` (`voxel.py` reference kernel and
  frame driver, `voxel_asm.py` generated asm).
- `tools/`: build and deploy, terrain generator (`make_terrain.py`, needs
  NumPy and Pillow), asm generator (`gen_voxel_asm.py`), desktop renderer and
  flicker meter (`voxel_host.py`, `voxel_flicker.py`), board runner.
- `tools/asm_to_viper.py` is from Adafruit's
  [Motion Tracking Eyeballs](https://github.com/adafruit/Adafruit_Learning_System_Guides/tree/main/CircuitPython_Turbo/Motion_Tracking_Eyeballs)
  guide (MIT, Liz Clark): it lets stock firmware load `asm_thumb` code.

The desktop renderer runs the same Viper reference kernel as the board (with
stand-in decorators in `tools/host/`), and board frames from the asm kernel
are checked bit-for-bit against it.

## license

MIT: see [LICENSE](LICENSE). `tools/asm_to_viper.py` keeps its own MIT
notice (Liz Clark for Adafruit Industries).
