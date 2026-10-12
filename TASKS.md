# TASKS — 任务与状态

- 最后更新：2026-10-12 16:18:37 +08:00
- 状态枚举：仅 todo / doing / blocked / done

## 1. 当前目标

MVP 已完成并验证（含 PyInstaller onedir 打包与交付形态自检）。当前目标按用户指示「按优先级逐步完成」，优先级顺序为：

**T-016（修掉渲染抖动）→ T-026（渲染稳定性 10 条逐条落地与验证）→ T-024（视觉规范 + 双主题）→ T-025（200 卡片上限与降级）→ T-021（目录卡片跳转）→ T-020（大纲导航）→ T-019（搜索定位）→ T-017（渲染缓存上限）→ T-018（大文档压测）→ T-022（安装包 + 签名）**

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
| T-017 | 给渲染缓存加容量上限 | todo | 中 | 无 | `QtWebCardRenderer` 在缓存文件数超过上限时按最近使用淘汰；新增单测断言「写入 N+1 个后目录文件数 ≤ N」 | 1–2 h | — | D-014 | C 建议 LRU ~256 条 / 10–20 MB |
| T-018 | 大文档性能压测 | todo | 中 | 无 | 生成 500 与 1000 卡片的合成文档，记录「打开到可交互」与「拖动帧率」两组实测数字进 `docs/`；若 >2 s 或 <30 fps 则开新任务 | 3–5 h | — | — | spec NFR-2 目前只有 100 卡片假设 |
| T-019 | 搜索并定位卡片（V1.1） | todo | 中 | 无 | 输入关键字 → 命中卡片居中并高亮；新增集成测试断言命中卡片 id 与视口中心坐标 | 4–6 h | — | D-012 | spec §5.2 V1.1 候选 |
| T-020 | 大纲导航（V1.1，标题树跳转） | todo | 中 | 无 | 侧栏列出标题树，点击后目标标题卡居中；测试断言点击第 3 项后视口中心等于该卡中心 | 3–4 h | — | D-012 | 与 T-021 可能复用定位逻辑 |
| T-021 | 目录卡片点击跳转（FR-2.4） | done | 中 | 无（D-025 已确认纳入下一版） | 点击目录项后对应标题卡居中 **✅**（`QTest` 真点击 → `view.mapToScene(viewport.center)` 落在目标卡矩形内，且卡片未被拖动）；目标在折叠祖先内时逐级展开并提示 **✅**（F10） | 2–3 h | 2 h | D-025 D-033 | 实现：目录条目由 `build_toc` 按标题树生成（`[TOC]` 处才生成条目，含全部 H1–H6）；卡片内链接经 `QTextCharFormat.isAnchor()` 解析；顺带修两处既有缺陷：目录卡高度按条目数（parser 在块 `attrs` 戳 `toc_entries`）、普通点击不再误发 `moved`。证据：`tests/integration/test_toc_navigation.py` 5 项 + `build_toc/test_service.py` 7 项 + `detach_restore` 3 项 + sizer/adapter 各 2 项；全量 `pytest -q` 退出码 0（314 项） |
| T-022 | 安装包与代码签名 | todo | 低 | 证书材料（Thumbprint 或 pfx+口令，§4 阻塞项 1） | ①产出可安装包；②**本机近似干净环境**（全新安装目录 + 空的应用数据/日志目录 + 净化环境变量）静默安装后 `mcwr.exe --self-check` 退出码 0 且 `rendered_images=2/2`、`frozen=true`；③卸载后无残留；④真证书到位后对 `mcwr.exe` 与安装包签名，`signtool verify /pa` 通过（D-034） | 4–8 h | — | D-026 D-027 D-034 | 显示名 = `MarkdownCardWhiteboardReader`（D-026 accepted，待本任务落地到窗口标题/README/安装包）；`dist/` 为空需先重建冻结包；工具链已就绪（signtool ✓、Inno Setup 6 ✓）；**本机无代码签名证书**，用户已决定先不开工 |
| T-023 | 初始化四件套（本次 state-keeper 任务） | done | 高 | 无 | 项目根存在 `PROJECT_MAP.md` / `TASKS.md` / `DECISIONS.md` / `ERRORS.md`；事实均带证据；`docs/traceability.md` 与四件套无重复主记录 | 1 h | 1 h | D-019 D-020 | 本轮完成 |
| T-024 | 视觉规范 + 双主题实现 | done | 高 | 无 | ①`docs/visual-spec.md` 覆盖 D-021 全部条目 **✅**；②对比度经计算 ≥ 4.5:1（AA）、深色无纯黑、浅色无纯白 **✅**（脚本 `spikes/_out/contrast.py` + 单测 `test_theme.py` 钉住发布值）；③主题三态（跟随系统/浅色/深色）可切换且切换后 `CardLayout` **全字段与对象身份都不变** **✅**（`tests/integration/test_theme_switch.py` 6 项）；④深色下代码/公式/Mermaid 可读、缓存键含 theme **✅**（真实深色位图像素断言 + 文本卡像素断言 + `test_the_cache_key_separates_the_two_themes`） | 6–10 h | 4 h | D-021 D-030 D-031 E-019 E-021 | 证据：`ruff` 全绿；`mypy --strict` 76 文件 0 错误；`pytest -q` 退出码 0（**286 项**，较改动前 +27）；`test_web_renderer.py` 17/17（含 2 条真实深色渲染）；深色位图 `spikes/_out/render_card_math_dark_z1.0.png`、`render_card_mermaid_dark_z1.0.png`（已人工过目：深底浅字）。**真实平台**：主题三态切换在 `windows` 插件下实测通过（`spikes/spike_theme_switch_real.py` 退出码 0、布局/对象/文档均未变），但该次渲染失败属环境问题（本机会话 USER 句柄耗尽，既有 spike 同样失败）→ 见 **E-020**，故渲染判据以 offscreen 真实像素为准。**残留**：语法高亮未做、层级色条未做、浅色阴影为 1px 半透明近似（见 §4.1）。**E-021 修复**：真实平台探测发现"升级后页面缺 `mcwrSetTheme`"（渲染页固定文件名被 Chromium 磁盘缓存供了旧版），改为内容寻址 `_shell-<digest>.html` 后，在共享缓存目录 + 旧 `_shell.html` 在场 + 新 payload 的条件下实测 `rendered=1 cache_hits=0 failed=0`、无 TypeError |
| T-025 | 200 卡片上限与降级模式 | done | 高 | 无（D-029 已定降级表现） | ①解析后暴露卡片总数与超限标记 **✅**（`LoadedDocument.card_count`/`.over_limit`、`BoardSession.card_count`/`.over_limit`）；②201 张卡实测**打开 0.03–0.05 s**（预算 ≤ 5 s）、201 个 item 全在场、状态栏出「超限」提示 **✅**；③覆盖 200（正常，仍走离屏渲染）与 201（降级：**零渲染调用**、按原文绘制、仅一条日志） **✅** | 3–4 h | 1.5 h | D-023 D-029 | 证据：`tests/integration/test_card_limit.py` 4 项 + `load_document/test_service.py` 3 项（含 `MAX_CARDS == 200` 钉值）；真实 CLI `mcwr cards` 对 201 卡文件输出 `cards=201 blocks=398`；计时工具已入库 `spikes/spike_card_limit_timing.py`（对 200 卡 0.05 s、201 卡 0.03 s，可复跑）；200/201 卡文档由测试内脚本合成；全量 `pytest -q` 退出码 0（295 项） |
| T-026 | 渲染稳定性 10 条逐条落地与验证 | done | 高 | T-016 | 对 D-022 的 10 条各给一条可读回证据 | 6–10 h | 3 h | D-022 E-016 E-017 | 10 条证据齐（详见备注） |
| T-027 | 收敛 docs/traceability.md 与四件套边界 | done | 中 | 无 | traceability 只保留「决策 → 代码位置 → 测试名」映射与验收映射；理由/影响一律指向 `DECISIONS.md` | 0.5 h | 0.5 h | D-021 之后 | 本轮完成 |
| T-028 | 卡片左侧 3 px 层级色条（4 档，取值见 D-032） | todo | 中 | 无 | 左侧 3 px 色条按嵌套深度取 `docs/visual-spec.md` §6.1 的 4 档值；浅/深各一套；第 5 级及更深沿用第 4 档；新增测试断言「深度→颜色」映射、3 px 宽度、两套主题取值互不相同 | 1–2 h | — | D-032 D-021 | 取值由用户给定；不启用蓝色备选组 |
| T-029 | 代码卡片语法高亮（Pygments） | todo | 中 | 无 | `QTextDocument` 渲染路径按主题选用两套 Pygments 样式；浅/深下关键字/注释/字符串可区分；新增测试断言两套样式不同、深色下关键字与代码块底色对比度 ≥ 4.5:1 | 2–4 h | — | D-032 D-021 | `pygments` 已在依赖中；样式选择留在 interfaces/infrastructure，`application` 不得 import pygments |
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
| 1 | 代码签名**材料**：(a) 证书已在存储 → **Thumbprint**；或 (b) `.pfx` **绝对路径** + 环境变量 `MCWR_SIGN_PFX_PASSWORD`（口令不进聊天/仓库）。本机实测**无代码签名证书**，需用户提供或采购 | T-022 | 用户 | 2026-10-12 |

> 已解除：显示名字符串（D-026 = `MarkdownCardWhiteboardReader`）、超限降级表现（D-029 = 停止离屏渲染富内容 + 原文 + 提示）。

### 4.1 遗留项处理结果（用户已于 2026-10-12 答复，见 D-032）

| # | 遗留项 | 你的答复 | 落地 |
| --- | --- | --- | --- |
| 1 | 代码语法高亮（visual-spec §5） | 「需要」 | 已开任务 **T-029**（Pygments 两套样式） |
| 2 | 层级色条 4 档取值（visual-spec §6） | 给出中性灰蓝 4 档、浅深各一套，第 5 级及更深沿用第 4 档 | 取值写入 `docs/visual-spec.md` §6.1；已开任务 **T-028** |
| 3 | 浅色阴影模糊度 | 「不需要」 | 保持 1 px 偏移近似，不引入 `QGraphicsDropShadowEffect`（D-032） |

> 遗留项清零：本节不再有"待你决定"的条目。

## 5. 下一步行动

**当前状态：暂停推进任务**（用户 2026-10-12 07:05 指示）；`doing` = 0 条，工作区干净（HEAD `a86414d`）。**T-022 已明确等材料**：用户同日 16:18 决定「先不开工，等 Thumbprint 或 pfx」；其验收口径按 D-034（本机近似干净环境，交付说明中如实标注）。

候选（按 §1 顺序）：**T-020**（大纲导航，3–4 h，可直接复用 T-021 的 `session.reveal` + `centerOn` 定位链路）→ T-017（渲染缓存上限，1–2 h）→ T-018（大文档压测，3–5 h）→ T-019（搜索定位，4–6 h）→ T-022（安装包+签名，4–8 h，**等证书材料**）；另有 T-028（层级色条，1–2 h）与 T-029（Pygments 语法高亮，2–4 h）。

**恢复条件**：你说一句要做哪个任务（或给 T-022 的证书材料）即可，我按 D-028 一次只做一个。

