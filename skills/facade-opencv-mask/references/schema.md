# 输入输出规范

分割输入示例：

```json
{"schema":"bbox_class_only_v1","images":[{"index":0,"image_path":"D:/dataset/001.jpg","defects":[{"id":1,"class_code":"C","class_name":"Linearcrack","bbox_xyxy":[10,20,180,390]}]}]}
```

可选 class_subtype 为 GroundLitter 或 WallStain。保留输入 id，不强行连续编号。支持 C、M、D、L、T、R、V、P、S；遇到未知类型报错，不悄悄改类。单张可以有多个框和多个类型，散落物语义组不是逐物体实例分割。

输出目录：`annotations/`、`masks/`、`instance_masks/`、`class_masks/`、`overlays/`、`bbox_overlays/`、`previews/`、`metrics.csv`、`run.json`。RLE 是未压缩 Fortran 列优先游程：size=[H,W]，counts 从背景长度开始；不同于 COCO 压缩字符串。

annotations 包含 source_sha256、bbox坐标、类型、实例面积、RLE、method、parameters、roi_scale、quality_flags、时间及零 API 成本；不是其他工具完整 schema 的无损替代。如需原系统额外字段，应明确映射，不能继承旧 mask 的面积或旧专家验收状态。

评估用 reference manifest 为数组：`[{"index":0,"annotation":"D:/reference/annotations/001.json"}]`。各参考 JSON 需包含 defects 的 id、bbox_xyxy、class_code、mask_path，以及总 mask_path、overlay_path；相对文件路径以其 annotations 的父目录为根。参考必须同一图、同一bbox/id映射，脚本会验证。

计时：每图包含读取、分割及 mask/叠加/bbox 写盘；不包含 JSON 序列化、预览制作与后续评估。run.wall_seconds 另记录批处理总时间。参考为候选时 IoU/Dice 只是空间一致度，空-空计为 null 而非满分。
