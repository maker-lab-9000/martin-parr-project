"""Validate explicit scene partitions before any pixel sampling or fitting."""

from __future__ import annotations

import json
from pathlib import Path

from .regression import checked_path, sha256


def load_partition(manifest, root, excluded_hashes=()):
    records = json.loads(Path(manifest).read_text())['records']
    root = Path(root)
    roles = {'train': [], 'validation': [], 'regression': [], 'excluded': []}
    groups = {'train': set(), 'validation': set()}
    paths, hashes = set(), {}
    excluded_hashes = set(excluded_hashes)
    for record in records:
        role, group = record['role'], record['group']
        if role not in roles or not isinstance(group, str) or not group.strip():
            raise ValueError('invalid role or scene group')
        path = checked_path(root, record['file'])
        if path in paths:
            raise ValueError(f'duplicate path: {path}')
        paths.add(path)
        digest = sha256(path)
        if digest != record['sha256']:
            raise ValueError(f'checksum mismatch: {path}')
        if role == 'train' and digest in excluded_hashes:
            raise ValueError(f'excluded image used for training: {path}')
        if role in groups:
            if digest in hashes:
                raise ValueError(f'duplicate training/validation image: {path}')
            hashes[digest] = role
            groups[role].add(group)
        roles[role].append(path)
    if groups['train'] & groups['validation']:
        raise ValueError('scene leakage between train and validation')
    if not roles['train'] or not roles['validation']:
        raise ValueError('explicit nonempty train and validation partitions required')
    return roles['train'], roles['validation']
