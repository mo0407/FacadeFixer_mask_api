"""Offline validation of all 109 coordinate transforms; no API requests."""
import io
import numpy as np
from PIL import Image
import batch_local as batch
def main():
 items=batch.core.read(batch.ROOT/'input_manifest.json')['images'];count=0
 b=io.BytesIO();Image.new('L',(1254,1254),255).save(b,format='PNG')
 for it in items:
  for d in it['defects']:
   original,canvas,meta=batch.make_input(it,d);assert canvas.size==(1024,1024)
   restored,size=batch.local.restore(b.getvalue(),meta);x,y,X,Y=meta['roi_xyxy'];assert restored.shape==(original.height,original.width);assert restored.sum()==(X-x)*(Y-y)
   hit=np.zeros_like(restored,dtype='uint8')
   for t in meta['tiles']:
    a,c,A,C=t['source_xyxy'];hit[c:C,a:A]+=1;u,v,U,V=t['canvas_xyxy'];assert 0<=u<U<=1024 and 0<=v<V<=1024
   assert hit.max()==1 and np.array_equal(hit>0,restored)
   if d.get('class_subtype'):assert ('ground litter' in meta['prompt'] or 'wall staining' in meta['prompt'])
   count+=1
 print(f'PASS {count} targets: image dimensions, exact coverage, no overlapping tile pastes, canvas bounds, semantic subtype hints; no network.')
if __name__=='__main__':main()
