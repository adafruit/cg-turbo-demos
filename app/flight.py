"""The automatic fly-over path, shared by the demo and the desktop tools."""

import math


class Flight:
    ABOVE = 60  # flying height over the terrain ahead
    SPEED = 1.5  # texels per frame

    def __init__(self, space, x=200.0, y=330.0):
        self.space = space
        self.x = x
        self.y = y
        self.height = space.height_at(x, y) + self.ABOVE
        self.frame = 0

    def step(self):
        """Advance one frame and point the camera."""
        space = self.space
        angle = 0.6 + 0.8 * math.sin(self.frame * 0.004)
        fx = -math.sin(angle)
        fy = -math.cos(angle)
        self.x += fx * self.SPEED
        self.y += fy * self.SPEED
        ground = max(space.height_at(self.x, self.y), space.height_at(self.x + fx * 40, self.y + fy * 40))
        self.height += (ground + self.ABOVE - self.height) * 0.05
        space.view(self.x, self.y, self.height, angle, 60)
        self.frame += 1
