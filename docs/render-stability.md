# 渲染稳定性：设计约束与证据清单

> 决策依据：`DECISIONS.md` D-022（渲染稳定性为本项目最高优先级，冲突时让位于稳定性）。
> 本文件只记「用什么、证据在哪」；决策理由见 D-022，事故细节见 `ERRORS.md`。

## 1. 成熟库清单（T-026 第 3 条）

**不自行实现解析或渲染**，全部使用成熟库；版本随 `pyproject.toml` / `uv.lock` 锁定。

| 用途 | 库 | 版本 | 许可 | 引入位置 | 证据 |
| --- | --- | --- | --- | --- | --- |
| Markdown 分块解析 | markdown-it-py（CommonMark）+ mdit-py-plugins（dollarmath / tasklists） | 见 `uv.lock` | MIT | `src/mcwr/infrastructure/markdown_it_adapter.py` | `spikes/NOTES.md` Spike 1；`test_markdown_it_adapter.py`（14 项） |
| 数学公式 | KaTeX | 0.19.0 | MIT | `src/mcwr/assets/web/katex/`（含 20 个 woff2 字体） | `src/mcwr/assets/web/LICENSES.md`；`test_web_renderer.py::test_a_formula_renders_to_a_png_with_visible_content` |
| 图表 | Mermaid | 12.1.0 | MIT | `src/mcwr/assets/web/mermaid/dist/mermaid.min.js` | `LICENSES.md`；`test_web_renderer.py::test_a_mermaid_diagram_renders_to_a_non_blank_png` |
| 代码高亮 | Pygments | 见 `uv.lock` | BSD-2 | 依赖已声明（卡片正文渲染复用 Qt 的 Markdown 渲染） | `pyproject.toml` dependencies |
| 浏览器引擎 | QtWebEngine（Chromium，随 PySide6 6.12） | 6.12.0 | LGPLv3 / 商业 | `src/mcwr/infrastructure/web_renderer.py` | `test_web_renderer.py`；交付形态自检 `mcwr.exe --self-check` |
| PDF 栅格化 | QtPdf（`QPdfDocument.render`） | 6.12.0 | LGPLv3 / 商业 | 同上 | 同上 |

离线可用：KaTeX/Mermaid 随包分发，渲染时**不访问网络**（`_asset_paths` 只给出本地 `file://` 路径）。

## 2. 分层与错误隔离（T-026 第 1、2 条）

| 约束 | 落地方式 | 证据 |
| --- | --- | --- |
| 解析与渲染分离 | `domain` / `application` 不 import Qt、markdown-it、任何具体库；`infrastructure` 实现端口 | `tests/integration/test_render_stability.py::test_item_1_...` |
| 单卡失败不影响整板 | 渲染器任何失败返回 `None` 并记录原因；卡片保留文本形态 | `::test_item_9_...`、`test_a_failing_renderer_degrades_to_text_without_crashing` |

## 3. 异步、占位符与缓存（T-026 第 4、5 条）

| 约束 | 落地方式 | 证据 |
| --- | --- | --- |
| 异步渲染 + 可见占位符 | 渲染在事件循环的排队任务里逐卡进行；排队中的卡片标题栏显示「渲染中…」徽标，正文保持文本 | `::test_item_4_...` |
| 缓存异常自动降级重试 | 缓存按 `(kind, source, 桶)` 哈希落盘；空白栅格自动重打一次（`stats["retried"]`） | `web_renderer._render`、`test_web_renderer.py` |

## 4. 资源与性能底线（T-026 第 8、10 条）

| 约束 | 落地方式 | 实测 |
| --- | --- | --- |
| 每进程一个浏览器视图 | `web_renderer.shared_renderer()` 单例；`views_created()` 可断言 | 单例化前 200.7 s → 后 17.2 s（`ERRORS.md` E-016） |
| 首屏可交互 | 渲染不与打开阻塞（排队执行） | 冷缓存两卡 17.2 s；全量套件 16.6 s（251 项） |
| 失败不无限重试 | 空白重试 1 次即上报 | `stats["retried"]` / `failures` |

## 5. 日志与提示（T-026 第 9 条）

| 约束 | 落地方式 | 证据 |
| --- | --- | --- |
| 关键错误写日志 | `src/mcwr/shared/logging.py`：写 `%LOCALAPPDATA%\MarkdownCardWhiteboardReader\logs\mcwr.log`（可用 `MCWR_LOG_DIR` 重定向），1 MB 轮转、保留 3 份；**绝不写在 Markdown 同目录** | `::test_item_9_...` |
| 用户提示简洁 | 状态栏文案经 `shorten()` 截到 ≤ 40 字；完整信息进日志 | 同上 |
