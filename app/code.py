"""Boot into the demo menu (app/menu.py).

To run one demo directly while developing, set DEMO to its module instead:
voxel_demo, cornell_demo, metaballs_demo, meshes_demo or fb_bench. Keep this
file tiny: demos allocate their SRAM framebuffers first thing, and anything
imported before them uses up SRAM.
"""

DEMO = "menu"

__import__(DEMO)
