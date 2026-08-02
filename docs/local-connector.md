# 本机提取连接器

生产工作台运行在云服务器，抖音可能拒绝该服务器的匿名请求。本机连接器把公开链接下载、FFmpeg 音频提取和 FunASR 转写都放在访问者自己的电脑上执行：它先尝试匿名下载，失败后按 BaoCut 的行为读取本机浏览器会话重试。浏览器 Cookie 只用于本机到抖音的请求，不会发送到 CPM 或写入工作台服务端。

## 启动

安装 BaoCut 已使用的 `yt-dlp` 后，在仓库根目录运行一次：

```sh
./connector/install-local-connector.sh
```

安装器会在当前 Mac 登录后自动启动连接器。连接器只监听 `127.0.0.1:8765`。默认仅允许本地开发地址和生产工作台 `http://170.106.75.116` 调用；需要增加受信任工作台地址时，设置：

```sh
STILL_SETTLING_CONNECTOR_ORIGINS=https://workbench.example.com ./connector/run-local-connector.sh
```

打开工作台后，提交抖音分享链接只会走本机连接器。视频、音频和 Cookie 在临时目录内使用后立即删除，绝不上传到 CPM。连接器只把文稿和来源链接交给云端；腾讯云 PostgreSQL 保存文稿、分析和 Skill 历史，GitHub 只同步已审核发布的正式 Skill。
