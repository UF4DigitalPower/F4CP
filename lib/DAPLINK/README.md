# DAPLINKFirmware

面向 `STM32F103` 自制调试器硬件的 DAPLink 固件工程，包含可单独编译的 `Bootloader` 和 `Interface Firmware` 两套镜像。

这个仓库从 DAPLink 工程中整理出了一份适合自定义板卡维护的最小可编译子集，保留了原始目录结构，同时补上了和当前硬件有关的定制逻辑，方便单独开发、编译、调试和发布。

## 项目目标

- 为 `STM32F103` 自定义调试器提供可维护的 DAPLink 固件工程
- 保留 `Bootloader + Interface Firmware` 的标准升级链路
- 支持 UF2/拖拽升级风格的量产和维护流程
- 将与当前硬件强相关的改动集中在可追踪的位置

## 当前定制

### 板卡信息

- Board ID: `UF40`
- Board Vendor: `UF4OVER`
- Board Name: `UF4DigitalPower`
- USB Product String: `UF4PowerFirmwareDAPLINK CMSIS-DAP`

### 当前硬件假设

- HIC MCU: `STM32F103xB`
- Bootloader 区: `0x08000000 - 0x0800BBFF`
- Interface 区: `0x0800C000 - 0x0801FBFF`
- Config 区: `0x0801FC00 - 0x0801FFFF`

### 已包含的关键定制

- 自定义 `Bootloader` 板级描述
- 自定义 `Interface Firmware` 板级描述
- 针对“无独立复位按键”的启动逻辑修正
- 针对 `STM32F103` Bootloader 更新路径的整片擦除页数修正

## 目录结构

```text
DAPLINKFirmware/
├─ build.ps1
├─ projects.yaml
├─ requirements.txt
├─ tools/
├─ records/
├─ source/
│  ├─ board/
│  ├─ daplink/
│  ├─ family/
│  ├─ hic_hal/
│  ├─ rtos2/
│  ├─ rtos_none/
│  ├─ target/
│  └─ usb/
└─ projectfiles/
   └─ make_gcc_arm/
      ├─ stm32f103xb_custom_bl/
      └─ stm32f103xb_custom_f103rb_if/
```

## 功能说明

### Bootloader

- 作为维护模式固件运行
- 通过 U 盘拖拽升级 `Interface Firmware`
- 在 `Interface Firmware` 有效时自动跳转到主固件

### Interface Firmware

- 提供 CMSIS-DAP 调试功能
- 提供 MSC 拖拽下载
- 提供 CDC 串口桥接
- 保留 WebUSB / WinUSB 相关配置

## 构建环境

建议环境:

- Windows PowerShell
- Python 3
- `make`
- `arm-none-eabi-gcc`
- `arm-none-eabi-objcopy`
- `arm-none-eabi-size`

使用 `uv`:

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv sync
```


## 快速构建

推荐直接使用根目录脚本:

```powershell
.\build.ps1 -Target all
```

可选目标:

```powershell
.\build.ps1 -Target if
.\build.ps1 -Target bl
```

## 手动构建

### 构建 Interface Firmware

```powershell
python tools\progen_compile.py -t make_gcc_arm --clean stm32f103xb_custom_f103rb_if
Push-Location projectfiles\make_gcc_arm\stm32f103xb_custom_f103rb_if
python ..\..\..\tools\post_build_script_gcc.py
Pop-Location
```

### 构建 Bootloader

```powershell
python tools\progen_compile.py -t make_gcc_arm --clean stm32f103xb_custom_bl
Push-Location projectfiles\make_gcc_arm\stm32f103xb_custom_bl
python ..\..\..\tools\post_build_script_gcc.py
Pop-Location
```

## 输出产物

推荐直接使用根目录 `build/` 下整理后的文件。

### Interface Firmware

- `build/interface/interface.elf`
- `build/interface/interface.hex`
- `build/interface/interface.bin`
- `build/interface/interface_crc.hex`
- `build/interface/interface_crc.bin`
- `build/interface/interface_crc.txt`

### Bootloader

- `build/bootloader/bootloader.elf`
- `build/bootloader/bootloader.hex`
- `build/bootloader/bootloader.bin`
- `build/bootloader/bootloader_crc.hex`
- `build/bootloader/bootloader_crc.bin`
- `build/bootloader/bootloader_crc.txt`

### 编译系统原始输出

Interface:

- `projectfiles/make_gcc_arm/stm32f103xb_custom_f103rb_if/build/stm32f103xb_custom_f103rb_if.elf`
- `projectfiles/make_gcc_arm/stm32f103xb_custom_f103rb_if/build/stm32f103xb_custom_f103rb_if.bin`
- `projectfiles/make_gcc_arm/stm32f103xb_custom_f103rb_if/build/stm32f103xb_custom_f103rb_if_crc.bin`

Bootloader:

- `projectfiles/make_gcc_arm/stm32f103xb_custom_bl/build/stm32f103xb_custom_bl.elf`
- `projectfiles/make_gcc_arm/stm32f103xb_custom_bl/build/stm32f103xb_custom_bl.bin`
- `projectfiles/make_gcc_arm/stm32f103xb_custom_bl/build/stm32f103xb_custom_bl_crc.bin`

## 刷写和升级流程

### 首次烧录

1. 使用下载器将 `build/bootloader/bootloader.bin` 烧录到 `STM32F103`
2. 重新上电，设备进入 Bootloader 模式并枚举为大容量存储
3. 将 `build/interface/interface_crc.bin` 拖入 U 盘
4. 升级完成后设备应切换到 Interface Firmware

### 后续升级 Interface Firmware

正常情况下:

1. 进入 Bootloader 模式
2. 拖入 `build/interface/interface_crc.bin`
3. 等待拷贝结束并自动重启

### 说明

- 推荐升级 `Interface Firmware` 时使用 `_crc.bin`
- 如果需要重新烧录 Bootloader，建议使用外部下载器
- 旧版 Bootloader 在特定 `STM32F103` 硬件上可能存在整片擦除异常，本仓库已修正

## 已知问题

### 1. Windows 下 `Makefile` 里的 `env python ...` 可能失败

某些 Windows 环境中，`make` 调用的 `python` 不一定可用，因此 `post build` 钩子可能不会自动执行。

这不影响 `.elf / .hex / .bin` 主产物生成，但如果需要 `_crc.bin`，请手动执行:

```powershell
Push-Location projectfiles\make_gcc_arm\stm32f103xb_custom_f103rb_if
python ..\..\..\tools\post_build_script_gcc.py
Pop-Location

Push-Location projectfiles\make_gcc_arm\stm32f103xb_custom_bl
python ..\..\..\tools\post_build_script_gcc.py
Pop-Location
```

### 2. 这是一个面向特定硬件裁剪过的 DAPLink 子集

仓库不是完整官方 DAPLink 镜像，而是为了当前 `STM32F103` 自定义调试器维护而整理的最小可编译集合。

### 3. 开源发布前建议补充顶层许可证文件

仓库中的大量源码保留了上游 `Apache-2.0` 文件头。

## 单独导出产物

如果已经完成编译，只想重新整理根目录 `build/` 产物:

```powershell
python tools\export_build_artifacts.py --target-project stm32f103xb_custom_f103rb_if --out-dir build
python tools\export_build_artifacts.py --target-project stm32f103xb_custom_bl --out-dir build
```

## License

本项目采用Apache License 2.0授权。

因为该仓库包含源文件来源于上游
DAPLink代码，请在你使用时保留原始文件头。
修改或重新分发这些文件。

## 上游关系

本仓库基于 DAPLink 相关源码整理和裁剪，保留了原始工程的大部分目录组织方式，方便后续与上游结构对照、迁移和维护。

如果你准备继续演进这个仓库，比较推荐的做法是:

- 将板级差异尽量收敛在 `source/board/`
- 将构建差异尽量收敛在 `projects.yaml` 和 `projectfiles/`
- 把与具体硬件异常相关的修复写进 README 和提交说明

## 适合谁使用

- 正在做自制 DAPLink 调试器的人
- 需要在 `STM32F103` 上维护 Bootloader + Interface 双镜像的人
- 想把内部固件整理成可公开仓库的人
