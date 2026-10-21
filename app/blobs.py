"""The metaballs' motion: Lissajous paths, shared by the demo and the desktop tools."""

import math

# (radius, x speed, y speed, phase) per ball
PATHS = (
    (46, 0.31, 0.43, 0.0),
    (38, 0.47, 0.29, 1.3),
    (54, 0.23, 0.37, 2.1),
    (32, 0.53, 0.61, 3.7),
    (42, 0.41, 0.19, 4.4),
    (28, 0.67, 0.49, 5.2),
)


def positions(t, width, height):
    """(x, y, radius) of every ball at time t seconds."""
    balls = []
    for r, sx, sy, phase in PATHS:
        x = width / 2 + (width / 2 - r * 0.6) * math.sin(t * sx * 2 + phase)
        y = height / 2 + (height / 2 - r * 0.6) * math.sin(t * sy * 2 + phase * 1.7)
        balls.append((x, y, r))
    return balls
