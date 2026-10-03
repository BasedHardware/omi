#!/usr/bin/env python3
"""
Convert Omi conversation export JSON to a standard GeoJSON FeatureCollection (RFC 7946).

Usage:
    python conversations_to_geojson.py conversations.json [conversations2.json ...] -o conversations.geojson

Options:
    -o, --output FILE         Output path for the GeoJSON file (default: conversations.geojson)
    --require-coords          Only include conversations that have valid geolocation coordinates
    --filter-category CAT     Filter conversations by category (e.g. work, personal)
    --force                   Overwrite output file if it already exists

Outputs a standard RFC 7946 GeoJSON FeatureCollection ready for import into
QGIS, Kepler.gl, Mapbox, Felt, geojson.io, or Google Earth.
Zero external dependencies (pure Python standard library).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def clean_text(value: Any) -> str:
    """Normalize text whitespace and return cleaned string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return " ".join(value.split())


def extract_coordinates(item: Dict[str, Any]) -> Optional[List[float]]:
    """Extract [longitude, latitude, optional altitude] from conversation item."""
    # Check top-level or nested geolocation dictionary
    geo = item.get("geolocation") or item.get("location") or {}
    if not isinstance(geo, dict):
        geo = {}

    lat = geo.get("latitude") if geo.get("latitude") is not None else item.get("latitude")
    lon = geo.get("longitude") if geo.get("longitude") is not None else item.get("longitude")
    alt = geo.get("altitude") if geo.get("altitude") is not None else item.get("altitude")

    if lat is None or lon is None:
        return None

    try:
        lat_f = float(lat)
        lon_f = float(lon)
        # Validate latitude and longitude ranges
        if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
            return None
        coords = [lon_f, lat_f]
        if alt is not None:
            try:
                coords.append(float(alt))
            except (ValueError, TypeError):
                pass
        return coords
    except (ValueError, TypeError):
        return None


def format_feature(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an Omi conversation item into a GeoJSON Feature."""
    coords = extract_coordinates(item)
    geometry = {"type": "Point", "coordinates": coords} if coords else None

    structured = item.get("structured") or {}
    title = clean_text(item.get("title") or structured.get("title") or "Untitled Conversation")
    overview = clean_text(structured.get("overview") or item.get("summary") or "")

    # Transcript snippet (up to 300 chars)
    transcript = clean_text(item.get("transcript") or "")
    snippet = transcript[:300] + ("..." if len(transcript) > 300 else "")

    geo = item.get("geolocation") or item.get("location") or {}
    if not isinstance(geo, dict):
        geo = {}

    props = {
        "id": item.get("id"),
        "title": title,
        "category": clean_text(item.get("category")),
        "started_at": item.get("started_at") or item.get("created_at"),
        "finished_at": item.get("finished_at") or item.get("ended_at"),
        "duration_seconds": item.get("duration_seconds") or item.get("duration"),
        "location_name": clean_text(geo.get("location_name") or geo.get("name")),
        "address": clean_text(geo.get("address")),
        "overview": overview,
        "transcript_snippet": snippet,
    }

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": props
    }


def load_conversations(sources: Sequence[str]) -> List[Dict[str, Any]]:
    """Parse and deduplicate conversations from multiple JSON export files."""
    seen_ids = set()
    items = []

    for src in sources:
        p = Path(src)
        if not p.is_file():
            raise FileNotFoundError(f"Input file not found: {src}")
        raw = p.read_text(encoding="utf-8").lstrip("\ufeff")
        payload = json.loads(raw)

        if isinstance(payload, dict):
            for key in ("conversations", "items", "data"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break

        if not isinstance(payload, list):
            raise ValueError(f"{src}: expected JSON array or object containing conversations list")

        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(f"{src}: each conversation must be a JSON object")
            conv_id = item.get("id")
            if not conv_id:
                raise ValueError(f"{src}: conversation missing required 'id' field")

            if conv_id in seen_ids:
                continue
            seen_ids.add(conv_id)
            items.append(item)

    return items


def export_geojson(
    conversations: List[Dict[str, Any]],
    require_coords: bool = False,
    category_filter: Optional[str] = None
) -> Dict[str, Any]:
    """Generate a standard GeoJSON FeatureCollection."""
    features = []

    for item in conversations:
        if category_filter:
            item_cat = clean_text(item.get("category")).lower()
            if item_cat != category_filter.lower():
                continue

        feat = format_feature(item)
        if require_coords and feat["geometry"] is None:
            continue
        features.append(feat)

    return {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "omi-conversations-to-geojson",
            "total_features": len(features)
        },
        "features": features
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation export JSON to GeoJSON FeatureCollection."
    )
    parser.add_argument("inputs", nargs="+", help="One or more JSON files exported from omi conversation list")
    parser.add_argument("-o", "--output", default="conversations.geojson", help="Output GeoJSON file path")
    parser.add_argument("--require-coords", action="store_true", help="Only include conversations with coordinates")
    parser.add_argument("--filter-category", default=None, help="Filter conversations by category")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output file")

    args = parser.parse_args(argv)

    out_path = Path(args.output)
    if ".." in out_path.parts:
        sys.stderr.write("Error: Path traversal ('..') is not allowed in output path.\n")
        return 2

    if out_path.exists() and not args.force:
        sys.stderr.write(f"Error: Output file already exists: {out_path}. Use --force to overwrite.\n")
        return 1

    try:
        conversations = load_conversations(args.inputs)
        geojson_data = export_geojson(
            conversations,
            require_coords=args.require_coords,
            category_filter=args.filter_category
        )
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(geojson_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(geojson_data['features'])} features to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
