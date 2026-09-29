"""Post-run agreement with a candidate reference; never used by segment.py."""
import argparse,json,csv,os,html
from pathlib import Path
from collections import defaultdict
import numpy as np
from PIL import Image,ImageDraw
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def mask(p):return np.asarray(Image.open(p).convert('L'))>0
def rle_decode(r):return np.repeat(np.arange(len(r['counts']))%2,r['counts']).reshape(r['size'],order='F')>0
def counts(p,t):return [int((p&t).sum()),int((p&~t).sum()),int((~p&t).sum())]
def score(c):
 tp,fp,fn=c;return {'iou':tp/(tp+fp+fn) if tp+fp+fn else None,'dice':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None}
def main():
 pa=argparse.ArgumentParser();pa.add_argument('--reference-manifest',required=True);pa.add_argument('--results',required=True);args=pa.parse_args();root=Path(args.results).resolve();refs=read(args.reference_manifest);rows=[];images=[];parts=[];class_sums=defaultdict(lambda:np.zeros(3,np.int64));classes=defaultdict(list);micro=np.zeros(3,np.int64)
 (root/'comparison_previews').mkdir(exist_ok=True)
 def link(p):return os.path.relpath(p,root).replace('\\','/')
 for refitem in refs:
  ap=Path(refitem['annotation']);refbase=ap.parent.parent;t=read(ap);sid=ap.stem;pred=read(root/'annotations'/ap.name);i=refitem['index'];p=mask(root/pred['mask_path']);truth=mask(refbase/t['mask_path']);assert p.shape==truth.shape==(pred['height'],pred['width'])
  byid={d['id']:d for d in t['defects']};union=np.zeros_like(p);details=[];class_p={};class_t={}
  for d in pred['defects']:
   td=byid[d['id']];assert d['bbox_xyxy']==td['bbox_xyxy'] and d['class_code']==td['class_code']
   pm=mask(root/d['mask_path']);tm=mask(refbase/td['mask_path']);assert np.array_equal(pm,rle_decode(d['segmentation_rle']))
   x1,y1,x2,y2=d['bbox_xyxy'];outside=pm.copy();outside[y1:y2,x1:x2]=False;assert not outside.any();union|=pm
   c=counts(pm,tm);s=score(c);key=d['class_code']+('/'+d['class_subtype'] if d.get('class_subtype') else '')
   r={'index':i,'id':d['id'],'class':key,'method':d['method'],'pred_pixels':int(pm.sum()),'reference_pixels':int(tm.sum()),**s,'flags':' | '.join(d['quality_flags'])};rows.append(r);classes[key].append(r)
   class_p.setdefault(key,np.zeros_like(p));class_p[key]|=pm;class_t.setdefault(key,np.zeros_like(p));class_t[key]|=tm
   details.append(f'<tr><td>{d["id"]}</td><td>{key}</td><td>{d["method"]}</td><td>{s["iou"]:.3f}</td><td>{int(pm.sum())}</td><td>{html.escape(r["flags"])}</td><td><a href="{d["mask_path"]}">mask</a></td></tr>' if s['iou'] is not None else f'<tr><td>{d["id"]}</td><td>{key}</td><td>双方为空</td></tr>')
  assert np.array_equal(union,p);c=counts(p,truth);micro+=c;s=score(c);images.append({'index':i,'file_name':pred['file_name'],'seconds':pred['seconds'],**s,'empty_instances':sum(d['area_pixels']==0 for d in pred['defects'])})
  for key in class_p:class_sums[key]+=counts(class_p[key],class_t[key])
  original=Image.open(pred['source_path']).convert('RGB');ims=[original,Image.open(refbase/t['overlay_path']),Image.open(root/pred['overlay_path']),Image.open(root/pred['mask_path']).convert('RGB')]
  scale=min(360/original.width,620/original.height,1);sw,sh=max(1,round(original.width*scale)),max(1,round(original.height*scale));sheet=Image.new('RGB',(sw*4,sh+28),'white');dr=ImageDraw.Draw(sheet)
  for k,(im,title) in enumerate(zip(ims,['Original','Candidate reference','OpenCV overlay','OpenCV mask'])):sheet.paste(im.resize((sw,sh)),(k*sw,28));dr.text((k*sw+3,7),title,fill='black')
  sheet.save(root/'comparison_previews'/f'{i:02d}.jpg',quality=93)
  parts.append(f'<section id="i{i:02d}"><h2>{i:02d} · {html.escape(pred["file_name"])} · IoU {s["iou"]:.3f}</h2><p>本地耗时 {pred["seconds"]:.3f} 秒；空实例 {images[-1]["empty_instances"]}</p><p><a href="annotations/{ap.name}">OpenCV JSON</a> · <a href="{pred["mask_path"]}">mask</a> · <a href="{pred["overlay_path"]}">叠加图</a> · <a href="bbox_overlays/{sid}.png">bbox</a> · <a href="{link(ap)}">参考 JSON</a> · <a href="{link(refbase/t["overlay_path"])}">参考叠加图</a></p><img loading="lazy" src="comparison_previews/{i:02d}.jpg"><table><tr><th>id</th><th>类别</th><th>方法</th><th>IoU</th><th>像素数</th><th>复核提示</th><th>输出</th></tr>{"".join(details)}</table></section>')
 run=read(root/'run.json');summary={'reference_kind':'unverified_model_candidate_not_ground_truth','image_count':len(images),'instance_count':len(rows),'mean_image_iou':float(np.mean([x['iou'] for x in images if x['iou'] is not None])),'mean_instance_iou':float(np.mean([x['iou'] for x in rows if x['iou'] is not None])),'union_micro':score(micro.tolist()),'empty_instances':sum(x['pred_pixels']==0 for x in rows),'mean_seconds':float(np.mean([x['seconds'] for x in images])),'p95_seconds':float(np.percentile([x['seconds'] for x in images],95)),'classes':{k:{'instances':len(v),'mean_instance_iou':float(np.mean([x['iou'] for x in v if x['iou'] is not None])),**score(class_sums[k].tolist())} for k,v in classes.items()},'invariants_passed':['original_dimensions','frozen_bboxes_and_classes','RLE_matches_instance_PNG','no_pixels_outside_bbox','instance_union_matches_total_mask'],'run':run}
 save(root/'agreement_summary.json',summary)
 for name,rs in [('agreement_instances.csv',rows),('agreement_images.csv',images)]:
  with (root/name).open('w',encoding='utf-8-sig',newline='') as f:wr=csv.DictWriter(f,fieldnames=list(rs[0]));wr.writeheader();wr.writerows(rs)
 table=''.join(f'<tr><td>{k}</td><td>{v["instances"]}</td><td>{v["mean_instance_iou"]:.3f}</td><td>{v["iou"]:.3f}</td></tr>' for k,v in sorted(summary['classes'].items()))
 page=f'<!doctype html><meta charset="utf-8"><title>OpenCV 50张对比</title><style>body{{font:15px sans-serif;background:#eee;margin:20px}}section{{background:white;padding:16px;margin:20px 0}}img{{max-width:100%}}td,th{{border:1px solid #ddd;padding:6px}}table{{border-collapse:collapse}}</style><h1>OpenCV：50张、109个 bbox 分割</h1><p>输入仅原图、bbox、类别/子类别；未使用参考mask引导生成。类别规则共享，无逐图坐标修补。API费用与token均为0（不含本地计算成本）。</p><p>参考为此前模型候选标注，包含部分OpenCV修正，未经独立人工真值验收。下列为一致度，不是准确率；两种方法可能同时出错。</p><p>平均每图 {summary["mean_seconds"]:.3f} 秒；实例平均IoU {summary["mean_instance_iou"]:.3f}；空实例 {summary["empty_instances"]}。</p><p><a href="agreement_summary.json">统计JSON</a> · <a href="agreement_instances.csv">逐实例CSV</a> · <a href="metrics.csv">耗时CSV</a></p><table><tr><th>类别</th><th>实例</th><th>实例平均IoU</th><th>类别像素合并IoU</th></tr>{table}</table><p>'+ ' · '.join(f'<a href="#i{i:02d}">{i:02d}</a>' for i in range(len(images)))+'</p>'+''.join(parts)
 (root/'review.html').write_text(page,encoding='utf-8');print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':main()
