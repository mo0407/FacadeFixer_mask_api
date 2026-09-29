# API mask + OpenCV 自动精修

输入为 `results50_gpt_image_2_5_vscode` 汇总结果，输出默认 `outputs_refined50_v1`。原始API结果不变，不调用API、不读取参考mask、不使用逐图人工轮廓。与此前04号“人工引导+OpenCV”不同，本程序是自动混合方法，不能保证达到那次交互精修效果。

在当前项目VS Code终端执行：

```powershell
# 本机环境已安装OpenCV，其他环境先 pip install -r requirements-refine.txt
& 'E:\ai\低空\venvs\facadefixer\Scripts\python.exe' -X utf8 refine_api_masks.py
& 'E:\ai\低空\venvs\facadefixer\Scripts\python.exe' -X utf8 refine_api_masks.py --run
```

首行只校验输入；第二行实际离线精修。50张包含105个可用实例、4个API失败实例，失败实例不补造mask，仍标记partial。若之后补齐API，应先重新执行collect_results50.py，再指定新的精修输出目录。

完成后打开 `outputs_refined50_v1/comparison.html`：原图、API叠加、精修叠加、最终mask逐张对比。

- `raw_instance_masks/`：原始API mask；`candidate_instance_masks/`：候选精修；`instance_masks/`：经过异常检查选取的最终mask。
- `masks/`、`class_masks/`、`overlays/`：原尺寸总mask、类别mask、叠加图。
- `annotations/`：独立实例、bbox、类别、RLE、原API元数据、精修参数、处理尺度、耗时及复核提示。
- `records/`、`metrics.csv`：精修耗时及候选/回退数量。原API费用与token不覆盖；OpenCV新增API费用与token均为0。

## 方法与边界

裂缝C/M：原分辨率、多尺度black-hat暗线响应，在原mask膨胀后的搜索带内提取。可能混入墙面纹理、接缝；不能保证恢复偏移很远的裂缝。

其他区域类：以API mask的腐蚀内核为确定前景、外侧为背景，GrabCut按原图颜色精修。不强制按颜色类别阈值截断，以免漏掉白色析出物或灰色基材。大区域长边最多1200像素，记录缩放比例，回原图采用最近邻。确定前景也可能锁住API误选，须看原图核对。

所有类型使用共享参数，不按这50张的参考mask调参。搜索半径为bbox短边2.5%，限制4–32原图像素。候选为空、面积比小于0.35/大于2.5或与原mask IoU小于0.1时，保留原mask并记raw_fallback；这是保守异常检测，不是质量评分。原mask本身可能错误，回退也不代表正确。`prior_agreement_iou`仅表示改动程度，不是对真值准确率。

不自动填满空洞或bbox、不将失败API实例伪装为成功。空腔漏选、浅色起皮、污渍/阴影及大幅错位不能仅靠本流程可靠解决，需人工引导或重做分割。当前程序不包含手绘引导界面。

## 指定样本和续跑

```powershell
python refine_api_masks.py --indices 17,29,47 --output outputs_refined_cracks_v1 --run
python refine_api_masks.py --run --resume
python test_refine_api_masks.py
```

相同输入、参数和程序才能resume，跳过已有完成记录。输出已存在而不传resume会拒绝覆盖。异常退出遗留.running.lock时，确认旧进程停止后再移除锁。不要同时启动两个任务；改变代码、输入或范围应使用新输出目录。
