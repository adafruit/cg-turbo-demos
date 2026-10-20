"""Small memory helpers."""

import micropython

SRAM = 0x20000000  # internal SRAM starts here; PSRAM is at 0x11000000


@micropython.viper
def address(buf: ptr8) -> int:
    """Where a buffer's data lives."""
    return int(buf)
