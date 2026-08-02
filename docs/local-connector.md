# 本机提取连接器（兼容旧方案）

当前生产主路径不依赖本机提取连接器。CPM 工作台会在同一台服务器上调用 `yt-dlp` 下载公开媒体、调用已配置的外部音频转写 API，并在任务结束后删除媒体文件；网页用户不需要安装 Python、yt-dlp、BaoCut 或登录抖音。

本连接器保留给本机开发和服务器出口被平台临时限制时的兼容排障使用。它不再是网页提交链接的默认路径，也不应作为生产工作台的必装前置条件。

## 启动

安装 BaoCut 已使用的 `yt-dlp` 后，在仓库根目录运行一次：

```sh
./connector/install-local-connector.sh
```

安装器会在当前 Mac 登录后自动启动连接器。连接器只监听 `127.0.0.1:8765`。默认仅允许本地开发地址和生产工作台 `http://170.106.75.116` 调用；需要增加受信任工作台地址时，设置：

```sh
STILL_SETTLING_CONNECTOR_ORIGINS=https://workbench.example.com ./connector/run-local-connector.sh
```

仅在本机调试旧接口时才会使用该连接器。生产链接任务不会将下载的视频回传浏览器或长期保存在服务器上。
