"""Offline, ID-aligned evaluation against a versioned candidate reference."""
import argparse,csv,hashlib,html,json,shutil
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parent
NAMES={'opencv':'OpenCV','image25':'image2.5','hybrid':'image2.5 + OpenCV'}
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mask(p,shape):
 with Image.open(p) as im:a=np.array(im)
 assert a.shape==shape and np.isin(a,[0,255]).all(),str(p)
 return a>0
def scores(pred,ref,tolerance=2):
 tp=int((pred&ref).sum());fp=int((pred&~ref).sum());fn=int((~pred&ref).sum())
 if tp+fp+fn==0:return dict(tp=0,fp=0,fn=0,iou=1.,dice=1.,precision=1.,recall=1.,boundary_f1=1.)
 precision=tp/(tp+fp) if tp+fp else 0.;recall=tp/(tp+fn) if tp+fn else 0.
 bf=0.
 if pred.any() and ref.any():
  # Crop only for distance-transform efficiency, preserving original pixel scale.
  ys,xs=np.where(pred|ref);x=max(0,xs.min()-3);X=min(pred.shape[1],xs.max()+4);y=max(0,ys.min()-3);Y=min(pred.shape[0],ys.max()+4)
  edges=[]
  for a in (pred[y:Y,x:X],ref[y:Y,x:X]):edges.append(a&~(cv2.erode(a.astype('uint8'),np.ones((3,3),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0)>0))
  e,f=edges;df=cv2.distanceTransform((~f).astype('uint8'),cv2.DIST_L2,cv2.DIST_MASK_PRECISE);de=cv2.distanceTransform((~e).astype('uint8'),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
  bp=float((df[e]<=tolerance).mean());br=float((de[f]<=tolerance).mean());bf=2*bp*br/(bp+br) if bp+br else 0.
 return dict(tp=tp,fp=fp,fn=fn,iou=tp/(tp+fp+fn),dice=2*tp/(2*tp+fp+fn),precision=precision,recall=recall,boundary_f1=bf)
def aggregate(rows):
 if not rows:return {'instances':0}
 t=sum(r['tp'] for r in rows);f=sum(r['fp'] for r in rows);n=sum(r['fn'] for r in rows)
 return {'instances':len(rows),**{f'macro_{k}':float(np.mean([r[k] for r in rows])) for k in ('iou','dice','precision','recall','boundary_f1')},'micro_iou':t/(t+f+n) if t+f+n else 1.,'micro_dice':2*t/(2*t+f+n) if 2*t+f+n else 1.}
def csvout(p,rows):
 if rows:
  with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument('--reference',default=str(ROOT.parent/'builtin50_litter_wall_20260928_v6'));p.add_argument('--opencv',default=str(ROOT.parent/'opencv50_bbox_20260928/results'));p.add_argument('--image25',default=str(ROOT/'results50_gpt_image_2_5_vscode'));p.add_argument('--hybrid',default=str(ROOT/'outputs_refined50_v1'));p.add_argument('--output',default=str(ROOT/'comparison50_three_methods_v1'));args=p.parse_args()
 roots={k:Path(getattr(args,k)).resolve() for k in ['reference',*NAMES]};out=Path(args.output).resolve()
 if out.exists():p.error('Use a new output directory; preserve earlier comparisons')
 if any(out==v or out in v.parents or v in out.parents for v in roots.values()):p.error('Output must be separate from inputs')
 cv2.setNumThreads(1);out.mkdir();(out/'images').mkdir();anns={k:{a['file_name']:a for f in (v/'annotations').glob('*.json') for a in [read(f)]} for k,v in roots.items()}
 assert all(set(anns[k])==set(anns['reference']) for k in NAMES),'Image sets differ'
 for key,root in roots.items():
  dest=out/key;dest.mkdir()
  for folder in ['annotations','masks','instance_masks','class_masks','overlays','records']:
   if (root/folder).exists():shutil.copytree(root/folder,dest/folder)
  for name in ['metrics.csv','summary.json','experiment.json','audit.json']:
   if (root/name).exists():shutil.copy2(root/name,dest/name)
  if key=='hybrid':
   for folder in ['raw_instance_masks','candidate_instance_masks']:shutil.copytree(root/folder,dest/folder)
 rows=[];image_rows=[];provenance=[];cards=[]
 for name,refa in sorted(anns['reference'].items(),key=lambda item:item[1]['image_index']):
  idx=refa['image_index'];shape=(refa['height'],refa['width']);source=roots['reference']/'images'/name;assert sha(source)==refa['source_sha256'];shutil.copy2(source,out/'images'/name)
  maps={k:{d['id']:d for d in a[name]['defects']} for k,a in anns.items()};refmap=maps['reference'];common=set(refmap).intersection(*(set(maps[k]) for k in NAMES))
  unions={k:np.zeros(shape,bool) for k in roots}
  for key in roots:
   a=anns[key][name];assert (a['height'],a['width'])==shape and a['source_sha256']==refa['source_sha256'];assert set(maps[key])<=set(refmap)
   portable=read(out/key/'annotations'/(Path(name).stem+'.json'));portable['source_path']='../images/'+name
   write(out/key/'annotations'/(Path(name).stem+'.json'),portable)
   provenance.append({'index':idx,'method':key,'annotation_sha256':sha(roots[key]/'annotations'/(Path(name).stem+'.json'))})
  for ident,d in refmap.items():
   truth=mask(roots['reference']/d['mask_path'],shape);unions['reference']|=truth
   for key in NAMES:
    other=maps[key].get(ident);missing=other is None
    if other:
     assert other['bbox_xyxy']==d['bbox_xyxy'] and other['class_code']==d['class_code'],(idx,key,ident)
     pred=mask(roots[key]/other['mask_path'],shape)
    else:pred=np.zeros(shape,bool)
    unions[key]|=pred;metric=scores(pred,truth)
    # Missing results receive zero on all instance-level metrics, even if reference is empty.
    if missing:
     for k in ['iou','dice','precision','recall','boundary_f1']:metric[k]=0.
    rows.append({'index':idx,'file_name':name,'id':ident,'class_code':d['class_code'],'method':key,'missing':missing,'common_available':ident in common,**metric})
  for key in roots:assert np.array_equal(unions[key],mask(roots[key]/anns[key][name]['mask_path'],shape)),(idx,key,'union mismatch')
  for key in NAMES:image_rows.append({'index':idx,'method':key,'missing_instances':len(refmap)-len(maps[key]),**scores(unions[key],unions['reference'])})
  panels='<figure><figcaption>原图</figcaption><img loading="lazy" src="images/'+html.escape(name)+'"></figure>'
  for key,label in [('reference','参考真值（候选）'),*NAMES.items()]:
   path=key+'/'+anns[key][name]['overlay_path'];detail=''
   if key!='reference':
    group=[r for r in rows if r['index']==idx and r['method']==key];m=aggregate(group);detail=f'<p>实例均值 IoU {m["macro_iou"]:.3f} · Dice {m["macro_dice"]:.3f}<br>BF1 {m["macro_boundary_f1"]:.3f} · 缺失 {sum(r["missing"] for r in group)}</p>'
   panels+=f'<figure><figcaption>{label}</figcaption><a href="{path}"><img loading="lazy" src="{path}"></a>{detail}</figure>'
  delta=aggregate([r for r in rows if r['index']==idx and r['method']=='hybrid'])['macro_iou']-aggregate([r for r in rows if r['index']==idx and r['method']=='image25'])['macro_iou']
  cards.append(f'<section id="i{idx:02d}"><h2>{idx:02d} · {html.escape(name)} · 精修 ΔIoU {delta:+.3f}</h2><div class="panels">{panels}</div></section>')
  print(f'Evaluated {idx:02d}',flush=True)
 summary={'reference':'User-retained builtin50_litter_wall_20260928_v6 candidate labels, model-generated and revised with user feedback; not independent expert ground truth','boundary_tolerance_original_pixels':2,'missing_policy':'Missing instances are zero masks; macro instance scores set to zero','methods':{k:{'available':sum(not r['missing'] for r in rows if r['method']==k),'all_instances':aggregate([r for r in rows if r['method']==k]),'common_available_instances':aggregate([r for r in rows if r['method']==k and r['common_available']])} for k in NAMES}}
 deltas=[]
 for raw in [r for r in rows if r['method']=='image25' and r['common_available']]:
  new=next(r for r in rows if r['method']=='hybrid' and r['index']==raw['index'] and r['id']==raw['id']);deltas.append({'index':raw['index'],'id':raw['id'],'class_code':raw['class_code'],'api_iou':raw['iou'],'hybrid_iou':new['iou'],'delta_iou':new['iou']-raw['iou'],'delta_boundary_f1':new['boundary_f1']-raw['boundary_f1']})
 summary['hybrid_change']={'improved_iou':sum(r['delta_iou']>1e-9 for r in deltas),'worse_iou':sum(r['delta_iou']< -1e-9 for r in deltas),'unchanged_iou':sum(abs(r['delta_iou'])<=1e-9 for r in deltas)}
 classes=[{'method':k,'class_code':c,**aggregate([r for r in rows if r['method']==k and r['class_code']==c])} for k in NAMES for c in sorted({r['class_code'] for r in rows})]
 write(out/'summary.json',summary);write(out/'provenance.json',provenance);csvout(out/'instances.csv',rows);csvout(out/'images.csv',image_rows);csvout(out/'classes.csv',classes);csvout(out/'refinement_changes.csv',sorted(deltas,key=lambda r:r['delta_iou']))
 table='<table><tr><th>方法</th><th>可用/109</th><th>IoU均值</th><th>Dice均值</th><th>精确率</th><th>召回率</th><th>边界F1</th><th>共同105 IoU</th></tr>'
 for k,label in NAMES.items():
  entry=summary['methods'][k];a=entry['all_instances'];table+=f'<tr><td>{label}</td><td>{entry["available"]}/109</td>'+''.join(f'<td>{a["macro_"+m]:.4f}</td>' for m in ['iou','dice','precision','recall','boundary_f1'])+f'<td>{entry["common_available_instances"]["macro_iou"]:.4f}</td></tr>'
 table+='</table>'
 chart=''.join(f'<p>{label} <meter min="0" max="1" value="{summary["methods"][k]["all_instances"]["macro_iou"]}"></meter> {summary["methods"][k]["all_instances"]["macro_iou"]:.3f}</p>' for k,label in NAMES.items())
 doc='''<!doctype html><meta charset="utf-8"><title>三种方法与参考真值对比</title><style>body{font:15px system-ui;background:#eee;margin:24px}section{background:white;padding:12px;margin:18px 0}.panels{display:flex}figure{flex:1;min-width:0;margin:5px}img{width:100%;height:380px;object-fit:contain}table{border-collapse:collapse;background:white}td,th{border:1px solid #ccc;padding:10px}meter{width:300px;height:24px}h2{font-size:17px}</style><h1>OpenCV / image2.5 / image2.5+OpenCV 与参考标注</h1><p>参考为用户保留的v6候选标注，并非独立专家真值；以下指标是与该参考的一致度。全部109实例中，API与混合方法缺失4个，缺失按0分计。共同105列用于排除请求失败影响。固定bbox/类型/id匹配，未用参考mask调整分割。</p><p>IoU=交集/并集；Dice=2交集/两者面积和；精确率衡量误选，召回率衡量漏选；边界F1使用原图2像素容差。均值按实例等权，越高越贴合参考；不会用大量背景像素抬高准确率。</p>'''+table+chart+'<p><a href="instances.csv">逐实例</a> · <a href="images.csv">逐图总mask</a> · <a href="classes.csv">按类别</a> · <a href="refinement_changes.csv">精修增减排序</a> · <a href="summary.json">完整汇总（含微平均）</a></p>'+''.join(cards)
 (out/'comparison.html').write_text(doc,encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
