# 📰 动态

如果你是通过付费购买本程序，请立即退款并举报。此项目是免费、开源的。

## 💻 分辨率

- 本项目以1280x720为测试基准，理论适配市面上主流的分辨率。如遇到识别问题优先更新MaaWoA，次之调整分辨率为1280x720。Android端在后台分辨率模式选择16:9。

## 📱 Android端后台模式分辨率

1. 在停止任务后切换分辨率再开始任务可能会因为缓存遗留问题导致识别失败，缓存依赖Agent服务，Agent只有在启动MaaWoA时进行初始化。
2. 切换后台模式分辨率后应先关闭MaaWoA及后台进程，然后重新启动。

## 🍎 IOS控制器（试验）

- 内置 xdb 客户端 SDK 为 1.6.1。iOS 连接和 Toolkit 设备发现要求 xdb Server 1.6.0 或更新版本。客户端在建连时检查运行中的 Server 版本，旧版本或无法识别的版本会提示升级。
- 桌面端请先按 [XDeviceBridge 安装说明](https://github.com/scrctl/XDeviceBridge/blob/main/docs/INSTALL_zh.md) 安装对应系统和架构的完整运行包，可从 [GitHub Releases](https://github.com/scrctl/XDeviceBridge/releases) 获取。

## 🖥 桌面端前台控制器注意事项以及常见问题

1. 前台控制器在运行过程中会完全占用前台，此时手动操作会干扰脚本正常运行，不建议同时打开其他软件。
2. 截图功能是直接截取当前前台窗口的画面，因此截图中不能出现任何遮挡物，例如帧率显示、广告弹窗、Windows未激活标识等，否则会影响识别。

## 🖥 桌面端后台控制器注意事项以及常见问题

- 后台控制器在运行过程可完全后台操作，不会抢夺鼠标控制权，但需要目标程序支持，并且后台控制器有被捕获操作的可能。

## ⚖️ 授权

- 本软件的使用需遵守 [GNU Affero General Public License v3.0 (AGPL-3.0)](https://github.com/huzesama/MaaWoA/blob/main/LICENSE)

## ☕ 请我们喝咖啡

如果 MaaWoA 帮你省下了不少时间，不妨[请开发者喝杯咖啡](https://ifdian.net/a/venmzvi)？你的支持是我们持续更新的最大动力！💖
