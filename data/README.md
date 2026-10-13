# 本次50张实验数据

- `input/images/`：本次实际使用的50张原图。
- `input/manifest.json`：109个固定实例的ID、bbox、类别及可选子类型，无参考mask。图像路径相对于仓库根目录。
- `reference/annotations/`：50份参考JSON，含实例类别、bbox、面积、RLE与mask路径。
- `reference/instance_masks/`、`class_masks/`、`masks/`、`overlays/`：逐实例、逐类别、整图mask与参考叠加图。
- `dataset.json`：图像尺寸、SHA256、实例数及参考版本。

参考为用户保留的 `builtin50_litter_wall_20260928_v6`，可作为本次评估的“参考真值”，但由模型生成并经用户多轮修订，未经独立专家逐像素验收。不得把参考mask作为三种待测分割方法的输入。

原图和mask保持原文件字节；JSON仅将机器绝对路径转换为相对路径。bbox为原图像素坐标 `[x1,y1,x2,y2)`。同一张图允许多个实例和类型。标注中的路径相对于 `data/reference/`，原图共用 `data/input/images/`。

历史复用字段（如 reused_from）中的本机绝对路径已改为 `historical-provenance:` 开头的版本／文件名记录，只用于溯源，不指向仓库内文件。输入原图与mask路径均可直接解析。


## 类别调整（2026-10-13）

裂缝C包含原网裂M，共23例。原L类逐图核对后拆分：37号ID1白色沉积为“白桦”B（按用户指定名称），38号ID4黄褐色流挂污痕为“渗漏”L；各1例，当前共9类、109个实例。静态照片不能确认是否正在渗水。

原图、bbox、单实例mask及RLE不变；类别mask与分类指标重新归组，总体指标不变。原始类别字段仅作溯源，不是当前标签。见 [类别映射](taxonomy.json)。

