"""Validate packaged inputs, candidate reference masks and RLE without API calls."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
items=read(ROOT/'data/input/manifest.json')['images'];n=0
for it in items:
 src=ROOT/it['image_path'];a=read(ROOT/'data/reference/annotations'/(src.stem+'.json'))
 assert hashlib.sha256(src.read_bytes()).hexdigest()==a['source_sha256']
 assert (ROOT/'data/reference'/a['source_path']).resolve()==src.resolve()
 assert Image.open(src).size==(a['width'],a['height'])
 defects={d['id']:d for d in a['defects']};assert len(defects)==len(it['defects'])
 total=np.zeros((a['height'],a['width']),bool)
 for d in it['defects']:
  ref=defects[d['id']];assert ref['bbox_xyxy']==d['bbox_xyxy'] and ref['class_code']==d['class_code']
  m=np.asarray(Image.open(ROOT/'data/reference'/ref['mask_path']));assert m.shape==total.shape and np.isin(m,[0,255]).all()
  rle=ref['segmentation_rle'];counts=rle['counts'];assert sum(counts)==m.size
  decoded=np.repeat(np.arange(len(counts))%2,counts).reshape(rle['size'],order=rle.get('order','F'))
  assert np.array_equal(decoded>0,m>0);total|=m>0;n+=1
 assert np.array_equal(total,np.asarray(Image.open(ROOT/'data/reference'/a['mask_path']))>0)
assert len(items)==50 and n==109
print('PASS: 50 images, hashes, relative paths, 109 bbox/type instances, binary masks, RLE and total-mask unions.')
