# 可选 API + OpenCV 后处理

只有用户选择精修时才运行；普通API批次不自动加载本步骤。skill是可选操作规范，Python终端不会自动读取SKILL.md或改变提示词。

仓库入口 `python refine_api_masks.py --input API_RESULT --output NEW_DIR --run`；单独安装skill时可运行本skill的 `scripts/refine_api_masks.py`，同样显式传input/output路径。依赖scripts/requirements-refine.txt。无API调用，保留原始、候选及最终mask，逐实例保存参数和回退原因。旧版report写入WinError5已有有限重试，报表占用不会丢失完成的图片记录。

输入目录包含annotations、images、instance_masks、masks、overlays。annotation使用image_index、file_name、source_path（相对输入目录）、source_sha256、width、height、status、expected_instances和defects。defects含id、class_code、bbox_xyxy、mask_path。原图和mask必须同尺寸，bbox零基右下不包含。

裂缝使用原分辨率black-hat暗线搜索；其他类使用API前景内核初始化GrabCut，区域长边限1200。API误选内核可能被锁定；4–32像素搜索带不能修复远距离偏移。异常面积/一致度检查仅用于回退，不能认作准确率保证。初始缺失实例保持partial，不填框伪造。

应保存原API结果，比较前后区域IoU和边界F1；候选参考经过模型及人工反馈修订时，将数值称参考一致度。三方法比较时分别统计全部目标（缺失0分）与共同有效实例，按冻结id、类别、bbox对齐；不根据参考mask反向调整精修。

本次50张证据：相对候选参考，全109目标宏IoU从0.4056到0.4283，但2像素边界F1从0.4863到0.4411。不能声称全面提升；低IoU/细裂缝/污渍及空腔仍需语义或人工引导。逐图人工轮廓属于另一个实验模式，不混入自动结果。
