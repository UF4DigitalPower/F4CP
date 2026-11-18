# F4CP 工程约束

执行前阅读 `../CH32V208RBT6/docs/开发与交付流程.md`，保留用户未提交的修改。

- Windows / Python / UV；优先 pyproject.toml 配置的清华国内源。
- 保留首页、固件下载、设置、个人四页；软件更新集成在首页应用卡片下的子卡片，不单设导航页。
  首页不放固件更新卡片；不要恢复未使用的设备/电池/DAPLink/参数等页面。
- BLE 设备 UF4 Power V208，口令 005213；认证、加密和设备身份检查不可为了连接成功而移除。
- Windows 使用 app/protocol/windows_pairing.py 的 PIN 后端，处理 PROVIDE_PIN，
  请求 ENCRYPTION_AND_AUTHENTICATION，不回退 Just Works。
- 建链后通过版本和 OTA 状态受保护读取确认安全链路；仅对 ATT 0x05/0x0F 有限等待。
  不因通用错误重放写命令，不在正常连接、认证失败或超时时自动解除绑定。
- “重新配对”是用户主动选择的恢复操作，只移除所选设备的电脑端绑定。
  不在开发验证中自动操作真实设备绑定。配对事件无论成功、失败、超时或取消均须释放。
- WinRT / BLE 在单个工作线程的 asyncio loop 中执行，UI 用信号更新，不阻塞主线程。
- Flash 信息需检查协议、目标、可用标志和 JEDEC。未识别时禁用 OTA，上传前重新查询。
  PB3=CLK、PB4=MISO、PB5=MOSI、PD2=/CS，不能重新写成 PA4～PA7。
- 固件 0.1.0 的 SPI1 默认 PA4～PA7 用于 USBFS CMSIS-DAP；Flash 在 PB 组走独立 GPIO SPI。
  DAP 调试不依赖 F4CP，不为该功能恢复旧页面。PA0/PA1 是目标 NRST/BOOT0，不是 ESP32 控制。
- 上传后必须重连核对运行版本、长度、CRC；进度传完不能直接宣称安装成功。
- 上位机版本来自 pyproject.toml，与设备 App/firmware_version.h 独立。
  仅修上位机不提升设备版本，不要求用户无故重新烧录。
- 修改后运行 `uv run python -m unittest discover -s tests -v`；交付 EXE 时重新运行
  `uv run cxfreeze build`，确认相关模块已打包，交付保留 build/exe 整个目录。
- 软件更新下载不修改“当前版本”；未知软著信息保持待补充，不虚构作者登记资料。
