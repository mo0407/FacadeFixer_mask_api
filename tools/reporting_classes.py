"""Reporting-only class groups; source annotations and instance rows stay intact."""
import math

CLASS_NAMES = {
    'C+M': '裂缝', 'P': '剥落', 'S': '破损', 'T': '锈迹',
    'R': '腐蚀', 'D': '污染物', 'L': '渗漏／沉积物', 'V': '植物',
}
METRICS = ('iou', 'dice', 'precision', 'recall', 'boundary_f1')
MERGE_NOTE = '统计时将C裂缝与M网裂合并为“裂缝”（C+M）；按合并后的逐实例指标等权平均，原始标注和逐实例C/M编码保留。'


def reporting_code(source_code):
    return 'C+M' if source_code in ('C', 'M') else source_code


def source_codes(code):
    return ['C', 'M'] if code == 'C+M' else [code]


def aggregate_metrics(rows):
    """Accept scored dictionaries or CSV rows without changing the input rows."""
    if not rows:
        return {'instances': 0}
    tp, fp, fn = (sum(int(row[key]) for row in rows) for key in ('tp', 'fp', 'fn'))
    return {
        'instances': len(rows),
        **{f'macro_{key}': math.fsum(float(row[key]) for row in rows) / len(rows)
           for key in METRICS},
        'micro_iou': tp / (tp + fp + fn) if tp + fp + fn else 1.,
        'micro_dice': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.,
    }


def summarize_classes(rows, methods=None):
    """Recompute from every instance, never average the old C and M means."""
    methods = list(methods) if methods is not None else list(dict.fromkeys(row['method'] for row in rows))
    codes = {reporting_code(row['class_code']) for row in rows}
    unknown = codes - CLASS_NAMES.keys()
    if unknown:
        raise ValueError(f'Unknown reporting classes: {sorted(unknown)}')
    return [
        {'method': method, 'class_code': code, 'class_name': CLASS_NAMES[code],
         'source_class_codes': '|'.join(source_codes(code)),
         **aggregate_metrics([row for row in rows
                              if row['method'] == method and reporting_code(row['class_code']) == code])}
        for method in methods for code in CLASS_NAMES if code in codes
    ]


def class_reporting_metadata(classes):
    first_method = classes[0]['method'] if classes else None
    counts = {row['class_code']: row['instances'] for row in classes if row['method'] == first_method}
    return {
        'class_count': len(counts), 'class_instances': counts,
        'merged_classes': {'C+M': {'name': '裂缝', 'source_class_codes': ['C', 'M']}},
        'aggregation': 'Equal-weight mean of individual instance scores; missing instances retain zero scores',
        'note': MERGE_NOTE,
    }
