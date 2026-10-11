# Markdown Card Whiteboard Reader

把一份 Markdown 解析成卡片树（分隔线大卡片 + 标题嵌套），在可缩放白板中做非线性阅读的 **Windows 只读桌面工具**。
源 Markdown 文件是唯一内容源，应用**永不写入**该文件及其所在目录。

## 当前状态

| 阶段 | 状态 |
|---|---|
| 需求与方案冻结 | ✅ 见 [docs/requirements-spec.md](docs/requirements-spec.md)（决策台账 D1–D15） |
| 技术验证 spike | ⏳ 进行中 |
| 领域层 / 应用层 | ⏳ 进行中 |
| Typer CLI 垂直切片 | ⏳ 未开始 |
| PySide6 GUI | ⏳ 未开始 |
| 打包（PyInstaller onedir） | ⏳ 未开始 |

## 已冻结的关键决策（摘要）

- GUI：**PySide6 + QGraphicsScene** 原生白板。
- 公式 / Mermaid：Web 引擎**只做离屏渲染**，产出图片并按缩放档位缓存；画布内是静态图。
- 卡片身份：`stable_key`（结构键，跨刷新稳定）与 `content_hash`（内容指纹，只做变更检测）**分离**。
- 布局持久化：`%APPDATA%\MarkdownCardWhiteboardReader\boards\<path_hash>\<session_uuid>.json`，每会话一份分片 + `last_session` 指针，原子写 + schema 版本。
- 多窗口：**多进程，每窗口一个进程**，互不共享可变布局状态。
- 折叠：隐藏子孙卡片、父卡收缩、**记住子卡位置**。
- 缩放：整体画布变换（卡片尺寸与文字一起缩放）。
- 刷新：结构优先重建，判据为「大卡片数量或标题层级序列变化」。

## 开发环境

| 项 | 值 |
|---|---|
| Python | 3.12（`py -3.12`） |
| 依赖管理 | uv（`python -m uv`，本机以 pip 安装；`uv` 未加入 PATH） |
| 包名 / 分发名 | `mcwr` / `markdown-card-whiteboard` |
| CLI 命令 | `mcwr` |

```bash
python -m uv sync                                  # 安装依赖（默认走 pypi.org）
python -m uv run pytest -q                         # 测试
python -m uv run ruff check . && python -m uv run ruff format --check .
python -m uv run mypy src
```

> 本机 pip 全局索引指向 `pypi.tuna.tsinghua.edu.cn`，该镜像对 uv 包返回 403；
> 依赖安装请使用默认的 pypi.org（实测可达且较快），或显式指定 `--default-index https://pypi.org/simple`。

## 架构

分层 + 垂直切片 + Protocol 依赖倒置；`interfaces → application → domain`，`infrastructure` 实现端口。

```
src/mcwr/
├── domain/          # 纯模型与规则：零 IO、零框架、零 GUI
├── application/     # 用例编排 + 端口定义（Protocol）+ 每个 feature 一个目录
├── infrastructure/  # 适配器：实现端口，唯一碰外部库处
├── interfaces/      # cli/（Typer，先行）与 gui/（PySide6 绑定层）
├── shared/          # config / logging
└── container.py     # 唯一装配点
spikes/              # 一次性技术验证脚本（可随时删除）
```

## 只读承诺

应用对源文件及其同目录零写入；日志、缓存、临时文件一律落在应用数据目录。
集成测试会断言「打开前后源目录的文件集合与 mtime 不变」。
