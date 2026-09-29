# 三种方法与参考标注的量化对比

参考：用户保留的 builtin50_litter_wall_20260928_v6 候选标注。它经过模型生成和反馈修订，非独立专家真值。所有数值是与该参考的一致度。

|方法|可用实例|宏IoU|宏Dice|精确率|召回率|边界F1（2px）|共同105宏IoU|
|---|---:|---:|---:|---:|---:|---:|---:|
|OpenCV|109/109|0.3908|0.5001|0.4523|0.7020|0.3983|0.3795|
|image2.5|105/109|0.4056|0.5079|0.5408|0.5166|0.4863|0.4210|
|image2.5+OpenCV|105/109|0.4283|0.5283|0.5669|0.5377|0.4411|0.4446|

按实例等权平均；全部109中缺失按0分。共同105剔除API失败的四项，用于比较同一可用子集。另提供像素微平均，避免将宏/微混用。

精修相对API：61项IoU上升、31项下降、13项不变。区域重叠提高，但边界F1降低。93项采用候选不等于93项质量改善。

本地comparison.html包含原图+参考+三方法叠加，所有图片和输出使用相对链接，可将整个comparison50_three_methods_v1目录发给别人；GitHub只上传程序和统计，不上传图片。

## 文件

- reference/：参考标注及mask。
- opencv/：纯bbox+类型OpenCV基线，无逐图人工引导。
- image25/：API局部裁剪版（00、04历史复用）。
- hybrid/：API+自动OpenCV，含原始实例、候选、最终mask及回退记录。
- instances.csv：327行，109实例×3方法；按id/类别/bbox核对。
- images.csv：逐图总mask指标（不区分类别，不作为主要结论）。
- classes.csv：按缺陷类型宏均值。
- refinement_changes.csv：按精修ΔIoU升序排列，负值为退化。
- summary.json：全样本/共同子集、宏/微汇总。
- provenance.json：输入标注SHA256，原始图像SHA256在标注中。

缺失实例：25/ID2、27/ID1、30/ID1、39/ID1。新增OpenCV API费用/token均0，精修计算时间约59秒（不含复核、报表及此次评估）。两批API已知估算¥5.15、49次请求费用未知，不含两个复用实例原始请求及更早弃用试验。

## 重算评估

```powershell
python compare_three_methods.py --reference REFERENCE_DIR --opencv OPENCV_DIR --image25 API_DIR --hybrid REFINED_DIR --output NEW_COMPARISON_DIR
python test_comparison_metrics.py
```
