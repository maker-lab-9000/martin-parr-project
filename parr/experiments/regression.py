"""Immutable-by-checksum snapshots of camera comparison triplets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ValueError(f'path escapes dataset: {relative}')
    return path


def verify_snapshot(root: str | Path) -> dict:
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    files = list(manifest['baseline'].values()) + [manifest['capture_log']]
    for record in manifest['captures']:
        files.extend(record['files'].values())
    for item in files:
        if sha256(checked_path(root, item['path'])) != item['sha256']:
            raise ValueError(f"checksum mismatch: {item['path']}")
    return {'files_verified': len(files), 'captures': len(manifest['captures'])}


def freeze_regression(source_dir, graded_dir, out_dir, baseline_dir) -> dict:
    source, graded, out, baseline = map(Path, (source_dir, graded_dir, out_dir, baseline_dir))
    if out.exists():
        raise FileExistsError(out)
    photos = sorted(graded.glob('*_ungraded_parr.jpg'))
    if not photos:
        raise ValueError('no comparison triplets')
    records = {}
    for line in (source / 'captures.jsonl').read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        name = record['original']
        if name in records:
            raise ValueError(f'duplicate capture metadata: {name}')
        records[name] = record
    manifest = {'version': 1, 'purpose': 'reviewed regression set; not a blind final test',
                'source_dir': str(source.resolve()), 'comparison_dir': str(graded.resolve()),
                'captures': [], 'baseline': {}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.freeze-', dir=out.parent) as staging_name:
        staging = Path(staging_name) / 'snapshot'
        staging.mkdir()

        def copy(path, relative):
            digest = sha256(path)
            dest = staging / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            if sha256(dest) != digest or sha256(path) != digest:
                raise ValueError(f'input changed during snapshot: {path}')
            return {'path': relative, 'sha256': digest}

        for photo in photos:
            stem = photo.name.removesuffix('_ungraded_parr.jpg')
            original = f'{stem}_ungraded.jpg'
            if original not in records or 'grain_seed' not in records[original]:
                raise ValueError(f'missing capture metadata/grain seed: {original}')
            sources = {'ungraded': source / original, 'starter': source / f'{stem}_parr.jpg',
                       'v3': photo}
            files = {role: copy(path, f'images/{stem}_{role}.jpg')
                     for role, path in sources.items()}
            dimensions = []
            for path in sources.values():
                with Image.open(path) as im:
                    dimensions.append(im.size)
            if len(set(dimensions)) != 1:
                raise ValueError(f'comparison dimensions differ: {stem}')
            manifest['captures'].append({'id': stem, 'size': list(dimensions[0]),
                                         'capture': records[original], 'files': files})
        for name in ['parr.cube', 'params.json']:
            manifest['baseline'][name] = copy(baseline / name, f'baseline/{name}')
        manifest['capture_log'] = copy(source / 'captures.jsonl', 'captures.jsonl')
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        verify_snapshot(staging)
        if out.exists():
            raise FileExistsError(out)
        staging.rename(out)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--graded', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=Path('parr/data'))
    args = parser.parse_args()
    freeze_regression(args.source, args.graded, args.out, args.baseline)
    print(json.dumps(verify_snapshot(args.out)))


if __name__ == '__main__':
    main()
