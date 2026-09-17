"""Small-data pilot training with explicit, checksum-checked scene partitions."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from ..artifacts import Artifacts, write_artifact
from ..normalize import NormalizeParams
from ..train.dataset import CorpusSplit, SampleConfig, build_pool, corpus_sha1
from ..train.evaluate import check_gates, evaluate
from ..train.fit import FitConfig, _code_revision, _dependency_versions, fit
from ..train.report import write_report
from ..train.transport import hue_weights
from .partitions import load_partition
from .regression import sha256


def train_candidate(root, out, cfg=None, sample_cfg=None):
    root, out = Path(root).resolve(), Path(out)
    if out.exists():
        raise FileExistsError(out)
    cfg, sample_cfg = cfg or FitConfig(), sample_cfg or SampleConfig()
    excluded = json.loads((root / 'exclusions.json').read_text())['regression_sha256']
    src_train, src_val = load_partition(root / 'camera.json', root, excluded)
    tgt_train, tgt_val = load_partition(root / 'references.json', root)
    if set(src_train + src_val) & set(tgt_train + tgt_val):
        raise ValueError('camera and reference corpora overlap')
    base = Artifacts.load(root / 'baseline')
    target_norm = NormalizeParams(white_balance=False, levels=False)

    def corpus(train, val, norm):
        return CorpusSplit(train, val, build_pool(train, norm, sample_cfg),
                           build_pool(val, norm, sample_cfg), corpus_sha1(train + val))

    print(f'camera: {len(src_train)} train / {len(src_val)} scene-held-out development', flush=True)
    print(f'references: {len(tgt_train)} train / {len(tgt_val)} validation', flush=True)
    source = corpus(src_train, src_val, base.normalize)
    target = corpus(tgt_train, tgt_val, target_norm)
    package = Path(__file__).resolve().parents[1]
    code_hashes = {str(p.relative_to(package)): sha256(p) for p in sorted(package.rglob('*.py'))}
    started = time.perf_counter()
    result = fit(source.train_pool, target.train_pool, cfg, print)
    weights = hue_weights(source.val_pool.lab, target.val_pool.lab, cfg.hue_bins, cfg.chroma_floor)
    metrics = evaluate(result.lut, source.val_pool, target.val_pool, weights,
                       source.train_pool, target.train_pool, result.target_weights,
                       result.transported_lab, n_bins=cfg.hue_bins,
                       chroma_floor=cfg.chroma_floor, seed=cfg.seed)
    metrics['held_out_eval'] = True
    gates = check_gates(metrics)
    provenance = {
        'kind': 'camera-scene-partition-pilot', 'trained': True,
        'exploratory_small_data': len(src_train) < 30 or len(tgt_train) < 200,
        'evaluation_kind': 'scene-held-out development; not blind final test',
        'source_train': [str(p.relative_to(root)) for p in src_train],
        'source_validation': [str(p.relative_to(root)) for p in src_val],
        'target_train': [str(p.relative_to(root)) for p in tgt_train],
        'target_validation': [str(p.relative_to(root)) for p in tgt_val],
        'source_partition': json.loads((root / 'camera.json').read_text()),
        'target_partition': json.loads((root / 'references.json').read_text()),
        'exclusions_sha256': sha256(root / 'exclusions.json'),
        'source_corpus_sha1': source.corpus_sha1, 'target_corpus_sha1': target.corpus_sha1,
        'parent_normalization_lut_sha1': base.lut_sha1,
        'target_normalize': target_norm.to_dict(), 'fit': asdict(cfg),
        'sample': {**asdict(sample_cfg), 'partition_mode': 'explicit; val_fraction unused'},
        'code_revision': _code_revision(), 'dependency_versions': _dependency_versions(),
        'code_sha256': code_hashes,
        'elapsed_seconds': round(time.perf_counter() - started, 2),
        'gates': [asdict(g) for g in gates],
        'limitations': ['One source room; no broad camera calibration claim.',
                        'The development scenes have already been visually reviewed.',
                        'Reference distribution similarity is not photographer fidelity.'],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pilot-', dir=out.parent) as temporary:
        staging = Path(temporary) / 'artifact'
        write_artifact(staging, result.lut, base.normalize, base.grain, provenance)
        write_report(staging / 'report', result.lut, metrics, gates, source, target,
                     base.normalize, target_norm, sample_cfg)
        Artifacts.load(staging)
        if out.exists():
            raise FileExistsError(out)
        # Unlike artifacts.publish, rename never backs up/deletes another run.
        # A concurrently published (nonempty) artifact also makes rename fail.
        staging.rename(out)
    return {'metrics': metrics, 'gates': [asdict(g) for g in gates]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--neutral-cap', type=float, default=0.005)
    args = parser.parse_args()
    result = train_candidate(args.inputs, args.out, FitConfig(neutral_axis_cap=args.neutral_cap))
    for gate in result['gates']:
        print(f"{'PASS' if gate['passed'] else 'FAIL'}: {gate['name']}: {gate['detail']}")
    raise SystemExit(0 if all(g['passed'] for g in result['gates']) else 3)


if __name__ == '__main__':
    main()
