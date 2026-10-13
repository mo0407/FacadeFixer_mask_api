# 判定与复核数据格式

路径相对于 JSON 所在目录，或使用绝对路径。`key` 是唯一实例键，仅用英文字母、数字、下划线、连字符、点；不要用图片编号代替实例 ID。bbox 为原图像素、零基 xyxy、右下端点不含。输入 mask 是已按 API 上传画布/拼图记录还原、并裁到当前 bbox 的原尺寸 0/255 mask。

```json
{
  "schema_version": 1,
  "instances": [
    {
      "key": "image01_ID2",
      "image_path": "images/image01.jpg",
      "mask_path": "api_masks/image01_2.png",
      "bbox_xyxy": [20, 30, 180, 300],
      "class_code": "C",
      "geometry_verified": true,
      "judgment": {
        "state": "translation_confirmed",
        "confidence": "high",
        "reviewer": "实际判定模型名或人工",
        "evidence": [
          "上端弯折形状相同，mask在可见裂缝右侧",
          "下端分支也在可见裂缝右侧，偏移方向和距离近似一致"
        ],
        "estimated_shift_xy": [-4, 0]
      }
    }
  ]
}
```

允许状态：`aligned`、`translation_confirmed`、`nontranslation_error`、`uncertain`、`geometry_invalid`。置信度：`high`、`medium`、`low`。`estimated_shift_xy` 可为 null，单位是原图像素；不要从缩放预览图直接照抄屏幕像素。观察证据由判定者填写，不伪造固定文案。确认整体位移至少写两个相隔位置的证据；未确认时写原因。`geometry_verified` 是程序对坐标恢复和像素校验的实际结论，模型看图不能替代这项检查。

初始 `inputs.json` 使用上面的字段，但省略 `judgment`。`inspect` 会写入默认待复核的 `judgment`、`input_image_sha256`、`input_mask_sha256` 并生成 `inspection/decisions.json`；模型只填写判断，不修改哈希。`propose` 验证当前输入与模型看到的文件一致；输入变化时必须重新检查。

第二次查看算法候选后，只为实际移动的实例提交复核：

```json
{
  "schema_version": 1,
  "instances": [
    {
      "key": "image01_ID2",
      "verdict": "accept",
      "reviewer": "实际复核模型名或人工",
      "evidence": ["上下两个弯折均贴合原图裂缝，分支没有转移到相邻墙缝"]
    }
  ]
}
```

`verdict` 为 `accept`、`reject` 或 `uncertain`；后两种沿用原稿。算法未采用位移的实例不需要后复核条目。每份记录保存原图/原稿/候选哈希、前判定、是否调用复位、dx/dy、算法理由、耗时和后复核。工具不接收参考标注路径。

实际复核文件还必须原样带上该实例在 `proposals/records.json` 中的 `candidate_mask_sha256` 与 `input_image_sha256`，将复核绑定到具体候选和原图；旧实验的复核不能直接复用。上面的短例子省略了长哈希。
