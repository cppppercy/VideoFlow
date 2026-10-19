# ASR 质量与速度基准

版本：v0.4.3

环境：Windows、Python 3.13.7、CPU INT8、faster-whisper 1.2.1

## 复现工具

```powershell
python -m videoflow.benchmark "D:\media\course-sample.mp4" --profiles fast,balanced,accurate,gpu_turbo --models base,small --language zh --reference "D:\media\reference.txt" --json benchmark.json
```

工具对每个配置记录媒体时长、模型加载时间、推理时间、RTF、进程峰值内存、当前 Python 进程峰值显存、实际批量大小、需复核分段数、最后字幕时间、覆盖状态和输出字符数。只有提供同一测试片段的人工参考稿时才计算 CER；字符数、模型概率和需复核段数量都不能代替准确率。

要评估可疑片段精修，可在同一参考稿上额外运行一次：

```powershell
python -m videoflow.benchmark "D:\media\course-sample.mp4" --profiles gpu_turbo --language zh --reference "D:\media\reference.txt" --refine-low-confidence
```

GPU 默认按总显存保守选批量；8 GB 设备优先尝试 8。也可用 `VIDEOFLOW_GPU_BATCH_SIZE=1..8` 固定批量并比较速度/显存。CUDA 内存不足时，程序会针对当前媒体或当前 5 分钟分块回退到更小批量；基准结果中的“批量”是实际成功值。

参考稿应对应完整测试片段。建议从课程中另存 2–3 分钟、包含专业术语和正常停顿的片段，再人工逐字校对。媒体、参考稿和 JSON 结果不应提交到 GitHub。

## 本机实际结果

同一段经授权的 356.33 秒中文视频：

| 配置 | 管线 | 推理秒数 | RTF | 峰值内存 | 最后字幕 | CER |
|---|---|---:|---:|---:|---:|---:|
| GPU 增强 / turbo / beam 5 / FP16（RTX 4060） | batched | 6.07 | 0.017 | 1765.9 MB 进程内存 | 354.7 秒 | 未测 |
| fast / base / beam 1（当前） | batched | 9.83 | 0.028 | 964.1 MB | 354.7 秒 | 未测 |
| balanced / base / beam 5（当前） | batched | 14.50 | 0.041 | 本次未单独记录 | 354.7 秒 | 未测 |
| fast / tiny（历史配置） | batched | 8.63 | 0.024 | 726.5 MB | 354.9 秒 | 未测 |
| balanced / base（早期线程配置） | batched | 35.87 | 0.101 | 619.8 MB | 354.7 秒 | 未测 |
| fast / tiny（更早配置） | batched | 25.24 | 0.071 | 739.8 MB | 354.86 秒 | 未测 |
| 原始 tiny | standard | 74.68 | 0.210 | 475.1 MB | 355.36 秒 | 未测 |

本机是 i7-14650HX + RTX 4060 Laptop 8 GB。GPU 增强档使用 turbo/beam 5/FP16，实测比 CPU base 两档都快；快速档由 tiny 改为 base/beam 1，历史 tiny 数据只用于说明旧配置。这些结果不是对其他电脑的固定承诺。v0.4.2 保留短媒体批量路径，并让长媒体按 5 分钟分块后继续使用批量推理，以限制整段特征的峰值内存。

另一次同媒体冷启动记录中，balanced/base 批量推理为 129.80 秒，原始 base 为 95.43 秒；两者的词级时间戳和分段选项不同，不能据此作严格速度或准确率结论。

## 准确率结论

当前没有与该视频完整对应的人工参考稿，因此 fast、balanced、accurate 的 CER 均为“未测”。现有字符数与分段数只能验证程序输出，不能证明准确率提高。

`small` 没有在当前缓存中，SenseVoiceSmall、FunASR/Paraformer 和 whisper.cpp 也未安装或运行。本轮没有为了未经证明的收益增加大型必选依赖。后续只有在同一人工参考样本上证明 CER、速度和内存综合收益后，才应通过可选适配层加入其他引擎；现有 Whisper 必须继续作为回退。

## 当前推荐

- GPU 增强：检测到完整 NVIDIA CUDA 环境时作为本机默认；turbo 容量高于 base，且在 RTX 4060 上实测速度更快。仍需用人工参考稿验证课程 CER。
- 快速：base/beam 1，适合没有兼容 GPU 时先生成可搜索初稿。
- 均衡：没有兼容 GPU 时的普通课程默认；术语应填写课程热词并人工抽查。
- 高精度：需要更大模型和更多时间；在没有参考稿前不承诺比均衡档提升多少。
- 超过 20 分钟：自动使用 5 分钟重叠分块的批量路径，并显示当前块进度。3600 秒连续有声重复样本的旧 fast/tiny 推理为 60.66 秒、RTF 0.017、峰值约 815.4 MB；该历史样本不代表当前 base 快速档，也不等于真实课程准确率验收。
