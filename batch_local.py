"""Local-crop API batch with frozen targets, resume, two-worker limit and HTML review."""
import argparse,io,time,json,os,shutil,csv,threading,html
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from PIL import Image
import run as core
import local_crop_trial as local
ROOT=Path(__file__).resolve().parent
REUSE={0:'outputs_local_crop02',4:'outputs_local_crop_i04'}
def make_input(it,d):
 original=Image.open(it['image_path']).convert('RGB');canvas,meta=local.prepare_local(original,d)
 # Unlike generic D, these semantic subtypes must not be conflated.
 subtype=d.get('class_subtype')
 extra={'GroundLitter':'Select ground litter: discarded cloth, bags, masks, hangers and loose rubbish; exclude ground stains and wall dirt.','WallStain':'Select wall staining only; exclude ground litter, shadows and intact wall.'}.get(subtype,'')
 meta['prompt']=meta['prompt'].replace('Keep faint tail only where visibly discolored. ', 'Keep faint tail only where visibly discolored. ' if d['class_code'] in ['R','T','L'] else '')
 meta['prompt']+=' Target ID: '+str(d['id'])+'. '+extra
 return original,canvas,meta
def validate(root,it,d,r):
 src=Path(it['image_path']);assert r['source_sha256']==core.sha(src)
 if r['status']!='success':return
 p=root/r['mask_path'];assert core.sha(p)==r['mask_sha256'];im=Image.open(p);assert im.mode=='L' and im.size==Image.open(src).size
 a=np.asarray(im);assert np.isin(a,[0,255]).all();x,y,X,Y=d['bbox_xyxy'];assert (a>0).sum()==(a[y:Y,x:X]>0).sum()
def process(root,it,d,model,secret,retry,stop):
 src=Path(it['image_path']);name=f'{src.stem}_{d["id"]}';rp=root/'records'/f'{name}.json';prior=core.read(rp) if rp.exists() else None
 if prior:
  validate(root,it,d,prior)
  if prior['status']=='success' or not retry:
   print(f"{it['index']:02d}/{d['id']} retained {prior['status']}",flush=True);return prior
 if stop.is_set():return None
 if prior is None and it['index'] in REUSE:
  oldroot=ROOT/REUSE[it['index']]/model['id'];oldrp=oldroot/'records'/f'{name}.json'
  if oldrp.exists():
   r=core.read(oldrp)
   if r['status']=='success':
    validate(oldroot,it,d,r);oldann=core.read(oldroot/'annotations'/f'{src.stem}.json');od=next(x for x in oldann['defects'] if x['id']==d['id']);assert od['bbox_xyxy']==d['bbox_xyxy'] and od['class_code']==d['class_code']
    shutil.copy2(oldroot/r['mask_path'],root/'instance_masks'/f'{name}.png')
    for old,newfolder,ext in [('geometry.json','geometry','.json'),('submitted.png','submitted_images','.png'),('raw_response.bin','raw_model_outputs','.bin'),('raw_mask.png','raw_masks','.png'),('unclipped.png','unclipped_masks','.png')]:shutil.copy2(oldroot/old,root/newfolder/f'{name}{ext}')
    r.update(provenance='carried_forward',carried_from=str(oldroot),attempts=[],current_run_requests=0);core.save(rp,r);print(f"{it['index']:02d}/{d['id']} reused accepted trial",flush=True);return r
 original,canvas,meta=make_input(it,d);canvas.save(root/'submitted_images'/f'{name}.png');core.save(root/'geometry'/f'{name}.json',meta);buf=io.BytesIO();canvas.save(buf,format='PNG')
 attempts=list(prior.get('attempts',[])) if prior else []
 r={'index':it['index'],'id':d['id'],'model':model['model'],'source_sha256':core.sha(src),'status':'submitted','provenance':'regenerated','method':meta['method'],'group_requested':model.get('group_requested'),'group_verified':False,'estimated_cost':None,'actual_charge':None,'currency':'CNY','usage':None,'api_seconds':None,'attempts':attempts,'current_run_requests':len(attempts)+1}
 core.save(rp,r);start=time.perf_counter();print(f"{it['index']:02d}/{d['id']} submitting ({d.get('class_subtype',d['class_code'])})",flush=True)
 try:
  asset,usage,rid=core.api.call_api(model,secret,buf.getvalue(),meta['prompt']);r.update(api_seconds=time.perf_counter()-start,usage=usage,request_id=rid,estimated_cost=core.api.cost(usage,model.get('pricing')),**core.api.usage_fields(usage));core.save(rp,r)
  blob=core.api.asset_bytes(asset,model.get('proxy'));(root/'raw_model_outputs'/f'{name}.bin').write_bytes(blob)
  with Image.open(io.BytesIO(blob)) as im:r['returned_size']=list(im.size);im.save(root/'raw_masks'/f'{name}.png')
  m,size=local.restore(blob,meta);Image.fromarray(m.astype('uint8')*255).save(root/'unclipped_masks'/f'{name}.png');x,y,X,Y=d['bbox_xyxy'];final=np.zeros_like(m);final[y:Y,x:X]=m[y:Y,x:X]
  dest=root/'instance_masks'/f'{name}.png';Image.fromarray(final.astype('uint8')*255).save(dest);r.update(status='success',mask_path=dest.relative_to(root).as_posix(),mask_sha256=core.sha(dest),outside_bbox_pixels=int(m.sum()-final.sum()),empty=not bool(final.any()))
 except Exception as e:
  r.update(status='failed_or_unconfirmed',error_type=type(e).__name__,http_status=getattr(e,'status',None))
  if str(e)=='model_canvas_aspect_mismatch':r['error_code']=str(e)
  if getattr(e,'status',None) in [401,403]:stop.set()
 finally:
  r['total_seconds']=time.perf_counter()-start;r['attempts']=attempts+[{k:r.get(k) for k in ['status','api_seconds','total_seconds','estimated_cost','usage','total_tokens','http_status','error_type','error_code']}];core.save(rp,r)
 print(f"{it['index']:02d}/{d['id']} {r['status']} {r['total_seconds']:.1f}s HTTP={r.get('http_status')}",flush=True)
 return r
def report(root,items):
 def link(p):return Path(os.path.relpath(p,root)).as_posix()
 cards=[];image_rows=[];instances=[]
 for it in items:
  src=Path(it['image_path']);recs={}
  for d in it['defects']:
   rp=root/'records'/f'{src.stem}_{d["id"]}.json'
   if rp.exists():r=core.read(rp);validate(root,it,d,r);recs[d['id']]=r;instances.append(r)
  a=core.export(root,it,recs);a['segmentation_method']='bbox_local_tiled_api_no_refinement'
  for d in a['defects']:
   d['method']=a['segmentation_method'];d['provenance']=recs[d['id']]['provenance'];rr=d['segmentation_rle'];decoded=np.repeat(np.arange(len(rr['counts']))%2,rr['counts']).reshape(rr['size'],order='F')>0;assert np.array_equal(decoded,np.asarray(Image.open(root/d['mask_path']))>0)
  core.save(root/'annotations'/f'{src.stem}.json',a)
  knowncost=[r.get('estimated_cost') for r in recs.values()];image_rows.append({'index':it['index'],'file_name':src.name,'status':a['status'],'expected_instances':len(it['defects']),'successful_instances':len(a['defects']),'api_seconds_sum':sum(r.get('api_seconds') or 0 for r in recs.values()),'estimated_known_cost':sum(c for c in knowncost if c is not None),'cost_complete':len(knowncost)==len(it['defects']) and all(c is not None for c in knowncost),'total_tokens':sum(r['total_tokens'] for r in recs.values()) if len(recs)==len(it['defects']) and all(r.get('total_tokens') is not None for r in recs.values()) else None})
  panels=[('原图',src),('API局部裁剪：按实例着色',root/a['overlay_path']),('总mask',root/a['mask_path'])]
  if it['index']==4 and (ROOT/'outputs_hybrid_i04_v1'/'overlay.png').exists():panels.append(('此前04专用精修（额外视觉辅助）',ROOT/'outputs_hybrid_i04_v1'/'overlay.png'))
  figures=''.join(f'<figure><figcaption>{label}</figcaption><a href="{link(p)}"><img loading="lazy" src="{link(p)}"></a></figure>' for label,p in panels)
  details=[]
  for d in it['defects']:
   r=recs.get(d['id'],{});name=f'{src.stem}_{d["id"]}';status=r.get('status','not_submitted');links=''
   for label,folder,ext in [('输入','submitted_images','.png'),('原始返回','raw_masks','.png'),('mask','instance_masks','.png'),('映射','geometry','.json'),('记录','records','.json')]:
    p=root/folder/f'{name}{ext}'
    if p.exists():links+=f' <a href="{link(p)}">{label}</a>'
   details.append(f'<li>ID {d["id"]} {d.get("class_subtype",d["class_code"])} · {status} · {r.get("provenance", "")} · {r.get("error_code",r.get("error_type",""))}{links}</li>')
  cards.append(f'<section id="i{it["index"]:02d}"><h2>{it["index"]:02d} · {html.escape(src.name)} · {a["status"]}</h2><div class="row">{figures}</div><ul>{"".join(details)}</ul></section>')
 successful=sum(r['status']=='success' for r in instances);reused=sum(r.get('provenance')=='carried_forward' for r in instances);attempts=[a for r in instances for a in r.get('attempts',[])]
 summary={'images':len(items),'expected_instances':sum(len(i['defects']) for i in items),'successful_instances':successful,'reused_instances':reused,'new_request_attempts':len(attempts),'new_successful_instances':sum(r['status']=='success' and r.get('provenance')=='regenerated' for r in instances),'failed_or_pending_instances':sum(len(i['defects']) for i in items)-successful,'new_known_cost_estimate_cny':sum(a['estimated_cost'] for a in attempts if a.get('estimated_cost') is not None),'attempts_with_unknown_cost':sum(a.get('estimated_cost') is None for a in attempts),'actual_charge':None,'empty_successful_instances':sum(r.get('empty',False) for r in instances)}
 core.save(root/'summary.json',summary)
 with (root/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(image_rows[0]));w.writeheader();w.writerows(image_rows)
 page=f'''<!doctype html><meta charset="utf-8"><title>局部API范围测试</title><style>body{{font:15px system-ui;background:#eee;margin:24px}}section{{background:white;margin:20px 0;padding:16px}}.row{{display:flex;gap:12px}}figure{{margin:0;flex:1;min-width:0}}img{{width:100%;height:550px;object-fit:contain;background:#f6f6f6}}h2{{font-size:18px}}a{{margin-right:8px}}</style><h1>{items[0]['index']:02d}–{items[-1]['index']:02d}：局部裁剪 API，{summary['expected_instances']}个冻结bbox</h1><p>成功 {successful}/{summary['expected_instances']}；沿用先前00、04结果 {reused} 个；本批新增请求 {len(attempts)} 次。新请求已知费用估算¥{summary['new_known_cost_estimate_cny']:.2f}，另有{summary['attempts_with_unknown_cost']}次费用未知，非实扣账单。</p><p>原图+bbox+类型/子类型；局部裁剪，狭长区域四段拼图，按坐标还原；不做OpenCV修边、不读取参考mask。04精修仅作单独对照，含额外视觉轮廓。复用结果不是本轮新盲测。partial表示实例未齐，不代表空白处无缺陷。点图片查看原尺寸。</p><p><a href="metrics.csv">单张指标</a><a href="summary.json">汇总</a></p>'''+''.join(cards)
 (root/'review.html').write_text(page,encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--review-only',action='store_true');p.add_argument('--retry-failed',action='store_true');p.add_argument('--workers',type=int,default=1,choices=[1,2]);p.add_argument('--output');p.add_argument('--start',type=int,default=10);p.add_argument('--end',type=int,default=49);args=p.parse_args()
 manifest=core.read(ROOT/'input_manifest.json')['images'];indices={i['index'] for i in manifest}
 if args.start>args.end or not set(range(args.start,args.end+1))<=indices:p.error('start/end must select an existing inclusive index range')
 if args.run and args.review_only:p.error('--run and --review-only are mutually exclusive')
 if args.retry_failed and not args.run:p.error('--retry-failed requires --run')
 items=[i for i in manifest if args.start<=i['index']<=args.end];models=[m for m in core.read(ROOT/'models.json')['models'] if m.get('enabled')];assert len(models)==1;model=models[0]
 output=args.output or ('outputs_local_remaining40_v1' if (args.start,args.end)==(10,49) else f'outputs_local_{args.start:02d}_{args.end:02d}_v2');root=ROOT/output/model['id']
 for it in items:
  with Image.open(it['image_path']) as im:
   for d in it['defects']:
    x,y,X,Y=d['bbox_xyxy'];assert 0<=x<X<=im.width and 0<=y<Y<=im.height,'Invalid bbox'
 targets=sum(len(i['defects']) for i in items)
 print(f'{args.start:02d}-{args.end:02d}: {len(items)} images, {targets} targets; one request per uncached target. Output: {root}',flush=True)
 if args.review_only:report(root,items);return
 if not args.run:print('DRY RUN: no requests');return
 root.mkdir(parents=True,exist_ok=True);lock=root/'.running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
 try:
  for folder in ['records','geometry','submitted_images','raw_model_outputs','raw_masks','instance_masks','unclipped_masks']:(root/folder).mkdir(exist_ok=True)
  fp=core.api.digest(core.api.canonical([items,{k:v for k,v in model.items() if k not in ['key_file','api_key_env']},core.sha(__file__),core.sha(ROOT/'local_crop_trial.py'),core.sha(ROOT/'api_adapter.py')]))
  cfg=root/'experiment.json'
  if cfg.exists():assert core.read(cfg)['fingerprint']==fp,'Changed experiment: use a new output directory'
  core.save(cfg,{'fingerprint':fp,'mode':'bbox_local_api_no_refinement','model':model['model'],'workers':args.workers,'reuse_candidates':REUSE})
  secret=core.key(model);stop=threading.Event()
  with ThreadPoolExecutor(max_workers=args.workers) as pool:
   futures=[pool.submit(process,root,i,d,model,secret,args.retry_failed,stop) for i in items for d in i['defects']]
   for future in as_completed(futures):future.result()
  report(root,items)
 finally:lock.unlink()
if __name__=='__main__':main()
