# 三种mask生成方法：处理流程与数据流

依据当前实现绘制；参考标注只在评估阶段使用。蓝=输入，灰=处理，黄=判断，绿=数据产物，红=异常/回退。

## 纯 OpenCV：原图像素规则分割

对应 skills/facade-opencv-mask/scripts/segment.py。基线不使用模型mask，亦不使用assisted人工引导。

```mermaid
flowchart TD
  i["01 输入：只读原图 + 冻结检测清单<br/>原图 I：H×W×3 RGB；每张可有多个实例<br/>每实例：ID、类别/子类型、bbox=[x1,y1,x2,y2)，坐标为原图像素<br/>不读取 API mask、参考 mask 或人工逐图轮廓"]
  c["02 逐实例裁剪与计算尺度<br/>ROI = I[y1:y2, x1:x2]；记录原始 ROI 宽高、偏移与缩放<br/>裂缝 C/M：原分辨率；其他类：ROI 长边最多 1000 像素<br/>由类别分流；下方六条分支只执行对应的一条"]
  a["03A 裂缝 C / 网裂 M<br/>RGB → 灰度 → Gaussian 平滑<br/>多尺度 black-hat 取最大响应<br/>响应阈值：Otsu×0.65，限7–30<br/>另约束灰度 < 第80百分位<br/>连通域及线形过滤<br/>不做破坏细线的大开运算"]
  b["03B 锈迹 T / 腐蚀 R<br/>RGB → HSV 和 Lab<br/>筛红、橙、棕色像素<br/>H<27 或 H>173；S>48<br/>V>28；Lab a>127、b>132<br/>去小连通域，填少量小孔<br/>颜色不能独立证明锈蚀语义"]
  d["03C 植物 V<br/>RGB → HSV + 灰度<br/>绿色条件：H 29–100<br/>S>38 且 V>28<br/>另取暗色：灰度 < 截断Otsu<br/>绿色 ∪ 暗色 → 连通域过滤<br/>阴影可能混入"]
  e["03D 地面垃圾 D<br/>子类型必须是 GroundLitter<br/>低灰度样本的 Lab 中位数<br/>作为地面背景色<br/>取较亮像素或高色度/色差<br/>亮度分位阈值 + Lab 距离<br/>去小连通域；暗色布料可漏"]
  f["03E 污渍 D / 渗漏 L<br/>RGB → 灰度及局部平滑<br/>暗色 Otsu + 局部亮度残差<br/>候选：全局暗 或 局部偏暗<br/>L 额外加入黄棕色条件<br/>去小连通域、填小孔<br/>白色析出物仍可能漏选"]
  g["03F 剥落 P / 破损 S<br/>RGB → Lab → 4类聚类<br/>bbox边缘主色估计完好背景<br/>色差选择前景簇 → 种子<br/>腐蚀内核=确定前景<br/>边缘非目标=确定背景<br/>GrabCut 3轮 → 清理与填小孔"]
  merge["04 输出 ROI 二值候选，保留方法与参数<br/>每条分支产生当前 ROI 大小的 0/1 mask<br/>P/S：GrabCut失败或种子不足时使用聚类种子并记录原因<br/>记录尺度、阈值、前景比例和可能的阴影/材质误判"]
  restore["05 还原到原图坐标<br/>若ROI缩小过：最近邻恢复到原bbox宽高<br/>建立全黑 H×W 画布，在 [x1:x2, y1:y2] 对应位置贴回<br/>每个实例单独保存，不把不同bbox合成一个实例"]
  export["06 聚合与导出<br/>实例 mask_i → 按类并集 → 全部实例并集 M_total<br/>M_total / mask_i 均为 H×W，PNG单通道0/255<br/>原图 + 实例彩色mask + bbox/ID → 叠加图；同时输出bbox图<br/>JSON含类别、bbox、面积、列优先RLE；保存耗时、参数、质量提示"]
  verify["07 结果验证与人工复核<br/>检查尺寸、二值、bbox范围、实例并集及RLE可逆性<br/>小/空mask、几乎填满bbox等仅触发复核，不代表自动判错<br/>本次109实例全部有文件；不代表109实例分割正确"]
  i --> c
  c -->|"按类别"| a
  c -->|"按类别"| b
  c -->|"按类别"| d
  c -->|"按类别"| e
  c -->|"按类别"| f
  c -->|"按类别"| g
  a --> merge
  b --> merge
  d --> merge
  e --> merge
  f --> merge
  g --> merge
  merge --> restore
  restore --> export
  export --> verify
```

## image2.5：局部画布 → 模型mask → 原图坐标

对应 batch_local.py / local_crop_trial.py / api_adapter.py / run.py。VS Code只负责运行Python，不是分割模型。

```mermaid
flowchart TD
  i["01 输入与预检查<br/>原图 I(H×W×3) + 冻结 bbox/ID/类型/子类型<br/>读取模型配置、环境变量/密钥文件；检查范围与bbox；不重新检测<br/>默认 dry-run：不发请求；--run 才进入付费处理"]
  gate["02 缓存、复用与提交门控<br/>已有成功记录：验证原图/输出哈希后跳过<br/>已有失败记录：默认跳过；--retry-failed 才在本轮重试一次<br/>首次且00/04历史试验可用：核对bbox/类型并复制、标记 carried_forward<br/>无可用记录 → 当前实例进入裁剪；本次00和04走历史复用"]
  roi["03 取局部上下文 ROI<br/>横向边距=max(12, round(bbox宽×20%))<br/>纵向边距=max(12, round(bbox高×2.5%))；ROI裁到原图边界<br/>得到局部RGB及其原图偏移 (a,b)；bbox仍保持冻结"]
  tile["04 选择单面板或四段拼图<br/>max(ROI宽/高, ROI高/宽) > 3？<br/>是：沿长边等分4段，按阅读顺序放入2×2网格（每格512）<br/>否：使用一个1024面板；每面板等比缩放、居中留边<br/>总画布固定1024×1024，洋红补边；图像缩放使用LANCZOS"]
  geo["并行产物：geometry.json<br/>每面板 source_xyxy / canvas_xyxy<br/>scale_xy=(sx,sy) 与画布内目标bbox<br/>前向坐标：u=(x-x0)×sx+ox<br/>v=(y-y0)×sy+oy<br/>这些数据只用于提示和确定性逆映射"]
  prompt["05 构造提示并持久化请求输入<br/>上传PNG画布 + 类型定义 + 实例ID + 画布bbox坐标<br/>要求逐面板原位分割，白=目标，黑=背景/补边；不画框或文字<br/>垃圾/墙面污渍使用独立子类型提示；保存submitted_images与prompt"]
  api["06 单实例图像API请求<br/>POST /v1/images/edits，multipart：PNG + prompt + model<br/>服务商标识 gpt-image-2.5；请求 size=1024x1024、quality=high<br/>接收base64或图片URL；下载并保留原始返回；每bbox一次请求"]
  err["异常支路：失败不伪造mask<br/>HTTP / SSL / 下载 / 解码失败 → 记录错误<br/>401/403设置停止标记，阻止后续新提交<br/>不进行自动付费重试；需显式 retry-failed<br/>保存attempts、耗时、可获得的usage与费用<br/>缺失实例导致图片partial，不能视为无缺陷"]
  norm["07 校验返回画布并二值化<br/>拒绝 |返回宽/高 - 1| > 0.02 的图像，不强行拉伸<br/>透明区域合成到黑底 → 灰度 → 阈值128 → 0/255<br/>最近邻归一到1024×1024；实际返回可不是1024<br/>非方形比例异常也进入失败记录支路"]
  back["08 根据保存的几何信息逆映射<br/>从归一画布裁出各面板 canvas_xyxy<br/>最近邻还原成 source_xyxy 对应的原图区域大小<br/>按原图坐标贴回全黑 H×W 画布；保存 unclipped mask<br/>此处只还原坐标，不按原图纹理修边；生成内容仍可能错位"]
  clip["09 裁到冻结bbox，保存原尺寸实例mask<br/>final[y1:y2,x1:x2] = restored[y1:y2,x1:x2]，框外=0<br/>保存mask哈希、空结果标记、框外裁除像素数；空mask也需复核"]
  out["10 聚合、叠加、JSON/RLE和统计<br/>按实例/类别/全部并集导出；叠加使用原图与mask混合着色<br/>成功记录保留usage、token、API秒数、总秒数和估算费用<br/>token未知记null；失败费用未知不当作0；原始账单未独立核验<br/>本次105/109有mask；00/04复用来源单独记录"]
  cache["沿用分支的输出<br/>不发起当前实例新请求<br/>已有成功记录 / 合法历史复用 → 聚合<br/>历史复用保留原始输入、几何及mask<br/>不是本轮同条件新盲测"]
  records["旁路记录 / 不参与分割<br/>records/*.json：每次attempt状态、usage<br/>geometry/*.json：坐标变换<br/>raw_model_outputs / raw_masks：模型原稿<br/>任何参考mask都不进入API或坐标还原"]
  i --> gate
  gate --> roi
  roi --> tile
  tile --> prompt
  prompt --> api
  api --> norm
  norm --> back
  back --> clip
  clip --> out
  tile -->|"保存映射"| geo
  gate -->|"跳过/复用"| cache
  api -->|"失败"| err
  out -->|"记录"| records
  geo -.->|"逆映射参数"| back
  cache -.->|"沿用到聚合"| out
```

## image2.5 + OpenCV：先验约束精修与回退

对应 refine_api_masks.py。是可选后处理；与04号此前的人工轮廓辅助精修不同。

```mermaid
flowchart TD
  i["01 输入：原图 + 冻结目标 + 已有API实例mask<br/>原图 I(H×W×3)、mask_i(H×W 0/255)、bbox、类别/ID、源文件哈希<br/>只使用这批API输出作为先验；不读取参考真值、人工轮廓<br/>输入缺少API实例 → 保持缺失/partial，不新增分割结果"]
  check["02 校验并保留原稿<br/>核对图像哈希、尺寸、二值值域及mask在bbox内<br/>空输入mask：原样回退并记录empty_input<br/>复制原图、原API总mask/叠加图；逐实例原稿单独保存"]
  band["03 确定搜索范围和处理尺度<br/>band=clip(round(bbox短边×2.5%), 4, 32) 原图像素<br/>取bbox外扩band的原图ROI；allowed只允许冻结bbox内部<br/>裂缝C/M不缩小；其他类：ROI长边最多1200，记录scale<br/>outer = 膨胀(API mask, round(band×scale)) ∩ allowed"]
  crack["04A 裂缝 C / 网裂 M：在搜索带中找暗线<br/>ROI RGB → 灰度 → 3×3 Gaussian(σ=0.6)<br/>椭圆核半径2/4/8的black-hat响应，逐像素取最大<br/>仅在outer取样求Otsu阈值，阈值下限4<br/>candidate = outer ∩ (response > threshold)<br/>8邻域连通域，移除面积<3的小孤点<br/>不做大范围闭运算，不依靠参考裂缝定位"]
  region["04B 其他类别：API先验初始化 GrabCut<br/>outer外=确定背景；outer内=可能背景<br/>原API mask内=可能前景；腐蚀内核=确定前景<br/>内核不足5像素：尝试距离变换>1的内部点<br/>前景/背景仍不足 → 异常回退<br/>固定随机种子，GrabCut 4轮；只取outer内前景<br/>与纯OpenCV基线不同：不再按各类别单独颜色阈值"]
  restore["05 候选还原与bbox限制<br/>若缩小过：最近邻恢复ROI原尺寸，贴回H×W全黑画布<br/>candidate &= 冻结bbox；保存候选mask，不覆盖原API<br/>求解异常时保存与原mask相同的占位候选，并标solver_failed"]
  qc["06 异常筛选（不是准确率评估）<br/>计算面积比 r=候选面积/原mask面积，以及候选与原mask的IoU<br/>候选为空，或 r<0.35 / r>2.5，或 IoU<0.10 → 拒绝<br/>这是与API先验的分歧检查；API本身可能错误<br/>语义/裂缝/空腔风险另记复核标签，不单凭标签拒绝"]
  accept["07A 通过异常检查<br/>selected = candidate<br/>标记 refined_candidate；本次93个<br/>通过只代表未触发异常阈值，不保证变好"]
  fallback["07B 触发异常或求解失败<br/>selected = 原API mask<br/>标记 raw_fallback；本次12个<br/>保留候选/原因，不能把原有错误当作已修复"]
  export["08 聚合并保存三份实例结果<br/>raw_instance_masks：原稿；candidate_instance_masks：候选<br/>instance_masks：最终选用；按类与全图并集 → mask和叠加图<br/>JSON/RLE记录source_mask_sha256、尺度、搜索半径、面积变化<br/>记录opencv_seconds与回退原因；新增API请求/token/费用均为0"]
  eval["09 单独评估与复核（只读，不反馈调参）<br/>检查尺寸/二值/bbox/RLE/并集；先确认文件一致性<br/>需要评估时才读取参考mask：实例ID、类型、bbox和原图哈希对齐<br/>输出IoU、Dice、精确率、召回率、2px边界F1；人工看前后叠加<br/>本次区域宏IoU提高，但边界F1下降：不能自动覆盖所有原稿"]
  i --> check
  check --> band
  band -->|"C/M"| crack
  band -->|"其他类别"| region
  crack --> restore
  region --> restore
  restore --> qc
  qc -->|"通过"| accept
  qc -->|"拒绝/异常"| fallback
  accept --> export
  fallback --> export
  export --> eval
```
