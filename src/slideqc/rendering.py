"""Pure image rendering shared by the CLI and UI; no Streamlit dependency."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from .coordinates import thumbnail_bounds


def tile_bounds(tile: dict, dimensions: tuple[int, int], thumbnail_shape: tuple) -> tuple[int, int, int, int]:
    """Map a half-open level-0 footprint using each actual thumbnail dimension."""
    th, tw = thumbnail_shape[:2]
    return thumbnail_bounds(tile, dimensions, (tw, th))


def render_overlay(thumbnail: np.ndarray, mask: np.ndarray, tiles: list[dict],
                   dimensions: tuple[int, int], *, show_mask: bool = False,
                   selected_id=None) -> Image.Image:
    """Green check, orange cross+hatching, gray dotted state, selected black border.

    Only visited grid tiles are drawn: areas outside this coverage remain bare.
    Transparent fills leave the tissue visible for inspection.
    """
    base = Image.fromarray(thumbnail[:, :, :3]).convert("RGBA")
    if show_mask:
        tint = np.zeros((*mask.shape, 4), dtype=np.uint8)
        tint[mask.astype(bool)] = (28, 104, 179, 75)
        base = Image.alpha_composite(base, Image.fromarray(tint))
    overlay = Image.new("RGBA", base.size)
    draw = ImageDraw.Draw(overlay)
    for tile in tiles:
        x0, y0, x1, y1 = tile_bounds(tile, dimensions, thumbnail.shape)
        x1, y1 = max(x0, x1 - 1), max(y0, y1 - 1)
        status = tile["status"]
        color = {"acceptable": (12, 112, 89, 220), "rescan": (176, 66, 15, 240),
                 "unevaluated": (88, 89, 105, 220), "background": (108, 119, 120, 110)}[status]
        draw.rectangle((x0, y0, x1, y1), outline=color, width=1)
        if status == "rescan":
            w, h = x1-x0, y1-y0
            for shift in range(-h, w+1, 12):
                ax, ay = max(0, shift), max(0, -shift)
                bx, by = min(w, shift+h), min(h, w-shift)
                draw.line((x0+ax, y0+ay, x0+bx, y0+by), fill=(176, 66, 15, 90))
        if x1-x0 >= 12 and y1-y0 >= 12:
            cx, cy = (x0+x1)//2, (y0+y1)//2
            if status == "rescan":
                draw.line((cx-4, cy-4, cx+4, cy+4), fill=color, width=2)
                draw.line((cx-4, cy+4, cx+4, cy-4), fill=color, width=2)
            elif status == "acceptable":
                draw.line((cx-4, cy, cx-1, cy+3, cx+5, cy-4), fill=color, width=2)
            elif status == "unevaluated":
                draw.text((cx-3, cy-5), "?", fill=color)
        if tile["tile_id"] == selected_id:
            draw.rectangle((x0, y0, x1, y1), outline=(12, 20, 25, 255), width=3)
    return Image.alpha_composite(base, overlay).convert("RGB")


def rgba_on_white(rgba: np.ndarray) -> np.ndarray:
    if rgba.shape[2] == 3:
        return rgba
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255
    return np.rint(rgba[:, :, :3] * alpha + 255 * (1-alpha)).astype(np.uint8)
