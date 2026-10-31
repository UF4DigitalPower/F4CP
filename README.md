# F4CP

F4CP 是 UF4 数字电源的 Windows 上位机。它通过 UF4COM 与控制板通信，用于查看电源状态、设置参数、管理设备与 DAPLink。

## 环境

- Windows
- Python 3.15（64 位）
- [uv](https://docs.astral.sh/uv/)
- Visual Studio C++ x64/x86 生成工具与 Windows SDK（用于编译尚未提供 Python 3.15 wheel 的依赖，例如 `hidapi`）

项目依赖写在 `pyproject.toml` 和 `uv.lock` 中。首次运行前安装依赖：

```powershell
uv sync
```

如果旧锁文件在 Python 3.15 上提示 LIEF 没有预编译 wheel，更新相关依赖后再同步：

```powershell
uv sync --upgrade-package lief --upgrade-package pyqt5-sip --upgrade-package bitarray --upgrade-package numpy
```

不要固定 `lief==0.17.6`：它没有 Python 3.15 对应的 Windows wheel。当前锁文件使用 `lief==1.0.0`、`pyqt5-sip==12.20.0`、`bitarray==3.12.3` 和 `numpy==2.5.4`。

## 运行

在项目根目录执行：

```powershell
uv run python start.py
```

程序会加载 `app/` 下的界面和协议代码，`config/config.py` 保存本地配置。

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

## 主要目录

- `app/protocol/`：UF4COM 协议实现。
- `app/session/`：电源、设备、参数与 DAPLink 等页面逻辑。
- `app/widgets/`：PyQt5 界面组件和图表。
- `config/`：应用配置。
- `src/tools/uf4-target/`：用于切换 UF4 DAPLink 目标的小工具。

## 打包

项目使用 cx_Freeze 配置 Windows 可执行文件：

```powershell
uv run cxfreeze build
```

输出目录由 `pyproject.toml` 中的 `build/exe` 配置决定。
