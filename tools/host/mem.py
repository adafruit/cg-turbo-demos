"""Desktop stand-in for src/mem.py: there are no real addresses here."""

SRAM = 0x20000000


def address(buf):
    return 0


def zero(buf, words):
    memoryview(buf).cast("B")[: 4 * words] = bytes(4 * words)
