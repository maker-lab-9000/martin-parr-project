"""Paired runtime comparisons with fixed grain seeds and input-defined region masks."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from ..artifacts import Artifacts
from ..color import srgb_to_oklab
from ..grain import add_grain
from ..imageio import load_rgb, save_jpeg
from ..normalize import normalize_u8
from ..pipeline import Pipeline
from ..train.evaluate import (
    channels_are_monotone,
    clipped_volume_fraction,
    grey_axis_is_monotone,
    neutral_axis_max_chroma,
)
from .regression import sha256, verify_snapshot


def image_metrics(rgb, reference):
    # Identical deterministic spatial sample and masks for every variant.
    sample, original = rgb[::4, ::4], reference[::4, ::4]
    lab = srgb_to_oklab(sample.astype(np.float32) / 255)
    base = srgb_to_oklab(original.astype(np.float32) / 255)
    c0 = np.linalg.norm(base[..., 1:], axis=-1)
    hue = np.degrees(np.arctan2(base[..., 2], base[..., 1])) % 360
    lightness = base[..., 0]
    masks = {
        'near_neutral': c0 < 0.02,
        'restrained_midtones': (c0 >= 0.02) & (c0 < 0.12) &
                               (lightness > 0.25) & (lightness < 0.75),
        'coloured_highlights': (c0 > 0.03) & (lightness > 0.75),
        'shaded_skin_proxy': (hue > 20) & (hue < 75) & (c0 > 0.025) & (c0 < 0.14) &
                             (lightness > 0.2) & (lightness < 0.65),
    }
    for name, low, high in [('red', 0, 35), ('orange', 35, 75),
                             ('green', 105, 180), ('blue', 230, 310)]:
        masks[name] = (c0 > 0.03) & (hue >= low) & (hue < high)

    def stats(mask):
        pixels = lab[mask]
        if not len(pixels):
            return {'pixels': 0}
        chroma = np.linalg.norm(pixels[:, 1:], axis=-1)
        return {'pixels': len(pixels), 'mean_L': float(pixels[:, 0].mean()),
                'std_L': float(pixels[:, 0].std()),
                'p95_L': float(np.percentile(pixels[:, 0], 95)),
                'mean_C': float(chroma.mean()), 'high_C_fraction': float((chroma > 0.12).mean()),
                'clipped_fraction': float(((sample[mask] <= 1) | (sample[mask] >= 254))
                                          .any(axis=-1).mean())}

    return {'all': stats(np.ones(lightness.shape, dtype=bool)),
            'regions': {name: stats(mask) for name, mask in masks.items()}}


def lut_safety(lut):
    return {'grey_monotone': grey_axis_is_monotone(lut),
            'channels_monotone': channels_are_monotone(lut),
            'neutral_max_chroma': neutral_axis_max_chroma(lut),
            'clipped_volume': clipped_volume_fraction(lut)}


def evaluate_candidates(snapshot, artifacts, out):
    snapshot, out = Path(snapshot), Path(out)
    if out.exists():
        raise FileExistsError(out)
    verify_snapshot(snapshot)
    frozen = json.loads((snapshot / 'manifest.json').read_text())
    loaded = {'starter-control': Artifacts.load(snapshot / 'baseline')}
    for name, path in artifacts.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name) or name in {
            'starter-control', 'ungraded', 'recorded-starter', 'recorded-v3'
        }:
            raise ValueError(f'invalid/reserved candidate name: {name}')
        loaded[name] = Artifacts.load(path)
    baseline = loaded['starter-control']
    for art in loaded.values():
        if art.normalize != baseline.normalize or art.grain != baseline.grain:
            raise ValueError('paired comparison requires identical normalization and grain')
    report = {'snapshot_sha256': sha256(snapshot / 'manifest.json'),
              'notes': ['Reviewed regression set, not a blind final test.',
                        'Metrics sample every fourth pixel; masks use normalized input.',
                        'Candidate metrics exclude grain. Recorded JPEGs include existing grain.',
                        'Shaded-skin mask is a colour-range proxy, not semantic segmentation.'],
              'artifacts': {name: {'lut_sha1': art.lut_sha1, 'safety': lut_safety(art.lut),
                                   'path': str(art.path.resolve())}
                            for name, art in loaded.items()}, 'captures': []}
    pipelines = {name: Pipeline(art) for name, art in loaded.items()}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.compare-', dir=out.parent) as temporary:
        staging = Path(temporary) / 'result'
        (staging / 'images').mkdir(parents=True)
        names = ['ungraded', 'recorded-starter', 'recorded-v3', *loaded]
        canvas = None
        for index, capture in enumerate(frozen['captures']):
            stem, seed = capture['id'], capture['capture']['grain_seed']
            original = load_rgb(snapshot / capture['files']['ungraded']['path'])[0]
            normalized, _ = normalize_u8(original, baseline.normalize)
            displayed = {'ungraded': original}
            variants = {}
            for role in ['starter', 'v3']:
                path = snapshot / capture['files'][role]['path']
                displayed[f'recorded-{role}'] = load_rgb(path)[0]
            for name, pipe in pipelines.items():
                result, info = pipe.process(original, grain=False)
                variants[name] = {'metrics': image_metrics(result, normalized), 'pipeline': info}
                rendered = (add_grain(result, pipe.artifacts.grain, np.random.default_rng(seed))
                            if pipe.artifacts.grain.enabled else result)
                displayed[name] = rendered
                save_jpeg(rendered, staging / 'images' / f'{stem}_{name}.jpg')
            for name in ['ungraded', 'recorded-starter', 'recorded-v3']:
                variants[name] = {'metrics': image_metrics(displayed[name], normalized)}
            report['captures'].append({'id': stem, 'grain_seed': seed, 'variants': variants})
            if index % 4 == 0:
                canvas = Image.new('RGB', (260 * len(names), 4 * 190), '#202020')
            draw = ImageDraw.Draw(canvas)
            for column, name in enumerate(names):
                thumb = ImageOps.contain(Image.fromarray(displayed[name]), (256, 150))
                x, y = column * 260, index % 4 * 190
                canvas.paste(thumb, (x, y + 20))
                draw.text((x + 2, y + 2), f'{stem} {name}', fill='white')
            if index % 4 == 3 or index == len(frozen['captures']) - 1:
                canvas.save(staging / f'contact-{index // 4:02}.jpg', quality=95)
        (staging / 'metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        if out.exists():
            raise FileExistsError(out)
        staging.rename(out)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True,
                        help='parent folder containing candidate artifact folders')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    variants = {p.name: p for p in sorted(args.artifacts.iterdir())
                if (p / 'params.json').is_file() and p.name != 'starter-control'}
    report = evaluate_candidates(args.snapshot, variants, args.out)
    print(f"Compared {len(report['captures'])} captures; report: {args.out}")


if __name__ == '__main__':
    main()
