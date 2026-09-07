import json

import numpy as np
import pytest
from PIL import Image

from parr.experiments.regression import freeze_regression
from parr.preset import write_starter


def test_paired_evaluation_is_deterministic_and_refuses_overwrite(tmp_path):
    from parr.experiments.evaluate import evaluate_candidates
    source, v3 = tmp_path / 'source', tmp_path / 'v3'
    source.mkdir()
    v3.mkdir()
    rgb = np.random.default_rng(4).integers(30, 220, (32, 40, 3), dtype=np.uint8)
    for path in [source / 'a_ungraded.jpg', source / 'a_parr.jpg', v3 / 'a_ungraded_parr.jpg']:
        Image.fromarray(rgb).save(path)
    (source / 'captures.jsonl').write_text(json.dumps(
        {'original': 'a_ungraded.jpg', 'grain_seed': 20, 'lut_sha1': 'fixture'}))
    baseline = write_starter(tmp_path / 'baseline')
    snapshot = tmp_path / 'snapshot'
    freeze_regression(source, v3, snapshot, baseline)
    one = evaluate_candidates(snapshot, {'candidate': baseline}, tmp_path / 'one')
    two = evaluate_candidates(snapshot, {'candidate': baseline}, tmp_path / 'two')
    assert one['captures'] == two['captures']
    a = tmp_path / 'one/images/a_candidate.jpg'
    b = tmp_path / 'two/images/a_candidate.jpg'
    assert a.read_bytes() == b.read_bytes()
    assert one['captures'][0]['variants']['candidate']['metrics'] == \
        one['captures'][0]['variants']['starter-control']['metrics']
    assert (tmp_path / 'one/contact-00.jpg').exists()
    with pytest.raises(FileExistsError):
        evaluate_candidates(snapshot, {'candidate': baseline}, tmp_path / 'one')


def test_empty_region_is_reported_as_empty_not_nan():
    from parr.experiments.evaluate import image_metrics
    result = image_metrics(np.zeros((10, 10, 3), dtype=np.uint8),
                           np.zeros((10, 10, 3), dtype=np.uint8))
    assert result['regions']['coloured_highlights'] == {'pixels': 0}
    json.dumps(result, allow_nan=False)
