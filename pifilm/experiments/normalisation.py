"""Measure candidate normalisation parameters on a capture folder.

Phase 6 of the IMX708 roadmap: the levels lift brightened already-clipped
outdoor frames (53 of 108 pilot shots) and grey-world white balance stacked on
the ISP's AWB (up to 1.6x blue). This module re-normalises every original under
each candidate ``NormalizeParams``, applies the artifact's LUT with grain OFF so
only normalisation differs, and reports per shot and in aggregate:

- ``clip_pct``: percent of pixels with any channel >= 254 in the graded output.
- ``p1_luma`` / ``p5_luma``: 1st and 5th percentile of BT.709 luma of the graded
  output in [0, 1]. High values mean lifted, faded blacks.
- the applied ``gamma``, ``wb_blue``, ``highlight_frac`` and ``lift_weight``.

Aggregates are split indoor/outdoor by ``camera_metadata.Lux > 1500`` when a
``captures.jsonl`` sits beside the originals. A contact sheet shows
original | current | each candidate for named and sampled shots. Never changes
production defaults; outputs go to ``--out`` (gitignored).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from ..artifacts import Artifacts
from ..color import LUMA_709
from ..imageio import list_images, load_rgb
from ..normalize import NormalizeParams, normalize_u8

OUTDOOR_LUX = 1500.0
CLIP_LEVEL = 254
TILE_W = 480


def candidate_params(
    base: NormalizeParams, refs: list[float], no_wb: bool
) -> dict[str, NormalizeParams]:
    out = {"current": base}
    for ref in refs:
        out[f"ref={ref:g}"] = replace(base, levels_lift_highlight_ref=ref)
    if no_wb:
        for name, params in list(out.items()):
            out[f"{name}+nowb"] = replace(params, white_balance=False)
    return out


def grade(
    rgb_u8: np.ndarray, params: NormalizeParams, artifacts: Artifacts, lut_filter
) -> tuple[np.ndarray, object]:
    normalised, gains = normalize_u8(rgb_u8, params)
    graded = artifacts.lut.apply_pillow(normalised, lut_filter)
    return graded, gains


def measure(graded_u8: np.ndarray, gains) -> dict:
    clip = np.any(graded_u8 >= CLIP_LEVEL, axis=2)
    luma = (graded_u8.astype(np.float32) / 255.0) @ LUMA_709
    p1, p5 = np.percentile(luma, [1, 5])
    levels = gains.levels or {}
    return {
        "clip_pct": round(float(clip.mean() * 100.0), 3),
        "p1_luma": round(float(p1), 4),
        "p5_luma": round(float(p5), 4),
        "gamma": levels.get("gamma"),
        "wb_blue": round(float(gains.wb[2]), 4),
        "highlight_frac": levels.get("highlight_frac"),
        "lift_weight": levels.get("lift_weight"),
    }


def stem_of(path: Path) -> str:
    return path.stem.removesuffix("_original").removesuffix("_ungraded")


def load_lux(source: Path) -> dict[str, float]:
    log = source / "captures.jsonl"
    if not log.exists():
        return {}
    lux: dict[str, float] = {}
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        value = (rec.get("camera_metadata") or {}).get("Lux")
        if value is not None and rec.get("original"):
            lux[stem_of(Path(rec["original"]))] = float(value)
    return lux


def downscale(rgb_u8: np.ndarray, max_side: int) -> np.ndarray:
    im = Image.fromarray(rgb_u8)
    im.thumbnail((max_side, max_side))
    return np.asarray(im)


def aggregate(per_shot: dict[str, dict], lux: dict[str, float]) -> dict:
    def summarise(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0}
        clip = np.array([r["clip_pct"] for r in rows])
        gammas = np.array([r["gamma"] for r in rows if r["gamma"] is not None])
        return {
            "n": len(rows),
            "clip_pct_mean": round(float(clip.mean()), 3),
            "clip_pct_median": round(float(np.median(clip)), 3),
            "shots_clip_over_1pct": int((clip > 1.0).sum()),
            "p1_luma_median": round(float(np.median([r["p1_luma"] for r in rows])), 4),
            "p5_luma_median": round(float(np.median([r["p5_luma"] for r in rows])), 4),
            "gamma_min": round(float(gammas.min()), 3) if gammas.size else None,
            "gamma_median": round(float(np.median(gammas)), 3) if gammas.size else None,
            "gamma_max": round(float(gammas.max()), 3) if gammas.size else None,
        }

    rows = list(per_shot.values())
    result = {"all": summarise(rows)}
    if lux:
        outdoor = [m for s, m in per_shot.items() if lux.get(s, 0.0) > OUTDOOR_LUX]
        indoor = [m for s, m in per_shot.items() if s in lux and lux[s] <= OUTDOOR_LUX]
        result["outdoor"] = summarise(outdoor)
        result["indoor"] = summarise(indoor)
    return result


def contact_sheet(rows: list[tuple[str, list[np.ndarray]]], headers: list[str], out: Path) -> None:
    if not rows:
        Image.new("RGB", (TILE_W, 32), "white").save(out, quality=85)
        return
    tiles = [
        [ImageOps.contain(Image.fromarray(a), (TILE_W, TILE_W)) for a in imgs] for _, imgs in rows
    ]
    tile_h = max(t.height for row in tiles for t in row)
    label_h = 18
    width = TILE_W * len(headers)
    height = label_h + len(rows) * (tile_h + label_h)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    for c, name in enumerate(headers):
        draw.text((c * TILE_W + 4, 2), name, fill="black")
    y = label_h
    for (stem, _), row in zip(rows, tiles, strict=True):
        draw.text((4, y), stem, fill="black")
        for c, tile in enumerate(row):
            canvas.paste(tile, (c * TILE_W, y + label_h))
        y += tile_h + label_h
    canvas.save(out, quality=85)


def write_markdown(report: dict, out: Path) -> None:
    lines = ["# Normalisation candidates", ""]
    for name in report["candidates"]:
        lines.append(f"## {name}")
        for split, s in report["aggregate"][name].items():
            if s.get("n"):
                lines.append(
                    f"- **{split}** (n={s['n']}): clip mean {s['clip_pct_mean']}% / median "
                    f"{s['clip_pct_median']}%, shots >1% clipped {s['shots_clip_over_1pct']}, "
                    f"p1 {s['p1_luma_median']}, p5 {s['p5_luma_median']}, gamma "
                    f"{s['gamma_min']}/{s['gamma_median']}/{s['gamma_max']}"
                )
        lines.append("")
    out.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", type=Path, required=True, help="folder of *_original.jpg")
    parser.add_argument(
        "--artifacts", type=Path, default=None, help="artifact dir (default: bundled)"
    )
    parser.add_argument("--refs", default="0.02,0.05,0.10",
                        help="comma-separated levels_lift_highlight_ref candidates")
    parser.add_argument("--no-wb", action="store_true",
                        help="also evaluate every candidate with white_balance=False")
    parser.add_argument("--shots", default="", help="comma-separated stems always on the sheet")
    parser.add_argument("--sample", type=int, default=6, help="extra random shots on the sheet")
    parser.add_argument("--max-side", type=int, default=1536,
                        help="downscale originals to this before grading (speed)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    artifacts = Artifacts.resolve(args.artifacts)
    lut_filter = artifacts.lut.to_pillow()
    refs = [float(r) for r in args.refs.split(",") if r.strip()]
    cands = candidate_params(artifacts.normalize, refs, args.no_wb)
    originals = [
        p for p in list_images(args.source) if p.stem.endswith(("_original", "_ungraded"))
    ]
    if not originals:
        print(f"error: no *_original/_ungraded images in {args.source}", file=sys.stderr)
        return 1
    lux = load_lux(args.source)
    args.out.mkdir(parents=True, exist_ok=True)

    named = {s for s in args.shots.split(",") if s}
    rng = random.Random(args.seed)
    pool = [p for p in originals if stem_of(p) not in named]
    sheet_stems = named | {stem_of(p) for p in rng.sample(pool, min(args.sample, len(pool)))}

    per_shot: dict[str, dict[str, dict]] = {name: {} for name in cands}
    sheet_rows: list[tuple[str, list[np.ndarray]]] = []
    for path in originals:
        stem = stem_of(path)
        rgb = downscale(load_rgb(path)[0], args.max_side)
        graded_by = {}
        for name, params in cands.items():
            graded, gains = grade(rgb, params, artifacts, lut_filter)
            per_shot[name][stem] = measure(graded, gains)
            graded_by[name] = graded
        if stem in sheet_stems:
            sheet_rows.append((stem, [rgb, *graded_by.values()]))
        summary = ", ".join(f"{n} clip {m[stem]['clip_pct']}%" for n, m in per_shot.items())
        print(f"{stem}: {summary}")

    report = {
        "source": str(args.source),
        "artifacts": str(artifacts.path),
        "candidates": list(cands),
        "params": {name: p.to_dict() for name, p in cands.items()},
        "per_shot": per_shot,
        "aggregate": {name: aggregate(per_shot[name], lux) for name in cands},
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=1))
    write_markdown(report, args.out / "report.md")
    sheet_rows.sort(key=lambda r: r[0])
    contact_sheet(sheet_rows, ["original", *cands], args.out / "contact_sheet.jpg")
    print(f"wrote {args.out / 'report.json'}, report.md, contact_sheet.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
