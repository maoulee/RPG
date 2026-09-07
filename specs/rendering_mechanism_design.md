# 统一证据渲染机制设计（2026-08-21 立项，用户裁决：停止打地鼠，整体机制）

## 现状：13 个机制的补丁被子

分布于 4 个函数（_canonicalize_triples / _inline_events / _merge_edges /
_render_records），按到达顺序叠加，顺序敏感、路径分裂：

- **CVT 有两条渲染路径**（office-holder 记录路径 vs inline 事件路径），
  一致属性上提在两条路径各有一份实现（_uniform_attrs vs post-merge collapse）；
- **单次打印原则有三个入口**（记录键去重、首次括号内联、裸尾丢弃），
  语义相同、代码各异；
- 每个标本（Angelina/Sandler/Kim/Faroese/Gingrich…）暴露一个机制缺口，
  修补在缺口处再加一个 if——已验证会引入新交互 bug。

## 设计：五段管线 + 三条经济律 + 五条不变量

### 管线（严格顺序，段间单向）

```
S0 归一化    方向对齐（无向游走记录 → 图方向）；噪声关系类过滤
S1 事件化    每个CVT → 恰一个记录对象 {id, attrs{role→实体/值}}；
             记录是CVT的唯一真相源——辐条不再是独立边，是记录的派生视图
S2 同一化    边与记录按内容键去重（纯集合语义；零跨调用状态——B2终裁）
S3 分组      命名边按(h,r)分组；记录按(挂接头,关系)分组
S4 压缩+合成 三条经济律(下)作用于组，然后按统一行文法输出
```

**统一行文法**（唯一的输出形态）：
```
[(all: k=v; …)] head --rel--> payload | payload | …
payload := 命名实体 | 记录id [(判别属性)]
```
office 记录、测量记录、inline 事件统一为 payload 变体，不再是独立路径。

### 三条经济律（全部渲染层的压缩只来自这三条）

- **L1 组内一致律**：同一组的全部记录共享的属性 → 行首 `(all:)` 一次，
  各记录括号只留判别属性（一条实现，服务所有记录类型）；
- **L2 单次打印律**：任何实体（CVT 或命名）的载荷（属性括号/别名）在
  一次渲染中恰打印一次，后续引用为裸 id/名；
- **L3 预算律**：行数/尾数上限与 branch ref 折叠——只作用于渲染产物，
  从不作用于证据集合（完整性与经济性分离的终裁）。

### 五条可测不变量（回归门的判据）

- I1 每个事实三元组在视图中恰出现一次（L2 引用除外）；
- I2 每个CVT的属性集恰打印一次；
- I3 组内一致属性恰打印一次；
- I4 渲染零跨调用状态；
- I5 截断只发生在渲染层且带显式标记。

## 迁移与验证

1. **标本语料固化为 fixture**（每个历史标本一个断言）：
   Ethiopia(4L金链) / Nordic(回边消失) / Finland(date=value保留) /
   Düsseldorf(kind_of非空) / Gingrich(中心不断链) / Faroese(全量尾集) /
   Angelina(括号单次) / Sandler(辐条抑制+一致上提) / Kim(裸尾丢弃) /
   Vicksburg(记录归组)。任何改动全绿才算过。
2. 重写 _render_records 为五段管线（单函数 ~200 行，替代 4 函数 13 机制）；
3. 对照验证：同输入下新旧输出 diff 人工审 + I1-I5 程序化断言；
4. 100 例冒烟 → 错误集 A/B。

## 呈现层：概览+关系分块表格（2026-08-23 用户裁定，S4 的新合成形态）

**动机（质量主线）**：best-of-3 0.87 vs 单采样 0.72 的差距在答案层采样，
证据呈现驱动绑定选择。现行统一行文法把结构压进行内 `|` 列表，模型要逐行
扫描才能重建"这个子图有哪几条模式路径"的全貌。新形态：**①先给模式路径
概览（一眼看到结构），②再按关系分块、表格形式给证据详情（按列对齐比较
判别属性）**。示意（Brad Stevens case，实测输入）：

```
pattern paths:
  Brad Stevens --team--> Boston Celtics
  Brad Stevens --teams_coached--> [3 records]
  Boston Celtics --head_coach--> Brad Stevens

── team ─────────────────────────────
head          | tail
Brad Stevens  | Boston Celtics

── teams_coached ────────────────────
record    | position         | team
m.0w3_qv3 | Head coach       | Boston Celtics
m.0w48285 | Assistant Coach  | Butler Bulldogs men's basketball
(all: coach=Brad Stevens)

── head_coach ───────────────────────
head           | tail
Boston Celtics | Brad Stevens

candidates: ...(原样)   n_candidates: N   note: ...(原样——承重结构，一字不动)
```

### 与统一行文法/五段管线的关系（内部管线不变）

- S0-S3 照旧（S0 方向对齐仍由调用侧 `_canonicalize_triples` 完成——渲染器
  是纯函数，无 ctx 访问；S1 事件化=CVT→记录对象；S2 内容键去重；S3 分组）。
- **表格文法是 S4 输出的新合成形态**：压缩只来自三经济律（L1/L2/L3 全部
  照旧适用），只是把"统一行"换成"概览索引 + 关系分块表格"两层结构。
- 渲染器落位 `kgqa/stages/evidence_display.py`（纯函数、零外部状态），
  提供 `_render_records(all_triples, shown_edges) -> (lines, n_overlap)`
  的同签名 drop-in（`retrieve_subgraph` 调用点一线替换）；candidates/
  n_candidates/note 由调用侧 `_json_result` 原样拼装，渲染器不碰。
- 概览层是**索引**：每个 S3 分组恰一行（组数=概览行数，可断言），
  只含结构信息（head、关系、计数）；单例命名边组可内联其唯一尾（引用，
  L2 语义），多尾组显示前 2 尾 + `+N more` 显式标记；记录组显示
  `[N records]`。详情层（表格）才是事实载荷的唯一出处。

### 列生成规则

- **命名边组**（(h,r)→tails）：列固定为 `head | tail`，每个三元组一行；
  同关系多 head 的组并入同一块（行=边）。
- **CVT 记录组**（(head,rel)→records）：**末跳语义（修正 1）**——CVT 记录是
  模式路径的终点载荷，属性是终值、不可再游走。单记录（单 head）呈现为
  终点行 `  m.xxx [k=v; k=v]`（L3 括号，不再起表）；多记录/多 head 仍用
  记录表（首列 `record`、多 head 时插 `head` 列、其后判别属性列），块标题
  加 `(terminal records)` 标记终值语义。L1（all:）上提照旧；属性多值格用
  L2 括号并列。
- 列序：判别属性按组内首次出现顺序（确定性）；含日期列（from/to/date/
  year/...）的块内行按该日期升序（时间比较型问题的读表序）。
- 短名冲突：块按全名分键，标题用短名；两个不同全关系短名相同时，后到
  者标题退化为全名（确定性消歧）。
- 测量记录（date+value 对）与 office 记录、entity-bearing CVT 统一走
  同一记录表文法（date/value/holder/title 都只是属性列）——旧管线的
  holder/title 特判与 measurement 特判在表格文法下自然消解。
- 噪声规则沿用现产线：`_EDGE_NOISY_SHORT` 边与属性键过滤、自环丢弃、
  裸尾（零非噪属性记录）丢弃（Kim 标本）、`has_no_value` → 对应属性格
  `(incumbent)`。hub CVT（多组引用同一记录）：属性行只在首个组出现，
  后续组为**裸 id 引用行**（L2 在表格文法下的形态）。

### 同侧行折叠与多跳链（修正 2/3，2026-08-23 Mandela 审定）

- **同侧行折叠（修正 2）**：统一行的多对一语义回归表格——同块内尾集
  相同的 (head) 组合并为一行，join 侧（多值侧）单元格用 L2 括号并列；
  单 head 多尾的组把尾集折进一个单元格（_merge_edges 语义）。折叠后该
  块行数 = 不同 join 侧值（尾集）的个数；表头在确有多值格时才复数化
  （heads/tails）。
- **多跳链按路径呈现（修正 3）**：S2b 链重建——去重命名边中**贯穿节点**
  （in-degree=out-degree=1、非记录头、非自环）串成链（≤3 跳，回环不串，
  不确定保守不串）。链块列头 = 跳的关系序列短名（首列 `start`），每行 =
  一条具体实例链（start | 中间 | ... | 终点）；共享 (start, 关系序列,
  end) 的并行链合并为一行，中间跳扇出用 L2 括号并列。被链消费的边不再
  出现在单跳块。概览行 `  {start} --{r1}→{r2}--> {end}`（多链 `[N chains]`）。
- **分隔符层次（硬约束）**：三层不得混用——
  L1 `|` 只用于跳位/记录层（表格列间、概览行尾并列），**绝不进单元格**；
  L2 `(a; b; c)` 单元格内并列实体（折叠格、链扇出格、属性多值格）；
  L3 `[k=v; k=v]` 记录属性括号（沿用统一行文法）。
  保守回退：实体名本身含 `;`/`(`/`)` 的，该格不折叠/不并列，拆行呈现
  （层次无歧义优先于紧凑）；属性多值含不安全值时首值 + 精确 `…+K more`。

### 概览层:完整模式路径,一条 pattern 一行(修正 4/6,2026-08-23 Missouri/Ron Howard 审定)

概览行不再是逐边/逐三元组碎行,而是**pattern 级(模式形态)**:

- **每行 = 一条完整模式路径**;`{起点} --{r1}--> ?x --{r2}--> ?y`
  多跳一行写完,中间跳不拆行;
- **整条路径只有起点是实体**(锚点);后续节点一律占位槽(`?x/?y/...`),
  实例值全部住在下方块/表格——"Iowa --partially_contains--> Missouri
  River" 这类以实例开头的逐边行从概览消灭;
- **多中心(?var 展开)游走:锚点 = 中心集(修正 6)**——概览锚点渲染为
  变量符号 `?film`(接线传 anchor_label=?var 原始 token;无变量名时
  `(首成员; +N-1 more)`),同一 (关系,方向) 只一行,实例计数括注;
  **绝不逐成员出行**;成员出发的链按关系序列合并成一条集合锚点形状;
- **方向**:以锚点为起点的游走方向;逆向边用 `<--rel--` 记法;
- **去重**:distinct pattern = (锚点, 关系序列含方向, 终点槽类型);
  `[N records]` 终点形态保留(末跳记录语义不变);链 `(N chains)`;
  截断(`+N more paths`)照旧只作用行数;
- **锚点来源**:调用方传入 center 集 + ?var token(`_sg_finalize` 接线);
  非 center 组结构回退——同关系 ≥2 组共享单尾集 → 该尾为锚的逆
  pattern;无合并依据按组头局部锚。
- **断言**(check_invariants C4/C6):概览行数 == distinct pattern 数;
  每行仅起点为实体/集合符;载荷只许 ?slot/`[N records]`/计数;概览行
  禁 `|`;多中心 fixture 概览行数 == shape 数(个位数到十几,不是 73+)。

### 概览 = 真实 pattern 结构 + 严格起点锚定(修正 9 + C-raw,2026-08-23 Germany 审定)

- **C-raw(真实结构优先)**:概览行以 **PatternEvidence.tree_data 的真实
  游走路径为权威**(`{"nodes": [center, ...], "relations": [全名...]}`,
  接线处 `_sg_finalize` 汇总 top-5 patterns 的 paths 传入 `patterns=`);
  起点=游走中心(构造即 C9 合规),跳序/方向/终点(末节点 CVT→`[N records]`)
  全部取自真实结构;每方向解析对照展平边。展平边反推只作**补充**(覆盖
  raw_path 未覆盖的散边/泄漏关系,按 (关系短名,方向,终点类) 去重)。
  Germany 标本的 `contains→containedby (23 chains)` 这类形状现在天然来自
  游走结构(`Germany --partially_containedby--> ?x (23 instances)`)。
- **修正 9(起点锚定)**:pattern 行的锚只能是游走起点(单实体或集合符);
  **记录背边**(头≠起点、连到起点可达记录,如 Poland--adjoin_s-->同一
  记录)不产 pattern 行——背边实体作为记录属性值出现(`adjoins=(Germany;
  Poland)`),块内以裸 id 引用行承载该事实;非起点的散边/散记录同样只进
  块、不进概览。无 anchors 传入时回退修正 4 的结构行为(产线恒传)。
- **标题单一形状**:块标题 = 该块**主实例 pattern 的完整形状**(不再
  `/` 并置多方向——与 L1 `|` 层次混淆);其余方向在行内可见。
- **快检环(流程,2026-08-23 裁定)**:单 bug 修复的完整验证 = pytest +
  `tmp/fastcheck.txt` 10 标本 case 快检
  (`SPLIT=test_v4 CASE_FILTER=tmp/fastcheck.txt N_CASES=0 N_SAMPLES=1
  TEMP=0.3 CASE_BATCH=1000 LLM_MODE=http SEQ_PROMPT=V21 WALK_POOL=4
  OUT=tmp/fastcheck_out.json python -m kgqa.rl.seq_rollout`,~2 分钟);
  检查 ①零崩溃 ②标本块形态核对(起点锚定/列名/容量/引用)③机制事件
  计数(COMMIT/READY/无新增拒绝)。48×3/267×3 只在里程碑由主线程跑。

### 单一真相源:块也从 pattern 结构派生(修正 11,2026-08-24 Eleanor 审定)

**问题**:C-raw 后概览走 tree_data 真实路径、块走展平边分组——两条平行
数据路径天然漂移(Eleanor 标本:概览承诺 education 10 records / student 链
10 instances,块里只有 2 行;candidates 里的学生链实例在任何块里不可见;
链块载荷与链形状错位)。

- **形状块合成**:build_view 先解析 tree_data 路径为 shape groups
  (键=锚点+关系序列+终点类);每形状合成概览行**和**详情块——
  记录终点→记录组(属性自 CVT 映射,裸 id 引用防重复),单跳命名→
  边组(C2 折叠适用),多跳命名→链组(一条路径=一行实例链);
  **1-hop 形状吸收同 (成员头,关系) 的未覆盖展平实例**(tree_data 只带
  有界 witness,真实计数=路径+展平合并)。
- **展平降级纯补充**:形状跳边记入 covered;补充块只渲染未覆盖散边/
  散记录,概览不为其产行(维持修正 9);补充块中被形状已详述的记录
  降为裸 id 行(I2 跨块单次)。
- **C-consist 不变量**(进审计+fixture):①概览每形状计数 == 对应块
  实例行数(仅 shape-backed 块;结构补料 pattern 不受此约束——折叠块
  行数语义不同);②candidates ⊆ 全部块实体 ∪ (all:) 值 ∪ 记录属性格
  ∪ 裸 id(可选 candidates 参数逐调用核对);③链块第 k 列 = 第 k 跳
  终点(C7 列语义的形状级断言)。

### 表格列名 = 关系(修正 7,2026-08-23;废 head/tail 形式列)

- **任何块内不得出现 `head/heads/tail/tails` 字面列头**(硬断言,检查器
  逐表核对 report cols)。
- **块标题行 = 完整形状**(`── ?film --edited_by--> ?x ──`,记录块加
  `(terminal records)`,多方向 `/` 并列至多 2 + 计数);**列头 = 关系
  短名序列**,首列 = 锚点槽(实体名 / 集合符 `?film(43 centers)` /
  多起点块 `?node`);记录表 = [锚点列(多 head 时)] + 记录关系列
  (格 = m.id) + 属性关系列;链表 = 锚点槽 + 每跳关系一列(把链表形态
  普遍化到所有块)。
- **行内锚点侧在前**:逆向折叠行交换两格,首列恒为锚点侧;全逆块列头
  带 `<--rel` 记法。
- 折叠/L2 `(A; B; C)`/分支引用/计数标记全部保留,只换列名容器。

### 分支引用压缩提交(修正 5,2026-08-23 恢复;L3×提交协议)

V2 重写丢失了旧渲染器的分支引用机制(`_merge_edges` 的 `#head::relation`
压缩提交,answer 端 `_expand_branch_refs` 仍在但成了孤儿)。恢复:

- **发射点**:L3 预算截断隐藏答案候选处——折叠单元格超 cap(`…+K more`
  格内标记 + 引用行)、块内行超 cap(整组丢弃,引用行给出被丢组的引用,
  追加 `(also: #h2::r | #h3::r)` 最多 3 个);
- **语法**:`#anchor::relation`(与 `tools._BRANCH_RE =
  ^#(.{1,200}?)(?:::|\|)(.{1,300})$` 同步,本地副本防循环导入;relation
  用短名,展开端按全名/后缀/短名匹配);锚不安全(含 `#::|;/()` 或超长)
  则不发射;
- **锚选择**:尾集被截 → 锚=对侧首个显示实体(head);heads 被截 → 锚=
  该组首个显示尾(tail)——展开是方向无关的(center 匹配任一侧,收集对侧
  全量),两个折叠方向都合法;记录/链块的截断不发引用(展开器排除 CVT,
  引用会误导);
- **单一标记**:同一截断只出一个块级标记——cell-cap 出
  `+K more (total T). To answer with ALL of them, include "#a::r" as one
  answer entity — the system expands the ref to the full list.`;row-cap
  出 `... +K more edges (total M).` + 同款引用指令;不再并存
  `+N entities hidden` 之类的第二计数;
- **断言**:隐藏候选的边块必有引用;引用 token 过 `_BRANCH_RE` 语法;
  计数一致(显示数+more==总数,且 +more 能对上某发射格);端到端测试用
  真实 `_expand_branch_refs` 展开引用得全量(22-tail Celtics 标本 +
  137-tail 长尾 + heads-cap 逆向锚)。

### 预算律（L3）在表格下的语义（修正 8 重写:完整性优先,经济律只作用于极端 hub）

原则(旧规格"完整性与经济性分离"的正确落地):**模型绑不了它看不见的
东西**——单元格/行内 ≤120 实体一律全量显示;截断只允许发生在极端 hub
(单侧 >120)且必须带分支引用。

- **单元格实体上限 = 120**(L2 `;` 并列)——旧管线 `_MERGE_TAIL_CAP`
  的已验证容量(V2 重写时误压到 8,已回正);120 以内零 `…+N more`、
  零 hidden;
- **>120 触发截断**:格内 `…+K more` + 块级引用行(C5 机制,触发点
  上移到 120;`+K more (total T)`,显示数+more==总数);
- **块内行上限**(默认 40 折叠行)以**总行数为预算控制**,不以实体为
  单位截断;行超限丢弃的组带组级引用(`#head::rel` + `(also: …)`);
- **块数上限**(默认 12)与概览行上限(默认 20)照旧(修正 6 后概览是
  形状级,数量小);调用侧 `_TREE_LINE_BUDGET=200` 总行兜底不变;
- **单元格字符截断**:值 >120 字符加 `…`(高于最长真实实体名——实体名
  是答案候选,永不截断);日期键 ISO 时间戳取日期部分(格式化);
- I5 语义更新:断言「实体数 ≤120 的任何单元格/行必须全量显示」;一切
  截断带显式标记且计数精确。

### 五不变量在表格文法下的程序化断言（check_invariants）

- **I1**：每个被保留的事实三元组在**详情层恰出现一次**——折叠行/链行下
  语义为**每实体在所在行恰出现一次**（折叠单元格解析回实体多重集比对）；
  命名边=行；记录=record 行/终点行携其全部属性；链=实例链行；裸 id 引用
  行不计载荷。断言=视图结构与渲染文本回读的行/格实体多重集相等。
- **I2**：每个 CVT 的属性集恰打印一次（hub 引用行无属性格）。
- **I3**：组内一致属性恰打印一次——`(all:)` 行恰一条且这些键不出现在
  任何列/格（单 head 块）；多 head 块按 (all: head: k=v) 归属，上提键在
  该 head 的行内必须留白。
- **I4**：渲染零跨调用状态（同输入两次渲染逐字节相同；输入对象不被变异）。
- **I5**：一切截断带显式标记（行上限/块上限/格内实体上限/单元格/概览尾
  采样），标记内计数与隐藏量精确一致。
- **分隔符层次断言**：任何表格行的 `|` 分割数 == 列数（单元格内不得出现
  `|`）；格内并列一律 L2 括号形态。

### 验证与上线路径（阶段 1，2026-08-23）

1. fixture=17 历史标本 + 从 perf3_r267g3 真实轨迹重放挖取的 6-10 个
   代表性证据对象（CVT 密集/多关系/长尾集），断言=概览行数==组数、块数、
   表列集合、`(all:)` 单次、I1-I5 全绿（tests/test_evidence_display.py）；
2. **重渲染重放评测器**（一次性脚本）：对 48-cohort shaky 集 + 20 个
   已答对对照 case，重放工具调用至答案前（游走/GTE 确定性复现 evidence
   对象），monkeypatch `_render_records` 换新渲染，一次 LLM 调用只做
   答案层重答（重建历史 + ANSWER_READY 信号），对照已录答案/金标：
   错→对 / 对→错 / F1 delta / 答案层翻转代理；
3. 关系可达性检查器随重放运行：断言 retrieve_relations 展示的候选关系
   ⊆ 当前 center 的池（2-hop + CVT 透明跳 − 噪声），及"池内宣传但游走
   落空"事件计数——发现缺口只报告不修（修复涉 tools.py，等放行）；
4. 全绿 + 重放指标报告后，主线程放行 → 替换 `seq_tools._render_records`
  调用点（一线改动）。

### 阶段 1 结果（2026-08-23，已执行）

- **渲染器**：`kgqa/stages/evidence_display.py`（纯函数；`render_records_
  compat` 与 `_render_records` 同签名 drop-in）。真实数据挖出的 BUG 已修：
  多 head 记录块中，被组 A 上提 (all:) 的属性同时是组 B 的列时，组 A 的
  单元格曾仍打印该值（双重打印）——上提键的单元格强制留白。
- **fixtures**：tests/test_evidence_display.py 24 绿（17 标本 + compat +
  预算 + 9 个真实轨迹 fixture，tests/evidence_display_real_fixtures.json，
  含 8559-triple 的 CVT 密集块/长尾集）。
- **全量不变量审计**：重放 68 case 期间捕获的 **157 次真实渲染输入全部
  I1-I5 零违例**（renderer 修复后复跑确认）。
- **重放重答（答案层翻转代理）**：48 shaky cohort + 20 对照（sample 0，
  temp 0.3 × 2 重答；old 臂=录制的旧渲染同协议重答=采样基线臂）：
  * cohort: old 臂 meanF1 0.6434 (w2r 1 / r2w 2)；new 臂 0.6397 (w2r 0 /
    r2w 1)；delta −0.4pp（噪声带内）；all-hit 稳定性 72.9% vs 70.8%。
  * control: new 臂 meanF1 0.8708 == 录制 0.8708，20/20 保持命中，
    0 对→错。
  * 读法：新形态答案层**安全**（对照组零回归）；单次重答代理的功效
    看不出上行——上行假设（best-of-3 0.87 头寸）需要真实 rollout 验证。
- **重放保真**：68/68 重放成功；2 例 drift 标记为启发式误报（把
  entity_error/边界错误结果当成渲染计数——已修：只计含 triples: 的
  结果），两例数据实际一致。
- **可达性断言**：158 次 retrieve_relations 展示的候选关系全部 ⊆ 当前
  center 池（0 违例）；0 次"池内宣传但游走落空"。池过滤完备性在本次
  样本上无缺口。
- 工具：scripts/rerender_reanswer_eval.py（gitignored，一次性）；
  输出 tmp/rerender_eval.json + tmp/rerender_replay_only.json。

### 阶段 2 修正（2026-08-23，render_v2_g3 审定三修正,已实施）

接线已上产线（`seq_tools._sg_finalize` 的 `SEQ_RENDER_V2` env 门,默认开）。
用户审 render_v2_g3 失败相位 dump（Mandela case 为标本）裁定三修正+
分隔符层次硬约束（上文"同侧行折叠与多跳链"与"分隔符层次"小节）：

1. **修正 1（末跳记录）**：记录块改终点语义——单记录单 head 呈现
   `  m.xxx [k=v; k=v]`（不再起表）；多记录/多 head 保留属性列表格但
   块标题加 `(terminal records)`。末跳命题 corpus 验证（48 case 重放,
   1275 pattern / 17523 record 边）:**97.5% 记录边在 pattern 内无续走**;
   2.5%（442）存在从记录属性值出发的续走边（如 Brad Stevens coach 记录
   → teams_coached 记录）——这些续走边本就独立成块渲染,终点形态不隐藏
   任何事实（I1 审计全绿）。
2. **修正 2（同侧行折叠）**：共享尾集的 head 组合并一行、单 head 多尾
   折叠尾集（_merge_edges 语义回归表格）；折叠格 L2 括号并列。
3. **修正 3（多跳链）**：S2b 贯穿节点判定（in=out=1、非记录头、≤3 跳、
   回环/歧义保守不串）；链块列头=关系序列短名（首列 start），行=实例链；
   共享 (start,rels,end) 的并行链合并、中间跳扇出 L2 括号。
4. **分隔符层次（硬约束）**：L1 `|` 永不进单元格;L2 `(a; b; c)` 格内
   并列;L3 `[k=v]` 记录属性;含 `;/(/)` 实体不折叠拆行、属性多值不安全
   时首值+精确 `…+K more`。测试断言:任何表格行 `|` 分割数==列数。

**验证**：tests/test_evidence_display.py 32 绿（22 标本:含 Mandela
终点记录/折叠/链、中跳扇出 L2、`;` 回退、不安全属性多值+真实 9 fixtures
重审）;全套 pytest 98 绿;重放重答安全复核（render_v2_g3 的 20 已答对
对照,×3 重答/臂,成对种子）:old 臂（修正前 V2 文本重答,采样基线）r2w=3,
new 臂（修正后渲染）r2w=3,**翻转 case 重叠 2/3,渲染归因回归=0**
（new-only 1 例 1/3 采样翻转,old-only 1 例且 new 臂更优;两臂 any-hit
均 95%）。活重放 49 次渲染 I1-I5 全零违例。重物 fixture 压缩比:
8559 triples → 100 行（原 V2 199 行）。

## 状态
设计待用户裁决；裁决后实施（预计一次重写 + fixture 套件，不再有增量补丁）。
**2026-08-23 裁定**：呈现层采用"概览+关系分块表格"（本节），实施按
"验证与上线路径"四步走。**阶段 1 完成**（见"阶段 1 结果"）：渲染器 +
fixtures + 重放评测全绿，等主线程放行后做 `seq_tools._render_records`
调用点一线替换（阶段 2），再跑真实 267×3 验证 best-of-3 头寸。
