"""Image-edit transport helpers extracted from the existing local adapter. No credentials or active model configuration."""

from pathlib import Path

from urllib.parse import urlsplit

import base64

import csv

import hashlib

import io

import json

import math

import os

import re

import time

import argparse

import requests

import numpy as np

from PIL import Image

THRESHOLD = 128
OVERLAY_ALPHA = 0.45
DEFINITIONS = {}

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')

def annotations(file, directory):
    if not directory:
        return []
    candidates = [file.stem.removesuffix('_image') + '_detection.json', file.stem + '.json']
    for name in candidates:
        p = Path(directory) / name
        if p.exists():
            doc = read(p)
            rows = doc if isinstance(doc, list) else doc.get('annotations_in_crop', doc.get('annotations'))
            if rows is None:
                raise ValueError(f'未识别检测格式: {name}')
            result = []
            for row in rows:
                label, bbox = row.get('class_name'), row.get('bbox')
                if not isinstance(label, str) or not isinstance(bbox, list) or len(bbox) != 4:
                    raise ValueError(f'检测需 class_name 和 bbox=[x1,y1,x2,y2]: {name}')
                if not all(isinstance(x, (int,float)) and math.isfinite(x) for x in bbox) or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    raise ValueError(f'无效 bbox: {name}')
                result.append({'class': label, 'bbox_xyxy_original': bbox})
            return result
    return []

def prepare(file, detections, max_side):
    source = file.read_bytes()
    with Image.open(io.BytesIO(source)) as im:
        # Keep stored pixel coordinates identical to detector coordinates; do not EXIF-rotate.
        original = im.convert('RGB')
    w, h = original.size
    # Square letterbox: explicit API size and submitted geometry must agree.
    # Original pixels are uniformly scaled; never stretch the photograph.
    cw = ch = max(w, h)
    ox, oy = (cw-w)//2, (ch-h)//2
    scale = min(1, max_side / max(cw, ch))
    sw, sh = max(1, round(cw*scale)), max(1, round(ch*scale))
    canvas = Image.new('RGB', (cw, ch), (255, 0, 255))
    canvas.paste(original, (ox, oy))
    canvas = canvas.resize((sw, sh), Image.Resampling.LANCZOS) if scale < 1 else canvas
    buf = io.BytesIO(); canvas.save(buf, format='PNG')
    targets = annotations(file, detections)
    prompt = ('Produce ONLY a binary facade-defect segmentation mask from this photograph. '
              'White #FFFFFF = defect; black #000000 = everything else. '
              'Preserve the exact full-frame geometry, position, aspect ratio and scale. '
              'No cropping, recentering, zoom, boxes, text, outlines or stylization. '
              'Follow actual visible irregular boundaries, not detector box boundaries. '
              f'Input canvas is {sw}x{sh}. Original photograph size is {w}x{h}; '
              f'its position on the unscaled {cw}x{ch} canvas is x=[{ox},{ox+w}), y=[{oy},{oy+h}). '
              f'Map original coordinates to input by x_input=(x+{ox})*{sw/cw}, y_input=(y+{oy})*{sh/ch}. '
              'Magenta outside the photograph is artificial padding and MUST become black. ')
    if targets:
        prompt += 'Detector hints in ORIGINAL pixel coordinates: ' + json.dumps(targets, ensure_ascii=False) + '. Segment actual defects near these hints. '
    else:
        prompt += 'No detector annotations. Inspect for confidently visible defects; if none, return an all-black mask. Do not infer concealed damage. '
    labels = sorted({x['class'] for x in targets}) or list(DEFINITIONS)
    prompt += 'Class definitions: ' + '; '.join(k + ': ' + DEFINITIONS.get(k,k) for k in labels)
    prompt += '. Return UNION of target defects as one binary image. Preserve thin cracks without exaggerating width. Exclude ordinary texture, shadows and intact surfaces.'
    return original, buf.getvalue(), {'source_sha256':digest(source), 'original_size':[w,h], 'canvas_size':[cw,ch], 'input_size':[sw,sh], 'crop':[ox,oy,ox+w,oy+h], 'prompt':prompt, 'annotations':targets}

def call_api(model, key, input_png, prompt):
    url = model['base_url'].rstrip('/') + '/' + model.get('endpoint','/v1/images/edits').lstrip('/')
    if urlsplit(url).scheme != 'https': raise ValueError('API 地址必须使用 HTTPS')
    headers = {'Authorization':'Bearer ' + key, 'Accept':'application/json', **model.get('headers',{})}
    payload = {**model.get('params',{}), 'model':model['model'], 'prompt':prompt, 'n':1}
    options = dict(headers=headers, timeout=(20, model.get('timeout_seconds',600)), allow_redirects=False)
    field = model.get('image_field','image')
    with requests.Session() as session:
        if model.get('proxy'):
            session.trust_env = False
            session.proxies.update({'http': model['proxy'], 'https': model['proxy']})
        if model.get('transport') == 'dashscope':
            with Image.open(io.BytesIO(input_png)) as im:
                w,h=im.size
                scale=min(1,math.sqrt((2048*2048)/(w*h)))
                scale=max(scale,math.sqrt((512*512)/(w*h)))
                ow,oh=max(16,int(w*scale)//16*16),max(16,int(h*scale)//16*16)
                while ow*oh < 512*512: ow+=16;oh+=16
                mime='image/png';image_bytes=input_png
                if len(image_bytes)>10*1024*1024:
                    buf=io.BytesIO();im.convert('RGB').save(buf,format='JPEG',quality=95)
                    image_bytes=buf.getvalue();mime='image/jpeg'
                if len(image_bytes)>10*1024*1024:raise ValueError('Qwen 输入图片超过10MB，请降低 max_canvas_side')
            payload={'model':model['model'],'input':{'messages':[{'role':'user','content':[
                {'image':'data:'+mime+';base64,'+base64.b64encode(image_bytes).decode('ascii')},
                {'text':prompt}]}]},'parameters':{'size':f'{ow}*{oh}',**model.get('params',{}),'n':1}}
            response=session.post(url,json=payload,**options)
        elif model.get('transport','multipart') == 'multipart':
            response = session.post(url, data=payload, files={field:('input.png', input_png, 'image/png')}, **options)
        elif model['transport'] == 'json':
            payload[field] = 'data:image/png;base64,' + base64.b64encode(input_png).decode('ascii')
            response = session.post(url, json=payload, **options)
        else: raise ValueError('transport 仅支持 multipart / json')
    if not response.ok:
        # Do not persist provider bodies: they may echo credentials or request data.
        raise APIError(response.status_code)
    response.raise_for_status()
    data = response.json()
    if model.get('transport') == 'dashscope':
        assets=[part['image'] for choice in data.get('output',{}).get('choices',[])
                for part in choice.get('message',{}).get('content',[]) if part.get('image')]
        if len(assets)!=1:raise ValueError('Qwen 未返回单张图像，请检查返回格式')
        return {'url':assets[0]},data.get('usage'),data.get('request_id')
    assets = data.get('data') or []
    if not assets: raise ValueError('API 未返回 data 图像数组；该接口可能不是图像编辑接口')
    return assets[0], data.get('usage'), response.headers.get('x-request-id')

class APIError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f'API HTTP {status}')

def asset_bytes(asset, proxy=None):
    if asset.get('b64_json'):
        return base64.b64decode(asset['b64_json'], validate=True)
    url = asset.get('url')
    if url and urlsplit(url).scheme == 'https':
        # No API authorization header is forwarded to the image host.
        response = requests.get(url, timeout=(20,120), proxies={'https':proxy} if proxy else None); response.raise_for_status()
        return response.content
    raise ValueError('API 未返回 b64_json 或 HTTPS 图片 URL')

def cost(usage, pricing):
    if pricing and pricing.get('mode') == 'per_request':
        return float(pricing['amount'])
    if not usage or not pricing: return None
    if pricing.get('mode') == 'images':
        ni,no=usage.get('input_image_count'),usage.get('output_image_count')
        pi=pricing['input_rates'].get(usage.get('input_image_type'))
        po=pricing['output_rates'].get(usage.get('output_image_type'))
        if any(v is None for v in (ni,no,pi,po)):return None
        return ni*pi+no*po
    total = 0
    for entry in pricing.get('components',[]):
        value = usage
        for part in entry['usage_path'].split('.'):
            value = value.get(part) if isinstance(value,dict) else None
        if not isinstance(value,(int,float)): return None
        total += value * entry['usd_per_million'] / 1e6
    return total * pricing.get('multiplier',1) if pricing.get('components') else None

def write_images(original, blob, meta, mask_path, overlay_path):
    """仅二值化和恢复尺寸，不做轮廓修正。叠加图严格使用同一个最终 mask。"""
    with Image.open(io.BytesIO(blob)) as im:
        expected = meta['input_size']
        aspect_error = abs((im.width / im.height) / (expected[0] / expected[1]) - 1)
        if aspect_error > 0.02:
            # Never silently stretch an incompatible generated canvas and call it aligned.
            raise ValueError('model_canvas_aspect_mismatch')
        rgba = im.convert('RGBA')
        black = Image.new('RGBA', im.size, 'black')
        black.alpha_composite(rgba)
        binary = black.convert('L').point(lambda v: 255 if v >= THRESHOLD else 0)
    mask = binary.resize(tuple(meta['canvas_size']), Image.Resampling.NEAREST).crop(tuple(meta['crop']))
    assert mask.size == original.size
    rgb = np.asarray(original)
    selected = np.asarray(mask) > 0
    overlay = rgb.copy()
    overlay[selected] = np.rint(rgb[selected] * (1-OVERLAY_ALPHA) + np.array([255,0,0]) * OVERLAY_ALPHA).astype(np.uint8)
    for image, path in ((mask, mask_path), (Image.fromarray(overlay), overlay_path)):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        image.save(tmp, format='PNG')
        tmp.replace(path)

def usage_fields(usage):
    usage = usage or {}
    ins = usage.get('input_tokens_details') or {}
    outs = usage.get('output_tokens_details') or {}
    input_tokens, output_tokens = usage.get('input_tokens'), usage.get('output_tokens')
    total = usage.get('total_tokens')
    if total is None and isinstance(input_tokens,int) and isinstance(output_tokens,int):
        total = input_tokens + output_tokens
    return dict(input_image_count=usage.get('input_image_count'),output_image_count=usage.get('output_image_count'),
                input_image_type=usage.get('input_image_type'),output_image_type=usage.get('output_image_type'),
                input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total,
                input_text_tokens=ins.get('text_tokens'), input_image_tokens=ins.get('image_tokens'),
                output_text_tokens=outs.get('text_tokens'), output_image_tokens=outs.get('image_tokens'))
