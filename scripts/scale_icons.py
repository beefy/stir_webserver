"""
Scale the existing favicon.ico up to produce the 192×192 and 512×512
PWA app icons.

The favicon.ico is a 32×32 image. This script reads it, scales it up
using nearest-neighbour interpolation (to preserve the pixel-art look),
and writes the results to static/icon-192.png and static/icon-512.png.

Outputs:
    static/icon-192.png — 192×192 app icon (PWA)
    static/icon-512.png — 512×512 app icon (PWA)

Usage:
    python scripts/scale_icons.py
"""

import os

from PIL import Image


def main() -> None:
    # Paths
    script_dir = os.path.dirname(__file__)
    project_root = os.path.join(script_dir, "..")
    favicon_path = os.path.join(project_root, "favicon.ico")
    static_dir = os.path.join(project_root, "static")
    os.makedirs(static_dir, exist_ok=True)

    # Open the favicon — PIL reads the first (32×32) frame from the ICO
    favicon = Image.open(favicon_path)
    print(f"Read favicon: {favicon.size[0]}×{favicon.size[1]}")

    # Scale up to 192×192
    icon_192 = favicon.resize((192, 192), Image.NEAREST)
    path_192 = os.path.join(static_dir, "icon-192.png")
    icon_192.save(path_192, format="PNG")
    print(f"Created: {path_192}")

    # Scale up to 512×512
    icon_512 = favicon.resize((512, 512), Image.NEAREST)
    path_512 = os.path.join(static_dir, "icon-512.png")
    icon_512.save(path_512, format="PNG")
    print(f"Created: {path_512}")

    print("Done.")


if __name__ == "__main__":
    main()
