"""Observable synthetic checks; not a real-world accuracy evaluation."""
import tempfile,json,subprocess,sys
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
from guided import crack_path,solve
from segment import encode
def main():
 im=np.full((200,200,3),210,np.uint8)
 # Variable-width target, interrupted in its middle; stronger distractor outside band.
 im[20:180,99:102]=35;im[115:180,97:104]=35;im[80:106,95:106]=210;im[20:180,127:132]=0
 m,info=crack_path(im,[[96,20],[96,179]],search_radius=9,response_min=8)
 assert m[30:70,97:104].sum()>100
 assert m[:,120:].sum()==0,'Jumped outside search band'
 assert m[89:98].sum()==0,'Filled unsupported crack gap'
 assert np.median(m[125:165].sum(axis=1))>np.median(m[30:65].sum(axis=1)),'Lost variable width'
 rgb=np.full((120,140,3),205,np.uint8);cv2.circle(rgb,(70,60),27,(70,100,150),-1)
 d={'id':1,'bbox_xyxy':[20,10,120,110],'operations':[{'kind':'polygon_grabcut','points':[[48,38],[92,38],[92,82],[48,82]],'band_px':9}],'exclude_polygons':[[[65,55],[75,55],[75,65],[65,65]]]}
 pm,_=solve(rgb,d);assert not pm[55:66,65:76].any();assert pm[42:51,65:76].any();assert not pm[:10].any();assert not pm[:,120:].any()
 again,_=solve(rgb,d);assert np.array_equal(pm,again),'Non-deterministic result'
 colors=np.zeros((30,40,3),np.uint8);colors[:,:20]=[180,100,50];colors[:,20:]=[70,150,90]
 cd={'bbox_xyxy':[0,0,40,30],'operations':[{'kind':'color','points':[[0,0],[39,0],[39,29],[0,29]],'hsv_ranges':[[[0,0,0],[179,255,255]]],'rgb_difference_min':{'R-G':25,'R-B':40}}]}
 colored,_=solve(colors,cd);assert colored[:,:20].all() and not colored[:,20:].any(),'Unsigned RGB difference regression'
 cd['operations']=[{'kind':'brightness','points':[[0,0],[39,0],[39,29],[0,29]],'gray_min':0,'gray_max':10,'sigma':0}]
 empty,_=solve(colors,cd);assert not empty.any(),'Unsupported dark foreground invented'
 try:crack_path(rgb,[[1,1],[1,1]])
 except ValueError:pass
 else:raise AssertionError('Degenerate guide accepted')
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);Image.fromarray(rgb).save(root/'source.png');d.update(class_code='P',guide_source='synthetic_fixture',guide_edit_seconds=None)
  data={'mode':'assisted','images':[{'index':0,'image_path':str(root/'source.png'),'defects':[d]}]};(root/'guides.json').write_text(json.dumps(data),encoding='utf-8')
  subprocess.run([sys.executable,str(Path(__file__).with_name('guided.py')),'--guides',str(root/'guides.json'),'--output',str(root/'output')],check=True)
  a=json.loads((root/'output/annotations/source.json').read_text(encoding='utf-8'));saved=np.asarray(Image.open(root/'output/instance_masks/source_1.png'))>0
  assert saved.shape==(120,140);assert a['defects'][0]['segmentation_rle']==encode(saved);assert a['mode']=='assisted';assert a['defects'][0]['guide_edit_seconds'] is None
  assert np.array_equal(np.asarray(Image.open(root/'output/class_masks/source_P.png'))>0,saved)
 print('PASS: variable width, supported path offset, gap preservation, distractor rejection, exclusion holes, bbox clipping, determinism, degenerate-guide rejection, CLI dimensions/RLE/provenance.')
if __name__=='__main__':main()
