"""Collect both batches without making API requests or changing original outputs."""
import csv,json,shutil,html
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 out=ROOT/'results50_gpt_image_2_5_vscode';out.mkdir(exist_ok=True)
 items=json.loads((ROOT/'input_manifest.json').read_text(encoding='utf-8-sig'))['images']
 cards=[];rows=[];failures=[];attempts=[];reused=[]
 for it in items:
  batch='outputs_local_first10_v1' if it['index']<10 else 'outputs_local_remaining40_v1'
  srcroot=ROOT/batch/'gpt_image_2_5_default';src=Path(it['image_path']);stem=src.stem
  for folder in ['images','annotations','masks','overlays','instance_masks','class_masks','records','geometry','submitted_images','raw_masks','raw_model_outputs','unclipped_masks']:(out/folder).mkdir(exist_ok=True)
  shutil.copy2(src,out/'images'/src.name)
  for folder in ['annotations','masks','overlays','instance_masks','class_masks','records','geometry','submitted_images','raw_masks','raw_model_outputs','unclipped_masks']:
   for f in (srcroot/folder).glob(stem+'*'):
    if f.is_file():shutil.copy2(f,out/folder/f.name)
  ann=json.loads((out/'annotations'/f'{stem}.json').read_text(encoding='utf-8'));ann['source_path']='images/'+src.name;ann['source_batch']=batch
  (out/'annotations'/f'{stem}.json').write_text(json.dumps(ann,ensure_ascii=False,indent=2),encoding='utf-8')
  recs=[json.loads((out/'records'/f'{stem}_{d["id"]}.json').read_text(encoding='utf-8')) for d in it['defects']]
  for d,r in zip(it['defects'],recs):
   attempts.extend(r.get('attempts',[]))
   if r.get('provenance')=='carried_forward':reused.append({'index':it['index'],'id':d['id'],'estimated_cost':r.get('estimated_cost')})
   if r['status']!='success':failures.append({'index':it['index'],'id':d['id'],'http_status':r.get('http_status'),'error_type':r.get('error_type')})
  row={'index':it['index'],'file':src.name,'batch':batch,'status':ann['status'],'expected':len(it['defects']),'successful':len(ann['defects']),'latest_instance_seconds_sum':sum(r.get('total_seconds') or 0 for r in recs),'batch_attempt_seconds_sum':sum(a.get('total_seconds') or 0 for r in recs for a in r.get('attempts',[])),'latest_total_tokens':sum(r['total_tokens'] for r in recs) if all(r.get('total_tokens') is not None for r in recs) else None,'batch_known_cost_estimate':sum(a.get('estimated_cost') or 0 for r in recs for a in r.get('attempts',[])),'batch_unknown_cost_attempts':sum(a.get('estimated_cost') is None for r in recs for a in r.get('attempts',[]))};rows.append(row)
  panels=''.join(f'<figure><figcaption>{label}</figcaption><a href="{path}"><img loading="lazy" src="{path}"></a></figure>' for label,path in [('原图','images/'+src.name),('API叠加','overlays/'+stem+'.png'),('Mask','masks/'+stem+'.png')])
  cards.append(f'<section id="i{it["index"]:02d}"><h2>{it["index"]:02d} · {html.escape(src.name)} · {ann["status"]} {len(ann["defects"])}/{len(it["defects"])}</h2><div>{panels}</div><a href="annotations/{stem}.json">JSON / RLE</a></section>')
 summary={'images':len(items),'complete_images':sum(r['status']=='success' for r in rows),'expected_instances':sum(r['expected'] for r in rows),'successful_instances':sum(r['successful'] for r in rows),'failures':failures,'batch_request_attempts':len(attempts),'batch_known_cost_estimate_cny':round(sum(a.get('estimated_cost') or 0 for a in attempts),2),'batch_unknown_cost_attempts':sum(a.get('estimated_cost') is None for a in attempts),'reused_prior_instances':reused,'actual_charge':None,'expert_validated':False,'method':'bbox_local_tiled_api_no_refinement','note':'Batch costs exclude original requests for the two reused instances and earlier discarded trials. Partial masks are incomplete. No hybrid refinement is included.'}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 with (out/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 (out/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>50张 GPT-image-2.5 / VS Code</title><style>body{font:16px system-ui;background:#eee;margin:24px}section{background:white;padding:15px;margin:16px 0}section div{display:flex}figure{flex:1;min-width:0;margin:6px}img{width:100%;height:480px;object-fit:contain}</style><h1>50张 GPT-image-2.5 / VS Code 汇总</h1><p>成功 '+str(summary['successful_instances'])+'/'+str(summary['expected_instances'])+' 个实例；完整 '+str(summary['complete_images'])+'/50 张。partial为空缺结果，不代表无缺陷。00、04沿用历史API试验；不含04额外视觉精修。生成mask仍可能偏移，未经专家验收，不能直接作为真值。</p><a href="summary.json">汇总与失败清单</a> · <a href="metrics.csv">耗时、token、费用</a>'+''.join(cards),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False));print(out/'review.html')
if __name__=='__main__':main()
