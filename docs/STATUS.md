# VideoFlow 状态

最后更新：2026-10-19

## 当前状态

- 当前版本：v0.4.3（GPU 自适应批量、显存诊断、可疑分段标记与可选精修）
- 当前任务：完成 v0.4.3 回归、实际 GPU 基准和 Git 同步；FunASR/SenseVoice/Paraformer 仅在隔离环境中评估，不替换已验证的默认路径。
- 下一任务：使用 2–3 分钟真实课程人工参考稿，比较 turbo 默认/精修、SenseVoice 和 Paraformer 的 CER、术语命中、时间戳质量、速度与资源，再决定是否新增可选中文后端。

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
- 增加快速（base/CPU）、均衡（base/CPU）、GPU 增强（turbo/CUDA FP16）与高精度（small/CPU）转录预设，以及最长 2000 字符的课程术语热词提示。
- 将网页顶层入口由五个收敛为“本地文件、在线内容、兼容录音”，并让所有语音识别入口共用转录设置。
- 新增长媒体稳定路径：20 分钟以上不再为整段音频预先堆叠批量特征，改为带 3 秒上下文的 5 分钟分块、块内批量识别；该阈值只是管线切换点，不是媒体时长上限。
- CPU 模型显式使用最多 8 个推理线程，避免 CTranslate2 默认线程数在本机 24 逻辑处理器上利用不足；快速档关闭多温度回退，使困难音频的耗时更可预测。可用 `VIDEOFLOW_CPU_THREADS=1..32` 做有依据的本机调优。
- 新增媒体时长、VAD 语音时长、末条字幕时间、模型加载/推理/总耗时、CPU 时间、RTF、进程峰值内存和管线类型诊断；Gradio 进度条按实际字幕时间推进。
- 对媒体末尾存在大范围未覆盖的结果标记为“需检查”，不再直接宣称完整成功；保留结果供用户区分尾部静音与真实遗漏。
- TXT 与 SRT 分离排版：TXT 合并时间片、保留已有标点并按可靠停顿/句末生成自然段；SRT 时间轴不变，本地、B 站、LMS、录音和批量 ZIP 统一生效。
- 新增 `videoflow-benchmark`：在同一媒体上记录加载时间、推理时间、RTF、峰值内存、末条字幕和覆盖状态；仅在提供人工参考稿时计算 CER。
- 完成 `docs/TRANSCRIPTION_DIAGNOSIS.md`、`docs/ASR_BENCHMARK.md`、v0.4.2 发布说明与交接摘要；未加入尚无 CER 证据的 FunASR、SenseVoice 或 whisper.cpp 强制依赖。

## 验证记录

- 2026-10-19 v0.4.3 开发中：新增本进程 GPU 显存探测、8 GB 显存下的保守批量 8、CUDA OOM 分级回退、热词标准化、模型启发式复核提示和最多 12 段的可选高 beam 精修；新增单元测试覆盖批量选择、OOM 回退、热词去重、低置信标记和候选接受规则。精修依据模型内部概率与重复指标，不是 CER。
- 2026-10-19 v0.4.3 回归：`python -m pytest --basetemp .tmp-pip\pytest-v043-full -p no:cacheprovider` 为 65/65 通过；`compileall`、`pip check`、浏览器助手 JavaScript 语法、Gradio `create_app()` 与 `git diff --check` 通过。临时 4 秒正弦音频在 GPU turbo 上实际选择批量 8、识别 0.5 秒、RTF 0.124、识别为无语音并正确报告 RTX 4060 名称；任务太短，驱动未暴露可采样的当前进程峰值显存，故该单次未得到显存数值。
- 2026-10-19 中文替代引擎可行性检查：在隔离 Python 3.9 环境中成功导入 FunASR 1.3.1、PyTorch CPU 与 torchaudio；官方 SenseVoiceSmall 权重下载约 893 MB，未在本轮完成，也尚未验证可与 VideoFlow 时间戳/SRT 结构兼容。隔离环境约 1.7 GB，已删除；未加入项目依赖、未接入网页，也未将其描述为可用功能。

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
- 2026-10-19 v0.4.2 自动化回归：47/47 项通过，新增自然段 TXT、中英数字连接、空文本、长媒体管线选择、时长探测、可疑尾部状态及 CER 测试；原有 B 站、LMS、回环录音、ZIP 和 SRT 测试继续通过。
- 2026-10-19 v0.4.2 静态与界面检查：`python -m compileall -q src app.py`、`python -m pip check`、浏览器助手 `node --check`、`git diff --check` 及 Gradio `create_app()` 均通过。
- 2026-10-19 Windows 启动复验：当前 `.venv` 包含可用的 `Scripts/python.exe`，但没有 `Activate.ps1`；README 已统一改为直接调用虚拟环境解释器。使用 `.\.venv\Scripts\python.exe app.py` 临时启动后，`http://127.0.0.1:7860/` 返回 HTTP 200，测试进程随后已停止。
- 2026-10-19 本机短媒体基准：同一授权 356.33 秒中文视频，fast/tiny 批量管线推理 25.24 秒、RTF 0.071、峰值约 739.8 MB、最后字幕 354.86 秒；原始 tiny 标准管线推理 74.68 秒、RTF 0.210、峰值约 475.1 MB、最后字幕 355.36 秒。没有人工参考稿，因此 CER 未测，不能宣称准确率提升。
- 2026-10-19 长媒体技术验证：用授权媒体的 10 秒音频在本机忽略目录构造 3900 秒稀疏语音 FLAC，语音分布跨越 0–64:45；fast/tiny 自动使用 `long-media` 管线，40.02 秒完成，峰值约 1070.8 MB，最后字幕 3894.77 秒，未在 30 分钟截断。该样本不是连续课程，不能代替学校回放验收。
- 2026-10-19 用户长任务现场诊断：旧 `long-media` 路径在 i7-14650HX 上运行约 41 分钟后，5 秒采样仅增加 0.05 CPU 秒，进程仍在但已近乎不工作；这不属于正常的 `tiny/快速` 转录速度。未读取或输出进程命令行、LMS token 或签名地址。
- 2026-10-19 长媒体加速回归：长媒体改为 `chunked-batched`，每块 5 分钟并带 3 秒上下文，字幕按中点归属去重。加入 LMS 提取进度回归后，全量 `pytest` 为 51/51 通过；`compileall`、`pip check`、浏览器助手 JavaScript 语法及 Gradio 页面构造通过。
- 2026-10-19 本机加速实测：i7-14650HX、8 CPU 推理线程。356.33 秒授权中文视频的 fast/tiny 为 8.63 秒、RTF 0.024、峰值约 726.5 MB；balanced/base 为 35.87 秒、RTF 0.101、峰值约 619.8 MB。3900 秒稀疏样本为 14.26 秒、RTF 0.004、峰值约 391.7 MB；3600 秒连续有声重复样本为 60.66 秒、RTF 0.017、峰值约 815.4 MB，最后字幕到 3600 秒。两种长样本都由授权媒体构造，不等于真实课程准确率或 LMS 登录态验收。
- 2026-10-19 LMS 提取进度修复：用户真实任务在 FFmpeg 提取阶段运行约 120 秒时页面始终显示 0%，但现场进程仍在工作且之后正常退出；根因是同步 `subprocess.run` 没有向 Gradio 转发 FFmpeg 进度。现改为逐行解析 `Duration`/`out_time`，每秒显示已处理媒体时间，有总时长时显示百分比；只保留脱敏错误类别，不保存或回显签名 URL/token。相关测试与 10 秒本地 FFmpeg 实测通过。
- 2026-10-19 中文质量修复：用户提供的真实课程结果包含繁简混杂、“们们们”和长串短语重复，以及大量专业词错听，证明 tiny 快速稿不足以满足该课程。快速档改为 base/beam 1；所有预设增加重复惩罚、3-gram 禁复读和静音幻觉阈值。新增 OpenCC 本地 `t2s` 后处理，中文预览、TXT、SRT 和 B 站字幕统一输出简体；连续 4 次以上的相同汉字/短语只做保守压缩，不尝试臆造被错听的原文。
- 2026-10-19 质量修复速度复验：同一 356.33 秒授权视频上，新 fast/base/beam 1 推理 9.83 秒、RTF 0.028、峰值约 964.1 MB；balanced/base/beam 5 推理 14.5 秒、RTF 0.041。未提供人工参考稿，不能用主观抽查或字符数宣称 CER 提升；small 高精度仍待首次下载和真实课程比较。
- 2026-10-19 中文质量修复回归：56/56 项自动化测试通过；新增繁转简、重复压缩、B 站繁体字幕转简体和非中文不转换测试。`compileall`、`pip check`、浏览器助手 JavaScript 语法及 `git diff --check` 均通过。
- 2026-10-19 base 质量复查：用户第二份真实课程结果仍有大量“方程组、残值、真解、高斯消去法、舍入误差”等系统性同音误识别，说明 base 的模型容量仍是主要限制，繁转简和重复后处理不能修复错听。
- 2026-10-19 GPU 增强实现与实测：检测到本机 RTX 4060 Laptop 8 GB；安装可选 NVIDIA 官方 `nvidia-cublas-cu12 12.6.4.1` 与 `nvidia-cudnn-cu12 9.5.0.50` 后，turbo/beam 5/FP16 在同一 356.33 秒授权中文视频上推理 6.07 秒、RTF 0.017、进程峰值约 1765.9 MB，最后字幕 354.7 秒。术语提示改用 faster-whisper `hotwords`，不再使用可能污染第一窗口的 `initial_prompt`。无人工参考稿，不能宣称具体 CER 提升。
- 2026-10-19 GPU 增强回归：59/59 项自动化测试通过；覆盖 GPU 预设参数、缺少 CUDA 时的受控错误和 UI 预设声明。完整静态检查见本轮结束记录。
- 2026-10-19 GPU 增强最终检查：`python -m compileall -q src app.py`、`python -m pip check`、浏览器助手 `node --check`、`git diff --check` 与 Gradio `create_app()` 均通过；页面实测默认值为 `gpu_turbo`，并同时保留 fast、balanced、accurate 选项。

## 未验证与限制

- 当前机器检测到 Python 3.13，未检测到 Python 3.11；项目声明兼容 Python 3.11–3.13，但尚未在 3.11 实机运行。
- 真实基准已运行 tiny、base 和 GPU turbo 的部分配置，但没有人工参考稿，无法计算 CER；`small` 未缓存，SenseVoiceSmall、FunASR/Paraformer 和 whisper.cpp 未安装或验证。
- 65 分钟稀疏样本和 60 分钟连续有声重复样本均已验证速度、内存和末尾覆盖；60–90 分钟连续**真实课程**的准确率、LMS 提取和完整性仍待用户验收。
- 覆盖检查只能发现明显的末尾差距，不能自动判断差距来自长尾静音还是漏转；状态为“需检查”时必须人工查看音轨。
- 下载文件仅存放在应用进程的临时目录，退出时清理；程序异常退出时临时目录清理尚未验证。
- B 站已有字幕的**真实成功**导入尚未验收，因为这通常需要用户显式选择其已登录的浏览器会话；应用已覆盖无登录、无字幕、超时和无效 URL 的受控失败路径。
- 西交 LMS 页面需要学校登录；V0.4.1 已根据用户真实失败修复媒体字段和请求头，但修复后的真实登录态成功结果仍待用户复验，平台 API 变化也可能需要继续适配。
- V0.3 的 Windows 回环录音尚未用真实课程/B 站播放声音完成端到端验收；不同耳机、蓝牙设备、驱动、静音状态或系统默认输出设备可能影响录音。录制会采集当前默认扬声器的全部系统声音，用户应关闭通知与其他播放内容。
- B 站已有字幕导入仍只适用于平台向所选已登录浏览器会话返回的已有文字字幕；它不转录或下载 B 站视频。无已有字幕时应优先使用 B 站独立音频转录；播放声音录制仅作兼容性兜底。
- B 站批量音频任务按顺序处理而非同时推理；这样可以自动处理多个链接，同时避免普通电脑因多个 Whisper 模型并发而耗尽内存。
- LMS 快速路径会让 FFmpeg 读取当前账号获准播放的媒体并只写出临时音频；若平台只提供音视频复用流，网络传输可能仍包含视频数据，但不会生成或保留完整视频文件。

## Git / 发布

- 本地分支：`main`，跟踪 `origin/main`；v0.4.2 主实现已于 2026-10-19 以提交 `32c23a3` 推送，状态同步提交随后推送。
- GitHub 远程：`https://github.com/cppppercy/VideoFlow.git`，已公开并包含 v0.4.2 当前进度。尚未创建 v0.4.2 Git 标签或 GitHub Release。
- 版本交接报告：`docs/HANDOVER_V0.1.0.md`、`docs/HANDOVER_V0.2.0.md`。后续发布标签或 GitHub Release 仍须负责人明确批准。
