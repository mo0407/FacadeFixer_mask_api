# 统计与报告代码

本目录工具不调用付费模型API。请从仓库根目录运行。

- `collect_results50.py`：汇总原实验两批已有输出。
- `compare_three_methods.py`：以实例ID对齐参考和三种方法，计算指标并生成对比报告。
- `build_experiment_brief.py` / `brief_flowcharts_medium.py`：精简报告及流程图。
- `build_experiment_recap.py` / `recap_reading_layout.py`：详细回顾。
- `build_workflow_diagrams.py`：详细流程图。
- `templates/MASK_METHODS.html`：比较报告中的方法说明片段。

Mask生成及精修入口在 `scripts/`，可选OpenCV skill在 `skills/`。
