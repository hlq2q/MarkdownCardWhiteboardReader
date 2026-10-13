# TASKS — 任务与状态

- 最后更新：2026-10-12 17:55:00 +08:00
- 状态枚举：仅 todo / doing / blocked / done

## 1. 当前目标

MVP 已完成并验证（含 PyInstaller onedir 打包与交付形态自检）。当前目标按用户指示「按优先级逐步完成」，优先级顺序为：

**T-016（修掉渲染抖动）→ T-026（渲染稳定性 10 条逐条落地与验证）→ T-024（视觉规范 + 双主题）→ T-025（卡片上限与降级）→ T-021（目录卡片跳转）→ T-020（大纲导航）→ T-019（搜索定位）→ T-017（渲染缓存上限）→ T-031（视口懒加载 + 上限 1000）→ T-018（大文档压测）**

> **T-022（安装包 + 签名）已取消**（D-035，2026-10-12）：本机自用、不发布，不需要安装包与代码签名；编号保留，见 §6。

排序依据：`DECISIONS.md` D-022 规定**渲染稳定性为最高优先级**（冲突时让位于稳定性），T-016 是当前唯一 `open` 的可靠性问题；视觉规范与规模上限是你本轮新下达的要求，排在其后；其余按依赖顺序。

## 2. 里程碑

| # | 里程碑 | 状态 | 完成判据（可读回） |
| --- | --- | --- | --- |
| M1 | 需求与方案冻结 | done | `docs/requirements-spec.md` 含 D1–D15 台账且阻塞项清零 |
| M2 | 技术风险验证（解析 / 离屏渲染） | done | `spikes/NOTES.md` 有 Spike 1 与 Spike 3 结论与实测数字 |
| M3 | 核心逻辑可在无 GUI 环境验证 | done | `mcwr cards spikes/samples/sample.md` 输出 `cards=19 blocks=25` |
| M4 | GUI 可用（拖动/拆出/还原/折叠/缩放/刷新/多窗口） | done | `tests/integration/test_gui_smoke.py` 13 项通过；真实平台启动一次成功 |
| M5 | 十项验收标准全部有端到端断言 | done | `tests/integration/test_acceptance.py` 11 项通过 |
| M6 | 可打包并在交付形态下自证可用 | done | `dist\mcwr\mcwr.exe --self-check <file>` 退出码 0，报告 `rendered_images=2/2`、`frozen=true` |

## 3. 任务表

| ID | 任务 | 状态 | 优先级 | 依赖 | 验收标准 | 预估 | 实际 | 关联决策/错误 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | 冻结需求与方案：输出需求规格 + 决策台账 D1–D15 | done | 高 | 无 | `docs/requirements-spec.md` 存在且 §0.2 无阻塞项 | — | — | D-001..D-015 | commit `24886c8` 之前已完成 |
| T-002 | Spike 1：验证 markdown-it-py 能区分全部所需块类型 | done | 高 | 无 | `spikes/spike_md_blocks.py` 退出 0 且 `spikes/NOTES.md` 有块类型对照表 | — | — | E-001 | 结论：可行 |
| T-003 | 建骨架：uv 环境、pyproject、分层目录、git init | done | 高 | T-002 | `python -m uv run mcwr version` 输出 `mcwr 0.1.0` | — | — | D-016 D-017 D-018 | commit `24886c8` |
| T-004 | domain 层：模型 / 枚举 / 错误 / 身份键 / 不变量 | done | 高 | T-003 | `domain/test_ids.py`、`domain/test_models.py` 全绿；不变量覆盖「块零丢失」 | — | — | E-003 E-004 | commit `24886c8` |
| T-005 | 建卡树：分隔线大卡片 + 标题栈嵌套 + 归属 | done | 高 | T-004 | 15 项单测通过（含层级跳变、重复标题、内容修改不换 ID） | — | — | D-004 D-005 | commit `24886c8` |
| T-006 | 解析切片：只读 reader + markdown-it 适配器 + 降级 | done | 高 | T-004 | 适配器测试覆盖 13 类块；编码探测与只读断言通过 | — | — | E-005 | commit `24886c8` |
| T-007 | CLI 垂直切片：`mcwr cards/version` | done | 高 | T-005 T-006 | `mcwr cards spikes/samples/sample.md` 打印卡片树，退出码 0 | — | — | 无 | commit `24886c8` |
| T-008 | 布局切片：线性初始布局 + 可注入尺寸估计器 | done | 高 | T-005 | 13 项测试：子卡在父卡内、顺序即 y 递增、折叠/拆出感知重排 | — | — | D-006 D-007 D-008 | commit `b773ec8` |
| T-009 | 拆出/还原状态机 + 折叠 | done | 高 | T-008 | 11 项测试：往返幂等、顶层卡拒绝拆出、折叠记住子卡几何 | — | — | D-006 | commit `b773ec8` |
| T-010 | 持久化切片：会话分片 JSON 快照 | done | 高 | T-004 | 35 项测试：字段往返、原子写无残留、损坏降级、新会话不覆盖旧分片 | — | — | D-009 D-015 | commit `5b921ac` |
| T-011 | PySide6 GUI：画布 / 卡片 / 窗口 / 右键 / 右下角按钮 / 多窗口 | done | 高 | T-008 T-009 T-010 | 13 项 GUI 冒烟测试 + 真实平台启动成功（19 卡、zoom≈35%） | — | — | E-002 E-006 | commit `b773ec8` `3ebe944` |
| T-012 | 刷新切片 + GUI 接线（结构优先重建） | done | 高 | T-011 | 42 项切片单测；端到端：改正文保位置、加分隔线/改层级触发重建 | — | — | D-011 | commit `b33296c` |
| T-013 | 十项验收标准端到端断言 | done | 高 | T-012 | `test_acceptance.py` 11 项通过，逐条对应 spec §1.5 | — | — | 无 | commit `b33296c` |
| T-014 | 离屏渲染切片：KaTeX/Mermaid → 位图卡片 | done | 高 | T-011 | 46 项渲染测试通过；App 内实测数学卡出 `E = mc²`、Mermaid 卡出流程图且 md5 不同 | — | — | D-003 D-007 D-014 E-007 E-008 E-009 | commit `0a54bb5` `593105b` |
| T-015 | PyInstaller onedir 打包 + 交付形态自检 | done | 高 | T-014 | `dist\mcwr\mcwr.exe --self-check spikes\samples\sample.md` 退出码 0，`frozen=true`、`cards=19`、`rendered_images=2` | — | — | E-010 E-011 E-012 E-014 | commit `48c7218` |
| T-016 | 定位并修掉 app 路径渲染的偶发抖动（2026-10-12 修复完成） | done | 最高 | 无 | 连续 10 次全量运行 `pytest -q` 中 `test_body_render.py` 不再出现 xfail，且报告 `rendered_images=2/2` | 2–4 h | 4 h | E-013 E-016 E-017 E-018 | 新增判据：**隔离运行与全量运行都必须连续 10 次全绿**；不接受「只在隔离下通过」。回归证据：加入 T-026 改动后全量连续 2 次 `2 failed, 255 passed in 95.02s`，报错 `render failed after a retry: rasterized image is blank`（Mermaid 卡），而同状态隔离运行通过。**实测：隔离 10/10 全绿（20–21 s）+ 全量 10/10 全绿（17–21 s，257 项）**；新增 2 个确定性测试钉住重试梯子（③ 次成功恢复 / 永久空白则在 3 次后放弃）。残留：瞬时触发的根因仍未定位，但失败模式已可自愈且可观测（`stats["retried"]`、`render failed after N attempt(s)`） |
| T-017 | 给渲染缓存加容量上限 | done | 中 | 无 | `QtWebCardRenderer` 在缓存文件数超过上限时按最近使用淘汰 **✅**（上限＝用户给定 **1024** 条；LRU 依据 mtime，缓存命中会刷新 mtime）；新增单测断言「写入 N+1 个后目录文件数 ≤ N」 **✅** | 1–2 h | 0.8 h | D-014 D-039 | 实现：`MAX_CACHE_ENTRIES=1024`（可注入 `max_cache_entries` 便于测试）、`_prune_cache()`（写入成功后触发；**覆盖 E-021 遗留的 `_shell-<digest>.html` 与旧 `_shell.html`**；在用的当前 shell 与 `_page.pdf` 豁免）、`stats["evicted"]` 可观测、失败不抛（多进程同目录下容忍文件已被删）。证据：`test_web_renderer.py` 新增 6 项（默认值钉住/超限淘汰最旧/命中刷新存活/**生产规模 1024+5 → 恰好 1024**/旧 shell 被回收/在用文件豁免/目录不存在不报错）+ 模块 26 项含真实 WebEngine 渲染；全量 `pytest -q` 退出码 0（373 项） |
| T-018 | 大文档性能压测 | done | 中 | 无（用户 2026-10-12：值得做） | 生成 500 与 1000 卡片的合成文档，记录「打开到可交互」与「拖动/缩放帧率」两组实测数字进 `docs/`；若 >2 s 或 <30 fps 则开新任务 | 3–5 h | — | D-040 NFR-2 | 补充口径（T-031 之后 T-018 独有的价值）：①500/1000 卡的拖动/缩放**帧率**；②富内容卡密布时**队列总时长**（T-031 只用记录型 renderer 数过调用，没测真实耗时）；另记录内存/句柄随规模的变化 |
| T-019 | 搜索并定位卡片（V1.1） | done | 中 | 无（用户 2026-10-12 确认纳入 V1.1） | 输入关键字 → 命中卡片居中并高亮 **✅**（工具栏搜索框 + 回车；与大纲/目录卡共用 `_focus_card`）；新增集成测试断言命中卡片 id 与视口中心坐标 **✅**（±2 px）；语义按用户取值：**大小写敏感 + 搜全卡正文** **✅** | 4–6 h | 1.5 h | D-012 D-038 D-037 | 实现：新切片 `search_cards`（`search_cards`/`card_text`/`SearchHit`，纯函数）+ 工具栏 `QLineEdit`；回车循环命中（状态栏"第 k/n 个命中（m 处）· 已定位 X"）、未命中不动视口、换文档清空命中表。证据：`search_cards/test_service.py` 12 项 + `tests/integration/test_search.py` 8 项（标题/正文/大小写/循环/重置/空查询/无文档/空白修剪）+ 真实平台图 `spikes/_out/search_box_{light,dark}.png`；`ruff`/`mypy`（87 文件）干净、全量 `pytest -q` 退出码 0（366 项）。**未做**：正则、忽略大小写开关、结果列表面板、片段预览 |
| T-020 | 大纲导航（V1.1，标题树跳转） | done | 中 | 无（用户 2026-10-12 确认进入 V1.1） | 侧栏列出标题树 **✅**（可停靠 `QDockWidget` + `QTreeWidget`，按 H 级嵌套，可隐藏/可左右停靠）；点击后目标标题卡居中 **✅**（真点击 → 视口中心与卡中心差 ≤ 2 px）；折叠祖先先展开 **✅** | 3–4 h | 1.5 h | D-012 D-037 D-033 | 形态按用户选择＝**可停靠侧栏**；条目与目录卡共用 `BoardSession.toc`，跳转与目录卡链接共用新抽出的 `MainWindow._focus_card`（单实现，避免两套行为漂移）；侧栏随主题着色（`app_bg`/`text_primary`/`selected`）；证据：`tests/integration/test_outline_panel.py` 6 项（结构/第 3 项点击居中 ±2 px/折叠展开/与目录卡一致/刷新跟随/主题）+ 真实平台图 `spikes/_out/outline_panel_{light,dark}.png`；`ruff`/`mypy`（83 文件）干净、全量 `pytest -q` 退出码 0（346 项）。**残留**：dock 的可见性/位置未持久化（窗口几何有持久化），见 §4.2 |
| T-021 | 目录卡片点击跳转（FR-2.4） | done | 中 | 无（D-025 已确认纳入下一版） | 点击目录项后对应标题卡居中 **✅**（`QTest` 真点击 → `view.mapToScene(viewport.center)` 落在目标卡矩形内，且卡片未被拖动）；目标在折叠祖先内时逐级展开并提示 **✅**（F10） | 2–3 h | 2 h | D-025 D-033 | 实现：目录条目由 `build_toc` 按标题树生成（`[TOC]` 处才生成条目，含全部 H1–H6）；卡片内链接经 `QTextCharFormat.isAnchor()` 解析；顺带修两处既有缺陷：目录卡高度按条目数（parser 在块 `attrs` 戳 `toc_entries`）、普通点击不再误发 `moved`。证据：`tests/integration/test_toc_navigation.py` 5 项 + `build_toc/test_service.py` 7 项 + `detach_restore` 3 项 + sizer/adapter 各 2 项；全量 `pytest -q` 退出码 0（314 项） |
| T-023 | 初始化四件套（本次 state-keeper 任务） | done | 高 | 无 | 项目根存在 `PROJECT_MAP.md` / `TASKS.md` / `DECISIONS.md` / `ERRORS.md`；事实均带证据；`docs/traceability.md` 与四件套无重复主记录 | 1 h | 1 h | D-019 D-020 | 本轮完成 |
| T-024 | 视觉规范 + 双主题实现 | done | 高 | 无 | ①`docs/visual-spec.md` 覆盖 D-021 全部条目 **✅**；②对比度经计算 ≥ 4.5:1（AA）、深色无纯黑、浅色无纯白 **✅**（脚本 `spikes/_out/contrast.py` + 单测 `test_theme.py` 钉住发布值）；③主题三态（跟随系统/浅色/深色）可切换且切换后 `CardLayout` **全字段与对象身份都不变** **✅**（`tests/integration/test_theme_switch.py` 6 项）；④深色下代码/公式/Mermaid 可读、缓存键含 theme **✅**（真实深色位图像素断言 + 文本卡像素断言 + `test_the_cache_key_separates_the_two_themes`） | 6–10 h | 4 h | D-021 D-030 D-031 E-019 E-021 | 证据：`ruff` 全绿；`mypy --strict` 76 文件 0 错误；`pytest -q` 退出码 0（**286 项**，较改动前 +27）；`test_web_renderer.py` 17/17（含 2 条真实深色渲染）；深色位图 `spikes/_out/render_card_math_dark_z1.0.png`、`render_card_mermaid_dark_z1.0.png`（已人工过目：深底浅字）。**真实平台**：主题三态切换在 `windows` 插件下实测通过（`spikes/spike_theme_switch_real.py` 退出码 0、布局/对象/文档均未变），但该次渲染失败属环境问题（本机会话 USER 句柄耗尽，既有 spike 同样失败）→ 见 **E-020**，故渲染判据以 offscreen 真实像素为准。**残留**：语法高亮未做、层级色条未做、浅色阴影为 1px 半透明近似（见 §4.1）。**E-021 修复**：真实平台探测发现"升级后页面缺 `mcwrSetTheme`"（渲染页固定文件名被 Chromium 磁盘缓存供了旧版），改为内容寻址 `_shell-<digest>.html` 后，在共享缓存目录 + 旧 `_shell.html` 在场 + 新 payload 的条件下实测 `rendered=1 cache_hits=0 failed=0`、无 TypeError |
| T-025 | 卡片上限与降级模式 | done | 高 | 无（D-029 已定降级表现） | ①解析后暴露卡片总数与超限标记 **✅**（`LoadedDocument.card_count`/`.over_limit`、`BoardSession.card_count`/`.over_limit`）；②超限卡数实测**打开 0.03–0.05 s**（当时上限 200；预算 ≤ 5 s）、item 全在场、状态栏出「超限」提示 **✅**；③覆盖边界（正常，仍走离屏渲染）与超限（降级：**零渲染调用**、按原文绘制、仅一条日志） **✅** | 3–4 h | 1.5 h | D-023 D-029 | **上限值已于 2026-10-12 由 D-040 提高为 1000；本行的机制与证据不受影响（边界与超限两侧现按 1000/1001 复测）**。证据：`tests/integration/test_card_limit.py` 4 项 + `load_document/test_service.py` 3 项（含 `MAX_CARDS` 钉值）；计时工具入库 `spikes/spike_card_limit_timing.py`（可复跑）；文档由测试内脚本合成 |
| T-026 | 渲染稳定性 10 条逐条落地与验证 | done | 高 | T-016 | 对 D-022 的 10 条各给一条可读回证据 | 6–10 h | 3 h | D-022 E-016 E-017 | 10 条证据齐（详见备注） |
| T-027 | 收敛 docs/traceability.md 与四件套边界 | done | 中 | 无 | traceability 只保留「决策 → 代码位置 → 测试名」映射与验收映射；理由/影响一律指向 `DECISIONS.md` | 0.5 h | 0.5 h | D-021 之后 | 本轮完成 |
| T-028 | 卡片左侧 3 px 层级色条（4 档，取值见 D-032） | done | 中 | 无 | 左侧 3 px 色条按嵌套深度取 `docs/visual-spec.md` §6.1 的 4 档值 **✅**（浅 `#D0D7DE/#AFB8C1/#8C959F/#6E7781`、深 `#30363D/#484F58/#6E7681/#8B949E`）；浅/深各一套 **✅**；第 5 级及更深沿用第 4 档 **✅**；测试断言「深度→颜色」映射、3 px 宽度、两套主题取值互不相同 **✅** | 1–2 h | 0.8 h | D-032 D-021 | 实现：`Palette.level_bar`（4 档/主题）+ `theme.level_bar_colour()`（≥4 夹取）+ `card_item._draw_depth_bar`（裁剪到圆角，边线画在其上）；**深度口径 = 卡片树祖先数 + 1**（写入 spec §6.1，不按 H 级）；`main_window._rebuild_items` 传 `depth`。证据：`test_level_bar.py` 4 项（像素级：每档颜色/3 px/切主题变色/第 5 级同色）+ `test_theme.py` 3 项（取值钉住/夹取/常量）；真实平台出图 `spikes/_out/depth_bars_{light,dark}.png`；`ruff`/`mypy`（83 文件）干净、全量 `pytest -q` 退出码 0（340 项） |
| T-029 | 代码卡片语法高亮（Pygments） | done | 中 | 无 | `QTextDocument` 渲染路径按主题选用两套 Pygments 样式 **✅**（浅 `default` / 深 `monokai`，作为 `Palette.pygments_style` 槽位）；浅/深下关键字/注释/字符串可区分 **✅**；两套样式不同、深色下关键字与代码块底色对比度 ≥ 4.5:1 **✅**（实测 9.36，另两类 4.80/10.84） | 2–4 h | 1.5 h | D-032 D-036 E-022 | 证据：`pygments_highlighter.py` 8 项 + `code_highlight.py` 3 项（含"命中块不得有围栏"与像素级颜色数断言）+ `render_card` 新增 6 项围栏测试 + `test_theme.py` 样式槽位；真实平台截图 `spikes/_out/code_card_{light,dark}.png`；spike 结论见 `spikes/NOTES.md`。**过程修复**：新路径暴露"代码卡画出围栏"（E-022），已把拆围栏收敛为 `strip_fenced_block` |
| T-030 | 落地显示名 `MarkdownCardWhiteboardReader` | done | 中 | 无（原挂靠 T-022，已取消） | 窗口标题与 README 标题统一为 `MarkdownCardWhiteboardReader` **✅**；测试断言标题字符串，且断言它与 `app_paths.APP_DIR_NAME` 同步 **✅** | 0.5 h | 0.3 h | D-026 D-035 | 实现：`mcwr.PRODUCT_NAME` 单一常量（`__init__.py`），窗口标题两处 + CLI `--help` + README 标题引用它（可执行文件名仍为 `mcwr.exe`）；新增 `test_gui_smoke.py::test_the_window_title_uses_the_product_display_name`（含与目录名同步的断言）；真实 CLI 实测 `mcwr --help` 显示新名；`ruff`/`mypy --strict`（80 文件）干净、全量 `pytest -q` 退出码 0（315 项） |
| T-031 | 视口懒加载（NFR-3 长期解法）+ 上限 200 → 1000 | done | 高 | 无（用户 2026-10-12 选定：懒加载 + 提到 1000 + 缩小门槛） | ①只对视口（外扩半屏）内、且屏上宽度 ≥ 160 px、且未被折叠祖先隐藏的公式/Mermaid 卡发起渲染 **✅**；②滚动/缩放稳定后重算队列（缩放 400 ms、滚动 180 ms），队序＝离视口中心由近到远 **✅**；③大文档实测：渲染调用集合 === 视口候选集合、视口外的卡零调用；1000/1001 卡实测打开 **0.31 s / 0.28 s**（预算 ≤ 5 s）**✅**；④`MAX_CARDS = 1000`，1000 卡不降级 / 1001 卡降级 **✅**；⑤内存位图上限 256（视口内的永不释放）**✅** | 4–6 h | 2.5 h | D-023 D-029 D-039 D-040 NFR-3 | 顺带修掉旧浪费：折叠区域内的卡不再被排队渲染。证据：`tests/integration/test_viewport_lazy_render.py` 7 项（fit 缩小下零渲染/只渲邻域/最近优先/滚动到位才渲/折叠卡不渲/内存释放/门槛钉值）+ 计时工具实测 1000 卡 0.31 s、1001 卡 0.28 s；按新语义修正 4 个旧测试的前置条件（`test_card_limit`/`test_body_render`/`test_render_stability`/`test_theme_switch`）；`ruff`/`mypy`（87 文件）干净、全量 `pytest -q` 退出码 0（**380 项**）。**非目标**：不虚拟化 QGraphicsItem、不改渲染器内部、不动 1024 缓存上限 |
| T-032 | 侧栏收起（按钮 + 快捷键）；dock 状态不持久化 | done | 中 | 无（用户 2026-10-12：不持久化；侧栏可用收起键收起） | ①侧栏内有**可见的收起控件**，点击即收起（隐藏）**✅**；②有**快捷键**可切换（Ctrl+B）**✅**；③收起后仍能一键恢复（工具栏「大纲」与快捷键同步）**✅**；④**不做** dock 可见性/位置持久化（用户选定"否"）**✅**；⑤测试断言：点击收起按钮后 dock 不可见且状态栏有提示、快捷键切换、收起后恢复 **✅** | 0.5–1 h | 0.8 h | D-037 D-041 E-023 | 形态由我定并写入 D-041（按钮文案「收起」+ `Ctrl+B`）；两种读法都覆盖，若只保留其一删一行即可。证据：`test_outline_panel.py` 增 2 项（按钮点击→隐藏+状态栏、`Ctrl+B` 双向切换+action 勾选态同步）+ 2 处样式断言（`QToolButton#outlineCollapse` 与主题色）；真实平台逐按钮裁剪图 `spikes/_out/outline_collapse_button_{light,dark}.png` 肉眼确认可读（亮度极差 204/203），整窗图与收起态图同目录；**过程中发现并修掉 E-023**（按钮未随主题配色，深色下浅底浅字）；全量 `pytest -q` 退出码 0（382 项） |
| T-053 | 代码/表格/图表元素到卡片四边距离一致（上下按左右对齐） | doing | 中 | 无（用户 2026-10-12："代码或表格,图表的元素上下和左右边缘,距离卡片边缘,宽度相同,并且上下以左右为标准调整"） | ①代码卡与表格卡的元素四边距离 **10/10/10/10**（修前 左10 右10 **上4 下16**）**✅**；②文字卡/列表卡同样满足（回归测试遍历全部可测量卡片）**✅**；③`ruff`/`mypy`/`pytest` 全绿 **✅** | 1h | 0.5h | — | 正文矩形上边从 `HEADER_HEIGHT` 改为 `HEADER_HEIGHT + PADDING`、高度去掉 2×PADDING；文档自身 4 px 边距 + PADDING 6 = 四边 10 px；正文高度仍精确等于测量高度（盒子预留 header + 测量 + 2×PADDING） |
| T-050 | 收紧卡片间距（下内边距 12→6、子卡间距 16→8） | done | 低 | 无（用户 2026-10-12 回答间距问题时选择"收紧到28px"） | ①父卡→首个子卡间距 **40 → 20 px**（实测；比选项里估的 28 px 更紧，因为文档行尾余量比预估小）**✅**；②无子卡卡片的 slack 归零（正文与盒子精确吻合）**✅**；③`ruff check` 0 / `ruff format --check` 合规 / `mypy src` 0 / `pytest` 全绿 **✅** | 0.5h | 0.5h | — | 改 `LinearLayoutOptions.padding 12→6`、`gap 16→8`，并且**同时**把 `theme.PADDING 12→6`（正文内缩）——两者必须一起改，否则盒子比正文短 12 px（实测 slack = −12）；`test_stack.py` 常量同步为 ROW=86/GAP=8 且字面量改由常量推导 |
| T-049 | 修复 E-029：卡片高度回测闭环（父卡/代码卡留白、长表格被裁） | done | 高 | 无（用户 2026-10-12 三条反馈："父卡片内文本结束后与子卡片的间隔太大"／"代码卡片代码部分结束之后下面留下的空白太多,检查其他卡片有没有这个问题"／"表格未能正常显示,比较长的表格只显示前面行,保证所有表格行都能显示"） | ①无子卡的卡：布局高度 == 34 + 2×12 + **真实渲染高度**（代码卡 174→130、标题卡 98→82、长表格卡 406→470 且全部行可见）**✅**；②正文不再被裁（`measured ≤ 卡片高度 − header − 2×padding`）**✅**；③各类父卡→首个子卡间距统一（40 px，原 56/36/36）**✅**；④结构重排／"全部还原"不再把测量值打回估算值 **✅**；⑤拖出+还原 round-trip 精确 **✅**；⑥`ruff check` 0 / `ruff format --check` 合规 / `mypy src` 93 文件 0 错误 / `pytest` 全绿 **✅** | 3h-5h | 4h | E-029 | 补上"渲染后回测"闭环（`measured_body_height` → `adopt_measured_heights` → `MeasuredHeightEstimator`）+ 估算器不再计标题行；测量重排时附着子卡按规则重排（其位置不是用户状态）；公式/Mermaid/图片卡正文是渲染图，继续用估算值；更新 4 处"不可能状态"旧断言 |
| T-048 | 卡片网格吸附（40 px、左上角、松手时 ≤12 px、默认开＋工具栏开关） | done | 中 | 用户 2026-10-12 追加需求："卡片增加网格吸附功能"（四项取舍经用户确认，见 D-051） | ①步长与绘制网格同值（测试断言 `grid.GRID_STEP == theme.GRID_STEP`）**✅**；②距格线 5 px 松手 → 落到格点；同一次落点另一轴距格线 20 px → 原地不动（各轴独立）**✅**；③关掉开关后同一次拖动保留落点（≈45.5，不吸到 40）**✅**；④开关默认开启且可勾选 **✅**；⑤`ruff check` 0 / `ruff format --check` 133 文件合规 / `mypy src` 91 文件 0 错误 / `pytest` **434 passed / exit 0** **✅** | 1.5h-2.5h | 1.5h | D-051 | 吸附实现为纯函数 `snap_to_grid` + `session.move_card(snap=)`，UI 只传开关状态；开关状态不持久化（未要求） |
| T-047 | 锁定 mypy / pytest 版本，避免同类漂移 | done | 低 | 无（用户 2026-10-12："也锁 mypy / pytest 以免同类漂移"） | ①`pyproject.toml` dev 组改为 `mypy==2.4.0`、`pytest==9.1.1`，`uv lock` 成功、`uv.lock` **只改这两行 specifier** **✅**；②`uv sync --frozen --dry-run` exit 0，只列"重装本项目自身"（依赖已一致）**✅**；③`ruff check` 0 / `ruff format --check` 131 文件合规 / `mypy src` 0 错误 / `pytest` **423 passed / exit 0**；版本确认 `mypy 2.4.0`、`pytest 9.1.1` **✅** | 0.5h | 0.5h | — | 与 T-042（锁 ruff）同一动机：判定"过/不过"的工具版本漂移会让同一份代码在不同时间得到不同结论。**未锁**：`hypothesis` / `pytest-cov` / `pyinstaller`（用户只要求 mypy 与 pytest） |
| T-046 | 修复：拖出+还原后末尾兄弟卡片错位（几何应用顺序） | done | 高 | 无（用户 2026-10-12 反馈："子卡片通过右键选项拖出后再通过右键选项回到原来在父卡片中的状态,会出现多个子卡片位置错位的情况…右键子卡片或刷新后又正常显示了"） | ①四兄弟场景 `detach(B)` → `restore(B)` 后逐卡 `item.scenePos() == layout`（修复前末位兄弟 D 停在旧 y：布局 630 / 界面 516）**✅**；②子卡 y 上下关系不变、不重叠（布局由布局引擎保证，界面与布局一致即不重叠）**✅**；③不再需要"右键或刷新"纠正 **✅**；④`ruff check` 0 / `ruff format --check` 131 文件合规 / `mypy src` 0 错误 / `pytest` **423 passed / exit 0** **✅** | 1h-2h | 1h | E-028 | 根因：`_Placer.place()` 先存子卡后存父卡 → 布局映射是**后序**，`_relayout_from` 按该顺序发 `cards_changed`，`_apply_geometry` 逐卡 `setPos` 时父卡的位置/高度仍是旧值 → 末位子卡被旧高度夹死（实测 local 456 被夹成 342）。修法：`_apply_geometry` 恒按 `tree.ordered_ids()`（父先子后）处理，不信任传入顺序。新增回归测试 `test_detach_and_restore_keep_every_item_on_its_layout` |
| T-045 | `Packaging.bat` 增加"应用运行中"预检 | done | 中 | 无（用户 2026-10-12："顺手给 bat 加一次『检测到运行中就先提示退出』的预检"） | ①应用运行时执行 `Packaging.bat` → 打印明确提示并**在第一步前就退出**（exit 1），不再走到 `uv sync` 的 `Access is denied` **✅**；②没有运行时正常放行（真实整跑打印 `pre-flight: no running mcwr.exe`，五步全过、产出安装包 155,973,082 字节）**✅**；③`/nosync` 跳过预检与同步 **✅**；④`Packaging.bat /?` 仍 exit 0 **✅** | 0.5h | 0.5h | E-025 | 预检用 `tasklist /fi "imagename eq mcwr.exe" /nh /fo csv` + `findstr /i`，命中即提示并 `goto :fail`；`/nosync` 时整段跳过。两个分支的 cmd 语法用等价临时脚本实测（命中 → exit 1、未命中 → exit 0），正式脚本的放行路径由那次真实整跑验证。README 打包小节加"先关掉正在运行的 mcwr"提示。**已验证（真实场景，2026-10-12 本轮）**：应用正在运行时执行脚本 → 打印运行中提示并 exit 1、未进入任何构建步骤；应用未运行时 → 打印 `pre-flight: no running mcwr.exe` 并五步全过 |
| T-044 | 修复 E-027：按标题栏拖动会拖走背后的顶层大卡片 | done | 高 | 无（用户 2026-10-12："修复E-027"） | ①标题栏按下 → 移动的是**该卡片**（局部 y 扫描 0–60 全部命中前景卡），背后的顶层卡**零位移** **✅**；②冻结卡的标题栏按下 → 零位移且只选中 **✅**；③正文区拖动行为不变（仍由 Qt 处理，y=200 命中 P）**✅**；④`ruff check` 0 / `ruff format --check` 131 文件合规 / `mypy src` 0 错误 / `pytest` **422 passed / exit 0** **✅** | 2h-3h | 2h | E-027 | 根因未能定位到 Qt 内部（实测跳过带 34–38 px；已排除 `NoIndex`／显式 `shape()`／`NoCache`／预热 move）；可查接口在同一落点（`scene.items` 四种调用、`view.itemAt`、`contains`、`shape().contains`）全部只列出前景卡，而投递给了背后卡 → 改为**视图层兜底**：按标题栏先接住（可移动卡由视图驱动拖动、冻结卡只选中），Qt 未抓住该卡时再接管同一条路径。新增两项集成测试 |
| T-043 | 冻结附着子卡：父卡内的相对位置不可拖动，只能随父卡移动 | done | 高 | 无（用户 2026-10-12 反馈 + 明确取舍："在父卡内部的相对位置完全冻结,只能跟随父卡移动"；同时裁决："父卡高度不得低于打开时高度"作废、T-036 保留） | ①附着子卡在**真实鼠标事件**下零位移（从正文区按下并下移 120 px，布局与 item 位置都不变），且 `session.move_card` 对附着卡的调用被忽略 **✅**；②自由卡仍可拖动且其附着子树同步跟随（真实拖动 60 → 128；子树位移与之逐位相等）**✅**；③子卡不再可能盖住父卡内容（冻结后子卡只可能待在标准槽位，测试逐个断言 `child.y ≥ parent.y + 标题栏高`）**✅**；④结构性缩高不受影响：拖出后 P 326→212、G 440→326、H 上移 114（原有测试继续通过）**✅**；⑤`ruff check` 0 / `ruff format --check` 131 文件合规 / `mypy src` 0 错误 / `pytest` **419 passed / exit 0** **✅** | 2h-4h | 2h | D-050 E-026 E-027 | 实现：`CardItem.set_movable()` + 默认冻结；`_apply_geometry` 只对自由卡/顶层卡开标志，并同步 `item.layout_state`；`session.move_card` 重写（附着卡忽略 + 子树跟随）；`stack.move_subtree` 新增、`resolve_overlaps` 去掉无用的 `dropped`。**排查中发现并修掉**：E-026（item 持有过期 `CardLayout` → 夹取按旧 `detached` 判断）。**发现但未修（既有行为）**：E-027（按标题栏拖动会拖走背后的顶层大卡片）——见 §5 待确认。取代 D-045 第 3/4 条与 D-048 的手动贴合部分 |
| T-042 | 锁定 ruff 版本（`ruff==0.17.0`）避免格式再次漂移 | done | 低 | 无（用户 2026-10-12："是否锁定 ruff 版本：是"） | ①`pyproject.toml` dev 组改为 `ruff==0.17.0`，`uv lock` 成功（`uv.lock` 仅 1 行：specifier `>=0.6.0` → `==0.17.0`）**✅**；②`uv sync --frozen --dry-run` **exit 0**，只列出一项待办＝重装本项目自身，依赖已一致、ruff 仍 0.17.0 **✅**；③`ruff check` 0、`ruff format --check` 131 文件全合规、`mypy src` 0 错误、`pytest` **424 passed / exit 0** **✅**；④真跑 `uv sync`（非 dry-run）**当前不可验证**：你的应用实例（`mcwr` PID 36964 + `.venv` python PID 34120）锁住了 `Scripts\mcwr.exe`，`uv sync` exit 2 —— 与锁版本无关，见 **E-025** | 0.5h | 0.5h | D-049 E-025 | 触发原因：T-038 修掉的 31 文件格式漂移疑似 ruff 版本演进所致（`ruff>=0.6.0` 在不同时间 `uv sync` 会装到不同版本的格式化器）。**注意**：`Packaging.bat:84` 把 `uv sync` 当闸门 → **打包前必须先关闭正在运行的 mcwr** |
| T-041 | 父卡底边始终贴合最低附着子卡（每次松手收紧/长大） | done | 中 | 无（用户 2026-10-12 试用补充："AB卡片在父卡片内部调整时,父卡片底边始终与最低子卡片底边重合"；并选定"每次松手都收紧；保持不能拖出父卡边界"） | ①子卡移动后父卡底边 = 最低附着子卡底边：探针三态 **delta 全为 0**（500/500、440/440、470/470；修前留白 174 px）**✅**；②祖先链同步（G 高、H 位置跟着走）**✅**；③被推下时父卡随之长大 **✅**；④折叠父卡不动、无附着子卡不动、游离卡不参与 **✅**；⑤`ruff check` 0 / `ruff format --check` 131 文件合规 / `mypy src` 0 错误 / `pytest` **424 passed / exit 0** **✅** | 1h-2h | 0.5h | D-048 | 根因：`resolve_overlaps` 只在检出重叠时**长大**盒子、从不收紧；`move_card` 在没有重叠时完全不碰盒子。修法：新增 `hug_children` / `hug_all`（收紧或长大都走 `propagate_height` 上传），接到 `move_card`（先修重叠再收紧）、`_relayout_from`、`_apply_layouts`。FR-3.4 的夹取未改 |
| T-040 | 画布四周留可平移余量：中键能左右平移 | done | 中 | 无（用户 2026-10-12 试用反馈："中间拖动视只能上下平移,而无法左右平移"；并在选项中选定"给画布四周留可平移余量"） | ①100% 缩放时水平滚动范围 **0 → 960**（纵向 386 → 1426），中键横向拖动 ±240 px 精确跟手 **✅**；②上下方向同样有余量且 1:1（±180 px）**✅**；③`fit_cards`（`Ctrl+0`）仍只框住卡片：它用 `itemsBoundingRect`，不读场景矩形 **✅**；④`ruff check` 0、`ruff format --check` 131 文件合规、`mypy src` 0 错误、`pytest` **416 passed / exit 0** **✅** | 1h-2h | 0.5h | D-047 | 根因：从未调用 `setSceneRect`，场景范围恒等于卡片包围盒；文档只有 960 宽而视口 1642 宽 → 水平滚动范围实测 **0**（纵向 386），物理上无处可平移。修法：`refresh_scene_rect()` 把场景矩形按"四周各一屏（≥600 px）"扩边，在窗口 resize 与 `_apply_geometry` 后调用 |
| T-039 | 修正残留字样：`traceability.md` 的 NFR-2 行 + TASKS §5 两条已失效备注 | done | 低 | 无（用户 2026-10-12："一并改掉"） | ①`docs/traceability.md` NFR-2 行改为 T-033 之后的实测值（46.6 → **1.8–3.7 ms / 270–555 fps**）且状态 **✅ 达标** **✅**；②TASKS §5 两条"尚未闭环的非任务痕迹"改为**已闭环**并写明各自结论 **✅**；③D-045 遗留项按用户答复"①不动"标为已闭环（校正而非删除）**✅** | 0.5h | 0.5h | D-045 | 用户在 T-035 交付后提出；核对确认 `traceability.md:37/:75` 的字样早已更新，只是 TASKS 里的备注没关掉 |
| T-038 | 统一代码格式（`ruff format .`）：修掉仓库既有不合规文件 | done | 低 | 无（用户 2026-10-12："单开一个任务统一格式化"） | ①`ruff format --check .` → **131 files already formatted, exit 0**（格式化前 32 个不合规）**✅**；②`ruff check .` 仍 0 违规 **✅**；③`mypy src` 89 文件 0 错误 **✅**；④`pytest` 仍全绿 **415 passed / exit 0** **✅** | 0.5h-1h | 0.5h | — | commit `b219ba9`（33 文件、+160/−141，纯格式无行为改动）。背景：README:73 把 `ruff format --check .` 列为必跑检查，但 HEAD 上有 31 个文件不合规（用工作区同一个 `ruff 0.17.0` 对 `git show HEAD:…` 复检同样失败 → 既有漂移，非本轮引入）；`pyproject.toml` 只写 `ruff>=0.6.0` 未锁版本。**未做**：未锁 ruff 版本（要不要锁由用户定） |
| T-037 | 中键拖动平移视图 | done | 中 | 无（用户 2026-10-12 原话："按住鼠标中键可以拖动视图"） | ①中键按住拖动 → 视图 **1:1 跟手**平移（滚动条位移 = 鼠标位移；单测实测 6 步 −240/−180 px，反向拖回原位）**✅**；②平移期间不选中、不移动任何卡片 **✅**；③左键框选与卡片拖动完全不变（`dragMode` 恒为 `RubberBandDrag`）**✅**；④平移时光标"抓手"、松开恢复箭头 **✅**；⑤`ruff check` 0、`mypy src` 89 文件 0 错误、`pytest` **415 passed / exit 0** **✅** | 1h-2h | 0.5h | D-046 | 现状曾是**假功能**：`mousePressEvent` 只把 `dragMode` 切成 `ScrollHandDrag` + 换光标，而 Qt 自带的 ScrollHandDrag **只认左键**、本类又**没有 `mouseMoveEvent`** → 实测中键拖 6 次滚动条纹丝不动（499/2140 不变）；裸视图受控对照：左键 2608→2848、中键 2848→2848。全仓无任何测试覆盖。**修法**：自实现平移（消费按下事件 + 按增量调两条滚动条，只应用整数部分防漂移），不再切换 `dragMode`。新增 `tests/integration/test_middle_pan.py` 6 项。README 第 54 行原有承诺由此变成真的 |
| T-036 | 紧凑化布局：拖出/还原时祖先链逐级缩高 + 同级卡片永不重叠 | done | 高 | 无（用户 2026-10-12 原话："A卡片被拖出时,父卡片及其更高层级的卡片均自动调整高度"、"父卡片内出现重叠情况就自动调整上下位置至不重叠"、"B被拖到A头上时,调整后B上A下"） | ①拖出 A：P 高 326→212、**G 高 440→326**、H 由 516 上移到 **402**（实测四值全中）**✅**；②还原 A：排列逐位回到离开前（P 326、G 440、H 516、A 288、B 402）**✅**；③两张都未脱离时把 B 拖到 A 头上松手 → **B 288 / A 402（B 上 A 下）**且不重叠 **✅**；④把 A 拖到 B 头上 → A 在上、B 下移、祖先跟着长高 **✅**；⑤已经清晰的手动位置不被修正（只修重叠）**✅**；⑥`ruff check` 0、`mypy src` 89 文件 0 错误、`pytest` **409 passed / exit 0** **✅** | 2h-4h | 1h | D-045 | 实现：新增 `layout_board/stack.py`（`propagate_height` 祖先链 + `resolve_overlaps` 不重叠 + `shift_subtree`），`session.py` 三处接线（`_relayout_from` / `move_card` / `_apply_layouts`）。测试：`test_stack.py` 11 项 + `tests/integration/test_layout_stack.py` 6 项。**看图发现并修掉一个真 bug**：重叠修正时父卡长高的量原先按"拖动后的当前栈底"算，导致 B 拖回自己原槽位也让 P/G 凭空多长 114 px（第一版 `spikes/_out/stack_after_drop_t036.png` 能直接看到空白），改为按**父卡盒子底边**算"伸出多少才长多少"。**未做**：拖出瞬间游离卡 A 仍停在原坐标（B 已上移到该处），二者此时重合 —— 见 §5 待确认 |
| T-035 | 悬浮按钮（刷新 / 全部还原）贴合画板区右下角 | done | 中 | 无（用户 2026-10-12 原话："将右下角的刷新和全部还原放到更靠近右下角的位置"） | ①按钮到**画板区**右下角 = **18 px**（`_gap()` 精确相等断言）**✅**；②窗口缩放 / 收起侧栏 / 加宽侧栏后仍 = 18 px **✅**；③不遮挡滚动条：`OVERLAY_MARGIN` 18 > 垂直滚动条 `sizeHint` 14 **✅**；④`ruff check` 0 违规、`mypy src` 87 文件 0 错误、`pytest` **392 passed / exit 0** **✅** | 0.5h-1h | 0.5h | D-044 | 根因：`_overlay` 是**窗口**子控件却只用 `central.width()/height()` 定位，漏加中央控件原点——实测 280−18 = **262 = `central.x()`**、48−18 = **30 = `central.y()`**，两向吻合。修法：按 `centralWidget().geometry()` 锚定 + 给 `view` 装 `QEvent.Type.Resize` 事件过滤器（侧栏改变画板几何但**不触发**窗口 `resizeEvent`）。新增 `tests/integration/test_overlay_position.py` 5 项，**先在旧代码上跑：4 项失败并打印 `QPoint(280, 48)`**；前后对比图 `spikes/_out/overlay_corner_{before,after}_t035.png`（gitignore 内，不入库） |
| T-034 | 生成 setup.exe 安装包 + `Packaging.bat`（含"项目改动后仍可用"） | done | 中 | 无（用户 2026-10-12 要求；Inno Setup 已安装） | ①`Packaging.bat` 一键：读版本 → 重建 `dist\mcwr` → 交付形态自检 → 调 `ISCC` 出 `setup.exe`，任一步失败即非零退出；②**版本单一来源**（读 `mcwr.__version__`，并与 `pyproject.toml` 交叉校验，不一致即失败）；③**路径不依赖当前目录/不带空格假设**（相对 `.iss` 定位 `..\dist\mcwr`，脚本自 `%~dp0` 定位仓库根）；④**ISCC 自动探测**（环境变量 → `where` → 注册表 → 常见路径）；⑤重新打包**升级既有安装**而不是并存（固定 `AppId`）；⑥`/nobuild`、`/fast`、`/verify` 开关，且 `/verify` 能真装一次并跑 `--self-check` | 2–3 h | — | D-035 D-043 | 签名仍不做（本机无证书，D-035 的签名部分继续取消）；安装形态＝**默认按用户安装（免 UAC）**，`/ALLUSERS` 可选机器级 | ①总览缩放的整视口重绘从 43–47 ms 降到 ≤15 ms **✅ 实测 1.8–3.7 ms（270–555 fps）**；②阅读缩放（≥100%）**像素零变化** **✅**（100% 整屏重绘 8.8 → 8.2 ms，背景像素统计一致）；③门槛不发明第二套无谓阈值 **✅**（卡片绘制未改；新增的是**另一个量纲**的 `MIN_GRID_DEVICE_STEP = 8.0` 设备像素） | 2–3 h | 2 h | T-018 D-042 E-024 | **交付与立项时的方案不同，必须记住**：原方案"缩得太小的卡不画正文"（沿用 160 px）实现后**实测零改善**（47.1 vs 47.0 ms）→ 代码已**回退**。真正原因是 `BoardScene.drawBackground` 的网格：fit 下暴露 11240×8460 场景单位、`GRID_STEP=40` ⇒ **492 条贯穿全屏抗锯齿长线 ≈ 40 ms**（`CacheBackground` 45.9→3.8 ms、空场景 0.7 ms、隐藏全部卡片仍 42.8 ms 三条证据）。修复＝网格设备像素间距下限；新增测试 `tests/integration/test_grid_detail.py` 5 项 + 前后对比图 `spikes/_out/grid_floor_{before,after}.png`（像素统计：before 3 色含网格色、after 仅 1 色）。全量 `pytest -q` 退出码 0（386 项） |
| — | **T-026 的 10 条证据**（下表为 T-026 行的展开，不单独编号） | | | | | | | |
| ① | 分层：`domain`/`application` 不依赖 Qt 与具体库 | | | | `tests/integration/test_render_stability.py::test_item_1_application_and_domain_do_not_import_gui_or_libraries`（并断言扫描到 ≥20 个文件，防空跑通过） | | | | |
| ② | 错误隔离：单卡渲染失败不影响整板 | | | | `tests/integration/test_body_render.py::test_a_failing_renderer_degrades_to_text_without_crashing` | | | | |
| ③ | 成熟库清单（不造轮子） | | | | `docs/render-stability.md` + `::test_item_3_the_mature_library_inventory_is_recorded` | | | | |
| ④ | 异步渲染 + 可见占位符 | | | | `card_item._draw_pending_badge` + `::test_item_4_a_card_shows_a_placeholder_while_its_image_is_pending` | | | | |
| ⑤ | 缓存/异常自动降级重试 | | | | `web_renderer._render` 空白栅格重试一次 + `stats["retried"]`（E-017） | | | | |
| ⑥ | 连续刷新 20 次不闪退/白屏/卡死 | | | | `::test_item_6_twenty_consecutive_refreshes_stay_stable` | | | | |
| ⑦ | 多窗口渲染隔离 | | | | `::test_item_7_a_failing_window_does_not_affect_another_window` | | | | |
| ⑧ | 资源管理（失败不无限重试、不泄漏视图） | | | | `shared_renderer` 单例 + `views_created() <= 1`（E-016）；`stats["failed"]` / `failures` 计数 | | | | |
| ⑨ | 关键错误写日志 + 状态栏文案 ≤ 40 字 | | | | `shared/logging.py`（`%LOCALAPPDATA%\...\logs\mcwr.log`）+ `::test_item_9_failures_are_logged_and_the_status_text_stays_short` | | | | |
| ⑩ | 性能底线（100 卡片级可接受） | | | | 冷渲染两卡 17.2 s、`PERF_CEILING_S = 60`、全量套件 17.28 s / 257 项 | | | | |

## 4. 阻塞项

| # | 阻塞内容 | 阻塞的任务 | 需要谁 / 什么 | 记录日期 |
| --- | --- | --- | --- | --- |
| — | **无阻塞项**（原阻塞项 1「代码签名材料」随 T-022 取消而撤销，见 D-035） | — | — | 2026-10-12 |

> 已解除：显示名字符串（D-026 = `MarkdownCardWhiteboardReader`）、超限降级表现（D-029 = 停止离屏渲染富内容 + 原文 + 提示）。

### 4.1 遗留项处理结果（用户已于 2026-10-12 答复，见 D-032）

| # | 遗留项 | 你的答复 | 落地 |
| --- | --- | --- | --- |
| 1 | 代码语法高亮（visual-spec §5） | 「需要」 | 已开任务 **T-029**（Pygments 两套样式） |
| 2 | 层级色条 4 档取值（visual-spec §6） | 给出中性灰蓝 4 档、浅深各一套，第 5 级及更深沿用第 4 档 | 取值写入 `docs/visual-spec.md` §6.1；已开任务 **T-028** |
| 3 | 浅色阴影模糊度 | 「不需要」 | 保持 1 px 偏移近似，不引入 `QGraphicsDropShadowEffect`（D-032） |

> 遗留项清零：本节不再有"待你决定"的条目。

### 4.2 本轮新增的残留（等你决定是否补，暂不建任务）

| # | 残留 | 现状 | 需要你的决定 |
| --- | --- | --- | --- |
| 1 | 侧栏（大纲）的可见性与停靠位置未持久化 | **已决议（2026-10-12，D-041）：不持久化**——重启回默认（左侧、可见）；改为"侧栏可用收起键收起"，已由 **T-032** 落地（侧栏「收起」按钮 + `Ctrl+B`，收起/展开均上报状态栏） | 已闭环，无需再决定 |

## 5. 下一步行动

**当前状态：任务表已全部闭环**——`doing` = 0、`todo` = 0，工作区干净。本轮完成序列：T-021 → T-025 → T-030 → T-029 → T-028 → T-020 → T-019 → T-017 → T-031 → T-032 → T-018 → **T-033**；**T-022 已取消**（D-035）；§4.2 已闭环（D-041）。

**尚未闭环的两行（都不在任务表内，且都不需要你决定，仅在此登记）**：

- `docs/traceability.md` 的 **D-027 代码签名 / 安装包**：随 T-022 一并取消（本机自用、不发布），行内仍留 ⏳ 标记属历史痕迹，**不打算再做**；若你想让该行也标成"已取消"我可以顺手改（纯文档，0.1 h）；
- **NFR-2** 行：T-033 已把"总览缩放 21–23 fps"修到 270–555 fps，该行待下一次状态维护时改 ✅（本轮已同步数字，状态字样未逐字改）。

**可选的下一步方向（都需要你先说一句，我不自行开工）**：

1. **回到 spec 的 V1.1 清单**：`docs/requirements-spec.md` §5.2 里"搜索/大纲"已做（T-019/T-020），其余候选（如导出、多窗口会话分片等）从未评估过**是否需要**——需要你指定范围，否则我不会把它们变成任务；
2. **把本轮的经验固化**：E-024 的教训（先测量再优化、C++ 虚函数不可 monkeypatch、看图要用像素复核）目前写在 `ERRORS.md`/`docs/performance.md`，如需我提炼进 `pitfall-playbook` 技能（跨项目复用），说一声即可；
3. **维持现状**：本机自用工具已覆盖你确认过的全部需求，也可以就此暂停。

**恢复条件**：你说一句要做哪件事即可，我按 D-028 一次只做一个。

## 6. 已取消的任务（编号保留，不实施）

> 说明：任务表的状态枚举只有 `todo / doing / blocked / done`，没有"取消"。为避免未来会话把取消的任务当成待办（`todo`）或永久等待不存在的材料（`blocked`），已取消的任务移入本节，标 `wontfix` 语义并保留编号。

| ID | 任务 | 标记 | 取消依据 | 日期 |
| --- | --- | --- | --- | --- |
| T-022 | 安装包与代码签名（Inno Setup + signtool） | wontfix（取消） | **D-035**：用户明确"只在本机运行、不发布为商业项目"；本机自建 exe 不带 Mark-of-the-Web、不触发 SmartScreen，安装包与签名对本机自用无必要。原验收口径 D-034、原依据 D-027 均已标 `superseded` | 2026-10-12 |

