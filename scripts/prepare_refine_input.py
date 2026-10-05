"""Copy API outputs plus original images into a portable refinement input."""
import argparse,json,shutil,hashlib
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args();src=Path(a.input).resolve();out=Path(a.output).resolve()
 if out.exists() or src==out or src in out.parents or out in src.parents:p.error('Choose a new separate output directory')
 annotations=list((src/'annotations').glob('*.json'))
 if not annotations:p.error('No annotations')
 out.mkdir();(out/'images').mkdir()
 for folder in ['annotations','masks','instance_masks','class_masks','overlays','records','geometry','submitted_images','raw_masks','raw_model_outputs','unclipped_masks']:
  if (src/folder).exists():shutil.copytree(src/folder,out/folder)
 for f in annotations:
  ann=json.loads(f.read_text(encoding='utf-8'));image=Path(ann['source_path']);image=image if image.is_absolute() else src/image
  assert hashlib.sha256(image.read_bytes()).hexdigest()==ann['source_sha256']
  shutil.copy2(image,out/'images'/ann['file_name']);ann['source_path']='images/'+ann['file_name'];(out/'annotations'/f.name).write_text(json.dumps(ann,ensure_ascii=False,indent=2),encoding='utf-8')
 print(f'Prepared {len(annotations)} images. No API calls. {out}')
if __name__=='__main__':main()
