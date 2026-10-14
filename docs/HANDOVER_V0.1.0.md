# VideoFlow v0.1.0 版本交接报告

报告日期：2026-10-14。本文供下一轮 ChatGPT 产品规划使用，只记录已实现和已验证的事实。

## 1. 版本与仓库

- 版本：`0.1.0`（见 `pyproject.toml`）。
- 代码基线：`main` 分支上的功能提交 `01ae3a9755c629bfbc8ca1da06b3c3fe7bd53cea`（`fix: pin PyAV compatibility and prepare v0.1 release`）。本交接报告后续的文档提交不改变该功能基线。
- GitHub：<https://github.com/cppppercy/VideoFlow>，已确认是公开仓库，默认分支为 `main`。

## 2. 已实现功能与可用程度

- 可在本机上传常见音频/视频文件，使用 faster-whisper 转录为带开始、结束时间和文本的分段数据。
- 默认参数为 CPU 与 INT8；可选模型仅为 `tiny`、`base`、`small`，支持自动识别语言或手动选择中、英、日、韩。
- Gradio 页面提供上传、模型/语言选择、处理状态、分段表格、全文/SRT 文本复制以及 TXT/SRT 文件下载。
- CLI 可将同样的转录结果写入指定输出目录。
- 真实可用性已验证：一段经负责人授权的 356.331 秒中文 H.264/AAC MP4 在 `tiny` 模型下产出 120 个分段、UTF-8 TXT（3315 B）和 SRT（7765 B）。项目负责人随后确认本机图形界面手动测试通过。

## 3. 技术栈与关键模块

- Python `>=3.11,<3.14`；本机验证环境为 Python 3.13.7。
- `faster-whisper 1.x`：本地推理；`ctranslate2` 为其运行时依赖。
- `PyAV >=11,<19`：媒体读取兼容性约束。PyAV 19 删除了 faster-whisper 1.x 仍传入的 `metadata_errors` 参数，不能放宽到 19。
- Gradio 5–6：仅绑定本机 `127.0.0.1`，未启用公开分享。
- pytest：单元测试；FFmpeg：实际媒体兼容性前提。

关键模块：

- `src/videoflow/transcriber.py`：输入/模型校验、模型加载与字幕分段转换。
- `src/videoflow/models.py`：`Transcript`、`TranscriptSegment` 数据模型与时间范围约束。
- `src/videoflow/exporters.py`：UTF-8 TXT、SRT 和毫秒时间码。
- `src/videoflow/ui.py`：Gradio 展示与临时导出文件管理；不复制转录业务逻辑。
- `src/videoflow/cli.py`：命令行入口。

## 4. 已执行测试与未验证内容

- `python -m pytest ...`：7/7 通过，覆盖时间码进位、TXT/SRT 格式、输入文件/扩展名/模型校验与模拟模型结果转换。
- `python -m compileall -q src app.py`：通过。
- `pip check`：通过。
- `create_app()` 与 `http://127.0.0.1:7860/` 本机启动检查：通过。
- 真实媒体 CLI/界面回调：已通过，见第 2 节。

未验证：Python 3.11 实机、`base`/`small` 在同一媒体上的准确率与耗时、无语音媒体、模型下载失败、损坏媒体以及程序异常退出时临时导出目录的清理。

## 5. 已知限制与待完成事项

- `tiny` 可快速确认流程，但同音字和专业术语误识别明显；它不是高准确率结果的保证。
- V0.1 不含说话人区分、翻译、摘要、在线视频下载、批量队列、数据库、登录、云端 API 或公开分享。
- 首次模型下载需要网络，CPU 处理长视频耗时较长。
- 现阶段没有已知阻断核心链路的 Bug；PyAV 兼容性已通过版本约束修复。
- 未创建 Git 标签或 GitHub Release；这属于发布决策，不是已完成的功能。

## 6. 本轮主要文件

- `pyproject.toml`：依赖、版本和 PyAV 兼容性约束。
- `app.py`、`src/videoflow/`：应用入口、转录、导出、界面、CLI 和数据模型。
- `tests/`：7 项自动化测试。
- `README.md`、`AGENTS.md`、`LICENSE`、`.gitignore`：使用、协作和发布基础文件。
- `docs/PRODUCT.md`、`docs/ROADMAP.md`、`docs/STATUS.md`、`docs/RELEASE_NOTES.md`：产品范围、进度、验证与发布材料。

## 7. 仓库状态

报告生成前，功能基线已推送到 `origin/main`，无未合并分支。交接报告与状态同步将作为文档提交推送；提交后应以 `git status --short --branch` 再次确认工作区干净且 `main` 未领先 `origin/main`。

## 8. 后续开发约束

- 保持 UI、转录和导出层分离；新能力不要把模型调用写入 Gradio 回调以外的业务层重复实现。
- 新模型或媒体后端必须保留结构化 `Transcript`/`TranscriptSegment` 输出，并在全部分段校验完成后再写出导出结果；不要在失败时留下部分不一致文件。
- PyAV 约束 `>=11,<19` 是当前 faster-whisper 1.x 的兼容性要求；升级二者前必须使用真实媒体回归。
- 不引入数据库、账户、云端 API、React、FastAPI、Docker、向量库或付费服务，除非下一轮产品规划明确批准。
- 媒体、模型缓存、导出文件和密钥必须继续保持在 Git 忽略范围；真实验收文件不得提交。

下一轮规划应先基于真实使用反馈选择一个单独的 V0.2 目标，而不是并行加入多个候选功能。
