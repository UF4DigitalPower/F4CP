# F4CP

[开发与交付流程](../CH32V208RBT6/docs/开发与交付流程.md) 固定硬件、版本、配对恢复、验证与交付规则。
协作约束见 `AGENTS.md`。从固件目录运行 `python tools/release_check.py --scope desktop --package`
可统一执行上位机测试与打包。

F4CP 是 UF4 数字电源的 Windows 上位机。本版配合 CH32V208RBT6 固件，通过 BLE 完成设备连接、基础通信和 W25Q256 备用区固件 OTA。

界面包含四页：**首页、固件下载、设置、个人**。软件更新集成在首页应用卡片下方的子卡片；
首页不再展示固件更新卡片。旧串口、设备参数、电源仪表、DAPLink 和电池页面已删除。

界面参考 [QFluentWidgets Pro 组件介绍](https://qfluentwidgets.com/zh/pages/pro/) 的渐变卡片、
状态标签、拖放与步骤进度设计，使用现有社区版组件及原生 Qt 绘制实现，无 Pro 依赖。
首页使用电路主题的渐变品牌区和三个快捷入口，应用卡片继续内嵌软件更新；
下载页以双栏呈现连接与任务，窄窗口自动上下排列。支持单个本地固件拖放，
与浏览文件共用格式/目标校验，任务进行期间不可替换文件。步骤、语义状态标签与三项指标
展示实际任务状态，上传完成后仍等待最终校验与安装确认。
本次界面调整136项测试通过，含拖放共用校验、任务中锁定文件、最终确认和首页快捷导航，
见 `output/workspace-ui-tests.log`。四页深浅主题、900/1000/1200/1400宽度、空闲/传输/成功/失败
及有线模式使用模拟数据检查，见 `output/workspace-ui-render.log` 与 `output/workspace-*.png`。
EXE构建、模块核对及启动记录为 `output/workspace-ui-package.log`、
`output/workspace-ui-package-check.log`、`output/workspace-ui-startup.log`。本轮未操作硬件。

固件下载页移除了设备通信和下载两个常驻日志框。连接、版本、存储、任务阶段、已上传字节、
上传速度与剩余时间以标签显示，结果只提示一次；失败通知保留到手动关闭。
“通信调试”按需展开，最近收发内容保留在标签，完整收发与诊断进入顶部标题栏右侧的“运行日志”。
日志按钮与灵动岛位于同一标题栏，在窗口控制按钮左侧，所有页面均可打开。
该独立窗口为非模态，可在下载期间查看、复制和导出，关闭窗口不影响任务。
全部记录继续使用同一个 `logs/f4cp_*.log`（每次启动一份），不新增分散的连接/下载日志文件。
窗口保留最近1500行，导出保存当前完整日志文件；“清空显示”不会清除磁盘日志。
统一日志改版时133项测试通过，见 `output/unified-log-tests.log`，含线程日志汇聚、诊断不重复、
阶段/速度独立展示、复制导出及结果仅通知一次。界面用模拟连接渲染检查，无实机操作。
EXE重新打包及模块核对记录：`output/unified-log-package.log`、`output/unified-log-package-check.log`。
顶部按钮调整后133项测试通过，见 `output/titlebar-log-tests.log`；模拟四页打开日志、
900/1000/1200宽度及深浅主题检查通过，未操作硬件。新版打包及模块核对记录为
`output/titlebar-log-package.log`、`output/titlebar-log-package-check.log`。

## 安装和运行

需要 Windows、Python 3.15 与 UV。项目已将 **清华国内镜像**设为 UV 默认源：

```powershell
uv sync
uv run python start.py
```

首次连接：在“固件下载”页选择无线，扫描 **UF4 Power V208**，连接时按 Windows 提示输入 **005213**。
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

固件 0.1.2 起，“通信调试”提供 **USB诊断**（现位于固件下载页）：通过安全 BLE 连接读取 USB 枚举计数、
寄存器和最近 SETUP，在统一运行日志窗口显示可复制的文本，无需串口或 USB 枚举成功。
固件 0.1.3 会先让 USB 独立枚举约3秒，再启动 BLE；新版诊断会同时显示 BLE 启动前冻结快照和当前状态。
保持 USB 连接并重启应用后读取；诊断不会清计数、复位 USB 或改写 Flash。
0.1.1 不支持此命令，需先安装诊断固件；0.1.2 仍兼容读取三页当前状态。
详见 [无串口诊断](../CH32V208RBT6/docs/USBFS-DAP.md)。
本功能用于定位代码 43，目前尚未确认实板枚举根因与修复效果。
固件 0.1.4 新增接收分类、DMA 地址读回和首个 TRANSFER 事件；诊断仍兼容 0.1.2/0.1.3。
本次 0.1.4 配套 EXE 位于 `build/exe-usb014/F4CP.exe`，需保留整个目录。
已有上位机仍在运行，保留其目录，使用独立输出目录重新打包。

## 固件下载界面

导航栏“固件下载”统一管理 V208 与 G474，包含 BLE 扫描、连接和通信，通过同一个
BLE 工作线程执行无线下载。首页保留应用介绍、内嵌软件更新与项目预览，
固件下载通过独立导航或首页快捷入口进入。下载页采用圆角卡片、语义标签和步骤进度，
横向空间足够时分为连接/任务双栏，否则上下排列；保留系统字体、用户主题色与 Mica 设置。
已有主题/字体偏好仍可在设置页调整。

| 芯片 | 无线 | 有线 |
| --- | --- | --- |
| CH32V208RBT6 | `.ota`，上传后重启、重连并核对版本/长度/CRC | 不提供 |
| STM32G474RBT6 | 通过 Link V3 暂存 BIN，再以 SWD 烧录并读回校验，最大 128KiB | DAPLink + 内置 pyOCD 和本地 STM32G4 Pack，`.hex` / `.bin` |

无线下载在本页连接，设备身份、认证、加密及 W25Q256 查询通过后才允许上传；
G474 还需设备提供 Link V3 G474 服务。G474 BIN 从 `0x08000000` 链接，上传按 8B 补 FF，
检查向量表、偏移和 CRC；暂存校验通过后才开始目标擦写。每次写请求只发送一次，
响应丢失不重放命令。目标擦写与 V208 安装提交后禁止取消；传输到 95% 后等待最终校验，
只有确认成功才显示 100%。

G474 无线上传会在暂存区准备后等待最多 1.5 秒刷新 MTU，兼容 MTU23，
每组继续刷新实际包长（MTU247 时为 239B 数据/包）。DATA 保留逐包写入应答，
每最多 8 包核对一次已持久化的偏移、长度和 CRC 身份；任何写入错误直接停止，
不自动重发。暂存完整 CRC 和目标 Flash 读回校验继续执行。
速度仅计算蓝牙上传阶段，不含暂存区擦除和 MTU 等待；不代表 SWD 写入速率或全程速度。
上述分组核对优化兼容现有 Link V3；用户实测仍约 1.3 KiB/s，且日志为
239 字节/包，确认该次上传已使用大包，但仍有逐包应答等待。

进一步的连续传输需要 V208 **0.4.3** 和本次新版 F4CP：能力协商后以无应答方式
连续发送最多 4 包 DATA，读取设备持久化偏移、长度和 CRC 身份后才推进下一组。
控制命令仍需应答；包长同时受设备 MTU、主机 MTU 和 Windows 无应答写入上限约束。
丢包、偏移错误、设备暂存错误或链路错误直接停止，不自动重传或执行目标擦写。
旧设备特征未提供连续传输能力时保留逐包应答模式，并在日志提示需 V208 0.4.3。
无需更新 G474 测速固件。实际提速效果尚待实板验证。

用户随后报告 V208 自身 OTA 约 1.5 KiB/s，日志确认已使用 236B/包、连续发送 4 包/组。
当前 F4CP 为 V208 OTA 和 G474 暂存上传增加被动耗时诊断，不增加 GATT 操作或改变发送顺序。
上传开始显示设备实际运行版本、MTU、Windows 无应答写入上限；每约 5 秒和传输结束/中断时，
在运行日志窗口及 `logs/f4cp_*.log` 记录写调用与状态读取的次数、累计/平均/最大耗时、其他耗时、
已确认/尝试发送字节数及未完整确认组数。统计只覆盖 DATA 阶段，不含擦除、CRC 或安装。
写调用耗时包含系统调度及协议栈等待，状态读取也可能等待设备处理；这些数据不能单独证明
Windows 或设备 Flash 是根因。本次仅提供定位证据，未确认吞吐提升，无需更新设备固件。
连接异常同时记录失败阶段和完整堆栈，配对检查有独立日志；连接失败后的清理异常
不会覆盖原始错误。服务发现返回 Windows `0x80070016` 时提示手动“重新配对”，不自动删除绑定。
本机只读诊断复现该错误发生于 G474 服务的实时特征枚举；缓存仍只有旧版 read/write，
而设备受保护版本读取已为 0.4.3 / 44331118。经用户明确授权，仅对所选 V208 重新配对后，
实时服务发现、认证加密版本/OTA 状态读取成功，G474/OTA 特征均含 write-without-response。
这是连接恢复的实板证据，不代表上传吞吐已修复。记录见 `output/ble-service-probe.log`、
`output/ble-discovery-modes.log`、`output/ble-discovery-confirm.log`、`output/ble-repair-pairing.log`。

本次诊断版验证：126 项上位机测试通过，见 `output/ble-timing-tests.log`；
打包与模块核对记录为 `output/ble-timing-package.log`、`output/ble-timing-package-check.log`。
EXE 启动存活记录为 `output/ble-timing-startup.log`。源码用户需重启程序加载本次诊断代码。

2026-11-18 用户确认 G474 120KiB 暂存上传12.52KiB/s、暂存CRC通过，上传515包无缺失，
状态读取占8.301/9.586秒。随后SWD在偏移65536报目标Flash错误。
只读SWD确认容量128KiB、OPTR=FFEFF8AA（DBANK=1）、SR=0xA8。
G474此布局的前64KiB从0x08000000开始，另64KiB从0x08040000开始，中间有空洞。
新增有线BIN/HEX预检和V208 0.4.4无线布局错误15，均在目标擦除前拒绝跨空洞的连续镜像，
不自动更改DBANK。当前板先使用 `../STM32G474RBT6/build/upload-test/G474_UploadTest_60KiB.bin`，
61440B、CRC32 `1A85A2C6`；旧120KiB连续镜像仅适用于DBANK=0。
本轮129项上位机测试通过（`output/g474-layout-tests.log`），覆盖有线空洞拦截和无线错误15解释；
固件仅Release编译，未运行固件测试、未刷写。60KiB实板烧录和LED仍待用户验证。
EXE打包、模块核对和启动记录：`output/g474-layout-package.log`、
`output/g474-layout-package-check.log`、`output/g474-layout-startup.log`。

连续传输交付验证：122 项上位机测试通过，日志 `output/g474-stream-tests.log`；
`uv run cxfreeze build` 已打包，日志 `output/g474-stream-package.log`。
打包上传模块字节码与源码一致，使用打包模块执行的 120 KiB 及丢包模拟通过，
见 `output/g474-stream-package-check.log`；EXE 启动存活检查通过，
见 `output/g474-stream-startup.log`。未连接或刷写真实设备。

2026-11-18 无线上传优化验证：115 项上位机测试通过，见
`output/g474-upload-tests.log`；含 MTU 延迟协商、MTU23/247、分组确认、取消、
偏移/CRC 错误、写应答丢失不重发及排除擦除时间的速度统计。
此前按两份 Python 文件字节相等判断 OTA 格式的过期测试，改为验证固件只读解析器
与桌面解析器对有效包、损坏包的兼容性，适配已迁移的 C 打包器。
`uv run cxfreeze build` 已重新生成 `build/exe/F4CP.exe`，保留整个目录；
新上传模块的打包字节码与源码核对、打包 BLE 依赖导入及 EXE 启动存活检查通过，
日志分别为 `output/g474-upload-package.log`、`output/g474-upload-package-check.log`、
`output/g474-upload-startup.log`。未连接、刷写真实设备，实际吞吐提升尚待实测。

V208 仅提供无线 OTA，连接方式固定为 BLE；已移除有线 WCH 烧录入口、工具配置和调用代码。
从 G474 有线模式切换到 V208 时会自动切回无线，并清除上一目标选择的固件。

G474 使用 pyOCD Python API，扫描后按完整 UID 选择 DAPLink；UF4 `1A86:FE0C` 显式注册，
优先 HID 接口。默认 100kHz、under-reset，可选择连接频率和模式。
内置 Pack 目标为 `stm32g474rbtx`，写入前核对 0x469 DEV_ID、128KiB 容量及保护状态；
禁止自动解除读写保护或修改选项字节。按扇区写入后逐字节读回全部固件段，全部一致才复位运行。
“连接 / 识别”结束后会释放会话，目标可能保持暂停，可下载或手动复位后运行。
旧代码先通过 `uf4-target` 为 F401 调试器切换 G474/F429，再调用 pyOCD；
当前 V208 的 SWD 固定连接 G474，不发送旧目标切换命令，也不恢复旧 DAPLink 独立页面。

G474 HEX 按自身地址烧录，拒绝越界、重叠、校验和错误及非程序区记录；BIN 从 `0x08000000` 写入。
不支持把 `.ota` 当作有线镜像，也不自动擦除绑定、用户区或解除保护。
G474 有线下载使用已检查文件的快照，在后台线程调用 pyOCD API；
冻结 EXE 不会通过 `sys.executable -m pyocd` 重新启动自身。

下载期间禁用设备操作和下载参数，避免并行访问。关闭窗口时先协作取消上传，
不会强行停止已进入安装或目标擦写阶段的工作线程。目标擦写断电后可能需要重新完整烧录。
本次只修改上位机，不提升设备版本；不自动刷写硬件。

新增校验覆盖固件格式/越界、G474 MTU23/247、取消、CRC/偏移错误、丢失响应不重放，
以及页面互斥、连接方式切换和最终成功确认。测试与界面检查不等于实板烧录通过。
本轮 106 项上位机测试通过（删除已移除通道的测试，保留 pyOCD 模拟探针、保护检查、读回失败和线程互斥），
测试日志 `output/remove-wch-tests.log`。打包命令 `uv run cxfreeze build`，
日志 `output/remove-wch-package.log`，交付 `build/exe/F4CP.exe`，保留整个 `build/exe` 目录。
隔离开发依赖后，交付目录的 pyOCD/HID/原生库导入、Pack 目标和调试序列解析通过，
记录见 `output/remove-wch-package-check.log`（同时验证打包界面的连接方式切换）；
EXE 启动检查见 `output/remove-wch-startup.log`。
原生窗口预览为 `output/home-restored.png`、`output/firmware-pyocd.png` 和
`output/firmware-wireless.png`。未连接或刷写真实设备，三种下载通道均待实板验证。

## 固件 OTA

首次通过有线烧录 `../CH32V208RBT6/build/UF4_CH32V208_factory.hex`；此后在“固件下载”页选择 V208 / 无线，再选择
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
不需要 F4CP 转发；BLE 连接、通信和自身 OTA 均位于固件下载页。
本版实现 V208 自身 OTA、G474 无线 SWD 下载、G474 有线 pyOCD 下载与基础通信。

## 设置与个人信息

设置页保留主题、主题色、字体、高 DPI、启动检查更新和预发布版本选项。
个人页以软件 ICO 和名称为顶部标识，项目详情、源码仓库与知识产权三张卡片垂直排列，
使用 QFluentWidgets 原生 `SimpleExpandGroupSettingCard`，标题栏、箭头、边框和折叠动画
沿用组件原样式；仅适配多行资料的内容高度。默认展开；点击标题栏或右侧箭头可独立收起，
聚焦箭头后键盘空格与回车也可操作。顶部标识卡片同样使用原生默认圆角。
去掉页底版权和版本栏，当前版本在项目详情内查看。框架、仓库和许可证使用工程真实信息。
软著信息从 `src/config/profile.json` 读取：`SoftwareName`、`Owner`、`CertificateNumber`、
`RegistrationNumber`、`AcquisitionMethod`、`RightsScope` 和 `RegistrationDate`。
已按用户提供填写何平、软著登字第18166005号、2026SR0951724、原始取得及全部权利；
未提供的登记日期显示“待补充”。重新打开个人页可刷新资料，版本跟随工程版本。
折叠界面的测试、模拟字段核对、深浅主题和900/1200宽度检查记录为
`output/profile-native-tests.log`、`output/profile-native-render.log`；同时检查原生组件、标题/箭头点击、
键盘操作、独立收起与布局缩短，预览为 `output/profile-native-preview.png`。
EXE构建、模块与资料核对、启动记录为 `output/profile-native-package.log`、
`output/profile-native-package-check.log` 和 `output/profile-native-startup.log`，未操作硬件。

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
- `app/widgets/pages/`：首页、固件下载、设置和个人四个页面。
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
`version_manager`）统一读写版本缓存，并通过 `changed(snapshot)` 通知首页和设置页。
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

首页 APP 卡片与个人页共用 QFluentWidgets 原生展开卡片，默认展开，点击标题栏或箭头可收起。
收起时仍显示软件当前版本与“检查更新”按钮；点击检查会展开内容，显示版本说明与更新结果。
下载区域与进度出现时自动适配内容高度，后台状态更新保留用户的收起选择。
在标题栏右侧点击“检查更新”，检查结果和下载控件直接显示在下方子卡片。默认检查
`UF4DigitalPower/F4CP` 的正式 Release，根据语义版本号判断是否需要更新；开发版不会被旧版 Release 降级。
“设置 → 启动”可开启启动检查和包含预发布版本（Alpha、Beta、RC）。

发现新版本后，程序按当前系统和 CPU 架构筛选附件（Windows x64 也兼容 x86 包），
可选择附件和保存位置，并查看下载进度或取消下载。下载完成前使用临时文件，完成后校验文件大小，
若 GitHub 提供 SHA-256 则同时校验摘要；失败或取消会清理临时文件。更新包下载完成后，请退出程序，
手动解压或运行安装包；检查和下载过程中停留在首页，不再跳转独立软件更新页。

未检查更新时，子卡片显示随软件附带的当前版本介绍（`src/assets/f4cp-release-notes.md`），
无需联网。发现新版本后展示该 Release 的 Markdown 更新说明和适配附件；最新发布与当前版本
相同时可显示对应发布说明，旧版 Release 不会替换当前版本介绍或触发降级下载。
自动检查失败时保留当前版本介绍，并在卡片内显示错误。深色与浅色主题均支持说明文本显示。

本轮 136 项上位机测试通过，包含首页版本说明、更新下载/取消和版本同步，
日志 `output/home-app-tests.log`。原生展开、动态高度、深浅主题、窄窗口和键盘操作检查
见 `output/home-app-render.log`，个人页回归记录为 `output/home-app-profile-check.log`。
打包、模块核对和 EXE 启动记录为 `output/home-app-package.log`、
`output/home-app-package-check.log`、`output/home-app-startup.log`。
交付 `build/exe/F4CP.exe`，保留整个目录。预览为 `output/home-app-light.png`、
`output/home-app-dark.png`、`output/home-app-collapsed.png`、`output/home-app-update.png`；
新版预览使用模拟 Release，不表示已发布该版本。未连接或刷写真实设备。

更新地址保存在 `src/config/config.json` 的 `Update.UpdateUrl`，支持 HTTPS GitHub 仓库、
Release 页面或 API 地址。原先指向 `UF4OVER/UF4DigitalPower` 的默认软件地址会自动迁移；
固件更新配置保持独立。

更新模块测试：`uv run python -m unittest discover -s tests -v`。
