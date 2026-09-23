"""Draw the Bauhaus icon (circle, square, triangle) as PNG, stdlib only."""
import struct
import sys
import zlib

PAPER, RED, BLUE, YELLOW = (243, 239, 228), (227, 49, 29), (29, 63, 187), (242, 194, 0)


def icon(n: int) -> bytes:
    rows = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            u, v = x / n, y / n
            c = PAPER
            if 0.5 <= u <= 0.9 and 0.5 <= v <= 0.9:
                c = BLUE
            if (u - 0.38) ** 2 + (v - 0.38) ** 2 <= 0.26 ** 2:
                c = RED
            # triangle: base on v=0.9 from u=0.1 to u=0.5, apex (0.3, 0.55)
            if 0.55 <= v <= 0.9 and abs(u - 0.3) <= 0.2 * (v - 0.55) / 0.35:
                c = YELLOW
            row += bytes(c)
        rows.append(b"\x00" + bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


for size, path in ((180, "site/icon.png"), (512, "site/icon-512.png")):
    open(path, "wb").write(icon(size))
