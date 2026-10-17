# VideoFlow LMS 助手

该本地浏览器扩展只在 `https://lms.xjtu.edu.cn/course/*/learning-activity*` 页面运行。用户点击按钮后，它使用当前已登录页面的正常权限读取活动和播放器地址，并将一次性短期任务复制到剪贴板。

它不会读取、导出或保存浏览器 Cookie、学校账号或密码，也不会后台批量访问课程。任务中包含短期播放器 token，请只粘贴到本机运行的 VideoFlow，并在处理后清空剪贴板。

## Edge 安装

1. 打开 `edge://extensions`。
2. 打开“开发人员模式”。
3. 点击“加载解压缩的扩展”，选择本目录 `browser-extension`。
4. 登录 LMS 并进入具体学习活动页面，点击右下角“复制到 VideoFlow”。

## Chrome 安装

打开 `chrome://extensions`，其余步骤相同。
