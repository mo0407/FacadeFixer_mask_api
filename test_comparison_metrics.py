import numpy as np
from compare_three_methods import scores,aggregate
a=np.zeros((30,30),bool);a[5:15,5:15]=True
b=np.zeros_like(a);b[5:15,10:20]=True
s=scores(a,a);assert s['iou']==s['dice']==s['boundary_f1']==1
s=scores(b,a);assert (s['tp'],s['fp'],s['fn'])==(50,50,50);assert abs(s['iou']-1/3)<1e-9 and s['dice']==.5
s=scores(np.zeros_like(a),a);assert s['iou']==s['dice']==s['boundary_f1']==s['recall']==0
c=np.zeros_like(a);c[6:16,5:15]=True;assert scores(c,a)['boundary_f1']==1
assert aggregate([scores(a,a),scores(np.zeros_like(a),a)])['macro_iou']==.5
print('PASS: exact/disjoint/partial overlaps, empty prediction, boundary tolerance, macro averaging.')
