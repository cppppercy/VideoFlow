# VideoFlow 开发约定

## 范围

- 当前仓库实现本地运行的 VideoFlow；V0.4.2 包含本地媒体转录、B 站已有字幕导入、B 站独立音频流批量转录、西交 LMS 已授权回放的短期任务转录，以及 Windows 扬声器声音录制兜底、可选 NVIDIA GPU turbo 增强、长媒体诊断、自然段 TXT、时间戳预览和 SRT 导出。
- 不要在未收到明确任务时加入账号系统、Cookie 管理、云端 API、数据库、在线分享、React、FastAPI、Docker 或后续版本功能。
- 优先采用免费、可离线运行的依赖。网页界面默认仅本机访问，不启用 `share=True`。

## 修改前后

- 先阅读 `docs/PRODUCT.md`、`docs/ROADMAP.md` 与 `docs/STATUS.md`，并保留用户已有改动。
- 转录逻辑放在 `src/videoflow/`；界面层不得复制业务逻辑。
- 在线字幕来源放在 `src/videoflow/sources/`。只允许经过严格校验的平台 URL；不得下载完整视频、绕过 DRM 或访问控制。
- B 站音频转录只允许 `bestaudio`，不得回退到完整视频格式。西交 LMS 仅接受本地浏览器助手在用户明确点击后生成的短期任务；不得读取、保存、打印或提交账号、密码、Cookie、播放器 token、Bearer token 或带签名的播放 URL。
- 播放声音录制逻辑放在 `src/videoflow/system_audio.py`；只记录用户本机默认扬声器正在播放的声音，必须在界面确认记录权限后手动启停，且不得读取课程链接、账号、Cookie 或视频流。
- 浏览器 Cookie 只能在用户于界面中明确选择浏览器后交给底层工具临时读取；不得保存、导出、打印或提交 Cookie。
- `browser-extension/` 只允许访问 `https://lms.xjtu.edu.cn/*`，只在用户点击后复制单个当前活动的短期任务，不得后台抓取、批量遍历或持久化登录信息。
- 新功能应具有可离线运行的单元测试；模拟测试不得写成真实模型或真实媒体验证。
- 完成一个任务后，运行相关测试，检查 `git diff`，并如实更新 `docs/STATUS.md`。

## 常用命令

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python app.py
python -m videoflow.cli path\\to\\media.mp4 --model base --language zh
```

## 发布与安全

- 不主动推送、公开仓库、创建 Release、删除用户媒体或进行付费操作。
- 不提交媒体文件、模型缓存、导出结果、密钥或 `.env`。
