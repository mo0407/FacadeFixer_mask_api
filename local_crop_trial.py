"""BBox-local API trial. Deterministic tile mapping, no OpenCV/ref-mask input."""
import argparse,io,json,time,math
from pathlib import Path
import numpy as np
from PIL import Image
import run as core
ROOT=Path(__file__).resolve().parent
def prepare_local(original,d):
 w,h=original.size;x,y,X,Y=d['bbox_xyxy'];px=max(12,round((X-x)*.2));py=max(12,round((Y-y)*.025))
 roi=[max(0,x-px),max(0,y-py),min(w,X+px),min(h,Y+py)];a,b,A,B=roi;rw,rh=A-a,B-b
 n=4 if max(rw/rh,rh/rw)>3 else 1;cell=512 if n==4 else 1024
 canvas=Image.new('RGB',(1024,1024),(255,0,255));tiles=[]
 for k in range(n):
  box=[a,b+round(k*rh/n),A,b+round((k+1)*rh/n)] if rh>=rw else [a+round(k*rw/n),b,a+round((k+1)*rw/n),B]
  crop=original.crop(box);s=min((cell-16)/crop.width,(cell-16)/crop.height);sw=max(1,round(crop.width*s));sh=max(1,round(crop.height*s));cx=(k%2)*cell if n==4 else 0;cy=(k//2)*cell if n==4 else 0;ox=cx+(cell-sw)//2;oy=cy+(cell-sh)//2
  canvas.paste(crop.resize((sw,sh),Image.Resampling.LANCZOS),(ox,oy));sx=sw/crop.width;sy=sh/crop.height
  target=[max(x,box[0]),max(y,box[1]),min(X,box[2]),min(Y,box[3])]
  mapped=[(target[0]-box[0])*sx+ox,(target[1]-box[1])*sy+oy,(target[2]-box[0])*sx+ox,(target[3]-box[1])*sy+oy]
  tiles.append({'tile':k+1,'source_xyxy':box,'canvas_xyxy':[ox,oy,ox+sw,oy+sh],'scale_xy':[sx,sy],'target_bbox_canvas':mapped})
 prompt=('Return only a black/white binary mask of this EXACT 1024x1024 input canvas. White=specified visible defect, black=background. '+f'This canvas contains {n} separate photo panels in reading order. Process each panel IN PLACE independently; do not combine, move, resize, extend or reconnect panels. All magenta padding MUST be black. Target class: '+d['class_code']+' '+core.DEFS[d['class_code']]+'. Target region coordinates on this submitted canvas: '+json.dumps([t['target_bbox_canvas'] for t in tiles])+'. Follow actual visible defect boundaries; never fill rectangles. Keep faint tail only where visibly discolored. Do not select intact light wall, shadows or padding. No labels, margins, illustrations or text.')
 return canvas,{'roi_xyxy':roi,'original_size':[w,h],'input_size':[1024,1024],'tiles':tiles,'prompt':prompt,'method':'bbox_local_tiled_api_no_refinement'}
def restore(blob,meta):
 im=Image.open(io.BytesIO(blob)).convert('RGBA');size=im.size
 if abs(im.width/im.height-1)>.02:raise ValueError('model_canvas_aspect_mismatch')
 bg=Image.new('RGBA',size,'black');bg.alpha_composite(im);mask=bg.convert('L').point(lambda v:255 if v>=128 else 0).resize((1024,1024),Image.Resampling.NEAREST)
 full=Image.new('L',tuple(meta['original_size']),0)
 for t in meta['tiles']:
  x,y,X,Y=t['source_xyxy'];part=mask.crop(tuple(t['canvas_xyxy'])).resize((X-x,Y-y),Image.Resampling.NEAREST);full.paste(part,(x,y))
 return np.asarray(full)>0,size
def main():
 p=argparse.ArgumentParser();p.add_argument('--index',type=int,default=0);p.add_argument('--run',action='store_true');p.add_argument('--output',default='outputs_local_crop01');args=p.parse_args()
 item=next(i for i in core.read(ROOT/'input_manifest.json')['images'] if i['index']==args.index)
 if len(item['defects'])!=1:raise ValueError('Trial expects one instance; general batch adaptation is separate')
 d=item['defects'][0];src=Path(item['image_path']);original=Image.open(src).convert('RGB');canvas,meta=prepare_local(original,d)
 out=ROOT/args.output/'gpt_image_2_5_default';out.mkdir(parents=True,exist_ok=True);name=f'{src.stem}_{d["id"]}'
 recordpath=out/'records'/f'{name}.json'
 if recordpath.exists():raise ValueError('Trial already submitted; inspect record, no automatic paid retry')
 canvas.save(out/'submitted.png');core.save(out/'geometry.json',meta)
 if not args.run:print('Prepared local input without API request');return
 m=next(m for m in core.read(ROOT/'models.json')['models'] if m['enabled']);png=io.BytesIO();canvas.save(png,format='PNG')
 rec={'index':item['index'],'id':d['id'],'status':'submitted','estimated_cost':None,'usage':None,'source_sha256':core.sha(src),'method':meta['method'],'group_requested':m.get('group_requested'),'group_verified':False};core.save(recordpath,rec);start=time.perf_counter()
 try:
  asset,usage,rid=core.api.call_api(m,core.key(m),png.getvalue(),meta['prompt']);rec.update(api_seconds=time.perf_counter()-start,usage=usage,request_id=rid,estimated_cost=core.api.cost(usage,m.get('pricing')),**core.api.usage_fields(usage));core.save(recordpath,rec)
  blob=core.api.asset_bytes(asset,m.get('proxy'));(out/'raw_response.bin').write_bytes(blob);mask,size=restore(blob,meta);Image.open(io.BytesIO(blob)).save(out/'raw_mask.png')
  Image.fromarray(mask.astype('uint8')*255).save(out/'unclipped.png');x,y,X,Y=d['bbox_xyxy'];final=np.zeros_like(mask);final[y:Y,x:X]=mask[y:Y,x:X]
  (out/'instance_masks').mkdir(exist_ok=True);dest=out/'instance_masks'/f'{name}.png';Image.fromarray(final.astype('uint8')*255).save(dest)
  rec.update(status='success',returned_size=list(size),mask_path=dest.relative_to(out).as_posix(),mask_sha256=core.sha(dest),outside_bbox_pixels=int(mask.sum()-final.sum()),empty=not bool(final.any()))
 except Exception as e:rec.update(status='failed_or_unconfirmed',error_type=type(e).__name__,http_status=getattr(e,'status',None))
 finally:rec['total_seconds']=time.perf_counter()-start;core.save(recordpath,rec)
 a=core.export(out,item,{d['id']:rec});a['segmentation_method']=meta['method'];a['geometry_path']='geometry.json'
 for row in a['defects']:row['method']=meta['method']
 core.save(out/'annotations'/f'{src.stem}.json',a)
 print(json.dumps({k:rec.get(k) for k in ['status','returned_size','api_seconds','estimated_cost','error_type']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
