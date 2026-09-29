"""Regression tests for transient Windows replace failures."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import refine_api_masks as r

with tempfile.TemporaryDirectory() as directory:
 p=Path(directory)/'summary.json';r.save(p,{'old':True});replace=r.os.replace;calls=[]
 def busy_then_ready(src,dst):
  calls.append(1)
  if len(calls)<3:raise PermissionError(5,'File busy',str(dst))
  replace(src,dst)
 with patch.object(r.os,'replace',side_effect=busy_then_ready),patch.object(r.time,'sleep'):
  r.save(p,{'new':True})
 assert r.read(p)=={'new':True} and len(calls)==3
 with patch.object(r.os,'replace',side_effect=PermissionError(5,'Still busy')),patch.object(r.time,'sleep'):
  try:r.save(p,{'must_not_replace':True})
  except PermissionError:pass
  else:raise AssertionError('Permanent failure must not be hidden')
 assert r.read(p)=={'new':True} and not list(Path(directory).glob('*.tmp'))
print('PASS: transient lock retry; persistent lock preserves previous JSON; temporary cleanup.')
