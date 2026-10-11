# Markdown Card Whiteboard Reader

把一份 Markdown 解析成卡片树（分隔线大卡片 + 标题嵌套），在可缩放白板中做非线性阅读的 **Windows 只读桌面工具**。
源 Markdown 文件是唯一内容源，应用**永不写入**该文件及其所在目录。

需求与全部已确认决策见 [docs/requirements-spec.md](docs/requirements-spec.md)（台账 D1–D15）。

## 当前状态

| 阶段 | 状态 | 证据 |
|---|---|---|
| 需求与方案冻结 | ✅ | docs/requirements-spec.md（D1–D15） |
| Spike 1：markdown-it 块分类 | ✅ | spikes/NOTES.md（全部块类型可判别） |
| 领域层 + 建树 + 解析 + CLI 垂直切片 | ✅ | `mcwr cards <file>` 可跑通真实文件 |
| 布局 / 拆出-还原 / 折叠 | ✅ | 32 项单测 |
| 布局持久化（D9+D15 会话分片） | ✅ | 35 项单测 |
| PySide6 GUI（拖动/缩放/右键/右下角按钮） | ✅ | 12 项离线 GUI 冒烟测试 + 真实平台启动验证 |
| 刷新（结构优先重建，D11 判据） | ✅ | 42 项切片单测 + 端到端验收（改正文保留位置、改层级/加分隔线重建） |
| 十项验收标准 | ✅ | tests/integration/test_acceptance.py（逐条对应 §1.5） |
| 公式 / Mermaid 离屏渲染（D14） | ✅ | 46 项渲染测试；App 内实测数学卡出 `E = mc²`、Mermaid 卡出流程图；打包后自检 `rendered_images=2/2` |
| 视觉规范 + 双主题（跟随系统/浅色/深色） | ✅ | docs/visual-spec.md（取值唯一来源）+ `interfaces/gui/theme.py`；`tests/integration/test_theme_switch.py` 6 项（切换不动任何布局字段）、深色真实位图像素断言 |
| 200 卡片上限与超限降级（D-023/D-029） | ✅ | 201 卡合成文档实测打开 0.03–0.05 s；`tests/integration/test_card_limit.py` 4 项：超限后零离屏渲染、公式按原文绘制、状态栏与日志各一次提示 |
| 目录卡片点击跳转（FR-2.4） | ✅ | `[TOC]` 处生成可点击条目（全部 H1–H6）；`tests/integration/test_toc_navigation.py` 5 项：真点击 → 目标卡居中并高亮、折叠祖先逐级展开、链接点击不拖动卡片 |
| 打包（PyInstaller onedir） | ✅ | `packaging/mcwr.spec`；交付形态自检 `dist\mcwr\mcwr.exe --self-check` 退出码 0（frozen=true，5 卡、公式与 Mermaid 各出 1 图），bundle 574 MB |

## 运行

```bash
python -m uv sync                                    # 安装依赖（默认走 pypi.org）
python -m uv run mcwr gui spikes/samples/sample.md   # 打开白板窗口
python -m uv run mcwr cards spikes/samples/sample.md # 打印卡片树（只读，无 GUI）
python -m uv run mcwr cards spikes/samples/sample.md --format json
python -m uv run mcwr version
```

GUI 操作：滚轮缩放（以光标为锚点）、中键拖动平移、双击卡片居中、拖动卡片（子卡片跟随父卡片，且不能拖出父卡片边界）、
右键卡片 → 拖出为自由卡片 / 还原到父卡片 / 收回所有子卡片 / 折叠展开，右下角 **刷新** 与 **全部还原**；
文档里写了 `[TOC]`（或 `[[TOC]]`）时，目录卡会列出全部标题，**点击条目跳到对应标题卡**（自动展开被折叠的祖先，不改变缩放）；
工具栏最右侧是**主题三态**（跟随系统 / 浅色 / 深色），切换只重绘、不移动任何卡片，选择会记住。
`Ctrl+N` 新建窗口（新进程，独立会话）、`Ctrl+O` 打开、`F5` 刷新、`Ctrl+Shift+R` 全部还原、`Ctrl+0` 适应视图、`Ctrl+±` 缩放。

## 开发

| 项 | 值 |
|---|---|
| Python | 3.12（`py -3.12`） |
| 依赖管理 | uv（本机以 pip 安装，命令为 `python -m uv`） |
| 包名 / 分发名 | `mcwr` / `markdown-card-whiteboard` |
| 数据目录 | `%APPDATA%\MarkdownCardWhiteboardReader`（布局、窗口状态、`settings.json` 主题偏好）、`%LOCALAPPDATA%\...\Cache`（渲染缓存） |

```bash
python -m uv run pytest -q                                   # 全部测试
python -m uv run ruff check . && python -m uv run ruff format --check .
python -m uv run mypy src
python -m uv run python spikes/spike_real_window.py          # 真实平台启动一次（1.5s 自动退出）

# 打包（onedir）与交付形态验证
python -m uv run pyinstaller packaging/mcwr.spec --noconfirm
dist\mcwr\mcwr.exe --self-check                              # 返回码 0 = 打开+公式/Mermaid 出图正常
$env:MCWR_SELF_CHECK_REPORT="$PWD\selfcheck.json"; dist\mcwr\mcwr.exe --self-check   # 报告落到文件
```

> 本机 pip 全局索引指向 `pypi.tuna.tsinghua.edu.cn`，该镜像对 `uv` 包返回 403；
> 依赖安装请使用默认的 pypi.org，或显式指定 `--default-index https://pypi.org/simple`。
> 离线测试无需显示器：`tests/conftest.py` 自动使用 Qt 的 `offscreen` 平台插件。

## 架构

分层 + 垂直切片 + Protocol 依赖倒置；`interfaces → application → domain`，`infrastructure` 实现端口，
`container.py` 是唯一装配点。

```
src/mcwr/
├── domain/          # 纯模型：Block(IR)/Card/CardLayout/BoardSnapshot、stable_key、不变量
├── application/
│   ├── features/    # parse_document · build_card_tree · load_document ·
│   │                # layout_board · detach_restore · persist_layout · refresh_document
│   └── */ports.py   # Protocol：MarkdownReader · BlockParser · SizeEstimator · LayoutStore
├── infrastructure/  # markdown_reader · markdown_it_adapter · heuristic_sizer ·
│                    # json_layout_store(_layout_codec/_atomic) · app_paths
├── interfaces/
│   ├── cli/         # Typer：cards / gui / version（先行垂直切片）
│   └── gui/         # PySide6：board_view · card_item · session(MVVM 边界) · main_window · app
│                    # theme.py：双主题调色板/字体/尺寸（docs/visual-spec.md 的代码形态）
├── shared/          # logging.py · config.py（用户偏好持久化，原子写）
└── container.py
spikes/              # 一次性验证脚本与结论（NOTES.md）
tests/integration/   # CLI 端到端、GUI 冒烟、只读保证
```

### 关键实现要点

- **白板坐标是唯一几何真相**：`CardLayout` 存绝对坐标，卡片的 Qt 父子关系只影响绘制/拖动；
  因此「拖出为自由卡片」不需要坐标系换算，只是解绑 parent（逻辑 `parent_id` 不变）。
- **卡片身份**：`stable_key`（路径哈希+标题路径+类型+序号）跨内容修改稳定；`content_hash` 只做变更检测。
- **只读保证**：读取路径之外没有任何写入；集成测试断言源目录文件集合与 mtime 不变。
- **测试防假绿**：PySide6 会吞掉 Qt 槽内异常，`tests/conftest.py` 安装 excepthook 把这类异常变成测试失败
  （已用一次性探针验证该守卫确实会触发）。

## 只读承诺

应用对源文件及其同目录零写入；日志、缓存、临时文件一律落在应用数据目录。
