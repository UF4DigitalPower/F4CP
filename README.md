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

## 网站风格界面原型

运行 `.\start-preview.ps1` 或 `python preview.py`，可以打开基于 me.hepi.ng 黑白 / 荧光绿风格的独立 PyQt5 原型。包含控制总览、波形、演示日志和主题设置，仅使用本地模拟数据。详细说明见 [prototype/README.md](prototype/README.md)。

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
