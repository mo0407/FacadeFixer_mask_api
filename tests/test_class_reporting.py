"""Regression checks for reporting-only C/M merging and instance weighting."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reporting_classes import CLASS_NAMES, METRICS, class_reporting_metadata, reporting_code, summarize_classes


def row(code, value, tp, fp, fn):
    return {'method': 'example', 'class_code': code, 'missing': value == 0,
            'tp': tp, 'fp': fp, 'fn': fn, **dict.fromkeys(METRICS, value)}


# The unequal C/M counts detect the tempting but wrong mean-of-two-means calculation.
rows = [row('C', 1., 10, 0, 0), row('C', 0., 0, 0, 10), row('C', .5, 5, 5, 5),
        row('M', .2, 2, 8, 8), row('P', .8, 8, 2, 2)]
before = copy.deepcopy(rows)
classes = summarize_classes(rows)
crack, peeling = classes
assert crack['class_code'] == 'C+M' and crack['class_name'] == '裂缝'
assert crack['source_class_codes'] == 'C|M' and crack['instances'] == 4
assert abs(crack['macro_iou'] - .425) < 1e-12
assert abs(crack['macro_iou'] - ((1 + 0 + .5) / 3 + .2) / 2) > .01
assert all(abs(crack['macro_' + key] - .425) < 1e-12 for key in METRICS)
assert abs(crack['micro_iou'] - 17 / 53) < 1e-12
assert peeling['instances'] == 1 and peeling['macro_iou'] == .8
assert rows == before and [row['class_code'] for row in rows] == ['C', 'C', 'C', 'M', 'P']
csv_rows = [{key: str(value) for key, value in row.items()} for row in rows]
assert summarize_classes(csv_rows) == classes
assert reporting_code('C') == reporting_code('M') == 'C+M'
assert reporting_code('P') == 'P' and len(CLASS_NAMES) == 8
assert class_reporting_metadata(classes)['class_instances'] == {'C+M': 4, 'P': 1}
try:
    summarize_classes([row('UNKNOWN', 1., 1, 0, 0)])
except ValueError:
    pass
else:
    raise AssertionError('Unknown codes must not silently disappear from the report')
print('PASS: C/M instance weighting, missing-zero retention, micro totals, CSV inputs, source-code preservation.')
