# F4CP

[开发与交付流程](../CH32V208RBT6/docs/开发与交付流程.md) 固定硬件、版本、配对恢复、验证与交付规则。
协作约束见 `AGENTS.md`。从固件目录运行 `python tools/release_check.py --scope desktop --package`
可统一执行上位机测试与打包。

F4CP 是 UF4 数字电源的 Windows 上位机。本版配合 CH32V208RBT6 固件，通过 BLE 完成设备连接、基础通信和 W25Q256 备用区固件 OTA。

界面保留四页：**首页、软件更新、设置、个人**。旧串口、设备参数、电源仪表、DAPLink 和电池页面已删除。

## 安装和运行

需要 Windows、Python 3.15 与 UV。项目已将 **清华国内镜像**设为 UV 默认源：

```powershell
uv sync
uv run python start.py
```

首次连接：在首页扫描 **UF4 Power V208**，连接时按 Windows 提示输入 **005213**。
连接后显示设备实际固件版本；读取设备信息可检查 W25Q256 的 JEDEC、32MiB 容量和用户区。
Flash 未识别时禁用升级并提示接线，上传前会再次查询确认，避免进入擦除后才报错误 5。
实际接线为 PB3=CLK、PB4=MISO、PB5=MOSI、PD2=/CS；0.1.0 起 Flash 使用 GPIO SPI，硬件 SPI1 用于 SWD。
0.1.0 同时更新 Boot 与应用，通过有线烧录完整 factory.hex 安装本版。

连接后会通过版本和 OTA 状态两次受保护读取确认安全链路。遇到 ATT 0x05（认证不足）或
0x0F（尚未加密）时，最多等待 25 秒；其他错误立即报告，不重放 OTA 写入命令。
如果刷机后出现 `Insufficient Authentication`，先留意 Windows 配对提示并输入 `005213`。
若仍失败，保持设备供电，在设备列表选中它并点击“重新配对”：仅清除该设备在电脑上的旧绑定，
然后重新配对和验证身份。普通连接和超时不会自动删除绑定。
Windows 使用独立的 WinRT 后端扩展处理 `PROVIDE_PIN` 事件，自动提交板端固定口令 `005213`，
仅请求认证加密配对，不回退到 Just Works；解决当前 Bleak 默认后端只接受 `CONFIRM_ONLY` 的兼容问题。
配对事件注册在结束、失败、取消或超时时均会移除。配对修复仅影响上位机，独立于固件版本递增。
通信框支持十六进制请求/响应，例如 `01 55 AA` 回显，`00` 查询信息。

固件 0.1.2 起，首页“设备通信”提供 **USB诊断**：通过安全 BLE 连接读取 USB 枚举计数、
寄存器和最近 SETUP，在下方日志框显示可复制的文本，无需串口或 USB 枚举成功。
固件 0.1.3 会先让 USB 独立枚举约3秒，再启动 BLE；新版诊断会同时显示 BLE 启动前冻结快照和当前状态。
保持 USB 连接并重启应用后读取；诊断不会清计数、复位 USB 或改写 Flash。
0.1.1 不支持此命令，需先安装诊断固件；0.1.2 仍兼容读取三页当前状态。
详见 [无串口诊断](../CH32V208RBT6/docs/USBFS-DAP.md)。
本功能用于定位代码 43，目前尚未确认实板枚举根因与修复效果。
固件 0.1.4 新增接收分类、DMA 地址读回和首个 TRANSFER 事件；诊断仍兼容 0.1.2/0.1.3。
本次 0.1.4 配套 EXE 位于 `build/exe-usb014/F4CP.exe`，需保留整个目录。
已有上位机仍在运行，保留其目录，使用独立输出目录重新打包。

## 固件 OTA

首次通过有线烧录 `../CH32V208RBT6/build/UF4_CH32V208_factory.hex`；此后首页选择
`UF4_CH32V208.ota`，确认包内版本后开始升级。

上位机会检查目标芯片、布局、入口、包长及两级 CRC，按实际 MTU 传输，显示上传进度、速度和剩余时间。
支持提交前取消；设备校验完成后提交、重启，随后自动重连核对**运行版本、长度和 CRC32**，全部匹配才报告成功。
上传进度最多先到 95%，安装确认完成后到 100%。
优先使用无响应写连续发送，每组最多 4 包后读取设备确认偏移；丢包自动从确认位置重传，连续失败限次中止。
包长取设备 MTU、电脑 MTU 与 Windows 实际无响应写限制的共同上限，最大 236 字节固件数据/包；
擦除后刷新协商结果，界面显示发送模式、包长和实际上传速度。旧固件明确不支持快速模式时回退逐包确认。
配套固件按 **32MHz 外部晶振、96MHz 系统时钟**构建，并主动申请 **2M PHY、7.5ms 间隔、零延迟、MTU 247**。
最终链路参数由电脑蓝牙适配器协商决定；2Mbps PHY 速率不等于实际 OTA 写入速率。
提交后不能取消；如果重连超时，明确显示安装未确认，可手动连接核对，必要时重新上电。

[固件接线、分区、通信协议与恢复说明](../CH32V208RBT6/README.md)。
0.1.0 新增的 [USBFS CMSIS-DAP](../CH32V208RBT6/docs/USBFS-DAP.md) 可供 OpenOCD/调试器直接访问 G4，
不需要 F4CP 转发；原有 BLE/OTA 操作保持在首页。
本版实现 CH32 的 OTA 与基础通信；未猜测未提供的 STM32 电源控制、采样和使能引脚。

## 设置与个人信息

设置页保留主题、主题色、字体、高 DPI、启动检查更新和预发布版本选项。
个人页显示作者、联系邮箱、项目与许可证。真实软著信息从 `src/config/profile.json` 读取，
填写 `SoftwareName`、`Owner`、`RegistrationNumber` 和 `RegistrationDate` 后重新打开个人页即可刷新。
没有提供的登记信息显示“待补充”。

## 验证与打包

```powershell
uv run python -m unittest discover -s tests -v
uv run cxfreeze build
```

打包输出 `build/exe/F4CP.exe`，请保留整个目录中的 DLL、lib 和 src。
固件交叉编译、OTA 核心掉电恢复模拟和界面验证已完成；用户日志已确认本板 BLE 扫描、配对和通信，修正后的 SPI 与 OTA 安装仍需实测。

## 模块

- `app/protocol/ble_device.py`：BLE 连接、通信与 OTA 上传/安装确认。
- `app/protocol/ota_package.py`：与固件打包器一致的升级包校验。
- `app/session/ble_controller.py`：独立工作线程中的 asyncio / WinRT 会话。
- `app/widgets/pages/`：四个页面。
- `config/`：原有原子保存、版本服务与主题设置。

## 配置模块

`config/` 按职责拆分：

- `schema.py`：配置项、默认值、验证和 Fluent 主题绑定；每个实例拥有独立配置项。
- `context.py`：`AppContext`、全局 `CTX` / `cfg`，以及加载、重载和保存入口。
- `versions.py`：统一的软件、Power 和 Upper 当前/最新版本管理服务。
- `paths.py`：源码与 cx_Freeze 环境下的目录解析，保留现有路径属性。
- `storage.py`：JSON 读取、旧配置迁移和原子写入，保存时保留未知字段。
- `logging.py`：日志初始化与 `get_logger()`，重复初始化不添加重复处理器。
- `constants.py`：配置分组、键名与软件仓库地址。
- `config.py` / `__init__.py`：兼容原有导入入口，现有 `from config import CTX, cfg, VERSION` 继续可用。

业务代码通过 `cfg.set(cfg.includePrereleases, True)` 保存设置；手动修改 JSON 后，
调用 `CTX.reload()` 原地更新配置并通知主题变化。重载保留配置项对象和已有信号连接，
读取失败时返回 `False`，错误可通过 `CTX.last_load_error` 查看，原文件和已有设置保持不变。
保存采用同目录临时文件加原子替换，格式损坏的 JSON 不会被默认设置覆盖。

测试或独立工具可使用 `AppContext(base_dir=临时目录, init_logging=False)`；
此类上下文独立读写自己的文件，不会替换应用的全局配置和主题。
`config.VERSION` 读取运行软件的版本，其余模块属性读取当前配置值；
使用 `from config import VERSION` 得到的是导入当时的值。

## 版本管理

`app/version.py` 统一版本比较、版本状态和不可变快照；`CTX.versions`（也可导入
`version_manager`）统一读写版本缓存，并通过 `changed(snapshot)` 通知首页、版本页和设置页。
组件名统一为 `App`、`Power`、`Upper`，配置使用两个分组：

```json
{
    "VersionCurrent": {"App": "2.0.0.A1", "Power": "", "Upper": ""},
    "VersionLatest": {"App": "", "Power": "", "Upper": ""}
}
```

空字符串表示版本未知。旧 `OldVersion` / `NewVersion` 字段与 `Application.Version` 会在读取时迁移，
保存时写入新结构；已有新字段优先，旧分组中的扩展字段继续保留。旧 `cfg.appVersion`、
`cfg.localAppVersion`、`cfg.localLowerVersion` 等名称是同一配置项的兼容别名，不重复保存。

软件当前版本优先读取 `pyproject.toml` 的 `[project].version`，其次读取已安装的 F4CP 包元数据；
仅旧打包程序缺少这些元数据时才使用已迁移的本地记录。cx_Freeze 配置会将 `pyproject.toml`
一同打包。检查 Release 只更新“最新版本”，下载更新包不会改写“当前版本”。

业务代码可用 `version_manager.snapshot().app.has_update` 判断软件更新，
通过 `version_manager.set_latest("Power", version)` 更新远程版本；确认本地固件版本后调用
`version_manager.set_current("Power", version)`。软件当前版本不允许通过此写入接口修改。
比较状态明确区分未知、格式无效、已是最新、有可用更新和本地领先，支持 `v` 前缀及 Alpha/Beta/RC。
保存失败会回滚本次写入，检查失败保留上次成功缓存。

## 软件更新

在“版本”页的“软件更新 · GitHub Release”卡片中点击“检查软件更新”。默认检查
`UF4DigitalPower/F4CP` 的正式 Release，根据语义版本号判断是否需要更新；开发版不会被旧版 Release 降级。
“设置 → 启动”可开启启动检查和包含预发布版本（Alpha、Beta、RC）。

发现新版本后，程序按当前系统和 CPU 架构筛选附件（Windows x64 也兼容 x86 包），
可选择附件和保存位置，并查看下载进度或取消下载。下载完成前使用临时文件，完成后校验文件大小，
若 GitHub 提供 SHA-256 则同时校验摘要；失败或取消会清理临时文件。更新包下载完成后，请退出程序，
手动解压或运行安装包。主页“检查更新”发现新版本时也可直接跳转下载。

更新地址保存在 `src/config/config.json` 的 `Update.UpdateUrl`，支持 HTTPS GitHub 仓库、
Release 页面或 API 地址。原先指向 `UF4OVER/UF4DigitalPower` 的默认软件地址会自动迁移；
固件更新配置保持独立。

更新模块测试：`uv run python -m unittest discover -s tests -v`。
