# VideoFlow v0.4.2 交接摘要

- 基线：`main` / `0a97623`（v0.4.1）。
- 本轮目标：长视频稳定性、可观察性、TXT 阅读格式和本机 ASR 基准。
- 已实现：20 分钟以上媒体采用 5 分钟重叠分块、块内批量识别；CPU 模型最多使用 8 线程；另有进度与诊断、可疑尾部覆盖提示、统一自然段 TXT、CER/RTF 基准工具。
- 中文质量修复：快速档由 tiny 改为 base/beam 1；解码阶段抑制重复和静音幻觉；中文结果经本地 OpenCC 确定性转换为简体，明显的连续重复只做保守压缩。该后处理不能修复模型错听。
- GPU 增强：检测到完整 NVIDIA CUDA 环境时默认使用多语言 turbo/beam 5/FP16；Windows cuBLAS/cuDNN 作为可选依赖，不增加 CPU 用户的默认安装体积。术语提示改用专用 hotwords。
- 自动化：59 项测试通过；Python 编译、依赖检查、JavaScript 语法、Gradio 页面构造和差异格式检查均通过。
- 真实技术验证：65 分钟稀疏样本在 64:54.6 仍有字幕；60 分钟连续有声重复样本到达 60:00，旧 fast/tiny 推理 60.66 秒。二者均由授权媒体构造，不是学校课程。当前 fast/base 在 5 分 56 秒授权视频上推理 9.83 秒，balanced/base 为 14.5 秒，RTX 4060 turbo 为 6.07 秒；均无人工参考稿 CER。
- 未验证：60–90 分钟真实连续课程、LMS 登录态完整回放、人工参考稿 CER、small/SenseVoice/Paraformer。
- 架构约束：所有来源继续统一输出 `Transcript`；TXT 排版只在导出层处理；SRT 不受影响；LMS 凭证保护和 B 站 `bestaudio` 限制保持不变。
- 发布状态：本文件不代表已推送、打标签或创建 Release。
