"""Offline, per-instance inspection and explicitly gated crack alignment.

inspect: prepare overlays and a fail-closed judgment template.
propose: call alignment only for high-confidence confirmed translations.
finalize: accept moved candidates only after a separate visual verification.
No API calls or reference-mask inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

STATES = {'aligned', 'translation_confirmed', 'nontranslation_error', 'uncertain', 'geometry_invalid'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def mask_at(path, shape, bbox):
    with Image.open(path) as im:
        if im.mode != 'L':
            raise ValueError(f'Mask must be L-mode 0/255: {path}')
        a = np.asarray(im)
    if a.shape != shape or not np.isin(a, (0, 255)).all():
        raise ValueError(f'Mask dimensions/values invalid: {path}')
    m = a != 0
    x1, y1, x2, y2 = bbox
    if m.sum() != m[y1:y2, x1:x2].sum():
        raise ValueError(f'Mask outside frozen bbox: {path}')
    return m


def load_inputs(path, judged=False):
    path = Path(path).resolve()
    data = read(path)
    if data.get('schema_version') != 1 or not data.get('instances'):
        raise ValueError('Expected schema_version=1 and nonempty instances')
    seen, inputs = set(), []
    for entry in data['instances']:
        row = dict(entry)
        key = row.get('key', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}', key) or key in seen:
            raise ValueError(f'Invalid/duplicate instance key: {key}')
        seen.add(key)
        for field in ('image_path', 'mask_path'):
            p = Path(row[field])
            row[field] = str((path.parent / p).resolve() if not p.is_absolute() else p.resolve())
        with Image.open(row['image_path']) as im:
            rgb = np.asarray(im.convert('RGB'))
        row['height'], row['width'] = rgb.shape[:2]
        box = row['bbox_xyxy']
        if (len(box) != 4 or not all(type(v) is int for v in box)
                or not 0 <= box[0] < box[2] <= rgb.shape[1]
                or not 0 <= box[1] < box[3] <= rgb.shape[0]):
            raise ValueError(f'Invalid bbox for {key}')
        if not isinstance(row.get('geometry_verified'), bool):
            raise ValueError(f'geometry_verified must be boolean: {key}')
        mask_at(row['mask_path'], rgb.shape[:2], box)
        for field, source in [('input_image_sha256', 'image_path'), ('input_mask_sha256', 'mask_path')]:
            actual = sha(row[source])
            if judged and row.get(field) != actual:
                raise ValueError(f'Judged input changed or hash absent: {key}/{field}; rerun inspect')
            row[field] = actual
        if judged:
            j = row.get('judgment', {})
            if j.get('state') not in STATES or j.get('confidence') not in {'high', 'medium', 'low'}:
                raise ValueError(f'Invalid judgment: {key}')
            if not isinstance(j.get('evidence'), list) or not all(isinstance(s, str) and s.strip() for s in j['evidence']):
                raise ValueError(f'Invalid evidence: {key}')
            if not j['evidence'] or not str(j.get('reviewer', '')).strip():
                raise ValueError(f'Missing observation/reviewer: {key}')
            if j['state'] == 'translation_confirmed' and len(j['evidence']) < 2:
                raise ValueError(f'Two separated observations required: {key}')
        inputs.append(row)
    return inputs


def new_output(path, folders):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('Output exists; choose a new directory')
    path.mkdir(parents=True)
    for folder in folders:
        (path / folder).mkdir()
    return path


def overlay(rgb, mask, bbox, color):
    a = rgb.copy()
    a[mask] = np.rint(.5 * a[mask] + .5 * np.asarray(color)).astype(np.uint8)
    im = Image.fromarray(a)
    ImageDraw.Draw(im).rectangle(tuple(bbox), outline=(0, 220, 0), width=2)
    return im


def views(root, row, candidate=None):
    with Image.open(row['image_path']) as im:
        rgb = np.asarray(im.convert('RGB'))
    raw = mask_at(row['raw_mask_path'], rgb.shape[:2], row['bbox_xyxy'])
    x1, y1, x2, y2 = row['bbox_xyxy']
    margin = max(12, round(max(x2-x1, y2-y1) * .05))
    crop = (max(0, x1-margin), max(0, y1-margin), min(rgb.shape[1], x2+margin), min(rgb.shape[0], y2+margin))
    key = row['key']
    Image.fromarray(rgb).crop(crop).save(root/'original_crops'/f'{key}.png')
    raw_im = overlay(rgb, raw, row['bbox_xyxy'], (255, 60, 60))
    raw_im.save(root/'raw_overlays'/f'{key}.png')
    raw_im.crop(crop).save(root/'raw_crops'/f'{key}.png')
    if candidate is not None:
        cand_im = overlay(rgb, candidate, row['bbox_xyxy'], (0, 205, 245))
        cand_im.save(root/'candidate_overlays'/f'{key}.png')
        cand_im.crop(crop).save(root/'candidate_crops'/f'{key}.png')


def review(root, records, candidate=False):
    cards = []
    for row in records:
        key = row['key']
        panels = [('原图局部', 'original_crops', 'original_crops'), ('原稿叠加', 'raw_crops', 'raw_overlays')]
        if candidate:
            panels.append(('候选叠加', 'candidate_crops', 'candidate_overlays'))
        images = ''.join(f'<figure><a href="{full}/{key}.png"><img src="{small}/{key}.png"></a><figcaption>{label}</figcaption></figure>' for label, small, full in panels)
        status = html.escape(row.get('skip_reason') or row.get('judgment', {}).get('state', 'unreviewed'))
        cards.append(f'<section><h2>{html.escape(key)} · {status}</h2><div class="row">{images}</div></section>')
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>裂缝复位检查</title>'
            '<style>body{font:16px system-ui;background:#eee;margin:24px}section{background:white;padding:16px;margin:20px 0}.row{display:flex;gap:12px}figure{flex:1;min-width:0;margin:0}img{width:100%;height:520px;object-fit:contain}figcaption{margin-top:8px}@media(max-width:850px){.row{display:block}}</style>'
            '<h1>裂缝复位检查</h1><p>点击叠加图查看原尺寸。绿色为冻结 bbox。候选仍需视觉复核，未读取参考标注。</p>' + ''.join(cards) + '</html>')
    (root/'review.html').write_text(page, encoding='utf-8')


def inspect(inputs_path, output):
    rows = load_inputs(inputs_path)
    root = new_output(output, ['original_crops', 'raw_overlays', 'raw_crops'])
    for row in rows:
        row['raw_mask_path'] = row['mask_path']
        views(root, row)
        row['judgment'] = {'state': 'uncertain', 'confidence': 'low', 'reviewer': 'unreviewed',
                           'evidence': ['尚未进行视觉检查'], 'estimated_shift_xy': None}
    save(root/'decisions.json', {'schema_version': 1, 'instances': rows})
    review(root, rows)
    return root


def propose(decisions_path, output, max_shift=24, min_kept=.98, solver=None):
    if not 1 <= max_shift <= 128 or not 0 < min_kept <= 1:
        raise ValueError('Invalid max_shift/min_kept')
    rows = load_inputs(decisions_path, judged=True)
    root = new_output(output, ['raw_masks', 'candidate_masks', 'original_crops', 'raw_overlays',
                               'raw_crops', 'candidate_overlays', 'candidate_crops'])
    records = []
    for row in rows:
        with Image.open(row['image_path']) as im:
            rgb = np.asarray(im.convert('RGB'))
        raw = mask_at(row['mask_path'], rgb.shape[:2], row['bbox_xyxy'])
        key, j = row['key'], row['judgment']
        skip = ('non_crack_class' if row['class_code'] not in {'C', 'M'} else
                'geometry_not_verified' if not row['geometry_verified'] else
                'judgment_not_confirmed_translation' if j['state'] != 'translation_confirmed' else
                'confidence_not_high' if j['confidence'] != 'high' else '')
        candidate, info, seconds = raw.copy(), {}, 0.
        if not skip:
            if solver is None:
                from alignment import search_shift_v2
                solver = search_shift_v2
            start = time.perf_counter()
            candidate, info = solver(rgb, raw, row['bbox_xyxy'], max_shift=max_shift, min_kept=min_kept)
            seconds = time.perf_counter() - start
        raw_path, candidate_path = root/'raw_masks'/f'{key}.png', root/'candidate_masks'/f'{key}.png'
        Image.fromarray(raw.astype(np.uint8)*255).save(raw_path)
        Image.fromarray(candidate.astype(np.uint8)*255).save(candidate_path)
        mask_at(candidate_path, rgb.shape[:2], row['bbox_xyxy'])
        record = {**row, 'raw_mask_path': str(raw_path), 'candidate_mask_path': str(candidate_path),
                  'raw_mask_sha256': sha(raw_path), 'candidate_mask_sha256': sha(candidate_path),
                  'solver_called': not bool(skip), 'skip_reason': skip,
                  'solver_seconds': seconds, 'solver_info': info,
                  'algorithm_shifted': info.get('selection') == 'shifted',
                  'algorithm_version': 'crack_shift_consensus_v2' if not skip else None,
                  'algorithm_sha256': sha(Path(__file__).with_name('alignment.py')) if not skip else None,
                  'tool_sha256': sha(__file__),
                  'parameters': {'max_shift': max_shift, 'min_kept': min_kept, 'min_gain': .08, 'min_displacement': 2., 'max_side': 1500},
                  'reference_mask_used_for_decision': False}
        records.append(record)
        views(root, record, candidate)
    save(root/'records.json', {'schema_version': 1, 'instances': records})
    review(root, records, candidate=True)
    return root


def rle(mask):
    a = mask.reshape(-1, order='F').astype(np.uint8)
    changes = np.flatnonzero(np.diff(a)) + 1
    counts = np.diff(np.r_[0, changes, a.size]).tolist()
    if a[0]: counts.insert(0, 0)
    return {'size': list(mask.shape), 'counts': counts}


def finalize(proposals, verifications_path, output):
    proposals = Path(proposals).resolve()
    rows = read(proposals/'records.json')['instances']
    verification = read(verifications_path)
    if verification.get('schema_version') != 1:
        raise ValueError('Invalid verification schema')
    by_key = {}
    for v in verification.get('instances', []):
        if v.get('key') in by_key or v.get('verdict') not in {'accept', 'reject', 'uncertain'}:
            raise ValueError('Invalid or duplicate verification')
        if not v.get('reviewer') or not v.get('evidence') or not all(isinstance(s, str) and s.strip() for s in v['evidence']):
            raise ValueError('Verification needs evidence and reviewer')
        by_key[v['key']] = v
    keys = {r['key'] for r in rows}
    if not set(by_key) <= keys:
        raise ValueError('Verification contains unknown instance')
    for row in rows:
        if row['algorithm_shifted'] and row['key'] not in by_key:
            raise ValueError(f'Missing post-verification: {row["key"]}')
        if row['algorithm_shifted']:
            v = by_key[row['key']]
            if (v.get('candidate_mask_sha256') != row['candidate_mask_sha256']
                    or v.get('input_image_sha256') != row['input_image_sha256']):
                raise ValueError(f'Verification refers to another candidate/image: {row["key"]}')
        if sha(row['image_path']) != row['input_image_sha256']:
            raise ValueError('Original image changed; repeat inspection')
        for field in ('raw', 'candidate'):
            if sha(row[field+'_mask_path']) != row[field+'_mask_sha256']:
                raise ValueError('Proposal mask changed; repeat proposal')
    root = new_output(output, ['instance_masks', 'overlays'])
    final = []
    for row in rows:
        v = by_key.get(row['key'])
        accepted = row['algorithm_shifted'] and v['verdict'] == 'accept' if v else False
        source = row['candidate_mask_path'] if accepted else row['raw_mask_path']
        with Image.open(row['image_path']) as im:
            rgb = np.asarray(im.convert('RGB'))
        m = mask_at(source, rgb.shape[:2], row['bbox_xyxy'])
        dest = root/'instance_masks'/f'{row["key"]}.png'
        Image.fromarray(m.astype(np.uint8)*255).save(dest)
        overlay(rgb, m, row['bbox_xyxy'], (0, 205, 245) if accepted else (255, 60, 60)).save(root/'overlays'/f'{row["key"]}.png')
        final.append({**row, 'post_verification': v, 'final_selection': 'shifted' if accepted else 'raw',
                      'mask_path': dest.relative_to(root).as_posix(), 'mask_sha256': sha(dest),
                      'area_pixels': int(m.sum()), 'segmentation_rle': rle(m),
                      'dx': row['solver_info'].get('dx', 0) if accepted else 0,
                      'dy': row['solver_info'].get('dy', 0) if accepted else 0,
                      'overlay_path': f'overlays/{row["key"]}.png'})
    save(root/'records.json', {'schema_version': 1, 'proposals': str(proposals), 'instances': final})
    return root


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    s = commands.add_parser('inspect'); s.add_argument('--inputs', required=True); s.add_argument('--output', required=True)
    s = commands.add_parser('propose'); s.add_argument('--decisions', required=True); s.add_argument('--output', required=True)
    s.add_argument('--max-shift', type=int, default=24); s.add_argument('--min-kept', type=float, default=.98)
    s = commands.add_parser('finalize'); s.add_argument('--proposals', required=True); s.add_argument('--verifications', required=True); s.add_argument('--output', required=True)
    args = p.parse_args()
    if args.command == 'inspect': root = inspect(args.inputs, args.output)
    elif args.command == 'propose': root = propose(args.decisions, args.output, args.max_shift, args.min_kept)
    else: root = finalize(args.proposals, args.verifications, args.output)
    print(f'{args.command}: {root}; no API requests')


if __name__ == '__main__':
    main()
