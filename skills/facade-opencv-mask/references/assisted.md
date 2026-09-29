# 视觉辅助分割：坐标、求解与溯源

此模式接收比bbox更精细的先验，由助手观察原图或用户交互提供。不要从参考mask反向提轮廓然后声称独立自动预测。算法在原图局部像素上求解，不调用图像生成模型重画场景。

## 输入示例

```json
{
  "mode":"assisted",
  "images":[{
    "index":0,
    "image_path":"D:/dataset/wall.jpg",
    "defects":[{
      "id":1,
      "class_code":"C",
      "bbox_xyxy":[30,20,200,360],
      "guide_source":"assistant_visual_original",
      "guide_edit_seconds":null,
      "operations":[{
        "kind":"path",
        "points":[[80,30],[100,130],[95,250],[130,350]],
        "parameters":{"search_radius":8,"max_half_width":8,"response_min":6}
      }],
      "exclude_polygons":[]
    }]
  }]
}
```

所有点是原图xy像素，不是展示缩略图坐标。缩略图上读点时必须用独立W/H比例还原，记录变换。`guide_source` 描述真实来源，例如 assistant_visual_original、user_clicks 或 model_contour（后者要另归 hybrid，不能使用 assisted 冒充原图盲判）。guide_edit_seconds 未测量记null。每个operation要有独立points，分支分开求解后合并。

## 路径

按约1原像素弧长重采样引导线，利用切向量构造法线；灰度小尺度平滑与更大尺度平滑的差值作为暗响应。动态规划同时考虑响应、与引导的距离、相邻法向偏移连续性，从而减少逐点最暗值的跳动。路径不是骨架输出：在每个优化中心向两侧根据绝对响应和相对响应阈值增长，得到可变宽度。没有暗响应的采样点不画前景，真实断裂不强行连通。

默认搜索半径/最大半宽均8原像素只是起点。调整要依据原图线宽、引导误差与纹理；过大的搜索带会吸向邻近缝隙。输出 optimized_path_xy、width_pixels 和 unsupported_samples 供复核；这些是求解轨迹，不是真值边界。

## 轮廓与 GrabCut

operation 为 `{"kind":"polygon_grabcut","points":[...],"band_px":5,"iterations":5}`。在bbox原分辨率局部裁剪中，腐蚀轮廓作为确定前景，膨胀外侧作为确定背景，中间为可能前/背景；排除区始终为背景。局部结果回填原图，最后限制到bbox。

闭合轮廓需要包围预期目标，不能只沿黑色区域画框而漏掉浅色翘皮或灰色基材。空洞内部是否包括在破损中应遵守标注定义；真实非缺陷孔洞用exclude_polygons保留。过细轮廓腐蚀后没有前景种子会报错，应减小band或使用路径方法，而非静默返回整个轮廓。

## 颜色与组合

operation 为 `{"kind":"color","points":[...],"hsv_ranges":[[[0,50,30],[27,255,255]],[[174,50,30],[179,255,255]]],"rgb_difference_min":{"R-G":15,"R-B":30}}`。OpenCV H为0..179，S/V为0..255；红色跨零范围拆成两个区间。RGB差值以有符号数计算，颜色阈值为示例，不跨底色直接照搬。植物可使用G−R约束；紫色杂物可用B−G、R−G组合。范围在多边形内取并集，再扣除排除区。同一杂物可有轮廓主体、路径细带和颜色部件；重叠取并集，排除区优先。

黑斑用 `{"kind":"brightness","points":[...],"gray_min":0,"gray_max":75,"sigma":0.6}`。阈值由原图局部外观决定，正常深色饰面应降低阈值或缩小范围，不把历史示例当通用值。此操作也支持明确的亮度区间，而非只能选黑。

浅色渗漏析出物可明确设置低饱和高亮色候选，但这需要原图语义复核；不是把所有 L 类统一改成选白。现有批量暗色规则未因此改变。

## 验证与费用

`python scripts/test_guided.py` 检查偏移粗引导可被修正、线宽变化、断裂保留、带外强干扰排除、孔洞排除、坐标/RLE与确定性。合成测试通过只证明这些行为，不证明真实50张精度改善。

guided.py 的 seconds 包含本地读取/求解/图像导出，不包含引导制作和人工复核。导出 guide_edit_seconds=null/实测值、辅助次数及guides哈希。OpenCV阶段token为0，引导生成阶段未知；两者必须分开。图片条目可提供revision_reason、previous_run保存修订来源。当前没有完整50张辅助精修的新性能报告。

输出实例/类别/总mask、bbox图、guide_overlays、结果叠加以及JSON；尚无辅助模式独立HTML或直接兼容基线evaluate.py的适配器。
