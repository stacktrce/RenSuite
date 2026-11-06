"""Draws the RenPy Suite icon (speech bubble + gear) as PNGs. Pure standard library.

The artwork is generated entirely from the shapes below, so it is original
and free of third-party rights. Run:  python tools/make_icon.py
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "renpy_suite" / "assets"
SIZES = (256, 128, 64, 48, 32, 16)

TOP_LEFT = (0x7B, 0x4D, 0xFF)
BOTTOM_RIGHT = (0xFF, 0x4F, 0x8B)
BUBBLE = (0xFA, 0xFA, 0xFF)


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def gradient(x, y):
    return lerp(TOP_LEFT, BOTTOM_RIGHT, clamp((x * 0.6 + y * 0.4)))


def sd_round_rect(px, py, cx, cy, hw, hh, r):
    qx = abs(px - cx) - (hw - r)
    qy = abs(py - cy) - (hh - r)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    return outside + min(max(qx, qy), 0.0) - r


def sd_triangle(px, py, a, b, c):
    def seg(px, py, ax, ay, bx, by):
        ex, ey = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        t = clamp((wx * ex + wy * ey) / (ex * ex + ey * ey))
        dx, dy = wx - ex * t, wy - ey * t
        return dx * dx + dy * dy, ex * wy - ey * wx

    d = 1e9
    signs = []
    for (ax, ay), (bx, by) in ((a, b), (b, c), (c, a)):
        dist2, cross = seg(px, py, ax, ay, bx, by)
        d = min(d, dist2)
        signs.append(cross)
    inside = all(s >= 0 for s in signs) or all(s <= 0 for s in signs)
    return -math.sqrt(d) if inside else math.sqrt(d)


def smin(a, b, k):
    h = clamp(0.5 + 0.5 * (b - a) / k)
    return b + (a - b) * h - k * h * (1 - h)


def sd_bubble(x, y):
    body = sd_round_rect(x, y, 0.5, 0.44, 0.31, 0.23, 0.13)
    tail = sd_triangle(x, y, (0.29, 0.56), (0.22, 0.81), (0.47, 0.64))
    return smin(body, tail, 0.03)


def sd_gear(x, y):
    cx, cy = 0.5, 0.44
    dx, dy = x - cx, y - cy
    r = math.hypot(dx, dy)
    theta = math.atan2(dy, dx) + math.pi / 8
    wave = math.cos(8 * theta)
    tooth = 0.045 * clamp((wave + 0.25) / 0.5)
    outer = r - (0.125 + tooth)
    hole = 0.05 - r
    return max(outer, hole)


def coverage(d, px_size, soft=0.0):
    width = px_size + soft
    return clamp(0.5 - d / width)


def over(dst, src_rgb, src_a):
    dr, dg, db, da = dst
    out_a = src_a + da * (1 - src_a)
    if out_a <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    mix = lambda s, d: (s * src_a + d * da * (1 - src_a)) / out_a  # noqa: E731
    return (mix(src_rgb[0], dr), mix(src_rgb[1], dg), mix(src_rgb[2], db), out_a)


def render(n):
    px = 1.0 / n
    rows = []
    for j in range(n):
        y = (j + 0.5) / n
        row = bytearray([0])
        for i in range(n):
            x = (i + 0.5) / n
            col = (0.0, 0.0, 0.0, 0.0)
            bg = sd_round_rect(x, y, 0.5, 0.5, 0.47, 0.47, 0.21)
            a = coverage(bg, px)
            if a > 0:
                col = over(col, gradient(x, y), a)
                shadow = sd_bubble(x, y - 0.03)
                col = over(col, (20, 0, 40), 0.28 * coverage(shadow, px, soft=0.05) * a)
                bubble = coverage(sd_bubble(x, y), px) * a
                col = over(col, BUBBLE, bubble)
                gear = coverage(sd_gear(x, y), px) * bubble
                col = over(col, gradient(x, y), gear)
            r, g, b, alpha = col
            row += bytes((int(r + 0.5), int(g + 0.5), int(b + 0.5), int(alpha * 255 + 0.5)))
        rows.append(bytes(row))
    return b"".join(rows)


def png(n, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ico(images) -> bytes:
    """A Windows .ico holding PNG images (supported since Windows Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for n, data in images:
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    return header + entries + blobs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    images = []
    for n in SIZES:
        data = png(n, render(n))
        (OUT / ("icon-%d.png" % n)).write_bytes(data)
        images.append((n, data))
        print("wrote", OUT / ("icon-%d.png" % n))
    (OUT / "icon.ico").write_bytes(ico(sorted(images)))
    print("wrote", OUT / "icon.ico")


if __name__ == "__main__":
    main()
