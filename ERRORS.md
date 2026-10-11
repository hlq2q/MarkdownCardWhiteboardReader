# ERRORS — 错误、根因与验证

- 最后更新：2026-10-12 02:58:21 +08:00
- 状态枚举：仅 open / fixed / wontfix
- 说明：本轮（MVP 开发）实际发生的事故。可迁移的通用机制已在各条「防止复发」中指向 `pitfall-playbook` §13，此处只留细节。

## E-001 清华镜像装不上 uv，pip 挂起 5 分钟

- 日期：2026-10-12
- 状态：fixed
- 现象：`python -m pip install --upgrade uv` 报 `Could not find a version that satisfies the requirement uv (from versions: none)`；换阿里云镜像后命令 300 s 无输出超时。
- 报错/日志：`ERROR: Could not find a version that satisfies the requirement uv (from versions: none)`；`curl https://pypi.tuna.tsinghua.edu.cn/simple/uv/ → 403`；阿里云索引页 707 KB 且 30 s 只下到 707 KB 的一半。
- 根因：本机 pip 全局索引被配置为清华镜像，该镜像对工具链请求返回 403；阿里云索引页体积大且此处速度极慢，pip 卡在下载索引阶段。
- 修复：改用 `-i https://pypi.org/simple` 安装（pypi.org 实测 3 MB/7.9 s）；此后所有依赖安装显式走 pypi.org。
- 验证：`pip install uv -i https://pypi.org/simple` → `uv 0.13.0`；`python -m uv sync` 退出 0。
- 关联任务：T-003
- 防止复发：装依赖前先探测索引可达性与速度（`curl -w "%{http_code} %{time_total}"`），不要连续重试同一镜像；记录在 README「开发环境」段（pitfall-playbook §13.18 依赖缺就静默回退的反面：显式探测 + 指引）。

## E-002 Qt 槽内异常被 PySide 吞掉：真实平台启动崩溃，测试却全绿

- 日期：2026-10-12
- 状态：fixed
- 现象：离线 GUI 冒烟测试 12/12 通过，但真实 Windows 平台启动时抛 `KeyError`，卡片重排失败；`QGraphicsScene::addItem: item has already been added to this scene` 警告刷屏。
- 报错/日志：`File "main_window.py", line 243, in _reparent_items / item = self._items[card_id] / KeyError: '75c6ba888c07'`。
- 根因：① `session.open` 先发 `cards_changed` 再发 `document_loaded`，而 `_apply_geometry → _reparent_items` 假设所有卡片都已有 item，且对已在场景中的 item 重复 `addItem`；② PySide6 对槽内未捕获异常只调用 `sys.excepthook` 打印后继续，pytest 只捕获 stderr，因此测试仍判通过（假绿）。
- 修复：v 改为按 `self._items.get(...)` 遍历并跳过缺失项、仅当 `item.scene() is None` 时 `addItem`；`_apply_geometry` 在 item 尚未建立时直接返回；并在 `tests/conftest.py` 安装 excepthook 守卫，把槽内异常升级为测试失败。
- 验证：真实平台复跑 `spikes/spike_real_window.py` → `items=19 zoom=35%` 且无 KeyError/无 addItem 警告；用一次性探针文件确认守卫确实会把「槽内抛异常」变成测试失败（跑完即删）。
- 关联任务：T-011
- 防止复发：任何「UI 回调里可能抛异常」的技术栈都要装等价守卫；测试通过不等于真实入口可用（pitfall-playbook §13.1、§11 #10）。

## E-003 卡片身份键构造有碰撞风险（分隔符拼接）

- 日期：2026-10-12
- 状态：fixed
- 现象：`test_heading_path_segments_cannot_collide` 失败：`("a\x1fb",)` 与 `("a","b")` 生成同一个 `stable_key`。
- 报错/日志：`AssertionError: assert '242d85d318f2' != '242d85d318f2'`。
- 根因：键载荷用 `\x1f` 同时拼接「字段」与「标题路径分段」，标题文本里一旦含该字符即可构造歧义输入。
- 修复：`domain/ids.stable_key` 改为 `json.dumps([...])` 作为哈希载荷（JSON 会转义控制字符，结构无歧义）。
- 验证：该测试通过；`test_stable_key_reacts_to_structure` 等其余键测试仍绿。
- 关联任务：T-004
- 防止复发：任何「多字段拼成一个键/路径/命令」的地方都要用有转义语义的编码（JSON/长度前缀），不要用裸分隔符（pitfall-playbook §13.23 凭语法推理转义的反面：用结构化解码）。

## E-004 不变量漏算分隔线块，导致「块零丢失」检查误报

- 日期：2026-10-12
- 状态：fixed
- 现象：含 `---` 的文档建树后不变量检查报 `block coverage mismatch; missing=[6]`。
- 报错/日志：`FAILED test_every_block_is_owned_exactly_once`。
- 根因：分隔线只作为大卡片边界、不归属任何卡片，但 `tree_problems` 要求覆盖 `range(block_count)` 全部索引。
- 修复：新增 `required_block_indexes(blocks)`（排除 `THERMATIC_BREAK`），`tree_problems` 改收 `required_indexes` 参数。
- 验证：`test_every_block_is_owned_exactly_once`、`test_invariants_*` 全绿；真实样例文档 `blocks=25` 全部归位。
- 关联任务：T-004 T-005
- 防止复发：断言「全覆盖」时先显式定义「哪些必须被覆盖」，否则结构性元素会造成误报并掩盖真丢失。

## E-005 适应视图把缩放压到 1%（越过下限）

- 日期：2026-10-12
- 状态：fixed
- 现象：验收测试 `test_acceptance_9_...` 报 `assert 10.0 <= 0.9975...`：`fit_cards()` 后缩放变成 0.997%。
- 报错/日志：`assert 10.0 <= 0.997506234413965`。
- 根因：`board_view.fit_cards` 只在结果超过 `MAX_SCALE` 时夹取，没有处理低于 `MIN_SCALE` 的情况（长文档一次性 fit 会压到极小）。
- 修复：fit 后统一夹取到 `[MIN_SCALE, MAX_SCALE]`，越界时走 `set_zoom`（同时发 `zoom_changed`）。
- 验证：验收 9 通过；`set_zoom(1000)`→800%、`set_zoom(0.001)`→10% 均有断言。
- 关联任务：T-011 T-013
- 防止复发：凡「把外部/计算值写进受约束状态」处，上下限都要有测试；只测上限是最常见的漏测。

## E-006 解码失败直接拒绝打开文件

- 日期：2026-10-12
- 状态：fixed
- 现象：验收 10 期望「异常不崩溃且有降级」，实现却让 `open_path` 返回 False（文件打不开）。
- 报错/日志：`assert opened is True, "an undecodable file degrades, it does not abort the open"`。
- 根因：`FileMarkdownReader._decode` 在所有候选编码失败后抛 `DocumentDecodeError`，上层无降级分支。
- 修复：候选编码全部失败时用首个候选 + `errors="replace"` 解码，并附警告「decoded ... with replacement characters」，保证窗口能打开且提示可见；仅当候选列表为空（编程错误）才抛错。
- 验证：`test_undecodable_bytes_degrade_with_replacement_characters`、`test_empty_candidate_list_is_a_programming_error`、验收 10 均通过。
- 关联任务：T-006 T-013
- 防止复发：需求里写「降级」的地方，必须有一条测试断言「降级后仍然可用」，否则实现很容易退化成「直接失败」。

## E-007 离屏 `QWebEngineView.grab()` 返回未绘制表面，空白图被当成成功缓存

- 日期：2026-10-12
- 状态：fixed
- 现象：渲染返回了 PNG 文件，肉眼却是纯色（浅灰/白）；早期「非空白」检查只判「是否几乎全白」，于是把未绘制的灰面当成功写入缓存。
- 报错/日志：无异常；`spikes/_out/*_view-window_z*.png` 为纯色；后续图像判据发现 `near-uniform frame`。
- 根因：无头进程里（`QT_QPA_PLATFORM=offscreen` 或 `windows` + `WA_DontShowOnScreen`）QWebEngineView 的**部件表面从不合成**，`grab()` 拿到的是未绘制的 backing store；页面自身渲染正常（`mcwrState=done`）。
- 修复：改用 Chromium 的打印管线——`QWebEnginePage.printToPdf` → `QPdfDocument.render(size)`，矢量源按档位栅格化；同时把空白判据改为「拒绝任何近纯色帧」。
- 验证：渲染器 46 项测试通过；App 内实测数学卡输出 `E = mc²`、Mermaid 卡输出流程图（逐张看图核验）；缓存命中 0.1 ms。
- 关联任务：T-014
- 防止复发：无头环境下不要相信「部件截屏」；改用引擎自身的导出接口（打印/导出图），且图像判据必须能拒绝「近纯色」（pitfall-playbook §13.1「事件已发生 ≠ 数据已就绪」的同类）。

## E-008 跨图串帧：数学卡与 Mermaid 卡缓存出同一张图

- 日期：2026-10-12
- 状态：fixed
- 现象：App 跑完后缓存里 `web-math-*.png` 与 `web-mermaid-*.png` **md5 完全相同**，都是那张 Mermaid 流程图；界面上一张公式卡显示成流程图。
- 报错/日志：`md5sum` 两者一致；两张图人工查看确认为同一流程图。
- 根因：渲染管线在「等页面稳定」时只要求连续 N 帧一致——**旧内容本身就是稳定的**，稳定 ≠ 新内容已绘制；第二张卡因此拿到了上一张的画面。
- 修复：改用打印管线（同一页面按当前 DOM 打印，天然消除合成帧陈旧问题）；并加回归守卫 `test_two_web_cards_do_not_render_the_same_image`（每轮用全新缓存目录，断言不同卡片的像素不同）。
- 验证：该守卫通过；App 内两卡 md5 不同（`43e3e8...` vs `340243...`）。
- 关联任务：T-014
- 防止复发：「等稳定」类判据必须同时验证**内容已更新**（换内容或换签名），否则静态旧值永远满足；缓存命中会把错误结果伪装成通过。

## E-009 App 路径下每次渲染都超时（页面其实已渲染成功）

- 日期：2026-10-12
- 状态：fixed
- 现象：经 GUI 打开文档后公式/Mermaid 卡片全部退回纯文本；渲染器 `stats={'rendered': 0, 'failed': 3}`，而同一进程里查询页面得到 `mcwrRender=function, mcwrState=done, mcwrRenders=2`。
- 报错/日志：`render failed: timed out after 5000 ms`；探针 `page state: ["function","done",2,"complete",...]`。
- 根因（两处叠加）：① 轮询切片 250 ms 短于应用内 `runJavaScript` 回调到达时间（实测约 300 ms），轮询在答案到达前就重发命令，15 s 预算只够约 11 次读取，不足以覆盖 Mermaid 渲染；② 期望的渲染序号取自 Python 本地计数，而页面计数只在真正开始渲染时自增，二者错位后期望值永远达不到。
- 修复：轮询切片提到 1500 ms、默认超时 15 s；期望序号改为「先读页面计数再加一」；把 JS 的 `false` 明确当作「尚未完成」而非最终答案。
- 验证：App 内实测两卡各出图、`rendered_images=2/2`；集成测试 `test_body_render.py` 通过；打包产物自检 `rendered_images=2`。
- 关联任务：T-014 T-015
- 防止复发：跨语言/跨进程轮询必须「以对端状态为准」而不是本地计数；超时预算要与对端最慢路径匹配并有实测值（pitfall-playbook §13.1、§11 #33）。

## E-010 打包后渲染完全失效：spec 的 excludes 误删 QtWebChannel

- 日期：2026-10-12
- 状态：fixed
- 现象：源码形态一切正常；打包产物能打开文档（`cards=5`），但 `rendered_images=0`，公式/Mermaid 卡片全部退回文本。
- 报错/日志：自检报告 `{"opened": true, "rendered_images": 0, "frozen": true}`；加诊断后得到 `renderer_build_error: "ImportError: libshiboken: could not import module 'PySide6.QtWebChannel'"`。
- 根因：`packaging/mcwr.spec` 为减小体积把 `PySide6.QtWebChannel`/`QtQml`/`QtQuick` 等列入 excludes，而 `QtWebEngineWidgets` 依赖 QtWebChannel。
- 修复：从 excludes 移除 WebEngine 相关依赖链（QtWebChannel、QtWebSockets、QtQml、QtQuick、QtQuickWidgets、QtOpenGLFunctions、QtPdfWidgets），只保留确实无关的重模块；并在 spec 注释里写明原因。
- 验证：重建后 `dist\mcwr\mcwr.exe --self-check spikes\samples\sample.md` 退出码 0，`frozen=true`、`cards=19`、`web_cards=2`、`rendered_images=2`。
- 关联任务：T-015
- 防止复发：**打包产物必须在交付形态下自检**（`--self-check` 返回非 0 即失败）；减体积的 excludes 列表必须逐个验证真实功能（pitfall-playbook §11 #21「只在源码形态验证」）。

## E-011 渲染器构造异常发生在 Qt 槽内，被吞掉后静默不出图

- 日期：2026-10-12
- 状态：fixed
- 现象：打包后无图，但状态栏无提示、自检报告里 `renderer_error` 为 `null`（因为渲染器根本没被构造成功，异常消失在 Qt 槽里）。
- 报错/日志：`renderer_error: null`（误导），实际异常为 `ImportError: ... QtWebChannel`。
- 根因：`main_window._render_next_body` 里惰性构造渲染器的语句没有 try/except，异常在 Qt 定时器槽内被 PySide 吞掉——与 E-002 同一机制。
- 修复：构造失败时记录 `_renderer_error` 并经 `session.failed` 上报状态栏；`MainWindow.renderer_build_error` 暴露给自检。
- 验证：修好 excludes 前后 `renderer_build_error` 分别给出明确 `ImportError` 文本与空串（`{"renderer_build_error": ""}`）。
- 关联任务：T-015
- 防止复发：惰性构造/延迟初始化（`QTimer`、信号槽、回调）里的任何构造都要包错误上报，否则「不工作」与「没问题」在日志上无法区分（pitfall-playbook §13.9 同类）。

## E-012 自检文档里数学块闭合符写错，公式被解析成代码块

- 日期：2026-10-12
- 状态：fixed
- 现象：自检报告 `cards=4`、`web_cards=1`（期望 5 与 2），数学卡没出现。
- 报错/日志：`mcwr cards` 输出把 `$$ ... ` 显示为 `[code] code`，文档第 12 行是三反引号而非 `$$`。
- 根因：写 `SELF_CHECK_DOCUMENT` 时把数学块的闭合 `$$` 误敲成三反引号，导致该行既结束了 Mermaid 围栏又开启了新的代码块，后续内容被吞。
- 修复：改成正确的 `$$` 闭合；表格中的示例数字同步修正为 5。
- 验证：`mcwr cards` 对自检文档输出 `cards=5 blocks=5`，含 `[math_block]`；自检 `web_cards=2`、`rendered_images=2`、退出码 0。
- 关联任务：T-015
- 防止复发：自检/夹具文档要有一句「块类型断言」的校验（本次正是靠 `web_cards` 数量发现），不要只看「打开了没有」。

## E-013 全量套件下 app 路径渲染偶发 0/2（xfail），单独运行正常

- 日期：2026-10-12
- 状态：fixed（2026-10-12 定位并修复；根因见下，与 E-016 / E-017 是同一现象的两个叠加原因）
- 现象：全量 `pytest -q` 中 `test_two_web_cards_do_not_render_the_same_image` 出现 xfail（`only 0/2 cards got an image`），同一测试单独运行通过；复现率约 2/10。
- 报错/日志：`XFAIL ... only 0/2 cards got an image`；后续测得真凶是 `render failed: rasterized image is blank`（E-017）与进程内第二个 WebEngine 视图（E-016）。
- 根因（已验证）：① 每个测试各自建窗口并按 **25 s** 预算排空渲染队列，而冷启动 WebEngine + 两张位图实测约 **20 s/测试**（≈85% 预算被吃掉），全量套件里稍有额外负载就越界；② 约 20% 的运行里 Mermaid 卡的 PDF 栅格化返回空白且**不重试**（E-017）；③ 同进程内多个渲染器实例互相争用（E-016），把冷渲染从 17.2 s 拖到 200.7 s。
- 修复：① 渲染集成测试改为**每模块一次渲染会话**、预算提到 90 s（≈4.5× 实测），并把实测耗时作为性能断言（`PERF_CEILING_S = 60`）；② 渲染器对空白栅格**自动重试一次**（E-017）；③ 渲染器改为**进程级单例**，非渲染类集成测试用空渲染器（E-016）；④ 排空循环在渲染器已给出最终失败时快速失败，避免 90 s 空等。
- 验证：修复前 10 次全量运行 2 次失败（各 95 s）；修复后**连续 16 次全量运行全绿**（`251 passed`，每次 17–18 s，0 xfail）。单文件冷缓存 4 项 17.95 s。
- 关联任务：T-016（已 done）
- 防止复发：慢测试的预算必须按**实测最坏值 × 系数**设定并留证据；`xfail` 只能表示「环境不可用」，不得用于掩盖抖动；共享资源上的断言不得使用绝对值（见 E-018）。

## E-016 同一进程创建第二个 WebEngine 视图，渲染慢 11 倍

- 日期：2026-10-12
- 状态：fixed
- 现象：渲染集成测试单独运行 17.2 s；在全量套件（`src/mcwr/infrastructure/test_web_renderer.py` 先跑过）中同一段渲染耗时 **200.7 s**，并因此触发性能断言失败。
- 报错/日志：`AssertionError: cold render took 200.7s, ceiling is 60s`；`--durations` 显示除该 setup 外所有用例均为毫秒级。
- 根因（已验证）：`MainWindow` 在 `renderer=None` 时惰性调用 `container.build_web_renderer()`，而集成套件里 **11 处**窗口各建一个渲染器实例 → 同进程出现多个隐藏 `QWebEngineView`。QtWebEngine 在同进程内不支持干净的重复初始化，第二个视图带来数量级退化（渲染器自身 docstring 早已声明「一个进程一个页面」，但没有任何机制强制）。
- 修复：`web_renderer.shared_renderer()` 提供**进程级单例**（`container.build_web_renderer()` 改用它）；`tests/integration/conftest.py` 把容器工厂替换为空渲染器，使非渲染类集成测试完全不起 Chromium；渲染类测试（两个模块）都通过 `shared_renderer` 取同一实例；新增 `views_created()` 计数器供测试断言不变量。
- 验证：全量套件 **204.67 s（1 failed, 250 passed）→ 16.63 s（251 passed）**，约 12× 提速；`views_created() <= 1` 断言常驻于渲染测试。
- 关联任务：T-016 T-026（对应 D-022 第 8 条资源管理）
- 防止复发：单进程单例型资源（浏览器引擎、GPU、数据库句柄）必须有显式单例入口 + 计数器，让「多实例」成为可测事实而不是性能玄学。

## E-017 约 20% 的运行里 Mermaid 卡栅格化为空白，且不重试

- 日期：2026-10-12
- 状态：fixed
- 现象：全量套件约 2/10 的运行里，两张 web 卡只有一张出图；失败卡永久保持纯文本，排空循环因此空等到 90 s。
- 报错/日志：`renderer last error: render failed: rasterized image is blank`（对应卡片为 Mermaid）。
- 根因（已验证）：`printToPdf` → `QPdfDocument.render` 路径偶发得到近纯色帧（页面尚未完成绘制/布局时打印），而 `_render` 把「空白」当作**终局失败**直接返回 None。这违反 D-022 第 5 条「缓存失效或异常时不能导致崩溃，应自动降级重试或重新渲染」。
- 修复：`_render` 在失败原因含 `blank` 时暂停 250 ms 后**再打印并栅格化一次**；成功则计入 `stats["retried"]`，仍失败才上报（错误信息带 `after a retry`）。
- 验证：改前 10 次全量运行 2 红（各 95 s）；改后 **16 次连续全绿**（251 passed，17–18 s）。`stats` 新增 `retried` 计数器可观测重试是否发生。
- 关联任务：T-016 T-026（对应 D-022 第 5 条）
- 防止复发：任何「一次失败即放弃」的外部渲染/导出路径都要有一次重试，并把重试次数暴露成计数器，否则偶发失败会被当成环境噪声。

## E-018 共享单例后，绝对计数断言变脆弱（`rendered == 1` 实际为 4）

- 日期：2026-10-12
- 状态：fixed
- 现象：把渲染器改成进程单例后，`test_a_formula_renders_to_a_png_with_visible_content` 失败：`assert 4 == 1`（期望本模块只渲染 1 次）。
- 报错/日志：`> assert renderer.stats["rendered"] == 1 / E assert 4 == 1`。
- 根因：该断言假设「渲染器只被本测试文件使用」。单例把它变成跨模块共享状态，先跑的 `tests/integration/test_body_render.py` 已渲染 2 个 payload，计数自然不为 1 —— 与实现无关，是**测试对共享资源使用绝对值断言**。
- 修复：把该文件的计数断言改为增量或下界（`rendered >= 1`、`failed >= 1`），保留「缓存命中不增加 rendered」的增量断言（该处本来就是 `before/after` 形式）。
- 验证：全量套件 16 次连续全绿；`ruff`/`mypy` 干净。
- 关联任务：T-016
- 防止复发：共享/单例资源上的断言只用「增量」或「不变量」，不用绝对值；测试顺序变化不应改变结果。

## E-014 用管道末位退出码判断子进程结果，掩盖了失败

- 日期：2026-10-12
- 状态：fixed
- 现象：自检命令显示 `exit=0`，实际应用返回 1（渲染 0 张图）；另有一次 `uv sync` 的 job 报告 `exit code 1` 而依赖其实装好了。
- 报错/日志：`python ... --self-check | grep -E "^\{|error" ...; echo "exit=$?"` → `exit=0`（这是 `grep` 的退出码）。
- 根因：管道/`Select-Object` 之后 `$?`/`$LASTEXITCODE` 反映的是最后一个命令；窗口子系统 exe 还会让 Shell 不等待，`$LASTEXITCODE` 为空。
- 修复：改用 `Start-Process -Wait -PassThru` 取 `ExitCode`；应用侧把报告同时写入 `MCWR_SELF_CHECK_REPORT` 指定文件，避免依赖 stdout。
- 验证：`Start-Process ... -Wait` 得到真实 `exit code: 0`（修复前为 1）并读到报告 JSON。
- 关联任务：T-015
- 防止复发：判定子进程成败只认它自己的退出码与产物；管道中的 grep/`Select-Object` 一律不作为判据（pitfall-playbook §11 #22「子进程日志污染输出」、§13 同类）。

## E-015 同一文件两种写入通道（shell `sed -i` 与文件工具混用）

- 日期：2026-10-12
- 状态：fixed
- 现象：对 `spikes/spike_app_render_probe.py` 用 `sed -i` 改过之后，文件工具报 `cannot edit ...: file changed since it was read — re-read the file, then retry`。
- 报错/日志：`Error: cannot edit "...": file changed since it was read`。
- 根因：文件工具的版本守卫按「工具观测到的版本」判断；用 shell 直接改文件不经过该通道，守卫看到的是未知变更。
- 修复：重新 `read` 该文件后再用文件工具编辑（不要绕过）。
- 验证：重读后编辑成功并跑通。
- 关联任务：—
- 防止复发：一个文件只走一条写入通道；需要批量替换时用 `ops_replace`，不要用 `sed -i` 混搭（pitfall-playbook §11 #1）。
