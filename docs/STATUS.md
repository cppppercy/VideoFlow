# VideoFlow 状态

最后更新：2026-10-19

## 当前状态

- 当前版本：v0.4.1（LMS 403 兼容性修复、批量推理预设与界面整理）
- 当前任务：v0.4.1 开发与回归检查已完成，并同步到 GitHub
- 下一任务：用户重启 VideoFlow，在同一已登录 LMS 活动页重新复制短期任务并复验修复后的课程回放。

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
- 新增 Windows 默认扬声器 WASAPI 回环录音：用户确认权限后可手动开始/停止，停止后复用本地转录与 TXT/SRT 导出；原始临时 WAV 在转录后删除，不读取 LMS 或 B 站的链接、账号、Cookie、页面或视频流。
- 将本机临时运行目录置于项目内已忽略的 `.videoflow-runtime/`，避免依赖受限系统临时目录；新增 B 站和本地转录的页面错误文本，避免 Gradio 仅显示无信息的“错误”。
- 新增 B 站独立音频转录：严格使用 `bestaudio`，不以完整视频格式兜底；最多 10 个 BV 链接顺序处理，逐项隔离失败并生成 TXT/SRT ZIP。
- 缓存最近使用的一个 Whisper 模型并串行保护推理，批量任务不再重复加载模型，也不会并发争用普通电脑内存。
- 新增西交 LMS 本地浏览器助手与短期任务适配器：扩展仅有 `lms.xjtu.edu.cn` 页面权限，用户点击后读取单个当前活动；Python 端用短期播放器 token 换取当前账号获准访问的最佳音频回放流，不保存 Cookie、token、Bearer 或签名 URL。
- 保留 Windows 扬声器录音作为最后兼容性兜底；快速路径不要求实时播放，也不受系统其他声音干扰。
- 修复 LMS 媒体提取：当前可用客户端表明 CDN 缺少 `Origin`/`Referer` 会返回 403，且回放使用 `download_url`；现已改为授权直链优先、携带同源请求头，并依次尝试备用地址和其他机位。
- 增加 401、403、404、无音轨、清单/分片失败的安全错误分类；错误不会回显带签名媒体地址。
- 增加快速（tiny/batch 8/beam 1）、均衡（base/batch 4/beam 5）与高精度（small/batch 4/beam 5）转录预设，以及最长 2000 字符的课程关键词提示。
- 将网页顶层入口由五个收敛为“本地文件、在线内容、兼容录音”，并让所有语音识别入口共用转录设置。

## 验证记录

- `python -m pytest --basetemp .tmp-pip\\pytest-v04-final -p no:cacheprovider`：31 项单元测试通过（Python 3.13.7）。
- `python -m compileall -q src app.py`：通过。
- V0.4 `create_app()`：通过；临时启动在 `http://127.0.0.1:7861/` 的页面返回 HTTP 200，随后已停止测试进程；代理环境所需的 `socksio` 已由 `httpx[socks]` 显式安装。
- `python app.py` 本机启动检查：访问 `http://127.0.0.1:7860/` 返回 HTTP 200，随后已停止测试进程；未上传媒体。
- 2026-10-14 独立真实媒体验收准备：虚拟环境已安装 `faster-whisper 1.2.1` 与 `ctranslate2 4.8.3`，但 Hugging Face 缓存中未发现 Whisper 模型；仓库内也没有可用于验收的本地媒体样本。因此未执行真实转录，不能将现有模拟测试表述为真实转录成功。
- 2026-10-14 错误路径检查：CLI 以不存在的 `.wav` 路径运行时返回“找不到本地文件”错误；当前 PowerShell 输出对中文显示为乱码，尚未完成终端中文显示验证。
- 2026-10-14 回归尝试：`pytest` 中不使用临时路径的 3 项导出测试通过；4 项依赖 `tmp_path` 的转录测试在会话收尾时遇到 `PermissionError`（测试临时目录不可访问），未能得到完整本轮回归结果。
- 2026-10-14 真实媒体端到端验收：负责人授权的 `D:/Cai/Videos/屏幕录制/屏幕录制 2026-06-21 104110.mp4` 可被 FFmpeg 识别为 H.264 视频与 AAC 音频，时长 356.331 秒。已下载并成功加载 `tiny` faster-whisper 模型（约 75.5 MB），但尚未产生字幕：`faster-whisper 1.2.1` 调用 `av.open(..., metadata_errors="ignore")` 时，已安装的 `av 19.0.1` 报 `TypeError: open() got an unexpected keyword argument 'metadata_errors'`。`pip check` 未报告依赖断裂，但该真实解码兼容性错误阻断转录、时间戳和 TXT/SRT 下载验收；回调向上抛出带媒体文件名和排查建议的中文 `TranscriptionError`。
- 2026-10-14 兼容性修复与复验：PyAV 19 已移除 `metadata_errors` 参数，故在项目依赖中加入 `av>=11,<19` 并安装 `av 18.1.0`；`pip check` 通过。以同一授权视频执行 `python -m videoflow.cli ... --model tiny --language zh --output-dir exports/acceptance-tiny` 后成功生成 120 段字幕：TXT 3315 B、SRT 7765 B，均可按 UTF-8 读取；SRT 编号连续，120 条时间码均为 `HH:MM:SS,mmm --> HH:MM:SS,mmm`，从 `00:00:00,000 --> 00:00:04,000` 至 `00:05:54,000 --> 00:05:54,800`，文本包含中文。`python -m pytest --basetemp .tmp-pip\\pytest-after-av-pin -p no:cacheprovider`：7 项通过。
- 2026-10-16 V0.2：加入 `yt-dlp 2026.8.19`。单 BV HTTPS URL 经白名单校验后才交给 yt-dlp；使用 `--skip-download --no-playlist --write-subs --write-auto-subs`，不选择视频格式，并将整个请求限制为 45 秒。离线自动化测试 16/16 通过，Gradio 页面构造通过。
- 2026-10-16 B 站真实无登录请求：公开样本 `https://www.bilibili.com/video/BV1F64y1U7xM` 未返回可访问字幕，应用在超时保护内返回“B 站常要求登录后才能读取字幕；可明确选择 Chrome/Edge 或改用本地文件”的受控错误；未下载完整视频，也未读取浏览器 Cookie。
- 2026-10-17 B 站复现：用户提供的 `https://www.bilibili.com/video/BV1j2J46sExN/` 链接格式有效；不读取登录态时，yt-dlp 返回“Subtitles are only available when logged in”，仅列出 `danmaku` XML，未返回可导出的文字字幕。V0.3 页面会显示具体原因；若登录态仍无可访问字幕，可改用播放声音转录。
- 2026-10-17 V0.3：安装 `SoundCard 0.4.6`，已成功枚举当前 Windows 默认扬声器及其回环设备；`python -m pytest --basetemp .tmp-pip\\pytest-v03-real -p no:cacheprovider` 为 21/21 通过，`compileall` 和 `pip check` 通过。回环录音的自动化测试使用伪音频设备，不等同于真实课程声音录制。
- 2026-10-17 V0.4 阶段自动化：31/31 项测试通过；覆盖 B 站纯音频命令、临时音频清理、批量去重和失败隔离、ZIP 导出、LMS 任务严格校验、短期授权交换、最佳音频选择及 UI 权限确认。浏览器助手通过 JavaScript 语法检查，Gradio 页面构造通过。
- 2026-10-17 B 站快速路径真实验收：用户提供的 `https://www.bilibili.com/video/BV1j2J46sExN/` 时长 10 分 44 秒，估算独立音频约 11.8 MB。在不读取 Cookie、不实时播放、不下载完整视频的情况下完成音频提取；`tiny` 模型识别为中文并生成 147 个分段，临时音频在工作流结束后清理。
- 2026-10-17 V0.4.1 自动化：36/36 项测试通过；新增覆盖 LMS `download_url` 优先级、同源请求头、备用地址重试、403 错误脱敏、批量推理参数及词级字幕重分段。`compileall`、`pip check`、浏览器助手 JavaScript 语法及改版 Gradio 页面构造通过；临时启动 `http://127.0.0.1:7862/` 返回 HTTP 200 后已停止测试进程。
- 2026-10-17 批量推理真实复验：同一段经授权的 5 分 56 秒中文视频上，快速档输出 48 段、1112 字符并耗时 14.46 秒，最长分段 8 秒；旧版 tiny/beam 5 输出 1133 字符并耗时 37.52 秒，快速档约为 2.6 倍速度。均衡档在最终分段上限调整前输出 1087 字符并耗时 33.02 秒。字符数不能证明准确率，关键词和术语仍需人工抽查。
- 2026-10-17 LMS 用户复现与修复：用户实际进入音频提取阶段后失败。对照当前仍可播放回放的开源客户端发现其明确为回放 CDN 添加 LMS `Origin`/`Referer`，并用 `download_url` 播放；旧实现使用 `play_url` 且没有同源头，符合 HTTP 403 表现。修复后尚未使用用户的短期任务复验，不能描述为真实成功。
- 2026-10-19 发布前回归：`python -m pytest --basetemp .tmp-pip\pytest-push-final-escalated -p no:cacheprovider` 共 36/36 项通过；`python -m compileall -q src app.py`、`python -m pip check`、浏览器助手 JavaScript 语法检查及 `git diff --check` 均通过。首次受限沙箱内运行因 Windows 临时目录权限失败，改为项目环境在沙箱外重跑后通过，未发现功能断言失败。

## 未验证与限制

- 当前机器检测到 Python 3.13，未检测到 Python 3.11；项目声明兼容 Python 3.11–3.13，但尚未在 3.11 实机运行。
- 真实验收使用 `tiny` 模型完成；默认 `base` 与 `small` 模型尚未在该视频上执行完整转录，速度与识别质量仍需按实际需求比较。
- 下载文件仅存放在应用进程的临时目录，退出时清理；程序异常退出时临时目录清理尚未验证。
- B 站已有字幕的**真实成功**导入尚未验收，因为这通常需要用户显式选择其已登录的浏览器会话；应用已覆盖无登录、无字幕、超时和无效 URL 的受控失败路径。
- 西交 LMS 页面需要学校登录；V0.4.1 已根据用户真实失败修复媒体字段和请求头，但修复后的真实登录态成功结果仍待用户复验，平台 API 变化也可能需要继续适配。
- V0.3 的 Windows 回环录音尚未用真实课程/B 站播放声音完成端到端验收；不同耳机、蓝牙设备、驱动、静音状态或系统默认输出设备可能影响录音。录制会采集当前默认扬声器的全部系统声音，用户应关闭通知与其他播放内容。
- B 站已有字幕导入仍只适用于平台向所选已登录浏览器会话返回的已有文字字幕；它不转录或下载 B 站视频。无已有字幕时应优先使用 B 站独立音频转录；播放声音录制仅作兼容性兜底。
- B 站批量音频任务按顺序处理而非同时推理；这样可以自动处理多个链接，同时避免普通电脑因多个 Whisper 模型并发而耗尽内存。
- LMS 快速路径会让 FFmpeg 读取当前账号获准播放的媒体并只写出临时音频；若平台只提供音视频复用流，网络传输可能仍包含视频数据，但不会生成或保留完整视频文件。

## Git / 发布

- 本地分支：`main`，跟踪 `origin/main`；V0.2 至 V0.4.1 代码及本状态更新已于 2026-10-19 推送并与远程同步（精确提交号以 `git log -1 --oneline` 为准）。
- GitHub 远程：`https://github.com/cppppercy/VideoFlow.git`，已公开。尚未创建 Git 标签或 GitHub Release。
- 版本交接报告：`docs/HANDOVER_V0.1.0.md`、`docs/HANDOVER_V0.2.0.md`。后续发布标签或 GitHub Release 仍须负责人明确批准。
