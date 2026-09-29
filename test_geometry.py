"""Offline geometry checks; no network, no credentials, no paid request."""
import io,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
import api_adapter as a
def main():
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)
  for w,h in [(171,2077),(2077,171),(511,431)]:
   src=p/'original.png';Image.new('RGB',(w,h),'white').save(src)
   original,submitted,meta=a.prepare(src,None,1024)
   assert Image.open(io.BytesIO(submitted)).width==Image.open(io.BytesIO(submitted)).height
   x,y,X,Y=meta['crop'];assert (X-x,Y-y)==(w,h)
   buf=io.BytesIO();Image.new('L',(1024,1024),255).save(buf,format='PNG')
   a.write_images(original,buf.getvalue(),meta,p/'mask.png',p/'overlay.png')
   assert Image.open(p/'mask.png').size==(w,h)
   assert np.all(np.asarray(Image.open(p/'mask.png'))==255)
   bad=io.BytesIO();Image.new('L',(881,1786),255).save(bad,format='PNG')
   try:a.write_images(original,bad.getvalue(),meta,p/'bad.png',p/'bad_overlay.png')
   except ValueError as e:assert str(e)=='model_canvas_aspect_mismatch'
   else:raise AssertionError('Mismatched aspect must remain rejected')
 print('PASS: portrait/landscape dimensions, crop mapping, binary output, aspect mismatch rejection')
if __name__=='__main__':main()
