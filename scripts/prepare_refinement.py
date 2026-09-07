"""Materialize the reviewed September 7 experiment selection without changing originals.

Run from the project root. This is a dated curation recipe, not automatic
photographer attribution or automatic scene recognition. Never overwrite a run.
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from parr.experiments.partitions import load_partition
from parr.experiments.regression import sha256, verify_snapshot

SOURCE_IDS = ('120804 120813 120819 120829 120839 120916 120926 120931 120937 '
              '120943 123755 123807 123815 123825 123835').split()
VALIDATION = {
    'dining-room': '125159 125212 125223 125235'.split(),
    'bathroom': '125250 125259'.split(),
    'street-from-window': '125841 125851 125903 125912'.split(),
}
REFERENCES = ([f'another-{i:03}.jpg' for i in range(6)] +
              ['artnet-last-resort-3104281.jpg'] +
              [f'artsy-{i:03}.jpg' for i in range(38, 45)] +
              [f'rocket-{i:03}.jpg' for i in [28, 30, 31, 32, 33, 34, 35, 36, 37]])
REFERENCE_VALIDATION = {'another-000.jpg': 'sunbather-closeup',
                        'artsy-039.jpg': 'sunbather-closeup',
                        'rocket-028.jpg': 'decorated-cakes',
                        'rocket-031.jpg': 'decorated-cakes'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', type=Path, required=True)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    expected = {f'{stem}_ungraded.jpg' for stem in SOURCE_IDS}
    if {p.name for p in args.camera.glob('*_ungraded.jpg')} != expected:
        raise ValueError('camera inventory changed; review the source selection before proceeding')
    verify_snapshot(args.snapshot)
    snapshot = json.loads((args.snapshot / 'manifest.json').read_text())
    reference_manifest = json.loads((args.references / 'manifest.json').read_text())
    reference_records = {r['file']: r for r in reference_manifest['images']}
    decisions = []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.inputs-', dir=args.out.parent) as tmp:
        staging = Path(tmp) / 'inputs'
        staging.mkdir()

        def copy(path, relative):
            digest = sha256(path)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            if sha256(destination) != digest or sha256(path) != digest:
                raise ValueError(f'input changed: {path}')
            return {'file': relative, 'sha256': digest, 'original_path': str(path.resolve())}

        camera = []
        for stem in SOURCE_IDS:
            name = f'{stem}_ungraded.jpg'
            camera.append({**copy(args.camera / name, f'camera/sept06-{name}'),
                           'group': 'bedroom', 'role': 'train'})
        for group, ids in VALIDATION.items():
            for stem in ids:
                record = next(r for r in snapshot['captures'] if r['id'] == stem)
                item = record['files']['ungraded']
                camera.append({**copy(args.snapshot / item['path'], f'camera/sept07-{stem}.jpg'),
                               'group': group, 'role': 'validation'})
        references, duplicate_groups = [], set()
        for name in REFERENCES:
            record = reference_records[name]
            group = record['duplicate_group']
            if group in duplicate_groups:
                raise ValueError(f'duplicate reference group: {group}')
            duplicate_groups.add(group)
            if sha256(args.references / name) != record['sha256']:
                raise ValueError(f'reference changed since prior curation: {name}')
            item = copy(args.references / name, f'references/{name}')
            references.append({**item, 'role': 'validation' if name in REFERENCE_VALIDATION
                               else 'train', 'group': REFERENCE_VALIDATION.get(name, group),
                               'provenance': record})
        for record in reference_manifest['images']:
            selected = record['file'] in REFERENCES
            decisions.append({'file': record['file'], 'selected': selected,
                              'reason': ('Documented publisher/gallery attribution; clean '
                                         'direct-lit colour, skin, food or seaside image; reviewed.'
                                         if selected else
                                         'Outside this coherent pilot subset: provisional personal/'
                                         'Pinterest attribution or broader ambient look.')})
        shutil.copytree(args.snapshot / 'baseline', staging / 'baseline')
        copy(args.camera / 'captures.jsonl', 'source-captures.jsonl')
        files = {
            'camera.json': {'records': camera,
                            'note': 'One training room; three scene-held-out development groups.'},
            'references.json': {'records': references,
                                'licence_policy': reference_manifest['licence_policy']},
            'selection.json': {'reference_decisions': decisions,
                              'source_date': '2026-09-06',
                              'regression_bedroom': 'in-domain; not scene-held-out'},
            'exclusions.json': {'regression_sha256': [r['files']['ungraded']['sha256']
                                                      for r in snapshot['captures']]},
        }
        for name, payload in files.items():
            (staging / name).write_text(json.dumps(payload, indent=2) + '\n')
        excluded = files['exclusions.json']['regression_sha256']
        load_partition(staging / 'camera.json', staging, excluded)
        load_partition(staging / 'references.json', staging)
        if args.out.exists():
            raise FileExistsError(args.out)
        staging.rename(args.out)
    print(f'Prepared {len(camera)} camera and {len(references)} reference records in {args.out}')


if __name__ == '__main__':
    main()
