"""Synthetic offline tests; no image API or production output changes."""
import tempfile
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import refine_api_masks as r

def main():
 rgb=np.full((120,160,3),210,np.uint8);cv2.circle(rgb,(80,60),24,(100,60,40),-1)
 prior=np.zeros((120,160),np.uint8);cv2.circle(prior,(84,60),24,1,-1);prior=prior>0;before=prior.copy()
 for code in ('P','C','D'):
  chosen,candidate,diag=r.refine(rgb,prior,[30,10,130,110],code)
  assert chosen.shape==prior.shape and candidate.shape==prior.shape
  assert np.array_equal(prior,before) and not chosen[:10].any() and not chosen[:,130:].any()
  rr=r.rle(chosen);decoded=np.repeat(np.arange(len(rr['counts']))%2,rr['counts']).reshape(rr['size'],order='F')>0;assert np.array_equal(chosen,decoded)
  if diag['selection']=='raw_fallback':assert np.array_equal(chosen,prior)
 empty=np.zeros_like(prior);chosen,_,diag=r.refine(rgb,empty,[0,0,160,120],'P');assert not chosen.any() and diag['selection']=='raw_fallback'
 try:r.refine(rgb,prior,[0,0,10,10],'P')
 except ValueError:pass
 else:raise AssertionError('Out-of-bbox prior should be rejected')
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);src=root/'input';out=root/'output';src.mkdir();out.mkdir()
  for folder in ['images','raw_masks','raw_overlays','raw_instance_masks','candidate_instance_masks','instance_masks','masks','class_masks','overlays','annotations','records']:(out/folder).mkdir()
  Image.fromarray(rgb).save(src/'photo.png');r.png(src/'raw.png',prior)
  a={'image_index':0,'file_name':'photo.png','source_path':'photo.png','source_sha256':r.sha(src/'photo.png'),'width':160,'height':120,'status':'partial','expected_instances':2,'mask_path':'raw.png','overlay_path':'photo.png','defects':[{'id':1,'class_code':'P','bbox_xyxy':[30,10,130,110],'mask_path':'raw.png'}]}
  (src/'annotations').mkdir();r.save(src/'annotations/photo.json',a)
  row=r.export_image(src,out,a);summary=r.report(out,[a]);assert row['status']=='partial' and summary['instances_available']==1 and summary['expected_instances']==2
  assert (out/'comparison.html').exists() and (out/'candidate_instance_masks/photo_1.png').exists()
 print('PASS: immutable input, dimensions/bbox/RLE, empty fallback, invalid input, partial export, report; no API calls.')
if __name__=='__main__':main()
