# 决策追溯表（映射）

- 最后更新：2026-10-12 03:20:00 +08:00
- **本表只记「决策 → 代码位置 → 测试名」**。决策的背景、选项、**理由与影响**一律以 `DECISIONS.md` 为唯一来源，此处不重复（收敛约定见 `PROJECT_MAP.md` §9）。
- 状态：✅ 已实现并验证 ｜ ⏳ 计划中 ｜ ⬜ 未开始 ｜ ❓ 待确认

## 1. 决策 → 代码 → 测试

| 决策 | 代码位置 | 测试 | 状态 |
| --- | --- | --- | --- |
| D-001 只读边界 | `infrastructure/markdown_reader.py`、`interfaces/` | `infrastructure/test_markdown_reader.py::test_reading_never_touches_the_source_directory`、`tests/integration/test_cli_cards.py::test_loading_never_touches_the_source_directory`、`tests/integration/test_gui_smoke.py::test_refresh_keeps_positions_and_adds_new_cards`（断言 mtime 不变） | ✅ |
| D-002 GUI 栈 | `interfaces/gui/board_view.py`、`card_item.py` | `tests/integration/test_gui_smoke.py`（13 项）+ `spikes/spike_real_window.py` | ✅ |
| D-003 原生卡片壳（Web 部件部分被 D-014 取代） | `interfaces/gui/card_item.py` | `test_gui_smoke.py::test_opening_a_file_builds_one_item_per_card` | ✅ |
| D-004 身份键分离 | `domain/ids.py`、`application/features/build_card_tree/service.py` | `domain/test_ids.py`、`build_card_tree/test_service.py::test_content_edits_keep_the_card_identity_but_change_the_hash` | ✅ |
| D-005 自有内容仅直属块 | `build_card_tree/service.py`（`own_block_indexes`） | `build_card_tree/test_service.py::test_content_blocks_belong_to_the_nearest_heading`、`domain/invariants.py` 覆盖不变量 | ✅ |
| D-006 折叠语义 | `detach_restore/service.py::toggle_collapse`、`layout_board/service.py::relayout_subtree` | `detach_restore/test_service.py::test_fold_flips_and_remembers_child_geometry`、`layout_board/test_service.py::test_collapsed_parent_shrinks_and_remembers_child_geometry` | ✅ |
| D-007 整体画布缩放 | `interfaces/gui/board_view.py`（`QTransform` + `AnchorUnderMouse`） | `tests/integration/test_acceptance.py::test_acceptance_9_zoom_works_from_wheel_and_from_a_typed_value` | ✅ |
| D-008 子卡跟随父卡 | `main_window._reparent_items`、`card_item.itemChange` | `test_acceptance.py::test_acceptance_4_a_child_cannot_be_dragged_out_before_detaching`、`test_gui_smoke.py::test_attached_cards_are_parented_to_their_card` | ✅ |
| D-009 每文档 JSON 快照 | `infrastructure/json_layout_store.py`（+`_layout_codec.py`/`_atomic.py`） | `infrastructure/test_json_layout_store.py`、`test_layout_roundtrip.py` | ✅ |
| D-010 多进程多窗口 | `interfaces/gui/app.py::spawn_new_window`、`main_window`（Ctrl+N） | `test_acceptance.py::test_acceptance_7_two_windows_are_independent` | ✅ |
| D-011 刷新判据 | `application/features/refresh_document/service.py` | `refresh_document/test_service.py`（42 项）、`test_acceptance.py::test_acceptance_6_refresh_keeps_layout_unless_the_structure_changes` / `..._6b_changing_a_heading_level_is_a_major_change` | ✅ |
| D-012 增强功能归属 | 折叠已实现（D-006）；大纲导航已实现（`main_window._build_outline`/`_focus_card`，T-020）；**搜索定位已实现**（`application/features/search_cards/` + 工具栏搜索框，T-019） | `tests/integration/test_outline_panel.py`（6）、`tests/integration/test_toc_navigation.py`、`tests/integration/test_search.py`（8）、`application/features/search_cards/test_service.py`（12） | ✅ |
| D-013 交付落点 | `docs/`、`src/mcwr/`、四件套在项目根 | — | ✅ |
| D-014 离屏渲染 + 档位缓存 | `infrastructure/web_renderer.py`、`application/features/render_card/`、`main_window._queue_body_images` | `render_card/test_service.py`（34）+ `infrastructure/test_web_renderer.py`（12）+ `tests/integration/test_body_render.py`（4） | ✅（E-013/E-016/E-017 已修） |
| D-015 会话分片 | `json_layout_store.py::_adopt` | `test_json_layout_store.py`、`test_gui_smoke.py::test_a_new_session_does_not_share_the_previous_layout`、`test_acceptance.py::test_acceptance_8_a_restart_restores_the_stored_layout` | ✅ |
| D-016 命名 | `pyproject.toml`、`infrastructure/app_paths.py`、`container.py` | `tests/integration/test_cli_cards.py::test_version_command` | ✅ |
| D-017 uv 管理 | `pyproject.toml`、`uv.lock`、README | 全部命令以 `python -m uv run` 执行 | ✅ |
| D-018 分阶段提交 | git 历史（12 次提交） | `git log --oneline` | ✅ |
| D-019 四件套落点 | 项目根四份 `*.md` | `PROJECT_MAP.md` §9 | ✅ |
| D-020 初版回溯范围 | 四件套内容 | `TASKS.md` T-001..T-023、`DECISIONS.md` D-001..D-020、`ERRORS.md` E-001..E-015 | ✅ |
| D-021 视觉规范 | `docs/visual-spec.md`、`interfaces/gui/theme.py`、`card_item.py`、`board_view.py`、`main_window.py`、`web_renderer`（主题参数 + shell 取色） | `interfaces/gui/test_theme.py`（槽位/无纯黑白/对比度/发布比值）、`tests/integration/test_theme_switch.py`、`infrastructure/test_web_renderer.py`（深色位图） | ✅ |
| D-022 渲染稳定性最高优先级 | `web_renderer.shared_renderer`（单例）、`_render` 空白重试、`card_item` 占位徽标、`shared/logging.py`、`tests/integration/conftest.py` | `tests/integration/test_render_stability.py`（10 条各一测）、`test_body_render.py`、`infrastructure/test_web_renderer.py`；全量 286 项 | ✅ |
| D-023 单文档规模上限（数值已被 D-040 取代） | `domain/models.MAX_CARDS`（现 1000）、`LoadedDocument.card_count`/`.over_limit`、`BoardSession.card_count`/`.over_limit` | `application/features/load_document/test_service.py`（边界不越界 / 越界 / 钉住 `MAX_CARDS == 1000`）、`tests/integration/test_card_limit.py` | ✅ |
| D-024 任务列表单独成卡 | `domain/enums.CARD_KIND_BY_BLOCK[TASK_LIST]`（既有行为） | `infrastructure/test_markdown_it_adapter.py::test_task_list_counts_checked_items` | ✅ |
| D-025 目录卡片跳转 | `application/features/build_toc/`、`card_item.link_clicked`/`anchor_at`、`session.reveal`、`main_window._on_link_clicked`、`markdown_it_adapter._stamp_toc_entries` | `tests/integration/test_toc_navigation.py`（`QTest` 真点击 → 视口中心落在目标卡内、折叠祖先逐级展开）、`build_toc/test_service.py`、`detach_restore/test_service.py::test_expanding_ancestors_*` | ✅ |
| D-026 显示名统一 | `mcwr.PRODUCT_NAME`、`main_window` 窗口标题（两处）、`README.md` 标题、CLI `--help` 文案 | `tests/integration/test_gui_smoke.py::test_the_window_title_uses_the_product_display_name`（并断言与 `app_paths.APP_DIR_NAME` 同步） | ✅ |
| D-027 代码签名 | 构建/签名脚本（未实现） | 待 T-022 | ⏳ |
| D-028 逐项完成 | `TASKS.md` 任务表（同时只允许 1 条 `doing`）、每个任务一次提交 | `git log --oneline`（一任务一提交） | ✅ |
| D-029 超限降级表现 | `main_window._queue_body_images` 短路、`session.limit_notice`、`_rebuild_items` 记一条日志 | `tests/integration/test_card_limit.py`（降级/原文绘制/仍可刷新） | ✅ |
| D-030 主题默认跟随系统 + 可切换 | `interfaces/gui/theme.py::resolve_theme` / `system_is_dark`、`main_window.apply_theme`、`shared/config.py` | `test_theme.py::test_follow_the_system_resolves_both_ways`、`test_config.py`、`test_theme_switch.py::test_the_chosen_mode_is_remembered_across_windows` | ✅ |
| D-031 主题实现细节 | `theme.py`、`card_item.py::set_palette`、`web_renderer._ensure_page_theme` + `mcwrSetTheme` + `_shell_file_name` | `test_theme_switch.py::test_switching_the_theme_changes_no_layout_field`、`test_web_renderer.py::test_the_cache_key_separates_the_two_themes`、`::test_the_shell_file_is_content_addressed` | ✅ |
| D-032 视觉遗留取值（高亮/色条/阴影） | **均已落地**：高亮 `infrastructure/pygments_highlighter.py` + `Palette.pygments_style`（D-036）；色条 `Palette.level_bar` + `theme.level_bar_colour` + `card_item._draw_depth_bar`（T-028，深度=祖先数+1）；阴影保持 1 px 近似（不做模糊） | `infrastructure/test_pygments_highlighter.py`（8）、`tests/integration/test_code_highlight.py`（3）、`tests/integration/test_level_bar.py`（4）、`interfaces/gui/test_theme.py`（样式槽位 + 色条取值/夹取） | ✅ |

## 2. 验收标准 → 测试

| 验收（spec §1.5） | 测试 |
| --- | --- |
| 1 线性排列 | `tests/integration/test_acceptance.py::test_acceptance_1_cards_are_laid_out_along_the_document_order` |
| 2 分隔线/标题/归属 | `...::test_acceptance_2_dividers_and_headings_nest_correctly` |
| 3 非卡片块并入内容 | `...::test_acceptance_3_prose_lists_and_quotes_are_not_cards` |
| 4 子卡不能直接拖出 | `...::test_acceptance_4_a_child_cannot_be_dragged_out_before_detaching` |
| 5 拖出/还原/全部还原 | `...::test_acceptance_5_restore_all_returns_the_initial_arrangement` |
| 6 刷新结构优先 | `...::test_acceptance_6_refresh_keeps_layout_unless_the_structure_changes`、`...::test_acceptance_6b_changing_a_heading_level_is_a_major_change` |
| 7 多窗口独立 | `...::test_acceptance_7_two_windows_are_independent` |
| 8 重开恢复布局 | `...::test_acceptance_8_a_restart_restores_the_stored_layout` |
| 9 滚轮/输入缩放 | `...::test_acceptance_9_zoom_works_from_wheel_and_from_a_typed_value` |
| 10 异常不崩溃 | `...::test_acceptance_10_broken_input_never_crashes_the_window` |

## 3. 当前缺口（映射视角）

| 缺口 | 决策 / 任务 | 状态 |
| --- | --- | --- |
| `docs/visual-spec.md` 未产出、双主题未实现 | D-021 / T-024 | ✅ 已交付（③④ 见 `test_theme_switch.py`，含 E-021 修复）；遗留已转为任务：语法高亮 **T-029**、层级色条 **T-028**（D-032），阴影不做模糊 |
| D-040 视口懒加载（NFR-3）＋ 上限 1000 | `main_window._render_candidates_now`/`_render_area`/`_release_offscreen_pixmaps`/`_on_viewport_scrolled`、`domain/models.MAX_CARDS` | `tests/integration/test_viewport_lazy_render.py`（7 项）、`test_card_limit.py`、`test_body_render.py`、`test_render_stability.py`、`test_theme_switch.py` | ✅ |
| D-041 侧栏不持久化 + 收起键（T-032） | `main_window._build_outline_panel`/`_toggle_outline`/`_on_outline_visibility_changed`、`OUTLINE_SHORTCUT`、`_apply_window_palette` 的 `QToolButton#outlineCollapse`（E-023）；`WindowState` 未改 | `test_outline_panel.py::test_the_panel_has_a_collapse_button_that_hides_and_restores_it`、`::test_the_ctrl_b_shortcut_toggles_the_panel`、`::test_the_outline_is_themed_with_the_window`；真实平台图 `spikes/_out/outline_collapse_button_{light,dark}.png` | ✅ |
| 视口外卡片仍被渲染（NFR-3 未落地） | D-040 / T-031 | ✅ 已实现：渲染候选 = 视口外扩半屏 ∩ 屏上宽度 ≥ 160 px ∩ 未被折叠祖先隐藏；`test_viewport_lazy_render.py` 断言"渲染调用集合 === 视口候选集合"、视口外零调用 |
| 200 卡片上限与降级未实现 | D-023 D-029 / T-025 | ✅ 已交付（`test_card_limit.py`；上限经 D-040 提高为 1000，边界实测 1000 卡 0.31 s / 1001 卡 0.28 s、超限零离屏渲染） |
| 渲染稳定性 10 条未逐条给出证据 | D-022 / T-026 | ✅ 10 条证据齐（`test_render_stability.py` + `docs/render-stability.md`） |
| app 路径渲染偶发 xfail | E-013 / T-016 | ✅ 已修（连续 16 次全绿；根因 E-016/E-017） |
| 目录卡片点击跳转未实现 | D-025 / T-021 | ✅ 已交付（`test_toc_navigation.py`：真点击居中 + 折叠祖先展开） |
| 渲染缓存无容量上限 | T-017 / D-039 | ✅ 已实现：上限 1024 条（`MAX_CACHE_ENTRIES`）、mtime LRU、命中刷新、覆盖历代 shell 文件；`test_web_renderer.py` 6 项含生产规模算术 |
| NFR-2 性能（打开 ≤3 s / ≥30 fps） | `spikes/spike_large_document.py`（T-018 工具）、`docs/performance.md` | 实测：111/551/1101 卡打开 0.03/0.22/0.63 s ✅；drag 122–159 fps、zoom 65–78 fps、阅读缩放整屏重绘 76–89 fps ✅；**总览缩放整视口重绘 21–23 fps ❌ → 开 T-033** | ⚠️ 部分达标 |
| 安装包与签名未做（证书已具备，路径未提供） | D-027 / T-022 | ⏳ |
| 显示名字符串未确认 | D-026 | ❓ |
