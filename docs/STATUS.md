# VideoFlow 状态

最后更新：2026-10-16

## 当前状态

- 当前版本：v0.2.0（开发完成，等待用户登录态的 B 站成功导入验收）
- 当前任务：V0.2 版本交接
- 下一任务：用户在本机网页中明确选择已登录 B 站的 Chrome/Edge，完成一次成功已有字幕导入验收；之后再由下一轮产品规划选择一个后续目标。

## 已完成

- 建立 Git 仓库、Python 项目结构、开发约定、产品/路线图/状态文档、MIT 许可证和忽略规则。
- 实现 `faster-whisper` 适配层：文件与模型参数校验、CPU INT8 默认值、语言自动/手动指定、结构化字幕段和可读错误。
- 实现 TXT/SRT 导出、标准毫秒时间码及命令行入口。
- 实现 Gradio 本地界面：上传、模型与语言选择、状态、分段结果、可复制内容及 TXT/SRT 下载。
- 编写无需模型或媒体样本的自动化测试。
- 完成真实媒体验收的依赖兼容性修复：将 PyAV 限定为 `>=11,<19`，避免 PyAV 19 与 faster-whisper 1.x 的解码参数不兼容。
- 准备 v0.1.0 演示说明、依赖许可证核对与发布前清单。
- 将仓库推送并设为公开，生成 `docs/HANDOVER_V0.1.0.md` 供下一轮产品规划使用。
- 新增 B 站单视频已有字幕导入：严格链接校验、45 秒总超时、仅字幕 JSON 下载、BCC 解析、统一导出和明确的登录/本地文件回退提示。
- 将导出文件名规范为跨平台安全格式，避免在线标题中的非法字符导致导出失败。

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
- 2026-10-16 V0.2：加入 `yt-dlp 2026.8.19`。单 BV HTTPS URL 经白名单校验后才交给 yt-dlp；使用 `--skip-download --no-playlist --write-subs --write-auto-subs`，不选择视频格式，并将整个请求限制为 45 秒。离线自动化测试 16/16 通过，Gradio 页面构造通过。
- 2026-10-16 B 站真实无登录请求：公开样本 `https://www.bilibili.com/video/BV1F64y1U7xM` 未返回可访问字幕，应用在超时保护内返回“B 站常要求登录后才能读取字幕；可明确选择 Chrome/Edge 或改用本地文件”的受控错误；未下载完整视频，也未读取浏览器 Cookie。

## 未验证与限制

- 当前机器检测到 Python 3.13，未检测到 Python 3.11；项目声明兼容 Python 3.11–3.13，但尚未在 3.11 实机运行。
- 真实验收使用 `tiny` 模型完成；默认 `base` 与 `small` 模型尚未在该视频上执行完整转录，速度与识别质量仍需按实际需求比较。
- 下载文件仅存放在应用进程的临时目录，退出时清理；程序异常退出时临时目录清理尚未验证。
- B 站已有字幕的**真实成功**导入尚未验收，因为这通常需要用户显式选择其已登录的浏览器会话；应用已覆盖无登录、无字幕、超时和无效 URL 的受控失败路径。
- 西交 LMS 课程回放链接需要学校登录，V0.2 不读取学校账号、不处理课程页面或绕过访问控制；请按课程平台规则获取本地文件。

## Git / 发布

- 本地分支：`main`，跟踪 `origin/main`；已包含 V0.2 B 站字幕导入提交，当前领先远程 1 个提交（精确提交号以 `git log -1 --oneline` 为准）。
- GitHub 远程：`https://github.com/cppppercy/VideoFlow.git`，已公开；本轮新提交尚未推送。尚未创建 Git 标签或 GitHub Release。
- 版本交接报告：`docs/HANDOVER_V0.1.0.md`、`docs/HANDOVER_V0.2.0.md`。后续发布标签或 GitHub Release 仍须负责人明确批准。
