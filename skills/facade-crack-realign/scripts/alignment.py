"""Image-only alignment core; packaged from crack_shift_consensus_v2. No reference inputs."""
from __future__ import annotations
import math
import cv2
import numpy as np


def line_response(rgb: np.ndarray) -> np.ndarray:
    """Dark, narrow structure relative to the nearby wall (0..1)."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    local = cv2.GaussianBlur(gray, (0, 0), 5)
    local_dark = np.clip(local.astype(np.float32) - gray, 0, None)
    dark_lines = np.maximum(
        cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))),
        cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))),
    ).astype(np.float32)
    response = 0.45 * local_dark + 0.55 * dark_lines
    high = float(np.percentile(response, 99.5))
    if high < 4:
        return np.zeros(gray.shape, np.float32)
    return np.clip(response / high, 0, 1).astype(np.float32)

def translate_within_bbox(mask: np.ndarray, bbox: list[int], dx: int, dy: int) -> tuple[np.ndarray, float]:
    """Translate foreground; never write outside the frozen bbox."""
    h, w = mask.shape
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
        raise ValueError('Invalid bbox')
    crop = mask[y1:y2, x1:x2]
    if mask.sum() != crop.sum():
        raise ValueError('Input mask contains pixels outside its bbox')
    target = np.zeros_like(crop)
    hh, ww = crop.shape
    src_x1 = max(0, -dx)
    src_y1 = max(0, -dy)
    src_x2 = min(ww, ww - dx)
    src_y2 = min(hh, hh - dy)
    if src_x2 > src_x1 and src_y2 > src_y1:
        target[src_y1 + dy:src_y2 + dy, src_x1 + dx:src_x2 + dx] = crop[src_y1:src_y2, src_x1:src_x2]
    output = np.zeros_like(mask)
    output[y1:y2, x1:x2] = target
    kept = float(target.sum() / crop.sum()) if crop.any() else 1.0
    return output, kept

def search_shift(rgb: np.ndarray, mask: np.ndarray, bbox: list[int], max_shift: int = 24,
                 max_side: int = 1500, min_gain: float = 0.08, min_kept: float = 0.98,
                 min_displacement: float = 2.0) -> tuple[np.ndarray, dict]:
    """Compare translations by original-image dark-line support, no reference masks."""
    if rgb.shape[:2] != mask.shape:
        raise ValueError('Image and mask dimensions differ')
    x1, y1, x2, y2 = bbox
    if not mask.any():
        return mask.copy(), {'selection': 'raw_fallback', 'reason': 'empty_input', 'dx': 0, 'dy': 0}
    roi = rgb[y1:y2, x1:x2]
    original = mask[y1:y2, x1:x2]
    scale = min(1., max_side / max(roi.shape[:2]))
    if scale < 1:
        size = (max(1, round(roi.shape[1] * scale)), max(1, round(roi.shape[0] * scale)))
        roi = cv2.resize(roi, size, interpolation=cv2.INTER_AREA)
        prior = cv2.resize(original.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    else:
        prior = original
    feature = line_response(roi)
    if not np.any(feature):
        return mask.copy(), {'selection': 'raw_fallback', 'reason': 'no_dark_line_evidence', 'dx': 0, 'dy': 0,
                             'scale': scale}
    ys, xs = np.where(prior)
    h, w = prior.shape
    # Deterministic cap keeps full-frame cracks affordable without using labels.
    if len(xs) > 150_000:
        stride = math.ceil(len(xs) / 150_000)
        xs, ys = xs[::stride], ys[::stride]
    limit = max(1, math.ceil(max_shift * scale))
    scored = []
    for dy in range(-limit, limit + 1):
        yy = ys + dy
        oky = (yy >= 0) & (yy < h)
        for dx in range(-limit, limit + 1):
            xx = xs + dx
            ok = oky & (xx >= 0) & (xx < w)
            kept = float(ok.mean())
            if kept < min_kept:
                continue
            support = float(feature[yy[ok], xx[ok]].mean())
            # Prefer the smallest translation among near-equal image matches.
            score = support - 0.00035 * math.hypot(dx, dy)
            scored.append((score, support, dx, dy, kept))
    if not scored:
        return mask.copy(), {'selection': 'raw_fallback', 'reason': 'bbox_clipping', 'dx': 0, 'dy': 0,
                             'scale': scale}
    base = next((v for v in scored if v[2:4] == (0, 0)), None)
    assert base is not None
    best = max(scored, key=lambda v: v[0])
    dx = int(round(best[2] / scale))
    dy = int(round(best[3] / scale))
    dx = int(np.clip(dx, -max_shift, max_shift))
    dy = int(np.clip(dy, -max_shift, max_shift))
    candidate, kept_native = translate_within_bbox(mask, bbox, dx, dy)
    gain = best[1] - base[1]
    reason = 'accepted' if math.hypot(dx, dy) >= min_displacement and gain >= min_gain and kept_native >= min_kept else (
        'insufficient_image_evidence' if gain < min_gain else
        'shift_too_small' if math.hypot(dx, dy) < min_displacement else 'bbox_clipping')
    chosen = candidate if reason == 'accepted' else mask.copy()
    info = {'selection': 'shifted' if reason == 'accepted' else 'raw_fallback', 'reason': reason,
            'dx': dx if reason == 'accepted' else 0, 'dy': dy if reason == 'accepted' else 0,
            'candidate_dx': dx, 'candidate_dy': dy, 'response_before': base[1],
            'response_candidate': best[1], 'response_gain': gain, 'candidate_kept_fraction': kept_native,
            'scale': scale, 'max_shift_original_px': max_shift, 'min_gain': min_gain,
            'min_kept': min_kept, 'min_displacement': min_displacement}
    return chosen, info

def search_shift_consensus(rgb: np.ndarray, mask: np.ndarray, bbox: list[int],
                           max_shift: int = 24, max_side: int = 1500,
                           min_gain: float = .08, min_kept: float = .98,
                           min_displacement: float = 2.) -> tuple[np.ndarray, dict]:
    """Score line support across eight sections; shift only on broad agreement."""
    if rgb.shape[:2] != mask.shape:
        raise ValueError('Image and mask dimensions differ')
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= mask.shape[1] and 0 <= y1 < y2 <= mask.shape[0]):
        raise ValueError('Invalid bbox')
    if mask.sum() != mask[y1:y2, x1:x2].sum():
        raise ValueError('Input mask contains pixels outside its bbox')
    if not mask.any():
        return mask.copy(), {'selection': 'raw_fallback', 'reason': 'empty_input', 'dx': 0, 'dy': 0}

    roi = rgb[y1:y2, x1:x2]
    prior = mask[y1:y2, x1:x2]
    scale = min(1., max_side / max(roi.shape[:2]))
    if scale < 1.:
        size = (max(1, round(roi.shape[1] * scale)), max(1, round(roi.shape[0] * scale)))
        roi = cv2.resize(roi, size, interpolation=cv2.INTER_AREA)
        prior = cv2.resize(prior.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    response = line_response(roi)
    if not np.any(response):
        return mask.copy(), {'selection': 'raw_fallback', 'reason': 'no_dark_line_evidence',
                             'dx': 0, 'dy': 0, 'scale': scale}
    # A little blur tolerates narrow differences without favoring a distant line.
    response = (.8 * response + .2 * cv2.GaussianBlur(response, (0, 0), .8)).astype(np.float32)
    ys, xs = np.where(prior)
    if len(xs) > 24_000:
        stride = math.ceil(len(xs) / 24_000)
        xs, ys = xs[::stride], ys[::stride]
    h, w = prior.shape

    # Divide the mask along its long axis. A single dark patch cannot authorize
    # translating the whole crack unless other sections also improve.
    coords = np.stack((xs.astype(np.float32), ys.astype(np.float32)), axis=1)
    centered = coords - coords.mean(axis=0)
    principal = np.linalg.eigh(centered.T @ centered)[1][:, -1]
    projection = centered @ principal
    boundaries = np.quantile(projection, np.linspace(0, 1, 9)[1:-1])
    section = np.searchsorted(boundaries, projection).astype(np.int32)
    counts = np.bincount(section, minlength=8)
    active = counts >= max(8, len(xs) // 100)
    if active.sum() < 3:
        active = counts > 0

    limit = max(1, math.ceil(max_shift * scale))
    candidates = []
    for dy in range(-limit, limit + 1):
        yy = ys + dy
        valid_y = (yy >= 0) & (yy < h)
        for dx in range(-limit, limit + 1):
            xx = xs + dx
            valid = valid_y & (xx >= 0) & (xx < w)
            kept = float(valid.mean())
            if kept < min_kept:
                continue
            values = response[yy[valid], xx[valid]]
            support = float(values.mean())
            section_count = np.bincount(section[valid], minlength=8)
            section_score = np.bincount(section[valid], weights=values, minlength=8) / np.maximum(1, section_count)
            robust = .65 * support + .35 * float(np.median(section_score[active]))
            # Larger translations require stronger image evidence.
            rank = robust - .0012 * math.hypot(dx, dy)
            candidates.append((rank, robust, support, dx, dy, kept, section_score))
    if not candidates:
        return mask.copy(), {'selection': 'raw_fallback', 'reason': 'bbox_clipping',
                             'dx': 0, 'dy': 0, 'scale': scale}
    base = next(c for c in candidates if c[3:5] == (0, 0))
    best = max(candidates, key=lambda c: c[0])
    dx = int(np.clip(round(best[3] / scale), -max_shift, max_shift))
    dy = int(np.clip(round(best[4] / scale), -max_shift, max_shift))
    moved, kept_native = translate_within_bbox(mask, bbox, dx, dy)
    delta = best[6] - base[6]
    agreement = float(np.mean(delta[active] > .01))
    median_gain = float(np.median(delta[active]))
    gain = best[1] - base[1]
    # Lower the average-gain gate only when the improvement is distributed over
    # the entire shape. Otherwise preserve the unshifted API result.
    threshold = max(.035, min_gain * .5)
    accepted = (math.hypot(dx, dy) >= min_displacement and gain >= threshold
                and median_gain >= .02 and agreement >= .625 and kept_native >= min_kept)
    reason = ('accepted' if accepted else
              'insufficient_image_evidence' if gain < threshold else
              'insufficient_section_agreement' if median_gain < .02 or agreement < .625 else
              'shift_too_small' if math.hypot(dx, dy) < min_displacement else
              'bbox_clipping')
    info = {'selection': 'shifted' if accepted else 'raw_fallback', 'reason': reason,
            'dx': dx if accepted else 0, 'dy': dy if accepted else 0,
            'candidate_dx': dx, 'candidate_dy': dy, 'response_before': base[2],
            'response_candidate': best[2], 'response_gain': gain,
            'median_section_gain': median_gain, 'section_agreement': agreement,
            'candidate_kept_fraction': kept_native, 'scale': scale,
            'max_shift_original_px': max_shift, 'min_gain': min_gain,
            'min_kept': min_kept, 'min_displacement': min_displacement}
    return moved if accepted else mask.copy(), info

def search_shift_v2(rgb: np.ndarray, mask: np.ndarray, bbox: list[int],
                    max_shift: int = 24, max_side: int = 1500,
                    min_gain: float = .08, min_kept: float = .98,
                    min_displacement: float = 2.) -> tuple[np.ndarray, dict]:
    """Require two independent image scores to agree on any new translation.

    Preserve the original conservative result where the new sectional scorer
    disagrees. Thick masks have uncertain centerlines, so they are never newly
    shifted by the relaxed scorer.
    """
    opts = dict(max_shift=max_shift, max_side=max_side, min_gain=min_gain,
                min_kept=min_kept, min_displacement=min_displacement)
    baseline, old = search_shift(rgb, mask, bbox, **opts)
    consensus, new = search_shift_consensus(rgb, mask, bbox, **opts)
    x1, y1, x2, y2 = bbox
    crop = mask[y1:y2, x1:x2].astype(np.uint8)
    distance = cv2.distanceTransform(crop, cv2.DIST_L2, 3)
    thickness90 = float(np.quantile(distance[crop > 0], .9)) if crop.any() else 0.
    old_dx, old_dy = old.get('candidate_dx', 0), old.get('candidate_dy', 0)
    new_dx, new_dy = new.get('candidate_dx', 0), new.get('candidate_dy', 0)
    agreement = math.hypot(old_dx - new_dx, old_dy - new_dy) <= 1.5
    use_consensus = (new['selection'] == 'shifted' and agreement and thickness90 <= 4.)
    chosen, info = (consensus, new) if use_consensus else (baseline, old)
    info = {**info, 'decision_rule': 'consensus' if use_consensus else 'conservative',
            'prior_thickness90_px': thickness90,
            'method_candidate_agreement': agreement,
            'conservative_candidate_dx': old_dx, 'conservative_candidate_dy': old_dy,
            'conservative_selection': old['selection'],
            'consensus_candidate_dx': new_dx, 'consensus_candidate_dy': new_dy,
            'consensus_selection': new['selection']}
    return chosen, info
