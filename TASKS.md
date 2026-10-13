# TASKS — 任务与状态

- 最后更新：2026-10-12 17:24:34 +08:00
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
| T-018 | 大文档性能压测 | doing | 中 | 无（用户 2026-10-12：值得做） | 生成 500 与 1000 卡片的合成文档，记录「打开到可交互」与「拖动/缩放帧率」两组实测数字进 `docs/`；若 >2 s 或 <30 fps 则开新任务 | 3–5 h | — | D-040 NFR-2 | 补充口径（T-031 之后 T-018 独有的价值）：①500/1000 卡的拖动/缩放**帧率**；②富内容卡密布时**队列总时长**（T-031 只用记录型 renderer 数过调用，没测真实耗时）；另记录内存/句柄随规模的变化 |
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
| T-033 | 总览缩放的帧率修复（背景网格设备像素下限） | done | 中 | 门槛沿用 T-031 的 160 px（用户 2026-10-12 同意；**最终未用**，见备注） | ①总览缩放的整视口重绘从 43–47 ms 降到 ≤15 ms **✅ 实测 1.8–3.7 ms（270–555 fps）**；②阅读缩放（≥100%）**像素零变化** **✅**（100% 整屏重绘 8.8 → 8.2 ms，背景像素统计一致）；③门槛不发明第二套无谓阈值 **✅**（卡片绘制未改；新增的是**另一个量纲**的 `MIN_GRID_DEVICE_STEP = 8.0` 设备像素） | 2–3 h | 2 h | T-018 D-042 E-024 | **交付与立项时的方案不同，必须记住**：原方案"缩得太小的卡不画正文"（沿用 160 px）实现后**实测零改善**（47.1 vs 47.0 ms）→ 代码已**回退**。真正原因是 `BoardScene.drawBackground` 的网格：fit 下暴露 11240×8460 场景单位、`GRID_STEP=40` ⇒ **492 条贯穿全屏抗锯齿长线 ≈ 40 ms**（`CacheBackground` 45.9→3.8 ms、空场景 0.7 ms、隐藏全部卡片仍 42.8 ms 三条证据）。修复＝网格设备像素间距下限；新增测试 `tests/integration/test_grid_detail.py` 5 项 + 前后对比图 `spikes/_out/grid_floor_{before,after}.png`（像素统计：before 3 色含网格色、after 仅 1 色）。全量 `pytest -q` 退出码 0（386 项） |
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

**当前状态：暂停推进任务**（用户 2026-10-12 07:05 指示）；`doing` = 0 条，工作区干净。本轮已完成：T-021 → T-025 → T-030 → T-029 → T-028 → T-020 → T-019 → T-017 → T-031 → T-032 → **T-018**；**T-022 已取消**（D-035）；§4.2 已闭环（D-041）。

**下一个候选**（只剩 1 项，需你先做一个决定）：

- **T-033 卡片绘制细节分级（LOD）**（2–3 h）——**T-018 按任务自定规则开出的新任务**：实测"缩小到总览"时整视口重绘 43–47 ms（21–23 fps）低于 30 fps，原因是**每张可见卡约 0.6 ms 的 Python 绘制按张计费**（`docs/performance.md` §4）。做法是"缩得太小的卡只画卡形+标题栏、跳过正文"，目标 ≤15 ms/帧，且**阅读缩放下像素级零变化**。门槛取值需你定（建议沿用 T-031 的 160 px，避免第二套阈值）。**开工与否等你点头**。

**恢复条件**：你说一句要做哪个任务即可，我按 D-028 一次只做一个。

## 6. 已取消的任务（编号保留，不实施）

> 说明：任务表的状态枚举只有 `todo / doing / blocked / done`，没有"取消"。为避免未来会话把取消的任务当成待办（`todo`）或永久等待不存在的材料（`blocked`），已取消的任务移入本节，标 `wontfix` 语义并保留编号。

| ID | 任务 | 标记 | 取消依据 | 日期 |
| --- | --- | --- | --- | --- |
| T-022 | 安装包与代码签名（Inno Setup + signtool） | wontfix（取消） | **D-035**：用户明确"只在本机运行、不发布为商业项目"；本机自建 exe 不带 Mark-of-the-Web、不触发 SmartScreen，安装包与签名对本机自用无必要。原验收口径 D-034、原依据 D-027 均已标 `superseded` | 2026-10-12 |

