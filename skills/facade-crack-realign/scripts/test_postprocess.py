"""Exercise routing, known offset, rejection and input/output provenance offline."""
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from alignment import search_shift_v2, translate_within_bbox
from postprocess import finalize, inspect, propose, read, save


def main():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        rgb = np.full((220, 320, 3), 205, np.uint8)
        truth = np.zeros(rgb.shape[:2], np.uint8)
        cv2.line(truth, (72, 50), (212, 160), 255, 3)
        cv2.line(truth, (150, 112), (178, 52), 255, 2)
        rgb[truth > 0] = 25
        bbox = [40, 25, 250, 190]
        raw, _ = translate_within_bbox(truth > 0, bbox, 7, -5)
        Image.fromarray(rgb).save(root/'image.png')
        Image.fromarray(raw.astype(np.uint8)*255).save(root/'mask.png')
        cases = [('aligned', 'high', True, 'C'), ('uncertain', 'low', True, 'C'),
                 ('nontranslation_error', 'high', True, 'M'), ('translation_confirmed', 'low', True, 'C'),
                 ('translation_confirmed', 'high', False, 'C'), ('translation_confirmed', 'high', True, 'C'),
                 ('translation_confirmed', 'high', True, 'P')]
        rows = [{'key': f'case{k}', 'image_path': 'image.png', 'mask_path': 'mask.png',
                 'bbox_xyxy': bbox, 'class_code': cls, 'geometry_verified': geo}
                for k, (_, _, geo, cls) in enumerate(cases)]
        save(root/'inputs.json', {'schema_version': 1, 'instances': rows})
        inspect(root/'inputs.json', root/'inspection')
        decisions = read(root/'inspection'/'decisions.json')
        for row, (state, confidence, _, _) in zip(decisions['instances'], cases):
            row['judgment'] = {'state': state, 'confidence': confidence, 'reviewer': 'synthetic-test',
                               'evidence': ['Known upper branch displacement', 'Known lower endpoint displacement']}
        save(root/'decisions.json', decisions)
        calls = []

        def spy(*args, **kwargs):
            calls.append(1)
            return search_shift_v2(*args, **kwargs)

        propose(root/'decisions.json', root/'proposals', max_shift=12, solver=spy)
        records = read(root/'proposals'/'records.json')['instances']
        assert len(calls) == 1 and records[5]['solver_called'] and records[5]['algorithm_shifted']
        assert all(not row['solver_called'] for k, row in enumerate(records) if k != 5)
        save(root/'empty.json', {'schema_version': 1, 'instances': []})
        try:
            finalize(root/'proposals', root/'empty.json', root/'pending')
        except ValueError as e:
            assert 'Missing post-verification' in str(e)
        else:
            raise AssertionError('Moved candidate must require post-verification')
        assert not (root/'pending').exists()
        save(root/'wrong_candidate.json', {'schema_version': 1, 'instances': [
            {'key': 'case5', 'verdict': 'accept', 'reviewer': 'synthetic-test',
             'evidence': ['A different candidate was checked'], 'candidate_mask_sha256': '0'*64,
             'input_image_sha256': records[5]['input_image_sha256']}]})
        try:
            finalize(root/'proposals', root/'wrong_candidate.json', root/'wrong')
        except ValueError as e:
            assert 'another candidate/image' in str(e)
        else:
            raise AssertionError('Verification must bind to this candidate')
        assert not (root/'wrong').exists()
        for verdict in ('accept', 'reject', 'uncertain'):
            save(root/'verification.json', {'schema_version': 1, 'instances': [
                {'key': 'case5', 'verdict': verdict, 'reviewer': 'synthetic-test',
                 'candidate_mask_sha256': records[5]['candidate_mask_sha256'],
                 'input_image_sha256': records[5]['input_image_sha256'],
                 'evidence': ['Known synthetic image checked']}]})
            final = finalize(root/'proposals', root/'verification.json', root/verdict)
            out = read(final/'records.json')['instances']
            for row in out:
                actual = np.asarray(Image.open(final/row['mask_path'])) > 0
                rr = row['segmentation_rle']
                decoded = np.repeat(np.arange(len(rr['counts'])) % 2, rr['counts']).reshape(rr['size'], order='F') > 0
                assert np.array_equal(actual, decoded)
                if row['key'] != 'case5' or verdict != 'accept':
                    assert np.array_equal(actual, raw) and row['final_selection'] == 'raw'
                else:
                    iou = (actual & (truth > 0)).sum() / (actual | (truth > 0)).sum()
                    assert iou > .7 and row['final_selection'] == 'shifted'
        decisions['instances'][0]['input_mask_sha256'] = '0'*64
        save(root/'changed.json', decisions)
        try:
            propose(root/'changed.json', root/'invalid', solver=spy)
        except ValueError as e:
            assert 'Judged input changed' in str(e)
        else:
            raise AssertionError('Changed judged input must be rejected')
        assert len(calls) == 1
    print('PASS: exact instance routing, no solver on skipped cases, synthetic alignment, post-review gate, raw fallback, RLE, input hashes; no API requests')


if __name__ == '__main__':
    main()
