# Spike 结论

## Spike 1 — markdown-it-py 能否暴露全部所需块类型（2026-10-11）

脚本：`spikes/spike_md_blocks.py` ｜ 样例：`spikes/samples/sample.md` ｜ 原始输出：`spikes/_out/md_tokens.txt`

配置：`MarkdownIt("commonmark", {"html": True}).enable("table")` + `dollarmath_plugin(allow_space=True)` + `tasklists_plugin`。

**结论：可行**，全部块类型都有稳定、可判别的 token 形态：

| 需要的块 | 实际 token | 判别依据 |
|---|---|---|
| 标题 H1–H6 | `heading_open` (tag=`h1`..`h6`, nesting=1) + `inline` | `tag` 取层级；标题文本在紧邻的 `inline.content` |
| 段落 | `paragraph_open` + `inline` | 默认 |
| 引用 | `blockquote_open`..`blockquote_close` | 容器区间 |
| 普通列表 | `bullet_list_open` / `ordered_list_open` | 无 task 类名 |
| 任务列表 | 同上 + `attrs["class"] == "contains-task-list"` | 勾选态来自子 `html_inline` 里的 `<input ... checked>` |
| 表格 | `table_open`..`table_close`，内含 `thead/tbody/tr/th/td` | 容器区间；单元格文本在各 `inline` |
| 代码块 | `fence`（`info='python'`） | `info` 首个词为语言 |
| Mermaid | `fence`（`info='mermaid'`） | 同 fence，靠 `info` 分流 |
| 块级公式 | `math_block`（需 dollarmath 插件） | `content` 为公式体，`markup='$$'` |
| 行内公式 | `inline` 子 token `math_inline` | 保留在所属卡片内 |
| 图片 | `inline` 子 token `image`（`attrs.src/alt`） | 纯图片段落可整段升级为图片卡片 |
| 目录 | **无专用 token**：`[TOC]` 被解析为段落，`inline.content == "[TOC]"` | 适配器需特判段落文本 |
| 分隔线 | `hr` | 直接映射 `thematic_break` |
| 原始 HTML | `html_block` | 归入内容（不单独成卡） |

**坑与对策**

1. `map` 为 `[start, end)`（0 起、不含 end），可用于取原文行与 `SourceSpan`（转 1 起、end 含）。
2. `[TOC]` 没有原生支持 —— 由适配器特判（`[TOC]` / `[toc]` / `[[TOC]]`）。
3. 任务列表的勾选框是 `html_inline`（原始 `<input>`），需按 `checked` 关键字统计，不能依赖渲染。
4. `fence.content` 末尾带 `\n`；`math_block.content` 前后带 `\n`，入库前需 strip。
5. `dollarmath` 的 `allow_space=True` 才会把 `$$ ... $$` 且内部有空格的公式识别为块级公式。
6. 未识别的顶层 token 必须降级为 `unknown` 块（不丢原文），不允许抛异常中断整篇解析。

## 待办 spike

| # | spike | 状态 |
|---|---|---|
| 2 | `spike_nested_drag.py`（Qt 嵌套拖动/拖出坐标换算） | 未开始 |
| 3 | `spike_web_render.py`（KaTeX/Mermaid 离屏渲染 + 缩放档位） | 未开始 |
| 4 | `spike_layout_roundtrip.py`（快照往返 + 损坏降级） | 未开始 |
| 5 | `spike_multiwindow.py`（多进程会话分片） | 未开始 |
