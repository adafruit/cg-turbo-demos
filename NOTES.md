# notes: early-SIGGRAPH-style CG demos on the Fruit Jam

## next

- **USB gamepad control for VoxelSpace** (to do later): fly the camera with a
  gamepad on the Fruit Jam's USB-A host port; keep the automatic flight path
  as the attract mode when nobody is flying. Crankfruit
  (`Impossible-Playdate/app/gamepad_input.py`) has a working DualShock 4
  reader for this board.
- A 160-column (2-pixel-wide) VoxelSpace mode, to see whether it reaches 60 fps.
- Metaballs: a push for 60 fps (exact circle spans instead of bounding
  boxes, which might allow more than 10 balls at 30 fps); a 3D version on the Cornell box
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
- Buttons: 1 next hue, 2 one ball fewer, 3 one more (1 to 10; 6 at start).
  `assets/metaballs.bin` now holds six table sets, the same look rotated in
  hue about the gray axis (specular stays white); `next_hue()` copies one
  set (9 KB) from PSRAM into the SRAM tables. Balls 7-10 follow paths made
  the same way as the first six (`blobs.PATHS`).
- Frame time by balls: 1: 8.5 ms, 3: 14.9, 6: 20.0, 9: 27.1, 12: 32.7 ms
  render only. Whole frames (with the flip and the Python per frame), as the
  demo runs: 9 balls 29.9 fps, 10: 29.7, 11: 25.5 (a third of frames late),
  so the count stops at 10. Count whole frames, not render time, before
  promising a frame rate. A 12-ball frame in a rotated hue is bit-identical
  to the reference.
- Double-clicking button 1 turns the glow (and its contour bands) off and
  on: `show_glow()` fills the SRAM glow palette with its first color, the
  empty field's; `next_hue()` keeps the state. A single click now acts
  0.35 s after the press, once it can't be the start of a double click.
  Glow-off and glow-on frames are bit-identical to the reference.

## 3D models (step 7)

The Utah teapot (Newell's patches, tessellated 6x6, seams welded: 1,177
vertices, 2,256 triangles) and the Stanford bunny (bun_zipper_res3: 1,889
vertices, 3,851 triangles), spinning, in four modes: wireframe, Lambert
(flat), Phong and Blinn (per-pixel lighting from interpolated normals).

- `tools/make_meshes.py`: downloads both, tessellates the teapot, centers and
  scales to the unit sphere, smooth vertex normals and face normals, and
  orients windings (the bunny's are consistent where its mesh is manifold).
  Both outputs are committed.
- `tools/make_mesh_luts.py`: 64x64 lighting tables indexed by the view-space
  normal (x, y; z toward the camera), for Lambert, Phong ((R.V)^n) and Blinn
  ((N.H)^n), same light and exponent. With a directional light and a nearly
  orthographic view, lighting depends only on the normal, so the tables are
  the per-pixel lighting.
- Pipeline: `mesh_asm.transform_asm` (FPU) rotates and projects vertices to
  12.4 screen coordinates, depth and normal x, y as u16, and face normals
  packed x << 8 | y (flat mode only); `mesh.sort` (cull back faces: positive
  screen area is front; bucket sort far to near, 256 buckets) and `mesh.draw`
  (clear; Bresenham edges, or edge-function fills over the bounding box,
  normals interpolated as (e0 na + e1 nb + e2 nc) / area). The asm versions
  (`mesh_draw`, from `tools/gen_mesh_draw.py`) step the edge functions and
  n_sum * inv instead of multiplying per pixel, and use area - e0 - e1 for
  the third edge function; results are identical.
- `tools/mesh_ref.py`: numpy float32 transform (bit-exact spec) + the viper
  sort/draw on the desktop. All 8 model/mode frames bit-identical on the board.
- Memory: a 240x200 back buffer (96 KB, `Display(back_width=240)`, copied
  into the screen's middle by `mem.copy_rows`) leaves SRAM for geo (vertex
  values, drawing order, packed face normals: 34 KB for the bunny), the args,
  the current lighting table (8 KB) and the transform block: 44 KB scratch.
- Frames, render only: teapot 14-23 ms, bunny 17-22 ms; whole frames hold
  30 fps in every mode. Viper sort/draw was 49-83 ms.
- Bugs worth remembering: the first back-face test was inverted (the renders
  were each model's far inside, lit as if facing us: measure what fraction of
  kept faces point at the camera); the packed face normals made geo an odd
  number of u16s, which misaligned everything carved after it in the scratch
  and put the table 2 bytes into the transform block (`_sizes()` rounds each
  part to 4 now); and an un-watchdogged probe hung the board with USB down.
- Bigger models, button 3 pause: each model file carries its own focal
  length, the largest that keeps it inside the 240x200 window (4 px margin)
  through a whole turn at the demo's tilt (`make_meshes.focal()`), so every
  projected value stays positive: teapot 332, bunny 292 (was 190 for both).
- Painter's algorithm vs the teapot: the original spout and handle run into
  the body, and sorting by triangle depth can't order surfaces that cut each
  other (dark jagged patches at the spout's base). `make_meshes` tessellates
  the spout and handle twice as finely and drops their triangles inside the
  body (a surface of revolution: nearer the axis than its radius at that
  height). Teapot now 2,065 vertices, 3,926 triangles; scratch 46 KB.
- Bigger models cost pixels (teapot Phong 29 ms, 20 fps). Normals are now
  scaled by 63, not 64, so table indices never pass 63 and the asm drops the
  clamps; and each row skips to the triangle's single run of pixels, paints
  it and stops. Teapot Phong 26 ms; whole frames 30 fps everywhere again,
  all frames still bit-identical.
- Quad wireframe (button 2's second mode): `make_meshes.quad_edges()` pairs
  triangles that share their longest edge and are nearly flat together (best
  first), and stores per triangle an edge mask without the quad's diagonal;
  mesh.draw mode 3 draws only those edges. The teapot comes back as Newell's
  patch grid (3,434 of 3,926 triangles paired); the scanned bunny is
  quad-dominant (2,524 of 3,851). The masks sit after the index block in the
  file, not in the records: 8-byte records cost a third more PSRAM reads in
  every mode and teapot Phong fell to 24 fps; with 6-byte records again, all
  five modes hold 30 fps, all bit-identical.
- Colors and order: each model has its own color (teapot a cooler glazed
  clay, bunny light gray: `make_mesh_luts.MODELS`), so mesh_luts.bin holds 3
  tables per model (48 KB) and the board copies in the one for the current
  model and mode. Wireframes: quads white, triangles green (`meshview.WIRES`).
  Button 2 order: quads (the start), triangles, Lambert, Phong, Blinn.

## Boot menu (step 8)

`app/menu.py`, run by `code.py`: the four demos with 80x50 thumbnails
(`tools/make_menu_thumbs.py` renders them with each demo's desktop reference;
`assets/menu_*.bmp`, deployed with the other assets), drawn with displayio,
`terminalio.FONT` and adafruit_display_text. Button 3 up, 2 down, 1 starts.

- A demo starts as a fresh run of its own file:
  `supervisor.set_next_code_file("/x_demo.py")` then `supervisor.reload()`.
  Importing it into the menu's session would leave the menu's objects on the
  heap, and every demo needs to allocate its SRAM buffers first thing.
  `set_next_code_file` lasts one run, so reset (or Ctrl-D) comes back to the
  menu, with the first demo (VoxelSpace) highlighted.
- Checked by doing what button 1 does from the REPL for each demo: all four
  start at their usual speeds, with no PSRAM warnings.
- Button help in every demo: `Display.text()` / `lines()` draw the built-in
  6 x 12 terminalio font straight onto the screen, once at startup, in the
  border around the demo's image (above/below the 320x200 and 240x200
  images, beside the 240x240 Cornell box). Frames only copy into the image,
  so the text stays and costs nothing per frame. The 3D models' window
  background is now black, like the border, so the window doesn't show.
- The 3D models demo shows the current shader in its top border (`shader:
  quad / tri / Lambert / Phong / Blinn`, `meshview.LABELS`), redrawn on each
  button 2 press: `Display.fill()` clears the strip, then `text()`.
