# FacadeFixer mask API

建筑外立面缺陷mask实验：原图＋固定检测框＋缺陷类型，生成原尺寸mask和叠加图，比较OpenCV、image2.5及API后精修。

## 代码与目录

```text
scripts/         mask生成、API接口、几何处理与可选精修
skills/          独立的OpenCV分割／精修skill
tests/           几何、精修、保存和评价指标测试
tools/           结果汇总、评价、HTML报告和流程图生成
data/input/      本次50张原图及109个bbox／类型
data/reference/  用户保留的参考标注、RLE和各级mask
evaluation/      已保存的量化统计
reports/         发布好的HTML报告与展示图片
```

生成mask的代码与生成报告的代码分开存放。所有命令从仓库根目录执行。

## 1. 准备环境与本次输入

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item models.example.json models.json
Copy-Item data/input/manifest.json input_manifest.json
$env:APINEBULA_API_KEY = '填写自己的密钥'
```

原图已包含在 `data/input/images/`，清单使用相对路径。编辑 `models.json` 设置自己的模型、地址、价格及可选代理；不要提交密钥。模板价格是历史实验配置，不代表当前报价。

## 2. 生成mask

```powershell
# 先检查输入，不请求API
python scripts/batch_local.py --start 0 --end 49 --output outputs_api50
# 正式调用，会产生API费用
python scripts/batch_local.py --start 0 --end 49 --output outputs_api50 --run
# 仅重试失败实例
python scripts/batch_local.py --start 0 --end 49 --output outputs_api50 --run --retry-failed
# 只更新结果预览
python scripts/batch_local.py --start 0 --end 49 --output outputs_api50 --review-only
```

每个bbox一次请求，不重新检测，不读取参考mask。输出包含独立实例mask、整图mask、类别mask、叠加图、JSON/RLE及耗时/token/估算费用。生成图尺寸正确不代表边缘准确，仍需复核。未知费用和token不等于0。不要同时向同一输出目录运行两个批次；代码或配置变化请使用新目录，保留原版本用于旧批次续跑。

### 纯OpenCV基线与可选精修

```powershell
pip install -r requirements-refine.txt
python skills/facade-opencv-mask/scripts/segment.py --manifest data/input/manifest.json --output outputs_opencv50
python scripts/prepare_refine_input.py --input outputs_api50/gpt_image_2_5_default --output API_RESULT_DIR
python scripts/refine_api_masks.py --input API_RESULT_DIR --output NEW_REFINED_DIR
python scripts/refine_api_masks.py --input API_RESULT_DIR --output NEW_REFINED_DIR --run
# 输入、代码、参数不变时续跑
python scripts/refine_api_masks.py --input API_RESULT_DIR --output NEW_REFINED_DIR --run --resume
```

模型输出目录名取决于配置中的模型ID。精修默认关闭，不新增API调用，不覆盖原mask。skill可独立安装，不安装也能在Python终端运行脚本。详见[精修说明](REFINEMENT.md)和[mask代码说明](scripts/README.md)。

## 3. 本次输入与参考真值

[数据目录及说明](data/README.md) · [输入清单](data/input/manifest.json) · [参考标注](data/reference/annotations/) · [数据校验信息](data/dataset.json)

包含50张原图、109个固定实例和对应参考mask。参考版本为 `builtin50_litter_wall_20260928_v6`：模型生成后经用户多轮修订保留，**不是独立专家真值**。原图和mask字节保持不变，机器绝对路径已改为相对路径。输入清单只含原图、bbox、类别及可选子类型；参考mask只用于评价。

## 4. 评价与测试

```powershell
python tools/compare_three_methods.py --reference data/reference --opencv outputs_opencv50 --image25 API_RESULT_DIR --hybrid NEW_REFINED_DIR --output NEW_COMPARISON_DIR
python tests/test_dataset.py
python tests/test_geometry.py
python tests/test_local_batch.py
python tests/test_refine_api_masks.py
python tests/test_refine_save.py
python tests/test_comparison_metrics.py
```

统计按原图哈希、实例ID、bbox和类别对齐。既报告缺失计0分的全部实例，也报告共同有输出的实例；指标表示与候选参考的一致度。参考不用于精修调参。详见[评价说明](EVALUATION.md)。

## 报告与展示

- **[精简版实验报告](https://mo0407.github.io/FacadeFixer_mask_api/reports/experiment_brief/index.html)**：方法、流程图、分类统计、时间费用和结论。
- [详细实验回顾](https://mo0407.github.io/FacadeFixer_mask_api/reports/experiment_recap/index.html)：迭代过程、案例和实现说明。
- [完整50张对比报告](https://mo0407.github.io/FacadeFixer_mask_api/reports/comparison50/comparison.html)：逐图对比参考、OpenCV、API和精修结果。
- [详细处理流程图](https://mo0407.github.io/FacadeFixer_mask_api/reports/comparison50/workflows.html) · [Mermaid源码](WORKFLOWS.md)。

截至当前记录：API及混合方法105／109实例有输出，46／50张实例齐全。缺失4项，不代表无缺陷。报告可在线浏览，也可下载仓库后打开HTML。

### 重新生成报告

```powershell
python tools/build_experiment_brief.py
python tools/build_experiment_recap.py
```

报告工具说明见[tools/README.md](tools/README.md)。生成新的三方法比较请使用上面的评价命令；`collect_results50.py`仅针对原实验两批目录。报告展示所需的历史图片仍保留原路径，既有在线链接不变。
