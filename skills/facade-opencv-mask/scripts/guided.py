"""Assisted segmentation: explicit original-coordinate guides, never bbox-only baseline."""
import argparse,json,time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
from segment import encode,dump,sha
VERSION='facade-guided-1.0'
def polygon(shape,points,offset=(0,0)):
 pts=np.asarray(points,np.float32)
 if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<3 or not np.isfinite(pts).all():raise ValueError('Polygon needs >=3 finite xy points')
 m=np.zeros(shape,np.uint8);cv2.fillPoly(m,[np.rint(pts-np.array(offset)).astype(np.int32)],1);return m>0
def crack_path(rgb,points,search_radius=8,max_half_width=8,response_min=6,edge_floor=4,relative_width_threshold=.3,guide_penalty=.15,smoothness=.6,max_step=3):
 pts=np.asarray(points,np.float32)
 if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<2 or not np.isfinite(pts).all():raise ValueError('Path needs >=2 finite xy points')
 pts=pts[np.r_[True,np.linalg.norm(np.diff(pts,axis=0),axis=1)>1e-4]]
 if len(pts)<2:raise ValueError('Zero-length path')
 search_radius=int(search_radius);max_half_width=int(max_half_width)
 if not 1<=search_radius<=64 or not 1<=max_half_width<=64:raise ValueError('Radii must be 1..64 original pixels')
 arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))];ss=np.linspace(0,arc[-1],max(2,int(np.ceil(arc[-1]))+1))
 center=np.column_stack([np.interp(ss,arc,pts[:,k]) for k in [0,1]]).astype(np.float32);tangent=np.gradient(center,axis=0)
 if len(tangent)>5:tangent=cv2.GaussianBlur(tangent,(1,5),0)
 tangent/=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-6);normal=np.column_stack([-tangent[:,1],tangent[:,0]])
 pad=search_radius+max_half_width+12;H,W=rgb.shape[:2];x0=max(0,int(pts[:,0].min())-pad);y0=max(0,int(pts[:,1].min())-pad);x2=min(W,int(pts[:,0].max())+pad+1);y2=min(H,int(pts[:,1].max())+pad+1)
 if x2<=x0 or y2<=y0:raise ValueError('Guide outside image')
 gray=cv2.cvtColor(rgb[y0:y2,x0:x2],cv2.COLOR_RGB2GRAY).astype(np.float32);blur=cv2.GaussianBlur(gray,(0,0),.6);response=np.maximum(0,cv2.GaussianBlur(blur,(0,0),4)-blur)
 extent=search_radius+max_half_width;offsets=np.arange(-extent,extent+1,dtype=np.float32);sample=center[:,None,:]+normal[:,None,:]*offsets[None,:,None];sx=sample[:,:,0]-x0;sy=sample[:,:,1]-y0
 values=cv2.remap(response,sx.astype(np.float32),sy.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)
 valid=(sample[:,:,0]>=0)&(sample[:,:,0]<W)&(sample[:,:,1]>=0)&(sample[:,:,1]<H)
 states=np.arange(-search_radius,search_radius+1);columns=states+extent;response_cost=-values[:,columns]/10+guide_penalty*(states[None,:]/search_radius)**2
 response_cost[~valid[:,columns]]=1e8;n,K=response_cost.shape;parents=np.zeros((n,K),np.int32);cost=response_cost[0].copy()
 for i in range(1,n):
  nxt=np.full(K,np.inf)
  for k in range(K):
   lo=max(0,k-max_step);hi=min(K,k+max_step+1);candidate=cost[lo:hi]+smoothness*np.abs(states[lo:hi]-states[k]);j=int(np.argmin(candidate))+lo;parents[i,k]=j;nxt[k]=candidate[j-lo]+response_cost[i,k]
  cost=nxt
 chosen=np.zeros(n,np.int32);chosen[-1]=int(np.argmin(cost))
 for i in range(n-1,0,-1):chosen[i-1]=parents[i,chosen[i]]
 mask=np.zeros((H,W),np.uint8);path=[];widths=[];missed=0
 for i,k in enumerate(chosen):
  col=int(columns[k]);strength=values[i,col];path.append(sample[i,col].tolist())
  if strength<response_min or not valid[i,col]:widths.append(0);missed+=1;continue
  threshold=max(edge_floor,strength*relative_width_threshold);l=r=col
  while l>max(0,col-max_half_width) and valid[i,l-1] and values[i,l-1]>=threshold:l-=1
  while r<min(len(offsets)-1,col+max_half_width) and valid[i,r+1] and values[i,r+1]>=threshold:r+=1
  cv2.line(mask,tuple(np.rint(sample[i,l]).astype(int)),tuple(np.rint(sample[i,r]).astype(int)),1,1);widths.append(r-l+1)
 return mask>0,{'solver':'normal_band_dynamic_programming','optimized_path_xy':path,'width_pixels':widths,'unsupported_samples':missed,'total_samples':n,'parameters':{'search_radius':search_radius,'max_half_width':max_half_width,'response_min':response_min,'edge_floor':edge_floor,'relative_width_threshold':relative_width_threshold,'guide_penalty':guide_penalty,'smoothness':smoothness,'max_step':max_step}}
def solve(rgb,d):
 H,W=rgb.shape[:2];box=d['bbox_xyxy'];x1,y1,x2,y2=map(int,box)
 if box!=[x1,y1,x2,y2] or not 0<=x1<x2<=W or not 0<=y1<y2<=H:raise ValueError('Invalid original-coordinate xyxy bbox')
 limit=np.zeros((H,W),bool);limit[y1:y2,x1:x2]=True;exclude=np.zeros((H,W),bool)
 for pts in d.get('exclude_polygons',[]):exclude|=polygon((H,W),pts)
 result=np.zeros((H,W),bool);records=[]
 for op in d['operations']:
  kind=op['kind'];flags=[]
  if kind=='path':m,info=crack_path(rgb,op['points'],**op.get('parameters',{}))
  elif kind=='polygon_grabcut':
   band=int(op.get('band_px',5));iters=int(op.get('iterations',5))
   if band<1 or iters<1:raise ValueError('Positive band/iteration count required')
   seed=polygon((y2-y1,x2-x1),op['points'],(x1,y1));ex=exclude[y1:y2,x1:x2]
   k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(band*2+1,band*2+1));er=cv2.erode(seed.astype(np.uint8),k,borderType=cv2.BORDER_CONSTANT,borderValue=0)>0;di=cv2.dilate(seed.astype(np.uint8),k)>0
   gc=np.full(seed.shape,cv2.GC_BGD,np.uint8);gc[di]=cv2.GC_PR_BGD;gc[seed]=cv2.GC_PR_FGD;gc[er]=cv2.GC_FGD;gc[ex]=cv2.GC_BGD
   if not np.any(gc==cv2.GC_FGD) or not np.any(gc==cv2.GC_BGD):raise ValueError('Polygon lacks foreground/background seeds; adjust polygon/bbox/band, not fill bbox')
   cv2.setRNGSeed(20260928);cv2.grabCut(rgb[y1:y2,x1:x2].copy(),gc,None,np.zeros((1,65)),np.zeros((1,65)),iters,cv2.GC_INIT_WITH_MASK)
   m=np.zeros((H,W),bool);m[y1:y2,x1:x2]=(gc==1)|(gc==3);info={'solver':'polygon_trimap_grabcut','parameters':{'band_px':band,'iterations':iters}}
  elif kind=='color':
   region=polygon((H,W),op['points'])&limit;hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);m=np.zeros((H,W),bool)
   for lo,hi in op['hsv_ranges']:
    if any(a>b for a,b in zip(lo,hi)):raise ValueError('Hue wrap must use separate intervals')
    m|=cv2.inRange(hsv,np.array(lo,np.uint8),np.array(hi,np.uint8))>0
   signed=rgb.astype(np.int16);channels={'R':signed[:,:,0],'G':signed[:,:,1],'B':signed[:,:,2]}
   for diff,minimum in op.get('rgb_difference_min',{}).items():
    if diff not in ('R-G','R-B','G-R','B-G','B-R'):raise ValueError('Unsupported RGB difference')
    a,b=diff.split('-');m &= (channels[a]-channels[b])>float(minimum)
   m &= region;info={'solver':'polygon_hsv_rgb_difference','parameters':{'hsv_ranges':op['hsv_ranges'],'rgb_difference_min':op.get('rgb_difference_min',{})}}
  elif kind=='brightness':
   gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);sigma=float(op.get('sigma',.6));gray=cv2.GaussianBlur(gray,(0,0),sigma) if sigma>0 else gray
   lo=float(op.get('gray_min',0));hi=float(op.get('gray_max',255))
   if not 0<=lo<=hi<=255:raise ValueError('Invalid brightness interval')
   m=polygon((H,W),op['points'])&(gray>=lo)&(gray<=hi);info={'solver':'polygon_brightness','parameters':{'gray_min':lo,'gray_max':hi,'sigma':sigma}}
  else:raise ValueError(f'Unknown operation {kind}')
  outside=int((m&~limit).sum());m &= limit&~exclude;result|=m
  if outside:flags.append('candidate_clipped_by_bbox')
  if not m.any():flags.append('empty_operation')
  records.append({**info,'kind':kind,'outside_bbox_pixels':outside,'flags':flags})
 result &= ~exclude
 return result,records
def main():
 p=argparse.ArgumentParser();p.add_argument('--guides',required=True);p.add_argument('--output',required=True);args=p.parse_args();guides=Path(args.guides).resolve();data=json.loads(guides.read_text(encoding='utf-8'));out=Path(args.output).resolve()
 if data.get('mode')!='assisted':raise ValueError('Explicit mode=assisted required')
 if out.exists() and any(out.iterdir()):raise ValueError('Use a new output directory')
 for folder in ['masks','instance_masks','class_masks','overlays','annotations','guide_overlays','bbox_overlays']:(out/folder).mkdir(parents=True,exist_ok=True)
 cv2.setNumThreads(1);start=time.perf_counter();rows=[]
 for item in data['images']:
  tick=time.perf_counter();src=Path(item['image_path']);rgb=np.asarray(Image.open(src).convert('RGB'));H,W=rgb.shape[:2];union=np.zeros((H,W),bool);over=rgb.copy();gi=Image.fromarray(rgb);draw=ImageDraw.Draw(gi);boxes=Image.fromarray(rgb);bd=ImageDraw.Draw(boxes);defs=[];class_masks={}
  for d in item['defects']:
   if not d.get('guide_source'):raise ValueError('guide_source must identify the source of extra visual information')
   m,operations=solve(rgb,d);union|=m;rel=f'instance_masks/{src.stem}_{d["id"]}.png';Image.fromarray(m.astype(np.uint8)*255).save(out/rel);over[m]=np.rint(rgb[m]*.55+np.array([255,50,50])*.45).astype(np.uint8)
   class_masks.setdefault(d['class_code'],np.zeros((H,W),bool));class_masks[d['class_code']]|=m
   x1,y1,x2,y2=d['bbox_xyxy'];bd.rectangle((x1,y1,x2-1,y2-1),outline='red',width=2);bd.text((x1,max(0,y1-12)),f'{d["id"]} {d["class_code"]}',fill='red')
   for op in d['operations']:
    pts=[tuple(x) for x in op['points']];draw.line(pts+([pts[0]] if op['kind']!='path' else []),fill='cyan',width=2)
   for pts in d.get('exclude_polygons',[]):draw.polygon([tuple(x) for x in pts],outline='yellow',width=2)
   defs.append({**d,'mask_path':rel,'area_pixels':int(m.sum()),'segmentation_rle':encode(m),'solvers':operations,'guide_edit_seconds':d.get('guide_edit_seconds'),'assistance_count':len(d['operations'])})
  Image.fromarray(union.astype(np.uint8)*255).save(out/'masks'/f'{src.stem}.png');Image.fromarray(over).save(out/'overlays'/f'{src.stem}.png');gi.save(out/'guide_overlays'/f'{src.stem}.png')
  boxes.save(out/'bbox_overlays'/f'{src.stem}.png')
  for code,cm in class_masks.items():Image.fromarray(cm.astype(np.uint8)*255).save(out/'class_masks'/f'{src.stem}_{code}.png')
  rec={'image_index':item.get('index'),'file_name':src.name,'source_path':str(src),'source_sha256':sha(src),'width':W,'height':H,'bbox_convention':'zero_based_xyxy_max_exclusive','mode':'assisted','version':VERSION,'defects':defs,'mask_path':f'masks/{src.stem}.png','overlay_path':f'overlays/{src.stem}.png','class_mask_paths':{c:f'class_masks/{src.stem}_{c}.png' for c in class_masks},'revision_reason':item.get('revision_reason'),'previous_run':item.get('previous_run'),'seconds':time.perf_counter()-tick,'elapsed_scope':'local segmentation and image export; excludes guide creation and JSON serialization','guides_sha256':sha(guides),'token_usage':{'opencv_stage':0,'guide_creation':None},'api_cost':{'opencv_stage':0,'guide_creation':None},'expert_validated':False};dump(out/'annotations'/f'{src.stem}.json',rec);rows.append({'image':src.name,'seconds':rec['seconds']})
 dump(out/'run.json',{'mode':'assisted','version':VERSION,'images':rows,'seconds':time.perf_counter()-start,'guide_creation_included':False,'guides_sha256':sha(guides),'script_sha256':sha(__file__)})
 print(json.dumps({'images':len(rows),'output':str(out)}))
if __name__=='__main__':main()
