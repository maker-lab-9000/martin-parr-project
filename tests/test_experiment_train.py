import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from parr.artifacts import Artifacts
from parr.experiments.regression import sha256
from parr.preset import write_starter
from parr.train.dataset import SampleConfig
from parr.train.fit import FitConfig


def training_inputs(tmp_path):
    root = tmp_path / 'inputs'
    root.mkdir()
    write_starter(root / 'baseline')
    for corpus in ['camera', 'references']:
        records = []
        for index, role in enumerate(['train', 'validation']):
            path = root / f'{corpus}-{role}.png'
            rgb = np.random.default_rng(index + (10 if corpus == 'references' else 0)).integers(
                40, 200, (24, 32, 3), dtype=np.uint8)
            Image.fromarray(rgb).save(path)
            records.append({'file': path.name, 'group': role, 'role': role,
                            'sha256': sha256(path)})
        (root / f'{corpus}.json').write_text(json.dumps({'records': records}))
    (root / 'exclusions.json').write_text(json.dumps({'regression_sha256': []}))
    return root


@pytest.mark.parametrize('relative_root', [False, True])
def test_explicit_training_writes_a_loadable_artifact_with_honest_provenance(
    tmp_path, monkeypatch, relative_root
):
    from parr.experiments import train as runner
    from parr.experiments.train import train_candidate
    pools = {}
    real_build, real_fit = runner.build_pool, runner.fit

    def observed_build(paths, *args):
        pool = real_build(paths, *args)
        pools[tuple(p.name for p in paths)] = pool
        return pool

    def observed_fit(source, target, *args):
        assert source is pools[('camera-train.png',)]
        assert target is pools[('references-train.png',)]
        return real_fit(source, target, *args)

    monkeypatch.setattr(runner, 'build_pool', observed_build)
    monkeypatch.setattr(runner, 'fit', observed_fit)
    root = training_inputs(tmp_path)
    if relative_root:
        monkeypatch.chdir(tmp_path)
        root = Path('inputs')
    out = tmp_path / 'trained'
    result = train_candidate(root, out, FitConfig(lut_size=3, iterations=1),
                             SampleConfig(max_side=32, pixels_per_image=20, max_pixels=40))
    art = Artifacts.load(out)
    assert art.training['trained'] is True
    assert art.training['exploratory_small_data'] is True
    assert art.training['source_train'] == ['camera-train.png']
    assert art.training['source_validation'] == ['camera-validation.png']
    assert art.training['evaluation_kind'] == 'scene-held-out development; not blind final test'
    assert len(art.training['code_sha256']['experiments/train.py']) == 64
    assert 'gates' in result and (out / 'report/metrics.json').exists()
    with pytest.raises(FileExistsError):
        train_candidate(root, out)


def test_training_rejects_regression_leakage_before_creating_output(tmp_path, monkeypatch):
    from parr.experiments import train as runner
    from parr.experiments.train import train_candidate
    monkeypatch.setattr(
        runner, 'fit', lambda *args: pytest.fail('fit must not run on excluded data')
    )
    root = training_inputs(tmp_path)
    (root / 'exclusions.json').write_text(json.dumps(
        {'regression_sha256': [sha256(root / 'camera-train.png')]}))
    with pytest.raises(ValueError, match='excluded'):
        train_candidate(root, tmp_path / 'trained')
    assert not (tmp_path / 'trained').exists()


def test_training_never_overwrites_artifact_created_while_fitting(tmp_path, monkeypatch):
    from parr.experiments import train as runner
    root = training_inputs(tmp_path)
    out = tmp_path / 'trained'
    real_fit = runner.fit

    def concurrent_fit(*args):
        out.mkdir()
        (out / 'keep.txt').write_text('other run')
        return real_fit(*args)

    monkeypatch.setattr(runner, 'fit', concurrent_fit)
    with pytest.raises(FileExistsError):
        runner.train_candidate(root, out, FitConfig(lut_size=3, iterations=1),
                               SampleConfig(max_side=32, pixels_per_image=20, max_pixels=40))
    assert (out / 'keep.txt').read_text() == 'other run'
