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

程序会加载 `app/` 下的界面和协议代码，本地设置保存在 `src/config/config.json`。

## 配置模块

`config/` 按职责拆分：

- `schema.py`：配置项、默认值、验证和 Fluent 主题绑定；每个实例拥有独立配置项。
- `context.py`：`AppContext`、全局 `CTX` / `cfg`，以及加载、重载和保存入口。
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
`config.VERSION` 等模块属性读取当前配置值；使用 `from config import VERSION` 得到的是导入当时的值。

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
