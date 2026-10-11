# 决策追溯表

每个已确认决策（docs/requirements-spec.md §0.1）落在哪段代码、由哪个测试守住。
状态：✅ 完成并验证 ｜ ⏳ 进行中 ｜ ⬜ 未开始。

| 决策 | 取值 | 实现位置 | 验证 | 状态 |
|---|---|---|---|---|
| D1 产品边界 | 只读、仅 Windows、无热更新/同步/回写 | `infrastructure/markdown_reader.py`、`interfaces/cli`、`interfaces/gui` | `test_markdown_reader.py::test_reading_never_touches_the_source_directory`、`tests/integration/test_cli_cards.py::test_loading_never_touches_the_source_directory`、`test_gui_smoke.py::test_refresh_keeps_positions_and_adds_new_cards`（断言 mtime 不变） | ✅ |
| D2 GUI 栈 | PySide6 + QGraphicsScene | `interfaces/gui/board_view.py`、`card_item.py` | `test_gui_smoke.py`（12 项，offscreen）+ `spikes/spike_real_window.py`（真实平台） | ✅ |
| D3 渲染策略 | Qt 原生壳 | `interfaces/gui/card_item.py`（QTextDocument 渲染卡片自有内容） | `test_gui_smoke.py::test_opening_a_file_builds_one_item_per_card` | ✅ |
| D4 卡片身份 | `stable_key` 与 `content_hash` 分离 | `domain/ids.py`、`build_card_tree/service.py` | `test_ids.py`、`build_card_tree/test_service.py::test_content_edits_keep_the_card_identity_but_change_the_hash` | ✅ |
| D5 卡片内容粒度 | 仅直属块 | `build_card_tree/service.py`（`own_block_indexes`） | `test_service.py::test_content_blocks_belong_to_the_nearest_heading`、`domain/invariants.py` 覆盖率不变量 | ✅ |
| D6 折叠语义 | 隐藏子孙 + 父卡收缩 + 记忆几何 | `detach_restore/service.py::toggle_collapse`、`layout_board/service.py::relayout_subtree` | `detach_restore/test_service.py::test_fold_flips_and_remembers_child_geometry`、`layout_board/test_service.py::test_collapsed_parent_shrinks_and_remembers_child_geometry` | ✅ |
| D7 缩放语义 | 整体画布变换 | `interfaces/gui/board_view.py`（`QTransform`，`AnchorUnderMouse`） | `test_acceptance.py::test_acceptance_9_...` | ✅ |
| D8 拖动联动 | 子卡跟随父卡；自由卡不跟 | `interfaces/gui/card_item.py`（Qt 父子项）+ `_reparent_items` | `test_gui_smoke.py::test_attached_cards_are_parented_to_their_card`、`test_acceptance.py::test_acceptance_4_...` | ✅ |
| D9 持久化格式 | 每文档 JSON、原子写、schema 版本 | `infrastructure/json_layout_store.py`（+`_layout_codec.py`/`_atomic.py`） | `test_json_layout_store.py`、`test_layout_roundtrip.py`（35 项） | ✅ |
| D10 多窗口 | 多进程，每窗口一进程 | `interfaces/gui/app.py::spawn_new_window`、`MainWindow`（`Ctrl+N`） | `test_acceptance.py::test_acceptance_7_two_windows_are_independent` | ✅ |
| D11 刷新判据 | 大卡片数或标题层级序列变化 = 重大 | `application/features/refresh_document/service.py` | 该切片 42 项单测 + `test_acceptance.py::test_acceptance_6_...` / `..._6b_...`（端到端交叉验证） | ✅ |
| D12 增强功能归属 | 折叠进 MVP，其余后续 | 折叠已实现；搜索/大纲/连线未做 | — | ✅（MVP 部分） |
| D13 交付落点 | 本仓库 | `docs/`、`src/mcwr/` | — | ✅ |
| D14 离屏渲染 | Web 仅做离屏渲染 → 图片 + 缩放档位缓存 | `infrastructure/web_renderer.py`、`application/features/render_card/` | 渲染器 12 项单测通过、PNG 经人工核验；App 内集成不可靠（页面已渲染但 Python 侧轮询超时 → 回退文本） | ⏳ |
| D15 会话分片 | 每会话一份分片 + `last_session` 指针 | `infrastructure/json_layout_store.py::_adopt` | `test_json_layout_store.py`（新会话不再动旧分片）、`test_gui_smoke.py::test_a_new_session_does_not_share_the_previous_layout`、`test_acceptance.py::test_acceptance_8_...` | ✅ |

## 验收标准 → 测试

| 验收（spec §1.5） | 测试 |
|---|---|
| 1 线性排列 | `test_acceptance.py::test_acceptance_1_cards_are_laid_out_along_the_document_order` |
| 2 分隔线/标题/归属 | `test_acceptance.py::test_acceptance_2_dividers_and_headings_nest_correctly` |
| 3 非卡片块并入内容 | `test_acceptance.py::test_acceptance_3_prose_lists_and_quotes_are_not_cards` |
| 4 子卡不能直接拖出 | `test_acceptance.py::test_acceptance_4_a_child_cannot_be_dragged_out_before_detaching` |
| 5 拖出/还原/全部还原 | `test_acceptance.py::test_acceptance_5_restore_all_returns_the_initial_arrangement` |
| 6 刷新结构优先 | `test_acceptance.py::test_acceptance_6_...`、`..._6b_...` |
| 7 多窗口独立 | `test_acceptance.py::test_acceptance_7_two_windows_are_independent` |
| 8 重开恢复布局 | `test_acceptance.py::test_acceptance_8_a_restart_restores_the_stored_layout` |
| 9 滚轮/输入缩放 | `test_acceptance.py::test_acceptance_9_zoom_works_from_wheel_and_from_a_typed_value` |
| 10 异常不崩溃 | `test_acceptance.py::test_acceptance_10_broken_input_never_crashes_the_window` |

## 已知缺口（诚实清单）

| 项 | 说明 |
|---|---|
| 公式 / Mermaid 实际渲染 | **未达标**：渲染器独立可用（12 项单测 + 人工看图确认），但经 App 路径时 Python 侧轮询超时，卡片退回原文渲染。复现：`python -m uv run python spikes/spike_app_render_probe.py`（页面 `mcwrRenders` 递增、`mcwrState=done`，而渲染器 stats 仍为 `rendered=0, failed=N`）。另有一次 App 运行把同一张 Mermaid 图缓存到两个卡片键下（跨图串帧），已加回归守卫 `tests/integration/test_body_render.py`（当前 xfail） |
| 目录卡片点击跳转（FR-2.4） | 未实现；spec §5.1 的 MVP 清单未列入该项，大纲导航在 §5.2 归入 V1.1 |
| 打包（NFR-7） | 未开始：PyInstaller onedir + 资源（含 `src/mcwr/assets/web`）路径尚未验证 |
| 多进程并发写同一分片 | 设计上由 D15 会话分片规避；未做真实双进程并发压测 |
| 单文档超大（>2000 卡片） | 未压测，spec §7.2 第 16 条待你决定上限行为 |
