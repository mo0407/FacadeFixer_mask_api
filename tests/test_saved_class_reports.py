"""Check saved statistics and generated brief without dumping embedded images."""
import csv
import json
import math
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from reporting_classes import CLASS_NAMES, METRICS, aggregate_metrics, class_reporting_metadata, summarize_classes


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


instances = read_csv(ROOT / 'reports/comparison50/instances.csv')
methods = ['opencv', 'image25', 'hybrid']
expected = summarize_classes(instances, methods)
assert len(instances) == 327 and len(expected) == 24
for method in methods:
    entries = [row for row in instances if row['method'] == method]
    assert len(entries) == 109
    assert sum(row['class_code'] == 'C' for row in entries) == 20
    assert sum(row['class_code'] == 'M' for row in entries) == 3
    assert all(row['class_code'] != 'C+M' for row in entries)
    assert sum(row['missing'].lower() == 'true' for row in entries) == (0 if method == 'opencv' else 4)
for path in [ROOT / 'reports/comparison50/classes.csv', ROOT / 'evaluation/classes.csv']:
    saved = read_csv(path)
    assert len(saved) == 24
    by_class = {(row['method'], row['class_code']): row for row in saved}
    assert set(by_class) == {(row['method'], row['class_code']) for row in expected}
    for row in expected:
        actual = by_class[row['method'], row['class_code']]
        for key in ('class_name', 'source_class_codes'):
            assert actual[key] == row[key]
        assert int(actual['instances']) == row['instances']
        for key in [*('macro_' + metric for metric in METRICS), 'micro_iou', 'micro_dice']:
            assert math.isclose(float(actual[key]), row[key], abs_tol=1e-12), (path, key)
    assert all(int(by_class[method, 'C+M']['instances']) == 23 for method in methods)
summary = json.loads((ROOT / 'reports/comparison50/summary.json').read_text(encoding='utf-8'))
evaluation_summary = json.loads((ROOT / 'evaluation/summary.json').read_text(encoding='utf-8'))
assert evaluation_summary == summary
assert summary['class_reporting'] == class_reporting_metadata(expected)
for method in methods:
    entries = [row for row in instances if row['method'] == method]
    for key, subset in [('all_instances', entries), ('common_available_instances',
                        [row for row in entries if row['common_available'].lower() == 'true'])]:
        metrics = aggregate_metrics(subset)
        assert metrics['instances'] == (109 if key == 'all_instances' else 105)
        for name, value in metrics.items():
            assert math.isclose(summary['methods'][method][key][name], value, abs_tol=1e-12), (method, key, name)


class BriefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_class_table = False
        self.in_body = False
        self.row_count = 0
        self.table_text = []
        self.text = []
        self.image_count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table' and attrs.get('class') == 'class-stats':
            self.in_class_table = True
        if tag == 'tbody' and self.in_class_table:
            self.in_body = True
        if tag == 'tr' and self.in_body:
            self.row_count += 1
        if tag == 'img':
            self.image_count += 1

    def handle_endtag(self, tag):
        if tag == 'tbody':
            self.in_body = False
        if tag == 'table':
            self.in_class_table = False

    def handle_data(self, data):
        self.text.append(data)
        if self.in_class_table:
            self.table_text.append(data)


brief = BriefParser()
brief.feed((ROOT / 'reports/experiment_brief/index.html').read_text(encoding='utf-8'))
text = ''.join(brief.text)
table_text = ''.join(brief.table_text)
assert brief.row_count == 8 and brief.image_count == 9
assert '裂缝 C+M23' in table_text
assert '网裂 M' not in table_text and '9类' not in text
assert '本轮报告8类' in text and 'C 20个＋M 3个' in text
assert '混合方法在8类中的6类平均IoU最高' in text
assert 'API初稿在8类中的6类边界F1最高' in text
for row in expected:
    assert f'IoU {row["macro_iou"]:.3f}' in table_text
    assert f'边界F1 {row["macro_boundary_f1"]:.3f}' in table_text
evaluation = (ROOT / 'EVALUATION.md').read_text(encoding='utf-8')
for row in expected:
    if row['class_code'] == 'C+M':
        assert f'|23|{row["macro_iou"]:.4f}|{row["macro_boundary_f1"]:.4f}|' in evaluation
print('PASS: both class CSVs, 23 merged instances, 8 categories, unchanged global summaries, generated brief and evaluation table.')
