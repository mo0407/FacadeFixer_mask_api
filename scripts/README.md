# Mask处理代码

从仓库根目录运行。`batch_local.py` 为当前API局部分割入口，`local_crop_trial.py` 负责几何变换，`api_adapter.py` 负责接口，`run.py` 包含公共工具及旧整图入口。

`prepare_refine_input.py` 整理API输出，`refine_api_masks.py` 执行可选OpenCV精修。`batch_local_first10_snapshot.py` 为历史首批快照。纯OpenCV入口位于独立的 `skills/facade-opencv-mask/scripts/segment.py`。

结果整理、评估和报告生成代码位于 `tools/`，不在本目录。
