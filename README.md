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

分类统计统一把原始 **C（裂缝）与 M（网裂）合并为“裂缝”**，共23个实例，汇总表使用 `C+M` 表示这一组。按23个实例等权重算 IoU、Dice 和边界F1，不是两个类别均值的简单平均。合并后共8个统计类别；原始标注、模型输入和逐实例CSV仍保留C/M，保证匹配与追溯。整体109实例指标不受此分类合并影响。

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


## 类别调整（2026-10-13）

原裂缝C和网裂M合并为“裂缝”C，共23个实例；原渗漏／沉积物L按用户指定名称改为“白桦”L，共2个实例。当前共8类、109个实例。

此操作是类别归并与改名，不重新判断缺陷外观：原图、bbox、单实例mask和RLE均未改变。类别mask按新类别合并，按类别的指标重新聚合；全部实例的总体指标不变。`original_class_code` / `original_class_name` 保留修改前类别，历史API提示词与原始响应不改写。见 [类别映射](data/taxonomy.json)。

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

## 可选 skill：先判断位移，再复位

[facade-crack-realign](skills/facade-crack-realign/SKILL.md) 对API生成的裂缝mask逐实例处理，默认作为可选后处理，不改变纯API实验。流程：**坐标还原与校验 → 模型看原图/叠加图 → 确认整体偏移才调用复位 → 模型复核候选 → 接受或沿用原稿**。

已对齐、形状/线宽错误、不确定或几何映射未验证的实例跳过复位；原稿、候选、判定证据、输入哈希、位移和耗时均记录。C/M输入都适用，统计统一归为裂缝。

```powershell
pip install -r skills/facade-crack-realign/scripts/requirements.txt
# 按数据格式准备inputs_crack.json，生成逐实例叠加图与判断模板
python skills/facade-crack-realign/scripts/postprocess.py inspect --inputs inputs_crack.json --output crack_inspection
# 模型或人工看crack_inspection/review.html，填写其中的decisions.json
python skills/facade-crack-realign/scripts/postprocess.py propose --decisions crack_inspection/decisions.json --output crack_proposals
# 再看候选叠加图，为实际移动的实例填写verifications.json
python skills/facade-crack-realign/scripts/postprocess.py finalize --proposals crack_proposals --verifications verifications.json --output crack_final
# 无API调用的离线验证
python skills/facade-crack-realign/scripts/test_postprocess.py
```

见[输入与判定JSON格式](skills/facade-crack-realign/references/decision-schema.md)及[API接入说明](skills/facade-crack-realign/references/api-integration.md)。`inspect`自动写入原图/mask哈希，判定时保持哈希不变；后复核必须绑定实际候选哈希。最终输出位于`crack_final/instance_masks/`、`overlays/`和`records.json`，mask保持原图尺寸、bbox限制，并附面积和RLE。默认最多允许2%前景因触框丢失；如需完整保留，给`propose`增加`--min-kept 1`。

Codex可将此skill文件夹安装到个人skills目录后用 `$facade-crack-realign` 调用。普通Python图像API不会自动执行`SKILL.md`：当前`batch_local.py`尚未自动调用视觉判断API，需由视觉agent或人工填写判定文件；完全自动接入时另行配置支持原图/叠加图与结构化输出的视觉模型。OpenCV复位不调用API，额外视觉判断的时间、token与费用应单独记录。

### 已保存的位移试验（23个裂缝实例）

| 版本 | 平均实例IoU |
|---|---:|
| image2.5原稿 | 0.161 |
| 旧整体位移版 | 0.183 |
| 分段一致性改进版 | 0.186 |

统计文件：[汇总](evaluation/crack_realign_summary.json)、[逐实例](evaluation/crack_realign_instances.csv)。这是此前位移算法的同批对照，尚未在50张真实样本上重新执行新增的“模型先判断、再复位、后复核”skill；它与原三方法中的边界精修实验分开记录。参考来自用户保留的候选标注，规则也在本批样本分析后调整，不能当作独立准确率。整体平移无法修复线宽、形状、漏分支或选错目标。
