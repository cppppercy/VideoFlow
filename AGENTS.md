# VideoFlow 开发约定

## 范围

- 当前仓库实现本地运行的 VideoFlow；V0.1 仅涵盖本地媒体转录、时间戳预览、TXT/SRT 导出。
- 不要在未收到明确任务时加入登录、云端 API、数据库、在线分享、React、FastAPI、Docker 或后续版本功能。
- 优先采用免费、可离线运行的依赖。网页界面默认仅本机访问，不启用 `share=True`。

## 修改前后

- 先阅读 `docs/PRODUCT.md`、`docs/ROADMAP.md` 与 `docs/STATUS.md`，并保留用户已有改动。
- 转录逻辑放在 `src/videoflow/`；界面层不得复制业务逻辑。
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
