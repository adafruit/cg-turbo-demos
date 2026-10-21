# notes: early-SIGGRAPH-style CG demos on the Fruit Jam

## next

- **USB gamepad control for VoxelSpace** (to do later): fly the camera with a
  gamepad on the Fruit Jam's USB-A host port; keep the automatic flight path
  as the attract mode when nobody is flying. Crankfruit
  (`Impossible-Playdate/app/gamepad_input.py`) has a working DualShock 4
  reader for this board.
- A 160-column (2-pixel-wide) VoxelSpace mode, to see whether it reaches 60 fps.
- Metaballs: a push for 60 fps (exact circle spans instead of bounding
  boxes; 9-12 balls drop to 20 fps); a 3D version on the Cornell box
  renderer.
- Cornell box: more scene (glass sphere, the classic boxes), on-screen sample
  count, then a baked room with live objects.

VoxelSpace terrain and Cornell box rendering in CircuitPython, with the hot
loops in Turbo (`@micropython.viper` compiled by `mpy-cross`, plus
`@micropython.asm_thumb` relabelled as viper). 320x240 RGB565, pixel-doubled
to 640x480 60 Hz by picodvi.

## firmware and tools

- Stock CircuitPython; developed on `11.0.0-alpha.1-126-gea91926f34`. Turbo
  `.mpy` loading is on for RP2xxx since 10.3.1; `Framebuffer.wait_for_vblank()`
  since 10.3.0.
- `tools/mpy-cross` is Adafruit's build for that exact commit (mpy v6.3).
  Compiled modules must match the firmware's mpy ABI: after a firmware update,
  download the matching `mpy-cross-macos-<version>-arm64` from
  `adafruit-circuit-python.s3.amazonaws.com/bin/mpy-cross/macos/`.
- The stock loader has no inline assembler, so `tools/build.py` runs
  `tools/asm_to_viper.py` (from Adafruit's Motion Tracking Eyeballs guide) on
  any module with `asm_thumb` functions. Relabelled asm receives its arguments
  as objects in an array at r3: pass small ints (addresses below 0x40000000
  are fine) and untag them with `asr(rN, rN, 1)`.

```
python3 tools/build.py --deploy            # compile src/, copy lib/*.mpy and app/* to CIRCUITPY
python3 tools/serial_log.py --restart      # restart code.py and watch the console
python3 tools/run_on_board.py probe.py     # run one file in the raw REPL
```

## measured (step 2, `app/code.py` + `src/fbtest.py`, 150 MHz)

| what | time | notes |
| --- | ---: | --- |
| naive viper fill16, 320x240 | 15.4 ms | ~30 cycles/pixel |
| viper fill32_fast, 320x240 | 1.04 ms | pointer bump, unrolled, hot vars in arg slots |
| asm fill32, 320x240 | 0.52 ms | 2 cycles per 32-bit store |
| any fill into PSRAM | ~18 ms | PSRAM writes cap at ~8.5 MB/s |
| copy 320x200 SRAM back buffer -> screen | 1.1 ms | slice assignment (C memcpy) |
| copy 320x240 PSRAM buffer -> screen | 6.1 ms | PSRAM reads ~25 MB/s |
| asm 8-bit palette expand, 320x240 from PSRAM | 8.8 ms | |
| viper XOR pattern (~12 int ops/pixel), 320x200 | 32.7 ms | locals spill to the stack |
| vblank period | 16.67 ms | |

## rules learned

- **Viper keeps only the first two locals in registers** (r4, r5): the first
  two arguments when there are any. Every other local is a stack load/store on
  each use, and `while a < b` builds a bool and tests it again. Put the moving
  pointer and loop counter in the first two argument slots, bump pointers
  instead of indexing (indexed ptr16 stores even push/pop a register), unroll
  with constant offsets. Check with `mpy-tool.py -e` + `arm-none-eabi-objdump
  -b binary -m arm -M force-thumb`.
- **Per-pixel math belongs in asm_thumb** when it has to run 77k times a frame;
  viper is fine for per-row/per-column setup and simple fills/copies.
- **Keep render targets in internal SRAM.** The GC heap gives SRAM until it
  runs out, then PSRAM. After the 150 KB framebuffer about 147 KB of SRAM is
  left: a 320x200 RGB565 back buffer (128,000 bytes) fits, a 320x240 one does
  not. Allocate render targets right after the framebuffer, before anything else.
- PSRAM is for big read-mostly data (terrain maps, accumulation buffers).
- Flip = `wait_for_vblank()` then slice-copy the back buffer; the copy outruns
  the beam, so it doesn't tear, and the loop locks to 60/30/20/15 fps.

## asm_thumb on stock CircuitPython

- Works through `tools/asm_to_viper.py` (see above). FPU instructions work too:
  `vmov`, `vcvt_f32_s32`, `vsqrt`, `vdiv`, `vmul`... (no `vmov` s-to-s: go
  through a core register). Dependent `vdiv` + `vsqrt` ~ 30 cycles.
- The assembler is the 16-bit Thumb subset: ALU ops only on r0-r7, small
  immediates (`add(rd, rn, imm3)`, `add(rd, imm8)`, `ldr` offsets <= 124), no
  register-offset loads, no `ubfx`/`mla`/`bfi`, no register shifts with 3
  operands. r8-r12 are reachable with `mov` (1 cycle): use them to hold
  constants. Save r8-r11 if you touch them. `data()` could emit raw Thumb-2.

## VoxelSpace (step 4)

- `tools/make_terrain.py` -> `assets/terrain16.bin`: u16 texels
  (height << 8 | palette index), 512x512 plus 256x256 and 128x128 mip levels
  (672 KB, PSRAM), and `assets/palette.bin` (256 rgb565, median cut).
- `src/voxel.py`: `render()` viper reference (also runs on the desktop) and
  `render_fast()`, which fills args slots 0-31 and calls
  `voxel_asm.frame_asm()` once per frame.
- `src/voxel_asm.py` is generated by `tools/gen_voxel_asm.py`: the per-sample
  loop written out per mip level (immediate shifts) and with/without the fog
  blend. Edit the generator, not the output.
- Rows use mip level 1 from z = 100 and level 2 from z = 200; distance steps
  grow by 0.016 per step.
- `tools/voxel_host.py` renders the same frame on the desktop. Desktop, board
  viper and board asm frames are bit-identical (CRC `f344122f` for the default
  view). Keep every table built with integer math: the board's floats are
  single precision, and `int(z)` / `int(600 * 0.35)` came out differently.
- Memory placement matters as much as code: `Display(scratch=8192)` reserves
  SRAM for the per-frame args (column buffer, palette, sky, asm slots) before
  the back buffer, and `VoxelSpace` loads the terrain after both. Create the
  Display before importing anything else: the SRAM margin is ~11 KB, and
  importing voxel + keypad first once pushed the back buffer into PSRAM
  (40 ms frames). Display warns when that happens.
- Button 1 cycles color map -> height map -> shaded height map
  (`VoxelSpace.show()` / `next_mode()`): each mode is a copy of the terrain
  with a different byte as the palette index (height, or the lighting from
  `assets/shade.bin`) plus a gray palette. No kernel change; each copy costs
  672 KB of PSRAM, and setup takes ~1.2 s.
- Button 2 cycles the terrain height: full, 1/2, 1/4, 1/8, flat
  (`next_height_scale()`), scaled around the lowest height (the sea). The
  per-sample height factor is `hinvz = invz >> shift` (31 for flat) and the
  offset folds into the per-row C, so the inner loop is unchanged; at full
  height the result is bit-identical to before. Flight frames: 24-26 ms at
  every scale.
- Button 3 toggles fog (`show_fog()`): fog off writes 0 into every row's fog
  entry, so the asm takes its fog-free loops. No kernel change.

| VoxelSpace, 320x200 | frame |
| --- | ---: |
| viper reference | 117-130 ms |
| asm columns, viper rows and sky (u32 texels) | 50 ms |
| + asm sky, constants in r8-r12 | 38 ms axis-aligned, 53-56 ms in flight |
| u16 texels + mip levels | 36 ms in flight (38 ms with args in PSRAM) |
| whole frame in one asm call, per-level loops | 32 ms |
| + 0.016 step growth, fog-free near loops | 24-31 ms in flight: locked 30 fps |

What's left per sample is ~25 instructions (~33 cycles); the next big steps
would be fewer samples (every other column on far rows) or half-width columns
for 60 fps.

### flicker

Point sampling aliases: wherever samples are further apart than texels, small
camera moves make them land on other texels and the terrain shimmers.
`tools/voxel_flicker.py` scores it on the desktop: mean |2nd temporal
difference| of luminance over 90 frames of the flight path.

| change | flicker | near | middle | far |
| --- | ---: | ---: | ---: | ---: |
| as first built (speckle, no blur, mips at 200/400) | 14.6 | 17.3 | 22.3 | 19.6 |
| 2 height + 2 color blur passes on the terrain | 7.8 | 8.6 | 10.8 | 12.1 |
| + mips at 100/200 (now) | 7.1 | 8.7 | 10.4 | 9.5 |

- The per-texel color speckle barely mattered (the 256-color quantization
  mostly removes it). The slope-based rock/grass mix was the real high
  frequency: blur the color map.
- Choosing the mip level from the sample spacing (max of the distance step
  and the column spacing) scores well but makes the foreground blocky: the
  first distance step is already 1 texel. Fixed distances keep near detail.
- The camera height is now fixed point (8 fractional bits): whole units made
  near terrain jump a few pixels at a time as the flight climbed.
- Coarser far levels also made frames faster (22-26 ms in flight).

## Cornell box (step 5)

Progressive path tracer, 240x240 centered on the screen, drawn straight into
the framebuffer a row at a time (no back buffer); a float32 accumulation
buffer (690 KB) in PSRAM. Unit-cube box seen through its open front: red/green
side walls, white floor/ceiling/back, a square ceiling light, a diffuse and a
mirror sphere.

- Per path: up to 3 interactions; the box exit is 3 divides (axis bounds
  ahead), 2 sphere tests; next event estimation (one light sample, shadowed
  only by the spheres) at every diffuse hit; cosine-weighted bounces (normal
  + random point in the unit ball, by rejection); emission counts only along
  camera -> mirror* -> light, which drops the slow mirror caustics
  (fireflies). xorshift32 per pixel, seeded from pixel index and pass.
- `tools/cornell_scene.py`: scene, parameter block layout; writes
  `app/cornell_scene.py` with every float constant as its float32 **bit
  pattern** (decimal float parsing on the board might round differently).
- `tools/cornell_ref.py`: numpy float32 reference, vectorized across pixels,
  same operations in the same order as the asm: board pixels and accumulation
  sums are **bit-identical** (full passes compared by CRC). 64 passes of the
  whole image take ~2 s on the desktop.
- `tools/gen_cornell_asm.py` -> `src/cornell_asm.py` (~700 lines, 2.4 KB):
  `trace_row(block)`. `app/cornell.py` drives it a row at a time.
- **0.73 s per pass** (~12.5 us, ~1900 cycles per pixel per sample): 64
  samples in under a minute, 256 in ~3 minutes.
- Button 1 paints the side walls white (and back): `Cornell.set_white_walls()`
  writes the white albedo's float bits into the red/green slots
  (`cornell_scene.WALL_SLOTS`) and starts over; button 2 starts over. The
  reference has the same switch (`use_white_walls()`, `--white-walls`); both
  looks are bit-identical on the board.
- Button 3 swaps the spheres for the original's two boxes (`set_boxes()`,
  the `MODE` slot; reference `use_boxes()` / `--boxes`): a short cube front
  right, a taller, slightly narrower box rear left, both rotated about y.
  Each box is a slab test in its own rotated frame, recording the entry face
  (`HIT_FACE`) for the normal, and the boxes shadow the light. 1.29 s per
  pass (each box test costs 6 divides, for camera and shadow rays alike)
  vs 0.74 s for the spheres. All modes are bit-identical to the reference.
- Exposure 1.8 (was 1.0): the white surfaces now nearly match the classic
  reference rendering; its colored walls are darker and less saturated than
  ours (it used measured spectra). 1.4 was tried first.
  5 interactions per path instead of 3 was tried and dropped:
  only 3-4% brighter, for 35% longer passes (0.98 s spheres, 1.76 s boxes).
- **Slice-assigning into a big bytearray is very slow in CircuitPython**:
  zeroing the 690 KB accumulation buffer row by row (`a[i:j] = zeros`, 2880
  bytes each) took 42 ms per row, 10 s in all. `mem.zero()` (viper) takes
  98 ms.

debugging asm on the board:

- A kernel stuck in asm can't be interrupted (Ctrl-C, USB): only reset.
  Probes arm `microcontroller.watchdog` (there is no `deinit()`: set
  `mode = None` to disarm), feeding it more often than the slowest step.
- Output printed just before a long asm call may not leave the board (USB
  is serviced between bytecodes): `time.sleep()` after diagnostic prints.
- Before blaming the asm, time the Python around it: the "hang" that led
  here was a 10 s `reset()`, not the kernel.

asm notes from this kernel:

- FPU instructions available: vadd, vsub, vmul, vdiv, vsqrt, vneg, vcmp +
  `vmrs(APSR_nzcv, FPSCR)`, vcvt both ways, vmov core<->s, vldr/vstr with
  offsets to 1020. Not available: vabs, vmla/vfma (good: no fused rounding),
  vmov between s registers or of an immediate, vldm/vpush.
- No float immediates: constants live in the block. Copy s registers through
  a core register (`vmov(r0, s); vmov(s', r0)`), keeping the bits.
- Branches: plain `b`/`bcc` reach only ~±2 KB / ±256 bytes; `beq_w` etc.
  reach ±1 MB; there is no wide unconditional branch, so long jumps use `bl`
  (fine outside subroutines). `bl`/`bx(lr)` subroutines work.
- NaN-safe skips after vcmp: skip unless a > b: `ble`; a < b: `bpl`;
  a >= b: `blt`; a <= b: `bhi`.
- s16-s31 are callee-saved: the kernel stores them in the block.

## Metaballs (step 6)

2D metaballs at 320x200 on the VoxelSpace display pipeline (back buffer,
vblank flip). Each ball adds Wyvill's falloff w = (1 - d^2/R^2)^2 (zero
beyond R, no divides) and its gradient to row sums, over its bounding span.
Inside the threshold, the surface shaded is z = sqrt(field - threshold), whose
slope (gradient * a table scale) steepens to edge-on at the rim like a
sphere's; the slope indexes a 64 x 64 lit-surface table. Outside, the field
indexes a 256-color glow palette with contour bands. All integer math.

- `tools/make_metaballs_tables.py` -> `assets/metaballs.bin` (glow palette,
  shading table, slope scales: 9 KB), made on the desktop so both sides use
  the same bits. The shading itself (light, color, gloss) lives there.
- `src/metaballs.py`: `render()` viper reference, `render_fast()` ->
  `src/metaballs_asm.py`, generated by `tools/gen_metaballs_asm.py`; its row
  sums are interleaved per pixel so one pointer reaches all three.
- `app/metafield.py` (setup), `app/blobs.py` (the paths), `app/metaballs_demo.py`,
  `tools/metaballs_host.py` (desktop frames).
- Desktop, board viper and board asm frames are bit-identical (4 test frames,
  positions on the 1/16-pixel grid).
- viper 117 ms, asm **20 ms per frame: locked 30 fps**.
- Shading the field itself looks like cones; the sqrt profile fixed that.
  The gradient sums grow away from a ball's center, the way the normal tilts.
- The asm slots grew the args header from 8 to 32 words, and the tables and
  args quietly stopped fitting the 13 KB scratch (they fell back to PSRAM:
  34 ms frames). Display(scratch=14336) now; the warning caught it.
- Buttons: 1 next hue, 2 one ball fewer, 3 one more (1 to 12; 6 at start).
  `assets/metaballs.bin` now holds six table sets, the same look rotated in
  hue about the gray axis (specular stays white); `next_hue()` copies one
  set (9 KB) from PSRAM into the SRAM tables. Balls 7-12 follow paths made
  the same way as the first six (`blobs.PATHS`).
- Frame time by balls: 1: 8.5 ms, 3: 14.9, 6: 20.0, 9: 27.1, 12: 32.7 ms
  (60 fps for 1-2, 30 for 3-11, 20 for 12). A 12-ball frame in a rotated hue
  is bit-identical to the reference.
