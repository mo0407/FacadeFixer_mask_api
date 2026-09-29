"""Frozen bbox/class image-edit benchmark; dry-run default, explicit --run for API calls."""
import argparse,os,json,time,io,csv,re,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import api_adapter as api
ROOT=Path(__file__).resolve().parent
COLORS=[(255,60,60),(0,190,255),(255,190,0),(180,60,255),(0,220,110),(255,80,190)]
DEFS={'C':'visible linear crack at actual width; exclude joints and shadows','M':'visible network of fine cracks; keep individual thin branches','P':'peeling coating/plaster including light curled flakes','S':'material loss including exposed grey mortar, brick, aggregate, rebar and cavities','T':'rust stain on the surface','R':'visible corrosion/rust','D':'surface contaminants; distinguish ground litter from wall stains using supplied subtype','V':'visible plant including fine leaves','L':'visible leakage deposit including white mineral efflorescence where present'}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):api.save(p,x)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rle(m):
 a=m.ravel(order='F').astype(np.uint8);idx=np.r_[0,np.flatnonzero(a[1:]!=a[:-1])+1,len(a)];counts=np.diff(idx).tolist()
 if a[0]:counts.insert(0,0)
 return {'size':list(m.shape),'order':'F','counts':counts}
def key(m):
 k=os.getenv(m.get('api_key_env',''))
 if not k and m.get('key_file'):
  p=Path(m['key_file']);p=p if p.is_absolute() else ROOT/p
  k=p.read_text(encoding='utf-8-sig').strip()
 if not k or '\n' in k:raise ValueError('Set api_key_env or a key_file containing only one token')
 return k
def prepare(src,d,max_side):
 original,png,meta=api.prepare(src,None,max_side)
 w,h=original.size;sw,sh=meta['input_size'];cw,ch=meta['canvas_size'];ox,oy,_,_=meta['crop']
 target={k:d[k] for k in ['id','class_code','class_name','class_subtype','bbox_xyxy'] if k in d}
 meta['prompt']=(f'Return ONLY one binary segmentation mask. White is the specified defect instance; black is all other pixels. Preserve full image geometry; no crop, recenter, zoom, labels, boxes or redraw. Original image {w}x{h}. Submitted canvas {sw}x{sh}. Original point maps as x_input=(x+{ox})*{sw/cw}, y_input=(y+{oy})*{sh/ch}. Magenta padding is background. Target in original pixel coordinates: '+json.dumps(target,ensure_ascii=False)+'. Definition: '+DEFS[d['class_code']]+'. Segment ONLY this target inside the supplied zero-based xyxy bbox (right/bottom exclusive). Do not segment other instances or fill the box. Preserve irregular boundaries, thin cracks and holes. If no visible target, return black.')
 return original,png,meta
def export(root,item,records):
 src=Path(item['image_path']);rgb=np.asarray(Image.open(src).convert('RGB'));h,w=rgb.shape[:2];over=rgb.copy();union=np.zeros((h,w),bool);classes={};defs=[]
 for d in item['defects']:
  rec=records.get(d['id'])
  if not rec or rec['status']!='success':continue
  m=np.asarray(Image.open(root/rec['mask_path']))>0;union|=m;c=COLORS[(d['id']-1)%len(COLORS)];over[m]=np.rint(rgb[m]*.55+np.array(c)*.45).astype(np.uint8)
  classes.setdefault(d['class_code'],np.zeros((h,w),bool));classes[d['class_code']]|=m
  defs.append({**d,'mask_path':rec['mask_path'],'area_pixels':int(m.sum()),'segmentation_rle':rle(m),'overlay_color_rgb':c,'method':'api_per_instance_bbox','quality_flags':['generated_mask_may_shift','clipped_to_frozen_bbox'],'seconds':rec['total_seconds']})
 im=Image.fromarray(over);dr=ImageDraw.Draw(im)
 for d in defs:
  x,y,X,Y=d['bbox_xyxy'];c=tuple(d['overlay_color_rgb']);dr.rectangle((x,y,X-1,Y-1),outline=c,width=max(1,w//600));dr.text((x,max(0,y-12)),f"{d['id']} {d['class_code']}",fill=c)
 for folder in ['masks','overlays','annotations','class_masks']:(root/folder).mkdir(exist_ok=True)
 Image.fromarray(union.astype('uint8')*255).save(root/'masks'/f'{src.stem}.png');im.save(root/'overlays'/f'{src.stem}.png')
 for c,m in classes.items():Image.fromarray(m.astype('uint8')*255).save(root/'class_masks'/f'{src.stem}_{c}.png')
 status='success' if len(defs)==len(item['defects']) else 'partial'
 known=list(records.values());fees=[r.get('estimated_cost') for r in known]
 a={'image_index':item['index'],'file_name':src.name,'source_path':str(src),'source_sha256':sha(src),'width':w,'height':h,'defects':defs,'expected_instances':len(item['defects']),'status':status,'mask_path':f'masks/{src.stem}.png','overlay_path':f'overlays/{src.stem}.png','seconds':sum(r.get('total_seconds',0) for r in known),'api_seconds':sum(r.get('api_seconds') or 0 for r in known),'estimated_cost':sum(fees) if status=='success' and all(v is not None for v in fees) else None,'actual_charge':None,'token_usage':{k:sum(r[k] for r in known) if status=='success' and all(r.get(k) is not None for r in known) else None for k in ['input_tokens','output_tokens','total_tokens']},'bbox_convention':'zero_based_xyxy_max_exclusive','expert_validated':False}
 save(root/'annotations'/f'{src.stem}.json',a)
 return a
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default=str(ROOT/'models.json'));p.add_argument('--manifest',default=str(ROOT/'input_manifest.json'));p.add_argument('--output',default=str(ROOT/'outputs'));p.add_argument('--run',action='store_true');p.add_argument('--indices',help='Comma-separated zero-based image indices');args=p.parse_args()
 data=read(args.manifest);items=data['images'];models=[m for m in read(args.config)['models'] if m.get('enabled',True)]
 if args.indices:items=[i for i in items if i['index'] in {int(x) for x in args.indices.split(',')}]
 if not items or not models:raise ValueError('No selected images/models')
 out=Path(args.output).resolve()
 for it in items:
  src=Path(it['image_path']).resolve();w,h=Image.open(src).size
  if out==src.parent or out.is_relative_to(src.parent):raise ValueError('Output must be separate from source images')
  assert len({d['id'] for d in it['defects']})==len(it['defects'])
  for d in it['defects']:
   x,y,X,Y=d['bbox_xyxy'];assert all(isinstance(v,int) for v in [x,y,X,Y]) and 0<=x<X<=w and 0<=y<Y<=h and d['class_code'] in DEFS
 assert len({m['id'] for m in models})==len(models)
 for m in models:
  assert re.fullmatch(r'[A-Za-z0-9_-]+',m['id']);assert not m.get('api_key') and not m.get('headers'),'Use env/key_file; custom auth headers not supported'
  assert m.get('transport','multipart') in ['multipart','json','dashscope']
 print(f'{len(items)} images, {sum(len(i["defects"]) for i in items)} requests/model, {len(models)} models; no detection and no contour refinement',flush=True)
 if not args.run:print('DRY RUN: no requests. Endpoint/model/credentials not remotely validated.');return
 if any('YOUR_' in str(m) for m in models):raise ValueError('Fill models.json before --run')
 keys={m['id']:key(m) for m in models};out.mkdir(parents=True,exist_ok=True);lock=out/'.running.lock'
 fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
 try:
  for m in models:
   root=out/m['id'];root.mkdir(exist_ok=True)
   for f in ['records','raw_model_outputs','instance_masks','unclipped_masks','scratch','submitted_images']:(root/f).mkdir(exist_ok=True)
   fingerprint=api.digest(api.canonical([data,{k:v for k,v in m.items() if k not in ['key_file','api_key_env']},sha(__file__),sha(ROOT/'api_adapter.py')]))
   rp=root/'experiment.json'
   if rp.exists() and read(rp)['fingerprint']!=fingerprint:raise ValueError('Config/input changed: use a new --output directory')
   save(rp,{'fingerprint':fingerprint,'model':m['model'],'group_requested':m.get('group_requested'),'group_verified':False,'input_manifest_sha256':sha(args.manifest),'mode':'per_instance_full_frame','postprocess':'threshold, inverse canvas transform, bbox clipping only','pricing':m.get('pricing')})
   last=0;stop=False;image_rows=[]
   for it in items:
    recs={};src=Path(it['image_path'])
    for d in it['defects']:
     name=f'{src.stem}_{d["id"]}';path=root/'records'/f'{name}.json'
     if path.exists():
      rec=read(path);assert rec['source_sha256']==sha(src),'Source changed; use new experiment'
      if rec['status']=='success':
       assert sha(root/rec['mask_path'])==rec['mask_sha256'],'Output damaged; recover without a new paid request'
      recs[d['id']]=rec;print(f'{m["id"]} {it["index"]:02d}/{d["id"]}: retained {rec["status"]}',flush=True);continue
     original,png,meta=prepare(src,d,m.get('max_canvas_side',4096));start=time.perf_counter()
     (root/'submitted_images'/f'{name}.png').write_bytes(png)
     rec={'index':it['index'],'id':d['id'],'model':m['model'],'group_requested':m.get('group_requested'),'group_verified':False,'source_sha256':sha(src),'status':'submitted','usage':None,'estimated_cost':None,'currency':(m.get('pricing') or {}).get('currency'),'actual_charge':None,'total_seconds':0,'api_seconds':None,'prompt':meta['prompt'],'input_size':meta['input_size'],'canvas_size':meta['canvas_size'],'crop':meta['crop']}
     save(path,rec);print(f'{m["id"]} {it["index"]:02d}/{d["id"]}: submitting',flush=True)
     try:
      wait=max(0,m.get('min_interval_seconds',0)-(time.perf_counter()-last));time.sleep(wait);last=time.perf_counter()
      asset,usage,rid=api.call_api(m,keys[m['id']],png,meta['prompt']);rec.update(api_seconds=time.perf_counter()-last,usage=usage,request_id=rid,estimated_cost=api.cost(usage,m.get('pricing')),**api.usage_fields(usage));save(path,rec)
      blob=api.asset_bytes(asset,m.get('proxy'));(root/'raw_model_outputs'/f'{name}.bin').write_bytes(blob)
      with Image.open(io.BytesIO(blob)) as returned:
       rec['returned_size']=list(returned.size)
       rec['aspect_error']=abs((returned.width/returned.height)/(meta['input_size'][0]/meta['input_size'][1])-1)
      save(path,rec)
      raw=root/'unclipped_masks'/f'{name}.png';api.write_images(original,blob,meta,raw,root/'scratch'/f'{name}.png')
      mask=np.asarray(Image.open(raw))>0;x,y,X,Y=d['bbox_xyxy'];clipped=np.zeros_like(mask);clipped[y:Y,x:X]=mask[y:Y,x:X]
      dest=root/'instance_masks'/f'{name}.png';Image.fromarray(clipped.astype('uint8')*255).save(dest)
      rec.update(status='success',mask_path=dest.relative_to(root).as_posix(),mask_sha256=sha(dest),outside_bbox_pixels=int(mask.sum()-clipped.sum()),empty=not bool(clipped.any()))
     except Exception as e:
      rec.update(status='failed_or_unconfirmed',error_type=type(e).__name__,http_status=getattr(e,'status',None))
      if isinstance(e,ValueError) and str(e)=='model_canvas_aspect_mismatch':rec['error_code']='model_canvas_aspect_mismatch'
      if isinstance(e,api.APIError) and e.status in [401,403]:stop=True
     finally:
      rec['total_seconds']=time.perf_counter()-start;save(path,rec)
      print(f"{m['id']} {it['index']:02d}/{d['id']}: {rec['status']} | {rec['total_seconds']:.1f}s | HTTP={rec.get('http_status')} | error={rec.get('error_code',rec.get('error_type'))}",flush=True)
      print(f'Record: {path}',flush=True)
     recs[d['id']]=rec
     if stop:break
    a=export(root,it,recs);image_rows.append({k:a[k] for k in ['image_index','file_name','status','seconds','api_seconds','estimated_cost'] }|a['token_usage'])
    with (root/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
     writer=csv.DictWriter(f,fieldnames=list(image_rows[0]));writer.writeheader();writer.writerows(image_rows)
    if stop:break
 finally:lock.unlink()
if __name__=='__main__':main()
