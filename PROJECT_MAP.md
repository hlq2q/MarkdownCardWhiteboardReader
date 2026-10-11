# PROJECT_MAP — 项目全貌

- 项目名称：Markdown Card Whiteboard Reader（包名 `mcwr`，分发名 `markdown-card-whiteboard`）
- 状态文件位置：`C:\Users\31094\Projects\MarkdownCardWhiteboardReader`（四件套与代码同根）
- 最后更新：2026-10-12 03:20:00 +08:00

## 1. 项目目标

用户原话：使用 Python 开发一个**仅面向 Windows** 的桌面端 Markdown 增强浏览工具，把 Markdown 解析成卡片并在可缩放白板中展示，支持嵌套、拖动、拆出、还原、手动刷新、多窗口与整体缩放；**源 Markdown 文件仍是唯一内容源，应用只读**，不提供编辑原 Markdown 的功能。

需求与全部已确认决策见 `docs/requirements-spec.md`（决策台账 D1–D15）。本四件套与该文档分工：规格文档记「需求与取值」，四件套记「状态、任务、决策索引与事故」。

## 2. 技术栈

| 项 | 值 | 证据 | 置信度 |
| --- | --- | --- | --- |
| 语言 / 版本 | Python 3.12.10（`py -3.12`） | `python --version`；`py -0p` | 高 |
| 框架（GUI） | PySide6 6.12.0（含 QtWebEngine），QGraphicsScene 原生白板 | `uv sync` 输出；`src/mcwr/interfaces/gui/*` | 高 |
| Markdown 解析 | markdown-it-py + mdit-py-plugins（dollarmath / tasklists）+ `enable("table")` | `src/mcwr/infrastructure/markdown_it_adapter.py:26-34`；`spikes/NOTES.md` Spike 1 | 高 |
| 富内容渲染 | KaTeX 0.19.0 + Mermaid 12.1.0（MIT，随包，`src/mcwr/assets/web/`，5.9 MB） | `src/mcwr/assets/web/LICENSES.md` | 高 |
| 其他运行时依赖 | typer、pydantic-settings、loguru、pygments | `pyproject.toml` dependencies | 高 |
| 运行时 / 包管理器 | uv 0.13.0（本机以 `pip` 安装，命令为 `python -m uv`） | `python -m uv --version`；`uv.lock` | 高 |
| 构建 / 测试工具 | pytest 9.1.1 + hypothesis、ruff 0.17.0、mypy 1.19（strict）、PyInstaller 6.22.3 | `pyproject.toml` dev 组；`uv sync` 输出 | 高 |
| 打包形态 | PyInstaller **onedir**，GUI 子系统（`console=False`） | `packaging/mcwr.spec`；`dist/mcwr/`（581 MB） | 高 |

## 3. 目录结构

> 观测命令：`ls -1`、`find src/mcwr -type f -name "*.py" | sort`、`find tests -type f | sort`
> 观测时间：2026-10-12 02:57 +08:00

```
MarkdownCardWhiteboardReader/
├── PROJECT_MAP.md / TASKS.md / DECISIONS.md / ERRORS.md   # 四件套（本目录）
├── README.md              # 状态表、运行方式、架构要点、只读承诺
├── pyproject.toml         # 单一依赖源 + ruff/mypy/pytest 配置 + console_scripts
├── uv.lock
├── docs/
│   ├── requirements-spec.md   # 需求规格 + 决策台账 D1–D15 + 风险 + 待确认清单
│   └── traceability.md        # 决策→代码→测试 追溯 + 已知缺口
├── packaging/
│   ├── entry_gui.py           # 冻结入口（GUI 子系统）
│   └── mcwr.spec              # PyInstaller onedir 规格（资源/排除项）
├── src/mcwr/
│   ├── domain/            # enums errors ids invariants models（纯模型，零 IO）
│   ├── application/
│   │   ├── features/      # parse_document · build_card_tree · load_document · layout_board
│   │   │                  # detach_restore · persist_layout · refresh_document · render_card
│   │   └── （端口在各 feature 的 ports.py）
│   ├── infrastructure/    # markdown_reader · markdown_it_adapter · heuristic_sizer
│   │                      # json_layout_store(+_layout_codec/+_atomic) · app_paths · web_renderer
│   ├── interfaces/
│   │   ├── cli/           # main.py（cards/version/gui）· views.py
│   │   └── gui/           # app.py · main_window.py · board_view.py · card_item.py · session.py
│   ├── assets/web/        # katex/ · mermaid/dist/ · LICENSES.md
│   └── container.py       # 唯一装配点
├── spikes/                # 一次性验证脚本 + NOTES.md + samples/ + _out/（_out 已 gitignore）
├── tests/
│   ├── conftest.py        # offscreen 平台 + QtWebEngine 预初始化 + 槽异常守卫
│   └── integration/       # test_acceptance.py · test_gui_smoke.py · test_cli_cards.py · test_body_render.py
├── build/ dist/           # PyInstaller 产物（gitignore）
```

## 4. 入口与启动方式

| 项 | 值 | 证据 | 置信度 |
| --- | --- | --- | --- |
| 入口文件（CLI/控制台脚本） | `mcwr.interfaces.cli.main:main` | `pyproject.toml:29`（`[project.scripts]`） | 高 |
| 入口文件（GUI 进程） | `src/mcwr/interfaces/gui/app.py`（`main()` / `run_self_check()`） | 文件内容 | 高 |
| 启动命令（源码） | `python -m uv run mcwr gui <file.md>`；无窗口只读工具：`python -m uv run mcwr cards <file.md> [--format json]` | README「运行」段；实测输出卡片树 | 高 |
| 启动命令（打包产物） | `dist\mcwr\mcwr.exe <file.md>` | 实测启动成功（`spikes/spike_real_window.py` 同路径源码验证） | 高 |
| 验证方式（怎么算跑起来了） | ① `mcwr cards <file>` 打印 `cards=N blocks=M` 与卡片树；② GUI 出现 19 张卡片、fit 后 zoom≈35%；③ `dist\mcwr\mcwr.exe --self-check <file>` **退出码 0** 且报告 `rendered_images == web_cards` | 实测：自检 JSON `{"cards":19,"blocks":25,"web_cards":2,"rendered_images":2,"frozen":true}` | 高 |
| 状态文件（布局）位置 | `%APPDATA%\MarkdownCardWhiteboardReader\boards\<path_hash>\<session>.json` | `src/mcwr/infrastructure/json_layout_store.py`；`docs/requirements-spec.md` §2.5 | 高 |

## 5. 模块 / 文件职责表

| 路径 | 类型 | 职责 | 关键导出 | 依赖 | 被依赖 | 风险 | 阅读优先级 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/mcwr/domain/models.py` | 文件 | Block(IR)/Card/CardTree/CardLayout/Viewport/BoardSnapshot/WindowState 等纯模型 | 同名 dataclass | 无（仅标准库） | application 全体 | 低 | 1 | 高 |
| `src/mcwr/domain/ids.py` | 文件 | `stable_key`（结构键，跨内容修改稳定）与 `content_hash` 生成规则 | `stable_key` `content_hash` `document_path_hash` `normalize_text` | enums | build_card_tree / parse_document | 中：键组成含序号，插入同级卡会改变键（靠 refresh 的二级回退兜住） | 2 | 高 |
| `src/mcwr/domain/invariants.py` | 文件 | 卡片树不变量检查（可达性 / 层级 / 块覆盖不重复） | `tree_problems` `required_block_indexes` | models | load_document / 测试 | 低 | 3 | 高 |
| `src/mcwr/application/features/parse_document/` | 目录 | 读文件 + 解析为块序列；解析失败降级为单块纯文本 | `parse_document` `MarkdownReader` `BlockParser` `SourceText` | domain/ids | load_document | 低 | 4 | 高 |
| `src/mcwr/application/features/build_card_tree/` | 目录 | 分隔线切大卡片 + 标题栈建树 + 稳定 ID（纯函数） | `build_card_tree` | domain | load_document | 中：归属规则是全项目核心语义 | 5 | 高 |
| `src/mcwr/application/features/load_document/` | 目录 | 组合「读+解析+建树」并校验不变量 | `load_document` `LoadedDocument` | parse_document / build_card_tree | container / GUI session | 低 | 6 | 高 |
| `src/mcwr/application/features/layout_board/` | 目录 | 线性初始布局 + 折叠/拆出感知的子树重排 | `layout_board` `relayout_subtree` `LinearLayoutOptions` `SizeEstimator` | domain | GUI session | 中：几何真相唯一在 domain | 7 | 高 |
| `src/mcwr/application/features/detach_restore/` | 目录 | 拆出 / 还原 / 收回子卡 / 全部还原 / 折叠状态机 | `detach_card` `restore_card` `reclaim_children` `restore_all` `toggle_collapse` | domain | GUI session | 低 | 8 | 高 |
| `src/mcwr/application/features/persist_layout/` | 目录 | 快照恢复/持久化用例 + `LayoutStore` 端口 | `restore_snapshot` `persist_snapshot` `LayoutStore` | domain | GUI session | 中：损坏快照必须降级不阻塞 | 9 | 高 |
| `src/mcwr/application/features/refresh_document/` | 目录 | 刷新合并：结构签名（D11 判据）、键匹配 + 内容哈希回退、几何合并 | `plan_refresh` `is_major_change` `match_cards` `merge_layouts` | domain | GUI session | 中：判据语义易被误读 | 10 | 高 |
| `src/mcwr/application/features/render_card/` | 目录 | 判定哪些卡片需要位图 + 提取待渲染源（纯逻辑，无 Qt） | `needs_web_render` `web_source` `card_image` `WebCardRenderer` | domain | GUI main_window | 低 | 11 | 高 |
| `src/mcwr/infrastructure/markdown_reader.py` | 文件 | 只读读字节、编码探测（utf-8-sig/utf-8/gbk/cp1252 → 替换字符降级）、换行统计 | `FileMarkdownReader` | parse_document.models | container | 中：降级路径需保持只读 | 12 | 高 |
| `src/mcwr/infrastructure/markdown_it_adapter.py` | 文件 | token → IR 块（9 类成卡块 + 内容块 + toc 特判 + 图片段落升级） | `MarkdownItBlockParser` `build_parser` | markdown-it-py / mdit-py-plugins | container | 中：依赖第三方 token 形态（Spike 1 已固化） | 13 | 高 |
| `src/mcwr/infrastructure/json_layout_store.py` | 文件 | 会话分片 JSON 快照存储：原子写 + schema 版本 + last_session 播种 | `JsonLayoutStore` | `_layout_codec` `_atomic` app_paths | container | 中：D15 分片语义 | 14 | 高 |
| `src/mcwr/infrastructure/web_renderer.py` | 文件 | 离屏 KaTeX/Mermaid 栅格化：单隐藏视图 + `printToPdf` → `QPdfDocument.render` + 档位缓存，任何失败返回 None | `QtWebCardRenderer` | PySide6(QtWebEngine/Pdf) app_paths | container | **高**：唯一依赖 GPU/Chromium 行为的模块，历史上多次静默错误 | 15 | 高 |
| `src/mcwr/infrastructure/heuristic_sizer.py` | 文件 | 无渲染时的卡片高度估算（文本度量启发式） | `HeuristicSizeEstimator` | domain | container/GUI | 低 | 16 | 高 |
| `src/mcwr/infrastructure/app_paths.py` | 文件 | `%APPDATA%` / `%LOCALAPPDATA%` / 资源目录定位（含测试覆盖变量） | `app_data_dir` `cache_dir` `assets_dir` | 无 | container / 测试 | 低 | 17 | 高 |
| `src/mcwr/interfaces/gui/session.py` | 文件 | MVVM 边界：持有文档+布局，调用用例，暴露 Qt 信号；唯一知道持久化的地方 | `BoardSession` | application 全体 + persist | main_window | 中：串起全部用例 | 18 | 高 |
| `src/mcwr/interfaces/gui/main_window.py` | 文件 | 窗口装配：视图、工具栏、右下角按钮、右键菜单、懒渲染队列、窗口状态 | `MainWindow` | session / board_view / card_item / render_card | app.py | 中：曾是槽内异常被吞的重灾区 | 19 | 高 |
| `src/mcwr/interfaces/gui/card_item.py` | 文件 | 单卡绘制（标题栏/图标/选中态）、受父约束的拖动、可选位图身体 | `CardItem` | PySide6 / domain | main_window | 中：绘制与命中测试耦合 | 20 | 高 |
| `src/mcwr/interfaces/gui/board_view.py` | 文件 | 画布：光标锚定缩放、中键平移、适应视图（缩放上下限夹取） | `BoardScene` `BoardView` | domain.models(Viewport) | main_window | 低 | 21 | 高 |
| `src/mcwr/interfaces/gui/app.py` | 文件 | 进程入口：QtWebEngine 预初始化、`--self-check` 自检、多窗口子进程拉起 | `run` `main` `prepare_webengine` `spawn_new_window` `run_self_check` | container / main_window | `packaging/entry_gui.py` | 中：启动顺序敏感 | 22 | 高 |
| `src/mcwr/container.py` | 文件 | 唯一装配点：构造 reader/parser/store/renderer | `load` `build_web_renderer` `build_layout_store` `new_session_id` | infrastructure | CLI / GUI | 低 | 23 | 高 |
| `packaging/mcwr.spec` | 文件 | onedir 打包规格：资源 data、隐藏导入、Qt 模块排除 | — | PyInstaller | 构建 | **高**：排除项曾误删 QtWebChannel 致打包后渲染失效 | 24 | 高 |
| `tests/conftest.py` | 文件 | Qt offscreen 平台、QtWebEngine 预初始化、**Qt 槽异常守卫**（吞异常→测试失败） | fixture `qapp` / `qt_slot_errors_fail_the_test` | PySide6 | 全部 GUI 测试 | 低 | 25 | 高 |
| `tests/integration/test_acceptance.py` | 文件 | 十项验收标准逐条端到端断言 | 11 个测试 | GUI 全栈 | — | 低 | 26 | 高 |
| `spikes/NOTES.md` | 文件 | spike 1（块分类）与 spike 3（离屏渲染）结论、坑与选型 | — | — | — | 低 | 27 | 高 |

## 6. 依赖关系图

```
interfaces(cli, gui) ──► application(features + ports) ──► domain
                                    ▲
                                    │ 实现 Protocol
                             infrastructure
        container.py ── 唯一装配点（构造 infrastructure 注入 application）
        packaging/entry_gui.py ──► interfaces.gui.app ──► container
```

规则（代码中实际遵守，`docs/requirements-spec.md` §3）：`application` 不 import 任何具体库；`domain` 仅标准库；`infrastructure` 是唯一碰 PySide6 / markdown-it-py / 文件系统的层。

## 7. 建议阅读顺序

1. `README.md` —— 理由：30 秒了解状态、运行方式、只读承诺。
2. `docs/requirements-spec.md` §0（决策台账 D1–D15）—— 理由：所有取值的唯一来源。
3. `src/mcwr/domain/models.py` + `ids.py` —— 理由：卡片/布局/身份的词汇表，其他模块都在说这套话。
4. `src/mcwr/application/features/build_card_tree/service.py` —— 理由：卡片树语义（分隔线/标题栈/归属）的核心。
5. `src/mcwr/application/features/refresh_document/service.py` —— 理由：刷新判据与合并，最容易被误读。
6. `src/mcwr/interfaces/gui/session.py` → `main_window.py` —— 理由：把用例串成窗口的装配顺序。
7. `src/mcwr/infrastructure/web_renderer.py` —— 理由：唯一高风险模块，改动前先读其模块 docstring 与 `spikes/NOTES.md` Spike 3。

## 8. 待补充信息

| # | 缺失信息 | 为什么需要 | 谁来补 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 应用显示名的**具体字符串** | 窗口标题、安装包显示名、开始菜单项 | 用户 | open（D-026 为 proposed：`Markdown Card Whiteboard Reader` vs `MarkdownCardWhiteboardReader`；`%APPDATA%` 目录名 `MarkdownCardWhiteboardReader` 已定不变） |
| 2 | 视觉规范的具体取值 | 界面实现与主题切换 | 代码（T-024） | scheduled：由 D-021 决定产出 `docs/visual-spec.md` 作为唯一来源，取值在该文件定义 |
| 3 | 超限（>200 卡片）降级的具体表现 | T-025 的验收标准 | 用户 | open（见 `TASKS.md` §4 阻塞项 3） |
| 4 | 签名证书文件路径与口令 | 才能执行签名 | 用户 | open（证书已确认具备，路径/口令未提供） |

> 已确认项（不再列为待补）：单文档规模上限 = 200 卡片（D-023）；任务列表单独成卡（D-024）；目录卡片点击跳转纳入下一版（D-025）；代码签名证书具备（D-027）；渲染稳定性为最高优先级（D-022）。

## 9. 文档边界（单一来源）

| 文件 | 主记录 | 不记 |
| --- | --- | --- |
| `PROJECT_MAP.md` | 结构 / 职责 / 入口 / 依赖 / 阅读顺序 | 任务进度、决策理由、错误根因 |
| `TASKS.md` | 目标、里程碑、任务、阻塞、下一步 | 决策理由（引 `D-xxx`）、错误细节（引 `E-xxx`） |
| `DECISIONS.md` | 决策的选项 / 决定 / **理由 / 影响** | 任务细节、错误细节 |
| `ERRORS.md` | 事故的现象 / 根因 / 修复 / 验证 | 通用规则（进 `pitfall-playbook` §13） |
| `docs/requirements-spec.md` | 需求条款与验收标准原文 | 状态与进度 |
| `docs/traceability.md` | 决策 → 代码位置 → 测试名的映射 | 决策理由与影响（一律指 `DECISIONS.md`） |
| `docs/visual-spec.md`（待建） | 视觉取值（配色/字体/尺寸/主题）的唯一来源 | 决策理由（指 `DECISIONS.md` D-021） |
