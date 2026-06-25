#!/usr/bin/env python3
"""Generate the notch-mode Omi logo SVG from the canonical app icon.

The source app icon is a white rounded square with the black Omi dot mark.
This script extracts only the black dot geometry, writes a transparent SVG with
white dots, rasterizes it, and reports fit metrics against the original mask.
"""

from __future__ import annotations

import argparse
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class Dot:
    area: int
    x0: int
    y0: int
    x1: int
    y1: int
    cx: float
    cy: float

    @property
    def radius(self) -> float:
        # Area-derived radius best matches the original antialiased dot weight.
        return math.sqrt(self.area / math.pi)


def black_dot_mask(image: Image.Image, threshold: int = 80) -> set[tuple[int, int]]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    mask: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a > 128 and (r + g + b) / 3 < threshold:
                mask.add((x, y))
    return mask


def connected_components(mask: set[tuple[int, int]]) -> list[Dot]:
    seen: set[tuple[int, int]] = set()
    dots: list[Dot] = []
    for start in list(mask):
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        xs: list[int] = []
        ys: list[int] = []
        while queue:
            x, y = queue.pop()
            xs.append(x)
            ys.append(y)
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in mask and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        if len(xs) > 20:
            dots.append(
                Dot(
                    area=len(xs),
                    x0=min(xs),
                    y0=min(ys),
                    x1=max(xs),
                    y1=max(ys),
                    cx=sum(xs) / len(xs),
                    cy=sum(ys) / len(ys),
                )
            )
    return sorted(dots, key=lambda dot: math.atan2(dot.cy - 512.0, dot.cx - 512.0))


def svg_for_dots(dots: list[Dot]) -> str:
    min_x = min(dot.cx - dot.radius for dot in dots)
    min_y = min(dot.cy - dot.radius for dot in dots)
    max_x = max(dot.cx + dot.radius for dot in dots)
    max_y = max(dot.cy + dot.radius for dot in dots)
    view_width = max_x - min_x
    view_height = max_y - min_y
    circles = "\n".join(
        f'  <circle cx="{dot.cx:.3f}" cy="{dot.cy:.3f}" r="{dot.radius:.3f}" fill="white"/>'
        for dot in dots
    )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.3f} {min_y:.3f} {view_width:.3f} {view_height:.3f}">',
            "  <title>Omi notch logo</title>",
            circles,
            "</svg>",
            "",
        ]
    )


def white_alpha_mask(image: Image.Image, threshold: int = 128) -> set[tuple[int, int]]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    mask: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a > threshold and r > 128 and g > 128 and b > 128:
                mask.add((x, y))
    return mask


def render_dots(dots: list[Dot], width: int, height: int, scale: int = 4) -> Image.Image:
    canvas = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for dot in dots:
        cx = dot.cx * scale
        cy = dot.cy * scale
        radius = dot.radius * scale
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(255, 255, 255, 255),
        )
    return canvas.resize((width, height), Image.Resampling.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source = Image.open(args.source).convert("RGBA")
    width, height = source.size
    original_mask = black_dot_mask(source)
    dots = connected_components(original_mask)
    if len(dots) != 8:
        raise SystemExit(f"expected 8 logo dots, found {len(dots)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg_for_dots(dots), encoding="utf-8")

    rendered_png = (
        args.report.with_suffix(".png")
        if args.report
        else args.out.with_name(f"{args.out.stem}.fit.png")
    )
    rendered_png.parent.mkdir(parents=True, exist_ok=True)
    rendered_image = render_dots(dots, width, height)
    rendered_image.save(rendered_png)
    rendered_mask = white_alpha_mask(Image.open(rendered_png))

    intersection = len(original_mask & rendered_mask)
    union = len(original_mask | rendered_mask)
    iou = intersection / union if union else 0.0
    center = (sum(dot.cx for dot in dots) / len(dots), sum(dot.cy for dot in dots) / len(dots))
    radii = [dot.radius for dot in dots]
    lines = [
        f"source={args.source}",
        f"svg={args.out}",
        f"rendered={rendered_png}",
        f"dot_count={len(dots)}",
        f"mask_iou={iou:.4f}",
        f"center=({center[0]:.3f},{center[1]:.3f})",
        f"radius_min={min(radii):.3f}",
        f"radius_max={max(radii):.3f}",
        f"radius_mean={sum(radii) / len(radii):.3f}",
        "dots:",
    ]
    for index, dot in enumerate(dots):
        lines.append(
            f"  {index}: cx={dot.cx:.3f} cy={dot.cy:.3f} r={dot.radius:.3f} "
            f"bbox=({dot.x0},{dot.y0})-({dot.x1},{dot.y1}) area={dot.area}"
        )
    report = "\n".join(lines) + "\n"
    print(report, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
