"""Offline hybrid refinement of collected API masks. No network/API calls."""
import argparse,csv,hashlib,html,json,os,shutil,time,tempfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parent
COLORS=[(255,60,60),(0,190,255),(255,190,0),(180,60,255),(0,220,110),(255,80,190)]
PARAMS={'version':'hybrid_auto_v1','band_fraction':0.025,'band_min':4,'band_max':32,'region_max_side':1200,'grabcut_iterations':4,'seed':20260929,'min_area_ratio':0.35,'max_area_ratio':2.5,'min_prior_iou':0.10}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 # Unique same-directory temporary file; keep the old file intact on failure.
 fd,name=tempfile.mkstemp(prefix=p.name+'.',suffix='.tmp',dir=p.parent);tmp=Path(name)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:
   json.dump(v,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  for attempt in range(8):
   try:os.replace(tmp,p);break
   except PermissionError:
    if attempt==7:raise
    time.sleep(min(.1*2**attempt,1.0))
 finally:
  try:tmp.unlink(missing_ok=True)
  except PermissionError:pass
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def binary(p):
 with Image.open(p) as im:
  a=np.asarray(im)
  if a.ndim!=2 or not np.isin(a,[0,255]).all():raise ValueError('Expected binary single-channel mask: '+str(p))
 return a>0
def png(p,a):Image.fromarray(a.astype(np.uint8)*255).save(p)
def rle(m):
 a=m.ravel(order='F').astype(np.uint8);idx=np.r_[0,np.flatnonzero(a[1:]!=a[:-1])+1,len(a)];counts=np.diff(idx).tolist()
 if a[0]:counts.insert(0,0)
 return {'size':list(m.shape),'order':'F','counts':counts}
def ellipse(r):return cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(r*2+1,r*2+1))

def refine(rgb,prior,bbox,code):
 """Return selected/candidate mask and diagnostics; no reference masks."""
 h,w=prior.shape;x,y,X,Y=bbox
 if not 0<=x<X<=w or not 0<=y<Y<=h:raise ValueError('Invalid bbox')
 if rgb.shape[:2]!=prior.shape:raise ValueError('Image/mask dimension mismatch')
 limit=np.zeros_like(prior);limit[y:Y,x:X]=True
 if np.any(prior&~limit):raise ValueError('Input mask outside frozen bbox')
 if not prior.any():return prior.copy(),prior.copy(),{'method':'empty_input','selection':'raw_fallback','flags':['empty_input']}
 band=int(np.clip(round(min(X-x,Y-y)*PARAMS['band_fraction']),PARAMS['band_min'],PARAMS['band_max']))
 a=max(0,x-band);b=max(0,y-band);A=min(w,X+band);B=min(h,Y+band)
 rgb_roi=rgb[b:B,a:A];p=prior[b:B,a:A];allowed=limit[b:B,a:A]
 scale=1.0
 if code not in ('C','M'):
  scale=min(1,PARAMS['region_max_side']/max(p.shape))
  if scale<1:
   size=(max(1,round(p.shape[1]*scale)),max(1,round(p.shape[0]*scale)))
   rgb_roi=cv2.resize(rgb_roi,size,interpolation=cv2.INTER_AREA);p=cv2.resize(p.astype('uint8'),size,interpolation=cv2.INTER_NEAREST)>0;allowed=cv2.resize(allowed.astype('uint8'),size,interpolation=cv2.INTER_NEAREST)>0
 radius=max(1,round(band*scale));outer=(cv2.dilate(p.astype('uint8'),ellipse(radius))>0)&allowed
 diag={'method':'dark_line_search' if code in ('C','M') else 'prior_seeded_grabcut','search_radius_original_px':band,'processing_scale':scale,'processing_size':[p.shape[1],p.shape[0]],'flags':[]}
 try:
  if not p.any():raise ValueError('Foreground lost when downsizing')
  if code in ('C','M'):
   gray=cv2.cvtColor(rgb_roi,cv2.COLOR_RGB2GRAY);smooth=cv2.GaussianBlur(gray,(3,3),0.6)
   responses=[cv2.morphologyEx(smooth,cv2.MORPH_BLACKHAT,ellipse(r)) for r in (2,4,8)]
   response=np.maximum.reduce(responses);values=response[outer]
   threshold,_=cv2.threshold(values.reshape(-1,1),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
   diag['blackhat_threshold']=float(max(4,threshold));m=outer&(response>max(4,threshold))
   n,labels,stats,_=cv2.connectedComponentsWithStats(m.astype('uint8'),8)
   # No large closing or erosion: preserve thin branches. Remove isolated speckles only.
   keep=np.flatnonzero(stats[:,cv2.CC_STAT_AREA]>=3);keep=keep[keep!=0];m=np.isin(labels,keep)
  else:
   gc=np.full(p.shape,cv2.GC_BGD,np.uint8);gc[outer]=cv2.GC_PR_BGD;gc[p]=cv2.GC_PR_FGD
   inner=cv2.erode(p.astype('uint8'),ellipse(max(1,radius//2)))>0
   if inner.sum()<5:inner=cv2.distanceTransform(p.astype('uint8'),cv2.DIST_L2,3)>1
   if inner.sum()<5 or (~outer).sum()<5:raise ValueError('Insufficient foreground/background seeds')
   gc[inner]=cv2.GC_FGD
   cv2.setRNGSeed(PARAMS['seed'])
   cv2.grabCut(np.ascontiguousarray(rgb_roi),gc,None,np.zeros((1,65)),np.zeros((1,65)),PARAMS['grabcut_iterations'],cv2.GC_INIT_WITH_MASK)
   m=((gc==cv2.GC_FGD)|(gc==cv2.GC_PR_FGD))&outer
  if scale<1:m=cv2.resize(m.astype('uint8'),(A-a,B-b),interpolation=cv2.INTER_NEAREST)>0
  candidate=np.zeros_like(prior);candidate[b:B,a:A]=m;candidate&=limit
 except (cv2.error,ValueError) as e:
  return prior.copy(),prior.copy(),{**diag,'selection':'raw_fallback','flags':['solver_failed'],'error_type':type(e).__name__,'error_message':str(e)[:300]}
 intersection=int((candidate&prior).sum());union=int((candidate|prior).sum());ratio=float(candidate.sum()/prior.sum());iou=intersection/union if union else 1
 flags=[]
 if not candidate.any():flags.append('empty_candidate')
 if not PARAMS['min_area_ratio']<=ratio<=PARAMS['max_area_ratio']:flags.append('area_change_outlier')
 if iou<PARAMS['min_prior_iou']:flags.append('large_disagreement')
 reject=bool(flags);selected=prior.copy() if reject else candidate
 if code in ('C','M'):flags.append('review_crack_alignment_and_texture')
 if code in ('P','S'):flags.append('review_cavities_and_light_flakes')
 if code in ('D','L','R','T','V'):flags.append('review_material_shadow_and_semantics')
 diag.update(selection='raw_fallback' if reject else 'refined_candidate',flags=flags,area_ratio=ratio,prior_agreement_iou=iou)
 return selected,candidate,diag

def export_image(srcroot,out,ann):
 start=time.perf_counter();idx=ann['image_index'];src=srcroot/ann['source_path'];rgb=np.asarray(Image.open(src).convert('RGB'));h,w=rgb.shape[:2];stem=Path(ann['file_name']).stem
 if (h,w)!=(ann['height'],ann['width']):raise ValueError('Source dimensions changed')
 if sha(src)!=ann['source_sha256']:raise ValueError('Source image hash changed')
 for folder in ['images','raw_masks','raw_overlays']:
  origin=src if folder=='images' else srcroot/ann['mask_path' if folder=='raw_masks' else 'overlay_path'];dest=out/folder/(src.name if folder=='images' else stem+'.png');shutil.copy2(origin,dest)
 union=np.zeros((h,w),bool);classes={};defs=[];diagnostics=[];overlay=rgb.copy()
 for d in ann['defects']:
  t=time.perf_counter();prior=binary(srcroot/d['mask_path']);chosen,candidate,diag=refine(rgb,prior,d['bbox_xyxy'],d['class_code']);name=f'{stem}_{d["id"]}.png'
  for folder,m in [('raw_instance_masks',prior),('candidate_instance_masks',candidate),('instance_masks',chosen)]:png(out/folder/name,m)
  encoded=rle(chosen);decoded=np.repeat(np.arange(len(encoded['counts']))%2,encoded['counts']).reshape(encoded['size'],order='F')>0;assert np.array_equal(decoded,chosen)
  detail={**diag,'id':d['id'],'class_code':d['class_code'],'source_mask_sha256':sha(srcroot/d['mask_path']),'source_mask_path':d['mask_path'],'raw_area_pixels':int(prior.sum()),'candidate_area_pixels':int(candidate.sum()),'selected_area_pixels':int(chosen.sum()),'opencv_seconds':time.perf_counter()-t}
  diagnostics.append(detail);union|=chosen;classes.setdefault(d['class_code'],np.zeros_like(union));classes[d['class_code']]|=chosen
  c=COLORS[(d['id']-1)%len(COLORS)];overlay[chosen]=np.rint(rgb[chosen]*.55+np.array(c)*.45).astype('uint8')
  defs.append({**d,'method':'hybrid_api_opencv_auto','mask_path':'instance_masks/'+name,'raw_mask_path':'raw_instance_masks/'+name,'candidate_mask_path':'candidate_instance_masks/'+name,'area_pixels':int(chosen.sum()),'segmentation_rle':encoded,'quality_flags':diag['flags'],'refinement':detail})
 im=Image.fromarray(overlay);draw=ImageDraw.Draw(im)
 for d in defs:
  x,y,X,Y=d['bbox_xyxy'];c=COLORS[(d['id']-1)%len(COLORS)];draw.rectangle((x,y,X-1,Y-1),outline=c,width=max(1,w//600));draw.text((x,max(0,y-12)),f'{d["id"]} {d["class_code"]}',fill=c)
 im.save(out/'overlays'/f'{stem}.png');png(out/'masks'/f'{stem}.png',union)
 for code,m in classes.items():png(out/'class_masks'/f'{stem}_{code}.png',m)
 result={**ann,'defects':defs,'method':'hybrid_api_opencv_auto','source_path':'images/'+src.name,'source_annotation_sha256':sha(srcroot/'annotations'/f'{stem}.json'),'expert_validated':False,'refinement_parameters':PARAMS,'opencv_version':cv2.__version__,'opencv_seconds':time.perf_counter()-start,'additional_api_requests':0,'additional_tokens':0,'additional_api_cost':0,'reference_mask_used':False,'human_guides_used':False}
 save(out/'annotations'/f'{stem}.json',result)
 row={'index':idx,'file_name':ann['file_name'],'status':ann['status'],'expected_instances':ann['expected_instances'],'available_instances':len(defs),'refined_candidates':sum(d['selection']=='refined_candidate' for d in diagnostics),'raw_fallbacks':sum(d['selection']=='raw_fallback' for d in diagnostics),'opencv_seconds':result['opencv_seconds'],'additional_api_cost':0,'additional_tokens':0}
 save(out/'records'/f'{stem}.json',{'row':row,'instances':diagnostics});return row

def report(out,annotations):
 rows=[];cards=[]
 for a in annotations:
  stem=Path(a['file_name']).stem;p=out/'records'/f'{stem}.json'
  if not p.exists():continue
  rec=read(p);row=rec['row'];rows.append(row)
  panels=''.join(f'<figure><figcaption>{title}</figcaption><a href="{path}"><img loading="lazy" src="{path}"></a></figure>' for title,path in [('原图','images/'+a['file_name']),('原API','raw_overlays/'+stem+'.png'),('自动精修（异常回退原mask）','overlays/'+stem+'.png'),('精修mask','masks/'+stem+'.png')])
  notes=''.join(f'<li>ID {d["id"]}: {d["selection"]} · {html.escape(", ".join(d["flags"]))}</li>' for d in rec['instances'])
  cards.append(f'<section><h2>{a["image_index"]:02d} · {row["status"]} · {row["available_instances"]}/{row["expected_instances"]}</h2><div>{panels}</div><ul>{notes}</ul><a href="annotations/{stem}.json">JSON/RLE</a> · <a href="records/{stem}.json">精修参数与记录</a></section>')
 summary={'images_exported':len(rows),'instances_available':sum(r['available_instances'] for r in rows),'expected_instances':sum(r['expected_instances'] for r in rows),'refined_candidates':sum(r['refined_candidates'] for r in rows),'raw_fallbacks':sum(r['raw_fallbacks'] for r in rows),'opencv_seconds':sum(r['opencv_seconds'] for r in rows),'additional_api_cost':0,'additional_tokens':0,'expert_validated':False}
 save(out/'summary.json',summary)
 if rows:
  with (out/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
 (out/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>API + OpenCV 精修</title><style>body{font:15px system-ui;background:#eee;margin:20px}section{background:white;padding:12px;margin:15px 0}section div{display:flex}figure{flex:1;min-width:0;margin:5px}img{width:100%;height:430px;object-fit:contain}</style><h1>原API → 自动OpenCV精修候选</h1><p>没有重新调用模型，不读取参考标注，不包含人工轮廓。partial表示API实例缺失。精修不保证改善；prior_agreement_iou衡量改动程度，不是准确率。异常候选保存在candidate_instance_masks，最终mask可能回退为原API。语义漏检和大幅错位需要人工引导或重新分割。</p><a href="summary.json">汇总</a> · <a href="metrics.csv">耗时</a>'+''.join(cards),encoding='utf-8')
 return summary

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',default=str(ROOT/'results50_gpt_image_2_5_vscode'));p.add_argument('--output',default=str(ROOT/'outputs_refined50_v1'));p.add_argument('--indices',help='Optional comma-separated image indices');p.add_argument('--run',action='store_true',help='Execute offline refinement (no API fees)');p.add_argument('--resume',action='store_true');args=p.parse_args()
 src=Path(args.input).resolve();out=Path(args.output).resolve()
 if out==src or src in out.parents or out in src.parents:p.error('Input/output must be separate sibling directories')
 anns=sorted([read(f) for f in (src/'annotations').glob('*.json')],key=lambda a:a['image_index'])
 if args.indices:
  wanted={int(v) for v in args.indices.split(',')};anns=[a for a in anns if a['image_index'] in wanted]
  if {a['image_index'] for a in anns}!=wanted:p.error('Unknown index')
 if not anns:p.error('No input annotations; run collect_results50.py first')
 fingerprints=[]
 for a in anns:
  image=src/a['source_path']
  with Image.open(image) as im:
   if im.size!=(a['width'],a['height']):raise ValueError('Source size mismatch')
  paths=[image,src/'annotations'/(Path(a['file_name']).stem+'.json')]+[src/d['mask_path'] for d in a['defects']]
  fingerprints.extend((str(f.relative_to(src)),sha(f)) for f in paths)
 fp=hashlib.sha256(json.dumps([fingerprints,PARAMS,sha(__file__),cv2.__version__]).encode()).hexdigest()
 # Explicit compatibility with the immediately preceding version: only file I/O
 # and resume/report handling changed; segmentation and parameters are identical.
 old_code_sha='a87c07228697cd92982edad5302a0f977bef3e73d7fa3f6841e54f1a226326dd'
 compatible_fp=hashlib.sha256(json.dumps([fingerprints,PARAMS,old_code_sha,cv2.__version__]).encode()).hexdigest()
 print(f'{len(anns)} images; {sum(len(a["defects"]) for a in anns)} available / {sum(a["expected_instances"] for a in anns)} expected masks. No API calls.',flush=True)
 previous_fp=None
 if args.resume and out.exists():
  previous_fp=read(out/'experiment.json')['fingerprint']
  if previous_fp not in (fp,compatible_fp):p.error('Inputs/code changed: use a new output directory')
  print('Resume fingerprint verified; completed image records will be skipped.',flush=True)
 if not args.run:print('DRY RUN: add --run for offline refinement. Output:',out);return
 if out.exists():
  if not args.resume:p.error('Output exists: choose a new directory or --resume')
 out.mkdir(parents=True,exist_ok=True);lock=out/'.running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
 try:
  save(out/'experiment.json',{'fingerprint':fp,'previous_compatible_fingerprint':previous_fp,'parameters':PARAMS,'input':str(src),'mode':'hybrid_api_opencv_auto','additional_api_calls':0})
  for folder in ['images','raw_masks','raw_overlays','raw_instance_masks','candidate_instance_masks','instance_masks','masks','class_masks','overlays','annotations','records']:(out/folder).mkdir(exist_ok=True)
  cv2.setNumThreads(1)
  for a in anns:
   stem=Path(a['file_name']).stem
   if args.resume and (out/'records'/f'{stem}.json').exists():continue
   row=export_image(src,out,a);print(f'{row["index"]:02d}: refined={row["refined_candidates"]} fallback={row["raw_fallbacks"]} {row["opencv_seconds"]:.1f}s',flush=True)
   try:report(out,anns)
   except PermissionError as e:print(f'WARNING: report file busy; image results saved, continuing. {e.filename}',flush=True)
  try:
   print(json.dumps(report(out,anns),ensure_ascii=False));print(out/'comparison.html')
  except PermissionError as e:
   print(f'WARNING: results saved but report update failed: {e.filename}. Close applications holding report files, then rerun --run --resume to rebuild reports.',flush=True)
 finally:lock.unlink(missing_ok=True)
if __name__=='__main__':main()
