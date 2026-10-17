# VideoFlow 开发约定

## 范围

- 当前仓库实现本地运行的 VideoFlow；V0.3 包含本地媒体转录、B 站单视频可访问的已有字幕导入，以及用户正常播放时的 Windows 扬声器声音录制转写、时间戳预览和 TXT/SRT 导出。
- 不要在未收到明确任务时加入账号系统、Cookie 管理、云端 API、数据库、在线分享、React、FastAPI、Docker 或后续版本功能。
- 优先采用免费、可离线运行的依赖。网页界面默认仅本机访问，不启用 `share=True`。

## 修改前后

- 先阅读 `docs/PRODUCT.md`、`docs/ROADMAP.md` 与 `docs/STATUS.md`，并保留用户已有改动。
- 转录逻辑放在 `src/videoflow/`；界面层不得复制业务逻辑。
- 在线字幕来源放在 `src/videoflow/sources/`。只允许经过严格校验的平台 URL；不得下载完整视频、绕过 DRM 或访问控制。
- 播放声音录制逻辑放在 `src/videoflow/system_audio.py`；只记录用户本机默认扬声器正在播放的声音，必须在界面确认记录权限后手动启停，且不得读取课程链接、账号、Cookie 或视频流。
- 浏览器 Cookie 只能在用户于界面中明确选择浏览器后交给底层工具临时读取；不得保存、导出、打印或提交 Cookie。
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
