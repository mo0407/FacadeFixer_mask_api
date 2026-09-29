"""Deterministic bbox/class-conditioned OpenCV segmentation. No model mask input."""
import argparse,json,time,hashlib,csv
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
VERSION='opencv-facade-1.0'
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encode(m):
 a=m.astype(np.uint8).ravel(order='F');cuts=np.flatnonzero(np.diff(a))+1;counts=np.diff(np.r_[0,cuts,a.size]).tolist()
 if a[0]:counts.insert(0,0)
 return {'size':list(m.shape),'order':'F','counts':counts}
def clean(m,area=5,linear=False):
 n,lab,st,_=cv2.connectedComponentsWithStats(m.astype(np.uint8),8);keep=np.zeros(n,bool)
 for k in range(1,n):
  x,y,w,h,a=st[k];keep[k]=a>=area and (not linear or max(w,h)>=5 and (max(w,h)/max(1,min(w,h))>1.7 or a/(w*h)<.40))
 return keep[lab]
def odd(v):return max(3,int(v)//2*2+1)
def kernel(k):return cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(odd(k),odd(k)))
def holes(m,max_area):
 n,lab,st,_=cv2.connectedComponentsWithStats((~m).astype(np.uint8),8);out=m.copy();h,w=m.shape
 for k in range(1,n):
  x,y,cw,ch,a=st[k]
  if x>0 and y>0 and x+cw<w and y+ch<h and a<=max_area:out[lab==k]=True
 return out
def otsu(a):return float(cv2.threshold(a,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[0])
def segment(rgb,box,code,subtype='',max_roi=1000):
 x1,y1,x2,y2=box;roi=rgb[y1:y2,x1:x2];oh,ow=roi.shape[:2];flags=[];params={};scale=1.0
 # Thin fissures stay at original resolution; area regions use bounded computation.
 if code not in ('C','M') and max(oh,ow)>max_roi:
  scale=max_roi/max(oh,ow);roi=cv2.resize(roi,(max(2,round(ow*scale)),max(2,round(oh*scale))),interpolation=cv2.INTER_AREA);flags.append('area_roi_downsampled')
 h,w=roi.shape[:2];g=cv2.cvtColor(roi,cv2.COLOR_RGB2GRAY);hsv=cv2.cvtColor(roi,cv2.COLOR_RGB2HSV);s=hsv[:,:,1];hue=hsv[:,:,0];v=hsv[:,:,2]
 if code in ('C','M'):
  method='multiscale_blackhat_linear_components';short=min(h,w)
  sizes=sorted(set(odd(min(31,max(5,short*f))) for f in [.025,.05,.09]))
  smooth=cv2.GaussianBlur(g,(3,3),.5);bh=np.maximum.reduce([cv2.morphologyEx(smooth,cv2.MORPH_BLACKHAT,kernel(k)) for k in sizes])
  threshold=max(7.,min(30.,otsu(bh)*.65));dark_limit=float(np.percentile(g,80))
  m=(bh>threshold)&(g<dark_limit);m=clean(m,max(5,round(h*w*.000015)),True)
  params={'blackhat_kernels':sizes,'response_threshold':threshold,'gray_upper':dark_limit,'opening':False,'native_resolution':True};flags+=['joints_pipes_and_texture_can_mimic_cracks']
 elif code in ('T','R'):
  method='hsv_lab_rust_color';lab=cv2.cvtColor(roi,cv2.COLOR_RGB2LAB)
  m=(((hue<27)|(hue>173))&(s>48)&(v>28)&(lab[:,:,1]>127)&(lab[:,:,2]>132))
  m=clean(m,3);m=holes(m,12);params={'hue_opencv':[0,27,173,179],'saturation_min':48,'value_min':28,'lab_a_min':127,'lab_b_min':132};flags+=['red_paint_and_brown_substrate_can_mimic_rust']
 elif code=='V':
  method='green_or_dark_vegetation';green=(hue>29)&(hue<100)&(s>38)&(v>28)
  threshold=min(135,max(45,otsu(g)));dark=g<threshold
  m=clean(green|dark,max(3,round(h*w*.0001)));params={'hue':[29,100],'saturation_min':38,'dark_otsu_capped':threshold};flags+=['dark_plant_shadow_ambiguity']
 elif code=='D' and subtype=='GroundLitter':
  method='lab_floor_background_deviation';lab=cv2.cvtColor(roi,cv2.COLOR_RGB2LAB).astype(np.float32)
  # Dark low-chroma floor is dominant; retain brighter/colorful foreign objects.
  bg=np.median(lab[g<=np.percentile(g,55)],axis=0);dist=np.linalg.norm((lab-bg)*np.array([.65,1.0,1.0]),axis=2)
  light=g>max(95,float(np.percentile(g,70)));color=(s>55)&(dist>23)
  m=clean(light|color,max(3,round(h*w*.000008)));params={'background_lab':bg.tolist(),'gray_threshold':max(95,float(np.percentile(g,70))),'chroma_distance':23};flags+=['dark_fabric_may_be_missed','bright_floor_can_be_false_positive']
 elif code in ('D','L'):
  method='dark_stain_global_local_contrast';smooth=cv2.GaussianBlur(g,(0,0),max(2,min(h,w)*.045));res=smooth.astype(np.float32)-g
  threshold=otsu(g);m=(g<threshold*.97)|((res>9)&(g<np.percentile(g,72)))
  if code=='L':m|=((hue<33)&(s>45)&(v>35)&(g<np.percentile(g,80)))
  m=clean(m,max(4,round(h*w*.00003)));m=holes(m,max(10,round(h*w*.00004)))
  params={'dark_threshold':threshold*.97,'local_response_threshold':9};flags+=['shadow_and_surface_stain_ambiguity']
 elif code in ('P','S'):
  method='border_background_lab_clusters_grabcut'
  lab=cv2.cvtColor(roi,cv2.COLOR_RGB2LAB).astype(np.float32);flat=lab.reshape(-1,3);rng=np.random.default_rng(20260928)
  sample=flat[rng.choice(len(flat),min(16000,len(flat)),replace=False)]
  cv2.setRNGSeed(20260928);_,_,centers=cv2.kmeans(sample,4,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,35,.25),3,cv2.KMEANS_PP_CENTERS)
  labels=np.argmin(np.sum((lab[:,:,None,:]-centers[None,None,:,:])**2,axis=3),axis=2)
  edge=np.zeros((h,w),bool);bw=max(1,round(min(h,w)*.06));edge[:bw]=True;edge[-bw:]=True;edge[:,:bw]=True;edge[:,-bw:]=True
  freq=np.bincount(labels[edge],minlength=4)/edge.sum();bg=int(np.argmax(freq));distance=np.linalg.norm(centers-centers[bg],axis=1)
  inside=np.bincount(labels.ravel(),minlength=4)/(h*w)
  selected=(distance>max(12,float(np.max(distance))*.27))&(freq<np.maximum(.34,inside*1.4));selected[bg]=False
  if not selected.any():selected[np.argmax(distance)]=True;flags.append('weak_color_separation_fallback')
  seed=selected[labels];gc=np.where(seed,cv2.GC_PR_FGD,cv2.GC_PR_BGD).astype(np.uint8)
  sure=cv2.erode(seed.astype(np.uint8),np.ones((3,3),np.uint8))>0;gc[sure]=cv2.GC_FGD
  gc[edge&(~seed)]=cv2.GC_BGD
  if np.any(gc==cv2.GC_FGD) and np.any(gc==cv2.GC_BGD):
   try:
    cv2.setRNGSeed(20260928);cv2.grabCut(roi,gc,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),3,cv2.GC_INIT_WITH_MASK);m=(gc==1)|(gc==3)
   except cv2.error:m=seed;flags.append('grabcut_failed_used_cluster_seed')
  else:m=seed;flags.append('insufficient_grabcut_seeds')
  m=clean(m,max(6,round(h*w*.00008)));m=holes(m,max(16,round(h*w*.001)))
  params={'lab_centers':centers.tolist(),'background_cluster':bg,'selected_clusters':np.flatnonzero(selected).tolist(),'grabcut_iterations':3,'border_fraction':.06};flags+=['bbox_border_assumed_sound','substrate_and_intact_coating_may_swap']
 else:raise ValueError(f'Unsupported class {code}')
 if box==[0,0,rgb.shape[1],rgb.shape[0]]:flags.append('full_frame_bbox_weak_background_prior')
 fraction=float(m.mean())
 if fraction<.0001:flags.append('empty_or_tiny_foreground')
 if fraction>.85:flags.append('near_filled_bbox_requires_review')
 if m.shape!=(oh,ow):m=cv2.resize(m.astype(np.uint8),(ow,oh),interpolation=cv2.INTER_NEAREST)>0
 return m,{'method':method,'parameters':params,'roi_scale':scale,'quality_flags':flags}
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--output',required=True);p.add_argument('--max-roi',type=int,default=1000);args=p.parse_args()
 inp=Path(args.manifest).resolve();out=Path(args.output).resolve();items=json.loads(inp.read_text(encoding='utf-8'))['images'];out.mkdir(parents=True,exist_ok=True)
 if (out/'run.json').exists():raise RuntimeError('Output already has a completed run; choose a new directory.')
 for folder in ['masks','instance_masks','class_masks','overlays','bbox_overlays','annotations','previews']:(out/folder).mkdir(exist_ok=True)
 cv2.setNumThreads(1);cv2.setRNGSeed(20260928);records=[];start=time.perf_counter()
 for item in items:
  tick=time.perf_counter();path=Path(item['image_path']);rgb=np.asarray(Image.open(path).convert('RGB'));h,w=rgb.shape[:2];sid=path.stem;union=np.zeros((h,w),bool);overlay=rgb.copy();boxim=Image.fromarray(rgb);draw=ImageDraw.Draw(boxim);ds=[];cm={}
  for n,d in enumerate(item['defects']):
   t=time.perf_counter();box=d['bbox_xyxy'];x1,y1,x2,y2=box;assert 0<=x1<x2<=w and 0<=y1<y2<=h
   patch,info=segment(rgb,box,d['class_code'],d.get('class_subtype',''),args.max_roi);m=np.zeros((h,w),bool);m[y1:y2,x1:x2]=patch;union|=m
   code=d['class_code'];cm.setdefault(code,np.zeros((h,w),bool));cm[code]|=m
   color=[(255,60,60),(50,220,80),(50,150,255),(255,190,30),(220,60,255),(40,230,225)][n%6]
   overlay[m]=np.rint(rgb[m]*.55+np.array(color)*.45).astype(np.uint8);draw.rectangle((x1,y1,x2-1,y2-1),outline=color,width=max(1,round(min(w,h)/250)));draw.text((x1,max(0,y1-14)),str(d['id'])+' '+code,fill=color)
   rel=f'instance_masks/{sid}_{d["id"]}.png';Image.fromarray(m.astype(np.uint8)*255).save(out/rel)
   ds.append({**d,'bbox_xywh':[x1,y1,x2-x1,y2-y1],'bbox_normalized_xyxy':[x1/w,y1/h,x2/w,y2/h],'mask_path':rel,'area_pixels':int(m.sum()),'segmentation_rle':encode(m),'overlay_color_rgb':color,'seconds':time.perf_counter()-t,**info})
  Image.fromarray(union.astype(np.uint8)*255).save(out/'masks'/f'{sid}.png');Image.fromarray(overlay).save(out/'overlays'/f'{sid}.png');boxim.save(out/'bbox_overlays'/f'{sid}.png')
  classpaths={}
  for code,m in cm.items():rel=f'class_masks/{sid}_{code}.png';Image.fromarray(m.astype(np.uint8)*255).save(out/rel);classpaths[code]=rel
  sec=time.perf_counter()-tick
  a={'schema_version':'facade_opencv_v1','image_index':item['index'],'file_name':path.name,'source_path':str(path),'source_sha256':sha(path),'width':w,'height':h,'bbox_convention':'zero_based_xyxy_max_exclusive','defects':ds,'mask_path':f'masks/{sid}.png','overlay_path':f'overlays/{sid}.png','class_mask_paths':classpaths,'foreground_pixels':int(union.sum()),'foreground_fraction':float(union.mean()),'classes_present':sorted(cm),'seconds':sec,'processing_resolution':[w,h],'token_usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0},'actual_charge':0,'cost_scope':'No API calls; excludes local compute/electricity','method_version':VERSION,'status':'candidate_requires_review','review':{'expert_validated':False,'pixel_accuracy_verified':False},'input_manifest_sha256':sha(inp),'model_mask_used_as_input':False,'elapsed_scope':'image decode, segmentation, mask/overlay/bbox export; excludes preview, JSON serialization and evaluation'}
  dump(out/'annotations'/f'{sid}.json',a);records.append({'index':item['index'],'file_name':path.name,'instances':len(ds),'seconds':sec,'tokens':0,'api_cost':0})
  sw=min(420,w);sh=max(1,round(h*sw/w));sh=min(sh,900);sw=max(1,round(w*sh/h));pr=Image.new('RGB',(sw*4,sh+28),'white');pd=ImageDraw.Draw(pr)
  for k,(im,label) in enumerate([(Image.fromarray(rgb),'Original'),(boxim,'Bboxes'),(Image.fromarray(union.astype(np.uint8)*255).convert('RGB'),'OpenCV mask'),(Image.fromarray(overlay),'OpenCV overlay')]):pr.paste(im.resize((sw,sh)),(k*sw,28));pd.text((k*sw+4,7),label,fill='black')
  pr.save(out/'previews'/f'{sid}.jpg',quality=92);print(f'{item["index"]:02d} {len(ds)} instances {sec:.3f}s',flush=True)
 with (out/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
 dump(out/'run.json',{'version':VERSION,'opencv':cv2.__version__,'seed':20260928,'threads':1,'manifest_sha256':sha(inp),'script_sha256':sha(__file__),'images':len(items),'instances':sum(r['instances'] for r in records),'wall_seconds':time.perf_counter()-start,'segmentation_export_seconds':sum(r['seconds'] for r in records),'max_area_roi':args.max_roi,'model_mask_used_as_input':False,'api_calls':0,'tokens':0,'api_cost':0})
if __name__=='__main__':main()
