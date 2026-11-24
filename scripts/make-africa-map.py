#!/usr/bin/env python3
"""Generate the local Africa SVG used by the EDUNOVA homepage.

The only input is Natural Earth's public-domain Admin 0 countries GeoJSON.
The script uses the Python standard library only.

Usage:
    python scripts/make-africa-map.py
    python scripts/make-africa-map.py --input path/to/ne_110m_admin_0_countries.geojson
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path
from typing import Iterable

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_110m_admin_0_countries.geojson"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "frontend/assets/afrique-map.svg"

VIEWBOX = 800.0
PADDING = 54.0
LAND = "#16264A"
OUTLINE = "#19A7A0"
HIGHLIGHT = "#E9B44C"


def load_geojson(input_path: Path | None) -> dict:
    if input_path is not None:
        with input_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "EDUNOVA-map-builder/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def iter_coordinates(geometry: dict) -> Iterable[tuple[float, float]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if kind == "Polygon":
        for ring in coordinates:
            for point in ring:
                yield point[0], point[1]
    elif kind == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for point in ring:
                    yield point[0], point[1]


def polygon_rings(geometry: dict) -> list[list[tuple[float, float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if kind == "Polygon":
        return [[(point[0], point[1]) for point in ring] for ring in coordinates]
    if kind == "MultiPolygon":
        return [
            [(point[0], point[1]) for point in ring]
            for polygon in coordinates
            for ring in polygon
        ]
    return []


def fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def make_path(geometry: dict, project) -> str:
    pieces: list[str] = []
    for ring in polygon_rings(geometry):
        if len(ring) < 3:
            continue
        segments = []
        for index, point in enumerate(ring):
            x, y = project(*point)
            segments.append(("M" if index == 0 else "L") + fmt(x) + " " + fmt(y))
        pieces.append(" ".join(segments) + " Z")
    return " ".join(pieces)


def arc_path(project, start: tuple[float, float], end: tuple[float, float], lift: float) -> str:
    sx, sy = project(*start)
    ex, ey = project(*end)
    mx, my = (sx + ex) / 2, (sy + ey) / 2
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    cx, cy = mx + nx * lift, my + ny * lift
    return f"M {fmt(sx)} {fmt(sy)} Q {fmt(cx)} {fmt(cy)} {fmt(ex)} {fmt(ey)}"


def build_svg(features: list[dict]) -> str:
    countries = [
        feature
        for feature in features
        if feature.get("properties", {}).get("CONTINENT") == "Africa"
    ]
    if not countries:
        raise ValueError("Aucun pays africain trouvé dans le GeoJSON Natural Earth.")

    points = [point for feature in countries for point in iter_coordinates(feature["geometry"])]
    min_lon = min(point[0] for point in points)
    max_lon = max(point[0] for point in points)
    min_lat = min(point[1] for point in points)
    max_lat = max(point[1] for point in points)

    available = VIEWBOX - 2 * PADDING
    scale = min(available / (max_lon - min_lon), available / (max_lat - min_lat))
    used_width = (max_lon - min_lon) * scale
    used_height = (max_lat - min_lat) * scale
    offset_x = (VIEWBOX - used_width) / 2 - min_lon * scale
    offset_y = (VIEWBOX - used_height) / 2 + max_lat * scale

    def project(lon: float, lat: float) -> tuple[float, float]:
        return lon * scale + offset_x, offset_y - lat * scale

    highlighted = [
        feature
        for feature in countries
        if feature["properties"].get("ADM0_A3") == "CIV"
        or feature["properties"].get("ISO_A3") == "CIV"
    ]
    if not highlighted:
        raise ValueError("La Côte d'Ivoire est absente du GeoJSON Natural Earth.")

    civ_rings = polygon_rings(highlighted[0]["geometry"])
    main_ring = max(civ_rings, key=len)
    civ_lon = sum(point[0] for point in main_ring) / len(main_ring)
    civ_lat = sum(point[1] for point in main_ring) / len(main_ring)
    civ_x, civ_y = project(civ_lon, civ_lat)

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(VIEWBOX)} {fmt(VIEWBOX)}" role="img" aria-label="Carte de l’Afrique, Côte d’Ivoire en or">',
        "  <title>Carte de l’Afrique — Côte d’Ivoire</title>",
        f'  <g fill="{LAND}" stroke="{OUTLINE}" stroke-width="1.35" stroke-linejoin="round" fill-rule="evenodd">',
    ]
    for feature in countries:
        properties = feature["properties"]
        is_civ = (
            properties.get("ADM0_A3") == "CIV" or properties.get("ISO_A3") == "CIV"
        )
        if is_civ:
            continue
        lines.append(f'    <path d="{make_path(feature["geometry"], project)}"/>')
    lines.append("  </g>")

    lines.append(
        f'  <path d="{make_path(highlighted[0]["geometry"], project)}" '
        f'fill="{HIGHLIGHT}" fill-rule="evenodd" stroke="{HIGHLIGHT}" '
        'stroke-width="1.6" stroke-linejoin="round"/>'
    )

    arcs = [
        ((11.5, 32.0), -18.0),
        ((3.4, 6.5), 14.0),
        ((28.0, -2.0), -22.0),
        ((31.2, 30.0), 18.0),
        ((18.5, -33.5), 26.0),
    ]
    lines.append('  <g fill="none" stroke-linecap="round" aria-hidden="true">')
    for index, (destination, lift) in enumerate(arcs):
        color = HIGHLIGHT if index in (0, 2) else OUTLINE
        opacity = "0.58" if index in (0, 2) else "0.44"
        lines.append(
            f'    <path d="{arc_path(project, (civ_lon, civ_lat), destination, lift)}" '
            f'stroke="{color}" stroke-width="1.6" opacity="{opacity}"/>'
        )
    lines.append("  </g>")

    label_x = min(max(civ_x - 150, 18), VIEWBOX - 190)
    label_y = max(civ_y - 110, 34)
    line_end_x = label_x + 84
    line_end_y = label_y + 8
    lines.append('  <g aria-hidden="true">')
    lines.append(
        f'    <path d="M {fmt(line_end_x)} {fmt(line_end_y)} L {fmt(civ_x - 5)} {fmt(civ_y - 4)}" '
        f'stroke="{HIGHLIGHT}" stroke-width="1.4" opacity="0.75"/>'
    )
    lines.append(
        f'    <circle cx="{fmt(civ_x)}" cy="{fmt(civ_y)}" r="4.5" fill="{HIGHLIGHT}" '
        'stroke="#FFF7E6" stroke-width="1.2"/>'
    )
    lines.append("  </g>")
    lines.append(
        f'  <text x="{fmt(label_x)}" y="{fmt(label_y)}" fill="{HIGHLIGHT}" '
        'font-family="Arial, Helvetica, sans-serif" font-size="19" font-weight="700">'
        "Côte d'Ivoire</text>"
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="GeoJSON local plutôt qu'un téléchargement.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = load_geojson(args.input)
    svg = build_svg(data["features"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"SVG généré : {args.output}")


if __name__ == "__main__":
    main()
