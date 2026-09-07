import json

import pytest

from parr.experiments.regression import sha256


def make_partition(tmp_path):
    records = []
    for name, group, role in [('a.jpg', 'room', 'train'), ('b.jpg', 'street', 'validation')]:
        path = tmp_path / name
        path.write_bytes(name.encode())
        records.append({'file': name, 'group': group, 'role': role, 'sha256': sha256(path)})
    manifest = tmp_path / 'partition.json'
    manifest.write_text(json.dumps({'records': records}))
    return manifest, records


def test_partition_enforces_groups_hashes_and_explicit_roles(tmp_path):
    from parr.experiments.partitions import load_partition
    manifest, records = make_partition(tmp_path)
    train, val = load_partition(manifest, tmp_path)
    assert [p.name for p in train] == ['a.jpg']
    assert [p.name for p in val] == ['b.jpg']
    records[1]['group'] = 'room'
    manifest.write_text(json.dumps({'records': records}))
    with pytest.raises(ValueError, match='scene'):
        load_partition(manifest, tmp_path)


@pytest.mark.parametrize('mutation', ['checksum', 'escape', 'role', 'excluded', 'duplicate'])
def test_partition_rejects_unsafe_inputs(tmp_path, mutation):
    from parr.experiments.partitions import load_partition
    manifest, records = make_partition(tmp_path)
    excluded = []
    if mutation == 'checksum':
        (tmp_path / 'a.jpg').write_bytes(b'changed')
    elif mutation == 'escape':
        records[0]['file'] = '../outside.jpg'
    elif mutation == 'role':
        records[0]['role'] = 'trian'
    elif mutation == 'excluded':
        excluded = [records[0]['sha256']]
    else:
        records.append(records[0].copy())
    manifest.write_text(json.dumps({'records': records}))
    with pytest.raises(ValueError):
        load_partition(manifest, tmp_path, excluded)
