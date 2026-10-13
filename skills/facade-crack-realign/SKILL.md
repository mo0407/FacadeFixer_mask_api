---
name: facade-crack-realign
description: 建筑裂缝或网裂的API mask出现位置偏移时，先用原图与叠加图判断是否整体平移，仅对确认偏移的实例调用OpenCV复位，并复核候选、保留原稿和判定记录。
---

# 裂缝 mask 判断与复位

这是可选的模型结果后处理：输入为原图、冻结 bbox、C（裂缝）或 M（网裂）类型、API mask。先完成裁剪、拼图、缩放的确定性坐标还原，mask 必须是原图尺寸的 0/255 图。不要用参考标注或 IoU 决定是否复位。

## 先判断，再调用

查看原图和原稿叠加图，必要时放大 bbox 内的局部，判断**同一实例**：

| 判断 | 依据 | 动作 |
|---|---|---|
| `aligned` | mask 已沿着可见裂缝，未见明确整体偏移 | 跳过复位，沿用原稿 |
| `translation_confirmed` | 形状、分支或弯折基本相符；至少两个相隔位置表现出近似同方向、同距离偏移，且可区分相邻墙缝 | 高置信度时调用复位 |
| `nontranslation_error` | 线宽、形状、分支、漏检或目标选择错误；各部分偏移方向不同 | 跳过，标记需要其他精修 |
| `uncertain` | 原图模糊、纹理干扰或多个相邻暗线，无法确定目标/位移 | 跳过，标记复核 |
| `geometry_invalid` | 裁剪或拼图映射未验证，尺寸/比例异常 | 先修复坐标映射，不用平移掩盖错误 |

“看起来有偏移”要写成观察证据，例如原图上的弯折点、端点或分支与 mask 相差方向。不要从低 IoU、低暗线分数或模型自己返回的信心值直接推断整体偏移。高置信度表示目标与位移都清楚，不是经过校准的概率。

先按 [判定数据格式](references/decision-schema.md) 准备仅含实例输入的 `inputs.json`，生成原图局部、原稿叠加与判定模板：

```powershell
python scripts/postprocess.py inspect --inputs inputs.json --output inspection
```

查看 `inspection/review.html` 后填写 `inspection/decisions.json`，保留工具生成的输入哈希。逐实例判定；一张图其他 bbox 不能因其中一个偏移而一并处理。工具只对 `translation_confirmed`、`high` 且坐标映射已验证的 C/M 实例调用算法。

```powershell
python scripts/postprocess.py propose --decisions inspection/decisions.json --output proposals
```

## 复位与复核

复位器只读原图、当前 bbox 和原稿 mask，搜索整体平移。它结合整条暗线响应、八段一致性和两种打分候选的一致性，也保留旧版的保守采用规则；图像证据不足则回退。模型估计的位移只作记录，不直接强制搬动像素。算法选中一个平移不表示目标语义已经正确。

查看 `proposals/review.html` 的原稿与候选叠加图。对于算法实际移动的实例，检查多个局部是否更贴合原图；不能只看某一个点，不能牺牲其他分支，也不能从“更暗”推断“更正确”。若复位后换到了墙缝/管线、其他部分变差或无法确认，填写 `reject` 或 `uncertain`；仅清楚改善时填写 `accept`。

按数据格式输出 `verifications.json`，再导出最终版本：

```powershell
python scripts/postprocess.py finalize --proposals proposals --verifications verifications.json --output final
```

最终复位必须同时满足模型前判定、算法采用、模型后复核。`reject`/`uncertain` 均保留原稿。一次自动复位和一次复核后仍不明确的实例交后续处理，不反复平移。最终叠加图只展示选用的 mask；原稿、候选和理由在记录中保留。

输出 mask 与原图同尺寸，像素在冻结 bbox 内；导回 API 批处理时重算实例面积、RLE、哈希、类别/总 mask 和叠加图。用 [API 接入说明](references/api-integration.md) 区分技能判断与普通图像 API，并记录后处理时间和判定模型用量。OpenCV 复位不调用 API，视觉判断若额外调用模型则需单独计费。
