"""Refresh saved class statistics offline without reading or rewriting masks."""
import argparse
import csv
import json
from pathlib import Path

from reporting_classes import class_reporting_metadata, summarize_classes

ROOT = Path(__file__).resolve().parent.parent


def refresh(report, evaluation=None):
    report = Path(report)
    with (report / 'instances.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    classes = summarize_classes(rows, ['opencv', 'image25', 'hybrid'])
    targets = [report / 'classes.csv']
    if evaluation is not None:
        evaluation = Path(evaluation)
        evaluation.mkdir(parents=True, exist_ok=True)
        targets.append(evaluation / 'classes.csv')
    for target in targets:
        with target.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=classes[0])
            writer.writeheader()
            writer.writerows(classes)
    summary_path = report / 'summary.json'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding='utf-8-sig'))
        summary['class_reporting'] = class_reporting_metadata(classes)
        document = json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
        summary_path.write_text(document, encoding='utf-8')
        if evaluation is not None:
            (evaluation / 'summary.json').write_text(document, encoding='utf-8')
    counts = class_reporting_metadata(classes)['class_instances']
    print(f'Refreshed {len(counts)} classes, C+M={counts.get("C+M", 0)} instances, {len(classes)} method/class rows.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/comparison50')
    parser.add_argument('--evaluation', type=Path, default=ROOT / 'evaluation')
    args = parser.parse_args()
    refresh(args.report, args.evaluation)
