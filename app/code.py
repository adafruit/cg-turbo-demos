"""Run one demo: voxel_demo, cornell_demo, metaballs_demo or fb_bench.

Keep this file tiny: demos allocate their SRAM framebuffers first thing, and
anything imported before them uses up SRAM.
"""

DEMO = "metaballs_demo"

__import__(DEMO)
