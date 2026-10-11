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

## Spike 3 — QtWebEngine 离屏渲染 KaTeX / Mermaid（2026-10-12）

脚本：`spikes/spike_web_render.py` ｜ 原始数据：`spikes/_out/spike_web_render_result.json`、`spikes/_out/worker_*.log` ｜ 产物 PNG/PDF：`spikes/_out/` ｜ 资源：`src/mcwr/assets/web/`

复现命令（退出码 0，会写出全部 PNG）：

```
cd /c/Users/31094/Projects/MarkdownCardWhiteboardReader
python -m uv run python spikes/spike_web_render.py --fetch-assets   # 仅首次：下载 KaTeX 0.19.0 / Mermaid 12.1.0
python -m uv run python spikes/spike_web_render.py                  # 4 个 worker（每种策略 × 平台组合一个子进程）
```

环境：Python 3.12.10（`python -m uv run` 的 venv）、**PySide6 6.12.0**、QtWebEngine 可用、Windows。
**网络可用**（npm registry 200，两个包均下载成功）。

### 结论：**可行（带约束）** —— 离屏渲染成功，且 `QT_QPA_PLATFORM=offscreen` 确实能承载 WebEngine

真正生效的组合（其余组合未测；`--no-sandbox` + `QTWEBENGINE_DISABLE_SANDBOX=1` 全程开启，未验证默认沙箱是否也可行）：

| 策略 | 平台 | flags | 结果 |
|---|---|---|---|
| `QWebEngineView` + `WA_DontShowOnScreen` + `grab()` | `QT_QPA_PLATFORM=windows` | `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu --no-sandbox` | **9/9 渲染正确**，无窗口出现；DevicePixelRatio=**1.25** |
| `QWebEngineView` + `show()` + `grab()` | `QT_QPA_PLATFORM=offscreen` | 同上 | 9/9 出图，**8/9 正确**；DPR=**1.0**（像素数 = CSS×zoom，档位换算最干净） |
| `QWebEnginePage`（无 view）+ `printToPdf` → `QPdfDocument.render` | `windows` | 同上 | 3/3 正确；**一次栅格化可出任意档位** |

`QT_QPA_PLATFORM=offscreen` **不是** 拦路虎 —— 平台插件列表里有 `offscreen`，WebEngine 在其上正常渲染（`--disable-gpu` 下走软件合成）。

### 实测数字

| 指标 | 实测值 |
|---|---|
| 冷启动（进程启动 → 外壳页 `ready`，含 QApplication + WebEngine 初始化 + 渲染子进程拉起） | windows **907–1016 ms**；offscreen **604 ms** |
| 每张公式渲染（`runJavaScript` → 轮询到 done，纯 JS 渲染） | **~20 ms**（首次 41 ms） |
| 每张 Mermaid 渲染（同上） | **首次 289–310 ms**（解析 5.5 MB bundle），**后续 61 ms** |
| 单张图端到端（含布局沉降 + 等到 3 帧稳定的 `grab()` + 存盘） | 公式 **230–290 ms**；Mermaid **326–706 ms** |
| 其中 `grab()+save` 本身 | 公式 3–32 ms；Mermaid 24–380 ms（大头是"等 3 帧一致"的防陈旧帧循环） |
| PNG 像素尺寸（DPR=1.0，offscreen；CSS 尺寸 496×78 公式 / 496×946 流程图） | 公式 z1.0/z1.5/z2.0 = 498×80 / 746×119 / 994×160；Mermaid = 498×948 / 746×1421 / 994×1894 |
| PNG 字节 | 公式 2.6–22 KB；Mermaid 30–113 KB |
| 进程工作集（本轮结束，主进程 + `QtWebEngineProcess.exe`，`GetProcessMemoryInfo`，psutil 未安装） | windows 总 **512 MB**（峰值 549）；offscreen 总 **348 MB**（峰值 362）；仅 PDF 策略 297 MB |
| 解码后 QImage 内存（ARGB32 = w×h×4） | 公式 3 档 **1.1 MB**；高流程图 3 档 **13 MB**（DPR1.25 下 **19.6 MB**） |

### 坑（都是实测撞出来的）

1. **陈旧帧**：改 `zoomFactor` / `resize` 后 WebEngine 异步重绘，`grab()` 会拿到上一档的画面。必须**等到连续 N 帧字节一致**（本 spike 用 3 帧 + 60 ms 间隔，实测稳定），否则 PNG 与档位不符。第一次用 2 帧判据时真的存下过一张错的图。
2. **view 尺寸必须按物理像素算**：`ceil(css_w × zoom × DPR) + 边距`。windows 平台 DPR=1.25，我最初按 CSS 像素 resize，z2.0 的 Mermaid 右边被裁掉一截。
3. **offcreen 平台的大画布**：946 CSS px 高的 Mermaid 在 `offscreen` 下 z2.0（994×1894 表面）连续两次跑出半成品（内容停在 1.5× 并带一条滚动条）；同尺寸在 `windows` 平台（DPR1.25，1245×2208）正常。小表面（公式）两平台全对。→ 建议单张渲染表面控制在 ~1000 px 量级，长图分块。
4. **WebEngine 起不来是"进程级致命"**：把 `QT_QPA_PLATFORM` 设成不存在的插件名，Qt 直接 `qFatal`：`This application failed to start because no Qt platform plugin could be initialized`，**子进程 exit 127，Python 侧捕不到异常**。降级必须靠"先探针、后使用"，且探针放子进程。
5. Mermaid SVG 插入 DOM 后必须 `removeAttribute("height")` + `style.width=100%`，否则在收缩容器里塌成 100 px 宽。
6. `runJavaScript` 回传 JS 对象不可靠（拿到空值）；改成 `JSON.stringify([...])` 再解析。

### 建议管线（D14）

- **一个常驻隐藏 `QWebEngineView`（`WA_DontShowOnScreen=True`，跟随 app 现有 `windows` 平台）复用给所有卡片**，外壳页只加载一次（省掉每张卡重解析 KaTeX/Mermaid + 首次 Mermaid 的 ~250 ms）。app 已经跑在 `windows` 平台上，**不能**指望切到 `offscreen` 平台（QApplication 平台在进程内固定）；真要 offscreen 就得另起进程。
- **档位 3 个：1.0 / 1.5 / 2.0**，渲染倍率 = 档位 × 屏幕 DPR；画布缩放低于 1.0 直接缩图（实测 1.0 档足够清晰），超过 2.0 才需要第 4 档。切换阈值：`|canvas_zoom - bucket| / bucket > 20%` 时换图并后台补渲染新档。
- **缓存键**：`sha256(kind | source_stripped | stage_width | theme | bucket | renderer_version)`（`renderer_version` 含 KaTeX/Mermaid 版本号，升级即失效）。落盘存 **PNG 字节**（LRU，如 256 条 ≈ 10–20 MB），内存里只保留**当前可见档**的解码 `QPixmap` —— 否则一张高流程图 3 档就吃 13–20 MB。
- **可选**：只要档位 ≥ 3 且内容不常变，`printToPdf` 一次 + `QPdfDocument.render(scale)` 多次更划算（公式打印 97–121 ms，每档栅格化仅 3–7 ms），但 Mermaid 首次打印 1.9 s，不划算。

### 失败降级（必须实现）

1. `QtWebEngineCore` **惰性 import**，包在 `try/except ImportError` 里；导入失败 → 后端标记不可用，永不重试。
2. 启动后**一次性子进程探针**（`--probe` 模式渲染一个固定公式，带超时）：子进程崩了/超时/没出图 → 本会话禁用 WebEngine 后端。绝不能把 WebEngine 初始化留在主进程主路径上（坑 4：`qFatal` 会带走整个应用，与"必须能打开"冲突）。
3. 后端不可用时，公式/Mermaid 卡片走现有 `QTextDocument` 路径显示 **原始文本**（`$$…$$` / ```mermaid``` 围栏内容），绝不弹窗、绝不崩。
4. 渲染是异步的：卡片先显示原始文本占位，PNG 就绪后发信号替换为图片（`QGraphicsPixmapItem`）。

### 未能验证

- 未测**默认沙箱**（未加 `--no-sandbox`）是否可行；所有成功组合都关了沙箱。
- 未测真实 GPU 路径（全程 `--disable-gpu`）。
- 未在**主应用进程内**（已有主窗口 + 卡片场景）测量 WebEngine 的增量内存与首帧延迟；本 spike 全是独立子进程。
- 未验证 D7 画布变换下的实际观感（档位切换时的重绘延迟只测到"单张 230–700 ms"这一层）。
- 未测 100 张卡片的批量渲染吞吐与磁盘缓存命中表现。

## 待办 spike

| # | spike | 状态 |
|---|---|---|
| 2 | `spike_nested_drag.py`（Qt 嵌套拖动/拖出坐标换算） | 未开始 |
| 3 | `spike_web_render.py`（KaTeX/Mermaid 离屏渲染 + 缩放档位） | **已完成（2026-10-12）**：可行；offscreen 平台可用；3 档 + 常驻页 + PNG 缓存为准 |
| 4 | `spike_layout_roundtrip.py`（快照往返 + 损坏降级） | 未开始 |
| 5 | `spike_multiwindow.py`（多进程会话分片） | 未开始 |
