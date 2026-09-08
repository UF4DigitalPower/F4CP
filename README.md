# F4CP

F4CP 是 UF4 数字电源的 Windows 上位机。它通过 UF4COM 与控制板通信，用于查看电源状态、设置参数、管理设备与 DAPLink。

## 环境

- Windows
- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)

项目依赖写在 `pyproject.toml` 和 `uv.lock` 中。首次运行前安装依赖：

```powershell
uv sync
```

## 运行

在项目根目录执行：

```powershell
uv run python start.py
```

程序会加载 `app/` 下的界面和协议代码，`config/config.py` 保存本地配置。

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
