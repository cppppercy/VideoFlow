# VideoFlow

VideoFlow 是一个优先本地运行的视频/音频转文字工具。V0.1 提供媒体转录、带时间戳的结果预览，以及 UTF-8 TXT、标准 SRT 字幕导出。

它面向希望快速获取视频内容的个人用户，也为后续学习整理、课程内容提取等能力保留扩展空间。不会上传媒体到服务器，也不会默认开启公网分享。

## 功能

- 使用 `faster-whisper` 转录本地音频和常见视频文件
- 默认 CPU `int8` 推理；可选 tiny、base、small 模型
- 自动识别语言，也可指定中文、英文、日文或韩文
- 网页中查看每段开始/结束时间与文字
- 导出 UTF-8 编码 TXT 和标准 SRT
- 命令行入口，便于排查和自动化使用

## 安装

需要 Python 3.11–3.13 和已安装的 [FFmpeg](https://ffmpeg.org/)（本机已经能在命令行执行 `ffmpeg -version`）。首次转录会下载所选 Whisper 模型；模型大小和耗时随模型选择及机器性能变化。

```powershell
git clone <你的 GitHub 仓库地址>
cd VideoFlow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 使用

启动本地网页：

```powershell
python app.py
```

浏览器打开终端显示的本机地址，上传媒体、选择模型和语言，然后下载 TXT 或 SRT。界面不会设置 `share=True`。

也可以命令行转录：

```powershell
videoflow "D:\\media\\lecture.mp4" --model base --language zh --output-dir exports
```

未传 `--language` 时自动识别语言。模型不可用、FFmpeg 无法解码或文件不是有效媒体时，程序会给出可读错误信息。

## 测试

```powershell
python -m pytest
```

这些是无需下载模型或准备媒体的单元测试，覆盖 SRT/TXT、时间码、输入校验和转录结果转换。真实转录仍需用户在本机准备有授权的媒体样本执行验收。

## 已知限制

- V0.1 没有说话人区分、字幕翻译、在线视频下载或批量队列。
- CPU 转录速度受电脑性能和模型大小影响；`base` 是普通电脑上的默认平衡选择。
- 模型首次下载需要网络；之后可从本地缓存使用。

更多规划和当前验证状态见 `docs/`。
