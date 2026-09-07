import json

import numpy as np
import pytest
from PIL import Image

from parr import preset


def inputs(tmp_path):
    source, graded = tmp_path / 'source', tmp_path / 'v3'
    source.mkdir()
    graded.mkdir()
    for name in ['120000_ungraded.jpg', '120000_parr.jpg']:
        Image.fromarray(np.full((8, 10, 3), 100, dtype=np.uint8)).save(source / name)
    Image.fromarray(np.full((8, 10, 3), 120, dtype=np.uint8)).save(
        graded / '120000_ungraded_parr.jpg')
    record = {'original': '120000_ungraded.jpg', 'grain_seed': 17,
              'lut_sha1': 'test-baseline'}
    (source / 'captures.jsonl').write_text(json.dumps(record) + '\n')
    baseline = preset.write_starter(tmp_path / 'baseline')
    return source, graded, baseline


def test_freeze_copies_triplets_and_detects_later_corruption(tmp_path):
    from parr.experiments.regression import freeze_regression, verify_snapshot
    source, graded, baseline = inputs(tmp_path)
    before = (source / '120000_ungraded.jpg').read_bytes()
    out = tmp_path / 'snapshot'
    manifest = freeze_regression(source, graded, out, baseline)
    assert len(manifest['captures']) == 1
    assert manifest['captures'][0]['capture']['grain_seed'] == 17
    assert verify_snapshot(out)['files_verified'] == 6
    assert (source / '120000_ungraded.jpg').read_bytes() == before
    photo = out / manifest['captures'][0]['files']['ungraded']['path']
    photo.write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='checksum'):
        verify_snapshot(out)


def test_freeze_refuses_missing_triplet_and_existing_output(tmp_path):
    from parr.experiments.regression import freeze_regression
    source, graded, baseline = inputs(tmp_path)
    out = tmp_path / 'snapshot'
    out.mkdir()
    with pytest.raises(FileExistsError):
        freeze_regression(source, graded, out, baseline)
    (source / '120000_parr.jpg').unlink()
    with pytest.raises(FileNotFoundError):
        freeze_regression(source, graded, tmp_path / 'new', baseline)
    assert not (tmp_path / 'new').exists()


def test_freeze_requires_unique_capture_metadata(tmp_path):
    from parr.experiments.regression import freeze_regression
    source, graded, baseline = inputs(tmp_path)
    log = source / 'captures.jsonl'
    log.write_text(log.read_text() * 2)
    with pytest.raises(ValueError, match='duplicate'):
        freeze_regression(source, graded, tmp_path / 'snapshot', baseline)
