# FacadeFixer mask API

建筑缺陷分割实验：原图 + 冻结 bbox + 缺陷类型 → gpt-image-2.5 API → 原尺寸 mask、叠加图、JSON/RLE、耗时/token/估算费用。可在 VS Code 的 Python 终端运行。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item models.example.json models.json
Copy-Item input_manifest.example.json input_manifest.json
$env:APINEBULA_API_KEY = '填写自己的密钥'
python batch_local.py --start 0 --end 49 --output outputs_api50
python batch_local.py --start 0 --end 49 --output outputs_api50 --run
```

将原图放在 `images/`，或修改 manifest 的 image_path；编号0–49，示例包含50张的109个bbox与类别，不包含图片或参考mask。bbox为原图像素坐标 `[x1,y1,x2,y2]`，右下不包含。请从项目根目录执行。VS Code先选择Python解释器，再通过“终端 → 运行任务”运行。

默认无参数选择10–49，是原实验后40张入口；新跑全部50张务必显式传入0–49。每个bbox一次请求，默认串行；不重新检测，不使用参考mask或OpenCV轮廓精修。未提供历史输出时不会复用00、04。

API地址为 `https://apinebula.ai/v1/images/edits`；模型名为服务商提供的 `gpt-image-2.5`，不代表独立验证其底层身份。group_requested仅记录请求分组，不能据此保证服务商路由。需要代理时，在模型配置增加 `proxy`，例如 `http://127.0.0.1:7897`；模板未绑定本机代理。

## 方法与限制

按bbox加上下文裁剪，宽高比超过3时沿长边分4段拼为2×2；等比映射到1024方形画布。返回二值mask经记录的坐标映射还原，最近邻缩放，并裁到冻结bbox内。保留原始返回、实际输入、变换、裁框前mask与最终mask。原尺寸一致不保证模型边界准确；裂缝偏移、空腔漏选、碎片化需要人工审查。

输出目录中 `review.html` 查看结果，`masks/` 为总mask，`instance_masks/` 为独立实例，`overlays/` 为彩色叠加，`annotations/` 为JSON及列优先RLE，`metrics.csv` 为单张最新记录，`records/` 的attempts保留重试历史。unknown/null不是0，汇总估算费用不等于账单。配置价格仅为实验时用户提供的¥0.05/次，请按实际平台计价更新。细分类可选class_subtype，例如GroundLitter、WallStain。

## 重试和验证

```powershell
python batch_local.py --start 0 --end 49 --output outputs_api50 --run --retry-failed
python batch_local.py --start 0 --end 49 --output outputs_api50 --review-only
python test_local_batch.py
python test_geometry.py
```

重复运行跳过已有记录，包括失败；显式retry-failed才重试，每实例本轮一次。程序不自动反复付费重试。不要并行运行两个批次到同一目录。异常退出后确认旧进程结束才可移除.running.lock；请求中断可能已扣费。配置或代码变化需新输出目录（指纹保护）。partial图片不是完整标注。

## 本次50张实验

截至本次汇总：50张109实例，成功105，46张实例齐全，4个失败：25/ID2、27/ID1、30/ID1、39/ID1。两批累计152次请求，已知估算¥5.15，49次费用未知；不含00、04复用结果的原始请求与更早被舍弃试验。不是准确率，尚未专家验收，不可直接当作真值。

`batch_local_first10_snapshot.py`保留首批代码，`run.py`为旧整图入口兼公共工具，当前推荐batch_local.py。`collect_results50.py`仅用于汇总原实验的first10及remaining40目录，复制图片并生成独立本地对比页；它不调用API。报告引用的图片和总mask已随HTML上传；其他中间结果保留在本地。04人工视觉辅助精修不纳入纯API实验。


## 可选 skill / OpenCV 精修（默认关闭）

纯API执行命令保持不变，不需要安装skill或OpenCV。需要精修时另行选择：

```powershell
pip install -r requirements-refine.txt
python prepare_refine_input.py --input outputs_api50/gpt_image_2_5_default --output API_RESULT_DIR
python refine_api_masks.py --input API_RESULT_DIR --output NEW_REFINED_DIR
python refine_api_masks.py --input API_RESULT_DIR --output NEW_REFINED_DIR --run
# 输入、参数不变时续跑
python refine_api_masks.py --input API_RESULT_DIR --output NEW_REFINED_DIR --run --resume
```

先用prepare_refine_input.py将API模型子目录整理成相对images路径的独立输入；需要原图仍在原位置。本次collect_results50.py生成的汇总已经可直接作为精修输入。精修不会调用API，不覆盖原mask。详见 [精修说明](REFINEMENT.md)。

`skills/facade-opencv-mask`是可选Codex skill，可自行安装到个人skills目录；不安装也可直接运行Python代码。Python终端不会自动执行SKILL.md。独立skill内含纯OpenCV segment.py、辅助guided.py和自动后处理refine_api_masks.py，分别区分bbox基线、人工引导、模型mask后处理。额外视觉引导不混入自动基线。

## 三方法评估

见 [量化报告](EVALUATION.md) 和 [统计文件](evaluation/summary.json)。参考来自用户保留的候选标注，未独立专家验收。全109实例宏IoU：OpenCV 0.3908、API 0.4056、混合0.4283；混合边界F1却比API下降，不宣称全面改善。

```powershell
python compare_three_methods.py --reference REFERENCE_DIR --opencv OPENCV_DIR --image25 API_DIR --hybrid REFINED_DIR --output NEW_COMPARISON_DIR
python test_refine_api_masks.py
python test_refine_save.py
python test_comparison_metrics.py
```

评估按原图哈希、实例ID、类别和bbox对齐，包含缺失按0分及共同可用子集两个统计口径；生成可离线分享的原图+参考+三方法对比页。输入为各程序输出根目录。评估只读取结果，不影响分割。完整HTML报告、原图、叠加图及总mask现已放在 reports/comparison50/；逐实例中间结果保留在本地。


## 可离线查看的完整报告

[报告目录](reports/comparison50/) · [HTML](reports/comparison50/comparison.html)。下载仓库ZIP并解压后，用浏览器打开该HTML；GitHub文件页面显示HTML源码，不代表页面无法使用。本次未启用GitHub Pages。

报告已补充四组mask的输入、方法、人工参与和限制，并提供每张的黑白mask链接。参考为多轮修订的候选标注，不是独立专家真值。
