"""
Generate a favicon and app icon with an octagon + static design.

The icon features an octagon shape filled with random static noise.
50% of the static pixels are grayscale (black/white) and the other
50% are random colors.

All sizes are generated from the same base 512×512 image so the
static pattern is identical across sizes — just scaled differently.

Outputs:
    static/favicon.ico  — 32×32 favicon
    static/icon-192.png — 192×192 app icon (PWA)
    static/icon-512.png — 512×512 app icon (PWA)

Usage:
    python scripts/generate_icons.py
"""

import math
import os
import random

from PIL import Image


def _point_in_polygon(
    px: float, py: float,
    vertices: list[tuple[float, float]],
) -> bool:
    """Check if point (px, py) is inside a convex polygon using the
    cross-product method (all cross products must have the same sign)."""
    n = len(vertices)
    sign = None
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        if cross != 0:
            if sign is None:
                sign = cross > 0
            elif (cross > 0) != sign:
                return False
    return True


def _regular_polygon_vertices(
    cx: float, cy: float, radius: float, n: int,
) -> list[tuple[float, float]]:
    """Return the vertices of a regular n-gon centered at (cx, cy).

    The first vertex is at the top (12 o'clock position).
    """
    vertices = []
    for i in range(n):
        angle = math.pi / 2 - 2 * math.pi * i / n  # start at top, go clockwise
        x = cx + radius * math.cos(angle)
        y = cy - radius * math.sin(angle)  # flip y for screen coords
        vertices.append((x, y))
    return vertices


def generate_base(size: int, seed: int = 42) -> Image.Image:
    """Generate a size×size icon with an octagon filled with static noise.

    50% of the static pixels are grayscale (black or white), and the
    other 50% are random colors.

    Args:
        size: Width and height of the output image in pixels.
        seed: Random seed for reproducible static patterns.

    Returns:
        An RGBA image with a transparent background and a static-filled
        octagon.
    """
    rng = random.Random(seed)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = img.load()

    # Octagon vertices — centered, taking up ~80% of the canvas
    margin = size * 0.1
    cx, cy = size / 2, size / 2
    radius = (size / 2) - margin
    vertices = _regular_polygon_vertices(cx, cy, radius, 8)

    for y in range(size):
        for x in range(size):
            if _point_in_polygon(x, y, vertices):
                if rng.random() < 0.5:
                    # Grayscale: black or white
                    v = 255 if rng.random() < 0.5 else 0
                    pixels[x, y] = (v, v, v, 255)
                else:
                    # Random color
                    pixels[x, y] = (
                        rng.randint(0, 255),
                        rng.randint(0, 255),
                        rng.randint(0, 255),
                        255,
                    )

    return img


def main() -> None:
    """Generate favicon and app icons from a single base image."""
    static_dir = os.path.join(
        os.path.dirname(__file__), "..", "static"
    )
    os.makedirs(static_dir, exist_ok=True)

    # Generate the base image at the highest resolution (512×512)
    base = generate_base(512)

    # Favicon — 32×32, scaled down from base
    favicon = base.resize((32, 32), Image.NEAREST)
    favicon_path = os.path.join(static_dir, "favicon.ico")
    favicon.save(favicon_path, format="ICO", sizes=[(32, 32)])
    print(f"Created: {favicon_path}")

    # 192×192 PWA icon, scaled down from base
    icon_192 = base.resize((192, 192), Image.NEAREST)
    path_192 = os.path.join(static_dir, "icon-192.png")
    icon_192.save(path_192, format="PNG")
    print(f"Created: {path_192}")

    # 512×512 PWA icon — the base image itself
    path_512 = os.path.join(static_dir, "icon-512.png")
    base.save(path_512, format="PNG")
    print(f"Created: {path_512}")

    print("Done.")


if __name__ == "__main__":
    main()
