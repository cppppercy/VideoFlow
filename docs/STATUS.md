# VideoFlow 状态

最后更新：2026-10-14

## 当前状态

- 当前版本：v0.1.0（功能实现与首次真实媒体验收已完成）
- 当前任务：T04 GitHub 发布准备
- 下一任务：负责人审阅发布材料并决定是否创建标签或 GitHub Release；之后再根据真实使用反馈决定是否为 V0.2 选择单一功能。

## 已完成

- 建立 Git 仓库、Python 项目结构、开发约定、产品/路线图/状态文档、MIT 许可证和忽略规则。
- 实现 `faster-whisper` 适配层：文件与模型参数校验、CPU INT8 默认值、语言自动/手动指定、结构化字幕段和可读错误。
- 实现 TXT/SRT 导出、标准毫秒时间码及命令行入口。
- 实现 Gradio 本地界面：上传、模型与语言选择、状态、分段结果、可复制内容及 TXT/SRT 下载。
- 编写无需模型或媒体样本的自动化测试。
- 完成真实媒体验收的依赖兼容性修复：将 PyAV 限定为 `>=11,<19`，避免 PyAV 19 与 faster-whisper 1.x 的解码参数不兼容。
- 准备 v0.1.0 演示说明、依赖许可证核对与发布前清单。

## 验证记录

- `python -m pytest --basetemp .tmp-pip\\pytest-run-3 -p no:cacheprovider`：7 项单元测试通过（Python 3.13.7）。
- `python -m compileall -q src app.py`：通过。
- `create_app()`：通过；代理环境所需的 `socksio` 已由 `httpx[socks]` 显式安装。
- `python app.py` 本机启动检查：访问 `http://127.0.0.1:7860/` 返回 HTTP 200，随后已停止测试进程；未上传媒体。
- 2026-10-14 独立真实媒体验收准备：虚拟环境已安装 `faster-whisper 1.2.1` 与 `ctranslate2 4.8.3`，但 Hugging Face 缓存中未发现 Whisper 模型；仓库内也没有可用于验收的本地媒体样本。因此未执行真实转录，不能将现有模拟测试表述为真实转录成功。
- 2026-10-14 错误路径检查：CLI 以不存在的 `.wav` 路径运行时返回“找不到本地文件”错误；当前 PowerShell 输出对中文显示为乱码，尚未完成终端中文显示验证。
- 2026-10-14 回归尝试：`pytest` 中不使用临时路径的 3 项导出测试通过；4 项依赖 `tmp_path` 的转录测试在会话收尾时遇到 `PermissionError`（测试临时目录不可访问），未能得到完整本轮回归结果。
- 2026-10-14 真实媒体端到端验收：负责人授权的 `D:/Cai/Videos/屏幕录制/屏幕录制 2026-06-21 104110.mp4` 可被 FFmpeg 识别为 H.264 视频与 AAC 音频，时长 356.331 秒。已下载并成功加载 `tiny` faster-whisper 模型（约 75.5 MB），但尚未产生字幕：`faster-whisper 1.2.1` 调用 `av.open(..., metadata_errors="ignore")` 时，已安装的 `av 19.0.1` 报 `TypeError: open() got an unexpected keyword argument 'metadata_errors'`。`pip check` 未报告依赖断裂，但该真实解码兼容性错误阻断转录、时间戳和 TXT/SRT 下载验收；回调向上抛出带媒体文件名和排查建议的中文 `TranscriptionError`。
- 2026-10-14 兼容性修复与复验：PyAV 19 已移除 `metadata_errors` 参数，故在项目依赖中加入 `av>=11,<19` 并安装 `av 18.1.0`；`pip check` 通过。以同一授权视频执行 `python -m videoflow.cli ... --model tiny --language zh --output-dir exports/acceptance-tiny` 后成功生成 120 段字幕：TXT 3315 B、SRT 7765 B，均可按 UTF-8 读取；SRT 编号连续，120 条时间码均为 `HH:MM:SS,mmm --> HH:MM:SS,mmm`，从 `00:00:00,000 --> 00:00:04,000` 至 `00:05:54,000 --> 00:05:54,800`，文本包含中文。`python -m pytest --basetemp .tmp-pip\\pytest-after-av-pin -p no:cacheprovider`：7 项通过。

## 未验证与限制

- 当前机器检测到 Python 3.13，未检测到 Python 3.11；项目声明兼容 Python 3.11–3.13，但尚未在 3.11 实机运行。
- 真实验收使用 `tiny` 模型完成；默认 `base` 与 `small` 模型尚未在该视频上执行完整转录，速度与识别质量仍需按实际需求比较。
- 下载文件仅存放在应用进程的临时目录，退出时清理；浏览器关闭或进程异常退出时的临时目录清理尚需真实界面验收。

## Git / 发布

- 本地分支：`main`，已跟踪 `origin/main`（提交号以 `git log -1 --oneline` 为准）。
- GitHub 远程：`https://github.com/cppppercy/VideoFlow.git`，已推送；未经负责人确认不公开仓库、不创建 Release。
- 建议发布标签：`v0.1.0`，前提是完成真实媒体验收、确认 README 截图/演示并审查待提交文件。
