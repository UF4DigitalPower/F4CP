# F4CP

F4CP 是 UF4 数字电源的 Windows 上位机。它通过 UF4COM 与控制板通信，用于查看电源状态、设置参数、管理设备与 DAPLink，并提供 ADP 外环模型的离线训练页面。

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
- `app/session/`：电源、设备、参数、DAPLink 与 ADP 训练等页面逻辑。
- `app/widgets/`：PyQt5 界面组件和图表。
- `config/`：应用配置。
- `src/tools/uf4-target/`：用于切换 UF4 DAPLink 目标的小工具。

## ADP 离线训练

在“ADP训练”页面采集或选择 CSV 数据，设置 `Ilimit`、`Epoch`、验证集比例和随机种子后导出模型权重。默认输出文件为：

```text
Upper/STM32G474RBT6/USER/ADP_Scheduler/adp_outer_weights.h
```

STM32G474 固件检测到该头文件后会使用其中的权重。导出后先查看 JSON 报告，并在限流条件下完成硬件验证再部署。

## 打包

项目使用 cx_Freeze 配置 Windows 可执行文件：

```powershell
uv run cxfreeze build
```

输出目录由 `pyproject.toml` 中的 `build/exe` 配置决定。
