# Session Memory — subgraph (KGQA agent)

### 2026-09-15 十补:GTE 排序根因 = last-2 截断丢失域前缀(b3c44e1 已修)
- **用户问题**:"嵌入不是跟人类语义对齐了吗,为什么 border→adjoins
  排 #11?" — 分解实验给了决定性答案:
  | 标签格式 | adjoins 排名 |
  |---|---|
  | last-1 (`adjoins`) | **#1** |
  | **last-2 (当前,`relationship.adjoins`)** | **#13** ← 问题 |
  | last-3 (`location adjoining relationship adjoins`) | **#1** |
  | 全名 | **#1** |
  | 自然语言化(去点/下划线) | **#1** |
- **根因**:last-2 恰好切掉 `location.` 域前缀;剩下的
  `adjoining_relationship.adjoins` 被中介名 `adjoining_relationship`
  拖偏(它本身不像"边界")。last-1/last-3/全名让 `adjoins` 核心词
  与 `location` 上下文一起呈现,语义恢复。
- **GTE 本身无罪**——嵌入对人类语义对齐很好,问题纯粹是候选文本
  截断了语义信号。
- **修复**:`_rel_last2` → last-3(`domain.type.attribute`,
  下划线→空格)。验证:1278d3da 模型现在直接选 adjoins;
  153 绿。
- 指令实验附带发现(7 配置对比):QUERY-SIDE-REWRITE(问句改写为
  "adjacent to or share a border")让 adjoin_s 排 #2——问句侧
  改写也有提升空间,但修标签格式已解决主问题。

### 2026-09-15 九补:跨层模式爆炸修复(534d55a)
- **用户发现**:24353bbc 子图2渲染出 9 个模式段——"第一层 top3 ×
  第二层 top3 = 9"的跨层笛卡尔积爆炸。设计应该是**整体模式路径
  也做 top-K 选择**(第二层重走后,全链按语义排 top-3,展示比
  第一层多了什么关键信息)。
- **修复**:`_patterns_from_layers` 加 top-K 链选择(K=3 与 derive
  对齐,短链优先+确定性排序),从源头砍掉爆炸。
- **验证**:24353bbc 9→6 段(渲染 7400→5765 字符)、1278d3da
  →3 段(4161 字符);分数 0.87/0.20 稳定;153 绿。
- **rr 候选问题(同轮发现)**:"which states does this river bisect"
  的候选里没有 contains/partially_contains——GTE 词汇重叠低,
  需要候选标签增强(问题 2 待修)。

### 2026-09-15 八补:层操作语义 + 提示语修改 + ≡标记(bdc46fa)
- **用户裁定**:更新/延长由**中心位置**决定——中心在最后层完成集=
  往前走 → EXTEND(追加);中心在更早层或根 = 同一步找方向 →
  UPDATE(替换该层关系集,清除不在新提交中的旧关系)。树链入双信号
  (实体+plan,保守方向)。实施 `SEQ_LAYER_OPS=1`(默认开):
  `_center_layer` 追踪中心所在层,据此分 extend / update:k / repeat;
  `layer_action` 回显让模型首次看到系统做了什么操作。
- **提示语三处**:§0 SEQUENCE EXTENSION 重写(教 "submit ALL
  semantically-matching relations together in ONE call" + root=update/
  frontier=extend 语义);§2.4 追加 "splitting semantic equivalents
  across calls wastes budget";state_aware_hint 改 "pick ALL structural
  bridge relations that encode the same semantic fact — submit them
  TOGETHER"。rr grouped_relations 行内同 domain.type 前缀追加 ≡ 标记。
- **迷你验证**:24353bbc **0.89**(历史最高,超旧栈 0.79);关系提交
  分布从 14:4(单:双)改善到 **7:5:1**(多关系提交占多数);
  layer_action echo 出现(extend×3, update×1)。1278d3da 0.07
  (答案层 tie 仍主导,证据已齐)。

### 2026-09-15 七补:链约束落地(603e3a8)+ 三问题修复状态
- **问题 3 已修**:序列存在时 declared-only(必须穿过已积层,
  满足整个关系链),自由枚举仅首次调用。验证:military_combatant
  自由链从 co2 结果中消失(free-enum=0)。迷你:1278d3da 0.27/
  24353bbc 0.63——分数仍卡答案层。
- 问题 1(单关系提交)与问题 2(GTE border→adjoins #11)待修。

### 2026-09-15 六补:用户轨迹审阅三大发现(待修,优先级排)
- **问题1:单关系提交回潮**。attrfix 轮 14/18 次 retrieve_subgraph
  只提交 1 个关系(设计是 2-3 个相关关系一起交,V21 §2.4)。诱因:
    type+value 分组显示后组间无重叠,模型不再"选一组=选多关系"。
  修向:rr 渲染恢复语义同族分组(如 adjoins/adjoin_s 并组)+
  组级提交提示;或在 grouped_relations 行内直接给"同义关系集合"。
- **问题2:GTE 排序回退实证**。"which countries border this country"
  对 France 池:adjoins 真实排名 **#11**(0.571),top10 全是
  containedby/contains/basin_countries 等容器类。这不是
  union-rank 引入的(离线复现原 per-entity 路径同序)——GTE 对
  "border→adjoins" 的语义匹配本身弱。修向:rr 问句改写提升
  词汇重叠(把 "border" 映射为 "adjoins/adjoin_s" 语域),或
  candidate label 中携带完整关系路径提示。
- **问题3(最核心):跨层约束缺失**。用户:第二子图的实体"不应该
  只满足第二个 step 的关系,还需要跟前面子图的关系有约束,某些
  起点实体应该跟前面的子图做重叠"。现状:derive-union(fix:
  declared∪derived)重新引入了自由枚举——military_combatant→co2
  等链出现,并非穿过已走的第一层关系。修向:**链枚举以前缀层
  为约束**——序列存在时,derived patterns 必须以已积层为前缀
  (derive 的 hop1 限定在 L1 关系集内),自由枚举仅在无序列时。

> **Purpose**: This file survives container resets. It is the operational

## 2026-09-15:关系序列参数 SEQ_REL_SEQ 落地(37a0a93,门默认关)
- **机制**(用户设计,参数累积语义):权威状态=ctx.anchor_seqs
  {锚:[L1关系集,L2...]}(运行期 setattr,与 fid_pattern 同惯例);
  同锚 retrieve_subgraph=追加——提交关系按**最深可行层**归层
  (两遍式:先按原完成集全判,再落地;同调用的前沿关系共享同一新层),
  声明层直接构建 multistep patterns(推导降级为兜底),下游
  语义配额/保证通道/license/V38 渲染零改动复用。
- **关键实现语义**(调试中确立,易错点):
  ① 层间接棒必须用**透明命名步进**(id 节点↔名字节点经 object.name
  桥接——actor.film 原始边落在 m.0gwrkz0,判别边挂在名字节点上,
  裸转移会判不可行)+ 跨层 visited 防回环;
  ② **最后一层只查原始边非空**(值型终点是 CVT/悬空节点,
  命名集为空≠不可行——这正是判别器家族的形状);
  ③ 同层兄弟一次提交共享新层(中途改 layers 会越界+拆层)。
- **配套面**:anchor_sequence 回显(层标签+完成数,教模型"锚+新关系"
  续层);_rr_prepare 前沿池扩展(菜单从序列前沿取池,摆脱检查点绑定);
  WALK_POOL=0 元组摊平 latent bug 修复;SEQ_AGENTS_V21 加
  SEQUENCE EXTENSION 条目(§0 格式块未动);schema description 更新。
- **验证**:tests/test_rel_seq.py 10 用例(分类/层积/裁剪/记忆化);
  tmp/relseq_specimen_test.py 真实 case 两调用标本——runtime/tvrage
  均:追加成层+声明模式(actor.film,判别关系)+echo 生成+gold 在
  透明前沿;pytest 153 绿。
- 48×3 SEQ_REL_SEQ=1 验证轮判决(reports/v38_relseq_48x3.json):
  **f1 0.6571 / hit 79.2%**——hit 超三 run 带顶(75.7-78.5)2.8pp,
  f1 带顶(unionrank 0.6558);**采用率 12%**(18/144 轨迹见过
  anchor_sequence echo)——机制生效但模型少用,头部空间在提示语引导。
  家族:c7fffe30(tvrage)0→**0.67**、eb615bab 0→**0.78** 结构性赢;
  d9206043/1278d3da 回落(churn 量级)。判决:方向正、单轮、
  采用受限——**门默认保持 0,站立 env 加 SEQ_REL_SEQ=1 积累样本**,
  采用率引导(提示语/echo 强化)列为下一步。
- **用户裁定更正(同日):叠加是系统默认行为,不是模型选用的调用形式**
  ——"采用率"概念作废。只要中心命中某锚树的成员(锚/任层完成集/
  手打名单子集/?var 绑定,结构上同一回事)即自动续树:关系入最深
  可行层、游走中心被**根替换**、从根实例化全链;只有不在任何树上
  的中心才另起新根。根优先=前沿可行>最深。实施(fdb7c3f):
  成员匹配自动续接 + **门默认翻 1**;提示语/schema 改自动语义。
  手打名单标本(s0/s1 失败形态)通过:传 Twilight/Abduction 仍续到
  Lautner 树、centers→[Lautner]、模式 (actor.film, runtime) 声明。
  pytest 153 绿。48×3 默认开实测**首战**
  (reports/v38_relseq_auto_48x3.json):
  **f1 0.6915 / hit 79.9%——f1 超三 run 带顶(0.6587)3.3pp,多步栈
  历史最高,逼近单步栈均值 0.6826**;续接 echo 覆盖 58% 轨迹
  (自动续接生效);判别器家族全面正向(tvrage 0→**1.00**、
  d9206043 0.50→**1.00**、027d077f runtime→0.67、6d6f2ca8 0→0.33、
  f85999f1 0→0.22、deflator→0.51;仅 1278d3da 回落待查)。
  **副作用为正**:walk 相位 3426s(pq_r2 轮 25711s)、GTE 调用
  1626 次(2980)——序列化游走更定向。r2/r3 复跑进行中凑三 run
  均值正式判决。
- **三 run 均值终判(reports/v38_relseq_auto{,_r2,_r3}_48x3.json)**:
  **f1 0.6709 / hit 78.0%**(spread 0.6515-0.6915/76.4-79.9,方差比
  单步栈大)——**+2.0pp f1 over 旧多步栈均值(0.6513),多步栈新
  站立配置**;距单步栈均值(0.6826)尚差 1.2pp,但逐 case 互补:
  relseq 赢 21/输 15/平 12——判别器族全在我们侧(d9206043 +0.78/
  deflator +0.41/027d077f +0.32),输面是答案层已知翻转家族
  (ab5818ba/1c0686c5/24353bbc——轨迹 echo=0,未触发续接,
  NONE/表象回潮,churn 非机制损伤)。两栈互补格局与此前"单步
  优势集中在作答层"结论一致——作答层另有 AOP/V6 线程。
- 运维:标准 env 的多步族现在含 SEQ_REL_SEQ(默认 1);
  回退开关 SEQ_REL_SEQ=0。

### 2026-09-15 补:回归家族取证(用户质疑成立,推翻"churn"结论)
- 用户判定正确:1278d3da/24353bbc 对旧多步栈是真回归
  (0.76→0.20/0.79→0.46),且 1278d3da 续接**确实触发**(echo=1),
  "echo=0=无损伤"的推理双重错误(中心替换发生在 echo 之前)。
- **取证定罪两个真 bug(已修,5a17471)**:
  ①根替换把 N 中心折叠成 1,多中心 COMPARE 对比注记丢失
  →补 cont_compare 契约注记("新层逐候选,比较后只交判别出的,
  链中实体是跳不是答案");
  ②普通直连步从**根**出发走了根自己的边——France 自己的 100 条
  CO2 边淹没每国一行的判别渲染(旧行为是从前沿/每绑定出发)
  →续接时普通步改用前沿成员当中心。
- **证据等价性核实**:修复后渲染与旧栈内容等价(co2 数值行
  95 vs 97 行都在;且数据侧 co2 g 节点非悬空——带
  measurement_unit.dated_metric_ton.number/date 属性,
  '12.8754' 等数值以字面量实体存在,与 deflator 的悬空形态不同)。
- **残余差距定位**:证据相同、行为不同——新栈模型选手打名单
  (触发变量警告+续接包装),answer 层 tie 契约没接住"全有边"
  的过溢(交 9 国全名单)。这是 AOP/V6 COUNT CONTRACT 线的活,
  不是检索层的。修复版 48×3 验证运行中(v38_relseq_fix2)。

### 2026-09-15 再补:用户 dump 审查揪出三处(311ffe0 已修)+一处开放
- **harness repeat 门死锁**(用户贴的 [7]→[10]):`_finalize` 的错误
  检测只认 JSON `'{"error"'`,而 SEQ `_json_result` 渲染平铺
  `error: ...` 文本——"绑定未声明"错误从不置位 `_last_tool_errored`,
  模型按提示声明检查点后重调同参 rr 被 REJECTED。已修(检测扩到
  平铺 error:/entity_error:)。
- **前沿计算错层**:续接普通步的前沿用了**更新后**层序的终层完成集
  (=co2 目标/日期值),应为**更新前**末层完成集(9 国)且排除锚
  自身(adjoins 边会回环到 France)。已修——每绑定一行渲染恢复
  (1278d3da s1 → 1.00 答 Belgium)。
- **声明链替换推导是错的**:声明-only 链死在保证通道裸枚举的
  id/名字节点边界(与 runtime 同款缝隙),渲染管线实证能渲染的是
  推导链。已改声明∪推导并集(声明优先排序)。
- **开放问题(下一轮取证入口)**:完成命令的链段
  (`adjoins ⭢ co2`)对 1278d3da 仍不渲染(并集后也不),而
  24353bbc 的链(`official_symbols ⭢ location_symbol`)能渲染——
  差异指向**末跳为值 CVT 的 2-hop 链**在 walk→license→collect
  某层被丢。这是值终端形态缝隙的又一处(pays/展开/链渲染一脉)。
  取证路径:对比两 case 的 _sg_execute walk 输出 pe["PG"].paths
  → _display_license_filter path_mode → collect_pattern_triples kept。
- fix3/fix4 迷你轮:1278d3da 0.47/0.27(修复面改善但翻转大),
  24353bbc 0.61/0.67 稳定。

### 2026-09-15 三补:渲染头+复合优先+链段丢失点收窄(53f0d95)
- **用户两点裁定**:①工具结果头措辞——起点为核心没错,但头要显示
  "序列根+本层作用于前沿"(已实现:`entities: France (sequence root;
  this layer applies to the frontier: ...)`);②**复合优先**——第二
  关系的检索基础=第一关系命中实体/模式路径终点,不与之前关系/路径
  重叠,最终产出**一条包含两个选定关系的模式路径**(与问题相关)。
- **后缀抑制方向反了(已修)**:render_v38 kept 的旧规则"链的后缀
  被片段渲染→丢链留片段"与设计相反——链=完成命令是主段,片段是
  其内部 hop 的冗余副本。已反转(片段是更长路径的连续子序列→丢)。
- 迷你轮:1278d3da **0.20→0.67(s1/s2=1.0 答 Belgium)**、
  24353bbc **0.83**。
- **链段丢失点最终收窄**:插桩证明 选择✓→walk✓(P1-P8 各 79-98
  路径)→render raw✗——丢失在 pe 合并之后、render raw 之前,即
  **_display_license_filter 的 path_mode 重建段**(:4543 起,
  "末跳是提交关系"的路径节点集重建逻辑疑似只重建 1-hop)。
  下轮入口:读 :4545-4640 的路径重建,修多跳路径透传。
- 插桩工具:SEQ_DEBUG_CHAIN=1(CHAIN-SEL/CHAIN-WALK 两级打印)。

### 2026-09-15 四补:链段丢失终局(用户跳数假说触发全面复现,b75645f)
- **用户两个判断均被证实**:①walk 从未失败——离线 probe 实证引擎
  对 (adjoins,co2) 层式执行产出 5 条见证路径
  (France→m.046csc5→UK→g,rels=(adjoins,adjoins,co2)),每步 2 跳
  预算内、CVT 占跳但层内自洽;PE(保证通道)穷举出 200 条 3-rel
  实例化;license 也放行。**②"模式路径丢失=直接失败"——丢失全在
  渲染前处理的两条守卫,均因 CVT 中间点改变路径形状**:
  - 守卫一(已修):render raw 的同关系往返守卫按"同关系+方向变化"
    杀路径——CVT 桥接(France←m.adjoins→Spain)天然同关系 r→f,
    全部被误判回环;修为"同关系+方向相反+回到已访问节点"。
  - 守卫二(已修):关系元组字面匹配——walked (r1,r1,r2) 对不上
    pattern 键 (r1,r2);修为 collapse 匹配(模式同一性=去重关系
    序列,CVT 穿越是展开细节),标签也用去重序列。
- **复合段实证渲染**(24353bbc):`▸ pattern official_symbols ⭢
  date_adopted (2 instantiations)` + 逐跳行(Kansas→CVT→日期)。
  1278d3da 的 co2 链段在部分采样出现;s0 仍首段 1-hop(顺序待调),
  分数仍受答案层 tie 拖累(0.2-1.0 振荡)。
- fix7 迷你轮:24353bbc 0.83、1278d3da 0.20(答案层)。
- 教训入档:**"walk 失败"类假设必须离线 probe 引擎实证**,两轮假设
  (id/名字边界、跳数超限)都被证伪,真凶是渲染守卫对 CVT 路径
  形状的误判。
- **fix8 全量首轮**(reports/v38_relseq_fix8_48x3.json):f1 0.6428/
  hit 75.7——距 relseq 均值 -2.8pp(±3pp 噪声带内但偏弱);家族赢面
  在(deflator **1.00** 历史首满、d9206043 0.83、6d6f2ca8 0.33),
  翻转 case 本轮不利(c7fffe30 0.33、1278d3da 0.13——mini 同代码
  曾 0.67/0.56,churn 主导)。r2/r3 复跑进行中出 fix8 栈三 run 均值
  正式判决。
- **fix8 栈三 run 均值终判**(fix8{,_r2,_r3}):**f1 0.6461/hit 75.0**
  (spread 极窄 0.6428-0.6480,一致非噪声)——**比修复前 relseq-auto
  均值(0.6709/78.0)净损 -2.5pp/-3.0pp**,与旧栈打平。家族赢面稳定
  (deflator 0.20→**0.80**、Saami 0.50→**0.89**、tvrage 0→0.44、
  24353bbc 0.64 部分恢复),但 1278d3da 0.29(答案层)与 027d777f
  0.11 回吐。**体量嫌疑实证**:平均子图结果 4450→5240 字符,
  平均段数 3.21→**6.06**——渲染面近乎翻倍(前沿普通步+链段+实际
  准入扩段三叠加),重蹈"压缩/扩面类改动测负"的历史规律。
  **下一步方向(待用户裁决)**:三修复的效果保留、体量回收——
  ①前沿普通步与链段的 hop2 行二选一(同内容不双渲染);②实际
  准入的深度/数量收紧;③对比注记精简。检索层语义已验证正确,
  这是纯呈现层瘦身活。
### 2026-09-15 五补:dump 审阅揪出段级属性披露缺失(655e00c 已修)
- **用户发现**:24353bbc 错误轨迹里 `m.04st86j`(Nebraska 的
  state-symbol CVT)只披露 Kind_of_symbol/symbol,没披露自带的
  date_adopted——"Nebraska--m.04st86j--1929 是完美路径,规则应匹配"。
- **根因**:sel_bare 排除(1171 标本规则"选中关系折进行不进属性")
  是**调用级**而非段级——date_adopted 是本调用选中关系,在**所有**
  段都被从 CVT 属性里排除,但它的行只在另一个段出现,归属关联断裂。
- **修法**:排除降为**段级**——键的关系属于本段模式跳(那里它以
  行渲染)才排除;跨段披露恢复(cvt_graph_all 为源)。
  **验证**:m.04st86j 三属性(date_adopted=1929/Kind/symbol)紧邻
  Nebraska 归属行渲染,完美路径一行组内可读。
- **但体积再涨**(5240→6137 chars/调用),两 case 分数 0.20/0.47
  仍卡答案层——模型看到 Nebraska-1929 关联仍不选它(V6 线的靶)。
  呈现层瘦身(去重+收紧)与 V6 是两个待办,分别针对体积和答案。
- **用户再裁定(56481cf):实际路径为准(ACTUAL-PATH GROUNDED)**——
  去重匹配虽救准入但制造"声明模式≠实际游走"不一致;实体+adjoins
  够不到 co2 而 +adjoins+adjoins 刚好命中,**带重复的实际元组就是
  真实模式**。实施:段准入=实际元组收尾完成提交关系(深度≤4),
  声明键降为意图匹配;标签用实际序列(CVT 进出保留);行本就
  逐实际跳渲染——三处一致。fix8 迷你:1278d3da 0.56(s0 0.67/
  s2 1.0)、24353bbc 0.72;co2 链段采样间可见性仍有波动,下一轮
  用 SEQ_DEBUG_CHAIN 对比"选中/walk/pe"三站在具体采样的差异;
  全量 48×3 确认轮待跑。

## 2026-09-15 凌晨:并集改"先并后排"(UNION-THEN-RANK)+池过滤审计
- **用户裁定:并集应先算所有实体的关系,再一次排名;不是每实体排
  完再拼**。实施 `SEQ_RR_UNION_RANK=1`(默认,seq_tools _rr_execute):
  池=全体请求实体的可达关系并集 → 一次标注 GTE 排名(top30,候选
  标签"实体|关系|?"——每关系取一个真实可达实体作头,保住
  Giants/Crazy Crab 要求的实体特异性,旧失败源于泛头非专头)。
  每实体 top-15 预切口消失,省 N-1 次 GTE 往返。生产函数四配置
  端到端(tmp/rr_union_rank_test.py):全关=缺席;STUB+任一排名修
  =菜单第 1 组 gdp_deflator_change;pytest 143 绿。
- **池过滤逐条审计(用户问:1/2/CVT-3 跳可达为什么还被复杂规则滤)**:
  可达性结构本身已符合意图(_expand CVT/g 透明,E→CVT→E2→E3 算
  2 命名跳)。叠在可达性上的三条准入:
  ①noisy(type.object.*/key/webpage)——真元数据噪声,保留;
  ②walkability(08-21 King)——不是质量预测,是"本引擎可达"的定义
  (池⟺可走一致性),撤掉重开"关系可达子图不可达"缝,保留;
  ③pays 渲染性(08-22 Norwood)——**质量预测当准入**,deflator 案
  证明预测会错(新渲染器下桩边=判别证据);已由 VALUE_STUB 修正,
  残余排除类=CVT 度数≥2 且零命名邻居(真无内容,暂保留)。
- **架构原则(用户表述,入档)**:池=结构可达性;语义=GTE 排名;
  质量/降级=选择-游走-显示时处理。准入过滤只准编码"结构不可能",
  不准编码"质量预测"。
- 验证序列:poolstub_gmerge 48×3(STUB+MERGE,UNION_RANK=0 状态)完成:
  **f1 0.6529/hit 75.7%——总分层带内**(基线三 run 均值 0.6513/77.6%,
  带 0.6390-0.6587/75.7-78.5)。**判别器家族显著正向**(逐 case vs
  perquotA 基线):deflator 0.20→**0.67**(轨迹实证:菜单出现
  gdp_deflator_change→模型走它→答"Andorra | Monaco"=恰为有边的
  两国,gold 在内;值不存在故无法再分,0.67 即数据最优)、tvrage
  0→0.33、eb615bab 0→0.33、f85999f1 0→0.33、d9206043 0.50→**1.00**;
  027d777f 0.33→0(翻转 case 采样噪声量级,列入观察)、6d6f2ca8 不变。
  UNION_RANK=1 一轮完成(reports/v38_unionrank_48x3.json):**f1 0.6558/
  hit 76.4%**——三态趋势 0.6513(基线均值)→0.6529(UR0)→0.6558(UR1),
  全部带内,f1 单调微升。UR0↔UR1 逐 case 有 16 个 >0.2 的移动
  (TEMP0.3×3采样的churn量级)——**翻转 case 的单轮逐 case 数字只在
  ±0.3-0.6 粒度可信**,机制级证据以离线复现+deflator 轨迹链为准。
  判决:三修复默认保持开;正式 UR 裁决若需要,各 3 轮均值。

## 2026-09-14 晚间:三 run 均值判决 + AOP(固定证据作答规则迭代)

### ⚠ 容器已重建,运维变更
- 系统解释器 /opt/conda py3.8 缺 aiohttp/pydantic2;**跑批/分析一律用
  `/root/miniconda3/envs/qwen35/bin/python`**(vLLM/GTE 服务即此环境)。
- vLLM :8000(Qwen3.5-9B)/ GTE :8003 均存活;batch 入口仍是
  `python -m kgqa.rl.seq_rollout` + env OUT(冒烟先 3 case)。

### 三 run 均值判决(用户方法;一对一重算,存档分不可信)
| 栈 | r1 | r2 | r3 | **均值** | hit |
|---|---|---|---|---|---|
| 单步(walkperf 配置,当前代码) | 0.6895 | 0.6745 | 0.6837 | **0.6826** | 80.6% |
| 多步(当前站立栈 perquotA 配置) | 0.6390 | 0.6587 | 0.6561 | **0.6513** | 77.6% |
- **单步真领先 ~3.1pp f1/3pp hit,分数带不重叠**(单步最低 0.6745 >
  多步最高 0.6587)——"历史最佳很微妙"落定:真实但集中在少数 case。
- 逐 case:单步赢 21 / 多步赢 16 / 平 11。单步头部优势 case =
  ab5818ba(Jesus Christ) / 1bf29d73(Europe) / ad5593ec / eb615bab
  ——全是作答层家族(平局/绑定),非检索;多步赢面 = da555ded
  (New Moon) / d9206043(Saami South)——老栈规则毁掉的两案。
- 历史记的 walkperf 0.707 实为 0.6895(存档分含 containment bug:
  1bf29d73 存档 1.0 → 重算 0.0,即评分切换导火索本尊)。
- run: reports/v38_wpcur_{r2,r3}_48x3.json + v38_pq_{r2,r3}_48x3.json
  + tmp/replicate_3run_casemeans.json(逐 case 三 run 均值)。

### 不稳定 case 分类(子智能体 A;主判据 perquotA 3 采样重算 f1)
- STABLE_GOOD 17 / UNSTABLE 23 / STABLE_BAD 8;**检索死区 0**
  (8 个全错 case 的 gold 也全可见)→ 失败全在作答层,佐证两分法。
- **AOP 子集 31 case**,证据固化 tmp/aop_evidence.json(31 case 取
  perquotA gold 可见采样;含 zh 重述)。索引 tmp/aop_index.txt,
  机器可读 tmp/aop_stability.json,可复现脚本 tmp/aop_analysis.py。
- **evidence_entities 字段弃用**(不可靠:38 gold 实例"在字段不在工具
  文本"= 渲染前子图超集;3 例反向漏报)——可见性判定一律文本法。
- 标本 91218362(NBA 全列):模型能列全年份但交裸值不交
  "XXXX NBA Finals" 节点名,三采样 0.11——表象/实体名家族。

### AOP 六变体判决(31 case × 3 采样 × 6,固定证据;子智能体 B)
| 变体 | f1 | 单gold(n=20) | 多gold(n=11) |
|---|---|---|---|
| **V3 条件式个数契约** | **.522** | **.447** | .658 |
| V4 =V3+判别值最近 | .505 | .444 | .614 |
| V0 六条基本规则(基线) | .493 | .392 | **.679** |
| V2 两步判读表 | .487 | .389 | .664 |
| V5 链式+类型守卫 | .486 | .367 | .702 |
| V1 answer-now(基线) | .446 | .342 | .635 |
- **无变体两面全赢**——单 gold 判别 × 多 gold 枚举的结构性张力在
  规则层复现(oracle-v2 教训再次坐实)。
- **因果结论**:①判读表单独无效(V2≈V0);**活性成分=条件式个数
  契约**(CASE A 全满足→交全部;CASE B 无全满足→交最强单个;
  V2→V3 = +3.5pp,空答 17→8);②判别值规则双刃,需 FILTER(保全部
  通过者)/DISCRIMINATOR(取单一极值)二分;③链式 FOCUS/穷举框架是
  单 gold 毒药(sg −8pp,合取题无中间 focus 就空答);④TYPE GUARD +
  "实体不裸值"安全(over/bare_value/chain_type 三家族清零)。
- **作答规则层不可修**(认知边界):under-枚举(检索完整性)、比较型
  择优、KG 词汇/粒度对齐(Parliamentary republic vs Democracy)。
- 家族计数(V0→V3→V5):定数过溢 7→4→1(治)、裸值 3→2→0(治)、
  None 13→8→15(半治,严判读反弹)、定数不足 15→15→17(治不住)。
- **V6 复合变体 = 唯一两族全赢的赢家**(主线程补跑):V3 骨架(判读表
  +条件个数契约)+ TYPE GUARD + "实体不裸值" + FILTER/DISCRIMINATOR
  二分 + 数值全 UNRESOLVED 不许空答,**去掉** V5 的 FOCUS/穷举链式框架。
  **f1 .543 / 单gold .453 / 多gold .708 / hit 64.5%**——四项全部超过
  V0(.493/.392/.679/58.1)与 V3;over 家族 7→3、None 13→6。
  规则原文在 tmp/aop_harness.py 的 `V6_RULES`(生产候选)。
- **决定性对照(同 31 不稳定 case)**:agent 在环作答(perquotA 自己的
  证据).441(单gold .362/多gold .585) < V0 裸答 .493 < **V6 一次性
  作答 .543**——两阶段协议(固化证据+单次 V6 作答)在自己证据上
  反超在环规则系统 +10.2pp。注意 full_fix agent 在这 31 case 上
  .582 仍高于 V6,但其证据不同(单步宽环境)+ 含世界知识幸运样本
  (Trn-1812 类),非同类比较。
- 家族残余:wrong_entity 27(比较型择优/KG 词汇粒度对齐——作答规则
  层不可修)、under 18(检索完整性问题)——这两族是下一步检索侧/
  两段式结构的靶子,不是提示语的靶子。
- 产物:tmp/aop_run_V{0..6}.json + tmp/aop_summary.json +
  harness tmp/aop_harness.py(V6 已注册,`--variants V6` 可复跑)。

### 2026-09-14 深夜:单 gold 低分机制解剖(读思考链+数据侧取证)
- **先纠正口径**:单 gold 并不弱。全 48 上 agent sg .645 > mg .620;
  AOP 子集 sg 低是选择偏差(17 个稳对 case 里 16 个是 sg 被排除)+
  计分结构(sg 53% 样本零分悬崖无部分分;mg 61% 样本靠部分分垫均值;
  V6 完全对率 sg 43% 反而 > mg 36%)。
- **思考链读判(7 标本 × 2 采样,tmp/aop_think_traces.json)**:模型认知
  全程正确——正确分解任务、显式扫描证据找值(runtime 标本原话
  "Scanning the text... No results")、正确判 UNRESOLVED、显式走完
  CASE B 梯子并指出全平局("any of the neighbors is equally valid"),
  然后按列表第一个(Italy)或连接度最高(Twilight)硬选。
  **错误选择是"值缺失+强制作答+全平局梯子"制造的,模型全程知情。**
  同题不同采样选不同错候选(Grant/Farragut、Cocoon/Gung Ho)——
  不稳定的选择过程,非固定名气偏见。
- **数据侧取证(case pkl 直查)**:判别关系全在 case KG 里
  (film.film.runtime / tv.tv_program.tvrage_id /
  location.statistical_region.gdp_deflator_change / date_of_death /
  initial_release_date)。**但 runtime/tvrage 全 case 各只有一条边,
  都挂在 gold 头上**(gold --runtime--> CVT m.0h100dp;
  gold --tvrage_id--> '20997' 字面值);deflator 76 条边但值全藏
  g.xxx 不透明节点后(R8)。
- **三条 surfacing 断裂**(值进不了证据的机制):
  ① frontier 完整性:agent 问"这电影的 runtime"时 entities=18 部电影
  **不含 gold**(tvrage 问甚至只带 Twilight 一个)——判别边只在 gold
  上,_reach2_relids(frontier) 池必然无此关系,菜单无法提供;
  ② GTE 排序:deflator 关系在池内(76 边),但 GTE 把 cpi/debt/health
  等兄弟排前面,菜单 top-K 切掉(模型自己扫描证据确认无 deflator);
  ③ 值不透明:即使边被走到,runtime 值在 CVT m.xxx 内、deflator 值在
  g.xxx 内,需 payload 展开才可见。
- **结论**:单 gold 判别失败=**判别值 surfacing 缺口**(检索侧),
  非作答规则问题——与 AOP "wrong_entity 作答层不可修"判决互证。
  修法家族=判别器定向探查:对全部候选(含 gold 候选)枚举值型关系
  (runtime/id/dates/statistical)+ CVT/g payload 展开,一次性把
  "候选×判别值"表带进证据。与 walkperf 审计候选 1(判别器门控发射)
  同向,现在有了数据级证据。作答侧无可修信息,别在那里找。
- 工具:tmp/aop_think_read.py(重跑抓 reasoning 的模板)。

### 2026-09-14 深夜二:三问取证(用户追问 CVT/GTE/frontier)
- **Q1 CVT 自动展开**:机制没坏,是没机会触发——展开条件是"被走到的
  路径端点(或倒数第二实体)是 CVT";runtime 的值在 gold 的**属性出边**
  后面(gold --runtime--> CVT m.0h100dp --值--> 分钟),这条边从未被
  走到(菜单没给),gold 又只是模式行里的命名叶(叶的出边 CVT 不在
  触发范围)。deflator 值藏 g.xxx 后同理(R8)。→ 叶属性值需要
  "判别器定向探查"显式带出,靠路径自然经过不会发生。
- **Q2 GTE 砍单(实测定罪,替 GTE 平反)**:GTE 本身无罪——deflator 在
  Monaco 池中排**第 1**(0.51 分断层);真凶是 `_rr_execute` 的并集
  构造:多实体调用按**实体顺序**拼 per-entity top-15,属性优先重排只
  取 `pool_rel_names[:15]`(=第一个实体的贡献)。生产路径模拟:
  9 国并集 41 条,deflator 在第 29 位(Monaco 是第 8 个实体)→ 显示前
  被切;**改成全局按分数 max-merge 后 deflator 回第 1**。
  附带数据事实:deflator 边只挂在部分国家(Monaco/Andorra),多数
  frontier 成员的池子里真没有——所以必须靠并集全局视角救。
- **Q3 frontier(用户关系序列约束提议)**:mid-loop retrieve_relations
  完全信任模型手打的实体表(runtime 问=18 部电影无 gold;tvrage 问=
  只有 Twilight)——模型抄的是**渲染出的名单**(每关系配额 3),不是
  模式实例化全集(gold 在实例化集里,证据中名字可见证明)。用户提议
  的"用关系序列约束 frontier/验证子图衔接"在代码里已有半套:
  ?var 单变量调用会触发 pattern-prefix continuation(_sg_prepare),
  模式实例化集包含 gold;缺的是 retrieve_relations 菜单询问不做
  实体表→实例化绑定集的自动扩宽。
- **修法三层(按侵入性排)**:①菜单并集改全局分数 max-merge
  (小改,模拟已证救回 deflator 类);②实体表扩宽:询问实体命中某
  模式位置时扩到完整实例化绑定集(救 tvrage/runtime 类——值边只在
  gold 上,frontier 必须含 gold);③判别器定向探查:问句含值判别
  需求时,系统侧对全部候选×值型边(日期/时长/id/统计+CVT/g 展开)
  出"候选×判别值"表(系统性收编 Q1+R8)。

### 2026-09-14 深夜三:runtime 原始轨迹核验(用户问:plan 问题还是机制问题)
- **判决:不是 plan 问题**。027d777f 三采样 plan 全部含显式 fact
  f3=(?film | what is the runtime of this film | ?runtime),
  answer=?longest_work——runtime 是显式约束成立,且拿到候选后
  每个采样都发了 runtime 检索。
- **同题两路对照(perquotA s0/s1 vs s2,同一 case)**:
  - s0/s1(答 Twilight,错):手打 18 部电影名单问 runtime(两次),
    名单不含 gold m.0gwrkz0——消息自述"event node bindings removed"
    (moot 关闭时 gold 的 id 形态绑定被当事件节点剥离);随后 [16]
    模式行明明列出全部 19 部(含 m.0gwrkz0),重问仍抄旧名单。
    per-entity 池永远没有 runtime 关系→菜单两次不提供→按协议
    正确关 ✗ unresolved→答题期强制单选。
  - **s2(答 The Nick and Jessica Variety Hour,对)**:用 ?movie
    **变量调用**(即用户关系序列语义)→retrieve_subgraph
    (film.film.runtime)→模式实例化仅 1 条:
    gold --runtime--> m.0h100dp→模型推理"只有一部有 runtime 证据"
    →答对。**?var+模式路径已被生产轨迹证明可行**——用户提议的
    序列约束 frontier 有正反两面人证。
- **新机制缺口(CVT 展开真实失败实例)**:s2 路径终点就是 CVT
  (m.0h100dp),但分钟值**未被展开渲染**(输出只有裸 id,无数字)
  ——?var pattern 路径的渲染没有走 multistep derive 的 CVT 终点
  展开。s2 靠"唯一有值即最长"绕过;若多候选都有值则致命。
  修法:pattern 行渲染时终点为 CVT/g 节点即展开 payload 属性
  (不限 multistep derive 路径)。
- 推论:判别器探查的最小可行形态已经存在——把"手打名单问值"
  引导/改写为"?var 问值"(或系统侧自动扩宽),再把 CVT 终点展开
  接上,两个标本家族(runtime/tvrage 类)即闭环。

### 2026-09-14 深夜六:【机制终局+已修】deflator 被砍真相 = 两道串联闸门
- **更正深夜二/五的归因**:并集切片不是唯一/第一死因。插桩定罪链:
  1. **闸门一(主凶):池的 pays 渲染性不变量**(tools.py `_reach2_relids`,
     2026-08-22 Norwood 规则)。deflator 全部 76 边都指向**悬空 g 节点**
     (度数=1,值链被数据截断),pays 判"渲染不出东西"→从**所有** GTE 池
     剔除→语义分再高也没进比赛(Monaco 直测排名本应 #1/0.51)。
     插桩反证:cpi_inflation pays 同样 False 却在池里——它从
     `_seq_pool_relids` 的 CVT 透明扩展**旁路**(无过滤)混入;deflator
     是 Monaco 直连边,旁路不覆盖。→ "兄弟都在唯独缺它"的诡异菜单。
  2. **闸门二:实体序并集 + [:15] 切片**(seq_tools `_rr_execute`)——
     池修复后 deflator 入并集第 17 位,仍被切。两闸串联,缺一不可。
- **修复(已提交,双门默认开,可独立回退)**:
  - `SEQ_POOL_VALUE_STUB=1`(tools.py):pays 承认"度数=1 的 CVT/g 终端
    =值桩"——桩边渲染为 `country --rel--> g.xxx`,**边存在性即判别
    证据**(deflator 2/9 邻国有边,runtime 1/19)。内容型 CVT(度数≥2)
    维持原判。
  - `SEQ_RR_GLOBAL_MERGE=1`(+`SEQ_RR_MERGE_CAP=80`)(seq_tools.py):
    属性优先重排输入从"实体序前 15"改为全并集(≤80)。
- **端到端验证(tmp/rr_slice_repro.py,真实函数三配置)**:
  双关=旧(全程缺席)/仅池(入 Monaco #1 但位 17 仍被切)/双开
  (**菜单最终 #1 = statistical_region.gdp_deflator_change**)。
  pytest 143 绿。48×3 实测运行中(reports/v38_poolstub_gmerge_48x3.json,
  对照 = 多步三 run 均值 0.6513/77.6%)。
- **普适性**:闸门一影响所有"值尾关系"(统计/时长/id 类判别器)的
  菜单可见性——不止 deflator 家族;闸门二影响所有多实体 rr 调用
  (变量扩展)里"非首位实体的高分关系"。

### 2026-09-14 深夜五:【更正】CVT"展开失效"系误诊 + 数据侧悬空值链真相
- **更正前两条(e7155b4/ab311a6)的错误前提**:"payload 在 ctx 数组
  一跳之遥,展开没接上"——实测不成立。
- **CVT 准入本来就是用户提议的语义**(实体判定+全图邻域源):
  cvt_graph 由**全量 case 数组**构建(seq_render_v38:217 遍历
  ctx.h/r/t,头为 CVT 即收 k=v),模式行准入判实体
  (seq_triples:101 for x in (h,t)),payload 从不依赖"机会性已走
  的边"。裸 id 渲染=悬空节点的诚实呈现。**准入机制无需修改。**
- **数据侧真相(三标本逐一对账)**:
  | 标本 | 值在数据? | 边在数据? | 断点 | 修法 |
  |---|---|---|---|---|
  | runtime 027d777f | 无(m.0h100dp 悬空,唯一边=入边) | 仅 gold 有 | 边没被走(s2 用 ?var 走到→靠"唯一有边"答对) | ② ?var 扩宽 |
  | tvrage c7fffe30 | 有('20997'字面量在边上) | 仅 gold 有 | 边没被走(问句只带 Twilight) | ② ?var 扩宽 |
  | deflator d25753d2 | 无('0.05'不在实体表,g 节点悬空) | 9 邻国中仅 Andorra+Monaco(各38边) | 关系被菜单并集切片砍掉 | ① max-merge |
- **新设计认识**:本数据集部分值判别器是**数据侧悬空**的——此时
  有效判别信号=**边存在性**(哪些候选带判别关系),模式实例化计数
  本身就是判别证据(runtime 1/19、deflator 2/9),s2 模型已实证
  会用("only one film has runtime evidence")。修法收敛为
  ①菜单 max-merge + ②?var/frontier 扩宽(让判别关系被走到);
  "值表"探查降级为可选(值存在时字面量随边渲染,如 tvrage)。
- CVT 终点展开"收集期无条件补拉"**不再需要**(全图源已实现,
  悬空节点补无可补)。

### 2026-09-14 深夜四:CVT 展开失效根因(代码级)+关系序列机制评估
  *(注:本节"payload 一跳之遥"前提已被深夜五更正,序列机制评估部分仍有效)*
- **CVT 根因**:"渲染完自动展开"不是实现事实。展开不是渲染层规则,
  而是 walk 证据构建层的**分支性**步骤(formatting.py:377
  `_expand_endpoint_cvt`,挂在 support-path/兄弟 CVT/K-path 分支,
  带 witness/scoring/_sel_ids 闸门;seq_tools:2104 注释自认
  "may miss some due to scoring/limits")。渲染层(seq_triples 的
  mid admission + seq_render 的 _mid_attr_pairs)只读已入库属性
  (cvt_graph/kept)——m.0h100dp 的属性边没被任何构建分支拉取,
  模式行就只剩裸 id。**修法方向**:模式实例化收集时,终点/倒数第
  二为 CVT/g 且库内无其属性 ⇒ 从 case 数组(ctx.h/r/t)无条件补拉
  一跳 payload——数据永远在一跳之遥,不需要 walk 分支碰巧跑到。
- **关系序列机制评估(用户提议,已对齐设计)**:
  - 现有半套:plan chains={anchor,fact_steps}(层级 DAG 已编码)/
    _derive_multistep_seq 关系元组枚举/ ?var pattern 接续/pattern_walk
    引擎。缺的是把"序列"提升为**请求与状态的一等单位**——绑定变成
    实例化集的派生读数(非权威状态),s0/s1 的名单≠实例化集分歧
    从构造上不可能。
  - 层级关切(用户 a):同级 fact(f1 影片/f2 电视)是并行序列,
    **绝不串接**(串接=类型域错配=关系崩溃);判别/属性类 fact 是
    当前层读数(PROBE),不是链延伸。层级来自 plan 的 chain DAG +
    关系域校验(r2 的 domain 必须匹配 r1 的 range 类型),不从调用
    顺序推断。
  - 多起点关切(用户 b):子图 k 的起点=其 DAG 父序列完成集的并集
    (junction 规则);父输出类型异构时(影片∪电视节目)保持按父
    分列序列、只在判别值表合并(tvrage 标本:film 域实体问
    tv.tv_program 域关系=类型错配的实例)。
  - 请求三态:SEQUENCE(start,seq,level)/PROBE(var,值关系)/
    FILTER(var,约束);frontier=实例化完成集(派生);菜单按序列
    位置的域约束池+全局 max-merge;CVT/g 终点展开为收集期无条件
    步骤。风险:plan 质量变成承重件(靠域校验+构造性顺延兜底);
    hub 上实例化成本(保证通道 200/模式预算已覆盖)。

## 2026-09-14 SESSION HANDOFF(压缩前完整状态,接管 2026-09-11 版)

### 当前分支与代码状态
- **分支**: walk-perf(领先 agent-toolcall ~50 commits;2026-09-12~13
  的全部提交见下方时间线,均已入 git)
- **测试**: 143 全绿(tests/,忽略两个缺数据文件的收集错)
- **评分口径已切换(重要)**:2026-09-13 起 = **实体一一对应**(规范化精确
  相等 + ≥8字符0.95模糊),包含匹配彻底移除(compute_match_stats /
  candidate_hit / strict_candidate_hit 三处,kgqa/core/utils.py)。
  **历史 run 的 recorded 数字与新口径不可直接比**——离线重算工具:
  逐条 compute_match_stats 重打。新口径下:topk5(站立) 77.8/0.645,
  perquotA(多步) 77.1/0.639,**差距只有 0.7pp/0.6pp**(旧口径 4.8pp
  大半是包含水分)。

### 多步管线终态(2026-09-13 收敛,全部用户裁决落地)
管线:模式枚举(任意跳深1..3,构造式=顺延内建)→ B段 GTE 语义选
(每提交关系 top-3 + 直连1跳免配额)→ 整链穷举实例化(无扇出上限)+
模式完整性保证 → 两层渲染(seq_triples 产三元组store / seq_rows 只渲染
行,跨模式去重,头/尾合并,capped 环境段)。
- 关键文件:kgqa/agent/seq_triples.py + seq_rows.py(两层);
  seq_render_v38._render_pattern_sections 已删,由两层取代;
  _derive_multistep_seq(任意深度);_sg_execute 语义选取+保证通道。
- 关键 env:SEQ_MULTISTEP=1(总开关)、SEQ_PAT_SEMANTIC=1(语义选,
  默认开)、SEQ_BRIDGE_TERMINAL=0(实验族)、WALK_POOL=3。
- 排序准则全线统一=命中(提交终结)→长度→语义→名字;**support/扇出
  从所有排序键删除**(用户:设计里从来没有);支持度路径上限已移除。
- 体量:p50=14 行/调用,p90=39,宽松段=0——数量问题不成立。

### 提示语状态(V2.1/V2.2/V2.2.1)
- **站立 = V21**(SEQ_PROMPT=V21);V2.2(seq_agents_v22.md)=用户/Codex
  稿+四修订;V2.2.1 = 有机融合(不完美立场开篇/值接近排序/平局=提交
  集合/✗empty前领域词改写/SLOT自检)。
- 判决:V21 一一口径 77.1/0.639 > V2.2 69.4 > V2.2.1 72.9(单轮带内);
  V2.2 的语义读题亮点实证(eb615bab 0→1.0),V21 的护栏句承重。
- **待做**:V2.2.1 vs V21 均值判决(各3轮,用户方法)未跑。

### 规则系统审判(2026-09-13 三线证据闭环,下一步主政)
1. **规则审计**(53失败样本全读):87% gold 在证据里,~33 模型推理点名过
   gold——规则系统是瓶颈。杀手排行:R4绑定冻结 10.25 / R2平局过溢 7.58 /
   R3 JOIN钉死 5.75 可回吸 f1;前3家族上限 +0.16(0.598→~0.76),超历史
   最佳差距。净正向规则(保留):SYSTEM JOIN整体/未消费门/STAGE GATE/§7.5。
2. **裸模型基线**(用户设计,同证据+六条基本规则):oracle 0.589/64.6% vs
   agent 0.598/72.9%——规则系统净贡献 +0.9pp f1;裸模型在被规则毁掉的
   6 case 全对(Village of Giants/New Moon/NBA全列/Jesus Christ/Barbados/
   Saami South);规则救的是纪律面(None回答/表象节点/类型对位)。
3. **oracle-v2**(answer-now 规则):0.579/66.7%——修单gold判别题、
   伤多gold列举题;平局全交/最强单交各管一半 case,无单一措辞全赢;
   None 回潮说明提交纪律必须有。
- **重构方向(待实施)**:保留纪律骨架(敢提交/表象排除/类型对位/实体名),
  砍状态钉死类(绑定冻结→证据驱动加宽;JOIN 只钉成员不钉拼写;平局在
  判别值已显示时按最近值裁)。约 1/4 override 质量在评分侧(strict×
  answer_type 字面/别名表象)。

### 思考预算
- 截断影响 25-31/48 case,受影响样本 -8-10pp(相关非因果);
  THINK_BUDGET 1000→2000:泄漏 46→8 样本,f1 +0.6pp(带内),墙钟+31%。
  **截断不是分数主驱动**;可取 1500 折中。

### 历史最佳参照
- walkperf(2026-09-07/08 full_fix#5 栈)一一口径 **80.6/0.707**;
  差距审计:集中在 ~6 case,11/12 最差损失 gold 可见=检索后失败;
  主导家族=未解析判别器下的答案集组成(与 R2/R4 同族)。
  当前栈赢面:宽模式环境让 gold 进视野(Trn-567 等)。

### 2026-09-12~13 完整时间线(全部已提交,细节见下方各节)
1. 09-12:license×BT0缝隙取证→路径级准入→CVT穿透修复→统一三元组→
   derive-always→链拆解回三元组→模式路径分段(pattern2 81.9 新高)→
   pattern3/4分解(压缩无罪)→语义选取(确定性平手+均值判决默认开)→
   support全面移除→两层渲染落地→子智能体审计+F1-F13修复→F5统一+
   路径完整性审计→保证通道(WALK_BREAK 27.3→0.6%)
2. 09-13:支持度上限移除→任意跳深+直连一等+顺延→按关系配额+echo缺失
   回退(f1 0.647)→一一对应评分→V2.2接入→回退归因→V2.2.1融合→
   walkperf差距审计→思考预算A/B→规则系统审计→裸模型oracle×2
- 关键提交:8af278e(评分修复)→b9a2162(一一对应+V2.2)→e25cd2b(V2.2.1)
  →9e869b5(walkperf审计)→2bc1d73(预算A/B)→9814329(规则审计)
  →1550474(裸模型)→c59e9d5(oracle-v2)

### 方法学教训(累积)
- 单轮 48×3 分差 <±3pp 是噪声;裁决顺序=确定性重渲染(rerender/
  path_integrity 审计)排除证据层差异 → 执行内 case 均值 → 跨执行均值
- 一一一口径下重算历史 run 再比较;审计工具先验证自身(解析器要处理
  头合并行/CVT反向槽位/节点对连通)
- 自写 rollout wrapper 必须 if __name__=="__main__" 守卫(WALK_POOL
  spawn worker 重导入 __main__ = 递归风暴)
- 压缩/收窄类改动几乎全部测负:凡砍证据面的"清理"先怀疑;语义/结构
  排序无罪,扇出计数不进任何排序键

### 待裁决(优先级排)
1. **规则系统重构实施**(方向已三线闭环,见上)——最大单项杠杆 +0.16
2. V2.2.1 vs V21 均值判决(各3轮)
3. 评分侧:answer_type 字面/别名表象的 override 质量(~1/4)
4. OSPD teacher pool / 分支合并 walk-perf→agent-toolcall

### 运维
- vLLM :8000(Qwen3.5-9B, TP2)/ GTE :8003(Qwen3-Embedding-0.6B)
- 标准env: `SPLIT=test_v4 N_CASES=48 N_SAMPLES=3 TEMP=0.3
  CASE_FILTER=tmp/v21_cohort.txt CASE_BATCH=1000 INFLOW_TARGET=500
  LLM_MODE=http SEQ_PROMPT=V21 WALK_POOL=3
  GTE_CLIENT_BATCH_WINDOW=0.08 GTE_CLIENT_BATCH_FIRST=0.02
  SEQ_RENDER_V38=1 SEQ_LICENSE_FILTER=1 SEQ_GHOST_EDGES=1
  SEQ_ZH_QUESTION=tmp/zh_questions_48.json SEQ_CVT_STYLE=inline
  SEQ_MULTISTEP=1 SEQ_BRIDGE_TERMINAL=0`(多步实验族)
- 跑批 wrapper:tmp/run_realign5_instr.py(OUT 可外覆;已守卫)
- 审计工具箱(tmp/,可复跑):path_integrity_audit(断链归因到层)/
  rerender_config_audit(配置确定性对比)/volume_eval(体量)/
  reach_audit(命中分类)/empty_derive_eval/semantic_pattern_eval/
  baseline_oracle_test{,2}(裸模型)/dump via scripts/dump_teacher_audit.py
- dumps: tmp/teacher_audit_dump_{perquotA,v22,v221,tb2k,walkperf-era...}
  + 各轮 index 文件

## 2026-09-11 SESSION HANDOFF(旧版,部分被上文取代)

### 当前分支与代码状态
- **分支**: walk-perf(领先 agent-toolcall ~40 commits)
- **站立配置 = topk5**: f1 0.6802 / hit 82.6% / 墙钟 316s / sg p90 12.7K
  - 全部等价速度五刀在产(证据构建 memo×5, 共 -92% hub walks)
  - walk_extra cap 6 / GTE 批窗口 0.08 / CVT 键 top-K 5 / 族键值 cap 40
  - CVT 命中键置顶(支柱 4b)
  - RPE 单步松终止 + 桥终止(SEQ_BRIDGE_TERMINAL=1)
  - 141 套件全绿
- **速度弧线收官**: walk-perf 378s → 质量弧线 ~1200s → 五刀+环境恢复 →
  **~570s 总墙 / 316s mean**(LLM 成为主要相位,GPU 饱和)

### 游走设计对齐实验弧线(八次,全部负收益/门控关)
| # | 配置 | f1 | mismatch | 教训 |
|---|---|---|---|---|
| 1 | 免桥 direct-first | -4.4pp | — | 桥穿透喂证据 |
| 2 | tier-1 锚定降级 | -3.2pp | — | 环境行承重 |
| 3 | 纯标注 bridge label | hit -3.4 | — | 连标签损注意力 |
| 4 | 遍历-only 桥 | — | 39 | 中段跳不能自给 |
| 5 | 提交终止准入 | hit -5.5 | — | 松终止证据系统性生产 |
| 6 | 引擎多步(单关系/跳) | 0.668 | 48 | 独木桥 |
| 7 | 并行跳(实体 BFS) | 计算爆 | — | 实体级=指数 |
| 8 | 模式层枚举(纯关系) | 0.650 | 72 | **判决被污染**:license×BT0 缝隙滤空证据,非到达不足(2026-09-11 取证) |
- **统一结论**: RPE 单步松终止是当前唯一测得可行的到达模型
- **用户设计(正确但引擎承载不了)**: specs/walk_realignment_spec.md
  四支柱 = 路径纪律/模式路径/一致性/CVT双设计; 引擎全有但 agent 未用

### Missouri River 标本(最深集成诊断)
- 模式枚举**(r1, family) 对**正确: 145 条三元组离线验证通过
- 集成 bug 1(已修): center 级 direct 检查被共提交的直连关系掩蔽
  → per-RELATION 检查(commit 141313b)
- 集成 bug 2(**已定性,见 2026-09-11 realign5 取证**):"引擎多步覆盖遗漏"实为
  license filter × SEQ_BRIDGE_TERMINAL=0 准入缝隙——到达成功、证据被滤空;
  realign4 全量 mm=72 判决受污染需重审
- **设计方向 A(未试)**: 模式做引导但用 RPE 单步执行——rel_idxs 限定
  为 {r1, family},保留 RPE 灵活性

### 游走对齐实验代码留存(门控关)
- `SEQ_MULTISTEP=1`: 模式层枚举+多步提交(可开)
- `SEQ_BRIDGE_TERMINAL=0`: 桥退役(可开)
- `SEQ_DIRECT_FIRST=1`: 中心直连免桥(可开)
- `SEQ_TIER_ANCHOR=1`: 路径一致性 tier-1(可开)
- `SEQ_BRIDGE_LABEL=1`: 桥段标注(可开)
- `SEQ_PATTERN_WALK=1`: 集合态模式游走(可开)

### 2026-09-10~11 完整实验时间线(按时间序)
1. 五刀速度优化(全部字节等价, 共 -92%): 静态memo→case级→家族去重→显示串memo
2. 游走成本模型验证: RPE=全环境游走(宽度无关), LLM 21.6s/轮正常
3. walk_extra 近因 cap(+0.8pp f1, -23% slots)
4. CVT 尾压缩 A/B(inline 胜)+族键 cap 40(hit +1.3pp)
5. CVT 键 top-K 3→5(hit +2.7pp, GTE 排判别键入列)
6. 桥标注(负,hit -3.4pp)
7. 遍历-only 桥(最差, mm 39)
8. 遍历-only 恢复+门控
9. 提交终止准入(负, hit -5.5pp)
10. 模式层枚举三轮(5case→全量→per-relation)
11. 游走设计对齐 spec 写入
12. Missouri River 深度集成诊断

### 失败分解(修正后)
- speed5 58 失败 = 8 三元组层 + 50 编排/模型层
- 三元组层 8 例: 5 环境压缩 cap(已修 cap 40) + 3 模型选择
- 环境修复已入产: 族键 cap 40 + CVT top-K 5

### 方法学教训(重要)
- pickle-sha 对含 set/dict 的结构过敏(插入序置换≠内容变化);
  正确验收 = 内容相等 + 同态字节稳定
- 审计工具自身先验证(presence 检查两个 bug: fact_id 前缀漏检 +
  normalize vs raw 假阴性)
- bisect 恢复用 `git checkout HEAD -- file` 会抹掉未提交工作区
- 跨进程 sha 对比固定 PYTHONHASHSEED
- 5case 快验可能偏采样(简单模式),全量才见真覆盖

### 待裁决(优先级排)
1. **游走完全体**: 方向 A(模式引导+RPE 执行)或 walk-algo 分支
   (bitmap 搜索+RPE 证据枚举合并)
2. **LLM 端上下文瘦身**: note/回显的重复提示面(墙钟 316→更低)
3. **OSPD teacher pool**: 原 任务
4. **分支合并**: walk-perf → agent-toolcall

### 运维
- vLLM :8000(Qwen3.5-9B, TP2)
- GTE :8003(Qwen3-Embedding-0.6B, GPU1 与 vLLM 共卡)
- 标准env: `SPLIT=test_v4 N_CASES=48 N_SAMPLES=3 TEMP=0.3
  CASE_FILTER=tmp/v21_cohort.txt CASE_BATCH=1000 INFLOW_TARGET=500
  LLM_MODE=http SEQ_PROMPT=V21 WALK_POOL=3
  GTE_CLIENT_BATCH_WINDOW=0.08 GTE_CLIENT_BATCH_FIRST=0.02
  SEQ_RENDER_V38=1 SEQ_LICENSE_FILTER=1 SEQ_GHOST_EDGES=1
  SEQ_ZH_QUESTION=tmp/zh_questions_48.json SEQ_CVT_STYLE=inline`
- dumps: tmp/teacher_audit_dump_{speed5,valcap40,topk5,realign4}.txt
  + mmfix 对照:tmp/teacher_audit_dump_{mmfix,topk5}.txt(2026-09-12 修后多步 vs 站立)
  + 导航索引:tmp/mmfix_vs_topk5_index.txt(逐 case delta,hit/goldvis 标注;回归 12 例
    几乎全部 vis 3/3——gold 可见仍答错,细读轨迹用)

### 2026-09-11 realign5 取证完结:MM 空结果是 license filter × SEQ_BRIDGE_TERMINAL=0 的缝隙,非数据/非引擎
- **用户问题**:realign5 的 6 次 MM 调用(UK--time_zones、ETZ--locations_in_this_time_zone)
  "walk reached nothing"——数据问题还是游走引擎问题?
- **判决:两者都不是,是证据准入层(显示 license filter)**。完整证据链:
  1. 数据在:2576 图 1331 实体里 `Americas --time_zones--> Eastern Time Zone`、
     `Falkland Islands --containedby--> South America/Americas`(GT Americas 就在 sg1 证据里)、
     UK→时区 2-hop 模式 `UK --administrative_children--> 属地 --time_zones--> tz` 三条真实存在。
  2. 推导在:per-relation 检查正确触发,`_derive_multistep_seq` 毫秒级给出 3/2 个 (r1,family) 模式,
     与线上错误回显的 attr_expansion 逐字节一致。
  3. 游走在:inline 与协调器(修好守卫后)两条路径对同 step 分别产出 137-222 / 89-49 条三元组。
  4. **缝隙**:realign 实验族 wrapper 带 `SEQ_BRIDGE_TERMINAL=0`(支柱 1 配置)——桥被计算并回显
     但**不进 rel_names/rel_idxs**。`_display_license_filter`(seq_tools:3896)的 subs 只含提交名,
     lic 集合只能沿提交关系/CVT 端点扩张;MM 模式的 hop-1 边(administrative_children)不在 subs
     → 中间节点永不入 lic → 终点边(X--time_zones-->tz)节点测试也挂 → **kept_triples 全灭**
     → "reached nothing",且误诊为 RELATION_MISMATCH。
  5. **闭环复现**:`SEQ_MULTISTEP=1 + SEQ_BRIDGE_TERMINAL=0` 离线 dispatch 重放,sg1✓/sg2 精确
     复现线上逐字错误(含 relations 回显只有 2 个提交名)/sg4 同错/sg3✓——四调用成败形态与线上一致。
     反事实:同 5case 重跑(BT 默认 1)sg2 `MM={841:3} empty=0` 证据正常(rel_idxs 回显 9 个名含桥)。
- **指纹**(以后判断历史 run 是否 BT0):错误回显 `relations:` 只有提交名(无桥)=BT0;
  有桥名 = BT1。realign5_s5.log 的 walk 相位正常(collect 16s≈realign4 的 16.5s),lane 无故障。
- **波及面**:**realign4 全量 48×3 的 mm=72"覆盖不足"判决被此缝隙污染**——到达其实成功,
  是准入层杀死;八次实验弧线中 realign3/4/5(BT0 族)的负结论需重审。站立配置(topk5,
  BT1+MM 关)不受影响。
- 修复方向(未实施,待裁决):MM 触发时把推导模式的 hop-1 关系并入 license 的 subs/lic
  扩张(引擎推导边≠模型漂移),或 MM pe 走 CVT 同款透明通道。
- **方法学陷阱(重要)**:自写 rollout wrapper 必须 `if __name__=="__main__"` 守卫——
  WALK_POOL spawn worker 会重导入 __main__,无守卫 = worker 递归重跑整个 rollout
  (spawn 风暴:wait=3000s+、假"复现"、输出翻倍)。本次两轮"复现"均此伪影,第三次守卫后消失。
- 留档:tmp/replay_tz_2576.py(数据审计+推导重放)、tmp/replay_dispatch_2576{,_bt0}.py
  (dispatch 全真重放 BT1/BT0 对照)、tmp/realign5_cases.txt(重建的 5case 队列)、
  tmp/realign5_instr3.json(反事实重跑)。

### 2026-09-13 oracle-v2(用户修订规则:答题现在/证据不完美/禁 CVT/实体名)
- **规则修订**:去掉平局全交/最强单交条款,改为——证据不完美很正常,
  基于当前证据**现在**作答;判别全条件自行最佳判断;禁 m.xxx/g.xxx;
  只用实体名。
- **判决**:oracle-v2 f1 0.579/hit 66.7%(v1 0.589/64.6%,agent 0.598/72.9%)
  ——v2 与 v1 同带,"答题现在"换掉平局条款后 hit 微升 f1 微降(更强单选
  =更多错单)。
- **逐 case 信号**:v2 修好 772d0e75(0→0.75)、44734cf0(0→0.50)、
  f85999f1(0→1.0)、b543f688(0.67→1.0);但弄丢 91218362(NBA 全列→
  单交 0.11)、24832cdc(1.0→0)、24353bbc(None 回潮)、991df028。
  **"答题现在"帮单 gold 判别题,伤多 gold 列举题**——平局/单交条款各管
  一半 case,合起来才是 0.6 级别的裸能力;没有单一措辞两面全赢。
- **与 agent 对比不变**:oracle-v2 赢 12/输 15/平 21——净差仍是纪律面
  (None 回潮/类型错位在 v2 规则下无人兜底)。
- 留档:tmp/baseline_oracle_test2.py + tmp/oracle_baseline2.json。

### 2026-09-13 裸模型基线测试(用户设计:剥规则,同证据直答)
- **设计**:48 case,证据=v221 run 每案第一条真实轨迹的全部工具结果,规则=
  六条基本作答规则(证据权威/命名实体精确复制/m.xxx 非答案/缺失≠否定/
  平局全交/最强单交),剥掉 plan/checkpoint/门/梯子/ANSWER_ANALYSIS 全部
  规则系统。严格一一一口径。thinking 2000。
- **判决**:
  | | f1 | hit |
  |---|---|---|
  | 裸模型(六条基本规则) | 0.589 | 64.6% |
  | 完整规则系统(agent) | 0.598 | 72.9% |
  **规则系统净贡献只有 +0.9pp f1(+8.3pp hit)**;oracle 赢 11 case /
  输 17 / 平 20。模型的裸能力≈整个规则系统。
- **oracle 大胜 case(规则拖累最重,与规则审计 R4/R5 完全吻合)**:
  eb59f791(Village of the Giants,裸 1.0 vs 规则 0.33)、da555ded
  (New Moon,裸 1.0 vs 0.27)、91218362(NBA Finals 全列)、ab5818ba
  (Jesus Christ)、7b0ad6b5(Barbados)、d9206043(Saami South)。
  **裸模型在 6 个被规则毁掉的 case 上全对**——绑定冻结/平局过溢的直接
  人证。
- **oracle 大败 case(规则的救场)**:ad5593ec(裸答 None——规则逼出的
  敢提交在起效)、1bf29d73(裸答时区名,规则版答对了 Europe)、
  772d0e75(空答)、cd80a639(答表象节点)、1c0686c5(Freemasonry)。
  规则系统救的是**纪律**面:类型对位/不答表象节点/敢提交。
- **结论**:规则系统的正确形态=保留纪律骨架(类型/表象/敢提交),砍掉
  状态钉死类(绑定冻结/JOIN 拼写钉死/平局无裁全交)——与规则审计的
  R4/R2/R3 修复方向完全一致,且现在有了双向人证。
- 留档:tmp/baseline_oracle_test.py + tmp/oracle_baseline.json。

### 2026-09-13 规则系统 vs 模型知识整体审计(子智能体,53 失败样本全读)
- **用户假设证实并精化**:**87%(46/53)失败样本的 gold 实体就在检索证据里**,
  ~33 个模型自己的推理点名过 gold——最终答案却走了别处,每个都有具体规则
  决策卡在知识与答案之间。**模型和检索不是瓶颈,规则系统是。**
- **规则杀手排行(可回吸 f1)**:
  | 规则 | 主致/触及 | 可回吸 |
  |---|---|---|
  | R4 检查点绑定冻结/收窄(闭合合同复合体) | 11/14 | **10.25** |
  | R2 平局政策过溢(§9 提交平局集合) | 10/21 | 7.58(实际~3-4) |
  | R9 名气/世界知识选(§8/§9 存在但未被执行) | 7/7 | ~1.5(执法后是集合非单gold) |
  | R3 SYSTEM JOIN 钉死(别名拼写/表象排除) | 6/7 | 5.75 |
  | R5 计划链+Mode2 中间绑定强提交 | 4/6 | 4.0 |
  | R6 offpool 拒绝环 | 4/4 | 4.0 |
  | R1 answer-type 合同(字面/组织/神格框架) | 3/7 | 3.0 |
  前 3 家族(R4+R2+R3)上限 ≈ +0.16 mean f1(0.598→~0.76),**单独超过
  历史最佳的差距**(walkperf 0.707)。
- **净正向规则(保留)**:SYSTEM JOIN 整体(26 成功 vs 7 失败;537_a52d
  Abandon 3×1.0 靠它)、未消费实体门+JOIN PATHS(救过 567_df97)、
  STAGE GATE(79 成功,无一例把对的改错)、§7.5 剥离。
- **标本级证据**:537_80c3"这些不在 Hunnam 作品列表里"——同时屏幕上是
  `Green Street --netflix_id--> 70167115`;567_11fd"The Journey:1959-08"
  读到了又说"不在导演片单";626 答了 join 钉死的"Lemurian windows"
  (walkperf 同知识 3×1.0 答 Kansas);2152 join 钉现名拼写,strict 评分
  判错(walkperf 用 gold 拼写 2×1.0)。
- **精化**:约 1/4 的 override 质量是**评分侧**而非 agent 侧(strict 实体
  × answer_type 字面/别名表象);7 样本模型自己名气破平(规则对但未执法)。
  截断仅 2/53 决定性——与预算 A/B 结论一致。
- 修法方向(机制级,非 case 特判):①绑定**证据驱动加宽**(新子图显示同事实
  新候选时允许检查点扩绑,保留反幻觉冻结其余);②平局在判别值已显示但藏于
  g.xxx/未取属性时按最近值裁;③JOIN 不钉拼写/表象,只钉成员;④R9 需要更强
  的执法措辞位置。

### 2026-09-13 思考预算 A/B(用户:截断疑虑)+截断实测
- **截断实测**:泄漏事件(思考被 vLLM 强制截断)影响 25-31/48 case;
  受影响样本 f1 比干净样本低 **8-10pp**(v221 0.545 vs 0.623;walkperf
  0.631 vs 0.730)——老问题,非新栈引入。
- **A/B(THINK_BUDGET 1000→2000,同栈)**:
  | | hit | f1 | 泄漏样本 | 墙钟 |
  |---|---|---|---|---|
  | tb1000(v221) | 72.9 | 0.598 | 46/144 | 348s |
  | tb2000 | 72.2 | 0.604 | **8/144** | 456s(+31%) |
  **预算翻倍把截断从 46 样本压到 8,f1 +0.6pp、hit -0.7pp(带内)——
  截断不是分数的主要驱动**(受影响样本低分是相关非因果:难 case 思考
  更长更易撞预算)。墙钟 +31%。单轮不可分,按用户方法需各 3 轮均值才可
  裁决;若追质量可取 1500 折中。
- run: reports/v38_v221_tb2k_48x3.json + dump _tb2k。

### 2026-09-13 walkperf(历史最佳 0.8)vs 当前栈差距审计(子智能体)
- **口径统一后真差距**:walkperf 一一口径 **80.6/0.707** vs perquotA 77.1/0.639
  (差 3.5pp/0.068)。差距**高度集中**:12 个最差损失=+6.33 分,当前栈赢的
  6 个=-3.15,23/48 完全相同——不是弥散性退化。
- **12 个最差损失里 11 个 gold 在当前栈自己的工具结果里**(10 个 3/3 可见)
  ——**几乎全是检索后失败,不是检索失败**。
- **主导失败家族(~7/12):未解析判别器下的答案集组成**。数值/比较/过滤需求
  (runtime/army/netflix_id/CO2/成立年份)图内无解时,"平局提交全部"过溢
  (4-8 实体)或错单选(Twilight)。precision 0.731→0.683 是主因。
  次家族:①绑定/渲染误读(gold 在但被按关系配额降级到 environment 尾注
  ——Trn-372 的 religion.deities;CVT 内联属性标注消失);②别名节点选择
  (d8d82010:模型规范化到现名,gold 是带 founded 边的历史别名)。
- **当前栈的真实赢面**:宽模式环境让 gold 进视野(Trn-567 Village of the
  Giants——walkperf 只绑导演片单;Test-1840 typed 实体;Test-1171 JEJ 3/3)。
- **三个机制级改进候选(排序)**:
  1. **判别器门控发射**:判别需求全 UNRESOLVED 时不上交全集——发射限界
     top-k(按支持数)或强制一次定向判别探查;
  2. **事件节点逃生+属性自动揭示**:§7.5 剥离绑定时自动展开已渲染事件的
     属性关系入下一候选表;硬拒绝 m./g. id 作 center(当前只是警告,
     Trn-25 仍重中心了 4 次);
  3. **答案期重绑+别名政策**:ANSWER_ANALYSIS 允许从渲染边重绑(Trn-493:
  ?location 绑了国家而 Europe 就在同屏边上);later_known_as 链上优先带
     判别边的别名节点;单条含金边从 environment 升回模式段。
- (Trn-1812 公平性注:walkperf 2/3 样本零渲染,靠世界知识 checkpoint 拿分
  ——新栈的严格接地故意堵死了这条路,部分"领先"是运气。)

### 2026-09-13 V2.2.1 有机融合(设计子智能体产出+实施)首测
- **方法(用户规则)**:基于 V2.2 骨架;不针对特定 case/关系;只优化作答逻辑;
  护栏句有机融进 V2.2 语域而非粘贴;新认识论立场显式写入("数据不完美,
  作答不等完美数据")。四处替换:§8(不完美立场开篇+Mode2 值接近排序+
  UNRESOLVED>CONTRADICTED+空答案保留给零相关证据+平局集合)、§9(平局=
  证据判决,提交平局集合;排除需显示矛盾)、§5.2 step6(✗empty 前必做
  一次领域词改写重查)、§3.2(SLOT SELF-CHECK:问题语法 > 计划,类型
  不覆盖语法)。+43 行。143 全绿。
- **48×3 判决(v221)**:hit 72.9/f1 0.598(V22 69.4/0.592,+3.5pp hit;
  V21 77.1/0.639 仍差 4.2pp)。7 个追踪 case:
  | case | V21 | V22 | V2.2.1 |
  |---|---|---|---|
  | da555ded | 1.00 | 0.13 | 0.27 |
  | bdf429c6 | 0.89 | 0.33 | 0.33 |
  | 44734cf0 | 0.69 | 0.17 | 0.33 |
  | 24832cdc | 1.00 | 0.67 | **1.00 复原** |
  | 9925c777 | 0.80 | 0.52 | **0.87 超V21** |
  | eb615bab | 0.00 | 0.56 | **1.00 双超** |
  | f85999f1 | 0.00 | 0.33 | 0.33 保持 |
  值接近比较(24832cdc)与 SLOT 自检(9925c777)两条护栏起效;eb615bab
  语义读题保持且首次满分。da555ded/bdf429c6 修复有限(单选偏置与弱关系
  集在 9B 上可能需要措辞更强的位置,或属于方差)。
- run: reports/v38_v221_48x3.json + dump _v221。OBS: 单轮方差,若继续
  迭代建议按用户均值方法(各 3 轮)再裁决 V2.2.1 vs V21。

### 2026-09-13 V2.2 回退归因(子智能体轨迹对比,5 回退 case 全样本)
- **五个回退的失败层分布**:da555ded=答案决策(金在证据里,单选偏置选了
  "the original film");bdf429c6=关系选择(sub-question 措辞泛化,
  servicemembers 没进候选,一次就 ✗empty)+绑事件节点;44734cf0=绑定污染
  (Red Hook 混入)+None 回答×5;24832cdc=绑定污染(角色名混入)后 Mode2
  排序重"有日期"轻"值匹配"(1997>1992-01 最近值);9925c777=答案变量
  计划成中间 ?person,被引擎 answer-type 合同覆盖。
- **5 个根因(排序)**:
  RC1 单选偏置——V22"Return the top-ranked candidate"+从严并列取代了
     V21 的"平局提交平局集合+禁名气选择"(三句承重文本被删);
  RC2 None 回答——V21 的"NONE 只保留给零相关证据"被删;
  RC3 弱关系集无修复梯——V21 §7 的改写重查/回退一级被删(sub-question
     泛化措辞永不到位,一次 ✗empty);
  RC4 实体优先计划削弱——V22 计划漏列 Stephanie Meyer(引擎未消费实体
     门没机会救);answer_type 灵活性条款被删;
  RC5 Mode2 排序重证据存在轻值接近——"比较判别器按显示值执行比较"被删。
- **两改善 case 证明 V22 亮点**:语义关系原则+按字面读题(eb615bab
  "talked about"→演讲主题→Democracy,V21 三样本全灭);Mode2 具体性排序
  敢于提交(f85999f1 The Journey)。
- **修复方向**:措辞级融合而非结构重写——V2.2 骨架 + 回填 V21 五段承重
  句(平局集合/禁名气/NONE 保留/修复梯/值接近比较),保留 V2.2 的语义
  选择与两层决策。

### 2026-09-13 实体一一对应评分(用户裁决)+V2.2 提示语首测
- **裁决**:gold 与预测是图实体,须**一一对应**——'Western Europe' 与 'Europe'
  是不同节点(语料中各自独立出现),token 包含也算错。三个匹配器
  (compute_match_stats/candidate_hit/strict_candidate_hit)全部收紧为
  **规范化精确相等 + ≥8 字符 0.95 模糊(容错)**,包含彻底移除。
  143 全绿。离线重算(一一对应口径):perquotA 77.1/0.639,topk5 77.8/0.645
  ——**多步配置与站立的差距缩到 0.7pp/0.6pp**(旧口径 4.8pp 主要是包含水分)。
- **V2.2 提示语**(用户/Codex 稿+四修订:plan 闭合纪律/answer_type 绑定自检/
  CVT 非答案条款/并列从严)已写入 kgqa/agent/SEQ_AGENTS_V22.md,
  SEQ_PROMPT=V22 接入。
- **V22 首测 48×3**:hit 69.4/f1 0.592 vs V21(perquotA 一一口径 77.1/0.639,
  **-7.7pp/-4.7pp——超方差带,首测负**)。V21 vs V22 逐 case:worse 6 / better 2;
  最大回退 da555ded(1.0→0.13)/bdf429c6/44734cf0;改善 eb615bab(0→0.56)/
  f85999f1(0→0.33)。sg 调用 376→330(检索更少),reached-nothing=0。
  **待读轨迹定位**:V2.2 的结构重排(两层决策/语义覆盖)对 9B 模型可能
  措辞面变化过大——需对比 da555ded 的 V21/V22 轨迹差异后迭代措辞。
- 评分变更后所有历史 run 的 recorded 数字不可与一一一口径直接比较。
- run: reports/v38_v22_48x3.json + dump _v22 + 索引 tmp/v22_index.txt。

### 2026-09-13 按关系配额+echo缺失回退(用户两问题)+终版判决
- **用户问题**:①比利时 1 个提交关系渲染 6 个多跳段(配额没对齐);
  ②Charlie Hunnam 的第二关系 starring_roles 完全没出现。
- **根因②(深)**:echo 只给"有族匹配或有桥"的名字回显——全名提交且无桥的
  starring_roles 没有 echo 条目 → prepare 的 _matched 和 execute 的
  _direct_fam 都只从 echo 构建 → 第二关系从模式族和直连步里整个消失。
  **修复**:两处都加 echo 缺失回退(按名匹配 ctx.rels)。
- **修复①**:配额改按 (中心,提交终结关系)——每个提交关系:直连 1 跳免配额
  恒选 + 最多 3 个非单跳模式;渲染层只显示被选模式+直连段(宽松进环境段,
  上次过滤负是因配额口径不一致,现已对齐);删除遗留 [:6] 硬帽。
- **标本**:Charlie 现在 `▸ tv_actor.starring_roles (7)` 直连段打头 +
  portrayed 的 top-3;比利时 = 直连 + 3 个多跳段 ✓ 对齐。
- **48×3(perquotA)**:hit 77.8 / f1 **0.647**(anydepth 0.612,+3.5pp,
  OVER-EMIT 24→17);墙钟 381s(3 跳成本)。路径审计:FULL 35.4%/
  RENDER 0.6%(新低)/WALK 10.6%/模型末跳 53.4%。
- 143 全绿。run: reports/v38_perquotA_48x3.json + dump _perquotA。

### 2026-09-13 任意跳深模式枚举+直连一等+顺延(用户三裁决)
- **裁决**:①模式路径 1/2/3 跳都枚举——单跳(正反两向)优先展示,多跳按
  (跳数,语义) 排序,不锁定某跳;②直连是一等模式(最短),推导永不真空;
  ③顺延=枚举从可达性构造,每个模式天生有实例,选取沿排名补足配额。
- **实施**:_derive_multistep_seq 重写为任意深度(1..3)元组键;选取排序
  (跳数,GTE,名字),1 跳免配额恒选;打包/保证通道适配任意深度。
- **48×3(anydepth)**:hit 77.8/f1 0.612(语义带 hit 78.7±1.4 带内,f1 略低);
  **墙钟 376s(↑43%,3 跳枚举+实例化成本)**;WRONG 32;OVER-EMIT 24(↑)。
  路径审计:FULL 31.7%/WALK 11.8%(3 跳需求部分覆盖)/RENDER 3.1%。
- 143 全绿。run: reports/v38_anydepth_48x3.json + dump _anydepth。

### 2026-09-13 支持度上限移除+体量评估(用户:固定模式路径无分支,实例化=整链满足)
- **链一致性语义确认**:保证通道的实例化即用户设计——center --r1→ X --r2→ Y
  两跳同时成立才保留(整链满足,非逐跳并集);渲染行内的边全部来自完整链。
- **支持度上限移除**:formatting._select_support_paths max_paths 24→无上限
  (固定模式路径无分支,扇出上限不得裁模式级完整链)。
- **体量评估判决(tmp/volume_eval.py)**:73 个模式渲染调用,行/调用
  **p50=14 p90=39 max=71 mean=19**;段=直连 47% 行 + 提交终结多跳 53% 行,
  **宽松(非提交终结)段=0**——此前爆炸源(57 段洪泛/链式行/环境刷屏)已全部
  消除。**"数量多了"不成立:语义 top-3 + 整链实例化 + 压缩后体量小而稳。**
- 143 全绿。

### 2026-09-13 链路完整性弧线:审计修正→保证通道→统一路由(门控)
- **审计三轮修正**:头合并行解析(两侧拆)、任一同长最短路、节点对连通
  (CVT 反向槽位 actor.film/performance.actor 同一关系)。基准=节点对连通的
  任一最短路全渲染。
- **保证通道(已上,原则性)**:选中模式从模式索引穷举实例(每模式预算 200,
  不经 RPE beam/分支/support 上限)补进 pe——用户原则"实体层不得截断模式层"
  的直接实现。**WALK_BREAK 44(27.3%)→1(0.6%)**。
- **统一路由(门控 SEQ_UNICHAIN,默认关)**:MM 下空推导调用也走两层渲染器
  (弃 legacy 压缩)。FULL 55→62/64,但 48×3(unichain) hit 74.3/f1 0.624
  vs 语义带 78.7±1.4/65.1±2.0——legacy 的 CVT 尾压缩是测得良好的上下文。
  **完整性 vs 质量的权衡待裁决**。
- **终版审计(161 gold-path)**:FULL 64(39.8%)/RENDER 10(6.2%)/WALK 1(0.6%)/
  模型末跳 86(53.4%)。**环境侧链路闭环;唯一大头=模型关系选择**。
- 143 全绿。审计脚本 tmp/path_integrity_audit.py(可复跑)。

### 2026-09-12 F5 统一+路径完整性审计(断链归因到层)
- **F5**:遗留渲染器行序去掉扇出键(multi/heads_of 改 (rel,name));排序准则全线
  统一=命中→长度→语义(名字)。143 全绿。
- **路径完整性审计**(tmp/path_integrity_audit.py):以 gold 最短路为基准,逐跳检查
  "边是否在工具结果里",断点归因——WALK_BREAK(原始游走输出里就没有)vs
  RENDER_BREAK(游走有、渲染丢)。判决(161 gold-path,真实调用确定性重放):
  | 分类 | n | % |
  |---|---|---|
  | 模型末跳未提交 | 82 | 50.9% |
  | **WALK_BREAK** | 44 | **27.3%** |
  | 全路径渲染 | 28 | 17.4% |
  | **RENDER_BREAK** | 7 | **4.3%** |
  **渲染层基本不断链(4.3%);断链主因=游走枚举缺口(27.3%,如 Brad Stevens→
  championships 的第二跳边不在原始 pe)+模型关系选择(50.9%)。**
- 标本:cd0c724a(film.starring CVT 边渲染丢)、ec2c1dfa(education.student CVT)
  为渲染侧两例;91218362(champion 第二跳)为游走侧家族。

### 2026-09-12 两层渲染落地(用户三裁决)+F4 修复
- **裁决**:①排序=命中(提交终结)→长度→语义,support 从不在设计(pattern_walk.py
  同步修复);②**核心原则:重建后的三元组=子图核心内容**——全图为基础,模式游走的
  逻辑路径重建为三元组,去重/合并评估都在三元组上,除 plan 解析外一切基于实际
  游走变量;③渲染分两层,互不干扰,行层只接受三元组。
- **实施**:kgqa/agent/seq_triples.py(三元组层:collect_pattern_triples——kept/edges
  /穿透边/直连合并→模式分组+排序+跨模式去重+per-CVT 准入→store);
  kgqa/agent/seq_rows.py(行层:render_rows——只吃 store,头/尾合并、前缀压缩、
  属性值列、capped 环境段、固定 note)。render_v38_ack 多步分支改为
  render_rows(collect_pattern_triples(...));_render_pattern_sections 删除。
- **行为差(有意)**:跨模式三元组去重(基线中同边在多段重复渲染,现全局一次);
  属性值列形态保持。原子三元组级对齐验证无内容丢失;5 标本渲染正常;143 全绿。
- 遗留渲染器(站立配置)未动。F5(遗留行序扇出)仍待裁决。

### 2026-09-12 渲染/游走层重建+子智能体审计+阻断项修复
- **CVT 逻辑跳定案(用户)**:实例化/展示期规则——路径最后或倒数第二实体为 CVT
  时延展一跳;模式路径本身固定,不存在验证;模式跳数只数命名实体跳。
- **重建(1f104f0)**:_render_pattern_sections 提取为独立渲染器(合并全部裁定:
  模式分段/逐跳三元组/per-CVT 准入/实例期 CVT 延展/capped 环境段),与遗留
  关系段渲染器物理分离;行为保持(5 标本字节一致+143 全绿)。
- **子智能体审计(16 findings)**:3 阻断+若干死码。**已修**:
  F1 _ms_map 阶段间 env 翻转崩溃(init 外提);F2 环境段双渲染(合并行的
  字符串重解析永不匹配→发期边记账,标本环境段 6 重复行→0);F3 全名提交无
  echo 时 _sub_sh 为空(补 rel_names 回退);F13 中心锚定认任一端点;
  F6 死参数;F7/F8 推导死码(support 计数残留清除);F14 语义选取按中心去重。
- **待用户裁决**:F4 pattern_walk.py(门后实验)仍用 support 选模式;F5 遗留
  渲染器行序用扇出(只影响顺序不影响成员)。
- 验证:5 标本渲染正常(环境段去重生效)、143 全绿。
- 审计全文在子智能体报告(已折叠入本条)。

### 2026-09-12 support 移除(用户:设计里从来没有)+当前命中审计
- **移除**:support(扇出计数)从全部排序键删除——推导枚举序(改名字典序,
  语义选取在 B 段做)、渲染段序(提交终结→中心根→跳数→名字)。设计=长度优先、
  语义次之,仅此两条。
- **当前命中审计**(tmp/reach_audit.py,pattern4 真实调用确定性重放,178 gold×调用):
  模型末跳未提交 48.9% / 直连命中 27.0% / 需3跳 12.4% / 两跳可推导+提交 7.3%
  (**渲染可见 13/13=100%**,候选遗漏 0)/ 图不可达 4.5%。
  **结论:交对关系时可推导路径全命中;瓶颈在模型关系选择(48.9%)与 3 跳枚举。**
- 143 全绿。

### 2026-09-12 均值判决(用户:单次波动大,看平均):语义选取默认开
- **方法**:两配置各 3 轮 48×3 同 GPU 串行(reports/v38_avg_s{0,1}_r{1..3}.json),
  汇总均值±半程。
- **判决**:
  | 配置 | n | hit | f1 |
  |---|---|---|---|
  | support top3 | 3 | 77.3±3.1% | 64.6±2.7 |
  | **GTE 语义 top3** | 3 | **78.7±1.4%** | **65.1±2.0** |
  池化均值语义更高且方差减半;pattern4 的 81.2 是 support 方差带上沿。
- **单位修正(用户:看单次执行内每 case 3 采样平均,非跨执行 9 指标)**:
  执行内 case均f1——support 0.644/0.620/0.675,semantic 0.630/0.670/0.652,
  **区间互覆,不可分**。默认开语义的依据=设计符合+确定性重渲染不劣(65 vs 66)
  +池化均值名义领先(不显著)。
- **SEQ_PAT_SEMANTIC 默认已翻 1(开)**;=0 可回 support。143 全绿。
- 方法论沉淀:单轮 48×3 分差 <±3pp 不可裁决,重复取均值;确定性重渲染
  (rerender_config_audit)先排除证据层差异,再跑均值排除采样差异。

### 2026-09-12 语义选取确定性重渲染判决(用户方法论:不重跑,重放调用)+门控bug修复
- **用户方法论**:rollout 有方差,同态重放真实调用(轨迹里的 center+rels)双配置
  重渲染,直接对比核心路径去留——零 LLM、零方差。
- **门控 bug(已修)**:SEQ_PAT_SEMANTIC 门把 _ms_map 初始化关进门内,门关时所有
  MM 调用 UnboundLocalError 崩(只污染了审计,未污染任何 run——semantic2 在门加
  之前跑的)。修复=外门 MULTISTEP、内门 SEMANTIC、打包块在外门内。
- **确定性判决(132 调用,0 错误)**:gold 可见 support 65(49.2%) vs semantic
  **66(50.0%)**——语义裁剪**不砍核心路径**(各丢 1-2 例互相抵消)。specifics:
  support 空段丢 cpi_inflation_rate(d25753d2)直连;semantic 在 Petruccelli
  crew-job 换了段组合。
- **结论**:①裁剪必须(用户:否则上下文爆炸);②语义裁剪安全(确定性同态);
  ③rollout 分差(81.2 vs 78.5/79.2)=方差+下游组成,非核心路径去留。
  SEQ_PAT_SEMANTIC 默认值待用户裁决(support=单轮最高分;semantic=设计符合+
  确定性平手)。
- 审计脚本:tmp/rerender_config_audit.py(可复跑);tmp/semantic_pattern_eval.py。

### 2026-09-12 pattern3/4 分解判决:压缩无罪,渲染层收窄有罪;f1 首超站立
- **用户质疑成立**:pattern3(73.6%)的 -8.3pp 不是头合并的锅。分解:
  | run | 模式选取 | 头合并 | hit | f1 |
  |---|---|---|---|---|
  | pattern2 | 全量(≤6+2env,排序) | 无 | 81.9 | 0.664 |
  | pattern3 | 只中心根+每关系top3 | 有 | 73.6 | 0.611 |
  | **pattern4** | pattern2 全量 | **有** | 81.2 | **0.701** |
- **头合并(前缀压缩)**:hit 带内(-0.7),**f1 +3.7pp=0.701,首超站立 topk5 的 0.680**。
- **渲染层 top-3/关系 + 只中心根 = 负**:推导层已每中心 top-3(设计所在层),
  渲染层再砍一刀切掉的是 RPE 宽松游走贡献的模式(桥抑制家族同型承重证据)。
  **层级分工定案:模式数量控制在推导层(derive topk),渲染层只排序不裁剪。**
- 残留:pattern3 曾出现的"模式段内混入他根实体"由排序的 rooted-优先缓解
  (不删除);环境模式 cap 2 保留。
- 143 全绿。run: reports/v38_pattern4_48x3.json + dump _pattern4。

### 2026-09-12 模式路径分段展示(用户终裁:段=模式,非提交关系;多步族新高 81.9%)
- **裁决**:三元组重建基于模式路径——关系是模式路径上的关系,实体须同时满足前一跳
  与后一跳;中间跳三元组在自己模式的段内(不再孤儿);CVT 渲染。不再按提交关系分段。
- **实施**(render_v38 pattern 分支,treq.multistep 时激活):kept 路径按关系序列分组,
  每组一段 `▸ pattern r1 ⭢ r2 (n instantiations)`,逐跳三元组(头侧合并尾列 ≤40);
  提交关系的 CVT 穿透边(p.triples 通道,不在 kept)并入对应一跳模式组;
  CVT mid 属性行随段渲染(4a/4b);非模式边进环境段(≤24)。
- **首轮负**(pattern 71.5%):环境垃圾 1 跳模式(written_work.subjects 71 实例)挤占
  6 段配额。**调序后**(pattern2):提交终结优先→中心锚定优先→跳数→支持度,环境
  模式限 2 段。
- **48×3 判决(pattern2,多步族新高)**:hit **118/144=81.9%**(triple 79.2,距站立
  topk5 82.6% 仅 0.7pp)/ f1 0.664(差 1.6pp)。arc: unitri 77.1 → triple 79.2 →
  **pattern2 81.9**。
- 标本:Eleanor `▸ pattern education.student` 带头 + `--institution--> The New School`;
  Belgium 直连模式→2 跳模式(language→region→time_zones)全跳可见。
- 143 全绿。run: reports/v38_pattern2_48x3.json + dump _pattern2(注:上一条 mihop
  run 已作废被覆盖,链拆解条目的 dump _triple 仍是 triple 轮)。

### 2026-09-12 链拆解回三元组(用户终裁:统一三元组,链不渲染)
- **裁决**:链式行整体移除——多跳见证的**每条边**作为独立三元组进入常规行管线,
  由既有的头/尾合并自然去重压缩(Delacroix 标本:5 条 Böcklin 链自然汇成一行
  `Arnold Böcklin --influenced--> Davies | Munch | Ernst | …`;`Delacroix→Böcklin`
  并入直连行)。压缩即标准三元组行合并,非链内合并(链内合并已测负,门控关)。
- Belgium 标本:`Europe --location.time_zones--> GMT | Moscow | Azores | WE`
  三元组行在提交段可见;143 全绿。
- **48×3 判决(triple,多步族最佳)**:hit **114/144=79.2%**(deriveall 75.0,
  +4.2pp)/ f1 **0.668**(+5.3pp)/ WRONG 36→**30**——链式行形态本身在损质量,
  拆解回三元组即恢复。距站立 topk5(82.6%/0.680)差 3.4pp/1.2pp,接近合拢。
  arc: unitri 77.1/0.611 → chaincomp 70.8/0.583(负,门控关) → **triple 79.2/0.668**。
- run: reports/v38_triple_48x3.json + dump tmp/teacher_audit_dump_triple.txt。

### 2026-09-12 链压缩 A/B:负收益,门控关(SEQ_CHAIN_COMPRESS)
- **用户裁决**:同前缀链(同中间节点+同来路)末跳终点应合并值列(Delacroix 标本
  5 条 Böcklin 链)。实施为按 (段,跳数,前缀) 分组合并终点。
- **48×3 判决(负)**:hit 75.0→**70.8**/f1 0.615→0.583/WRONG 36→**42**——合并后的
  终点值列被模型读成所问关系的**直接答案名单**(2 跳见证失去路径语义)。
  与桥抑制家族同一教训:压缩呈现改变答案分布。已门控默认关,恢复逐链展示
  (deriveall 行为);SEQ_CHAIN_COMPRESS=1 可开。
- 143 全绿。run: reports/v38_chaincomp_48x3.json + dump _chaincomp。

### 2026-09-12 derive-always(用户 Belgium/GMT 标本裁决:top-K 模式路径,非 top-1)
- **用户问题**:Belgium+time_zones 第一轮只有 1 跳直连(topk 变 top1),2 跳
  `Belgium --containedby--> Europe --time_zones--> GMT` 为何没命中?
- **两层根因**:①"有直连就跳过推导"的旧规则把 top-K 模式评估折叠成 top-1;
  ②兜底 RPE 的 beam 在 containedby 的 40+ 行政区扇出里丢了 3 个正向尾巴
  (Europe/Eurasia/WE)。另发现:同关系往返对(time_zones→time_zones,support 17)
  挤占 top-3。
- **修复**(均 MM 门内):①推导无条件运行(fam=matched 关系,BT1 下桥不进推导域);
  ②有直连的中心 pattern 步之外**保留直连步**(1 跳+2 跳并列,长度优先);
  ③多尾终点行也转链式(修 Europe→4 时区合并行吞中间跳);④同终点边取最短链;
  ⑤推导排除 r1==r2 往返对。
- **线上验证**:同 case 第一轮即渲染 `Belgium --official_language--> German
  --region--> Europe --time_zones--> Greenwich Mean Time Zone`+直连行+GMT 名册。
  **残留引擎缝隙(精确定位)**:组合路径 [Belgium,Europe,GMT][containedby,
  time_zones] 引擎有生成,但在证据裁决层被每模式 support≤24 上限的行政区碎片
  挤掉——渲染的链来自直连步 RPE 的 3 跳;2 跳链需证据层短路径优先(下项)。
- **48×3**(deriveall):hit 75.0/unitri 77.1(带内 -2.1)/f1 0.615(+0.004)/
  **OVER-EMIT 26→16(答多问题修复)**/WRONG 33→36。GMT case 0/3=模型答 Belgium
  (回显中心,答案层;证据含 Europe+GMT 完整路径)。
- 143 测试全绿。run: reports/v38_deriveall_48x3.json +
  dump tmp/teacher_audit_dump_deriveall.txt。

### 2026-09-12 统一三元组 CVT 展示(用户批准的 spec 对齐实施)
- **实施**(seq_render_v38):
  1. **cvt_disp 去括号**:CVT 属性不再内联 `[k=v;...]`,裸 mid 进行;
  2. **per-CVT 键准入**(支柱 4b 对齐):`_mid_attr_pairs` 准入域=该 CVT 自己的键,
     case 级 GTE 排名只作相对序;cap 仅对 >5 键的 CVT(3%)生效;never-blank 回退删除;
  3. **属性行同段发射**(`_emit_attr_rows`):`m.xxx --key--> value` 三元组行跟在
     浮出该 mid 的模式行同段;同 (key,value) 跨 mid 合并头侧(4c);每段 cap 20;
     选中段注册覆盖环境段注册(person.education 抢注 bug 修复);
  4. **压缩去重**:≥4 CVT 尾折叠摘要已含属性的 mid 标记 done,不再发属性行
     (用户裁决:压缩后括号信息不重复展示);
  5. **_candidate_provenance 整体删除**(用户多轮要求):有效信息走三元组,
     无边实体移除;答案合法性池/walk_extra 账本不变。
- **标本**:Eleanor `m.0k0m3wk --institution--> The New School` 同段可见;
  Ron-Howard awards_won 段 `(16 event records · award: Academy Award...)` 压缩摘要
  +链式行,无重复展开;143 测试全绿(provenance 测试随行为删除,Debussy 夹具误删已复原)。
- **48×3 判决**(unitri):hit **77.1%**(多步族新高,72.9→76.4→77.1)/ f1 0.611
  (cvtfix 0.644;**OVER-EMIT 16→26**——属性三元组暴露更多候选名,模型列举过多,
  组成分降)。WRONG 33 新低。**命中-组成权衡待用户轨迹裁决**。
- run: reports/v38_unitri_48x3.json + dump tmp/teacher_audit_dump_unitri.txt +
  索引 tmp/unitri_index.txt(topk5/cvtfix/unitri 三方)。

### 2026-09-12 CVT 括号消失取证+永不空括号回退(用户审计 1392 标本)
- **现象**:Eleanor/New-School case,`m.0k0m3wk --education.student--> Eleanor` 渲染为
  裸 mid,无 `[institution=The New School]` 括号——模型被迫绑定事件节点(触发 §7.5
  警告),答案键不可见。**非链式渲染改动的回归**——topk5 dump(一切改动前)已裸。
- **机制**:cvt_disp 的属性键 top-K 闸(GTE 序 top-5 ∪ 提交组件)。本 case 143 键,
  `institution` 排 GTE **#7** → 唯一携带答案的属性对被滤空 → 括号空 → 返回裸 mid。
  第二跳判别键同理:CVT 键名 `number`(3565) ≠ GTE #1 的
  `number_of_postgraduates`(字符串不同)→ 同样滤空。top-K 闸(09-08 引入,净 +2.7pp
  hit,防的是键洪泛)顺带把"答案键排在 6+ 位/键名字面不匹配"的 case 括号清零,
  违反行契约("事件节点不是答案,属性才是世界")。
- **修复**(seq_render_v38 cvt_disp):**永不空括号回退**——过滤后 pair 为空且
  原始 pair 非空时,按 GTE 序回退显示该 CVT 自身前 3 键。闸只防洪泛,不清空。
- **标本验证**:`m.03j_v30 [institution=Allenswood Academy] | m.0k0m3wk
  [institution=The New School] --education.student--> Eleanor Roosevelt`——答案在
  首次检索即可见;144 测试全绿。
- **48×3 判决**:hit 110/144=**76.4%** / f1 **0.644**(chainrender 72.9%/0.598,
  +3.5pp/+4.6pp;topk5 82.6%/0.680)。WRONG 型 39→34。亮点:bb7d9156(located ID)
  0.00→1.00、772d0e75 +0.38、1c0686c5(Liszt) 0→0.33——判别键(number=3565 类)
  可见性恢复的直接收益。残留回归:bc8c9e1a/9deb3d9d/1bf29d73 仍 -0.67(hit 3|3|3→
  1/3,gold 可见仍答错,答案层)。
- run: reports/v38_cvtfix_48x3.json + dump tmp/teacher_audit_dump_cvtfix.txt +
  索引 tmp/cvtfix_index.txt。
- **设计对齐裁决(用户,当日)**:top-K 本义是 **per-CVT** 属性排序(该 CVT 自己
  的键,通常 2-5 个)——不存在 case 级 143 键词表排序;"96 键/case"是跨 CVT
  聚合假象(实测 97% CVT ≤5 键,74% ≤2)。never-blank 回退=临时止血(afead4c,
  +3.5pp hit),per-CVT 重实现后应移除。spec 已更新(walk_realignment_spec
  支柱 4 + 对齐裁决节),重实现方向待用户批准。

### 2026-09-12 链式完整路径渲染(用户人工审计三裁决,已实施)
- **用户审计**(Ron-Howard 标本 567_df97,mmfix dump)三问题→三裁决:
  1. **桥跳不可见**:多跳见证只渲染末跳边,头实体凭空出现
     (`Glenn Gordon Caron --director.film--> Clean and Sober` 与中心无关联)——
     证据原子应是**完整路径**,桥/中间跳必须渲染;
  2. **排序**:带桥路径/模式路径按**长度优先**排序(短者先);
  3. **无边实体**:候选列表里只有实体名没有边的行没有价值,删。
- **实施**(seq_render_v38):kept 路径→chains 映射(≤3 跳,每关系 ≤8 条,中心起锚,
  末跳边同时是中心 1 跳边的保留合并平行);singleton 终点行替换为链式文本
  `Ron Howard --producer.film--> Clean and Sober <--director.film-- Glenn Gordon Caron`;
  段序=(段内最小跳数, 模型提交序[attr_expansion 键序,桥排后], 字典序),段内行按跳数;
  `_candidate_provenance` 删无边类(答案合法性池不受影响,显示层)。
- **验证**:标本重放——直连 28 部在前,链式行桥跳全显,提交段先于桥段,裸实体行消失;
  144 测试全绿(provenance 测试按新行为更新);2576 标本无回归。
- **48×3 重测**(chainrender,同 mmfix 配置+新渲染):hit 72.9% / f1 0.598
  (mmfix 0.593——噪声带内持平);证据层漏失略降(render 4.3→3.4%,walk 1.2→0.7%);
  wrong_relation 51.2→55.2%(带内)。**质量结论待人工轨迹审计**——渲染结构修复
  的价值需读轨迹判断,非单轮指标。
- 留档:tmp/teacher_audit_dump_chainrender.txt + tmp/chainrender_index.txt
  (三方对照 topk5/mmfix/chainrender);标本脚本 tmp/replay_rh.py。

---
### 2026-09-12 mmfix 全量 48×3(修后多步配置)+分层审计:证据层合格,缺口在答案层
- **run**:reports/v38_mmfix_48x3.json(SEQ_MULTISTEP=1+BT0+路径准入+CVT穿透修复);
  墙钟 243s/case×3(站立 316s);**mismatch 调用 32(realign4)→2**——缝隙修复确证。
- **分层审计**(tmp/evidence_layer_audit.py,可换 RUN_JSON 重跑):330 gold×sample,
  按"实际提交配对 BFS 判右关系→gold 是否出现在该调用返回文本→是否在
  evidence_entities→答案对错"分层:
  | 配置 | 右关系gold可见 | 渲染丢失 | 游走丢失 | wrong_relation | hit |
  |---|---|---|---|---|---|
  | topk5 站立 | 96.7% | 2.0% | 1.3% | 54.8% | 82.6% |
  | realign4 修前 | 96.2% | 3.3% | 0.5% | 44.8% | 76.4% |
  | mmfix 修后 | 94.4% | 4.3% | 1.2% | 51.2% | 72.9% |
- **gold 可见率(任意工具结果含 gold)**:topk5 95.1% / realign4 88.9% / **mmfix 93.8%**
  ——修复后证据层几乎追平站立;mismatch 洪水消失。
- **判决:缺口已移到答案层**。mmfix 可见→答对转化率 77.7% vs topk5 86.9%(-9pp)。
  标本 1bf29d73(GMT/Belgium,修后 -1.0):证据完整含 Europe,模型答 Belgium(回显
  中心)——纯答案层。"渲染丢失"两标本(e2c80dcd Sharon Mae ×3、7b0ad6b5 Barbados)
  复核为分析器配对伪影/模型时序错误(Caribbean 未经 sg1 直接当 center),非引擎漏。
- **含义**:多步纪律把 gold 送到了眼前(与宽松体制几乎同水平),但该渲染形态下
  模型最终选择变差——多步证据样式(无桥终止段/候选名单更长)对答案选择的代价,
  属模型/编排层课题,不是游走或过滤层。站立=topk5 仍是质量最优配置。
- per-case delta(mmfix−topk5):最差 1bf29d73 -1.0 / fe70cad9 -0.64 / da555ded -0.47;
  最好 eb59f791 +0.67 / 772d0e75 +0.38(Village of the Giants 族修复)。

---
### 2026-09-12 静态 gold 路径审计(用户裁决:不重跑,直接查路径)+推导 CVT 穿透修复
- **方法**:48 cohort case 逐个:建图→定位 gold 实体→BFS(无向)最短路(起点=轨迹里
  实际提交过的 center+锚点)→用 realign4 48×3 轨迹的**实际 (center,关系) 配对**判定:
  末跳关系是否被提交、前缀是否在 2 跳推导范围内(直接调 `_derive_multistep_seq` 验证)。
  秒级,无 LLM/GPU。
- **修复前**:direct 60 / rank_miss 17 / deriv2_none 3 / terminal_miss 30 / **needs_3hop 0**。
- **根因 2(推导 CVT 穿透 bug,已修)**:穿透只查**同关系前向** `ix.fwd[r].get(cvt)`——
  performance CVT 的 actor 边在反向表、film 边在前向表,同关系前向=空 → performance 类
  模式 support 算 0、从不进枚举(17 rank_miss+3 none 的统一根因)。原代码还有隐性雷:
  `for r3, n3 in <int列表>` 双元解包,CVT 恰有同关系前向边时 TypeError 被 except 静默吞
  (整个推导失效)。修复=CVT 一跳邻居贡献其**全部命名邻居**(任意关系,双向,单层,
  memo 化;与 `_seq_pool_relids` 的 CVT 透明跳同语义)。
- **修复后**:direct 60(54.5%)/ **deriv2_ok 20(18.2%)**/ rank_miss 0 / none 0 /
  terminal_miss 30(27.3%)。**引擎侧可达(给定实际提交)=80/110=72.7%**;
  残余 30 全是模型侧(从未提交正确末跳关系——关系选择家族,引擎不可修)。
- **判决链终版**:①"引擎多步到达不足 mm=48-76"=license 缝隙(已修);②"2 跳刚性
  需 3 跳枚举"=**被反驳**(needs_3hop=0);③排序缺口=support 低估计(CVT 穿透修复
  连带解决,rank_miss 17→0);④残余失败=模型关系选择 27.3%(与失败分解的模型/
  编排层家族一致)。
- 回归:144 测试全绿;站立配置字节级不变;BT0+MM 标本输出不变(3672/1865)。
- 留档:tmp/goldpath_audit.py(审计脚本,可重跑)、tmp/check_ledge.py(穿透 bug 标本)。

### 2026-09-12 路径级准入已实施(用户裁决:准入单位=路径,非边)
- **裁决**:过滤器是旧架构(实体游走→事后归纳)的产物;模式时代先跑完模式再过滤;
  模型提交的是**末尾关系**,评估对象是**路径**——"最后一跳是提交关系"即合法,
  不逐跳对照。过滤在游走完成后进行,看最终路径。
- **实施**(`_display_license_filter` path_mode,treq.multistep 非空时激活):
  末跳 ∈ 提交关系(全名/typed)或端点 CVT → 路径合法,路径节点整体入 lic;
  渲染路径列表用同一末跳判据(修掉了首版"节点在 lic 即渲染"漏过坏路径的缺口,
  单测抓出)。普通调用走旧规则。
- **验证三层**:①单测 3 条(末跳准入/旧规则钉住/render 形态头剥离),套件 144 全绿;
  ②离线:BT0+MM 标本 sg2 报错→3672 字符证据(候选含 Eastern Time Zone)、
  sg4→1865;站立配置(MM=0+BT1)四调用输出 diff 为空(字节级不变);
  ③线上 5case(MM=1+BT0):sg2 类调用全 empty=0,FLUSH-EMPTY 1/全程(真不可达)。
- **fix5c 5case 质量注记**:mean_f1 0.356 不可与 realign5 0.622 直接比——重建队列
  slot3 是难题(Tolkien/GMT,GT King Edward's)而非原 Belgium(易题)。Falkland
  证据流出后模型答 North America|South America vs GT Americas=模型层终端粒度
  失败,非环境。**realign 判决重审需全量 48×3(待用户裁决,~25min GPU)**。
- 遗留:多步枚举仍 2 跳;排序 support 优先(GTE 二次排序未接,C 段无 IO)。

---
(以下为历史记录,按时间倒序)
> working memory across sessions — how to run things, where artifacts live,
> what's in progress, and traps we've hit. The chat log inside the container
> gets wiped on provider reset; **this file is git-tracked and will not**.
>
> Update it whenever: a run finishes, a command/prefix changes, a trap is
> discovered, or a milestone is hit. Keep entries dated and concise.
> Design rationale lives in `specs/agent_redesign_spec.md` (§0) — this file is
> about *operations*, not *why*.

---

## How to run the pipeline (current, 2026-07-06)

### Services required
The agent needs two services up before any run:

| service | port | what | model |
|---|---|---|---|
| vLLM (LLM) | `:8000` | chat completions + reasoning field | `/zhaoshu/llm/Qwen3.5-9B` |
| GTE embeddings | `:8003` | relation/entity semantic retrieval | `/zhaoshu/llm/Qwen3-Embedding-0.6B` |

No separate graph server — traversal runs **in-process** (`stage_5_graph_traversal`), so only the two HTTP services above are needed.

### Start commands
```bash
# GTE (light, ~1GB VRAM) — start first so vLLM can coexist
CUDA_VISIBLE_DEVICES=1 GTE_MODEL_PATH=/zhaoshu/llm/Qwen3-Embedding-0.6B \
  nohup python scripts/gte_api_server.py --port 8003 > logs/gte_server.log 2>&1 &

# vLLM (TP=2, both GPUs, ~8.5GB weights + KV)
nohup bash scripts/start_local_qwen35_server.sh > logs/vllm_server.log 2>&1 &
# ~3 min to first response (weight load 48s + torch.compile 38s + warmup 80s)
```

### Health checks
```bash
curl -s http://localhost:8003/retrieve -X POST -H 'Content-Type: application/json' \
  -d '{"query":"x","candidates":["a"],"top_k":1}'          # GTE up?
curl -s http://localhost:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"Qwen3.5-9B","messages":[{"role":"user","content":"ok"}],"max_tokens":10}'  # LLM up?
```

### Run a batch
```bash
# 100-case eval (the standard benchmark slice), parallel=16
python scripts/run_agent_batch.py --start 0 --end 100 \
  --output reports/<NAME>/results.json --parallel 16
# smoke first to verify the path:  --start 0 --end 1
```
`run_agent_batch.py` hardcodes pilot = `reports/cwq_gte_bridge_100/results.json`
(100 rows) and CWQ pkl = `data/cwq_processed/...completed.pkl`. Masked
wrong-type ids (`data/cwq_processed/mask_wrong_type_ids.json`) are excluded
automatically → typically yields **99 cases**.

### Render a trajectory
```bash
# results.json is a list; extract one case, then render
python scripts/render_trajectory.py tmp/<case>_raw.json tmp/<case>_trajectory.txt
```
`render_trajectory.py` takes a **single case dict** as input. To pull one case
out of a `results.json` list:
```python
import json
r=json.load(open('reports/X/results.json'))
c=next(x for x in r if x.get('case_num')==N)
json.dump(c, open('tmp/caseN.json','w'), ensure_ascii=False)
```

---

## Current state (2026-07-06)

### What just landed
4-tool merge (`decompose` + `select_relations` + `expand_branches` + `answer`).
`retrieve` and `select` are folded in: decompose runs GTE inline, select_relations
runs traversal inline. Per-case turns dropped ~7 → ~4. Spec: `specs/agent_redesign_spec.md` §0.

### Latest 100-case result — `reports/cwq_merged_100/results.json`
| metric | merged 4-tool | prior baseline (`cwq_fromwhere_100`) |
|---|---|---|
| GT hit | **91/99 (0.919)** | 90/99 (0.909) |
| LLM hit | 87/99 (0.879) | 88/99 (0.889) |
| Overall F1 | 0.7888 | 0.7935 |
| GT-hit F1 | 0.8472 | 0.8617 |
| GT-hit Prec | 0.8599 | 0.8878 |
| GT-hit Recall | 0.9045 | 0.9095 |

**Verdict**: merge held GT-hit (+1) and recall (~flat); small precision drop
(−0.028) from over-emitting candidates. Net: noise-level, acceptable for the
tool-count halving. Committed in `ab7ec0a`.

### Workspace triage (2026-07-06)
Cleaned a pile of uncommitted work on `agent-toolcall` into focused commits:
- `110eafe` — two default-off experimental features: `--adaptive-routing`
  (simple/complex split, zero-LLM classifier in `stage1_cascade.classify_complexity`)
  and `KGQA_DIRECTED_TRAVERSAL=1` (directed Freebase edges). **Neither
  benchmarked yet.** Also adds `agent`/`free` reason-styles to stage8.
- `0f2d80c` — `agent_stage_scorer.py` now parses `select_pool` + reports
  `S_plan`/`S_select`/`S_reason` (3-stage GT-recall decomposition).
- `7c10abf` — `_BATCH_SIZE` 500→100 (vLLM prefill-queue at 500), plus
  `KGQA_LLM_BATCH_TEMPERATURE`/`_TOP_P` env overrides.
- `81696f4` — tracked the react entry scripts (`run_react.py`,
  `run_cwq_react_eval.py`, `run_webqsp_agent_eval.py`, `render_trajectory.py`)
  + `tests/test_skill_aggregation.py`. Were untracked despite being the
  only way to run the already-committed agent.
- `05b1362` — removed `start_graph_server.sh` (graph traversal is in-process
  now) and `run_webqsp_qwen35_local.sh` (replaced by `start_local_qwen35_server.sh`).

Three RL-era dirs (`config/`, `configs/`, `prompts/`) — unreferenced by active
code — moved to `_archive/rl_{config,configs,prompts}/` (gitignored, kept on
disk in case RL is revisited).

### Reference trajectory
`tmp/case1_merged_trajectory.txt` (367 lines) — the canonical 4-tool example:
Lou Seal → SF Giants → 2014 World Series, F1=1.0, 4 clean turns.
Use it as the "what good looks like" sample.

---

## RL data sampling + EoG study (2026-07-07)

> Added mid-session to preserve context across resets. Source: ZCode
> session on `agent-toolcall` branch. Sampling artifacts live in
> `reports/samp_val_pool/` (**gitignored** — see trap; reproduce via
> `scripts/resume_sample.py`).

### Sampling pipeline (`reports/samp_val_pool/`)
- **Driver**: `scripts/resume_sample.py --batch-size 50 --max-batches 60`
  (nohup, PID was 267675 on 2026-07-07). Reads state from
  `reports/samp_val_pool/state.json` (`{next_offset, batches_done}`),
  writes one `batch_###.jsonl` per 50 cases × 4 samples = 200 traj.
- **Source**: `data/cwq_processed/val.pkl` (**3519 cases total**).
  Started at case 750 (`batch_013`), running to ~case 3750.
- **Per-traj schema** (`batch_###.jsonl`, one JSON per line): `case_id`,
  `sample_id`, `question`, `gt_answers`, `messages`, `gt_hit`, `llm_hit`,
  `llm_f1`, `llm_answer`, `S_plan`, `S_select`, `S_reason`, `total_score`,
  `scorer_notes`, `agent_failed`, `n_steps`.
  ⚠️ **The reward field is `llm_f1`, NOT `f1`.** Confusing two caused
  an earlier miscount (showed 0 SFT / 400 all-wrong). Always use `llm_f1`.
- **`grpo.jsonl` / `sft.jsonl` are OVERWRITE-per-batch** (not cumulative).
  They only reflect the last batch run. To get cumulative counts, aggregate
  across all `batch_*.jsonl` with `llm_f1` per `case_id`.

### Cumulative training pool (as of batch_020, case 750–1050, 1600 traj)
| bucket | rule | cases |
|---|---|---|
| all-correct → SFT | all 4 samples `llm_f1 ≥ 0.99` | **89** |
| mixed → GRPO | otherwise | **205 cases (205 samples)** |
| all-wrong → flag | all 4 samples `llm_f1 < 0.01` | **106** |
Total 400 cases. Ratio ~22/51/27. Mixed dominates → good for GRPO
(both + and − reward present). SFT 89 is thin but ok for cold-start.

### ⭐ Decisive diagnosis: bottleneck is `S_plan`, not data
On the **120 all-wrong cases** (3-stage GT-recall decomposition, best of 4):
```
S_plan = 0  (decompose/relation-select loses GT):  99/120 = 82%
S_plan > 0  (plan found GT, lost downstream):      21/120 = 18%
```
**Implication**: the failure is the agent picking the wrong relation
direction at the decompose/`select_relations` step — a **model-decision**
problem, not a data/recall problem. GRPO with a path-reward is exactly
the right lever (penalize wrong relation choice, reinforce gold path).

⚠️ **Open question to close before training**: is the gold path's relation
even in the GTE candidate set for those 99 `S_plan=0` cases? If yes →
pure decision problem, train. If no → real recall limit, must fix GTE
candidate strategy first. **TODO: sample 20 `S_plan=0` cases, check gold
relation membership in GTE candidates. ~30 min.**

### EoG repo study — `github.com/ysq111333/EoG` (ICLR 2026)
Cloned to `/tmp/EoG_ref/` (scratch; not in repo). Read `reward_func.py`,
`data/EoG_process.py`, `test/eog_eval.py`, `run_rog_cwq.sh`. Findings:
- **EoG is NOT an agent loop.** `eog_eval.py` dumps the **entire subgraph**
  (`graph_info`) into one prompt; the LLM "reasons" in `<think>` and emits
  `<answer>`. `grep search_entity|search_relation` → **0 hits in code**.
  The tool-action framing in the paper is conceptual; the impl is
  single-turn reasoning over a pre-extracted subgraph.
- **Same data as us**: default input is
  `qald_10_en_test_original_2hop_remove_errors.jsonl` (2-hop CWQ subgraph).
  No data advantage.
- **Reward = path-match only**: `total = hits@1*0 + f1*0 + reasoning*1.0`
  (`reward_func.py:45-49`). Pure process reward, final answer weight 0.
  Reasoning score = extracted triplets ∩ gold `reasoning_path` / |path|.
  Same family as our S_plan/S_select/S_reason, but more aggressive.
- **"EoG's search_relation bypasses pre-extracted subgraph" — FALSE.**
  This was the prior hypothesis for why EoG might be better; the code
  shows it operates on the same pre-extracted subgraph we do. Our agent
  (stepwise expand) is arguably the more flexible design.
- **Net**: EoG is same-family, same-data, same-reward-idea, but **no agent
  loop**. Our agent-ization is the differentiator, not a disadvantage.

### Decisions pending (this session)
1. **Verify gold-relation-in-GTE-candidates** on 20 S_plan=0 cases — **DONE
   2026-07-08** at scale (n=3013). Verdict: DATA 49% > MODEL-DECISION 36% >
   RETRIEVAL 15%. See "Plan-failure root-cause diagnosis" below.
2. Continue sampling to ~3750 cases (nohup, ~4h remaining as of 2026-07-07).
3. Then start training (89 SFT cold-start → GRPO on mixed).

---

## Plan-failure root-cause diagnosis (2026-07-08)

**Question**: for S_plan==0 (plan-failed) cases, is the failure model DECISION,
system RETRIEVAL, or DATA? Tool: `scripts/diagnose_plan_failures.py` (offline;
reads `reports/samp_val_pool/batch_*.jsonl` + val.pkl; gold relation = BFS
anchor→answer path in the case's own subgraph, generic rels filtered; adversarially
audited by a 6-agent workflow). Full JSON: `reports/samp_val_pool/plan_failure_diagnosis.json`
(**gitignored**).

⚠️ **SPARQL cannot label val.pkl cases** — `cwq_sparql/test.json` aligns to the
TEST pkl (3531/3531), NOT val.pkl (0 id/question overlap). Gold relations are
derived intrinsically per case. If SPARQL labels are wanted, sample the test pkl.

**Result (n=3013 S_plan==0 samples, after fixing 2 measurement bugs the audit
found — `normalize()` empty-string match + short-literal false-match)**:
| side | % | detail |
|---|---|---|
| DATA/SUBGRAPH | **48.7%** | gold answer entity absent from the case subgraph (BFS anchor→answer unreachable). Validated 8/8 by spot-check. |
| MODEL-DECISION | **36.0%** | TRAVERSAL 25.4% (gold rel retrieved AND selected, but graph walk missed answer) + DECISION 9.3% (gold in L2, not selected) + ANCHOR_MISS 1.4% (rooted on a type node). DECISION/TRAVERSAL validated 8/8 / 7/8. |
| SYSTEM-RETRIEVAL | **15.3%** | GTE_MISS 10.3% (gold in scope, GTE didn't surface) + SCOPE_MISS 5.0% (pruned by structural scope). Upper bound; the genuinely-GTE-accuracy subset is smaller (some are anchor-quality artifacts). |

**Headline**: plan failures are dominated by **DATA (~49%)** and **MODEL-DECISION
(~36%)**; **SYSTEM-RETRIEVAL (~15%)** is the smallest. Model-decision ≫ retrieval
(~2.4×), but BOTH are outweighed by the subgraph-coverage problem. **This overturns
the prior "S_plan=0 = decision problem → GRPO is the lever" framing: ~49% of plan
failures are unreachable by any model/GTE/prompt change (answer not in graph) —
GRPO cannot move them.**

**Actionable code defects flagged by the audit (production agent, NOT yet fixed)**:
1. **Traversal/materialization** (largest validated lever): on the
   `influence.influence_node.*` family the model selected the correct outgoing
   gold edge that 1-hop reaches the answer, yet the answer never entered the
   plan-reachable pool. Pure code fix, near-100% conversion on that family. Also:
   forward-only-traversal vs undirected-gold mismatch on symmetric pairs
   (influenced/influenced_by); multi-hop branch expansion fails when the 2nd-hop
   relation is outside the anchor scope.
2. **Over-conservative L3 selection**: `select_relations` picks l3_union_size
   1–6 vs l2_union_size 7–19 — drops available gold. Relax the budget so l3
   scales with l2.
3. **Anchor selection**: type/meta-node rejection when a concrete q_entity exists
   (Turkey→"Country"); degree tiebreak for name collisions (":Sydney" stub vs
   city); **possible RUNTIME anchor-propagation bug** — verify the ReAct BATCH
   path propagates the model's decompose anchor to `ctx.anchor_idx` before
   `_gte_for_fact` (single-case path does via `_resolve_anchor`; batch
   `_process_one` may not).
4. Genuine GTE-accuracy failure is the SMALL minority — don't over-invest; GTE is
   hard-capped by the per-case subgraph (Freebase can't be loaded).

**Recommended order**: (a) verify+fix the batch anchor-propagation bug + the
influence-node materialization defect (highest certainty, pure code); (b)
quantify DATA recoverability — count "one-hop-short" cases (intermediate
discriminator present, final answer edge dropped) for targeted deeper
re-extraction; (c) relax L3 budget + improve relation-name display; (d) then
revisit RL — train only on the model-decision subset, exclude the data-side.

---

## GrailQA / GraphQuestions integration (2026-07-09)

**Status: cannot run here — needs Freebase KG for subgraph extraction.**

The framework does inference on **pre-extracted per-case subgraph pkls** (val.pkl /
test pkl format: `h_id_list/r_id_list/t_id_list` + ents/rels). Freebase cannot be
loaded in this container. Any new Freebase dataset (GrailQA, GraphQuestions) must
have its candidate subgraphs extracted on a server WITH Freebase, then the pkls
brought here for inference.

**Data sources (QA only, NO subgraphs):**
- GraphQuestions FB15: `dki-lab/GrailQA` repo `data/graphquestions_v1_fb15_*.json`
  (gold graph = query pattern, avg 2.5 nodes; **answer in it 0%** — NOT a candidate
  subgraph).
- GrailQA QA data: https://dl.orangedox.com/WyaCpL/ (same gold-graph format).

**KG (for extraction):** full Freebase via Virtuoso (`dki-lab/Freebase-Setup`) or
FastRDFStore/Sempre (per `ysu1989/GraphQuestions` README). NOT a simple file
download. ArcaneQA's `cache/` = SPARQL result caches, NOT subgraphs. The on-disk
FB15k/FB15k237 (`/zhaoshu/kgc/`) are KGC subsets, incompatible (7.6% mid overlap
with GraphQuestions).

**Server-side extraction steps (do where Freebase is available):**
1. Set up Freebase (Virtuoso via `dki-lab/Freebase-Setup`, or FastRDFStore).
2. For each GrailQA/GraphQuestions question: entity-link the topic entity, extract
   a 2-3 hop candidate subgraph (`data/deploy_bundle/graph_server.py` does this;
   produces h/r/t + ents/rels per case — same as how val.pkl/test pkl were built).
3. Serialize to the pkl format: `id, question, q_entity, text_entity_list,
   non_text_entity_list, relation_list, h_id_list, r_id_list, t_id_list, a_entity`.
4. Copy the pkl here; run inference via `run_agent_batch` (ReAct, the current
   agent) or `run_pipeline` (legacy stage).

**Architecture mismatch (why "direct" doesn't work):** GrailQA/GraphQuestions/
ArcaneQA query Freebase at runtime via SPARQL; our framework retrieves from
pre-extracted per-case subgraphs. Converting requires the KG for extraction.

---

## Hit@1 + scoring fixes + F1<1 analysis (2026-07-10)

### Commits this session
- `5813eb3` traversal: CVT transparency in _hit_paths (+4.36pp F1, ReAct greedy A/B)
- `d381143` score: S_plan from structured pool (not overview regex); answer_candidates captured
- `6a27056` agent: Hit@1 metric in react_loop + minimal "first=most-certain" SELECT
- `cc06462` score: fuzzy threshold 0.92→0.95 (stop collapsing year-variant events)

### Current metrics (100-case test, greedy, corrected matcher)
GT-hit 90.9% > llm_hit 85.9% > **Hit@1 79.8% > F1 77.2%** (standard hierarchy).

### CWQ SPARQL constraint distribution (n=3531)
**92.3% list-all** (no LIMIT) → keep-ALL default is CORRECT. **7.7% LIMIT-1** → irreducible
ambiguity (English doesn't convey SPARQL constraint). Don't default to "most recent."

### F1<1 failure classification (32/99)
- **5 LIMIT-1** (irreducible hidden constraint): Lou Seal/Crazy Crab "what year" w/ SPARQL LIMIT 1.
- **27 list-all** (actionable): OVER_EMIT 9 (junk in set, CVT dates not displayed), UNDER_EMIT 7
  (world knowledge narrowing — NBA model said "From world knowledge, Brad Stevens..."),
  SELECTION_MISS 6 (wrong entity), RETRIEVAL_MISS 9 (gold alias / missing / granularity).
- **84% of multi-entity answers are alphabetically sorted** (LLM habit) → gold often alpha-later → Hit@1 wrong.

### Key case findings
- **Libya leader**: expand 80 triples but only 2 with dates. 7/8 leaders lack CVT tenure dates → model can't distinguish → over-emit 8.
- **NBA Finals**: model used WORLD KNOWLEDGE ("Brad Stevens coached 2013-2021") to narrow 17→1. Violated "graph only."
- **Lou Seal**: always emitted all 3 WS (baseline too). F1=1.0 was inflated by fuzzy 0.92. After fix F1=0.5 (honest).

### Answer-cardinality analysis (partial = list answer, F1∈(0,1)) — 2026-07-10
Of 99 cases: SINGLE_HIT 61 · SINGLE_MISS 14 · LIST_FULL 13 · **LIST_UNDER 8** · LIST_OVER 2 · LIST_MIXED 1.
**After the fuzzy fix, UNDER-emit (8) dominates OVER-emit (2)** — junk is no longer the main problem; dropping valid answers is.
All 11 partial cases have gt_hit=TRUE (gold in the 60-dedup pool) — so it's reasoning/tooling, not subgraph recall.
Decomposed the 11 by WHERE the cardinality split breaks (`scripts/analyze_answer_cardinality.py` + `analyze_under_cause.py`):

| root cause | n | cases | mechanism |
|---|---|---|---|
| **REASONING** (gold fully shown, model narrowed) | 4 | Barcelona-God 4→1, Ohio-gov 2→1, Mansfeld 6→9(OVER), GrandCanyon 2→3(MIXED) | "their God/the governor" read as singular; world-knowledge |
| **EXPAND-TRUNC** (gold in pool, expand didn't surface) | 3 | CO2, Frankfort, NBA | see below |
| **SUBGRAPH-MISS** (gold not even in pool) | 3 | Bachelet 4/5, Castlemont 0/2, Missouri 4/6 | pre-extracted pkl missing gold — out of agent scope |

**(a) vs (b) for EXPAND-TRUNC — verified the user's hypothesis:**
- **(a) branch under-expansion: CO2, Frankfort.** Gold IS in the ranked evidence-tree overview, but on branches the model never expanded.
  - CO2: 4 branches exist → model expanded only [1,2]. Costa Rica (×3) + El Salvador (×2) sit on branches 3,4.
  - Frankfort: **30 branches** exist → model expanded only [1,2]. "Contiguous US"(×8) + "US w/Territories"(×1) on branches 3–30.
- **(b) in-branch cap (SECONDARY): NBA.** Branch 1 correct (all 17 Finals on the championship chain), but candidate display cap surfaced only 10/17. Model then self-narrowed 10→1 (world knowledge) — so (b) cap is minor vs reasoning.
- CVT value-noise crowd-out (CO2 branch 1: 515 materialized paths → only 4 country candidates): the `co2_emissions_per_capita` CVT explosion floods candidate slots with value-nodes (g.1245_xxx) instead of resolving back to countries.

**SPARQL cross-ref — narrowing is NEVER query-justified for list questions (2026-07-10):**
Joined 99-pilot case_ids → `data/cwq_sparql/test.json` (3531, real SPARQL in `sparql` field; `machine_question` is the NL query intent).
- Meaningful narrowing operators across 3531: **LIMIT 7.7%** (ALL are `LIMIT 1`+`ORDER BY DESC(datetime)` = superlative/"most recent" → gold=1, classified single) · **COUNT 27.6%** ("how many", different gold format). **FILTER 99.2% is STRUCTURAL boilerplate** (`?x != ?c` anti-self-join + lang filter) — NOT semantic, do not count.
- **0% of the pilot's 24 LIST questions carry LIMIT/ARGMAX.** Logical closure: if the query had LIMIT, gold would be 1 (→ single); gold>1 (list) ⟹ query has no narrowing ⟹ gold IS the full set the query returns.
- ∴ every under-emit ("3答2"/"4答1") is NEVER constraint-justified: the narrowing exists in neither SPARQL nor 题干. Model **invents** it (conservative bias + singular-reading + world-knowledge).
- Under-emit decomposes into: **invented-narrow** (pool had ALL gold, model self-cut: Barcelona 4→1, Ohio 2→1, Frankfort 3→1, NBA 17→1 = reasoning layer) vs **retrieval-miss** (pool lacked gold: Bachelet 5→4, Missouri 6→4, Castlemont 2→0 = subgraph).
- **Confirmed: the reasoning layer over-narrows; retrieval supplies the info; query labels say "return full set."**

**CoT fix framework + Type A/B split (user direction, 2026-07-10; SPARQL used as analysis LABEL, not model input):**
Fix is NOT a structured `<evidence>` block — it is a CoT ORDERING in `<think>`: **证据(evidence) → 约束(explicit constraints) → CVT隐含约束(CVT attributes that exist but 题干 didn't state) → 推理(answer)**. The 3rd step is the crux — that is where invented narrowing happens. Real-SPARQL labels split the 4 invented-narrow cases into two complementary fix targets:
- **Type A (plain multi-value, no CVT, no constraint): Barcelona 4→1, Frankfort 3→1, NBA 17→1.** SPARQL is just `entity→multival→?x` (NBA's has NO date-intersection — model INVENTED "championship during Stevens tenure"). Fix = CoT step 1 (list evidence) + step 3 rule: "CVT has dates but 题干 didn't ask to filter by date → DO NOT apply." Step 1 alone fixes Barcelona/Frankfort.
- **Type B (CVT mediator + date attrs + real constraint): Ohio 2→1 (and Libya).** Ohio SPARQL filters on CVT `government_position_held.from/to` (during 2011) + a 2nd CVT (before 1983); gold=2 (Meigs via NOT EXISTS date-missing branch). Model can't apply because expand_branches doesn't SURFACE CVT date attrs. Fix = expand_branches CVT 属性补全 (separate TODO). CoT can't fix alone.
- **CoT step-3 rule (locked):** list CVT-implicit attrs (date/role/qty); 题干 states the constraint → filter via the matching CVT attr; 题干 does NOT → list but DO NOT use as filter, keep all. Attacks Type-A invented narrowing; needs CVT-display fix for Type B.

**⚠️ FRAMEWORK CORRECTION (2026-07-10) — the above step-3 rule is WRONG, superseded below:**
The rule "题干没给时间 → 全留" is self-contradictory on Libya. Libya SPARQL filters `government_position_held.from/to` to **2015-08-10** (= dataset "now" / current leader), but **the date is NOT in 题干** — it comes from present-tense "is the leader" / "now." So for time-bound relations, filtering is REQUIRED even when 题干 gives no date.
**Correct判据 = relation type, not 题干-ness:**
- **Accumulative/set relations** (all coexist): championships, deities, containedby, education, languages_spoken → CVT dates are bookkeeping → list ALL, never filter. (Model error = treating as exclusive → under-emit: Barcelona/Frankfort/NBA.)
- **Exclusive/temporal relations** (one-at-a-time): government_position_held, head_coach, marriage → CVT dates are tenure bounds → MUST filter. Time source = 题干 explicit date (Ohio 2011/1983) OR present-tense "is/now" (Libya current). (Model error = treating as accumulative → over-emit: Libya 8.)
- NOTE: CVT-ness alone doesn't decide — `government_position_held` and `education` are both CVT+date, but former exclusive (filter), latter accumulative (list-all, Castlemont gold=2).判据 = real-world "one-at-a-time?" semantics.
- Model's under-emit AND over-emit are SYMMETRIC symptoms of ONE error: misclassifying the relation type. NOT two independent fixes.
- **CVT-date display (expand_branches) is NOT an optional patch — it is the required execution substrate for the EXCLUSIVE branch** (Libya/Ohio can't filter without dates surfaced). Promotes the expand CVT-属性补全 TODO from optional to necessary-for-exclusive-relations.
- **Revised step-3 rule:** (1) classify relation exclusive vs accumulative; (2) accumulative → list all, dates not filters; (3) exclusive → must filter by time (题干 date or present-tense→current), needs CVT from/to displayed.

**Framework VALIDATED on full pilot (`scripts/scan_relation_framework.py`, gold-cardinality × SPARQL-filter, 99 cases):**
```
              no-filter   FILTERED
single gold       56         19
list gold         23          1
```
- Binary holds — **100% of cases are exclusive (filtered, ~20%) or accumulative (no-filter, ~80%)**. No third type. The 1 list+filter case (Ohio) is "exclusive + time-window" (governor during 2011, gold=2 incl. a NOT EXISTS date-missing artifact) — still exclusive, not a counterexample.
- **CRITICAL REFINEMENT: accumulative ≠ "many answers".** 56/79 no-filter cases have gold=1 (data-driven: "where did X go to college"→1 school; "what country borders France & has airport serving Y"→1). Cardinality for no-filter cases = how many entities satisfy the constraints in Freebase (usually 1, sometimes 17).
- ∴ the rule is "accumulative → return the full SATISFYING set, size is data-driven (1 or many)", NOT "accumulative → return many". The 56 accumulative-|G|=1 cases are where the model ALREADY succeeds (returns the 1) — NOT the risk surface.
- **Risk surface = 23 accumulative-list (invent-filter→under-emit: Barcelona/Frankfort/NBA) + ~20 exclusive (fail-filter→over-emit: Libya).** Model may use relation-SEMANTIC world knowledge (gov_position=exclusive, championships=accumulative — allowed by AGENTS.md "typing the relation") but NOT entity-specific world knowledge (NBA date-intersect).
- Fix is sound; no framework rework needed, only the "accumulative=many" implicit assumption must be corrected to "accumulative=full satisfying set, data-driven size".

**Time-resolution within exclusive relations — VALIDATED on full test (`scripts/scan_time_resolution.py`, 421 government_position_held cases):**
Cross-tab role × time-shape:
```
                    no-date  attr-no-f  pt(now)  filt(date)
ANSWER(person)           0         0       39         59
CONSTRAINT             247        39        0         37
```
- **"unspecified-time → latest" has ZERO exceptions within the answer-relation** (39/39 point-in-time cases filter to dataset "now" = 2015-08-10, all present-tense "who is the leader/PM"). The "not-latest" cases are ALL constraint-role (247 no-date: person's position used to identify a country, answer is religion/language/location — time irrelevant to the answer).
- ∴ determinant = **answer-relation vs constraint-relation** (structural, model can read from 题干): "who is the leader" → answer=person → must filter (now→latest if no date, else 题干 date); "what religion in the country where X holds position" → constraint → no filter.
- datetime literals: 2015-08-10 ×39 (= "now"); 2009/2011/2010 year-ranges (= 题干 explicit years); 1795-03-04 / 1983-01-03 (= 题干 explicit historical dates). All dates traceable to either dataset-now or 题干.
- **98 answer-relation cases ALL need CVT from/to displayed to execute** (39 now→latest pick incumbent; 59 apply 题干 date). Quantifies expand CVT-display ROI: 23% of gov_position cases, and the sole prerequisite for getting them right. Model picks latest via "no `to` date OR most-recent `from`" — approximates dataset-now (Freebase snapshot ≈2015) without needing the literal 2015-08-10.

**Gold source + single/multi split + implicit-constraint catalog (2026-07-10, `scripts/catalog_implicit_constraints.py`):**
- Gold = pkl `a_entity` field = result of executing gold SPARQL against Freebase. Cardinality is EMERGENT (SPARQL constraints × Freebase data), NOT manually labeled. **single |G|=1: 75.8% (2676) · multi |G|>1: 24.2% (855)**.
- Constraint catalog across 3531 SPARQL:
  - structural/ignore: negation `?x!=?c` 97.8% (anti-self-join boilerplate).
  - EXPLICIT (model reads from 题干): time-explicit 7.7% (date in 题干) · LIMIT/ORDER-BY 7.7% (superlative word).
  - IMPLICIT (truly invisible): **hidden "now" time 2.1% (73)** — all present-tense "who is the leader/PM/governor", SPARQL hardcodes 2015-08-10 · **NOT-EXISTS 3.9% (138)** — data-completeness permissive clause (admits entries with missing dates, e.g. Ohio Meigs) · time-attr-only 5.0% (partial).
- Only ~6% of questions carry a truly-implicit constraint. Of those:
  - **hidden-now (2.1%) is the only one worth treating** — recoverable via "exclusive answer-relation + present-tense → pick incumbent (no `to` OR most-recent `from`)" which needs CVT-date display. Maps exactly onto the 39 now-type answer-relation cases.
  - NOT-EXISTS (3.9%) is unrecoverable but a PERMISSIVE clause (admits extra candidates) — ignoring it only loses data-missing edge answers, low cost, not worth treating.
- ∴ the model does NOT need the literal 2015-08-10; it needs (relation-type + role + tense) judgment + CVT dates surfaced. Confirms fix scope: CVT-date display (substrate) + relation-type/role-aware CoT (prompt).

**Generalization: implicit constraints are RELATION-AGNOSTIC, not just time (`scripts/scan_relation_slots.py`, 2026-07-10):**
- **342 distinct answer-relations** in test set; **27 concepts have ≥2 disambiguating slots** (language: official_language 48 vs languages_spoken 195; currency: currency_used 167 vs currency_formerly_used 9; border: contains/containedby/adjoins/partially_contained; religion: religion_percentage/deities/texts; film: actor/director/writer/producer slots). ∴ per-relation rule enumeration is INFEASIBLE — need a relation-agnostic pattern.
- The unifying structure: **answer = candidate set ∩ (selection-criterion → graph-evidence) filter**. The 342 relations don't matter; the CRITERION does. Only 5 criterion types: temporal (tense/date→CVT dates) · designative (official/main→right slot) · superlative (largest/predominant→numeric attr) · exclusivity-implied (one-at-a-time relation→needs temporal even if unstated) · none (no selection word + non-exclusive→return ALL).
- **The reasoning pattern (locked): answer = candidates satisfying the criterion bound to graph evidence; no criterion + non-exclusive → full set.** 4 disciplines, each fixes one observed error:
  1. recall broadly, don't pre-filter (fixes under-emit / singular over-read: Barcelona/Frankfort)
  2. extract criterion explicitly — explicit words ∪ exclusivity semantics (fixes implicit-constraint miss: Libya now, official-language)
  3. criterion MUST bind to graph evidence; no evidence → don't filter, never invent (fixes world-knowledge narrowing: NBA)
  4. no criterion + non-exclusive → keep ALL (fixes conservative bias)
- Maps to pipeline: decompose (relation_hint must carry criterion precision) · select_relations (pick slot by criterion, recall both if ambiguous) · expand_branches (SURFACE criterion evidence — CVT dates, %; the gap) · answer (criterion→evidence→filter, default-all).
- Coverage: pattern handles filter-type + set-type (~72%). COUNT "how many" (~28%, answer=number, aggregate) is a separate type the model already mostly gets right — not the risk surface.
- Fix is NOT rule-writing; it's restructuring the answer step into explicit criterion→evidence→filter reasoning + surfacing criterion evidence in expand.

**⚠️ CORRECTION — expand already expands CVT attributes; drop the expand lever (2026-07-10):**
Earlier claim "expand doesn't show from/to → fix expand to display CVT dates" was a WRONG premise. Verified on Ohio: the select-built POOL (CVT-expanded) contains 5 tenure dates (2011-01-10, 1810-12-08, 1982-01-13, 1808-12-12, 1979-01-03). expand's design locates the CVT and expands its attributes — from/to ARE expanded.
- What actually happens (Ohio): the 2-branch expand surfaced Kasich's date (2011-01-10) + Meigs the PERSON, but not Meigs' date (his date is on an unexpanded branch). So a candidate can appear WITHOUT its full CVT date profile — a per-branch coverage nuance, NOT "from/to not expanded."
- **The Ohio failure is FIXED by answer-step discipline #3 alone, NO expand change:** Kasich has date→qualifies→keep; Meigs has NO date evidence in expand→cannot exclude→KEEP → Kasich+Meigs = gold.
- ∴ **DROP the "expand CVT-date display" lever entirely.** Fix = PURE answer-step CoT (the 4 disciplines, esp. #3 "no evidence → don't filter, keep candidate"). The earlier "98 cases need CVT-date display" is superseded: those cases need the model to USE the already-expanded dates, and keep candidates whose dates aren't surfaced.
- Net fix scope: ONE change — restructure the answer step into criterion→evidence→filter CoT. No expand/select code change required.

**Label-ambiguity ceiling — irreducible, same class as LIMIT-1 (2026-07-10, language proof):**
- Verified: the SAME phrasing "what language is spoken in [place]" maps to DIFFERENT gold relations — official_language (Egypt/Gebel Elba→[Arabic]) vs languages_spoken (Chile→[5 langs], Denmark→[4], Thailand→[13]). Indistinguishable from text; SPARQL annotator chose per-case. To a human BOTH answer-sets are valid.
- Harm is bounded by the "monolingual coincidence": 45/48 official and 129/259 all cases have |G|=1 — for monolingual places official≈all return the same entity (Dominican Republic→Spanish under both), so picking the "wrong" relation still answers right. Ambiguity only BITES on multilingual places (official≠all): ~3 official-multi + some all-multi.
- Statistical tiebreaker: answer=language → **gold=all 84% (259/307), official 16% (48)**; only 7/48 official cases carry the word "official". ∴ default to ALL (languages_spoken) — the keep-ALL default — is correct 84% of the time; flip to official only on explicit "official" signal. Consistent with the 92.3% list-all finding.
- GENERALIZES to ALL multi-slot concepts (currency used/formerly, border contains/adjoins/partial, religion any/predominant): CWQ gold = "one valid answer-set of several"; non-gold-but-defensible answers are penalized.
- **Implication for optimization:** the eval has an irreducible ceiling — some F1<1 cases are label ambiguity, NOT model error, and cannot reach F1=1 no matter the model. MUST separate model-error from label-ambiguity before chasing. Best strategy = default-broad-relation + flip only on explicit signal + accept ambiguity ceiling (don't chase it). This is statistical backing for keep-ALL + the 4 disciplines, not a new rule.

**Full-test-set ambiguity screen (`scripts/screen_annotation_ambiguity.py`, sub-agent, 2026-07-10):**
- UNION potential ambiguity: **565/3531 = 16.0%**; HARD grade (no disambig signal): **493 = 14.0%**. Multi-slot hard 350 (9.9%) + soft 73 (2.1%); hidden-criterion 144 (4.1%: hidden-time 74, NOT-EXISTS 138, overlap).
- Per-concept HARD ambiguity split into defaultable (gold=majority slot → defaulting recovers) vs irreducible (gold=minority slot, no signal → true ceiling):
  - CURRENCY: 95% maj → 83 defaultable, 0 irreducible (fully defaultable, default currency_used)
  - LANGUAGE: 80% maj → 116 defaultable, 40 irreducible (default languages_spoken; 40 official-as-minority unrecoverable)
  - RELIGION: 68% maj → 19 defaultable, 1 irreducible (default religion_percentage/predominant)
  - BORDER_CONTAIN: 44% maj (plurality only) → 45 defaultable, 29 irreducible (NO good default — concentrated irreducible)
  - GOVT_FORM_HOLDER: 63% maj → 6 defaultable, 17 irreducible (ambiguous cases mostly want form_of_government, the minority — mostly irreducible)
- **~269 hard-ambiguity cases are defaultable** (default-broad + explicit-signal-flip recovers them). **~87 are truly irreducible** (concentrated in language 40, border 29, govt 17) ≈ 2.5% of test = the ambiguity ceiling.
- **Combined irreducible (ambiguity ~2.5% + hidden-time 2.1% + LIMIT-1 class) ⇒ real F1 ceiling ≈ low-90s%.** Anything above is label ambiguity, not earnable by the model.
- Optimization target: implement per-concept statistical default (currency→used, language→all, religion→predominant) + flip only on explicit signal; do NOT chase the ~87 irreducible. Caveat: disambig-signal detection is keyword-heuristic, hard-count may slightly over-count; relative ordering and defaults are robust.

**Full-3531 GT × SPARQL structural profile (`scripts/profile_gold_sparql_structure.py`, sub-agent, 2026-07-10) — validates all pilot conclusions at scale:**
- Gold cardinality × filter: single 2146 no-filter / 530 filtered; list 766 no-filter / 89 filtered. **single 75.8% / list 24.2% (matches pilot). filtered→86% single, no-filter→74% single (both mostly single; no-filter's 26% list = data-driven).**
- **Single-predictor ranking:** LIMIT 100% single (272) · exclusive-relation 90% (mean|G| 1.1) · title-filter 81% · accumulative 72% (mean|G| 2.0). **Constraint richness: m_count 1→2→3→4 = 59→81→87→89% single** (more constraints ⇒ more single).
- **Framework CONFIRMED at scale:** exclusive (kw, n=256) single 90%, mean|G| 1.1, 76% filtered; accumulative (n=1549) single 72%, mean|G| 2.0, 10% filtered. Exclusive→~1, accumulative→data-driven.
- **Relation→cardinality PRIOR (usable by model):** always-single (~95%+): place_of_birth, actor, official_language, place_of_death, date_founded. inherently-list (<60% single): **languages_spoken (39% single, mean 3.5)**, form_of_government (42%), genre (51%), profession (55%), containedby (58%). Model should EXPECT many for the list-y relations.
- **CORRECTION: GT is ~100% entities (3530/3531), literals≈0; COUNT queries = 0.** Earlier "COUNT 27.6%" (catalog_implicit_constraints) was a false-positive — RETRACTED. ∴ all answers are entity sets, NO number/aggregate answer type to handle. Simplifies output format.
- List cases (n=855): mean |G| 4.7, median 3; |G|≥15 (36 cases) = film lists + championships.
- Ambiguity ceiling revalidated stable: 16% union / 9.9% hard / 2.5% irreducible (73% of ambiguity is single-answer).
- ∴ pilot conclusions all hold at scale; 3 additions: framework confirmed, relation-cardinality prior table, COUNT-type retracted.

**WebQSP data profile (`scripts/webqsp_profile_gold_sparql_structure.py` + `webqsp_screen_annotation_ambiguity.py`, sub-agent, 2026-07-10) — DIFFERENT distribution from CWQ:**
CWQ vs WebQSP comparison:
| metric | CWQ(3531) | WebQSP(1639) |
|---|---|---|
| single gold | 75.8% | 49.7% |
| list gold | 24.2% | 49.7% |
| filtered | 17.5% | 11.1% |
| exclusive-relation single% | 90% | 58% |
| accumulative single% | 72% | 39% |
| list mean |G| | 4.7 | 19.4 |
| ambiguity union | 16.0% | 14.8% |
| irreducible ambiguity | 2.5% | 4.6% |

- WebQSP is HALF multi-answer (vs CWQ's quarter) with MUCH bigger lists (mean 19.4, median 4; |G|>15 = 128 cases/7.8%). Big-list relations: film.performance.film (mean 38), countries_spoken_in (36), tourist_attractions (26), languages_spoken (13), postal_codes (15).
- GT type: 95.9% entity, 2.9% literal, 0.7% empty, 0.5% mixed (WebQSP HAS literals + empty-gold, unlike CWQ's 100% entity). COUNT=0; literals are years/numbers.
- Relation→cardinality prior is STRONGER/more extreme in WebQSP: near-100% list (mean 20+): tourist_attractions, countries_spoken_in, film.performance.film, languages_spoken, postal_codes. near-100% single: place_of_birth, place_of_death, currency_used (92%).
- Framework still directional but WEAKER: exclusive 58% single (vs CWQ 90%) — WebQSP's exclusive-relation questions often ask for ALL holders (no time filter), so exclusive does NOT default to "filter to latest" here. Must distinguish "the X" (→one) vs "all X" (→all) from 题干.
- Less filtering (11.1%); no-filter is list-MAJORITY (52% list vs CWQ's 26%) — WebQSP relies on "return what the relation returns."
- Higher irreducible ambiguity (4.6%) ⇒ lower F1 ceiling than CWQ.
- **Implications for reasoning optimization:** (1) default-all + don't-invent-filter matters MORE (half list, big lists, conservative narrowing drops F1 hard); (2) relation-cardinality prior is a strong usable signal, esp. for the near-100%-list relations; (3) exclusive relations need 题干 "the vs all" judgment, NOT default-latest; (4) handle empty-gold (0.7%) + literals (2.9%).
- 85% of cases expand ≤2 branches (modal = 2, exactly 44/99); only 3/99 expand ALL available. 94/99 expand fewer than available.
- BUT the model picks branches **semantically** (status notes: "expand branches that reach the religions (3,4)", "branch 1 directly connects X→Y"), NOT by copying the prompt's `['1','2']` example. `['1','2']` dominates because branches are **pre-ranked by relevance** → answer usually in top 1-2.
- **Under-expansion rarely costs F1:** of 23 under-expand list cases, mean F1 = **0.794** and ~13 are F1=1.0 (top branches held the full answer). True branch-selection losses = **only CO2 + Frankfort (~2 cases)**. NBA/Barcelona/Mansfeld/Ohio saw gold in the expanded branch but narrowed anyway → those are **reasoning**, not branch-selection.
- Real failure driver = **branch generator over-fragmenting one semantics** (CO2: 4 branches, Frankfort: 30) → gold diluted into low-ranked branches the model reasonably skips as "duplicates."

**Fixable levers (priority order, evidence-weighted):**
1. **[P0] reasoning singular-over-narrow** — Barcelona 4→1, Ohio 2→1, NBA 10→1, Mansfeld over-emit: model SAW gold but narrowed. Biggest bucket. Prompt: "their X / the Y" can be a set; graph lists N → emit N; graph-only (no world knowledge).
2. **[P1] branch de-fragmentation** — merge same-semantics branches so gold isn't diluted into low-ranked ones (CO2/Frankfort). NOT "force expand all" — that wastes the ~18 cases where expand-2 already gives F1=1.
3. CVT candidate de-noise — resolve value-nodes back to entities (CO2 secondary).

---

## Traps & gotchas

### `tmp/` AND `reports/` are both gitignored — artifacts are NOT safe
`.gitignore` excludes **both** `tmp/` and `reports/`. Trajectories, dumps,
run results, scratch JSONs written to either **will be lost on container
reset**. Decision (2026-07-06): keep `reports/` entirely untracked — the
run results are reproducible by re-running `run_agent_batch.py`, so we
record only the *metrics + run path* here in memory, never the artifacts.
Only `specs/`, `scripts/`, `kgqa/`, and `docs/` are git-tracked (safe).
If an untracked artifact genuinely matters (e.g. a one-off trajectory to
keep), copy it into `specs/` with a dated name, or it's gone on reset.

### "Deleted" scripts aren't actually lost
39 scripts show up under `git log --diff-filter=D` (e.g. `test_chain_decomp_v2.py`,
`build_case_skills.py`). They were removed by a commit but remain in history —
recover with `git show <commit>:scripts/<name>.py`. Only **untracked** files
(things never committed) are truly gone on reset.

### `reasoning_end_str` leaks into content
vLLM's reasoning boundary phrase (`"I will now emit the tool call..."`) can
bleed into the `content` field, corrupting a tool arg mid-JSON (seen in
case1 turn 3: `branch_ids: ["1I will now emit..."`). The `parse_react_output`
truncation-recovery fallback usually saves it by taking a later valid JSON,
so results don't break — but it's a latent parsing-robustness issue. Watch
for it if a case fails with a malformed-args rejection.

### GTE port conflict
If `:8003` is already bound (another shell started it), a new GTE process
exits with `Errno 98 address already in use` after loading the model. Check
`ss -tlnp | grep 8003` and `pgrep -af gte_api_server` before starting —
there's likely one already alive (health check returns 200).

---

## TODO / open levers (updated 2026-07-10)

### Done this session
- [x] CVT transparency fix (commit 5813eb3, +4.36pp F1 ReAct greedy A/B)
- [x] S_plan from structured pool (commit d381143)
- [x] Hit@1 metric + minimal "first=most-certain" prompt (commit 6a27056, +2pp Hit@1)
- [x] Fuzzy threshold 0.92→0.95 (commit cc06462, F1 honest, Hit@1 > F1)
- [x] F1<1 failure classification + CWQ SPARQL distribution (92.3% list-all)
- [x] GrailQA spec: needs Freebase KG extraction (commit 77a16b3)

### Done — answer-layer prompt engineering CONVERGED (2026-07-11)
- [x] **Answer prompt = content-checklist "B" (constraint-forced)** — AGENTS.md answer step now requires the model to write, IN CONTENT before `tool:`: `CANDIDATES → CONSTRAINTS the question states (one graph triple each) → ANSWER`. Lean-content suspended for the answer call; parser anchors on `tool:`. Winner of an exhaustive A/B arc (FROM→WHERE→SELECT, 4-step, v4-minimal C, structured-`<think>`, Role-tighten, 27B model, content-checklists A/B/C). Only B did NOT regress (F1 0.7768 vs baseline 0.7744, best llm_hit 87.9%) and fixed NBA (returned all championships). Tooling: `scripts/abcd_test.py`, `scripts/ab_test_compliance.py`, `scripts/ab_test_content_cot.py`, `scripts/run_cases_ab.py`.
- [x] **Reframe: remaining F1<1 is GOLD NOISE, not model error** — the content checklist PROVES the model reasons correctly (cites graph triples, applies constraints). Barcelona "their God"→God is label ambiguity (God defensible, ~2.5% irreducible); Ohio Kasich-only is the SPARQL NOT-EXISTS date-missing artifact (Meigs qualifies via missing-date loophole; model's Kasich answer is semantically correct). **不为标注错误让位 — don't chase these.**
- [x] 27B model ruled out (not better — same singular bias, regressed Mansfeld + bare-year format). Model size is not the bottleneck.
- [x] `expand_branches` candidate_attrs display fix in tools.py (surfaces `to=(incumbent)` for exclusive-role incumbent detection; fixed Libya 8→1).

### Open — RL / data (the next phase)
- [ ] **Re-sample RL data with fixed code** (CVT fix + scorer fix + candidate_attrs + content-checklist prompt B). Old samp_val_pool has buggy scorer + no CVT fix + lean-content prompt.
- [ ] **SFT cold-start on B prompt** → GRPO. Reward = total_score + can add top-1 reward for Hit@1. RL target: enforce coexisting→all, no-evidence→keep, no-world-knowledge, pick-incumbent-for-current-role (the behaviors B surfaces but the model's prior still sometimes overrides).
- [ ] **val.pkl unrepaired** (19.1% answers not in subgraph). Filter GT-suspect before training.

### Open — lower priority
- [ ] **branch de-fragmentation** (CO2/Frankfort) — merge same-semantics branches so gold isn't diluted into low-ranked branches. Low ROI (under-expand rarely costs).
- [ ] Benchmark adaptive-routing + directed-traversal (commits 110eafe, default-off).
- [ ] GrailQA: needs Freebase KG on a server (see GrailQA section above).

### Open — lower priority
- [ ] Benchmark adaptive-routing + directed-traversal (commits 110eafe, default-off).
- [ ] GrailQA: needs Freebase KG on a server (see GrailQA section above).

---

## File map (what lives where)
- **Design spec** (why): `specs/agent_redesign_spec.md` §0 = current truth.
- **Operational memory** (how): `specs/SESSION_MEMORY.md` (this file).
- **Agent prompt** (the model's rules): `kgqa/agent/AGENTS.md`.
- **Results**: `reports/<run_name>/results.json` — **gitignored**, reproducible.
  Record metrics here, not the files.
- **Trajectories**: rendered into `tmp/` (gitignored — see trap above).
- **Historical/reference docs**: `docs/` (legacy design notes, experiments).
- **Archived RL-era code**: `_archive/rl_{config,configs,prompts}/`
  (gitignored, kept on disk in case RL is revisited).
- **Logs**: `logs/{gte,vllm}_server.log`, `logs/run_*.log`.
- **Models**: `/zhaoshu/llm/Qwen3.5-9B`, `/zhaoshu/llm/Qwen3-Embedding-0.6B`.

---

## RL pipeline session (2026-07-12) — large-scale data + hybrid SFT+GRPO ready

### Full-scale sampling done
- `scripts/sample_full_test.py` sampled **all test pkl (342 scored cases) × 4 = 13588 trajectories** → `data/offline_grpo/full_sample_3k.jsonl` (362M).
- **Full-test baseline** (not curated pilot): S_plan=0.788, S_select=0.736, S_reason=0.630, llm_f1=0.703, gt_hit=0.828. (Lower than pilot 100's F1=0.78 — pilot was an easier subset; full-test is the honest baseline.)
- **Split** (`data/offline_grpo/full3k_split/`): 303 variable+clean → **train 258 cases / 11316 trajectories** · **held-out 45 cases / 1912 trajectories**. Bottleneck: reason 168(55%), plan 101(33%), select 34(11%). Filter: `scripts/filter_gt_suspect.py` + `scripts/split_variable_cases.py` (JSONL input fixed).

### RL trainer validated (tiny scale, 26 train / 6 held-out — directional only)
- **per-stage per-token group-baselined GRPO**: held-out S_reason +0.186 (0.506→0.692), plan protected (+0.010). **Best process reward.** Loss went negative (GRPO reinforcing). Checkpoint saved.
- **origin-stage (per-case origin turn, scalar limer)**: S_reason +0.042, **S_plan -0.083** (training plan-weak cases hurt the plan). Worse than per-stage.
- **Conclusion**: per-stage per-token is the better process reward (saturated stages get ~0 gradient = natural protection). origin-stage's "train the weakness" backfired on plan.
- Speed: ~100-142 s/step (bottleneck = 9B backbone forward, not loss; limer only speeds lm_head). Origin-stage ~25% faster but hurt plan.

### RL infrastructure (all in scripts/, on disk)
- `train_offline_grpo.py`: 3 modes — `--origin-stage` (default, scalar limer, per-case origin), `--per-stage` (per-token, group-baselined), `--single-adv` (original scalar). All backward-compatible. Liger fallback to AutoModelForCausalLM if liger_kernel absent.
- `build_advantage_dataset.py`: `--origin-stage` (default), `--per-stage`, `--single-adv`. Group-baselined (default), `--no-group-baseline` (PRM raw), `--normalize-std`.
- `build_hybrid_dataset.py`: CiSPO hybrid (role=sft seeds + role=grpo). `run_hybrid_zero2.sh` runs it. **Ready for large-scale hybrid SFT+GRPO.**
- **Environment**: liger-kernel 0.8.0 + transformers 5.13.1 installed (qwen3_5 support for offline trainer). vLLM 0.21 (transformers >=4.56 ≠5.0-5.5 → 5.13.1 OK). ms-swift 4.0.2 wants transformers<5.4 (conflict, but offline trainer doesn't use swift).
- **No-merge policy**: eval via vLLM LoRA serving (--enable-lora in start script), don't merge LoRA→base (saves 18GB/disk). Cleaned all old checkpoints + val.pkl + old val-based trajectories.

### Next steps (locked)
1. **build_hybrid_dataset** on full3k_split/train.jsonl (258 cases, SFT seeds + GRPO advantage, CiSPO).
2. **train hybrid** (SFT+GRPO one run, no distribution shift) — from base 9B.
3. **eval 45 held-out** (statistically reliable, vs full-test baseline F1=0.703).
4. If hybrid improves → scale up (more epochs, tune CiSPO curriculum, integrate per-stage into hybrid).

### Uncommitted (scripts/ tracked, changes on disk)
- `scripts/run_cases_ab.py` (M, added --start/--end + --runs).
- `scripts/filter_gt_suspect.py`, `scripts/sample_full_test.py`, `scripts/split_variable_cases.py` (new).
- `scripts/train_offline_grpo.py`, `scripts/build_advantage_dataset.py` (per-stage + origin-stage + group-baselined, on disk, not committed).
- `kgqa/agent/AGENTS.md` committed at 177a69c (content-checklist B).
- `kgqa/agent/tools.py` committed at 177a69c (candidate_attrs).

### Stage-vs-agent gap analysis (2026-07-12) — agent is NOT a worse baseline
Question: stage-pipeline full test was F1≈0.78; agent full-test is 0.703. Is RL polishing a worse baseline?
**Compared on the SAME 342 cases** (`scripts/compare_stage_vs_agent.py`, current eval fuzzy 0.95):
- stage = `reports/cwq_full_test/chunk*/results.json` (3397 rec, ~10/case). agent = `data/offline_grpo/full_sample_3k.jsonl` (13588 rec, ~40/case).
- | stage mean-F1 **0.7654** | agent all **0.7033** | agent valid (excl HTTP-fail) **0.7270** |
- | stage best-F1 0.9401 | **agent best-F1 0.9634** | ← agent ceiling HIGHER |
- | stage gt-hit 0.9649 | **agent gt-hit 0.9883** | ← agent retrieval BETTER |
- **GT-reach buckets**: both-reach 330, stage-only-reach **0**, agent-only-reach 8, neither 4. Agent never loses retrieval stage had.
- **Both-reach answer quality**: gap only F1 +0.011 (agent P −0.023 / R +0.020 — trades precision for recall).
- **Variance**: per-case F1 std agent 0.277 vs stage 0.234. Top-15 loss cases: agent BEST is correct (f1=1.0) in ~13/15, mean dragged by sampling variance.
**Verdict**: gap = sampling variance (temp 0.3) + 3.4% HTTP-failure samples (468 rec, 187 cases), NOT capability. Agent retrieval ≥ stage, ceiling > stage. RL target = sharpen distribution (make correct the mode) — exactly GRPO's job. **Green-lights training.** Decisive confirmatory test if ever needed: greedy single-shot agent eval on the 342 (removes variance).

### Per-stage hybrid (CiSPO on per-stage path) — implemented + training (2026-07-12)
User insight: origin-stage DISCARDS turns after the bottleneck → loses good downstream practice of fully-correct trajectories. Fix = per-stage hybrid (keep ALL turns):
- **SFT seeds** (role=sft, one/case, top1 by llm_f1): adv_plan=adv_select=adv_reason=1.0 → per-stage tokenizer emits uniform +w_stage on EVERY assistant turn → whole good trajectory imitated (plan+select+reason), downstream retained. Scaled by CiSPO λ(t) 1.0→0.2.
- **GRPO** (role=grpo, rest): per-stage signed advantage w_stage × adv_stage (group-baselined S_stage − mean). Saturated stages get ~0 gradient (natural protection — e.g. plan when all samples reach gold).

**Data curation (user's GT-first rule)**: 7/258 train cases had NO good sample (max llm_f1<0.5). Of those, 2 are GT-noise → EXCLUDED:
- WebQTrn-662 (2008 FIFA CWC winner gold="Newton Heath L&YR F.C." = Man Utd's 1878 alias — obscure alias artifact)
- WebQTrn-1679 ("location incl DC+NY" gold="Mid-Atlantic states" vs model "United States" — granularity ambiguity)
Remaining 5 genuinely-hard-but-reachable cases (1436/3087/3412/3769/724) kept as weak GRPO signal; Phase 2 directed-rollout targets.

**Pipeline**: build_train_msgs.py (agent_trajectory→messages + score_case S_*) → build_advantage_dataset --per-stage → build_hybrid_dataset (sft-per-case top1). Clean dataset: `data/offline_grpo/full3k_split/hybrid_per_stage_clean.jsonl` (10895 rec, 256 cases, 1734 SFT / 9161 GRPO).

**Smoke VALIDATED** (4 steps, LoRA saved). **Full 1-epoch run LAUNCHED** (PID 474424, nohup, /tmp/perstage_full.log): max_length=14336 (memory ceiling, 40GB/GPU full — CANNOT raise), batch=1, eff_batch=16, ~160s/step, **~26h/epoch (~594 steps)**, save_steps=200 → eval checkpoints at 200/400/594. Output: checkpoint/perstage_hybrid_256.

**Phase 2 (deferred)**: directed rollout for the 5 hard cases (fix best plan prefix, re-sample downstream ×N via react_loop prefix-resume) to inject positive trajectories. Also: filter_gt_suspect systematic pass on held-out for clean eval.

**vLLM stopped** for training (was OOMing: 37GB/GPU). Restart with --enable-lora for eval after training (no-merge policy).

### Code review fixes (2026-07-12) — corrected model/LoRA + committed trainer
External review caught real issues (all verified against the actual model):
- **Qwen3.5-9B is HYBRID**: layer_types = 3×linear + 1×full → **24 linear-attn + 8 full-attn** layers, vocab **248,320**, hidden 4096, multimodal checkpoint (vision_config present).
- **LoRA targets were wrong**: old list (q/k/v/o + MLP) matched only the 8 full-attn layers + MLP, leaving the **24 linear-attn layers (3/4 of attention) UNADAPTED**. Fixed: now target q/k/v/o (full) + in_proj_qkv/z/b/a + out_proj (linear), rank 32, attention-only (MLP dropped). → 36.2M trainable.
- **Explicit text model**: load `Qwen3_5ForCausalLM` (text branch, 0 vision params — hard-assert via named_parameters). apply_liger_kernel_to_qwen3_5(rms_norm, swiglu; FLCE off). use_cache=False.
- **_diag_trainable**: prints trainable params, asserts only lora_A/B trainable + no vision, confirms DeepSpeed ZeRO enabled (world_size 2).
- **datasets.map int64-to-null fix**: skip records return [0]/[-100] placeholders (consistent dtype) so low max_length doesn't crash the num_proc map.
- **train_offline_grpo.py + train_sft.py were .gitignored** (scratch-era) → NEVER committed. Un-ignored + committed all trainer work.
- **Fast path BLOCKED**: causal-conv1d + flash-linear-attention build FAILS vs torch 2.11+cu130 (CUDA ext compile error). The 24 linear-attn layers run on slow torch fallback — the #1 speed suspect, UNFIXABLE here without torch downgrade (would break vLLM/transformers).
- b_origin truncation (at bottleneck stage) helps little: most b_origin is reason-bottleneck (last stage, no tail to cut).
- batch=2 stays infeasible: ZeRO-2 OOMs (18GB base duplicated), ZeRO-3 slower (gather/scatter > batch benefit at 9B). **batch=1 ZeRO-2 is the only stable+fast config.**

Corrected pipeline VALIDATED end-to-end (4096 smoke: Qwen3_5ForCausalLM 8.95B/0 vision, 36.2M trainable lora-only, ZeRO-2 ws=2, training step runs). Real run: batch=1, ZeRO-2, max_length 12288 (80% data), rank 32 attention-only, ~18h. Length/rank tunable later; LoRA+ (--loraplus-lr-ratio) stub for convergence; directed rollout = Phase 2.

## SEQ offline-GRPO closed loop (2026-08-14) — v2 results + WebQSP cross-check

### 2×2 matrix (CWQ test 100 common cases, repaired = test_v4_repaired.pkl)
| | original pkl | repaired pkl |
|---|---|---|
| base | 0.7796 | 0.8101 |
| LoRA v1 (old-data train) | 0.7876 | 0.7881 |
| LoRA v2 (repaired-data train) | — | **0.8148**, hit 91% |

- v2: 255 steps, 3h27m, data `/tmp/seq_train_v5.jsonl` (4152 traj, adv mean +0.006 / std 0.886),
  ckpt `checkpoint/seq_grpo_v2`, eval `reports/seq_eval_v2_lora_100.json`.
- Robust claims ONLY: data repair +3pp (both models, >> noise) and v2-vs-v1 +2.7pp
  (= training-distribution match). **v2 vs base(repaired) is NOT significant**: paired
  Δ=+0.47pp, t=0.17, sign-test p=0.39, 95% CI [-4.9,+5.9]pp; 100-case protocol MDE=±5.4pp.
- Behavioral drift all toward "stabilization" but within noise: hit 91 vs 89, ≥12-turn
  cases 3 vs 5, mean turns 6.64 vs 6.73.

### WebQSP cross-dataset (test_virtuoso_patched.pkl, first 100, same protocol)
- base F1=0.7492 / hit 89% / turns 4.7 (`reports/seq_eval_webqsp_base_100.json`)
- v2  F1=0.7344 / hit 87% / turns 4.7 (`reports/seq_eval_webqsp_v2_100.json`)
- paired Δ=-1.48pp, t=-0.45, CI [-7.9,+5.0]pp → no catastrophic overfit, **no transfer
  either**; v2 ≈ base-equivalent everywhere within noise.
- Old Aug-12 v1-on-webqsp run (0.7863) is uncontrolled single-seed (its base was
  overwritten) — do not chase.

### Follow-ups decided
1. **3-seed stability test DONE (2026-08-14, reports/seq_eval_stab_{base,v2}_s{11,22,33}_100.json)**:
   stabilization hypothesis REFUTED — per-case cross-seed F1 std base 0.0852 vs v2 0.0857
   (identical), flips 28 vs 28, seed-mean spread base ±2.95pp vs v2 ±3.31pp. Seed-averaged
   paired Δ(v2−base) = **−0.47pp**, CI [−3.8,+2.9]pp — the original single-seed +0.5pp was
   seed luck. v2 ≈ base in every measurable dimension. Offline GRPO at this setup = parity.
2. **Empty answers are a harness bug, not a model property**: 24/600 stab3 runs end empty;
   17/24 are P4-rescuable (answer call present or `ANSWER:` checklist written). With the
   audit's P1-P6 fixes (see below) that's ~1-2pp mean-F1 recovery for BOTH models — bigger
   than anything the LoRA delivered.
3. Oracle headroom: 0.815 vs oracle 0.911 → ~10pp; next lever is data/harness, not more
   GRPO epochs at this setup.
4. Efficiency A/B prepared (post-epoch): group_by_length + `configs/ddp_lora.yaml` +
   batch4/accum2; also **drop the 839/4152 (20%) zero-advantage samples** before tokenize
   (exactly-zero gradient, ~20% free speedup, mathematically neutral).

### v10 penalty design (2026-08-15, user re-alignment): punish redundancy & insufficiency absolutely
User's clarified architecture (matches implementation): trajectory reward = pF-based
(gold probability under current retrieval) → group-centered = advantage CEILING A_exp;
fwd/LOO/G = WITHIN-trajectory allocation weights (scale) only.
**Final credit matrix (v10.2)** — behavior class × trajectory polarity:
| | A_exp>0 | A_exp<0 |
|---|---|---|
| effective hop (Δp>+0.005) | FULL A_exp (吃满) | +min(Δp, 0.15) measured-gain rescue |
| redundant/flat (scale=0 or \|Δp\|≤0.005) | −λ_red 0.08 | −λ_red 0.08 (waste priced uniformly) |
| harmful hop (Δp<−0.005) | −δ·\|Δp\| (no positive ride-along) | A_exp (FULL, not share-diluted) − δ·\|Δp\| |
Plus: insufficient trajectory (pF−p0<0) → A_exp −= δ_abs 0.15 (31%, 117/720 groups
all-insufficient previously escaped); answer axis = F1(pred, gold∩evidence) − group mean.
Cell counts on v7b: pos_eff 11597 / pos_harm 705 / neg_eff 1858 / neg_flat 6968 /
neg_harm 5316 / redundant 6107. Share-dilution removed per user: a harmful hop's
cost must not depend on how many other harmful hops exist (same behavior same credit).
Implementation traps found: single-SG 'credits' are LOG-domain (vF−v0) vs multi-SG
probability-domain — the naive fwd/loo AND-criterion never fires (and the L-gate
0.01 threshold is domain-inconsistent across granularity, inflating single-SG
scale to 1); forward_credits=None for 71% (single-SG) trajectories. Use the
probability gain (always present, domain-consistent) for insufficiency.
**v10.5 THREE-WAY TAXONOMY (user-corrected after mechanism review)**: my
"LOO<0=有害" assignment was WRONG (46% false positives). Correct semantics:
harmful = Δp<−τ AND not gold-bearing (sequential active damage; gold-bearing+Δp<0
= reader-side candidate competition, not retrieval harm); effective = Δp>+τ OR
flat-Δp with LOO>+τ (indispensable — removal would drop); redundant = flat-Δp AND
LOO≤τ (dispensable — removal doesn't hurt; mutual-overlap P(A∪B)<P(A) reads as
removal-raises for BOTH overlapping sgs, Δp separates contributor from free-rider
— Soros: sg1 Δp+0.27 effective, sg2 Δp+0.002/LOO−0.014 redundant). Sign fact
(verified on raw V): c_i = P(full)−P(without i); c<0 ⟺ removal RAISES. v10.5
cell counts: effective-full 10842 / rescue 1838 / harmful 4345 / redundant 15413.
**v10.6 fwd RESCUE (user catch: complementary ≠ redundant)**: Soros sg2
(people.person.religion, ALONE=0.322 > sg1's 0.281) reads Δp≈0.001 ONLY because
sg1's constraint nearly suffices — it is an INDEPENDENT question clause, not
redundancy. effective now also fires on fwd>τ (alone value: independent constraint
present, masked by sibling sufficiency). Redundant requires flat-Δp ∧ LOO≤τ ∧
fwd≤τ (truly no independent value). Reclassified: effective-full 11872 (+1030) /
rescue 2186 (+348) / redundant 14818 (−595 turns rescued).
**v10.7 AMBIGUOUS class (user counter: fwd cannot adjudicate)**: duplicate copies
have alone-values as high as complementary constraints (a copy alone ≈ original
alone) — flat-Δp + high-fwd is MEASUREMENT-INDISTINGUISHABLE between complementary
and redundant (535 sgs, 15% of multi-SG; relay middle hops unaffected — Δp>0 covers
them). fwd removed from the effective class; ambiguous gets DEFAULT MILD POSITIVE
+min(fwd, cap) in both polarities (info-gain logic: real info fetched; punishing
risks teaching avoidance of necessary clauses; full 吃满 unjustified for possible
duplicates). Final taxonomy: harmful = Δp<−τ ∧ no-gold; effective = Δp>τ ∨ LOO>τ;
ambiguous = flat ∧ fwd>τ → mild positive; true-redundant = all low → −λ_red.
**v10.8 RELATION-OVERLAP ADJUDICATOR (resolves the indistinguishability)**: the
ambiguous class splits by relation-set overlap with PRIOR sgs — disjoint relations
= different question clause (complementary, 380/535=71%, audited: Baskett/Stevens/
Watt/Hornacek second clauses) → mild positive +min(fwd,cap); same relations
re-fetched (duplicate copy, 111/535=21%) → −λ_red. Probability measurements cannot
separate complementary from duplicate (a copy alone ≈ original alone); the RETRIEVAL
STRUCTURE (relation identity) can. This closes the hardest open problem of the
taxonomy (user: "最难得就是互补中判定哪一步有效").
Output: tmp/seq_train_v10adv.jsonl. Params AUTO-CALIBRATED (2026-08-15 late): hand-set
values (0.08/0.15/0.15) were 5-10x the differential scale (|A_exp| median 0.013,
group-range median 0.059) — penalties dominated the GRPO signal. Now anchored to
S=median group range of R_exp: λ_red=0.3S, δ_abs=0.5S, cap_eff=1.0S,
δ_harm=0.5S/median|Δp_harm| (flags accept manual override; -1=auto). NOTE (user):
advantage is CASE-level; intra-trajectory factors are secondary scalings — the
multipliers (0.3/0.5/1.0) remain unprincipled pending a validation criterion.
**GOLD VETO on harm detection (trajectory audit finding)**: 46% of Δp/LOO-flagged
harmful sgs are GOLD-BEARING — their probability dip is candidate-competition in
exact-token TF (distractors absorb mass; audited: Soros religion w/ Atheism,
RedSox championship list, ETZ w/ Canada), NOT information harm. Punishing them
would teach avoiding the essential discriminating retrieval. Harm now applies
only to non-gold-bearing sgs (true-noise types: Panama waterways, wrong-entity
subgraphs); gold-bearing sgs fall through to the effective/full-credit branch.
Harmful trigger remains the UNION of Δp<−0.005 and LOO<−0.005 (41% of multi-SG
sgs LOO-negative; LOO catches 285 sgs Δp misses), magnitude = max of the views.

### v9 calibration finding (2026-08-15): pF was NEVER product-compressed — value baseline REJECTED
Two facts from the per-entity IG rework: (1) `gold_logprob` returns MEAN per-token
logprob (offline_vllm.py:192 `sum(lps)/len(lps)`) — the "0.77^20 joint product
compression" story was WRONG for this codebase; measurement was already
length-normalized. Per-entity averaging changed pF only cosmetically (corr old-new
0.906). The residual length-correlation (-0.2) is substantive: multi-entity golds
have genuinely less-predictable tokens (obscure list tails). (2) The deeper problem:
**corr(pF, actual F1) ≈ 0.02-0.05 in both forms** — exact-token teacher-forcing of
the gold string can't see the actor's fuzzy-matched correctness (synonyms/partial
lists), so ANY pF-based value baseline is noise-dominated (trial showed mean a_ans
+0.22, 76% positive = systematic over-credit). Answer axis REVERTED to group-mean
(MC value estimate). Per-entity IG KEPT (entity-uniform weighting is the right
semantics; harmless). Lesson: frozen-model exact-token TF is too strict a reader
to serve as V̂ — a usable value model must score answers the way the scorer does
(fuzzy), which the current IG machinery cannot.

### FINAL VERDICT v8 per-turn (2026-08-15, 3-seed): parity — training side CLOSED
v8 (0.8222/0.8131/0.8030, mean 0.8128, hit 89.0%) vs base 0.8178: Δ−0.50pp CI
[−4.0,+3.0]; vs v7 scalar: +0.78pp CI [−2.6,+4.1] (nominal, noise). std 0.0563,
flips 22 — no stabilization. Empty 0/300. **All three formulations (v2/v7 scalar,
v8 per-turn) = parity with base.** Per-turn credit was mathematically realized
(span-aligned, unit-verified) and data-validated (99% groups have turn-pattern
variance) — the learning still doesn't move. Interpretation: remaining error is
①intent/noise (26%, unlearnable) + ②relation variance whose full stabilization
ceiling (~2-4pp) sits at the 3-seed detection floor; plus LoRA/1-epoch capacity.
**Training lever CLOSED; proven levers = data repair (+3pp) + harness (+3pp).**
v8 details: 5760 traj (720 cases, runaway-rollout salvage), 311 steps 1h17m at
batch1×accum8 (15s/step — FASTER than scalar batch2's 35s; batch2 OOMs from
chunked-logits materialization 2GB/1024-chunk, inherent to per-token weighting).
Post-reset traps: /tmp wiped (use repo tmp/), pip-installed-after-image packages
gone (bitsandbytes), zombie vLLM workers must be force-killed before next GPU job.

### DATA REGRESSION FOUND: literal_and_language_fixed pkl LOST measurement edges (2026-08-17 night)
CPI-case drops in the pathdisc 100-case run (1.00→0.00/0.13) were NOT harness
regressions — they are a DATA VERSION regression. basenh (0.8178 baseline,
2026-08-14) ran on `test_v4_repaired.pkl`: its CPI case carries 814
dated_percentage edges (ents 2010). The current default
`test_literal_and_language_fixed_path_completed.pkl` has 0 (ents 1585 — ~425
numeric/date literal entities dropped in the rebuild). basenh's rendered
`Portugal --cpi_inflation_rate--> [date=1961-08; value=1.55]` came from those
edges via the old post-pass; on current data stat cases are undiscriminable.
⚠ This CORRECTS the earlier note "measurement value edges near-absent
globally" — they were present in v4 and lost in the literal rebuild, not
never-there (the 20-random-case probe missed stat cases: sampling bias).
RESOLVED (user ruling): v4 IS the intended repair — switched the three core
pipeline references to `test_v4_repaired.pkl` (kgqa/core/config.py
DEFAULT_CWQ, kgqa/rl/seq_rollout.py TEST_PKL, scripts/run_seq_eval.py).
v4 + pathdisc 100-case: F1 0.8139, hit 0.90, 3.4s/case (TAG v4_pathdisc_100;
single unseeded run vs basenh 3-seed mean 0.8178 = parity). Per-case vs basenh:
drops 5→2 (BOTH CPI cases recovered to 1.00/Macau — measurement rendering back
via pattern paths), gains 8. Remaining drops: Greenwich (known variance case)
and Rihanna (Saint Michael Parish vs declared Barbados — places_lived parish
level possibly lost in path display, UNEXAMINED).

### PATTERN-PATH ADJUDICATION COMPLETE (2026-08-19 late) — the three-layer semantics
Final self-consistent semantics after the user's hit-logic ruling:
① POOL VISIBILITY (GTE candidates, _reach2_relids rewritten as layered BFS):
budget = TWO NAMED hops, CVT nodes TRANSPARENT (free passage, endpoints on
CVTs penetrated too) — a relation is offered iff reachable within that budget.
② PATTERN PATH (evidence admission, _hop_ok in formatting.py): last hop rides
a selected relation AND SHORTEST-FIRST — if the CENTER has DIRECT selected-
relation edges, longer detour paths through a NAMED mid are NOT pattern paths
('Nordic <--contains_major_portion_of-- Northern Europe --contains--> member'
cut because 'Nordic --contains--> member' exists; the back-edge pair was a
BUG, not noise — user's ruling). Without a direct selected edge
('Düsseldorf --kind_of→' has no 1-hop) the 2-hop detour IS the only pattern
path and stays. Applied to support_paths AND the witness/Option-B channel.
③ CVTs transparent everywhere (Ethiopia bridge retained). Four-case matrix
ALL PASS (tmp/pattern_adjudication.md): Ethiopia 4L gold chain; Nordic 1L
(back-edges gone); Finland 1L (date=value kept, olympics family gone);
Düsseldorf kind_of NON-EMPTY (pool-walk consistency closed). Chain restarted
(9th) on: final adjudication + transparent pool. NOTE the iteration history
this entry closes: out-edge-only → broke reverse hops; CVT-only mid gate →
broke pool-offered relations; plain-2-hop → re-admitted detours; conditional
shortest-first gate is the synthesis that satisfies all rulings.

### GTE POOL SEMANTICS ALIGNED (2026-08-19, user design ruling)
User clarified the ORIGINAL pool design: candidates = 1-hop ∪ one CVT-
transparent extension — a relation behind a NAMED mid-entity was never meant
to be offered. _reach2_relids (tools.py) had implemented plain 2-hop-ANY
(named mids included), so 'Düsseldorf --pertinent_type--> German city
--kind_of--> …' offered kind_of on a center that can never traverse it under
the hop gate — the model selects it and burns the turn on an empty walk.
FIX: 2-hop pass restricted to CVT mediators (pool = 1-hop ∪ CVT-2-hop), plus
the existing CVT-transparent 3rd hop in _seq_pool_relids. Verified: Düsseldorf
candidates now all reachable (kind_of/kinds gone; administrative_parent/
containedby family leads to the Germany→form_of_government gold path);
Ethiopia's CVT-extended office_holder still offered (regression PASS). An
earlier 1-hop-only filter attempt in retrieve_relations was REVERTED (too
narrow — would have dropped CVT-extended candidates). Chain restarted (7th)
on: evidence discipline final + pool semantics fix.

### EVIDENCE DISCIPLINE FINAL (2026-08-19 night) — six rules, all verified
Complete rule set in build_pattern_evidence_triples (formatting.py):
① last-hop-selected path qualification; ② path_edge — every segment of a
qualified path enters evidence (center-connected); ③ HOP GATE — unselected
mid-path hops allowed ONLY through CVT nodes (named-entity detours like
'Nordic <--contains_major_portion_of-- Northern Europe --contains--> members'
rejected — applied to support_paths AND the witness channel of Option-B, the
latter was a leak: the detour re-entered via w_nodes[-2] enumeration); ④ CVT
BRIDGE — explicit construction of center --any-rel--> CVT --selected--> target
(walk expands only step_relations, so role-direction selections like
office_holder need the bridge to reach the center's CVTs — not beam luck);
⑤ bidirectional enumeration (direction-agnostic, reverse gold hops work);
⑥ bare attribute-less CVT tails dropped from renders. Renders under the final
set (tmp/final_discipline_render.md): Ethiopia(test_v4) = ONE line
'Hailemariam Desalegn → Prime minister [from=2012-09-21; jurisdiction=
Ethiopia]'; Nordic = ONE center-rooted contains line; Finland co2 = ONE
date=value record line. DATA FACT: train_v4's Dire Dawa pool LACKS Ethiopia's
governing_officials edge (2306 neighbors, all stats/misc — test_v4 has it);
per user ruling we stay on v4 uniformly — that case is simply unreachable in
train. Data chain restarted (6th) on the final discipline; display review
tmp/final_discipline_render.md.

### ENUMERATION DIRECTION SETTLED: bidirectional, last-hop-selected is THE rule (2026-08-19)
The out-edge-only variant (tried between the Weeze audit and this ruling) broke
reverse gold hops: 'institution --students_graduates--> person' queried from
the person center enumerated to ZERO (Gingrich probe). USER RULING: direction
does not matter — `root --r1--> node1 <--r2-- node2` is as legal as forward;
the ONLY structural constraint is the LAST hop rides a selected relation.
Final evidence discipline (all four now in place): last-hop-selected paths,
center-connected via path segments (path_edge), bidirectional fan-out, no bare
attribute-less CVT tails. Nordic re-probe under bidirectional: 80 triples /
9 clean lines (in-edge flood does NOT return — the flood had arrived via
mid-path segments of unselected relations, now bounded by the path filter).
Chain restarted (5th) on the final discipline.

### OUT-EDGE FAN-OUT DISCIPLINE + BARE-CVT DROP (2026-08-19, user audit of gold-visible failures)
User reviewed tmp/gold_failed_fulltraj.md and ruled the core principle: every
evidence edge must lie on a path FROM the center. Option-B's fan-out had been
enumerating BOTH directions (path node as head OR tail) — in-edge neighbors
('Düsseldorf --contains--> Duisburg', 'Vaasa --country--> Finland', 'Fugloy')
are not on any center-rooted path and flooded the display. FIX:
Option-B enumerates OUT-EDGES ONLY (head == path node); the walk itself stays
undirected (reverse gold hops still arrive via path segments). Also: bare
m./g. tails with no inlined attributes are dropped from rendered lines
(Gingrich dump showed dozens of attribute-less CVT IDs per line); the
candidates pool already excluded CVTs. Verified on the Nordic case: Vaasa/
Fugloy in-edges gone, `Nordic countries --contains--> members` retained, 90
triples (was a flooded list); Ethiopia chain unaffected. Data chain restarted
(4th) on: path_edge + out-edge + bare-CVT drop.

### CENTER-DISCONNECT BUG (2026-08-19, user found in Gingrich trajectory)
User spotted the CENTER absent from every displayed triple (subgraph showed
headless `Newcomb College --students_graduates--> ...` under a Newt Gingrich
center). Root cause: after the last-hop-selected support filter, _make_adder
STILL applied the sel check to each path segment — unselected MID-path edges
were dropped, leaving tail-only edges with no visible link to the center
(chained retrieval: center --unselected--> X --selected--> tails). Fix:
path_edge bypass channel — every segment of a QUALIFIED support path enters
evidence (add(..., path_edge=True)); verified Ethiopia chain now shows
`Ethiopia --rulers--> Haile Selassie --government_positions_held--> ...`.
Impact class: all chained-path retrievals (Gingrich/Ethiopia shape) — likely
a chunk of the flat/still-zero 848 triage. Round-2 rollout restarted on fixed
code (third restart; the pre-fix in-flight data was defective).

### ⭐ v15 WORKS ON THE HARD CASES — 7-parity verdict OVERTURNED (2026-08-19)
User's two calls proved right: (1) the 100-case eval is easy-case-dominated —
evaluating on the 848-case wrong set (SAME harness, offline engine with the
new POLICY=seq_grpo_v15 LoRA sampling) shows base 0.2518 → v15 0.4071
(+15.5pp), 178/848 fully rescued, ZERO newly-broken, improved:worsened
273:74, hit 0.572. (2) Iterated RL enabled: OfflineVLLM now serves LoRA
adapters (lora_modules ctor + chat_batch(model=...) + LoRARequest from
vllm.lora.request), seq_rollout takes POLICY=<name>; seq_train_grpo takes
--init-adapter (round-2 CONTINUES from the v15 LoRA weights).
⚠ EVAL-HYGIENE DECOMPOSITION (user caught the overlap): v15's training cases
intersect the 848 — splitting the +15.5pp: trained-on n=572 Δ+0.181 (memory
risk), **never-trained n=276 Δ+0.103 / 41 rescued — the GENERALIZATION gain is
independently real**. All rollout/eval sets here are TRAIN split (r2 filters
inherit diag2 ← train_v4 pkl; the 848 is an eval-only slice of train). Round-2
launched: v15-policy rollout on the 670 still-wrong (G=6) + 178 rescued keep-
balance (G=4), t0.8, WALK_POOL=16, setsid-detached (a session-cascade SIGTERM
killed one attempt mid-round-1; completion flag logs/r2c_status.txt). Triage
of the 848 (tmp/v15_wrongset_triage.md): rescued 178 / improved 97 / flat 189
/ worsened 74 / still-zero 310 — the still-zero block (37%) likely contains
the GTE-miss retrieval failures training cannot fix.
NOTE the meta-lesson: parity verdicts from easy-dominated slices can mask
real gains — always pair full-slice evals with the hard-subset eval, and
split by trained-on vs never-trained.

### v15 FINAL TRAINING CYCLE (2026-08-19) — SEVENTH consecutive parity
Full pipeline on clean ground: diag-3000 (F1 0.7885, wrong 848 = answer 651 +
retrieval 197) → rollout 6784 traj (848×6 + 424×4, t0.8; spread 67%, empty 7%,
pool MISS-retry healthy) → IG → v0 (tf) → v1.5 train-out (plan-leak fix, N/U
L3) → final 3816 traj / 668 groups (pos:neg 1.29:1, mean +0.720) → per-turn
training 232 steps (--per-stage-chunk 384 after OOM at step 6 on v15's longer
trajectories; the flag needed passthrough added in seq_train_grpo.py).
Eval (GTE+LLM both health-checked first): v15 = 0.8348/0.7742/0.7928, mean
0.8006, hit 0.887 — statistical parity with the base band [0.802-0.812]
(7th: v2/v7/v8/v12crash/v13/v14/v15 across scalar, per-turn, discrete-credit,
targeted+balanced, and now correct-credit+clean-harness+2.9x-data formulations).
s11 0.8348 is the best single seed ever recorded but s22 0.7742 reverts it —
seed variance ±3pp dominates any training effect at this scale. CONCLUSION
(final): the offline-GRPO+LoRA lever on Qwen3.5-9B/1-epoch is CLOSED at this
scale; the compounding levers are data repair, harness fixes, and answer-rule
philosophy (§18-C). Assets that remain for any future attempt: v1.5 credit
(scripts/recompute_advantage_v15.py --train-out), spawn walk-pool, the
diag→rollout→IG→credit pipeline, and the GTE+LLM health-check rule.

### v1.5 CREDIT RULES WIRED INTO THE ROUND-2 PIPELINE (2026-08-18)
User's parallel-session work (specs/credit_assignment_mechanism.md §10.8 +
scripts/recompute_advantage_v15.py) landed: v1.5 cascade — plan-turn leak
FIXED (scale = 1{R_exp>0}×A_exp; v12/v14 plan-turn credit was unreliable,
334 turns negative→nonneg on v14b), L3 novelty re-adjudicated by N (new
DISPLAYED triples ≥0.2) ∧ U (f>0.005) with g as OR-arm — the old relation-
overlap "duplicate" class was a NAMING artifact (100% of old-dup turns
carried new content; zero true copies), failed-trajectory reference
protection (rare, correct). Added --train-out to the script (was audit-only):
writes the same records with turn_advantages replaced by v1.5 values —
smoke-tested on adv_v14b.jsonl (1680 recs). ROUND-2 PIPELINE: diag-3000
(running) → attribution filter → rollout G=6+balance → IG → v0 pass (trajectory
layer: a_exp/a_ans/r_exp into _v0_fields) → recompute_advantage_v15
--train-out (turn layer) → v15 training.

### NEW RULES ON THE 280 WRONG CASES: +15.8pp (2026-08-18 night)
Reran the train-diagnostic wrong set (280 cases, old mean 0.2502) under the
FINAL STABLE CONFIG (offline engine, TEMP 0.3 G=1, TAG train_wrong_newrules):
**new mean 0.4077 (Δ+15.8pp)**, fully rescued (<0.99→≥0.99) 56/280 (20%),
improved>0.05 88 vs worsened 20 (4.4:1), hit 0.45→0.58. The harness/prompt
fixes bite exactly where intended — the hard cases — while the full 100-case
mean stays flat (0.80-0.81) because easy cases dominate it. Single-seed caveat
applies, but 56 full rescues is far beyond noise. Implication for training
data: the wrong-case set has SHRUNK and shifted — any future rollout must
re-diagnose, not reuse the 280.

### §18-C HUMAN-ANSWER PHILOSOPHY + WRAPPED-LINE PARSE FIX (2026-08-18 night, final)
User approved the philosophy rewrite of §18-C (constraints refine a fact set,
never empty it): Step 1 base-facts-first (bindings ARE the answer skeleton);
Step 2 constraint statuses now four — PASS / FAIL / **PARTIAL(order-only)** /
UNKNOWN-keep — singular/tense treated as question-writer phrasing habits =
ORDERING preferences, never removal rules; Step 3 answer = filtered fact set,
never empty; explicit FALLBACK (budget exhausted / retrieval stalled → answer
with current BASE_BINDINGS, a human never blanks unless the fact set itself is
empty). Rationale: v14's "broken" cases were the model applying §18 strictly
against a harness defect (profession blacklist) — the philosophy gives
rule-following models the human fallback path. Checklist template gains
PARTIAL(order).
Found while validating: WRAPPED-LINE PARSE BUG — long entity lists fold across
lines in generation ('entities: A | B\\n | C | D'); _parse_flat kept only the
first line (9 emitted → 4 parsed, Mansfeld F1 0.2 instead of 0.8). Fix:
'|'-leading continuation lines extend the previous list key (unit-tested).
3-seed after both: 0.8085/0.7854/0.8327 (mean 0.8089, hit 0.90; s33 0.8327/
0.93 best single seed on record) — statistical parity with the 0.80-0.81 band,
deterministic gains in emission correctness + philosophy scaffolding for
trained/strict models. FINAL STABLE CONFIG: v4 data + pattern-path discipline
+ rel-mislabel fix + profession unblacklisted + §18 (A bindings / B entity-
level join / C human philosophy / D byte-identical emission) + wrapped-line
parsing.

### BLACKLIST FULL AUDIT + STALE-GATE EXPERIMENT (2026-08-18 evening)
User suspected more answer-edge blacklisting beyond profession — confirmed:
alias/name (6 another-name questions), member/organization/role/appointees (22
what-group/team/org questions) are also answer-bearing. But REMOVING them all
measured −3.5pp (0.8186→0.7834 s11): the hub quartet radiates from title
entities via LEGAL pattern paths (they ARE the answer edge, so the path
discipline cannot stop them) — flooding beats the 30 questions it would serve.
Final blacklist: bookkeeping + common-topic + alias/name + hub quartet;
profession stays removed (deterministic gold-list restoration, Mansfeld).
STALE-GATE (graph-structure anti-iteration, for Arizona's reworded-retrieval
budget exhaustion): unconditional 2-strike −1.6pp; same-centers-conditioned
−2.7pp (3-seed 0.7850 vs 0.8117). REVERTED — the nudge text perturbs retrieval
more than the rare exhaustion costs; the fallback belongs in §18's answer
rules, not the retrieval layer. Measurement lesson: vLLM continuous-batch
nondeterminism makes single-seed deltas ±1.6pp even at fixed LLM_SEED — only
deterministic probes (gold-list restoration) or 3-seed means are decision-
grade. Current clean config 3-seed: 0.8022/0.8150/0.7894 (mean 0.8022, parity
with base3 0.8117 within noise).

### PROFESSION-BLACKLIST BUG (2026-08-18, user found in final-case review)
User spotted `triples: (empty)` with populated candidates in the Mansfeld
trajectory: `_EDGE_NOISY_SHORT` listed "profession" ("holds no answer signal" —
a wrong call: profession IS the answer edge for what-profession questions).
Effect: `person --profession--> Monk` dropped from rendered triples while walk
candidates kept the professions → under strict §18-A (candidates ≠ binding)
the model correctly refused to bind → empty/failed answers. This also explains
part of v14's "broken" cases: base answered from the candidate pool (rule-
violating but lucky), v14 followed §18 strictly and hit the harness defect —
the stricter rule EXPOSED the hidden blacklist bug. Fix: "profession" removed
from _EDGE_NOISY_SHORT; verified Mansfeld now renders
`Martin Luther --profession--> Physician | Theologian | Writer | Monk |
Professor | Priest` (exactly the gold list). Audit lesson: walk candidates
non-empty + triples empty ALWAYS means a rendering-layer filter is eating the
answer edge — check _EDGE_NOISY_SHORT first.

### v14 TRAINING CYCLE + GTE OUTAGE TRIPLE-MISDIAGNOSIS (2026-08-18)
v14 = first full cycle on the new stack (v4 data + path discipline + §18
BASE_BINDINGS rule + spawn walk-pool + train-split-only rollout). Data:
tmp/seq_train_v14final.jsonl — 1300 traj / 229 groups, error-cases (answer-layer
203 + retrieval 77, G=6) balanced with 150 correct cases (G=4), dead groups
filtered, credit mean +0.627 (v12.1 discrete credit, tf-mode exploration).
Training: --per-turn, 79 steps / 31min / loss 0.202 / grad_norm 0.86-1.3,
checkpoint/seq_grpo_v14.
EVAL DRAMA (lesson): first v14 eval read 0.24-0.26 across seeds → suspected the
training, then v13-on-new-harness also 0.22, then BASE also 0.23 → root cause =
**GTE service (:8003) had died** (network drop / GPU cleanup), silently
degrading retrieve_relations. The misdiagnosis chain (LoRA → enable-lora →
GTE) cost three evals. RULE: run BOTH health checks (8000 + 8003, commands at
the top of this file) before believing ANY eval number. Server restart note:
/root/.venv/subgraph is gone post-reset — start_local_qwen35_server.sh needs
VENV= VLLM_BIN=/root/miniconda3/envs/qwen35/bin/vllm override; launch via
tool-managed background (nohup-& dies instantly).
TRUE v14 verdict (GTE healthy, same server as base): v14
0.8063/0.7888/0.7923 (mean 0.7958, hit 0.897) vs base 0.8040/0.8121/0.8189
(mean 0.8117, hit 0.903): Δ −1.59pp, per-seed +0.2/−2.3/−2.7 — nominal
slight-negative, indistinguishable from parity at 3 seeds. SIXTH consecutive
parity-or-worse training result (v2/v7/v8/v12-crash/v13/v14) across scalar,
per-turn, discrete-credit, and now targeted+balanced data formulations.
The training lever on this stack remains unproven; the error-reduction
levers that HAVE worked are data repair, harness fixes, and prompt rules.

### PLAN-TURN IDENTITY LEAK in v12 cascade + credit docs split (2026-08-18)
Static read + synthetic probe (tmp/probe_plan_turn_leak.py) CONFIRMED: in
recompute_advantage_v0.py's v12 cascade the plan/decompose turn never takes its
own branch — the `s` variable leaks from the earlier `for s in sg_order:` g_first
loop, so the plan turn is classified as the LAST subgraph (dp_map lookup hits).
The `scale = 1{r_exp>0}` line is dead code (stats only). Effect: any v12-family
training data (v12/v12.1/v14) mis-credits plan turns — plan inherits the last
sg's class (probe: winner plan got −0.5 inheriting a redundant last sg where
spec says +1.0). ALSO: the redundant-class weight is −0.5·|A_exp| in code
(same as harmful), NOT the −0.1 recorded in the v12 entry above — record
corrected; the class distinction is currently diagnostic-only. NEW DOCS:
specs/credit_assignment_mechanism.md — self-contained external-discussion
writeup of the whole credit mechanism (no code jargon; §10 frames the soft
S_t / N-U-S fusion / structure-conditioned Shapley design space, incl. the
efficiency-axiom vs anti-duplication tension as the first agenda item).
credit_assignment_code.md remains the code-mapping counterpart.

### v1.5 credit rules EVAL on existing rollouts (2026-08-18, same data old-vs-new)
scripts/recompute_advantage_v15.py — turn-layer rules only (trajectory-layer
a_exp/a_ans reused from stored _v0_fields, so deltas are pure rule changes;
v12 replication 94.7% / v14 94.0%). Three deltas: plan-leak fix, L3 N(displayed
-edge novelty)∧U(standalone fwd) with g OR-arm replacing relation-overlap,
failed-traj reference protection (display-based "failed" — the structured
evidence_entities field saturates and NEVER marks failure; display gold_e is
the operative definition). RESULTS (v12: 5760 traj/720 grp; v14: 1300/200):
effective +37%/+42%; partial 1497/217 → 0 (masked-effective at FULL weight);
redundant_dup 672/169 → **0** — the old duplicate class was a RELATION-NAMING
ARTIFACT: not one content-level copy existed (all had ≥20% new edges); 202
rescued (new edges + standalone value, e.g. Nolan Ryan ov=1.0 but N=0.65
f=0.25), 268 → new redundant_irr (new-but-useless noise, kept negative);
harmful ~unchanged; ref protection fires 10+4 turns (0.1-0.3%) — rare but
correct when it fires (Darth Vader portrayed_in_films right-first-hop
protected); plan credit changed on 66-67% of plan turns (802+222 neg→nonneg)
— quantifies the leak's dominance. Credit mass STABLE (|Σ| median
0.50→0.65 / 1.00→1.01) — v12.1 scale calibration survives, no re-anchor
needed. Docs: mechanism.md §10.8 (converged adjudication + numbers).
Artifacts: tmp/v15_audit_{v12,v14}.jsonl (per-turn old/new class + all
signals), tmp/v15_report_{v12,v14}.txt. TRAP: relation-name parsing must
strip reasoning-leak suffixes ("rel - this looks like...") or overlap/StructSim
are polluted; audit tuples are [name, cls, old, new, sig].

### IG/scoring perf + server numeric floor (2026-09-01, user-approved batch fix)
CONTEXT: 4-CPU cgroup quota (nproc lies: 128 host view, cpu.max=4) shared by
client scripts AND the :8000 vLLM server AND GTE — CPU is the scarce pool.
Codex perf directives partially wrong: /v1/chat/completions/batch IS a native
true-batch route in this vLLM 0.25.1 (N convs → one engine submission,
merge_async_iterators); /v1/completions accepts prompt as list[str] (one
indexed choice each, full prompt_logprobs — live-verified); max_tokens=0 is
the supported prefill-only branch (bit-identical logprobs to =1); logprobs=0
returns only the actual token (by-id lookup unchanged, payload halves).
prompt_logprobs=0→1 "fix" REJECTED (0 is deterministic single-entry; =1 makes
next(iter()) order-dependent). IMPLEMENTED (scripts/informat_tf_calib.py):
prepare() tokenize-once (was 2-3 full re-encodes/job — dominant client CPU),
score_batch() prompt-array POSTs chunk=64 w/ retry+per-prompt fallback, span
semantics replicated EXACTLY (t1 prefix re-encode count — do NOT "fix" to
pure offsets: changes values); pair_loo.py switched to the same path;
http_batch._achat retry bug fixed (except-block returned early — retries
never ran). MEASURED (60 real jobs): NO wall speedup (480→510 ms/job) —
with 6 concurrent workers the engine is ALREADY prefill-compute-bound
(~12K tok/s @ max_num_batched_tokens=2048 default for A100 OpenAI-server —
server has no flag set; raise to 8192 on next restart = the real lever).
Batch win is CPU headroom + robustness, not throughput at this shape.
**NUMERIC FLOOR FINDING (methodology-relevant, pre-existing)**: server
prompt_logprobs depend on co-batch composition — solo vs accompanied vs
different partners give deterministic-but-different values; on real spans
max |Δln|=0.089, max |Δp|=0.036 >> dI threshold TH=0.005. Old 6-worker
production runs carry the same variance (demonstrated). Borderline dI
verdicts in informat/pair_loo outputs are mode-lottery — add a guard band
or re-score critical calls before trusting |dI| near TH.

### TRAP: 16384-token server + echo scoring = OOM engine death (2026-09-01)
User restarted :8000 with --max-num-batched-tokens 16384 (generation smoke
passed, cold 4.8K-token prompt ~10.4K tok/s). The 60-job scoring benchmark
KILLED it: torch.OutOfMemoryError allocating 3.91 GiB (= 4096 tokens ×
248,320 vocab × fp32 — the prompt_logprobs full-vocab logits buffer; the
scheduler chunks prefill within the 16384 budget). GPU1 had only 2.6GB free:
a FOREIGN host-side process (host pid 1531941, 2314 MiB, outside container
PID namespace — untouchable) permanently eats GPU1 headroom. Spike math:
≈0.93 GiB per 1024 step-tokens → 2048=1.96GB (proven safe at util 0.82 with
the squatter), 4096=3.91GB (fatal), 8192=7.86GB (not scoring-safe on this
box). GENERATION never hits this (samples only last-token logits/seq —
16384 is fine for rollout-only phases). RULE: match --max-num-batched-tokens
to the workload — 16384 for pure rollout (48×3 etc.), 2048 whenever
echo/prompt_logprobs scoring will run against the server (or use the offline
engine path, already tuned util=0.75 + 2048). After any engine death: verify
BOTH :8000 liveness AND engine health (a lingering APIServer can look alive
while EngineCore is dead).
SOURCE-LEVEL CONFIRMATION (vllm 0.25.1, gpu_model_runner.py:5583-5585
`_get_prompt_logprobs_dict`): prompt logprobs run a SECOND per-request
projection — `hidden_states[offset:offset+num_logits]` → `compute_logits`
(bf16 [rows,248K] GEMM output) → `sampler.compute_logprobs` =
`log_softmax(dtype=torch.float32)` (fp32 [rows,248K]). The 3.91GiB OOM ask
= 4096 rows × vocab × 4B (fp32 softmax output); bf16 GEMM output is alive
alongside → true peak ≈ 1.42MB per scored row. Slicing is PER-REQUEST
(rows = that request's chunk this step ≤ budget), so the spike is capped by
min(prompt len, max_num_batched_tokens) — shortening prompts does NOT fix
memory unless < ~2K tokens; the only live knob is the batched-tokens budget.
`logprob_token_ids` (sampling_params.py:278) acts on the gather AFTER the
full softmax — cannot reduce the spike. num_prompt_logprobs k only sizes
the gather → False cheap, 0/1/5 identical memory (Codex's discriminating
experiment unnecessary — answered by source). CUSTOM-ENDPOINT PATCH POINT:
slice only the tail-K span positions at :5583 → lm_head+softmax drop from
num_logits rows to K (K=30 ≈ 40MB) while prefill keeps full 16K throughput
— would let one 16384 config serve rollout AND scoring.
FOLLOW-UP (same day): custom logits processors CANNOT fix this — they hook
AFTER materialization (sampler.py:80-101, apply_logits_processors runs after
compute_logprobs + fp32 convert) and the prompt-logprobs path bypasses
processors entirely. BUT the trail exposed a purpose-built route:
`/generative_scoring` (entrypoints/generate/generative_scoring/, mounted via
api_server.py register_generate_api_routers) — sends query+item with
max_tokens=1 + logprob_token_ids=labels, reads FULL-VOCAB-normalized label
probs (apply_softmax=False = exp(log_softmax over 248K), i.e. exact
teacher-forcing semantics; apply_softmax=True = label-only renorm — do NOT
use). Memory-safe by construction (projects last position only, [1,vocab] ≈
1MB) and tiny responses → works on a 16384 server. Multi-token gold spans =
K chained requests (item=evidence+gold[:i], labels=[gold_i]) with prefix
caching making prefill incremental; query/items accept token IDs (BPE-exact
span control). UNVERIFIED (server was down): route liveness under `vllm
serve`, numeric agreement vs echo path (expect co-batch-floor-level match),
batch throughput vs K-requests-per-span overhead. If it validates, the
2048-scoring downgrade AND the :5583 patch both become unnecessary.
VALIDATED (2026-09-01 evening, new :8000 @ util 0.82 + max-num-batched-tokens
8192): route live; response = data[i].score = exp(logprob) of FIRST label
token (apply_softmax=False); same-server echo-vs-chain agreement on a
1483-token prompt: max|Δln| = 0.000000 (bit-identical, K=6); stress: 10,342-
token prompt chain-scored on the 8192 server in 0.9s (94 ms/span-token;
1.5K-prompt chain 37 ms/token), server healthy after — where echo would
spike ~7.9GB and die. VERDICT: chain scoring via /generative_scoring
REPLACES echo scoring — one high-budget server serves rollout AND scoring;
remaining work is client-side only (informat score_batch → K chain requests
per span, token-id query/item). NOTE: cross-server/cross-config IG values
drift (old-2048 vs new-8192 individual span tokens differ up to ~0.3 ln /
~0.02 p — same numeric-floor family); dI comparisons must stay
within-server-run.
CLIENT SHIPPED (same evening): informat_tf_calib.score_batch rewritten to
the chain path (per span-token POST /generative_scoring, query=ids[:i] as
token list, items=[[]], label=[ids[i]], apply_softmax=False, value=mean
ln(score), -9999.0 floor; ThreadPool workers=6 default, 2×retry). Old echo
batch kept as score_batch_echo (memory-unsafe >2048 budget — docstring
warning). pair_loo.py switched. VALIDATION: workers=1 vs sequential echo
max|Δln|=0.000000 (bit-identical); workers=6 max|Δln|=0.037 (co-batch floor,
same class as the old 6-worker echo path — no regression); 18 prompts
(12 × ~9K tokens) in 3.8s at workers=6 vs old echo ~293-480 ms/job.
INCIDENT (trap re-confirmed): a smoke using the ECHO path as reference on
~9-10K-token info_prompts OOM-killed the 8192 server (3.42GiB ask, ~3.7K
rows) — echo scoring of multi-K prompts dies at ANY budget >2048. Server
restored with the identical config (0.82 / 8192 / hermes). RULE: never use
echo/score()/score_batch_echo on long prompts against a high-budget server;
chain path is the default and is budget-immune. PARKED (user): offline
engine rollout for speed, revisit later.

### ALL-ZERO GROUPS = spawn-pool cache bug, not model failure (2026-08-17 night)
User asked whether the 145 all-zero rollout groups were harness or model.
Attribution: 71% were EMPTY-ANSWER trajectories, 99% of those hit "walk reached
nothing". Root cause = the spawn walk-pool's worker-side case cache: between a
case's rounds, hundreds of first-time cases flood the pool, the 256-cap
`clear()` evicts everything, and the case's next walk lands on a cacheless
worker → `_W_CASE_CACHE.get → None → return {}` → retrieve_subgraph emits
"walk reached nothing" → model declares facts failed → empty answer. Static
probe (20 sequential calls) NEVER misses — only churn reproduces it. FIX:
MISS-sentinel protocol (worker returns "MISS"; caller reships the task once
WITH the case arrays; verified 30/30 full under 600-case churn). Both v14
rollouts (error 1680 + ok 600) were polluted by the bug and are being rerun
with the fix (TAG rollout_v14b). Lesson: any worker-side cache keyed by case
must survive churn or use miss-retry; also diagnosing "model gave up" needs
the empty-answer vs wrong-answer split first (30 list-gold noise + 12 true
wrong in the polluted set; the 103 empty were the artifact).

### DATA-LEAK CORRECTION: rollout must use TRAIN split (2026-08-17, user caught it)
The first v14 rollout launch filtered error cases from the test-split full
eval — training on the test set. Killed immediately, zero trajectories trained.
Correct flow (now running): ① SPLIT=train_v4 diagnostic pass (train_v4_
repaired.pkl, 1000 cases × 1 sample TEMP 0.3 — same offline engine, the
diagnostic IS a rollout with G=1) → ② attribute wrong cases (answer-layer vs
retrieval by gold-in-evidence) → ③ CASE_FILTER + SPLIT=train_v4 real rollout
(G=6 TEMP 0.8, answer-layer-weighted sample). seq_rollout PKLS already carry
the train_v4 entry. NOTE for evaluation hygiene: the eval 100-case slice and
full 3397 are test-split — never let rollout case ids intersect them.

### FULL TEST 3397: seq agent BEATS stage pipeline (2026-08-17)
Offline full eval (seq_rollout engine, N=1 TEMP 0.3 CASE_BATCH 200, 4.7s/case,
16069s wall) on test_v4_repaired vs the stage-pipeline chunks
(reports/cwq_full_test/chunk0-6, 3397 recs — decomposition→select→reason full
traj). Aligned n=3291: stage F1 0.7458 / hit 0.7906 vs **seq agent (v4 +
path-discipline + §18 rule) F1 0.7692 / hit 0.8335** (+2.3pp F1, +4.3pp hit);
per-case agent wins 600 / stage wins 465 / tie 2226. Agent over ALL 3397:
F1 0.7524 / hit 0.8154 (the 106 cases the chunks skipped are hard ones, agent
mean ≈0.23 there). Report: reports/full_v4_offline.json (85MB, trajectories
included). Single-seed full-eval attribution: wrong 1091 = answer-layer 881
(gold reached evidence) + retrieval-layer 210 — answer layer is 81% of errors
at scale, matching the 100-case finding.

### OFFLINE ROLLOUT THROUGHPUT findings (2026-08-17, full-eval prep)
Profiled the "slow walk" suspicion: single-case walk is 83ms warm (user's SAPS
memory correct). The 1-3s Stage-5 prints in rollout logs are QUEUE POSITION
under the GIL (16 gathered coroutines enter the sync CPU walk; the Nth one's
timer includes the N×0.1s wait), not compute. True bottleneck of the offline
full eval = LLM decode throughput: ~9 rounds × ~800 tok/case ≈ 24M tokens —
9B TP2 physical limit. HTTP vs offline are the SAME 3.07-3.4s/case for this
reason (engine swap changes nothing); prefix caching only helps prefill.
TRAPS: ① WALK_POOL (fork ProcessPool in seq_tools._run_walk_one_step, default
OFF) CRASHES vLLM — forked children corrupt EngineCore/WorkerProc
initialization ("WorkerProc initialization failed"). Do not enable while any
vLLM engine lives in-process. Code kept, env-gated WALK_POOL=0. ② Long-tail
starvation (user observation): stage-based batching drains to 1 active case →
LLM batches of ONE prompt (112 tok/s) for its last rounds ≈ +150s/stage ≈ 25%
wallclock waste. FIX (planned, for the rollout refactor): replace stage
boundaries with a water-level work pool — whenever active < threshold (e.g.
32), admit pending cases into the same turn-synchronous round (their round-1
prompts merge into the batch); done cases leave. Keeps vLLM decode at full
batch across case lifetimes. ③ vLLM engine load ≈ 87s — don't kill runs in
warmup (a hasty kill left EngineCore/Worker zombies holding 38GB; force-kill
by pid). ④ /tmp/attr.py shadowed the `attr` (attrs) module for scripts run from
/tmp — python's sys.path[0] picks it up inside aiohttp's import chain and
EXECUTES the wrong file. Never leave scratch scripts with stdlib/dep-like names
in the script's directory.

### PATTERN-PATH DISCIPLINE RESTORED (2026-08-17 evening, user ruling — the big one)
User read the China dump (tmp/china_expansion_dump.md) and ruled: evidence lives
ONLY on paths whose LAST hop rides a selected relation — mid-path relations may
chain freely, but nothing off such paths belongs (job records under a trade
query, CO₂ stats, hub adjacency). Investigation found the discipline was broken
in THREE stacked layers: ① the support-path filter required EVERY hop selected
(`all(r in _sel_ids)`) — this discarded exactly the chained paths
(Ethiopia --governing_officials--> CVT --office_holder--> holder), emptied
support_paths; ② the coverage hole was papered over by the CVT auto-penetration
post-pass (any-adjacency expansion → China 13k edges); ③ sibling CVT expansion
was dead (parent edges of non-selected relations rejected → sibling=0
everywhere). Fixes (formatting.py): support filter = LAST hop selected;
_expand_sibling_cvts parent edges allowed when the sibling CVT itself touches a
selected relation (cvt_attr channel); post-pass DELETED entirely. Verified
probes: Ethiopia `Hailemariam → Prime minister [from=2012-09-21]` intact via
pure path+sibling (57 triples); China = trade edges only, no job records, no
stats (13641 → 760); Ohio position records with dates (12 lines); Libya PM
holders with Abdullah [from=2014-06-09]. GDP-type caveat stands: measurement
value/date edges are near-absent from the data pool globally (20 random cases:
6 numeric + 18 date CVT edges total) — stat questions stay undiscriminable
until the data pipeline includes them (user decision pending).
§18 also rewritten (codex-review framework, user-corrected): BASE_BINDINGS /
CONSTRAINT_CHECK (PASS/FAIL/UNKNOWN per requirement, verified-first; `the`/
singular alone ≠ top-1; comparative constraints need full coverage or explicit
incumbent) / FINAL_BINDINGS byte-identical to the entities arg; A: candidates is
a NAVIGATION INDEX, never a binding; B: intersection of DECLARED sets at answer
time (declarations stay model-submitted — system does entity-level join only).
seq_react_loop parse-nudge keywords extended for the new field names; both
worked examples updated.
3-seed 6-case after path discipline + new §18 (TAG pathdisc): F1
0.548/0.586/0.808, hit 17/18 (vs hubfix 0.40/0.57/0.42, hit 12/18). Per case:
Greenwich 0.22/0.25/0.67 → 1.00/1.00/0.67 (§18-A cured the copy-the-pool
declarations), Ohio → 1.00×3, museum hit 0/1/0 → 1/1/1 (s2=1.00), UTC s2 →
1.00. Remaining: Libya 0.18×3 (conservative UNKNOWN→keep-all by design —
training-layer target), UTC s0/s1 (dual-anchor plan rule rolled back — same),
Greenwich s2 0.67 + museum s0/s1 partial (unexamined). No case-shaped prompt
rules anywhere in this configuration.

### HUB-RADIATION fix: post-pass anchored to CENTER only (2026-08-17, user path-discipline ruling)
User pointed out the original repo logic: a hub on a path contributes ONLY its
pattern-relevant relations, never all adjacency. The CVT auto-penetration
post-pass (Ethiopia fix) violated this — it expanded adjacent CVTs for EVERY
named entity in the evidence, including title hubs ('Governor', 'Senator',
degree 10k+) that merely surfaced via CVT attr edges. Measured on the Ohio f2
probe: full-_named = 11552 triples (1456 Governor-hub edges alone); center-only
= 744 (−94%); no-postpass = 234. Kasich's own position edges survive in all
variants. Fix: `_named = {anchor_name} if anchor_name else set()` in
build_pattern_evidence_triples (formatting.py, the post-pass). Verified
Ethiopia still renders `Hailemariam Desalegn → Prime minister
[from=2012-09-21; jurisdiction=Ethiopia]` (230 triples, no radiation) — the
pass's original purpose (center CVT reachability) is intact. 6-case × 3-seed
after fix: 0.40/0.57/0.42 — but per-case attribution shows the dips are NOT
causal: hubfix Greenwich s0/s1 crash = the model copied the sg2 CANDIDATES
POOL (8 countries) into the declaration while relfix s0 copied the true
triples bindings (2 countries) with IDENTICAL sg2 displays — Greenwich's
known declaration-discipline variance; museum s1 improved 0.15→1.00; Ohio
s2 1.00→0.67. The 6-case set is all pathological cases; harness-fix net
effect needs the 100-case run vs basenh 3-seed baseline (0.8178) to measure.
Both fixes (rel-mislabel + hub-radiation) are deterministic correctness fixes
— keep them regardless of small-sample noise.

### REL-MISLABEL BUG found+fixed in _render_records (2026-08-17, Ohio diagnosis)
User asked why Ohio f2 showed Kasich/Meigs position CVTs as bare MIDs with no
dates. Root cause (NOT a penetration gap): `_render_records`'s fallback branch
appended `(h, sr, t)` where `sr` was a LEAKED variable from the previous loop —
every named→CVT holderless edge (education/party/guest_roles/headquarters/…)
got mislabeled with the short rel of the LAST triple processed (here:
government_positions_held). Meigs' 13 "position" tails were actually his
education/party/spouse/guest-roles CVTs mislabeled; Kasich's two "position"
tails were education+party. One-line fix: `fallback.append((h, _short_rel(r),
t))`. Verified: after fix all edges carry true rels (`Meigs --guest_roles-->`,
`Kasich --education-->`, `Super Duper --headquarters--> m.0zft690 [country=USA]`)
and Kasich's real position records DO render with from/to dates (render layer
was never broken — feeding it from-edges yields `Kasich → United States
Senator [from=1979-01-03]`). ALSO: source-data cross-contamination in this case
— m.0bfmhy4 (US-Senator position CVT) hangs under BOTH Kasich and Meigs in the
pool; walk paths are legal; rendering was faithful to (noisy) pool data.
Affects ALL cases' fallback edges (display semantics), fix is in
seq_tools.py:791. Repro recipe: build_context(Ohio sample) →
`_run_walk_one_step(ctx, kasich_idx, [294,309], 'f2')` → inspect pe.triples
(correct) vs `_render_records` output (mislabeled pre-fix).
3-seed after fix (CONFOUNDED: §4.2/§18-example prompt patches had just been
reverted per user ruling — relfix run = reverted prompt + rel fix; no clean
"reverted prompt only" baseline exists): Ohio 1.00/1.00/0.67→1.00×3 ✓,
Greenwich 0.67/0.29/0.67→1.00/1.00/0.67 ✓ (net rel-fix gains); UTC
0.67/0.67/1.00→0×3 (§4.2 rollback cost — dual-anchor plan gone), museum
1.00×3→0/0.15/0 and Libya 1/3→0/3 (§18-example rollback cost — gold still
retrieved in museum f1 bindings, discrimination behavior regressed). Reading:
the prompt-example patches were TRANSPLANTING ability (model copied the
discrimination pattern); with them reverted the failure modes return — the
training layer's job. rel fix = pure harness correctness, keep it.

### Answer-layer soft-discriminator + constraint-anchor plan rule (2026-08-16, 6-case × 3-seed A/B)
Two SEQ_AGENTS.md edits (user-directed): ① §18 answer rule rewritten as ACTIVE
SCAN — structural join first, then scan DISPLAYED attributes for the question's
requirement (from/to dates, incumbent markers, quantities, type labels); found →
narrow citing the edge; NOT found → `DISCRIMINATOR: none` → return ALL bindings
(a missing attribute is not evidence against a candidate). No forced declaration.
② §4.2 new rule — every entity listed in `entities` must be USED by some fact;
attribute-like named entities (time zone, currency) anchor their OWN subgraph and
share the variable for a structural join (UTC−05:00 example written into prompt).
A/B on the 6 answer-layer error cases, base Qwen3.5-9B, t0.3, LLM_SEED 0/1/2:
NEW F1 0.753/0.689/0.889 (hit 18/18) vs OLD 0.753/0.756/0.411 (2 misses at s2 —
UTC plan failure + museum enumeration, exactly the two modes the rules target).
UTC FIXED 3/3: dual-anchor plan (sg1 DR→?region, sg2 UTC−05:00→?region); s2 =
perfect join (sg1 5 candidates ∩ sg2 [Greater Antilles] → 1.0). Was one-hop plan
that never used the constraint entity. Libya: discrimination now REACHABLE but
not dominant — 1/3 seed = 1.0 (sole expanded-holder salience), 2/3 still
enumerate with `none` despite displayed from=2014-06-09 → prompt ceiling reached;
making discrimination the MODE = answer-axis training. museum 3/3 = 1.0 (old
1/1/0). Greenwich high-variance under both prompts (0.29–0.67), untouched mode.
greedy single-shot is NOT an accept/reject gate (softdisc_t0 0.364 = path noise).
Run: `CASE_IDS=<6 ids> TAG=x N_CASES=0 /root/miniconda3/envs/qwen35/bin/python
scripts/run_seq_eval.py` (KGQA_LLM_TEMPERATURE=0 for greedy; LLM_SEED to seed).
Case ids: WebQTest-590_6aad…, WebQTrn-2209_c137…, WebQTrn-3100_143c…,
WebQTest-12_68d7…, WebQTest-361_e245…, WebQTrn-2664_471b… (full ids in
reports/seq_eval_softdisc_t03_0.json). TRAP: post-reset /opt/conda base python
has NO aiohttp — use `/root/miniconda3/envs/qwen35/bin/python` (3.12), do not
pip-install into base.

FOLLOW-UP (same day, user ruling): reasoning→emission audit showed Greenwich s0
computed the correct join {Sierra Leone} in thinking but emitted the LAST
subgraph's full binding [SL | UK] — §8 defined checkpoints as "bindings FROM
THIS FACT", so the copy chain (fact→checkpoint→CANDIDATES→ANSWER) had no step
executing §16's intersection. A §8 intersection rule was tried (join v1):
Greenwich fixed (1.00/0.67/1.00) BUT UTC regressed 0/1/0 — the model
hallucinated declarations into agreement at the checkpoint and the join
laundered the noise into confident wrong answers (means 0.380/0.808/0.475).
USER RULING: STOP iterating checkpoint/patch rules — case-shaped prompt rules
(UTC dual-anchor example copied verbatim by the model, Libya PM example) are
overfit; the retrieval workflow itself works. Direction = (a) harness-side
deterministic fixes (e.g. Ohio CVT-penetration gap), (b) ONE answer
EPISTEMOLOGY replacing procedural rules, (c) training for the rest. ALL THREE
prompt patches REVERTED (§4.2 constraint-entity rule, §8 join paragraph, §18
CANDIDATES line + Libya example); prompt now = pre-session + §18 scan principle
only. Libya root cause (from reasoning dumps): model SEES from=2014-06-09,
dismisses it via invented standards ("question lacks literal 'current'",
"wants dates on EVERY candidate") — implicit-constraint reading failure, 1/3
seeds read it correctly; training target. Ohio: dates NOT displayed (bare MID
position CVTs while other senators' CVTs got attribute inlining — penetration
gap). UTC residual: "globe region" type not displayed + gold ambiguity.

### v12.1 BOTH AXES gated z-score + the v7/v8 parity ROOT CAUSE (2026-08-16)
Magnitude audit (user hypothesis, CONFIRMED): v8 training data |Σturn_adv| median
= 0.0000 (exploration turns median literally zero) — the parity results trained
on ~zero-magnitude advantages → ~zero gradients. Root cause chain complete:
multiplicative collapse × tiny magnitudes. Fix: gated z-score (clip ±1) on BOTH
axes — exploration (alive: max gain>0.05, 62% of groups) and ANSWER (alive: F1
std>0.1, 44% — 56% of groups had saturated all-correct answers where plain
centering ≈0). v12.1 result: trajectory |Σ| median 0.49 / q90 4.5, answer q90
1.0 — signal scale up ~100× for the median sample. Niger winner final:
[1.0×6 effective, 0.5×2 partial (sg2 fwd-veto reclassified), answer 0.577].
WARNING for first v12 training: lr 1e-5 was tuned at the old scale — sweep
3e-6..3e-5, watch grad_norm (old healthy band 0.3-0.8 will shift up).

### v12 FINAL CREDIT ARCHITECTURE (2026-08-16, user-driven convergence)
Trajectory: ALIVE groups (max gain>0.05) → A_exp = clip(z-score, ±1) — winner's
effective turns take the FULL ±1.0 (user: 正确探索给满优势); DEAD groups not
amplified (noise regime) + δ_abs insufficiency. Turn-level THREE-LAYER VALIDITY
(deterministic-first, user spec): (1) STRUCTURE: removal breaks anchor→gold
connectivity OR lineage (later retrieval centers from this sg) → effective;
(2) PROBABILITY: LOO>τ → effective; Δp<−τ∧no-gold → harmful; (3) NOVELTY: new
relations + gain → partial(0.5); same-rel re-fetch or flat → redundant.
CREDIT: positive traj — effective +1.0·A_exp(吃满), partial +0.5·A_exp, redundant
−0.1·|A_exp|, harmful −0.5·|A_exp|; negative traj — effective/partial 0 (behavior
encouraged via OTHER positive trajectories' same behavior: cross-trajectory
aggregation), redundant & harmful eat the FULL negative. Answer axis independent.
Anchor-case verification: Niger winner [1.0,1.0,−0.5...], Soros [sg1 0.593 吃满,
sg2-complementary 0.296 partial]. GPT-input history: additive process advantage
(r1) → retracted for purity (r2) → user's discrete validity weights won (collapse
+ cross-traj aggregation rationale); gated z-score added after user's
"0.089-should-be-amplified" challenge. Implementation: recompute_advantage_v0.py
(structural tests + gated z + v12 credit block). Data: tmp/seq_train_v12adv.jsonl
(mean +0.59, |A| median 0.232).

### Evidence-pipeline discipline restoration (2026-08-15 evening, user-led audit)
From the trajectory-dump manual review (Favreau case) three display-layer defects
were found and fixed CLASS-BASED (name-list patch rolled back per user — 打地鼠):
1. **SCHEMA EDGE LEAK** (Option-B bug): the walk blacklist (type./common./freebase.
   prefixes, k_queue) never applied to build_pattern_evidence_triples' node_edges —
   ontology edges flooded in via type-label hub nodes ('Film character' deg-23 in the
   audited case). Fixed: _is_schema_rel class filter at the _add choke point.
2. **OFF-PATTERN EDGE LEAK** (the SAPS→SEQ regression the user identified): evidence
   had drifted to raw-triple accumulation — non-selected relations traversed en route
   (support-path intermediates, named-leaf extensions like Denver--portrayed-->Film
   off any center path) entered evidence. The original SAPS rendering was pattern-
   path-strict. Fixed: build_pattern_evidence_triples(selected_rel_ids=...) — edge ∈
   evidence ⟺ relation selected ∨ cvt_attr of on-path CVT; support paths must be
   pure selected-rel chains; Option-B enumeration gated on witness-last-hop ∈
   selected. Caller (_run_walk_one_step) now passes rel_idxs (it always had them).
3. Root data fact: CVT/type nodes named by TYPE LABELS ('Portrayal'/'Film'/'Film
   character'/'Topic') are IN the RoG pkl text_entity_list (upstream dataset
   construction) — unfixable at data level; the CVT-name-detection gap remains a
   known limitation (their role attrs reveal only when the relation is selected).
Smoke (30-case): 0.7564 vs prior band 0.81-0.84 — paired analysis: 26/30 tie, 3
drops of which 2 are documented variance cases (UTC-region, Brad-Stevens), 1 answer-
turn over-inclusion (opposite of starvation) → no regression confirmed; multi-seed
rebase remains the definitive check.

### CONTAINER RESET TRAP (2026-08-15 morning): /tmp wiped, NFS survived
Overnight container reset cleared container-local /tmp — lost: v5/v6adv/v7adv
training jsonls, rollout_v7_newharness.json, case filters, all /tmp run scripts.
SURVIVED (NFS): checkpoints (seq_grpo_v7 adapter!), reports/, code changes,
SESSION_MEMORY, repo tmp/. **Rule: pipeline artifacts (rollout/IG/adv jsonls) go
to /zhaoshu/subgraph/tmp/, NEVER container /tmp.** Also: `pkill -f "vllm serve"`
inside a compound command kills the invoking shell (pattern matches own cmdline) —
run pkill standalone. Rebuild pipeline: GTE → full train_v4 rollout (no filter —
v5 stats lost) → IG → v0 recompute → v8 per-turn training; script logic recorded
in this entry, artifacts → tmp/{rollout_v7b.json, seq_train_v7b_ig.jsonl,
seq_train_v7badv.jsonl}.

### v7 eval verdict (2026-08-14, 3-seed): parity again — per-turn credit NOT realized
v7 (0.8164/0.7913/0.8074, mean 0.8050, hit 89.3%) vs base post-B (mean 0.8178):
paired Δ −1.28pp CI [−3.9,+1.4] = noise. Cross-seed std 0.0540 vs base 0.0457,
flips 17 vs 19 — **no stabilization**. Empty 0/300. Data-side metrics were all green
(①69% ②89%), so the credit redesign improved the ADVANTAGE DATA but training still
shows parity. Root cause known and documented: the scalar-sum tokenize collapses
turn_advantages into ONE number (Σa_t) — **per-turn credit never reached the gradient**.
v7 tested "better scalar advantage", not per-turn credit. The decisive untested
experiment is the per-stage/per-turn loss path (~2.5x slower/step, ~3.5h/run) — or
accept the conclusion that offline-GRPO+LoRA at this scale is parity and the proven
levers are data repair (+3pp) and harness (+3pp).

### v7 cycle: new-harness rollout → IG → v0-adv → training (2026-08-14)
Rollout: 364 signal-cases (v5 group stats filter) × 8 = 2912 traj in **2.2h** (44% of
v5-equiv; THINK 512 / ROUNDS 12 / prefix caching); 337/364 groups have reward spread
(92.6% vs v5's 77%). Structured fields recorded: evidence_entities (ctx-level, full
incl. hidden leaves/expansions) + pred_entities (post-expansion) — passthrough added
to run_real output. IG pass: 199s (0.07s/traj).
**KEY FINDING — recall saturates on the new harness**: display-mode R_exp gave ①flip
only 20% because WHOLE GROUPS hit evidence-recall=1.0 (Option B enumeration makes gold
visible to every member) → a_exp=0 for all. The discriminating evidence-quality signal
is the TF gain (pF−p0; 32.6% of high-F1 traj have pF<0.2). tf-mode v7: **①翻正 69%
(best), ②压低 89%, zero-adv 1%**. Structured fields remain authoritative for G
(per-sg gold attribution) + answer-axis F1.
Training: v7adv launched (2884 kept, 144 steps, 33.5s/it, ETA ~1.4h) → checkpoint/seq_grpo_v7.

### Training speed smoke PASSED (2026-08-14, v6adv, 30 steps)
Config: ZeRO-2 + batch2/accum4 (global 16) + group_by_length + adamw_bnb_8bit +
drop-zero-adv → **35.4 s/step vs v2's 45-50 (~28% faster)**, loss healthy (0.23-0.47,
grad_norm 0.3-0.8). Traps hit: (1) trl SFTConfig rejects `group_by_length` ctor kwarg —
inject post-construction as attributes; (2) **plain-DDP config BREAKS the liger path**:
`_get_base_transformer` unwrapping differs under DDP → trl's `_chunked_ce_forward`
patch intercepts → full lm_head logits (16GB) → OOM. ZeRO-2 is the working config;
DDP needs an unwrapping fix before use. (3) batch4 OOMs under ZeRO-2 (38GB peak at
batch2 already). v6adv tokenize: kept 3177/4152 (945 too_long at 8192).

### v0 binary advantage scheme IMPLEMENTED + v5 recomputed (2026-08-14)
`scripts/recompute_advantage_v0.py`: two-axis scheme on existing rollouts —
A_exp = group-center(R_exp) with R_exp = evidence-gold recall ('display' mode) or
pF−p0 teacher-forcing gain ('tf' mode — for OLD rollouts whose display was truncated
pre-Option-B); per-turn a_t = scale_t × A_exp, scale ∈ {0,1} from any of G (gold
first-attribution) / F (forward credit > 0) / L (LOO > 0); plan scale = R_exp>0;
answer axis = group-center F1(pred, gold∩evidence), empty∩ → 0; scale=0 turns in
negative trajectories get −ε·|A_exp| (eps=0.05, counteracts the relative-probability
lift of zero weights — user's observation). No ÷n, no Σ conservation.
v5→v6adv (tf mode): ①好探索+坏答案 158条 → 58% exploration credit flipped positive;
②坏探索+好答案 440条 → 79% suppressed. Residual 42% of ① = sg-level signals parsed
from truncated displays — will resolve on new-harness re-rollout with structured
fields. Output: /tmp/seq_train_v6adv.jsonl.
Trainer flags added: `--optim adamw_bnb_8bit` (bitsandbytes installing), 
`--drop-zero-adv` (zero gradient = free drop; 17% in display-mode data, 1% tf-mode).
Training speed stack (ranked): drop-zero-adv > group_by_length+DDP+batch4 (prepared) >
torch.compile > 8bit optim (memory lever, minor speed for LoRA). fla/causal-conv1d
fast kernels already active since 07-25 (in v2's 45-50s/step).

### Error attribution + rollout speed design (2026-08-14, user framing)
Three-bucket attribution on rebase CWQ base (3 seeds, 100 cases; 65 correct):
| bucket | cases | F1-loss share |
|---|---|---|
| ② relation selection (18 variance + 6 stable-wrong) | 24 | **72.6%** |
| ① intent/noise (alias/granularity) | 10 | 26.4% |
| ③ under/over-answer | 1 | 0.9% |
User's priority confirmed: ② dominates. ②variance (18) has natural GRPO signal;
②stable-wrong (6) needs directed/hard-case rollout if all samples repeat the error.
Speed: `scripts/select_rollout_cases.py` picks wrong+flip cases from multi-seed
reports → CWQ filter = 35/100 (tmp/rollout_case_filter_cwq.txt). Combined with
THINK_BUDGET 1000→512, MAX_ROUNDS 16→12, and 2×single-GPU data-parallel rollout
(9B fits 1×40GB), estimated 5h → ~40min for the informative subset. Train side:
zero-adv drop (20%) + group_by_length + DDP + batch4 (prepared, untested).

### NEW BASELINE (2026-08-14 rebase, 3-seed 11/22/33, post all harness changes)
| dataset | base | v2 LoRA |
|---|---|---|
| CWQ 100 | **0.8178** (0.808-0.828) hit 91.0% | 0.8166 (0.804-0.824) hit 90.7% |
| WebQSP 100 | **0.8080** (0.782-0.823) hit 90.0% | 0.8028 (0.793-0.813) hit 90.0% |
Empty answers 0-1/300, rescue 0 — traps no longer form. Paired same-seed vs stab3
(pre-Option-B): CWQ base +3.0pp, ALL 3 seeds positive. WebQSP decomposition:
single-answer 0.853→0.856 (+0.3pp, unchanged as designed), multi-answer
**0.678→0.739 (+6.0pp)** — the list-question fixes carried the whole gain.
CWQ-WebQSP dataset gap: 6.1pp → 1.0pp. v2 ≈ base everywhere (paired Δ −0.1 to
−0.5pp, noise) — LoRA trained on old-harness rollouts gets no benefit from the new
evidence form (distribution shift); retraining requires fresh rollout on this harness.
Reports: seq_eval_rebase_{cwq,webqsp}_{base,v2}_s{11,22,33}_100.json.

### Zero-information-gain CVT attr compression (2026-08-14, user principle)
In `_render_records` office-record groups: an attribute IDENTICAL across all records
of a comparison group cannot discriminate candidates — collapse uniform attrs
(jurisdiction + extra keys) into ONE "(all: k=v; ...)" clause on the group header;
varying attrs stay per-record (from/to never hidden — usual discriminators and often
the literal answer). `extra[:2]` display cap now preferentially shows VARYING extras.
Unit-verified; CWQ 30-smoke 0.8061 (band, no regression). Same principle applies to
future display surfaces: uniform-across-group = no gain = compress.

### Option B implemented: leaf-set enumeration in the evidence builder (2026-08-14)
Per user's architecture review: same-prefix/different-leaf = ONE one-hop pattern; the
24 support-path cap must bound path-SHAPE variety, never leaf cardinality. Moved leaf
enumeration INTO `build_pattern_evidence_triples` (witness last-hop incident edges,
BOTH orientations — witness-direction gating was tried and REVERTED: the walk is
undirected so witness orientation is an arbitrary ranking artifact, and gating on it
emptied the leaf set → offpool rejected the model's displayed-evidence answers;
WebQSP list GT is also orientation-loose). `pe.candidates` now enriched from
pat_triples (no [:50] cap) so offpool covers every leaf. The retrieve_subgraph-level
parallel enumerator (Option A patch) was REMOVED — single producer again.
Branch protocol syntax changed `#c|r` → **`#c::r`** ('|' collides with the flat
protocol's list separator — '#Smokey Robinson|track' parsed as two entities).
`_last_answer_entities` rescue also reads the last checkpoint binding.
Verification (8-case mega-list slice, single-seed, ±noise is large at this n):
pre-fix 0.636 → B2 0.774 / B4 0.740; WebQTest-97: model submits `#Smokey Robinson::track`
→ system expands to 242 entities → F1 1.00 (|G|=441) — branch protocol end-to-end ✓.
CWQ 30-smoke 0.8283 (band 0.81-0.84, no regression).
**Residual failure modes (next design pass, do NOT patch ad-hoc)**:
1. checkpoint declarations of huge lists truncate at max_tokens → unterminated bracket
   → _CKPT_RE misses → bindings lost AND rescue blind (WebQTest-95: pred=1 after model
   wrote 150-book checkpoint). Candidate fix: allow `?var = [#center::relation]` branch
   refs INSIDE checkpoints, expanded in _update_var_bindings (compressed checkpoint).
2. Run-to-run swings on the 8-case slice (B2 .774 / B3 .652 / B4 .740) are single-seed
   noise; conclusions need multi-seed from now on.

### List-question evidence fix + branch protocol (2026-08-14, user insight) — superseded by Option B above
User insight: K-path bounds the number of PATTERNS, not entities WITHIN a pattern —
the walk was correct; the truncation was in the EVIDENCE builder
(`build_pattern_evidence_triples._select_support_paths(max_paths=24)` kept only 24
sibling paths → Smokey Robinson --track--> 27 of 256 songs). Implemented:
1. `_enumerate_selected_direct` (seq_tools.py): full local enumeration of ALL edges
   of the model-selected relations incident to each center (walk stays pattern-bound).
2. `_merge_edges` per-line cap 120 + advertised `#center|relation` BRANCH REF.
3. `_expand_branch_refs` (tools.py `_do_answer`): `#center|relation` answer entities
   expand to the full pattern edge set before offpool (system-level compressed answer).
   Verified in unit tests; model hasn't spontaneously submitted a ref yet (adoption
   needs prompt guidance/repeats — the tool-result hint is contextual only).
Results: WebQSP mega-list slice (8 cases) F1 0.636→**0.749** (+11.3pp), hit 8/8
(WebQTest-87: 63/63 enumerated → F1 1.0). CWQ 30-smoke 0.8111→0.8394 (no regression).
**vLLM server now runs with --enable-prefix-caching** (Mamba 'align' mode; launcher
/tmp/start_vllm_v2.sh sets VLLM_ENABLE_PREFIX_CACHING=1) — matches the offline-rollout
9.6x-reuse config.
**Seed-variance root cause CONFIRMED (user's claim)**: of the 28 cross-seed F1 flips
(stab3), 86% (base) / 89% (v2) show DIFFERENT final relation choices across seeds —
the instability lives at the relation-SELECTION layer; same-relation extraction
variance is only 11-14%. Combined with the v5 credit decomposition (retrieval turns
carry only negative advantage mass, -647 vs +673 on the answer turn), this explains
why offline GRPO did not stabilize: the dimension that varies (relation choice) is
the dimension that never received positive credit.

### Harness audit (2026-08-14) — rejection/feedback design + reasoning_end leak
- **WebQTest-3 dead-lock**: answer-before-facts rejection says "call answer again", then
  repeat-rejection says "do not re-call" → model trapped in 10 identical rejections →
  empty answer with correct answer in hand. Two contradictory instructions, both in harness.
- **reasoning_end leak**: start tag is template-injected in PROMPT; vLLM parser can't find
  boundary in OUTPUT → budget force-inject glues "I will now emit...</think>" onto the last
  partial word mid-entity-list. Parse repair saves tool STRUCTURE, not VALUES (bindings /
  entities get the glued string). v2 training-data contamination RULED OUT (3/4152 samples).
- **Fix plan P1-P6 IMPLEMENTED (2026-08-14)**: P1 answer exempt from repeat-reject
  (`seq_react_loop.py` repeat gate) — the premature-answer one-shot (`reminded` in
  seq_harness) already existed but the repeat gate sat IN FRONT of it and blocked the
  compliant retry forever; P3 budget message now only names executable actions; P4
  `SeqReactCase.rescue_terminal_answer()` (called by BOTH runners) recovers the answer
  from the last trapped `tool: answer` call or `ANSWER:` checklist → result gets
  `terminal_rescue: true`; P5 ingress sanitizer `strip_reasoning_leak()` in
  `kgqa/core/utils.py` applied at `process_turn` head (before history/bindings/parse);
  P6 same strip inside `_do_answer` entity values. Verified: syntax + unit (real
  WebQTest-3 trajectory replay recovers ["William Roache"]) + 30-case smoke (0 empty,
  0 failed, F1 0.8111). **Post-fix WebQSP 100-case rerun (same protocol/pkl)**:
  base 0.7492 → **0.7814** (+3.2pp), v2 0.7344 → **0.7612** (+2.7pp); empty answers
  base 3→1, v2 3→0. All 4 trap cases (WebQTest-3/89/91/109) went **0.00 → 1.00** for v2.
  terminal_rescue fired 0 times — P1/P3/P5 fixed the traps IN-LOOP (answer accepted
  normally); P4 is pure backstop. WebQTest-64 (Dickens mega-list) unchanged = real
  behavior, not a trap. v2 still < base on WebQSP (no cross-dataset transfer, unchanged).
  Single-seed caveat: aggregate Δ carries ±1.5-3pp seed noise; the paired trap-case
  recoveries are the directly-attributable part.
  **Post-fix CWQ 100-case rerun**: base 0.8101 → 0.8072 (flat, win/loss 9/9 = noise),
  v2 0.8148 → 0.7899 (within v2's own seed band 0.767-0.815 from stab3+orig; drops are
  uncorrelated per-case flips — Vicksburg flipped back, base moved +0.82 on it). Rescue
  fired 0; empties 2→1. **Verdict: fixes are a WebQSP-sized win, CWQ-neutral, no
  regressions.** Benchmark protocol from now on: multi-seed mean ± spread, never
  single-seed deltas <3pp.

## v16 round-2 verdict + CWQ 题干-答案错配审计 (2026-08-19)

### v16 (round-2 iterative RL) — FLAT, marginal gain exhausted
- v15→v16 on the 1091 TEST error set: **0.4283 → 0.4144** (-1.4pp, inside the
  ±1.6pp single-seed band). EM churn bothEM=205 only15=74 only16=54;
  big-gain(>+0.3F1)=94 vs big-loss=111. 100-case easy-slice 3-seed mean 0.7928
  (flat, expected).
- **Iteration curve: base 0.2291 → v15 0.4283 → v16 0.4144.** Round-2 added
  nothing; remaining error mass is not reachable by another GRPO round on the
  same signal (gold_never class + eval artifacts, see audit below).
- Artifacts: `reports/v16_testwrong.json`, checkpoint `checkpoint/seq_grpo_v16`.

### CWQ question↔gold mismatch audit (two-pass LLM judge, full 3531 pool)
Method: pass-1 accuse judge (temp 0) flags 1652 (46.8%); pass-2 adversarial
defense judge re-tried only the flagged ones; **两遍确认 813 (23.0%)**, defended
830. Manual 30-sample calibration agrees (~50% of pass-1 flags true; confirmed
set precision ~80%). True magnitude band ≈ 813–1000.
- Families (confirmed): SCOPE 301 (singular/plural, scope words — pure stem
  reword), TYPE 283 (interrogative vs gold type), NON_ANSWER 217 (gold chain
  corruption, NOT rewordable), ECHO 12.
- Objective add-ons: dup gold entries 57, raw-ID gold leak 11 (all from
  WebQTest-213 Scarlett Johansson cluster — repair-pipeline artifact).
- **Error-set attribution: 372/1091 (34.1%) of the error set is confirmed
  mismatch; v16 meanF1 there 0.322 vs 0.462 on the rest; 200 hard-zeros.**
- NOTE scoring interplay: `compute_match_stats._matches` has substring match
  with NO min length → "2014" matches gold "2014 World Series" → the
  asks-year/gives-event family has LOW eval impact; SCOPE/NON_ANSWER are the
  score-killing families.
- Same gold reused by 3-30 different questions is NORMAL scaffold structure
  (FDR ×25 etc.), not corruption — don't "fix" it.
- Reviewable dump with per-case proposed minimal stem fixes:
  `tmp/qa_mismatch_review.md` (813 cases, grouped by family, error-set marked).
  Raw: `tmp/qa_mismatch_llm.json` (pass1), `tmp/qa_mismatch_llm_pass2.json`.
  Scripts (gitignored one-offs): `scripts/audit_qa_mismatch*.py`,
  `scripts/aggregate_qa_mismatch.py`, `scripts/build_qa_mismatch_dump.py`.
- **NOT yet applied**: any stem reword would fork the eval file
  (test_v5_stemfix) and break comparability with 0.2291/0.4283/0.4144
  baselines — awaiting user adjudication of the dump.
- test_v4_repaired.pkl is a MIXED pool: 1203 WebQTest- + 2328 WebQTrn-prefixed
  ids (3531; eval pool 3397). No id overlap with train_v4 (leak check clean).

### TYPE-family stem repair applied (2026-08-19, user ruling: stem-only, gold untouched)
- User adjudication: this round = TYPE family only (other families need gold
  edits). Pipeline: 283 confirmed TYPE → LLM minimal reword (interrogative
  only, constraints frozen) → numeric-token preservation gate → fresh-context
  MATCH verification → drop no-ops (3) + gold-leak rewrites (4).
- **Final: 136 rewords applied → `data/cwq_processed/test_v5_stemfix.pkl`**
  (v4 copy, questions only; 76/136 in the 1091 error set). Review list:
  `tmp/qa_stemfix_type.md`; per-case JSON `tmp/qa_stemfix_type.json`,
  kept-set `tmp/qa_stemfix_keep.json`. Script (gitignored):
  `scripts/stemfix_type_family.py`.
- 114 rewords rejected by verifier = deeper-than-wording mismatches (ECHO
  masquerading as TYPE, wrong-landing golds) — left original, candidates for
  a future gold-repair round.
- v5 is a SEPARATE file: eval with TEST_PKL=...test_v5_stemfix.pkl; numbers
  are not comparable to the v4 baselines (0.2291/0.4283/0.4144) on the
  reworded slice.
- **User tightened policy (same day): sentence structure FROZEN — word-level
  substitution only** ("不改变原始的句式，顶多措辞调整"). Added a structure gate
  (difflib word alignment: ≤3 replaced tokens, ≤1 inserted/deleted) on the
  136 → **final 98 rewords in test_v5_stemfix.pkl** (52 in error set); 38
  restructures (e.g. object-absorbing "In what year...win the Super Bowl" →
  "Which Super Bowl...win") reverted to original. Kept-set:
  `tmp/qa_stemfix_strict.json`; review: `tmp/qa_stemfix_type.md`.

### Stemfix paired A/B (2026-08-19): TYPE repairs WORK
- Design: v15 policy, TEMP=0.3, N_SAMPLES=1, same 98 cases, only the stem
  differs (v4 original vs v5 reworded). GTE health-checked before run.
  Outputs: `reports/stemfix98_v15_v4.json` / `stemfix98_v15_v5.json`
  (split `test_v5` registered in seq_rollout PKLS).
- **meanF1 0.602 → 0.748 (+14.6pp), hit 68.4% → 84.7%.** Flips: rescue 23
  (17 from F1=0) vs regress 10. Error-set 52 subset: **0.392 → 0.642
  (+25.0pp, 15 →EM)**; non-error 46: 0.838 → 0.867 (noise-band).
- Regressions inspected: over-enumeration (gold included among extras,
  precision hit, e.g. Picasso listed with 5 others) + retrieval flips —
  not systematic rewrite damage; single-seed paired noise.
- Residual v5 failures (23 at F1<0.5) are gold-granularity / retrieval
  issues (Bethany Congregational "United Church of Christ" vs gold
  "Christianity"), NOT type-wording — consistent with TYPE family being
  exhausted by stem repair.

### TRAP: full-pool rollout stage-startup deadlock + silent chain stall (2026-08-20)
- Symptom: full_v5 base run — stages 1-2 (1000 cases each) fine, stage 3
  hung right after the "── stage 3/4" header: engine idle (GPU 0%, memory
  held), log silent 30+ min. The setsid chain's `echo DONE` never fired, so
  the follow-on run never started — status-file silence ≠ still running.
- Fixes:
  1. `seq_rollout.py` now has **RESUME**: if OUT exists it loads the
     incrementally-saved results, counts done cases (saves happen only at
     stage boundaries → exact), skips covered stages. Kill+relaunch is safe.
  2. Watchdog chain `logs/run_full_v5_chain.sh`: log-mtime staleness
     (>1200s) → kill tree → retry (≤6); resume makes retries lossless.
- Diagnosis habit for long runs: check BOTH the status file AND
  `nvidia-smi` AND log tail — json existing means stages saved, not that
  the process exited.

### Failure-phase attribution (2026-08-20, scripts/analyze_failure_phase.py)
F1 loss mass by phase (v15 error set 1091 / v5-base 2000 — same current
harness, consistent):
- **ANSWER-MISS (all gold in evidence, zero bound): 40%/44% of loss mass,
  ALL F1=0** — the single biggest bucket.
- RETRIEVAL-MISS (gold never reached evidence): 30%/26%
- OVERSHOOT (all gold answered + extras, precision loss): 21%/20%
- ANSWER-PARTIAL: 4%/6%; RETRIEVAL-PARTIAL: 6%/4%
- Refinement: of 250 v15 ANSWER-MISS, **245 (98%) had full gold in the
  RENDERED tool text** (checked against trajectory tool messages, not the
  accumulated superset) → NOT display truncation: true selection/binding
  failures. Texture: constraint-sifting (picks anchor-salient entities over
  constraint-satisfying row) + granularity (regiments vs CSA, sport vs club).
- Of those 245, **104 (42%) are two-pass-confirmed gold mismatches** →
  pure trainable "saw it, bound wrong" = 141 cases. Answer-layer total
  (MISS+PARTIAL+OVERSHOOT) ≈ 65-70% of loss mass → next lever is the
  answer stage (constraint-check discipline / round-3 RL credit at answer
  turn), NOT more retrieval work.
- CAVEAT comparability: full_v4_offline (0.7524) predates the 08-18/19
  harness changes → v5-full vs v4-full is harness-confounded. Clean pairs:
  98-stemfix A/B, v15/v16 testwrong, v5 full runs (become the new
  canonical baselines on current harness).
- Full-trajectory review dump for manual phase-cause adjudication (3 per
  bucket, THINKING + tool calls + verbatim tool results):
  `tmp/failure_phase_review.md`. Bucket sizes refined: ANSWER-MISS total-bind
  = 141 clean / 104 gold-mismatch; partial-bind = 39 clean / 36 mis;
  notvis = 6; RETRIEVAL-MISS 184; RETRIEVAL-PARTIAL 54; OVERSHOOT 248.

## Walk×display design audit (2026-08-20) — see specs/walk_display_design_audit.md
- Systematic design-vs-implementation comparison (user directive: no
  whack-a-mole). Root cause class: THREE granularities across layers
  (walk=pattern w/ bounded sibling leaf sampling, display=edge-look lines
  deduped at (h,r,t), answer=entity pool) with unspecified inter-layer
  contracts — the tool note promises EDGE semantics nobody provides.
- Manifestations B1-B5 (edge-extension ownership, tail-split across
  subgraphs, candidates-line drift, navigation contract, completeness/
  economy entanglement). D1/D2 verified implemented.
- Proposed: Option A edge-authoritative evidence contract (full tail
  enumeration for D2-admitted edges; (h,r)-union re-render; candidates
  line = ctx.all_candidates; caps demoted to render-only). Awaiting user
  adjudication before implementation.

### TRAP (box-level, 2026-08-20): filesystem mtime does NOT update on writes
- Proven: logs/full_v5_base.log grew 109KB→128KB while mtime stayed frozen
  13+ min behind; v15.log showed content written after its launch with an
  earlier mtime. **Never key watchdogs/liveness on mtime on this box** —
  use file SIZE growth (reliable) or GPU util.
- v1 chain "600s kills" + v2 would-be kills both stem from this. v3 chain
  (logs/run_full_v5_chain.sh): size-based watchdog (1800s frozen → kill),
  setsid PGID tree-kill + `VLLM::EngineCore/Worker` pattern sweep + GPU
  compute-app sweep (GTE exempt) before each attempt. Killing only the
  direct child leaves orphaned workers holding ~78GB → next engine blocks
  at init → false "hang" cycle.

### B2 FINAL RULING IMPLEMENTED (2026-08-20): cross-call triple dedup ABOLISHED
- User ruling: the dedup was an economy hack for walk-bloated subgraphs;
  admission now lives in the walk layer (pattern-path discipline). A triple
  that is a link of the CURRENT subgraph's pattern path must never be
  suppressed — suppression severs paths and masks entities from an edge's
  displayed extension.
- Patch: `shown_edges` is now a per-call local set in the retrieve_subgraph
  handler (was ctx-persisted (h,r,t) key set). Tool note updated (edge
  re-appearance across subgraphs is legitimate; full tail set expected).
- Validated: Faroese shape (sg2 renders all 4 tails of
  Denmark--languages_spoken on one line), within-call dedup intact, CVT
  record rendering intact, select_expand smoke green.
- CAVEAT: the v5 full-eval chain running at patch time imported the OLD
  module; any watchdog retry after the patch would mix display semantics
  within one report file — checked status (no retries at patch time); final
  numbers to be sanity-checked for retry events before use.

## Plan-contract v2 IMPLEMENTED (2026-08-21, user ruling after specimen analysis)
Philosophy (user): plans are hypotheses, not contracts — a human closes dead-end
steps and answers the moment the QUESTION is answerable. Specimens: Ramble/VP
(16-round loop on a dead-end fact, empty answer; evidence had Al Gore at turn
9) and Kovu (model misread WHO→movie, answered a film).
- **answer_type**: plan declares a ONE-WORD type for what the question asks
  (two-phase: analyze question → type word → decompose). Schema PlanArgs +
  _parse_flat + ctx.plan_answer_type; echoed in allowed_tools_hint whenever
  answer is legal; §18 checklist gains a C_type line.
- **Three-state closure**: `[fid ✓]` / `[fid ✗ empty]` (pool holds no
  advancing relation — a verdict, not a failure) / `[fid ✗ moot]` (target
  already bound by earlier evidence). Parser _CKPT_CLOSE_RE → ctx.closed_facts.
- **Plan immutable**: second plan call → REJECTED with close-only directive
  (ctx.plan_declared gate in _do_seq_decompose).
- **Question-driven terminal**: answer legal as soon as the answer variable is
  bound (§9/§18 rewritten; "only answer after all facts closed" REMOVED).
- **Answer floor**: rollout now calls rescue_terminal_answer (per-call runner
  already did; rollout path was MISSING it — the Ramble specimen scored empty
  because of this gap). Records carry `rescued` flag.
- Validated offline: closure regex/merge, flat-plan answer_type, schema,
  immutability gate, imports. Behavioral replay (both specimens) + smoke after
  the v15 chain frees the GPU.

### Prelink v2 (2026-08-21, user ruling B): question-ranked anchor injection
- Specimens: Ron Howard (alphabetical sorted()[:3] sampled award.* for a FILM
  question — anti-relevant on the question's axis; model treated the sample as
  the graph's state) and Lala/Carmelo (q_entity ≠ question subject; the old
  "system confirmed" wording made the model doubt the question).
- Ruling: keep names+relations injection, but rank BOTH the anchor entities and
  their neighbor relations with GTE against the ORIGINAL question (anchors via
  gte_retrieve question↔names; relations via _gte_for_triple with
  pool_relids=1-hop set). Fallback on GTE failure: dataset order / no relations.
- Wording scoped: names are spelling references, never a mandate to pivot;
  relations are a question-ranked sample, "authoritative relation set always
  comes from retrieve_relations".

### Perf attribution (2026-08-21, instrumented 100-case, phase timers)
- Instrumentation: PHASE_TIMES + phase_timer in kgqa/core/utils.py; rollout
  prints llm/dispatch wall + walk/render/gte per stage. Perf run log:
  logs/perf_timing100.log.
- Result (100 cases, 529s total, 5.3s/case — smaller batches beat 500-case
  stages' 8s: GTE contention scales with concurrent lanes):
  **llm=209s wall (39%) | dispatch=296s wall | gte=2542 lane-s | walk=314 | render=2**
- Verdict: render is nothing (user's intuition confirmed). GTE awaits ≈ 89%
  of in-dispatch lane time — the GTE server (single proc, embeds the FULL
  candidate pool on EVERY /retrieve call, no candidate caching) is the CPU-side
  bottleneck; 16 concurrent rollout lanes saturate it.
- Levers (ranked, awaiting ruling): (1) GTE candidate-embedding cache
  (/precompute exists, unused by this path); (2) reuse embeddings for repeated
  (head,pool) queries within a case; (3) batch the 16 lanes' GTE calls into
  fewer larger requests; (4) shrink pools.
- Contract v2 + prelink v2 smoke (100, v4 stems, base): **0.7941 / EM 72%
  / rescued=3** vs old-stack same slice 0.7826 — flat-to-positive, floor
  fired, no format regressions (0 failed, 0 rejects beyond nudges).

### GTE perf saga (2026-08-21): to_thread fix BACKFIRED, refactor greenlit
- Instrumented 100-case: pre-fix gte=2542 lane-s; after asyncio.to_thread in
  the server endpoints: **7663 lane-s (3x worse), stage 1010s vs 529s** —
  tokenizer is pure Python (GIL-bound), concurrent small batches thrash.
  Reverted; cache lock kept (harmless).
- User greenlit a retrieval-service REFACTOR (old script, patching exhausted).
  Core design direction: vocabulary-keyed vector index (candidates keyed by
  STABLE pure-relation text → global cross-case cache; queries LRU-cached) +
  single batched inference worker (dynamic batching, no thread thrash) +
  client pool hygiene (aareas.schema noise filter, top-K 30 per the old
  tuning). Ranking-format change (labeled-triple → pure-relation candidates)
  must pass an offline recall@K gate on recorded trajectories before switch.

### Gold-relation recall benchmark (2026-08-21, user-directed) — THE gate for GTE tuning
- scripts/bench_goldrel_recall.py: N train cases, gold edge (edge touching gold
  answer), center = other endpoint, query = FULL question (stress; real
  sub-questions are cleaner), pool = _seq_pool_relids, recall@15 of the gold
  relation. 150 cases: gold-in-pool 86%.
- **2x2 matrix (labeling x instruct), n=126 in-pool:**
  L2V0(current) 39.7% | L1V0 34.1% | **L2V2 42.1%** | L1V2 34.9%.
- Verdicts: (a) last-1 labeling LOSES ~5pp — user's "纯关系语义飘逸" concern
  CONFIRMED on the corpus (namespace words disambiguate); (b) V2 answer-bearing
  instruct WINS +2.4pp with last-2 (and was the Iraq specimen's fix lever).
  Iraq-type burial is real but niche; the corpus-level winner is
  **keep last-2 labeling + V0→V2 instruct** — embedding-native, zero drift risk.
- GTE server v3 deployed: single inference worker (dynamic batching via
  concurrent.futures + queue; one CUDA stream, no GIL thrash) + query-side
  embedding cache. Replaces inline (loop-blocking, 2542 lane-s/100) and
  to_thread (GIL-thrash, 7663 lane-s). Timing v3 rerun pending.

### CVT display dedup + checkpoint CVT guard (2026-08-21, Angelina awards specimen)
- Specimen: one awards-hub subgraph rendered the same ~70 CVTs under EVERY
  spoke (nominee/ceremony/award/work heads) each with the full attr bracket —
  `_inline_events` inlined attrs at EVERY appearance (4x blowup), and the
  model checkpointed raw m-ids (?award = [m.010wr37v | ...]) with no harness
  interception (the note's "events are never answers" was prose only).
- Fixes: (1) `_inline_events` prints the attr bracket ONCE per CVT per render
  (first appearance carries it; later spokes bare id); (2) checkpoint parser
  strips is_cvt_like bindings + sets ctx.cvt_binding_flag → process_turn
  injects the harness reminder (bind the named ATTRIBUTE inside the bracket).
- Unit-verified: bracket count == 1 on multi-spoke fixture; binding strips
  m-ids keeping named attrs.

### CVT-answer system rejection (2026-08-21) — 34% of empty answers eliminated
- Quantified (user-directed scan): v5_base 158 empty answers — 54 (34%) involve
  CVT binding (49 checkpoint-bound m-ids, 50 answer-submitted m-ids); v15
  error set 97 empty — 32 (33%). Mechanical, fixable class.
- Third gap closed: _do_answer's mid-strip silently emptied all-mid
  submissions and ACCEPTED them (tools.py:1969-74). Now: all-mid submission →
  one-shot REJECTION with the fix instruction (bind the named attribute from
  the event bracket); retry passes (same semantics as the offpool check).
  Combined with the checkpoint guard (strips + reminds at bind time), both
  CVT entry points are intercepted.

### CVT philosophy layered in (2026-08-21, user ruling: philosophy + reminders first)
- SEQ_AGENTS.md §7.5 "Event Nodes Are Abstract Records — Bind the Attribute
  Entity": the event node names no thing; its identity IS its attributes;
  bind per-variable the attribute entity whose KEY answers the question
  (award→award=, residence→location=, who played→actor=...); one record may
  feed several variables. Harness reminders (checkpoint guard + answer
  rejection) aligned to the same record-vs-world framing. Mechanical guards
  remain as backstop, not as the primary teaching.

### Rendering mechanism design (2026-08-21) — specs/rendering_mechanism_design.md
- User ruling: STOP patching the renderer (13 mechanisms across 4 functions,
  each specimen added an if; interaction-bug risk compounding). Greenlit a
  unified design review instead.
- Design: 5-stage pipeline (normalize → eventify → identity → group →
  compress+synth), ONE line grammar, 3 economy laws (L1 uniform-attr hoist /
  L2 single-print /  L3 budget), 5 testable invariants (I1-I5). Office
  records, measurement records, inline events become payload variants of one
  grammar instead of separate paths.
- Migration gated by a 10-specimen fixture corpus (every historical specimen
  becomes an assertion); rewrite as ONE function; no more incremental patches.
- Pending user adjudication of the design before implementation.

### GTE request-path optimization (2026-08-21, user-directed)
- Diagnosed from v5: GTE wall = ~35s compute + batch-window tax (60ms×calls)
  + big-request parse overhead (same (head,pool) re-sent 10-30KB across facts,
  only the query changes).
- Fixes: (1) POOL REGISTRY protocol — /retrieve accepts pool_key; first call
  registers candidates, later calls send key only (client: _gte_for_triple
  computes md5(head+pool) and tracks _REGISTERED_POOLS per process);
  measured e2e: 601ms register vs 45ms key-only. (2) batch window 60→15ms +
  early-close at 256 merged texts. Server restarted with both; Field import
  fix included.
- timing v6 launched to measure combined effect (target: GTE wall share
  <15%, per-case <3.5s).

### Answer-rules audit (2026-08-21) — specs/answer_rules_audit.md
- User ruling: audit the answer rules holistically (human-answer philosophy),
  no whack-a-mole; plus assess whether the new display forms structurally
  improve attribution.
- §18 v2 = existing rules + FOUR new laws derived from the session's specimen
  corpus: (A) evidence-citation duty (every PASS/FAIL cites that candidate's
  own displayed evidence, else UNKNOWN); (B) graph-first (world knowledge
  hypothesizes, never adjudicates; missing edge = UNKNOWN); (C) discriminator
  visibility (display-side co-responsibility — discriminators as scannable
  columns); (D) per-candidate attribution (no borrowed evidence).
- Display co-design answer: YES, structurally — citation duty needs
  addressable evidence units; record/join tables provide row/column
  coordinates, intersection becomes column alignment, nav-index separates
  navigation noise from evidence. ANSWER-MISS 245 (98% gold visible but
  drowned) is the noise-harm quantification.
- Implementation batches with the rendering rewrite; gate = specimen fixtures
  + 100-case A/B + error-set phase-attribution delta.

### Empty-66 RESCUE TRIAL (2026-08-21): fix stack VALIDATED on the exact cohort
- Re-ran the 66 previously-empty regression cases (all F1=0 in v5_base) on the
  current stack (plan-contract v2 + CVT four layers + answer floor + display
  dedup; NOT yet rendering rewrite / §18 v2):
  **meanF1 0.0 → 0.755, EM 0 → 48/66 (73%), still-empty 66 → 2.**
- Answer floor fired 5x; CVT guards left only 2 cases with residual m-id
  patterns (1 of them EM). Remaining non-EM ≈ gold-mismatch/hard family.
- Interpretation: the empty-answer regression cohort was almost entirely the
  mechanical family (dead-end loops + CVT swallowing) the contracts targeted.
  Rendering rewrite + §18 v2 remain the next lever (ANSWER-MISS/partial
  families). Run: reports/empty66_rescue.json.

### Two more root causes nailed (2026-08-21, user adjudications)
- CH specimen (answer='CH'): plan's answer SLOT inverted (?language for a
  "which countries" question) — answer_type was OPTIONAL and skipped. FIX
  SHIPPED: plan handler now REJECTS plans without answer_type (forced turn-0
  type commitment; slot/type contradiction surfaces immediately).
- Germany adjoin_s specimen: user verdict "关系丢失, not display suppression"
  — CONFIRMED at code level. The walk DID emit m.02nxjlh --adjoins--> Poland;
  the render fallback's back-edge suppression keys on EACH ENTRY's head
  (v==h skip): the neighbor's spoke entry (Poland→CVT) processed first
  suppresses adjoins=Poland (its "back-edge") and keeps Germany; the center's
  entry then adds nothing (dedup). Net: keeps the CENTER restatement, drops
  the NEIGHBOR — exactly backwards. Suppression must key on the RETRIEVAL
  CENTER. Recorded as a rewrite fixture (S1 eventify keeps ALL role entities;
  center-restatement suppression happens at synthesis keyed on the block
  anchor). Old renderer NOT patched per the no-whack-a-mole ruling.

### Plan-error variance adjudication (2026-08-21, Thundera specimen, 8 samples)
- User question: is the wrong-plan behavior sampling variance? ANSWER: NO —
  the plan anchor is DETERMINISTIC (8/8 MacFarlane). The real lesion was
  top-1 relation selection; the anchor was never wrong (TV performance
  relations in-pool reach Lion-O).
- WIDE-SELECTION NOTE (shipped same day: retrieve_relations note now says
  "select ALL plausible bridges (2-4), not only the top-ranked") moved the
  case from F1=0 to 7/8 samples containing gold (mean 0.688, EM 4/8).
- Residual failures: 1/8 top-1 relapse; 3/8 join-filter misses (bound ALL
  Thundera-born characters without re-verifying the voiced-by constraint) —
  the §18 citation duty's exact target.
- PRIORITY REORDERED: wide-selection (live) > §18 v2 join discipline >
  bounded re-plan (deprioritized — no confirmed wrong-premise specimen).
- Ops note: rollout filter env is CASE_FILTER (file), NOT CASE_IDS — a
  misconfigured variance run silently swept 32 cases × 8 (killed; data
  incidentally confirmed anchor determinism corpus-wide: anchors flip in
  only ~2/256 samples).

### Per-subgraph hallucination check (2026-08-21, user proposal — SHIPPED)
- Kevin Costner specimen root cause: the answer-time sg1.f1 RE-DECLARATION
  merged the other actor's films into sg1 (Twilight never in Costner's
  evidence) — cross-subgraph contamination sailed through the GLOBAL pool
  check; the intersection then wrongly included Twilight (F1 0.667).
- User proposal implemented: each retrieve_subgraph records its OWN named-
  entity evidence set (ctx.fact_evidence[fid]); the checkpoint validator
  strips bindings absent from the DECLARING fact's subgraph + injects a
  "bind only from this subgraph's evidence" reminder. Unit-verified: Twilight
  stripped from sg1.f1 while sg2.f1 passes it legitimately.
- Related specimens this turn: (a) performance-CVT film= discriminators eaten
  by the back-edge-suppression entry-order bug (same Germany lesion — the
  (all: film=Kevin Costner) hoist proves the back-edge occupied the attr
  slot); rewrite fixture extended. (b) award checkpoint bound movies/persons
  from inside award CVT brackets — key-matching rule (§7.5) is the check
  there, teaching-side. (c) Berlin festival pool top-1 = languages — GTE
  residual noise (IDF leg pending). (d) 'Stephanie Meyer' entity resolution
  failed (graph spells Stephenie) — correction candidates were useless.

### Berlin/Meyer specimen adjudication (2026-08-21) + two shipped fixes
- Berlin "relation tool errored": pool was 160 (NO sparse fallback), the gold
  relation film_festivals IS on the center (dist 0) — pure GTE ranking burial.
  V2 instruct already moves it to #13 (in-display). Residual junk top-10 =
  rdf-schema#domain/#range — W3C schema plumbing added to the CLASS noise
  filter (same universal-structural class as type.*, not a case list).
- Meyer: NO author entity exists in the case graph (only attribute-string
  fragments "Based on the Novel by Stephenie Meyer") — data gap; the
  correction candidates were honestly nearest (incl. the fragments). REAL
  bug = the entity_error note said "re-call with the right entity" while the
  repeat gate rejects same-name re-calls — model trapped. Note rewritten:
  re-call with a CANDIDATE name (different args pass), else ✗ empty.
- Per-subgraph hallucination check (previous entry) covers the Costner
  cross-subgraph contamination; performance-CVT film= loss = same Germany
  entry-order lesion (fixture).

### Meyer entity: triple absence confirmed (2026-08-21)
- WebQTrn-25_7cec: q_entity=[Taylor Lautner] only; entity lists (319 text +
  275 non_text) contain NO Meyer node; ZERO author/written_by/based_on edges
  in the whole case graph. The author exists ONLY as attribute-string
  fragments inside award notes_description. GTE entity search behaved
  correctly (searches the entity list; the node is absent).
- Root: the case-snapshot extraction dropped the ADAPTATION namespace
  entirely (gold film's edges are all starring/awards/sequel — no novel
  chain). Repair spec: New Moon --adapted_from--> novel --author--> Meyer.
- Correct model behavior under the fixed entity_error note: ✗ empty the
  Meyer fact, judge by award evidence at answer time (the based-on
  constraint is graph-unverifiable → UNKNOWN per §18).

### Variable freezing + regression-cohort full-stack rerun (2026-08-21, FINAL)
- Freezing semantics (user ruling "注册必须基于对应的子图"): [fid ✓] locks at
  the current retrieval seq; re-declaration WITHOUT new subgraph → REJECTED
  as hallucination with reminder (original stands); WITH new retrieval →
  allowed, validated against the UNION domain (original ∪ new evidence).
  Full matrix unit-verified (lock / frozen-reject / post-retrieval change /
  out-of-domain strip). Wired: frozen_binding_flag reminder in process_turn.
- 267-case regression cohort rerun on the CUMULATIVE stack (contract v2 +
  CVT 4-layer + answer floor + display dedup + walkability pool + V2
  instruct + wide-selection note + answer_type gate + per-subgraph
  hallucination check + freezing + rdf/owl noise class + entity-error note):
  **meanF1 0.272 → 0.751 (+0.479), EM 0 → 165/267 (62%), empty 66 → 5,
  rescued-to-EM 165, lost 0.** (reports/regress267_rerun.json)
- User's closing priority: the remaining frontier is RELATION SELECTION /
  PLAN / FINAL ANSWERING — i.e., the queued batch (rendering rewrite + §18
  v2 four laws + GTE IDF ranking leg).

### answer_type rejection: prompt/examples drift (2026-08-19, found in r267 dump)
- The `plan requires answer_type` gate fired on the FIRST plan call in
  **267/267** cases (reports/regress267_rerun.json). After the rejection only
  55 re-emitted a plan with the field; **212/267 skipped plan entirely** and
  went straight to retrieve_relations → plan contract v2 (immutability +
  answer_type echo) was effectively INACTIVE for 79% of the rerun; the 0.751
  F1 was achieved mostly planless.
- Root cause: SEQ_AGENTS.md §4 prose taught `answer_type:` but the args
  schema block, the flat format example, and ALL 7 worked-example plan blocks
  omitted the line — the model copies examples over prose.
- Fix: added `answer_type: <word>` after `answer:` in the schema block +
  flat example + all 7 plan blocks (verified: 7/7 blocks now carry it).
  Live source is kgqa/agent/SEQ_AGENTS.md read in full by seq_react_loop
  (no truncation; the sys_cap in seq_advantage is the RL path only).
- Also logged while dumping: rescue_terminal_answer overshot on multi-
  candidate constraint questions (9/11 rescued non-EM, pred#42/gold#1 etc.)
  — tighten rescue to obey the §18 discrimination law in the answer batch.
- Error dump for review: tmp/failure_phase_review_r267_rerun.md (index of all
  102 errors + per-bucket sampled full trajectories; OVERSHOOT 47 /
  ANSWER-MISS-vis-clean 22 / vis-mis 15 / RETRIEVAL-MISS+PARTIAL 17).

### Hop-gate made PER-RELATION (Greeley specimen, 2026-08-19)
- Symptom (r267 dump review): model selects {contains, school_type, campuses}
  at city center Greeley; tool shows ONLY the contains line — 2/3 selected
  relations yield zero triples, looks like the pool→walk guarantee broke.
- Trace: walk DID find the 2-hop paths (CASE B works; witness = Greeley
  --containedby--> Aims CC --school_type--> Community college); the loss is
  in build_pattern_evidence_triples._hop_ok (formatting.py): the
  shortest-first gate was SET-LEVEL (_has_direct_sel = ANY selected rel has
  direct edges) — selecting the BRIDGE (contains, direct) silently voided
  every 2-hop-only PAYLOAD sibling (school_type/campuses) in the same call.
- Fix: gate keyed to the path's LAST relation (_direct_sel_rels): detour
  discipline applies only when THAT relation itself has a direct
  instantiation at the center (generalizes the Nordics/Düsseldorf rulings —
  they were already per-relation in spirit). Verify: Greeley now P1 contains
  + P2 school_type (Aims/UNC); Nordic fixture still 1-line contains
  (no back-edge regression); Ethiopia office_holder CVT chain intact
  (tmp/pattern_adjudication.md). Unit tests pass.
- Note: campuses stays empty CORRECTLY (self-loop edges in this graph).

### Plan-phase gate desync fixed (CH specimen, 2026-08-19, WebQTest-1251)
- Symptom: plan rejected (missing answer_type) → model's CORRECT re-emission
  rejected with "Wrong tool in the retrieve phase"; earlier its
  retrieve_relations also failed (anchor never seeded). Three guards
  contradicting each other = deadlock; case ended empty.
- Root cause (three-layer): ① seq_harness.validate transitions INIT→RETRIEVE
  on PARSE success, before the handler's answer_type gate rejects → state
  RETRIEVE with no accepted plan; ② _do_seq_decompose set ctx.plan_declared
  BEFORE the answer_type gate → a rejected plan poisoned the immutability
  flag; ③ the phase gate then blocks the re-emission the rejection demanded.
- Fix (three coordinated): ① answer_type pre-check moved INTO validate (INIT,
  no transition on rejection — message text identical to the handler's);
  ② plan_declared set only after every rejection gate; ③ loop rolls state
  back to INIT when a plan/decompose dispatch result is a rejection AND no
  plan was ever accepted (flat-text result format: check "REJECTED"/"error:"
  substring — _json_result emits flat text, NOT JSON quotes).
- Verified: state machine T1-T4 (reject stays INIT / re-emit accepted /
  second plan phase-blocked / retrieve legal) + handler T5-T7 (no poisoning /
  accept / IMMUTABLE). Consequences: RETRIEVE is now structurally
  un-enterable without an accepted plan — the 212/267 planless flow from the
  r267 rerun cannot recur; anchor seeding always runs (CH entity_error path
  gone). NOTE for next rerun: first-plan rejection rate should collapse
  (SEQ_AGENTS.md examples now carry answer_type).

### Option-B fan-out anchor made orientation-aware (Bernie Brewer specimen, 2026-08-19)
- Symptom (WebQTest-534, gold Hank|Bernie|Bonnie Brewer, answered only Bernie):
  last hop `Milwaukee Brewers --team_mascot--> {3 mascots}` has NO constraint —
  should enumerate the full tail set, but evidence showed ONE backwards triple
  ('Bernie Brewer --team_mascot--> Milwaukee Brewers').
- Root cause: the P2 witness was a 1-hop REVERSE traversal (center Bernie
  <--team_mascot-- Milwaukee). Ruling ⑤ (bidirectional enumeration) was
  implemented direction-agnostic per EDGE but the FAN-OUT anchor stayed
  w_nodes[-2] (path order) = the center — a mascot has no team_mascot
  out-edges, so enumeration silently yielded just the witness. The path-edge
  display also rendered the reverse hop backwards.
- Fix (formatting.py): _true_edge(u, r, v) resolves a path hop to the graph's
  stored (h, r, t) — prefer forward, else the reverse edge (condition: edge at
  v with t_==u; NB first attempt wrote h_==u and silently no-op'd). Used in
  BOTH the path-edge add loop (display truth) and the Option-B anchor
  (_pen = true head → full leaf enumeration).
- Verified: Bernie P2 = all three mascots, correct orientation; Nordic 1-line
  (no back-edge regression); Ethiopia 5 holders intact; Greeley P1+P2 intact;
  unit tests pass. NOT done (ruled out): walk-layer chained-selected-relation
  extension — Nordic data contains Scandinavia--contains-->Sweden/Norway/
  Denmark same-rel chains, so it would re-admit pruned detours; enumeration
  from the true head already delivers the full leaf set (Bernie proves it).

### Direction & truncation full-chain AUDIT (2026-08-19, user directive)
- Baseline invariants (user): undirected walk; edge-level no-backtrack only
  (inverse-pair aware; node revisit via a DIFFERENT relation is legal); CVT
  transparent in/out symmetrically; direction constraints live ONLY in the
  pattern-path adjudication layer (last-hop-selected).
- Full audit table in specs/direction_truncation_audit.md. Verdicts: P0
  direction bugs to fix = ① _collect_hr_frontier path-order (h,r) matching
  (reverse hops never match → no sibling tails); ② _expand_sibling_cvts
  forward-only parent edge; ③ compress_paths _has_non_cvt_loop is NODE-level
  (stricter than the edge-level design). P1 open ruling = CASE A continue +
  CASE B non-target-first gating creates ORIENTATION LUCK (Greeley survived
  only because both contains+containedby edges exist; single-direction data
  would lose the 2-hop payload) — safe fix needs a new hop-gate rule: same-
  relation chains rejected when that relation has direct instantiation at the
  center (Nordics guard), awaiting user ruling. P2 truncation economy
  (prune tiebreak, cands[:20] alphabetical, budget stacking) → rendering
  rewrite batch. OK sites: _canonicalize_triples, _chain_is_cyclic
  (hand-curated 6-entry inverse table — unknown pairs unsuppressed, harmless
  dup display), k_queue/RPE adj, pool _reach2_relids, CVT bridge construct.
- Bernie end-to-end re-verified through the REAL display channel
  (pat_triples → _canonicalize_triples → _render_records): model sees
  'Milwaukee Brewers --team_mascot--> Bernie Brewer | Hank | Bonnie Brewer'.
  NOTE: retrieve_subgraph does NOT use _render_path_tree (that's the legacy
  stage7 channel — path-order arrows, slated for the rendering rewrite).

### Selected-chain walk extension LIVE (orientation-luck ruling demo, 2026-08-19)
- Empirical scan of the r267 cohort for orientation-luck victims (selected
  bridge + selected payload, gold only reachable via the chain, NO unselected
  reverse edge for CASE B rescue): exactly ONE case — Bernie itself (Hank/
  Bonnie lost pre-fix). Freebase dual-direction storage (contains AND
  containedby as separate edges) makes CASE B rescue nearly universal; the
  residual exposure is single-direction snapshot data.
- Implemented for ruling review (+20 lines, logical_paths.py _hit_paths):
  CASE A named-node extension — after a 1-hop target hit, continue through a
  NAMED mid when hop 2 rides a DIFFERENT selected relation (rel2 != rel1).
  Same-relation chains are structurally never generated (walk-level filter),
  so the Nordics back-edge detours cannot return and NO evidence-layer rule
  is needed (supersedes the earlier proposed hop-gate rule in
  specs/direction_truncation_audit.md §3.1).
- Fixtures (all PASS, live): Bernie = both-direction full set incl. multi-head
  'Bernie|Bonnie|Hank --team--> Milwaukee Brewers'; Nordics = still 1 line
  (contains->contains chains absent); Greeley P1+P2 unchanged (now robust to
  single-direction data); Ethiopia records intact; unit tests pass.
- Status: awaiting user ratification; trivially revertible (single-file +20).

### RULING APPLIED: original per-relation last-hop walk restored (2026-08-19)
- User clarified the original branch design: enumerate ALL paths within k
  hops, keep those whose LAST hop rides a declared relation, display by path
  length priority; per-relation queues so one relation's hit never blocks
  another's search. k_queue_traverse (the fallback in THIS repo) is that
  design verbatim; the mode-level primary walk had drifted into hit-and-stop
  (CASE A continue + CASE B non-target-only) — the root of the whole
  orientation-luck family.
- Implemented (supersedes the +20 selected-chain patch): _hit_paths now
  enumerates 2-hop last-hop completions from EVERY first hop (target-hit or
  not; the old CASE A CVT extension is subsumed). CASE C (CVT-transparent
  3-edge) now also applies to target first hops. Walk = pure enumerator.
- Detour pruning moved to adjudication, where the user's invariant says
  direction constraints live: _hop_ok new rule — a mid hop REPEATING the
  last-hop relation over a NAMED node, when that relation has a direct
  instantiation at the center, is a back-edge detour (Nordics
  contains→contains via Scandinavia rejected; CVT same-rel passage stays
  transparent).
- Fixtures all PASS: Bernie 3 mascots both directions; Nordics 1 line
  (chains now generated by walk, rejected by gate — architecture as
  designed); Greeley P1+P2 (now structural, direction-luck-free); Ethiopia
  records intact. Unit tests pass. 20-case r267 smoke: no exceptions, walks
  bounded (≤0.67s/call, avg 8.2 patterns — display budgets absorb; P2
  economy question unchanged, rendering-rewrite batch).

### Stop-motion specimen validates the fix stack (2026-08-19)
- WebQTest-1923_c606 (genre Stop motion ∩ Miley Cyrus films): pre-fix sg1
  showed ONLY the 40-program tv.tv_program.genre mass — films_in_this_genre
  (0 direct edges at the genre center) was silently dropped by the OLD
  set-level hop gate (child_genres unselected named mid + sibling selected
  rels having direct edges = the Greeley shape). Post-fix: P6/P7 deliver
  'Stop motion --child_genres--> Clay animation --films_in_this_genre--> 7
  films' structurally. Gold [Bolt, Super Rhino] is a CONFIRMED mismatch
  (CGI films, no Stop motion edges in graph) — low F1 is data's fault.
- Residual: tv 40 direct edges → only 28 triples (support-paths 24 cap,
  audit D5 truncation economy) → rendering rewrite batch.

### Hallucination-detector fix + SYSTEM JOIN (Stop-motion ∩ Miley specimen, 2026-08-19)
- Detector bug found (user): the freeze guard rejected ANY re-declaration
  without new retrieval — including faithful VERBATIM re-statements the model
  emits when composing the §18 checklist. Warning text even claimed "tried to
  change bindings" when nothing changed (false accusation, twice per episode
  under rescue pressure). FIX: idempotence = normalized SET equality vs the
  standing fact_bindings (order-insensitive); hallucination filter moved
  BEFORE the freeze check (stored bindings are post-filter; comparing
  pre-filter text misread once-filtered re-statements as value changes);
  frozen rejection now suppresses the same-turn halluc flag (one message).
- Hidden store bug exposed on the way: vb[?var] is keyed by VARIABLE — the
  second subgraph binding the same var OVERWROTE the first (intersection
  information destroyed). Now ctx.fact_bindings[fid] keeps per-fid values.
- SYSTEM JOIN (user ruling "层序层面给出两个子图的交集"): when ≥2 fids bind
  the same var, the harness computes the intersection (normalized, original
  casing), sets vb[var] = intersection (so ?var expansions + answer bindings
  are the join, not one side's list), and injects a ⌗ SYSTEM JOIN note
  (non-empty: "answer with THESE entities only"; empty: "EMPTY — a conscious
  empty answer is CORRECT, do not dump one side's list").
- Rescue alignment: in-loop empty-answer rescue skips when joins exist and
  ALL are empty (deliberate graph-grounded empty); rescue_terminal_answer
  becomes join-aware — all-empty joins → no dump; non-empty joins → recover
  the INTERSECTION instead of a raw one-side checkpoint list (kills the
  pred#42/gold#1 overshoot family for joined plans).
- Verified: T1-T6 matrix (verbatim restatement silent / real change frozen /
  join computed / empty join / rescue gates / casing preserved) + unit tests.
  Expected impact: the 47-case OVERSHOOT bucket's multi-anchor slice (Sandler/
  Miley/Favreau 'which movie AND crew-member' family) joins now happen
  harness-side.

### Cross-subgraph center repair implemented + retreat philosophy (2026-08-19)
- User proposal 2 (anchor wrong / relations right): implemented as a THIRD
  repair mode. Mechanism was ALREADY legal (subgraph_entities accumulates
  globally — any retrieved entity passes the boundary check for any fact);
  the model just never knew. Now taught in THREE places: seq_tools
  entity_error note (both sites: _entity_correction result + retrieve_subgraph
  bad_name path), the boundary error text, and SEQ_AGENTS.md §14 new
  subsection "Cross-subgraph center repair" (+ §15 anchor-ban carve-out
  note: re-centering on ALREADY-RETRIEVED evidence with same relations is a
  repair, not a re-plan).
- User question 1 (detect-but-cannot-retreat) — philosophy position recorded:
  immutability bans were a MEANS against two diseases (Ramble loops; noise-
  driven re-plans per the variance experiments), not an end. The principled
  fix distinguishes AIMLESS rambling (no new info, same action — stays
  banned, repeat-gate) from GROUNDED retreat (carries a mismatch DIAGNOSIS +
  a different action + consumes budget — should be legal). Three carriers:
  ① ✗ mismatch closure with diagnosis; ② cross-subgraph center repair
  (done); ③ bounded ONE-SHOT fact replacement in the same fid slot after a
  diagnosed ✗ mismatch — the previously-shelved bounded re-plan, now gated
  on an evidence-citing diagnosis (AWAITING USER RULING before implementing;
  variance risk was the original objection, the diagnosis gate addresses it).
- NOTE: fixstack2c single-stage 267 rerun in flight when these notes were
  written (prompt edits below land in the NEXT run, not fixstack2c).

### fixstack2 FINAL (2026-08-19, corrected JOIN semantics, CASE_BATCH=1000)
- 267-cohort on full fix stack (answer_type prompt + per-relation hop gate +
  CH state machine + Bernie Option-B anchor + original-design walk restore +
  hallucination idempotence + JOIN v2 empty-not-enforced):
  **meanF1 0.7512→0.7544, EM 165→170 (61.8%→63.7%), empty 5→6, rescued
  11→7.** vs the first JOIN-v1 attempt (0.7254/158/12): the Thundera
  correction recovered +2.9pp/+12EM. Mechanism debt cleared: answer_type
  rejections 267→0, frozen-false-positives 91→7, SYSTEM JOIN 78 injections.
- Specimen scoreboard: CH/Greeley/Parkdale/Hunnam/France-co2/Ron-Howard
  family all 0→1; 3/4 JOIN-v1 casualties fully recovered (Thundera/Teklel/
  TaylorSwift 1.00; Miley-Zigman 1.00→0.67 — non-empty join over a partial
  list, acceptable). Remaining drops are small (rescue-tightened fake scores:
  Lautner-runtime 0.07→0).
- Gains 48 / drops 46 / flat 173. Verdict: ship. (This run predates the
  cross-subgraph center-repair prompt — lands in the TRAIN rollout below.)
- OPS note: RESUME + enlarged CASE_BATCH is UNSAFE (skip condition is
  stage-granular: done_cases=100 with batch=1000 re-runs everything and
  DUPLICATES records). Either resume at the original batch or start fresh.

### train_v4 diagnostic on NEW harness (2026-08-19, harness-v2 baseline)
- 1000 cases × G=1 TEMP=0.3 CASE_BATCH=1000: **meanF1 0.8049, EM 722
  (72.2%), empty 8, rescued 20** (reports/train_v4_diag_harnessv2.json).
  Mechanisms live: at-rejections 0, frozen warnings 11 (true value-changes),
  SYSTEM JOIN 235, cross-subgraph-center note surfaced 22×, planless 9.
- Attribution of 278 errors: ANSWER-LAYER 216 (78%) / RETRIEVAL 54 (19%) /
  empty 8 — confirms the queued §18 v2 + rendering batch is aimed at the
  dominant bucket.
- Training flow launched per convention (errors G=6 + balance G=4):
  ① RUNNING: 278 errors × G=6 TEMP=0.8 → reports/train_v2h_err278_g6.json
  ② NEXT: 150 perfect (seed 19) × G=4 → tmp/train_v2h_balance150.txt
  → merge → IG → new training round on the new harness.

### Training rollout v2h error batch DONE (2026-08-19)
- 278 errors × G=6 TEMP=0.8 (reports/train_v2h_err278_g6.json): 1668 trajs,
  182/278 cases with within-case variance (trainable), 96 dead groups,
  127 cases with ≥1 perfect trajectory (contrastive signal). Trajectory F1
  mean 0.4237 / per-case max mean 0.6457 (hard cohort as expected).
- Balance batch (150 perfect × G=4) launched → reports/train_v2h_bal150_g4.json.
  Next: merge → IG filtering → training round on the new harness.

### Training round v2h launched on new harness (2026-08-19)
- Data: 278 errors × G=6 (1668 trajs; 182 variance, 127 with perfect traj) +
  150 perfect × G=4 (600 trajs; 147 keep-perfect) = 2268 merged
  (reports/train_v2h_merged.json).
- IG pass (seq_advantage data mode; PYTHONPATH=/zhaoshu/subgraph REQUIRED —
  script import fails without it): 15207 pairs, 12 MID filtered → reallocate
  wrote 2256 trainer records (tmp/seq_train_v2h.jsonl; single-SG connected
  1509/1770). IG json kept at tmp/seq_ig_v2h.json (container /tmp copies die
  on reset — project tmp/ is the durable one).
- Trainer smoke (MAX_STEPS=4) PASSED → checkpoint/seq_grpo_v2h_smoke.
  FULL RUN in flight: DATASET=tmp/seq_train_v2h.jsonl OUTPUT=checkpoint/
  seq_grpo_v2h, 113 steps @ eff-16, ~48s/step ETA ~80min
  (logs/seq_train_v2h_full.log).
- After training: eval the v2h policy (POLICY=seq_grpo_v2h? adapter name per
  checkpoint dir) on the 267 cohort + a fresh test slice; compare vs
  fixstack2 harness-only baseline (0.7544/170EM on r267; 0.8049/722EM on
  train diag).

### v2h training verdict: SEVENTH consecutive parity-or-worse (2026-08-19)
- checkpoint/seq_grpo_v2h (113 steps on 2256 new-harness records) evaluated
  on r267 (TEMP=0.3 G=1, LoRA via POLICY=seq_grpo_v2h):
  **meanF1 0.7544→0.7281 (−2.6pp), EM 170→164, empty 6=6.** Gains 40 /
  drops 50 / flat 177. Several 0→1 gains (Ron Howard first-release, Igor of
  Kiev, 1994 NBA) but net negative — same shape as v2/v7/v8/v12/v13/v14.
- Conclusion unchanged across 7 formulations (scalar/per-turn/discrete/
  targeted+balanced/new-harness data): the LoRA lever does not move this
  agent; the harness/prompt/rules lever does (r267 +6.9pp from 0.68→0.7544
  harness fixes today). The dominant remaining bucket is ANSWER-LAYER (78%
  of train diag errors) — the queued §18 v2 + rendering rewrite + IDF batch
  is the evidence-backed next move, not more training rounds.
- Artifacts: reports/regress267_v2h.json; training log logs/seq_train_v2h_
  full.log; smoke checkpoint can be deleted (checkpoint/seq_grpo_v2h_smoke).

### CVT-chain deadlock + pool renderability (Norwood specimen, 2026-08-22)
- Bug 1 (user: "模型给出cvt后又跟调度冲突"): the v2h plan made f2 walk FROM
  ?nomination, whose only value is the nomination CVT m.0bb28t6. The §7.5
  strip guard correctly emptied the binding → "no declared bindings" error →
  the model re-declared the CVT and retried → 16-turn declare/error loop,
  answer = the CVT id, F1 0 (base run solved it 1.0 by planning 2 facts).
  FIX ×3: ① all-events declarations record ctx.cvt_empty_var=(var,fid);
  ② the unbound-var error for that var becomes a MOOT-CLOSURE exit ("can
  NEVER bind… close [fid ✗ moot], the target is inside the brackets");
  ③ loop breaker: 2nd occurrence → harness closes the fact moot itself and
  orders the next fact centered on a bracket attribute entity.
- Bug 2 (user: "关系不可达又来了，能选必可达"): students_graduates was offered
  but ALL 5 instantiations end on attribute-less CVT stubs (snapshot kept
  only the back-edge; g.xxx nodes have NO other edges) — walk enumerates
  them, pat_triples carry them, renderer rule ⑥ correctly drops bare CVT
  tails → selection pays nothing. Greeley campuses = same disease via
  self-loops. FIX: pool RENDERABILITY filter in _reach2_relids — a relation
  stays offered only if some instantiation pays: named far side (self-loops
  never pay), or a CVT that carries information BEYOND that very edge (a
  named neighbor OTHER than the edge's other endpoint — first _pays draft
  "any named side" was wrong: the anchor side is always named).
- Verified: Norwood sg dropped, education/institution kept; Ethiopia CVT
  family intact; Bernie both directions intact; Greeley campuses dropped /
  school_type+contains kept; unit tests pass.

### General fixes round (drops review, 2026-08-22) — user framing: case级修复无价值
- ① PRELINK HINT NOISE FILTER: prelink already GTE-ranks the qentity's 1-hop
  neighbor relations (CVT both-sides) by the original question — the gap was
  the pool's noise classes NOT applied to the hint pool (common.topic.
  notable_for outranked government.* for the Minister-of-State qentity).
  Fixed: hint pool filtered by _is_noisy_path_relation (9→6 rels, gov.* now
  in top-3). Answered user's question: yes the 1-hop CVT ranking existed.
- ② CVT NOTE WORDING RULING (user): the prompt teaches ONLY the CVT essence
  (abstract record), how it behaves (attributes auto-appear — the SYSTEM's
  business, unconditional from the model's view), and the ban (never answer
  OR BIND CVT ids). My "conditional auto-reveal" contract edits were REVERTED
  — retrieval-layer mechanics do not belong in the prompt; discriminator
  visibility is the system's guarantee (rendering-rewrite record groups).
  Kept one addition: "NEVER variable bindings" in the subgraph note.
- ③ FRANCE/CENTER-BORROW REPLAY: with sg1's ?country bindings as centers +
  the model's own sg2 government relations, the walk yields the Minister-of-
  State records for Belgium (Henri Rolin) and Monaco (Michel Roger) = gold.
  The mechanism (cross-subgraph center repair) exists; the failing run
  predates it. The "model saw the wrong plan but couldn't adjust" family is
  covered by ①hints ②center-repair ③pending diagnosed-fact-replacement.
- Liszt employment_history single-record: NOT a bug — the snapshot has exactly
  1 employment edge on the node (data limitation).
- GTE general levers (awaiting ruling): V2-instruct neutral rewrite validated
  on the existing gold-relation suite; candidate head→type-word de-bias; IDF
  leg. NO family-collapse (user: no universality).

### §1.5 error-correction ladder + decision-point replay verdict (2026-08-22)
- User philosophy (认可, data-backed): on mismatch, diagnose PLAN first
  (close ✗ mismatch with diagnosis / borrow center), then RELATION layer
  (pick the skipped sibling candidates), then REPHRASE the sub-question
  (GTE deterministic — same wording = same window, a repeat is wasted).
  Injected as SEQ_AGENTS.md §1.5 (opening, before tool sequence) + §14
  repair gate widened to "evidence mismatch" (was: empty/off-target only).
- DECISION-POINT REPLAY (user-designed experiment, NOT full rerun): cut
  error trajectories at the first MID-COURSE detection (after ≥1
  retrieve_subgraph result — the first probe draft cut at turn-0 plan
  thinking, a regex artifact), swap in the new system prompt, one
  generation, compare the next action (ARGUMENT-aware, not line-1).
  scripts/probe_ladder_replay.py; tmp/ladder_replay.json.
- Verdict on 47 probes (17 A-locked + 30 C-passive): **16/47 (34%) take a
  corrective action** (back to retrieval with new question/relations,
  better ✗ diagnoses — e.g. Kim-Richards refused the checkpoint and went
  for the length discriminator; co2/Lala resumed the co2 fact), 22 replay
  the original verbatim, 8 format-only diffs. Mechanism VIABLE but not
  sufficient — prompt injection moves a third of frozen decision points.
- End-to-end err97 replay launched for the net F1 verdict
  (reports/err97_ladder_e2e.json).

### Variance verdict + RESTART mechanism (2026-08-22)
- VARIANCE RUN B (same new-stack, second sample, r267): A=163/B=165 EM,
  **self-churn 62/267 (23%)** — the "40 lost EM vs fixstack2" sits INSIDE
  this noise band → new stack is statistically PAR with the old on r267
  (163/165 vs 170), while the err97 gain (+42 EM) is real movement of the
  systematic-error cohort. r267 hard core: 72 wrong in BOTH samples.
- RESTART mechanism implemented (user ruling: 模型认知探索错了→带诊断整案重答,
  NOT answer-layer patching): declaration `[restart: diagnosis]` → harness
  resets messages to [system, question+anchors] + lesson turn carrying the
  diagnosis; resets state machine (INIT) + all accumulated stores
  (bindings/facts/joins/closed/evidence/triples/anti-loop); ONE restart per
  case (second rejected+return); turn budget SHARED between attempts.
  Taught in SEQ_AGENTS.md §1.5 level 4 (use only when STUCK). Unit-verified
  (reset completeness / lesson seeding / one-shot rejection).
- e2e validation in flight: err97 × restart (vs ladderstack A 0.6064/42EM).

### RESTART reshaped to NONE-verdict (user ruling, 2026-08-22)
- Redesign: the model never asks for a restart — it declares
  `[explore ✗ none]` ONLY on COMPLETE exploration failure (nothing
  answer-relevant retrieved; PARTIAL relevance → continue via ladder 1-3).
  First none → system restart once; the lesson carries the DIAGNOSIS plus
  the relations attempt-1 tried (dead-end list) so attempt-2 plans
  differently instead of resampling. Second none → REJECTED, the attempt
  MUST answer (explicit empty allowed) — kills variance loops. Turn budget
  shared. Free-form `[restart:]` trigger REMOVED. §1.5 level 4 rewritten.
- Scenario analysis backing the design: (A) complete-failure cases are pure
  upside for restart (current trajectory scores 0 anyway); (B) PARTIAL
  success must NOT restart — the 38/40 answer-layer variance shows partial
  cases lose on BINDING, cheaper to fix by continuing/comparing than
  risking a re-explore; (C) rich-but-wrong-direction cases belong to ladder
  1-3 (borrowed center / sibling relations / rephrase) — restart only when
  those are exhausted; (D) pure sampling-variance errors are contained by
  the must-answer-second-attempt rule.
- Unit-verified: restart-on-none (store reset / dead-end lesson / INIT) +
  second-none rejection. Unit tests pass.

### Restart mechanism verdict: no traction, SHELVED (2026-08-22)
- Three err97 variants (97-case cohort, temp 0.3): ladder-only 0.6064/42EM,
  free-restart 0.6205/43EM, NONE-verdict 0.5935/40EM — statistically flat
  (same variance band). CRITICAL: BOTH model-facing declarations
  (`[restart: …]` and `[explore ✗ none]`) were used **0 times** — the model
  never spontaneously adopts new declaration verbs, no matter the teaching;
  only the deeply-trained checkpoint family ([fid ✓/✗]) gets used.
- System-side mechanical triggers are too narrow: zero-✓-checkpoints fires
  on 3/97 err97 (2 wrong) and would false-fire on 2 EM cases; empty-answer
  fires on 1/97. Complete-failure signatures are RARE because most wrong
  cases have PARTIAL exploration success (the answer-layer variance family
  again).
- Verdict: keep the code (harmless — never fires), shelve the mechanism.
  The err97 +42EM came from the STACK (ladder teaching + V3 + notes), not
  restart. The evidence-backed next lever remains §18 v2 + rendering
  rewrite (38/40 answer-layer variance; 78% of train-diag errors). Current
  stack is PAR on r267 (163/165/170 within ±23% churn) and +28pp on the
  error cohort — ship-candidate for the next full-test evaluation.

### EVIDENCE_STATUS adoption experiments — 3 iterations, verdict (2026-08-22)
- Codex-audit four-state design probed via decision-point replay (error-arm
  30 mid-course detection cuts + healthy-arm 30 EM cuts, temp 0.3):
  iter1 prose-mandatory: adoption 11/60; iter2 examples+MUST phrasing:
  **46/60 (healthy 28/30, 27 SUPPORTED — near-zero false alarm; mapping
  100% consistent)**; iter3 philosophy-first + softer "guides not
  bureaucracy" + two failure-scene demos: adoption DROPPED to 39/60
  (healthy 28→9) — mandatory phrasing drives compliance; philosophy
  preamble dilutes it.
- CRITICAL NEGATIVE: RELATION_MISMATCH / PLAN_MISMATCH outputs = **0 across
  ALL three framings** — the model self-labels troubled evidence as
  PARTIAL/SUPPORTED (self-affirmation bias), never mismatch. And the
  objective-emptiness hint never fired (0/30 error cuts had empty results —
  their evidence is rich-but-wrong).
- Verdict (hybrid): ① production ships the TWO-state
  EVIDENCE_STATUS: SUPPORTED | PARTIAL in iter2 form (mandatory phrasing +
  example lines) — proven adoption/discrimination/consistency, one-line
  cost, makes PARTIAL explicit for the answer rules; ② mismatch detection
  moves HARNESS-side: RELATION_MISMATCH only on objective walk-empty
  (narrow but sound); PLAN_MISMATCH stays as ladder prose (no cheap
  objective signal); ③ the audit's variance killers — ANSWER READY gate,
  mechanical BASE_BINDINGS ledger, answer-as-pure-function — are
  independent of the status machine and remain the big lever (38/40
  answer-layer variance).

### ANSWER-LAYER calibration ruling (user, 2026-08-22): least-wrong, not pure-function
- 作答层不能卡死成纯函数状态机 — questions are AMBIGUOUS by nature:
  similar phrasings ask for "the latest" vs "all", one vs many. The answer
  stage's standard is 给出基于当前信息最不会错的答案 (the least-wrong
  answer the current evidence supports), NOT a deterministic function.
- Split Codex's answer-purity proposal accordingly:
  * MECHANICAL stays mechanical: BASE_BINDINGS ledger / shared-variable
    intersections are objective — harness-computed, model copies (kills the
    re-derivation variance).
  * INTERPRETATION stays judgment: question intent (latest/all, one/many,
    constraint scoping) is the MODEL's call at answer time — governed by
    the §4 turn-0 type analysis and echoed C_type; when the phrasing is
    ambiguous, prefer the reading the retrieved evidence fully supports.
  * The "may not reconsider retrieval" ban is SCOPED to retrieval
    correctness (no re-judging relation choices at answer time); it never
    bans question interpretation or discriminator application.
  * ANSWER READY gate survives for FLOW variance (don't answer before
    discriminator facts close) but with the ambiguity escape: if the
    discriminator is missing AND unobtainable within budget, answer
    least-wrong under the PARTIAL/UNKNOWN rules instead of stalling.

### IDF ranking leg REJECTED (user ruling, 2026-08-22 — closing a recurring item)
- IDF leg (cos × log(N/df)) is OFF the roadmap: corpus-frequency heuristic,
  no universality (binds ranking to the train distribution). It kept
  resurfacing in pending lists — this entry closes it. GTE ranking levers
  that remain valid: instruct wording (V3 shipped) + candidate-format
  de-bias (pending, general) — nothing frequency-based.

### Calibrated answer batch SHIPPED to validation (2026-08-22)
- Implemented: ① §1.5 production = two-state EVIDENCE_STATUS (SUPPORTED |
  PARTIAL, MUST phrasing + Example-1 status line — the iter2 form that
  adopted at 93%) with the repair ladder folded under PARTIAL; NONE level
  removed (restart code stays dormant). ② §18 READY gate (BOUND≠READY;
  close discriminator facts first; ambiguity escape → least-wrong under
  PARTIAL/UNKNOWN), BASE_BINDINGS copy-from-ledger instruction, scoped
  no-re-judging (retrieval only; question interpretation explicitly the
  model's job). ③ plan note aligned (status + READY semantics).
  ④ walk-empty error upgraded to RELATION_MISMATCH diagnosis text.
  ⑤ BINDING LEDGER harness injection: once all declared facts are closed,
  one authoritative user turn lists per-variable effective bindings
  (declared sets ∪ shared-var joins, original casing) — verified by unit
  sim; answer stage copies instead of re-deriving. IDF leg REMOVED from
  roadmap (user rejection: no universality).
- Validation running: err97 (reports/err97_status.json) → then full 267.

### Pool-compute perf fix (2026-08-22, user caught the slowdown)
- Symptom: status-batch 267 run at ~6min/round vs 4min baseline. Profile:
  `_reach2_relids`'s BFS `_adj` scanned ALL edges PER NODE — O(V×E) on hubs
  (France: 17.5k calls, 0.97s in ONE pool call, in the event loop, blocking
  all concurrent cases). Fix ×2: ① per-ctx FULL adjacency index built once
  (single O(E) pass, cached on ctx._full_adj_idx — France 1050ms → 438ms
  first / 3ms cached); ② per-relation edge lists + precomputed pays bits
  for the walkability/renderability filters (O(pool×edges) → O(pool)).
  Fixture semantics PASS (France gov-rels / Namath sg-drop / Greeley
  campuses-drop), unit tests pass.
- Remaining slowdown is BY DESIGN: the READY gate runs cases longer (16→
  expected 18-20 LLM rounds; err97 turns 6.8→7.2). This is the cost of
  closing discriminator facts before answering.

### Status-batch full-267 verdict (2026-08-22): PAR with mechanisms live
- regress267_status_a (perf-optimized pool): meanF1 0.7384, EM 165/267,
  empty 2, turns 6.7. vs fixstack2 170 / ladder A-B 163-165 — all inside
  the ±23% same-stack churn band (statistically par). vs ladder-A: gains
  52 / drops 41. Mechanisms live at scale: EVIDENCE_STATUS 598 (~2.2/case),
  BINDING LEDGER 221. Empties 6→2 across the new stacks (join/rescue
  alignment). err97 cohort holds (0.59 within its 39-43 EM band, baseline
  was 0.32).
- Perf fix verified in-run: 267 finished in ~33 min (~2min/round) vs the
  pre-fix ~6min/round — the O(E) adjacency index + per-relation edge lists
  removed the event-loop stalls; remaining round growth (16→18) is the
  READY gate's designed cost.
- Standing verdict: the cumulative stack (answer_type + Greeley hop gate +
  CH + Bernie + walk restore + join + center-repair + prelink filter +
  renderability + V3 + ladder + two-state status + READY + ledger) is the
  ship candidate — parity on the full cohort with real error-cohort
  movement. Next lever per all evidence: RENDERING rewrite (answer-layer
  variance remains the dominant family).

### EVIDENCE_STATUS ROLLED BACK (decorative — trajectory audit, 2026-08-22)
- Audit of regress267_status_a: PARTIAL was followed by a REAL repair move
  only 2/33 times (both non-EM); total repair moves 304 vs fixstack2's 297
  on the same cases — the status line changed NOTHING in behavior. Verdict
  per user's criterion (no triggered correction → rollback): decorative.
- Rolled back: §1.5 two-state status + Example-1 status line + plan-note
  status requirement. §1.5 returns to the plain repair ladder (top-up /
  borrowed center / rephrase / mismatch closure). KEPT: perf fixes (pure
  win), walk-empty RELATION_MISMATCH hint, READY-gate language, BINDING
  LEDGER (superseded soon by V2.1's Evidence Commit if adopted).
- V2.1 (Codex full redesign: Question Contract R/D ids, append-only PLAN
  EXTEND, Evidence Commit with SUPPORT/UNRESOLVED matrix replacing strict
  join, two-stage ANSWER_ANALYSIS→ANSWER_READY) — harness-gap analysis
  recorded separately; prototype path = ablation A/B/C on 30-50 curated
  "right-relations shaky-answer" + "one-branch-failed" cases with the
  same-evidence flip-rate as primary metric, BEFORE replacing production.

### V2.1 harness adaptation implemented + cohort ablation launched (2026-08-22)
- Code-level correspondence done: ① flat parser handles R*.kind/text lines
  and sgN.fM.covers (was SILENTLY EATEN by the fact branch); ② harness
  parses requirements + fact_covers into SeqAgentState; ③ [PLAN EXTEND]
  block in process_turn (append-only, validates requirement∈contract &
  UNPLANNED — NB dict-values trap: `rid in covers_dict` checks KEYS, must
  be .values() — and anchor∈question-entities|bound-vars); ④ SYSTEM JOIN
  hard-enforcement REMOVED both directions (V2.1: missing evidence ≠
  negative); ⑤ BINDING LEDGER upgraded to EVIDENCE COMMIT (CANDIDATES +
  SUPPORT_BY_REQUIREMENT from covers mapping + full-support count +
  UNRESOLVED≠CONTRADICTED note) with TWO-STAGE gate: first answer after
  commit intercepted → ANSWER_ANALYSIS required → ANSWER_READY signal;
  ⑥ SEQ_AGENTS_V21.md (Codex text + runtime protocol additions: flat
  format, checkpoints, CVT ban, determinism, budget); switch via
  SEQ_PROMPT=V21.
- Unit-verified: plan parse (R lines/covers), EXTEND accept/reject (dup
  coverage, unknown R), two-stage gate. Cohort: 48 cases (54 shaky-answer
  flip cases ∩ evidence-complete + 25 one-branch-failed), tmp/v21_cohort.txt.
- Ablation running: V21 × G=3 TEMP=0.3 (flip-rate within-config is the
  primary metric per Codex; current-stack flip baselines exist from
  ladderstack A/B).

### V2.1 first real signal (2026-08-22, format-fixed ablation)
- First V21 run collapsed (F1 0.05): my condensed V21 prompt omitted the
  exact tool-call formats → the model called retrieve_relations with
  `entities:` instead of `center:` — EVERY retrieval errored. Lesson
  (third time): FORMAT EXAMPLES ARE LOAD-BEARING; any prompt rewrite must
  carry the full tool-call format block verbatim.
- Format-fixed V21 (48-cohort × G=3, temp 0.3): **flip 71%→62%, meanF1
  0.6143→0.6631 (+4.9pp), best-of-3 0.8147, any-EM 36/48** — the FIRST
  configuration to beat the current stack beyond the noise band on this
  hardest cohort (all prior batches were par). Two-stage flow obeyed
  (ANALYSIS 438×, format errors 0). EXTEND accepted 0/63 attempts (model
  tries to extend already-covered requirements — the gate works but the
  model misjudges coverage; acceptable for now, coverage check teaches).
  COMMIT fired only 8× — the all-facts-closed condition rarely coincides
  (many cases answer via budget-end path); needs the READY-condition audit.
- Next: full-267 V21 validation (vs current stack 170/163/165 band).

### Eval wall-time audit (user pushback, 2026-08-22)
- Diagnosis (GPU 98-100% util, rollout proc 6.7% CPU): the loop is
  LLM-DECODE-bound, not dispatch-bound. Decode math: 267 × ~18 rounds ×
  ~1.2k tok ≈ 350k tok/round ÷ ~3k tok/s aggregate ≈ 2min/round floor with
  the full cohort active. WALK_POOL=8 now set (walks were INLINE-serialized
  before — every prior run!). V21 prompt is 11.7k chars (3× SHORTER than the
  38.8k current) — length is NOT the slowdown; extra turns (ANALYSIS/EXTEND/
  gates) are. Do NOT extrapolate early-round pace: rounds shrink as cases
  complete; status_a2's true total was ~33min (current stack).
- OPS RULES for experiments: always WALK_POOL=8; expected walls: current
  stack ~33min/267 G=1, V21 ~40-50min (analysis turns); fast iteration =
  the 48-cohort (~6-8min G=1, ~20min G=3); THINK_BUDGET cut (1000→600) is
  an available 2× decode lever but needs a quality A/B before adoption.

### Turn-inflation root cause + gate-feedback fix (user caught it, 2026-08-22)
- User's speed math was right: decode is only half the story — the other
  half is FEEDBACK turns. Audit (48-cohort): current stack 7.0 turns/case
  (3% wasted); V21 **16.0 turns/case (≈ full budget), 15% wasted (343)**.
  Single biggest source: **plan-IMMUTABLE rejections ×243** — V21's
  "plan is append-only extensible" philosophy made the model RE-PLAN, and
  the old immutable gate stonewalled it. EXTEND rejections ×45 (model
  extends already-covered requirements).
- Gate feedback upgraded from dead-ends to signposts: ① plan re-emit →
  rejection now CARRIES the [PLAN EXTEND] template + the "plan locks
  facts, not retrieval choices" clarification; ② EXTEND rejection now
  LISTS current coverage (fid→R) and redirects to relation repair when
  the requirement is already covered.
- Expected effect: kills the 243-turn waste class; 48-cohort re-run to
  verify turn distribution before the next full-267.

### System-layer format decoupling (user ruling: 系统层与大模型层分开修, 2026-08-22)
- Audit of regress267_v21 (267 runs): 561 "(unparsed)" turns decomposed into
  193 checkpoint+analysis blocks + 60 checkpoint-only + 35 ANSWER_ANALYSIS +
  273 post-answer prose — nearly ALL legal declarations the harness treated
  as garbage, then nudged with a JSON-teaching error while the protocol is
  FLAT (the model's format oscillation was SYSTEM-INDUCED). Plus 33 schema
  rejections that were plain scalars-where-lists.
- Fixes (system layer, flat/YAML is THE protocol — user direction; JSON kept
  only as parser tolerance): ① no-tool path rewritten — ANSWER_ANALYSIS
  turns now fire ANSWER_READY IMMEDIATELY (the tail-side signal was dead
  behind this early return — the two-stage flow was effectively broken),
  checkpoint-only turns get a soft "recorded, next tool:" acknowledgement,
  checklist turns get the FLAT answer template, generic nudge teaches flat;
  ② validate_args coerces str→[str] for entities/center/relations before
  rejecting; ③ all JSON-teaching error text removed from the feedback paths.
- Verified: coercion T1/T2, ANALYSIS→READY T3, soft-checkpoint T4; unit
  tests pass. Model-layer (purity/satisficing) remains prompt-side per the
  ruling — separate batch.
- V21 full-267 verdict recorded earlier today: **0.7855 / 182 EM (+3.1pp /
  +12 EM vs fixstack2 170 — first beyond-noise full-cohort win), DESPITE
  16.0 avg turns and 560 IMMUTABLE-rejection waste.**

### Purity-removal batch + CRITICAL structural repair (2026-08-22 night)
- ① Tool note aligned to V2.1 sufficient-coverage (the "select ALL 2-4" wide-
  selection wording removed — user: conflicts with design).
- ② V21 prompt de-purity per Codex: SATISFICING + Stop Rule ("would this
  change WHICH NAMED ENTITY") front of §2; Minimal Constraint (no temporal
  overlap/main-role/currentness unless stated; world knowledge may parse,
  never audit); answer_type = SEMANTIC ROLE HINT (year/date/number answers
  are NAMED entities — "2008 NBA Finals" satisfies "what year"); ANSWER_
  ANALYSIS = selection stage, no new requirements.
- ③ Purity-loop detector (harness): per-center question similarity (tokens
  len≥3, inter≥3, jac≥.45 OR cont≥.6 OR inter≥4&jac≥.3) as a STREAK;
  3rd similar query → forced Stop-Rule reminder; 4th → harness closes the
  fact ✗ unresolved-after-repair. Verified: tenure paraphrase chain fires,
  5 distinct intents don't.
- CRITICAL STRUCTURAL REPAIR discovered en route: an earlier edit had left
  STAGE-GATE+seq_validate+purity indented INSIDE the repeat-gate branch
  after its return — validate/phase-gates/purity were DEAD CODE and every
  tool dispatched UNVALIDATED (explains the two-stage gate never
  intercepting in v21 runs). Region rebuilt cleanly; STAGE GATE now
  intercepts (T4), validate back on path. OPS RULE: after any indentation-
  sensitive edit, run an instrumented single-turn smoke — dead-code zones
  from mis-indentation are silent.

### Post-purity-batch fixes (2026-08-22 night, user review round)
- Turn-count verification: the purity t10 run has ZERO 16-turn cases (max
  11, avg 7.5; n_turns ≡ assistant-message count verified per-record). The
  "many still 16" impression came from reading the OLD dump
  (tmp/v21_review.md = pre-fix baseline); the new one is
  tmp/v21_purity_t10_review.md.
- FREEZE-GATE REFINEMENT ALLOWANCE (Belgium/GMT specimen): the two-stage
  analysis NARROWS standing bindings ([W-Europe|Europe|Eurasia|N-Hemisphere]
  → [Europe]) — that is discrimination, not hallucination. The frozen gate
  now accepts SUBSET re-declarations (updates the lock + vb) and keeps
  rejecting only introductions outside the standing set. Verified: subset
  accepted silently; out-of-domain values still stripped by the
  subgraph-evidence check (Mars case: strip → surviving value equals
  standing → idempotent silent path — correct, no false warning).
- Wall-time note for small batches: 20-traj run = 82s engine load (fixed
  tax) + latency-bound rounds (slowest single generation ~30-40s at
  thinking 1000) + ~5min unattributed inter-round overhead (under audit);
  batch amortization is why 3.3s/case only holds at 267-scale.

### Persistent-server mode SHIPPED (user design 固化为类API, 2026-08-22)
- LLM_MODE=http on seq_rollout: HTTPChatBatch (kgqa/llm/http_batch.py) —
  sync chat_batch bridge over a background-thread event loop, POSTs the
  persistent :8000 vLLM server with thinking_token_budget + sampling
  params; reasoning field preserved. Verified on t10: quality par
  (0.560/9EM vs 0.606/8EM, turns 7.0 vs 7.5), llm=102s identical, and the
  ~2.5-min engine spawn/compile tax GONE (run finished in ≤200s wall).
  OPS: keep the server resident between runs; LoRA POLICY still requires
  the in-process engine (guarded).
- Timing correction on record: the user's aggregate-throughput math
  (~3k tok/s) was RIGHT — llm wall matches batch math; the earlier
  "slowest-single-stream bounds the round" claim was wrong for offline
  batch inference.

### V21 FINAL (purity batch, http mode): 0.7606/179EM, 7.8 turns, ZERO empty (2026-08-22)
- regress267_v21_final: meanF1 0.7606, EM 179/267 (67.0%), empty **0**,
  turns 7.8 (was 16.0), wall ~17min via http+pool (round16 t=994s,
  vs in-process ~35-50min). vs fixstack2 0.7544/170: +0.6pp/+9EM.
  vs V21-pre-purity 0.7855/182: −2.5pp/−3EM (within the ±23% churn band —
  same-config A/B needed for a strict call).
- Purity batch working as designed: turns 16→7.8 (budget-cap cases gone),
  EMPTY ANSWERS 6→4→**0** (the two-stage flow + refinement gate + support
  matrix eliminated the empty family entirely), STAGE GATE 127×,
  ANALYSIS 405×, purity reminder needed only 0× (prompt-side Stop Rule
  sufficed; harness detector as backstop, 1 auto-closure).
- Walk-pool core math on the 4-core container: single walks are 0-4ms
  (hub 268ms) — the 12147s "walk" phase was QUEUE-WAIT inflation from
  WALK_POOL=8 oversubscribing 4 cores. OPS RULE: WALK_POOL=3 on this box.

### Throughput fixes verified (user directive 先提高吞吐, 2026-08-22)
- ① HTTPChatBatch → ONE batch POST per round (server /chat/completions/
  batch continuous-batches natively; per-request fallback kept). ② WALK_POOL
  8→3 (4-core box: 8 workers were oversubscribing, queue-inflating the walk
  phase). t10×2 wall: 200s → **106s (round9 done=20)**, quality UP on this
  sample (0.771/13EM vs 0.560/9 — small-n, but no degradation signal).
- Single-walk truth on record: 0-4ms typical, 268ms worst hub (France) —
  the design (one BFS, per-relation queues) intact; "slow walks" were
  core-contention queue waits.

### Inflow mode + GTE residency audit (user speed round, 2026-08-22)
- INFLOW (user design 长尾拉满): rollout admits pending trajectories
  whenever active < inflow_target (auto = full cohort size when
  single-stage; INFLOW_TARGET env overrides). Kills the lockstep long tail
  (final rounds ran 2-5 cases latency-bound while the server idled). meta
  plumbing rebuilt via id-map (completion order ≠ admission order).
- Per-case GTE residency ALREADY largely in place: ctx-resident
  _full_adj_idx / _rel_edges_idx / _rel_pays_idx (pool compute), GTE
  server query cache (50k) + pool_key registry (labeled candidates ship
  once per pool). Residual per-iteration cost = 1 HTTP (~50-130ms) +
  server-side embed of the NEW question text (necessary work). Added next:
  per-case pool memo keyed by center-set (rephrase loops re-query the SAME
  center — currently recomputes reachability each time).

### G=3 VARIANCE VERDICT (V21 final, 2026-08-22): two-stage did NOT cut variance
- regress267_v21_g3 (267×3, temp 0.3, http+pool): answer-set instability
  **48% (129/267)** vs old-stack A/B 38% — the two-stage answer flow did
  NOT reduce flip rate (the Codex C-arm hypothesis is not confirmed at
  this stack). meanF1 0.7344 (all samples), best-of-3 **0.8703**, any-EM
  211, all-EM 123.
- KEY reading: best-of-3 = 0.87 vs single = 0.73 — the CEILING is there
  (~14pp recoverable); the instability is answer-layer sampling, exactly
  the family the RENDERING rewrite targets (evidence presentation drives
  binding choice). Next lever confirmed: rendering (五段管线/三形态),
  not more answer-stage machinery.
- Wall: 801 trajectories in ~46min lockstep (long tail rounds 10-16 with
  ≤10 active — inflow mode lands NEXT run).
- Tool note aligned to design language (semantic-fit question per
  candidate; direction-agnostic; the sufficient-coverage wording was
  mechanism-speak, not the design's semantic-matching intent).

### USER METHODOLOGY RULING (2026-08-22, before context compaction)
- 指标不够，必须看实际工具调用与结果：audit whether the model ACTED per
  design (正确的工具序列/关系选择/checkpoint 语义/两阶段衔接), not just
  F1/EM/flip metrics — "光看指标很多 bug 根本看不出". Every batch from
  now on: metrics + trajectory-level behavioral audit (call sequence,
  tool results, mechanism events) before declaring victory.
- Pending next: RENDERING REWRITE (specs/rendering_mechanism_design.md —
  五段管线/统一行/三经济律/五不变量/17 fixtures; user re-confirmed the
  table-form record display). best-of-3=0.87 vs single 0.73 = the
  recoverable headroom sits in answer-layer sampling, presentation-driven.
- Stack state: V21 final (SEQ_PROMPT=V21) = contract(R/covers) + EXTEND +
  evidence-commit + two-stage + purity prompt (SATISFICING/StopRule/
  minimal-constraint/role-hint) + purity-loop detector + refinement gate
  (subset ok) + format decoupling (flat-only feedback, ANALYSIS→READY
  signal at no-tool path, schema coercion) + join non-enforcement +
  semantic-fit note. Ops: LLM_MODE=http + batch POST + WALK_POOL=3 +
  per-case pool memo + INFLOW sliding-window admission (wired, lands next
  run) + persistent :8000 server resident. r267 single: 0.7606/179EM/
  0 empty/7.8 turns; G=3: flip 48%, best-of-3 0.8703.

### G=3 BEHAVIORAL AUDIT (user methodology: 看实际调用不看指标, 2026-08-22)
- Sequence compliance (fence-stripped parse, 801 trajs): first-tool=plan
  94% ✓; ANALYSIS-then-pure-answer 83% ✓; STAGE GATE→ANALYSIS 295/295 ✓.
  DEVIATIONS: ① 42% (337/801) of trajectories NEVER emit ANSWER_ANALYSIS —
  they answer directly WITHOUT passing the commit/analysis stage (the
  EVIDENCE COMMIT fires only when all_retrieved; cases that answer
  mid-flow via the READY-gate bypass skip the two-stage entirely).
  Direct-answer trajs meanF1 0.697 vs ANALYSIS-path 0.762 (+6.5pp) — the
  two-stage path is measurably BETTER, so the bypass is costing quality.
  ② 19% end on 'ckpt' (151) — model closes facts then budget ends without
  answering (rescue sweeps these); 43 end mid-retrieval.
- READING: the design works where it runs; the failure is the BYPASS —
  commit condition (all facts closed) is too narrow. Fix candidates:
  fire COMMIT when the answer var is bound AND no OPEN fact can still
  constrain it (the READY condition, pre-answer), not only at
  all_retrieved. This likely also recovers part of the 14pp best-of-3
  headroom.
- Audit-script trap on record: model outputs are ```-fenced; a raw
  startswith('tool:') parse reads 0% compliance — strip fences first.

### COMMIT-WIDENING DESIGN AUDIT (dedicated agent, 2026-08-22 — verbatim conclusions)
- VERDICT: widening is SAFE and NECESSARY — it implements the already-
  ruled "BOUND ≠ READY" that the prompt teaches but the harness never
  enforced; 42% bypass is the measured gap. BUT must land as an 8-item
  PACK, not a one-line trigger change.
- THREE PRE-EXISTING DEFECTS blocking mechanization: ① state never stores
  the plan's answer var (COMMIT guesses it — breaks under early-bind);
  ② fact identity spans 3 namespaces (f1 / sg1 / sg1.f2 in
  retrieved_fids vs closed_facts) — missing-lists and ✓ marks are ALWAYS
  wrong today; ③ closures (✗ empty/moot) don't count into all_retrieved
  (why COMMIT fired only 8/144).
- READY predicate (harness-computed): all facts CLOSED, OR (answer bound
  AND no OPEN fact with tail==answer [rebind/intersect] OR head==answer
  [discriminator walk — REQUIRED or the 28-case overshoot family gets
  whitewashed] OR covers a requirement also covered by a tail==answer
  fact [multi-anchor alias escape]). No transitive closure needed.
- MUST-SYNC 8 items: store state.answer + fact_key_map + fact_edges;
  all_retrieved counts closures via key_map; early-answer reminder
  missing-list limited to blocking facts + skip when answer_ready (else
  READY signal vs reminder double-reject); COMMIT trigger→READY; kill
  the _answer_var guess; RESTART resets the 3 two-stage flags; EXTEND
  after commit re-injects ledger; V21 §9/§10 wording aligned (prompt-
  env contradiction is the proven failure mode).
- High risks handled: overshoot whitewash (clauses ②③), double-reject
  (#3), wrong CANDIDATES var (#1/#5). Validation: 48-cohort unit sim →
  G=3 (expect ANALYSIS coverage 58%→~95%, bypass-F1, turns, overshoot
  bucket no-regress) → full 267.

### WALK+GTE PERF AUDIT (dedicated agent, 2026-08-22 — key findings)
- Profile (267×3, 2772s): llm 55%, dispatch 42%. Walk lane 32492s but
  real walk CPU only 459s (7416 walks, mean 62ms) — 98.6% is queue/IPC/
  event-loop blockage. GTE lane 17761s (~4.5k HTTP calls).
- P0 fixes (do all, then measure): ① INFLOW_TARGET=450-550 (kills the
  22% tail-idle in rounds 8-16; batch the per-case prelink top-up);
  ② walk task packing (one pool task per retrieve_subgraph CALL carrying
  all centers — 7416→~1814 tasks; kills per-task asyncio.run + pickle)
  + per-case worker affinity (3 single-worker executors, hash(case)%3 —
  kills the 2/3 MISS-reships from per-worker _W_CASE_CACHE vs global
  _SENT_CASES asymmetry); ③ GTE server: query encode batch_size=1 is a
  real batching HOLE (merged 30-query jobs encode one-by-one → 30 GPU
  forwards; set 32) + adaptive batch window (skip 15ms tax when queue
  empty). Expected combined −580~900s.
- P1: event-loop blockers OUTSIDE any timer (the 70× lane amplifier):
  _seq_pool_relids CVT-expansion unmemo'd (hub first-call 324ms!),
  _name_to_idx rebuilds O(V) norms per call (~10k calls), 
  _canonicalize_triples/_accumulate rebuild full-graph sets per call.
  All ctx-cacheable → −100~180s.
- P2: GTE same-case sample dedup (3 lockstep trajectories send identical
  prelink queries — in-flight future dedup + server (pool,q,topk) cache
  → −2/3 prelink); MAX_CACHE_SIZE 50k < 320k unique candidates (raise to
  400k ≈1.6GB) + offline /precompute warm-up; DISPATCH_CONCURRENCY 64
  A/B 24-32; worker-side adj reuse.
- P3: THINK_BUDGET 600 (the 55% llm lever, quality A/B pending); GTE on
  GPU1 shares with vLLM TP rank-1 — fine now, re-evaluate if INFLOW
  overlaps llm/dispatch.
- Bottom line: dispatch 1172s → ~300-500s achievable without touching
  llm; with THINK_BUDGET maybe ~20min total for 267×3.

### SESSION HANDOFF (2026-08-22, before context compaction → plan mode)
- USER FLOW: memory updated → compress context → ENTER PLAN MODE for the
  implementation batch. Do NOT start coding before plan approval.
- APPROVED IMPLEMENTATION QUEUE (user said 可以):
  ① P0 perf pack: INFLOW_TARGET=450-550 on next runs; walk-task packing
     (per-CALL batch carrying all centers) + per-case worker affinity
     (3 single-worker executors hash(case)%3, kills MISS-reships); GTE
     server query batch_size 1→32 + adaptive batch window. Measure one
     267×3 run after.
  ② 8-item COMMIT-widening pack (design audit approved): store state.
     answer/fact_key_map/fact_edges; all_retrieved counts closures via
     key_map; early-answer reminder limited to blocking facts + skip when
     answer_ready; COMMIT trigger → READY predicate (3 clauses: tail==ans
     / head==ans [overshoot guard] / shared-covers); kill _answer_var
     guess; RESTART resets 3 two-stage flags; EXTEND-after-commit
     re-injects ledger; V21 §9/§10 wording sync. Validate: 48-cohort sim
     → G=3 (ANALYSIS coverage 58%→~95%) → full 267.
- AFTER BOTH: rendering rewrite (specs/rendering_mechanism_design.md, the
  biggest quality lever — best-of-3 0.87 vs single 0.73); THINK_BUDGET
  600 A/B (llm 55% lever).
- KEY NUMBERS: r267 V21-final single 0.7606/179EM/0-empty/7.8turns;
  G=3 flip 48% (old stack 38%), best-of-3 0.8703; two-stage path +6.5pp
  over bypass; 42% trajectories bypass ANALYSIS (the bug the pack fixes).
- OPS: persistent :8000 vLLM resident; LLM_MODE=http (batch POST);
  WALK_POOL=3; SEQ_PROMPT=V21; DISPATCH_CONCURRENCY=64 (A/B pending);
  GTE :8003 resident. All run cmds in this file above.

### P0 PERF PACK + COMMIT-WIDENING PACK SHIPPED (dual-agent plan, 2026-08-23)
- Dual PARALLEL agents (file-disjoint, per approved plan):
  * TRACK A perf: ① INFLOW top-up batched (pop whole deficit, gather-prelink,
    seq_rollout.py:103-114); ② walk-task PACKING — one pool task per
    retrieve_subgraph CALL carrying all centers (7416→~1814 tasks, one
    _aio.run per call; stage_5 multi-case safe) + per-case LANE AFFINITY
    (WALK_POOL × single-worker spawn executors, hash(case_key)%N, per-lane
    sent-sets → no MISS-reships; seq_tools.py _walk_call_spawn/_run_walk_
    packed); ③ GTE /retrieve QUERY encode batch_size 1→32 (merged query jobs
    were 30 sequential 1-text forwards) + adaptive batch window (5ms first
    slice, extends to full 15ms only on arrivals; gte_api_server.py). :8003
    restarted on new code. Tests: test_walk_pool_packing (4), test_gte_
    batching (5).
  * TRACK B 8-item COMMIT pack: state.answer_var/fact_key_map/fact_edges
    (+sg_facts/done-sets) filled at plan AND EXTEND parse; closures (✗) count
    into completion (done_fids, unified namespaces); early-answer reminder
    limited to BLOCKING facts + suppressed when READY; COMMIT trigger =
    ready_to_commit (branch1 all-closed | branch2 answer-bound ∧ no open
    fact with tail==ans / head==ans [overshoot guard] / shared-covers) with
    SEQ_WIDE_COMMIT fuse (default on, off = legacy all_retrieved); CANDIDATES
    from state.answer_var (guess only as display fallback, SUPPORT lines
    suppressed when guessed); RESTART resets _ledger_injected/_analysis_
    pending/_analysis_done; EXTEND re-arms the ledger; V21 §9/§10 wording
    synced (format blocks untouched). BONUS FIX en route: PlanArgs pydantic
    silently DROPPED requirements/covers → merged back post-validate
    (seq_react_loop) — without it EXTEND/SUPPORT/answer_var all dead.
- PLACEHOLDER-FID FAMILY (cohort trajectory audit caught it — 指标看不出):
  22% of fuse-on trajectories declared checkpoints as `[fid ✓]` (the DOC
  PLACEHOLDER, not a real id) → junk keys → no COMMIT, while the legacy
  call-count accounting let the answer through. Fix: _canonical_decl_fid in
  seq_react_loop (real ids via fact_key_map; `fid/f/fact/id` resolve by
  DECLARED VAR against fact_edges — tail-exact first (chain ?x on f1-tail/
  f2-head disambiguates), any-side second, single-fact fallback for var-less
  ✗; memoized ctx._fid_alias so re-statements hit the same freeze-lock).
  ctx now carries fact_key_map/fact_edges (synced at EXTEND + main sync).
  3 regression tests added (tests/test_commit_widening.py), suite 41 green.
- COHORT A/B (48×3, same stack, ONLY the fuse differs): fuse-on+fix (g3d)
  flip 56% / best3 0.7760 / anyEM 42 / meanF1 0.6160 / turns 9.2 / empty 1 /
  coverage 99%; fuse-off (g3c_off) 56% / 0.7450 / 40 / 0.6232 / 8.3 / 3 /
  100%. Unfixed fuse-on (g3c) was 67%/0.7688 — the placeholder fix recovered
  flip and anyEM. FUSE STAYS ON. Note: coverage is now carried by the
  ACCOUNTING fixes (fuse-off also 100% — the old 42% bypass died with
  closures-counting, not with the READY predicate).
- FULL 267×3 verdict (regress267_v21_g3w vs regress267_v21_g3, SAME script):
  meanF1 0.7122 vs 0.7344, best3 0.8585 vs 0.8703, flip 51% vs 49%, EM
  641/801 vs 647/801, empty 9 vs 4 (ZERO case overlap — churn tails).
  Quality PAR within the churn band (−2.2pp ≪ band). BEHAVIOR AT SCALE:
  ANALYSIS coverage 58%→94% (755/801), COMMIT 682, STAGE GATE 559, READY
  signal 602, immutable rejections 0, turns 8.2, F1[analysis-path] 0.736 vs
  F1[bypass] 0.318 (bypass n=46 = budget-end tails). CORRECTION ON RECORD:
  the earlier note "any-EM 211 / all-EM 123" for the g3 baseline was WRONG —
  same-script recompute gives 245/184. Trust recomputes over recall.
- PERF (267×3): wall 2772→2445s (−12%); dispatch 1172→874s (−25%); gte lane
  17761→11529s (−35%); walk lane 32492→27819s (−14%); llm 1519s unchanged
  (decode-bound, THINK_BUDGET lever untouched). The 300-500s dispatch target
  NOT reached — walk lane queue-waits and P1 event-loop blockers remain.
- RESIDUAL FAMILIES (documented, follow-up queue): ① premature self-ANALYSIS:
  the no-tool ANALYSIS→ANSWER_READY signal fires regardless of readiness →
  first answer then eats a missing-facts reject (5/801 full-run) — gate the
  signal on commit_due; ② empty-binding ✗ closures skip the ledger by design
  (nothing to analyze); ③ EXTEND contract misjudgments (model-side, gate
  teaches); ④ walk lane still 27.8k serial-sum / gte 11.5k (P1/P2 unfixed).
- OPS RULES: 267-regression runs NEED `CASE_FILTER=tmp/regress267.txt`
  (SPLIT=test_v4 alone loads 1000 cases — an accidental 3000-traj launch was
  caught and killed at round 3). Full 267×3 env: CASE_FILTER + N_SAMPLES=3
  TEMP=0.3 CASE_BATCH=1000 INFLOW_TARGET=500 LLM_MODE=http SEQ_PROMPT=V21
  WALK_POOL=3. Behavioral audit: scripts/audit_g3_behavior.py (one-off,
  gitignored) — fence-stripping included; flip/best3 via the recompute
  snippet in this entry, NEVER from memory.

### PERF2: round-level WALK COORDINATOR shipped + GTE/vLLM memory trap (2026-08-23)
- MEASUREMENT FIRST (instrumented 48-cohort, walk lane split wait/exec via
  cross-process perf_counter=CLOCK_MONOTONIC): walk 2754 job-s = wait 2300
  (83.5% LANE QUEUE) + exec 341 + parent-side 113 → the 14s/task attribution
  confirmed queueing, not traversal. GTE side (server /cache/stats now
  carries infer_wait_s/encode_s/n_jobs): 1531 job-s queue vs 63s encode —
  GTE is ALSO queue-dominated (single inference worker serializes ~50-call
  bursts; became the top dispatch cost after the walk fix).
- WALK FIX (seq_tools.py): round-level coordinator — adaptive batch window
  (GTE _collect_batch pattern: first slice 0.3s, second arrival extends to
  full window 1.0s; LONE request flushes after the slice, no fixed tax) →
  dedup identical (case_key,center,frozenset(rels)) steps → memo-skip
  (memo-covered slots NOT re-executed; all-memo requests resolved instantly)
  → sticky lane map + greedy-LPT balance → ONE packed multi-case task per
  lane per flush. Legacy per-call lane path kept (WALK_BATCH_WINDOW<=0);
  rollout setdefaults it to 1.0; per-case runners unaffected. Determinism
  pinned by tests/test_walk_batch_coordinator.py (7): memo==fresh==legacy==
  inline, batch==per-case spawn, dedup shares 1 execution, lone-request
  no-tax, burst extension. P1 blockers ctx-cached en route: _name_to_idx
  whole-result memo + norms, _seq_pool_relids memo + _full_adj adjacency
  (tools.py:721 shared), _canonicalize_triples raw/n2i/r2i, _norm_idx_all
  multi-map (_accumulate/_entity_correction).
- 48-COHORT A/B (same stack, cold GTE both sides): wall 674→617s (−8.5%),
  dispatch 318→260s (−18%), walk wait 2300→21s (−99%), walk exec 341→202s
  (−41%, dedup 295 + memo 369 of 1885 steps), collect (window) 377 job-s
  over 24 flushes (6 singles, burst span ~2.3s total). Quality IN NOISE
  BAND: meanF1 0.6429→0.6853 (~1.3σ of 144-traj churn), flip 50→44%,
  coverage 98→97%, turns 9.0, empty 2. Remaining dispatch cost is GTE
  (2305 job-s client, 1923 server queue) — the NEXT lever is GTE client
  (pool,q,topk) dedup + server response cache, deferred by scope ruling.
- GPU MEMORY TRAP (cost ~40min): restarting GTE :8003 while vLLM is UP lets
  vLLM grow into the freed VRAM (its KV pool never shrinks) — the relaunched
  GTE then OOMs on every forward (/retrieve 500s mid-run). Worse: a vLLM
  restart with GTE resident re-sizes to ~0.94 of total, leaving <1MB. FIX:
  vLLM restarted with VLLM_GPU_MEMORY_UTILIZATION=0.82 (34.1GB/GPU, ~5GB
  headroom; steady-state KV usage peaked ~16% so no throughput cost) —
  GTE (1.8GB) now coexists regardless of start order. :8000 restart was
  explicitly out of scope but the constellation was already broken (any
  run 500s) — decision made solo, flagged to user. NOTE: killing the vllm
  wrapper leaves orphan VLLM::EngineCore/Worker_TP procs holding the GPU —
  find via `ls /proc/*/fd | nvidia` and kill -9 by PID.

### PERF-2 terminal (267×3) + per-case wall metric + SIGTERM incident (2026-08-23)
- WALK ROUND-BATCH at full scale (perf2_r267g3): queue wait eliminated
  (wait=935 job-s; the pre-fix equivalent was ~27k) but TOTAL WALL
  2526s vs baseline g3w 2445s (+3%) — dispatch 956 vs 874. The per-flush
  BATCH BARRIER (a request's future resolves only when its whole flush
  finishes — mixed slot durations serialize) + collect ate the queue-elimination
  gain. Cohort scale was −8.5% (617s); full scale is llm-dominated:
  llm=1529s = 60% of wall. WALK IS NO LONGER THE DISPATCH DRIVER.
- GTE now top dispatch lane: 10458 job-s (n=8312) on a COLD cache and still
  below the warm-cache baseline 11529 — the client-side P1 event-loop caches
  are paying. Phase-3 levers remain: client (pool,q,topk) dedup + server
  response cache + MAX_CACHE_SIZE (46k/50k saturates).
- PER-CASE WALL METRIC SHIPPED (seq_rollout): results carry wall_s
  (admission→completion stamps; budget-end stragglers stamped at extraction)
  + printed mean/p50/p90/max + implied round wall. FIRST MEASUREMENT
  (267×3, INFLOW 500): mean=1322s p50=1258s p90=1661s max=2500s on 8.2 turns
  → implied round wall 162s. Single-case time = turns × round wall; the
  round wall is the LLM decode of the whole 500-prompt round (~60% of run
  wall). Tool-side optimization cannot move this; levers are THINK_BUDGET
  (decode length), turns (behavior, frozen), GTE phase-3.
- Quality/behavior at terminal run: meanF1 0.7169 / EM 640/801 / coverage 95%
  / turns 8.2 / empty 11 — all par vs g3w (0.7122/640/94%/8.2/9).
- INCIDENT (ops): 04:25:41 the resident vLLM got an EXTERNAL SIGTERM
  mid-generation (234 reqs running; not OOM, not crash — likely a session
  shell process-group reaper). The in-flight run then died on http_batch's
  1800s future timeout. Recovery trap: scripts/start_local_qwen35_server.sh
  silently exits 1 when `command -v vllm` is empty — vllm lives ONLY in
  /root/miniconda3/envs/qwen35/bin now; launch with explicit
  PYTHON_BIN=/root/miniconda3/envs/qwen35/bin/python
  VLLM_BIN=/root/miniconda3/envs/qwen35/bin/vllm
  VLLM_GPU_MEMORY_UTILIZATION=0.82 (0.90 + GTE reload = OOM cascade; 0.82
  leaves ~5GB headroom, KV peak ~16%, no throughput loss). Server started as
  a TOOL-LEVEL background task survives across turns; plain `setsid nohup`
  from a Bash call did NOT survive for the vllm script (GTE did).
- NEXT LEVERS (ordered by expected wall impact): ① THINK_BUDGET 1000→600 A/B
  (decode is the round-wall floor; needs quality gate — cohort then 267×1);
  ② GTE phase-3 (dedup + response cache); ③ walk flush per-slot future
  resolution (removes the batch barrier — recovers pipelining while keeping
  collect/dedup; est. ≤100s); ④ WALK_BATCH_WINDOW 1.0→0.5 (burst span p75
  0.13s; collect 1485→~700).

### PERF-3 GTE SHIPPED: client round-batch collector + /retrieve_batch + response cache (2026-08-23)
- MECHANISM (3 pieces, zero behavior change; scoring math untouched):
  * CLIENT collector (kgqa/stages/stage2_entity.py, gte_retrieve signature
    unchanged — all callers auto-inherit): adaptive two-stage window
    (GTE_CLIENT_BATCH_FIRST 0.25s first slice; 2nd arrival extends to
    GTE_CLIENT_BATCH_WINDOW 1.0s from first arrival; lone request flushes
    after the slice — walk-coordinator pattern); one flush = ONE POST to
    /retrieve_batch; same-(pool,query,top_k,instruct) requests share ONE
    in-flight future and return the SAME result object (callers read-only);
    completed-memo (GTE_CLIENT_MEMO_MAX 50k) serves repeats with zero HTTP;
    404/transport failure → per-request /retrieve fallback (old semantics);
    atexit one-liner prints _GTE_BATCH_STATS (rollout can't be touched to
    print them per stage). Window<=0 = legacy path.
  * SERVER (scripts/gte_api_server.py): /retrieve_batch (registration pass
    FIRST so key-only siblings share a batch with their registering item;
    response-cache hits resolve in place; misses = ONE merged query encode
    (32,256) + ONE encode per unique pool by sig); RESPONSE CACHE
    (pool_sig,query,top_k,instruct)→rows, LRU 100k (GTE_RESP_CACHE_MAX),
    shared by BOTH endpoints — resident server serves a rerun cohort with
    ~zero encode/queue. /cache/stats now carries batch_calls/batch_items/
    resp_cache_hits/resp_cache_size. :8003 restarted (cold).
  * Tests: test_gte_client_batch.py (10) + test_gte_batch_endpoint.py (8);
    suite 66 green (same 2 pre-existing collection errors ignored).
- TRAP FOUND BY LIVE CHECK (unit tests masked it via cache parity): pool_key
  mode labels rows by the ITEM's own mode — registering call → candidate=
  its candidates; key-only call → candidate= stored cand_texts (pre-existing
  /retrieve semantics). Batch first reused the registering item's labels for
  key-only siblings → rows differed. Fixed: labels resolve per item, pool
  EMBED dedup by sig only. Live parity re-verified exact (scores included)
  via top_k-widening (distinct cache key, IDENTICAL q_text — NEVER verify
  recompute by altering instruct: instruct is PART of the query text).
- COHORT 48×3 A/B (same env as perf2 cohort; baseline llm=351 dispatch=300
  gte≈2126-2657 n≈2000-2241 wall 617-659):
  * A COLD (perf3_cohort_a): wall 674s llm=365 dispatch=283 walk=4542
    gte=2374 job-s (n=1991). Client: 231 flushes (78 single) http_items=1207
    dedup=288 memo=496 fallback=0 collect=1047 job-s. Server: 231 batch/1207
    items resp_hits=0 infer_wait=198s encode=34s. → requests to server
    −40% (2000-2241→1207), server queue −90% (1923→198 job-s).
  * B HOT (perf3_cohort_b, same resident server): wall 647s llm=364
    dispatch=262 gte=1655 job-s (n=2120). Server DELTA for the whole run:
    +219 batch calls, resp_hits +487 (38.6% of items), encode +6.3s,
    infer_wait +2.5s — GTE server work ≈ ZERO; remaining gte lane is client
    RTT + collect window + event loop.
  * QUALITY both in band: A meanF1 0.6593/EM 109/best3 0.8346/anyEM 43/
    flip 29%/cov 97%/turns 9.5/empty 1; B 0.6577/108/0.7669/40/21%/97%/
    9.4/0. dispatch 300→262-283; wall bounded by llm (365s = 56% of wall,
  decode) — A's 674 is at the band edge (llm noise 351→365), B 647 in band.
- VERDICT: request-count lever works as designed (server queue eliminated,
  reruns near-free); wall at cohort scale is now llm-bound, so the 267×3
  terminal gain will show mostly in dispatch (expect gte lane 10458 job-s →
  ~4-5k cold / near-0 server wait hot). Main thread runs the 267×3.

### PERF-3 TERMINAL + SYNC-TAX MEASURED (2026-08-23) — tool-side is DONE
- PERF-3 267×3 terminal (perf3_r267g3, warm GTE cache): wall 2577s (round 1
  +63s = vLLM prefix-cache cold after idle; rounds 2+ identical to perf2),
  llm=1527s, dispatch 956→908s, gte client n=8171 (dedup+memo live), server
  queue ≈0 warm. Quality par: 0.7169 / EM 639 / coverage 95% / flip 52% /
  best3 0.8671 / turns 8.1 / empty 8. Per-case wall mean 1296s (p50 1328 /
  p90 1612 / max 2489) — unchanged, as predicted (turns × round wall).
- SYNC-TAX (PYTHONASYNCIODEBUG=1, 48×3 cohort, 4 rounds harvested before
  user stopped it — few cases suffice): 71 callbacks >100ms, TOTAL BLOCKED
  133.5s ≈ **~33s/round at 144-active**; blockers are the process_turn
  coroutines' own synchronous segments (parse/validate/render/evidence
  build/message assembly), 100-266ms each. Scaled to the terminal run's
  ~350 avg active ≈ 80-115s/round — i.e. **the dispatch wall is now
  essentially the event-loop sync tax**. The deep refactor (staged pipeline:
  parse/render off-loop in process pools, event loop pure orchestration) is
  the only remaining dispatch lever (est. dispatch 908→~200-300s) — but it
  restructures process_turn, same surgery as the harness consolidation:
  schedule AFTER the rendering rewrite provides the replay safety net.
- STANDING PERF VERDICT: llm decode 1527s (59%) owns the wall. Remaining
  levers by size: ① THINK_BUDGET 600 (llm →~1000s; quality A/B pending —
  the ONE cheap big lever); ② deep staged dispatch (post-rendering);
  ③ micro: walk flush per-slot futures, window 0.5s (≤100s combined).
  Combined theoretical floor ≈ ~1400-1500s for 267×3 (from 2772s baseline).

### EVIDENCE PRESENTATION LAYER (rendering rewrite, phase 1 done 2026-08-23)
- USER RULING: retrieve_subgraph's evidence display becomes ①pattern-path
  overview + ②per-relation TABLE blocks (role-slot columns). Design spec
  section "呈现层：概览+关系分块表格" in specs/rendering_mechanism_design.md
  (table grammar = NEW S4 synthesis form; S0-S3 internals + L1/L2/L3 + I1-I5
  unchanged; candidates/note verbatim from caller).
- DELIVERED (parallel-discipline safe: only NEW files + spec edits):
  * kgqa/stages/evidence_display.py — pure renderer, `render_records_compat`
    is a same-signature drop-in for seq_tools._render_records (phase 2 = the
    one-line swap at the retrieve_subgraph call site, AFTER the dispatch-
    refactor agent is done + 主线程放行).
  * tests/test_evidence_display.py — 24 green (17 specimens incl. Brad
    Stevens mockup/Libya incumbent/measurement pairing/hub-CVT refs +
    9 REAL fixtures mined from perf3_r267g3, tests/evidence_display_real_
    fixtures.json). Budget law defaults: ROW_CAP 40 / BLOCK_CAP 12 /
    CELL_CAP 120 (entity names are ANSWER CANDIDATES — never truncate a
    name; 48-cap broke the Gingrich 54-char title).
  * scripts/rerender_reanswer_eval.py (gitignored one-off): replays recorded
    trajectories through process_turn (walk/GTE live-deterministic; env
    CASE_FILTER=tmp/regress267.txt, WALK_POOL=0), monkeypatches
    _render_records to swap rendering + capture inputs; ANSWER-layer re-answer
    = truncated history + ANSWER_READY signal → :8000 (temp .3, tb 1000,
    paired seeds); old-arm (recorded rendering re-answered) = sampling
    baseline. Outputs tmp/rerender_eval.json.
- REAL-DATA BUG the fixtures caught (fixed): in a multi-head record block,
  an attr uniform for head A while a column for head B was ALSO printed in
  A's cells (double print). Fix: hoisted keys force blank cells. I3 checker
  restated at (head, rel) group granularity.
- NUMBERS: invariant audit 157/157 captured real renders I1-I5 clean.
  Re-answer proxy, cohort 48 (sample 0, ×2/arm): old arm meanF1 .6434
  (w2r 1 / r2w 2), new arm .6397 (w2r 0 / r2w 1) — PAR within noise;
  controls 20/20 hits kept, F1 identical (.8708). READING: new form is
  answer-layer SAFE; the best-of-3 upside hypothesis needs the real rollout
  (proxy can't see multi-sample variance).
- REACHABILITY AUDIT (design task): 158 retrieve_relations results — every
  displayed candidate_relation inside the center's pool (2-hop + CVT-
  transparent − noise), 0 walk-empty-on-advertised-relation. No pool gap on
  this sample.
- REPLAY TRAPS: ① recorded subgraph results include ERROR payloads
  (entity_error / boundary) that never reach _render_records — count only
  "triples:"-bearing results or fidelity flags false drift (2/68 hit this);
  ② _json_result inlines a SINGLE-line triples block as "triples:   <line>"
  (no newline) — block regex must handle both forms; ③ replay capture key
  must be a ContextVar (shared global races under concurrent replays).
- NEXT (phase 2, gated on 放行): swap _render_records call site → 48-cohort
  A/B → 267×3 real run vs perf3 baseline (meanF1 .7169 / best3 .8671) —
  the best-of-3 headroom (0.87 vs 0.73 single) is the target metric.

### PERF-4 TERMINAL — round-level dispatch (sync tax dissolved) (2026-08-23)
- ARCHITECTURE (user-directed, replaces point-optimization plan): per-case
  process_turn split into A `_parse_prepare` (pure CPU: parse/bind/gates/
  validate → serializable tool request) → B `_execute_tool` (IO) → C
  `_finalize` (pure CPU: result landing/COMMIT/messages). process_turn KEPT
  as the sequential composition — per-case runner + run_seq_react_batch +
  all tests go through it, zero fork (seq_react_loop.py:764-1362). Tool side
  same split: ST.dispatch_prepare/execute/finalize (seq_tools.py:2265-2310),
  retrieve_relations → _rr_* (1791-1936), retrieve_subgraph → _sg_*
  (1998-2252), _do_seq_decompose converted async→sync (no awaits inside).
  Round scheduler `run_round_dispatch` (seq_react_loop.py:1364): one round =
  A loop for ALL active → every GTE/walk request fires together (collectors
  coalesce; walk flushes collapsed 117→14 ≈ round boundaries; GTE GPU and
  walk CPU lanes overlap) → C loop for all. rollout wired at
  seq_rollout.py:163-166 (ROUND_SCHED=0 = legacy gather fallback);
  DISPATCH_CONCURRENCY semaphore obsolete on the round path.
- REPLAY HARNESS (scripts/replay_dispatch.py, gitignored one-off): replays
  recorded assistant contents of reports/perf3_r267g3.json (801 traj) through
  dispatch with live GTE/walk. Fidelity 801/801 (answer/turns/rejects) on
  every config; gte_n=8171 matches the real run exactly.
- NUMBERS (801-traj replay, dispatch wall): original code 752/766s →
  +refactor only (legacy interleave) 727s → +round scheduler 633/648s →
  +normalize lru_cache 514s. Total −33%. Per-call hot spot killed:
  normalize 6.07M calls/33s per 300-traj profile (core/utils.py:51 bounded
  2^18 lru_cache; pure fn) → gone from profile; _render_records 26.1→4.5s.
  100-case real LLM (perf4_c100): wall 450s = llm 268 + dispatch 165;
  hit 85%, meanF1 .774, ANALYSIS 97%, turns 8.7, failed 0, empty 0, purity 6,
  restart 0, first_tool_plan 100 — band green (audit_g3_behavior).
- DETERMINISM FIX (flagged, pre-existing): _accumulate iterated a SET to
  append all_candidates → pool ordering was PYTHONHASHSEED-dependent per
  process (candidate_pool order differed run-to-run; 42/801 recorded trajs
  show it). Now first-appearance order via dict.fromkeys (seq_tools.py:1097).
  Same SET, stable order. Also _update_var_bindings' per-declaration O(V)
  n2i multi-map rebuild → ctx-cached _norm_idx_all (seq_react_loop.py:222)
  — this was the 100-266ms PYTHONASYNCIODEBUG segment.
- EQUIVALENCE EVIDENCE: byte-replay oracle vs an original-code reference
  replay: legacy interleave 801/801 BYTE-IDENTICAL (three-phase refactor
  proven behavior-clean at full scale). Round scheduler 798/801 — the 3
  (140|2, 160|0, 166|2) are full-scale-only, deterministic, absent in
  isolation (99-case cohort incl. neighbors = 99/99); user ruled them
  timing/batch-order class, recorded not fixed (2 rendered walk-empty;
  answers still identical). Walk-lane job exceptions now PRINT (were silent,
  seq_tools.py _walk_flush_async) — none observed in these runs.
- TRAPS: ① replay of an interrupted/edited file — Python caches modules at
  process start, but spawn WALK WORKERS import seq_tools fresh at lane
  creation: edit carefully mid-run; ② cProfile numbers include epoll waits —
  rank by cumtime but read the wall separately; ③ PHASE_TIMES['walk'] is a
  per-await SUM (inflated under round scheduling: ~simultaneous awaits each
  measure the whole round) — use round dispatch walls for wall truth;
  ④ replay REPLAY_ONLY=<case_idxs> env for single-case debugging.
- NEXT levers: GTE server throughput now owns the big rounds (r5≈72s);
  walk exec 662s lane-sum; residual A/C CPU ~13% of wall (next candidate
  _reach2_relids O(E) scans ≈2.6% — below the 5% marginal line, skipped).

### RENDER V2 SHIPPED + PERF-4 WIRED (2026-08-23) — verdicts on record
- Round-scheduler (PERF-4) + V2 renderer both landed and validated. pytest
  90 green. Renderer wiring: seq_tools._sg_finalize display path →
  kgqa/stages/evidence_display.render_records_compat, env SEQ_RENDER_V2=0
  reverts (default on).
- V2 100-case A/B vs old rendering (same scheduler code): 0.7706/84EM vs
  0.7736/85EM — par (↑4/↓5 single-sample churn); coverage 99%, mechanisms
  healthy; render lane 1s (renderer is free).
- V2 FLIP VERDICT (48×3, WALK_POOL=4): flip 58% vs baseline 56% — NOT
  reduced. best3 0.8003 vs 0.7760 (+2.4pp), meanF1 0.6342 vs 0.6160, anyEM
  43/42, allEM 29/27, turns 8.9. READING: V2 is safe with a small positive
  drift on every point estimate, but the presentation-driven variance-reduction
  hypothesis is NOT confirmed — answer-layer sampling variance (best-of-3
  0.80 vs single 0.63 on the cohort) survives the rendering change; residual
  lives in ANALYSIS selection sampling, not evidence format.
- 100-case reference wall now: 481s (llm 268 + dispatch 195), per-case wall
  mean 369s / p90 414s on 8.7 turns × 42s round wall.
- GTE Q&A ON RECORD: candidates were ALWAYS embedding-cached; per-call GPU
  work is query-encode only; scoring is CPU numpy BY DESIGN (10²-10³ pools,
  3M FLOPs/query ≈ ms — GPU transfer would cost more). Real gaps = cold-
  start warm-up (/precompute or disk-persist vectors) + MAX_CACHE_SIZE 50k→
  400k (~320k unique candidates full-dataset). Both small, queued.
- Trajectory dump for review: tmp/failure_phase_review_render_v2_g3.md
  (failure-phase families: ANSWER-MISS 全部漏绑 29 / 漏绑部分 12 / OVERSHOOT
  11 / RETRIEVAL-MISS 8+1 / notvis 2).

### EVIDENCE RENDER V2.3: three user corrections shipped (2026-08-23)
- User audited tmp/failure_phase_review_render_v2_g3.md (Mandela case =
  WebQTest-1470) and ruled THREE corrections + a separator HIERARCHY (all in
  kgqa/stages/evidence_display.py; wiring untouched — _sg_finalize's
  SEQ_RENDER_V2 gate already live):
  * C1 terminal records: single-record/single-head blocks render as
    `  m.xxx [k=v; k=v]` (no table); multi-record keeps attr columns but the
    block title carries `(terminal records)`. Attr values are TERMINAL
    payloads, never walkable-edge columns.
  * C2 sibling-row folding: groups sharing a tail-SET merge into one row
    (join side = L2 cell); one head many tails folds its tails (the old
    _merge_edges semantics back in table form). Block rows = distinct
    tail-sets; header pluralizes only when an emitted cell is multi.
  * C3 chains: pass-through nodes (in=out=1, non-record-head, ≤3 hops,
    cycles/ambiguity → no stitch) chain into path blocks — headers are the
    relation sequence (+ leading `start`), rows are instance chains; parallel
    chains sharing (start, rels, end) merge with mid-hop fanout as an L2 cell.
  * SEPARATOR HIERARCHY (hard): L1 `|` NEVER inside a cell (hop/record layer
    only); L2 `(a; b; c)` in-cell entity lists; L3 `[k=v; k=v]` record attrs.
    Entities containing `; ( )` never join — rows stay unfolded; unsafe attr
    multi-values degrade to first value + exact `…+K more`.
- TERMINAL-CLAIM AUDIT (tmp/probe_terminal_records.py, 48-case replay, 1275
  patterns / 17523 record edges): 97.5% of record edges have NO continuation
  from their attr values inside the pattern; 2.5% do (e.g. Brad Stevens
  coach-record → teams_coached-record traversals) — those continuation edges
  render as their own blocks, so the terminal form hides nothing (I1 green).
  TRAP: the audit must EXCLUDE attr==head back-refs and sibling pattern edges
  or it over-counts continuations 14× (6248 false → 442 real).
- VALIDATION: tests/test_evidence_display.py 32 green (22 specimens incl.
  Mandela real captures + mid-hop-fanout L2 + `;` fallback + unsafe attr
  values; 9 real fixtures re-audited). Full suite 98 green (2 pre-existing
  collection errors ignored). Heavy fixture: 8559 triples → 100 lines
  (was 199 under V2).
- SAFETY RE-CHECK (render_v2_g3, 20 correct controls, ×3 re-answers/arm,
  paired seeds; replay fidelity via candidates-fingerprint — 20/20 clean,
  49/49 live renders I1-I5 clean, reachability 49 audits 0 violations):
  old arm (pre-correction V2 texts re-answered) r2w=3, new arm r2w=3, flip
  overlap 2/3 → ZERO rendering-attributable regression (1 new-only marginal
  draw vs 1 old-only where new arm is BETTER; any-hit 95% both). NOTE: both
  arms sit ~10pp under the recorded meanF1 (.81/.80 vs .91) — that is the
  answer-layer SAMPLING baseline (recorded answers were lucky temp-0.3
  draws), NOT a rendering effect; always read arm-vs-arm, not arm-vs-recorded.
- EVALUATOR UPDATES (scripts/rerender_reanswer_eval.py): capture patch now
  wraps kgqa.stages.evidence_display.render_records_compat (the LIVE entry
  since _sg_finalize wires it directly — patching seq_tools._render_records
  alone captures NOTHING); fidelity = candidates-line fingerprint
  (rendering-independent walk signature); CAPTURE_DUMP env dumps raw
  captures; _accumulate post-refactor receives ONE PatternEvidence per call.

### RENDER V2.3 (user's 3 fixes + separator hierarchy) verdict (2026-08-23)
- V2.3 shipped: terminal-record semantics (97.5% of 17.5k record edges are
  pattern-terminal — corpus-verified; the 2.5% with continuations render as
  independent blocks), same-side row folding with L2 `(A; B; C)` cells,
  multi-hop chains (relation-sequence headers, entity-chain rows), separator
  hierarchy (L1 `|` = hop/record axis, NEVER in cells; L2 `;` = in-cell
  entities; L3 bracket attrs). Compression: 8559-triple fixture 199→100
  lines. 98 tests green; 20-control render-attributed regression 0.
- 48×3 verdict: flip 58% (same), best3 0.7314, anyEM 41, allEM 28, meanF1
  0.6189. vs V2.0 (0.8003/43/29/0.6342) and base g3d (0.7760/42/27/0.6160).
  HONEST READ: best3 across same-ish-stack runs spans 0.73-0.81 (g3b 0.8147
  / g3c_off 0.7450 / g3c 0.7688 / g3d 0.7760 / v2 0.8003 / v2.3 0.7314) —
  the V2.3 dip is within cross-run churn; structural correctness (terminal
  semantics + unambiguous hierarchy) is a real improvement. Decision pending
  user review of tmp/failure_phase_review_render_v23_g3.md.
- Dump regenerated: tmp/failure_phase_review_render_v23_g3.md (OVERSHOOT 13
  vs 11, 部分漏绑 18 vs 12, families otherwise stable).

### EVIDENCE RENDER V2.4: corrections 4+5 shipped (2026-08-23)
- C4 PATTERN-LEVEL OVERVIEW (Missouri River specimen, WebQTest-626_74344):
  overview lines are now WHOLE pattern paths — only the START is an entity
  (the call's centers, passed as `anchors=` by _sg_finalize, one-line wiring
  change); every later node is a slot (?x/?y); multi-hop = ONE line; inverse
  edges render `<--rel--`; same (relation, direction, anchor) merges to one
  line with `(N instances)`; `[N records]` terminal unchanged. Structural
  fallback without anchors: ≥2 groups sharing a singleton tail-set merge as
  a reverse pattern anchored at that tail. The per-edge instance-headed
  lines ("Iowa --partially_contains--> Missouri River") are gone. Checker
  asserts: overview lines == distinct patterns, slot-only payloads, no '|'
  in overview lines.
- C5 BRANCH REFS RESTORED: the V2 rewrite had orphaned the compressed
  submission mechanism (answer-side _expand_branch_refs in tools.py was
  alive but nothing advertised refs — dump caught Boston Celtics 17
  championships showing 8). Edge blocks now emit, at every cap that hides
  answer candidates: cell-cap → `  +K more (total T). To answer with ALL of
  them, include "#anchor::rel" as one answer entity — the system expands
  the ref to the full list.`; row-cap → same instruction after the dropped-
  groups marker (+ `(also: #h2::r | #h3::r)`). Anchor = OPPOSITE cell's
  first shown entity (expansion is direction-agnostic: _BRANCH_RE center
  matches either side). Records/chain truncations emit NO refs (expander
  drops CVTs — a ref there would mislead). Contradictory double markers
  (`…+9 more` + `+0 more edges; +9 entities hidden`) removed — ONE block
  marker per cut, shown+more==total asserted.
- Token grammar kept in sync with tools._BRANCH_RE = ^#(.{1,200}?)(?:::|\|)
  (.{1,300})$ via a LOCAL copy in evidence_display (stages→agent import
  would cycle); tests assert against the LIVE regex + end-to-end
  _expand_branch_refs expansion (22-tail Celtics, 137-tail, heads-cap
  reverse anchor).
- VALIDATION: tests/test_evidence_display.py 37 green (Missouri C4 fixture
  from real capture; Boston/huge/heads/rowcap C5 fixtures). Full suite 103
  green. Kansas-chain NOTE from the Missouri fixture: pass-through stitching
  legitimately consumes inverse-edge pairs (containedby+contains round trip
  became ONE 2-hop chain, folding counts drop accordingly — expected).

### V2.4 + MULTI-RELATION NOTE: cohort record (2026-08-23)
- V2.4 (overview=complete pattern paths w/ ?slots + reverse-edge notation +
  branch-ref compressed submission restored, end-to-end verified vs live
  _BRANCH_RE) + prompt §2.4 cost-asymmetry rewrite + retrieve_relations note
  ("2-3 fitting relations is the NORM / single-relation precision is not the
  goal"). 103 tests green; re-answer proxy: V2.4 alone +5.4pp, new-only
  regression 0.
- 48×3 combined (render_v24_g3): **meanF1 0.7095 (record; prior configs
  0.6143-0.6853), EM 116/144 (80.6%), best3 0.8670 (record), anyEM 44,
  allEM 32 (record), coverage 100% (bypass 0!), turns 8.6, empty 0, reject-
  other 13 (was 19-24)**. flip 60% (between-good-answers churn; allEM record
  makes it moot).
- NOTE EFFECT IS LARGE AND DIRECTLY MEASURED: retrieve_subgraph calls with
  1 relation 85%→19%; mean relations/call 1.21→2.34 (the over-precision the
  user diagnosed, fixed). Calls 421→363 (fewer repair rounds).
- Attribution: V2.4-render proxy +5.4pp measured alone; note's coverage
  effect adds the rest (turns↓, rejects↓, EM↑ coherent). Full 267×3
  confirmation launched as ship gate.

### V2.4+NOTE FULL-267 SHIP-GATE: WIN (2026-08-23)
- 267×3 (render_v24_r267g3): **meanF1 0.7405 (+2.4pp) / EM 666/801 (+27,
  83.1%) / flip 47% (−4pp — variance DID drop at full scale, unlike the
  cohort) / best3 0.8759 (new full-267 record) / anyEM 248 / allEM 192 (+11)
  / turns 8.0 / empty 5 / coverage 96%**. vs perf3 (same G=3/temp/stack):
  every point estimate improved coherently. First full-cohort beyond-noise
  quality win since V21 itself.
- COST (honest): wall 3118s (vs 2577s) — the 120-entity cells + full pattern
  overviews enlarge evidence text → llm 1730s (+203s, bigger contexts) and
  dispatch 1266s; per-case wall mean 1569s (+273s). Quality-per-token trade,
  acceptable; token-budget tuning is a later lever.
- Renderer iteration continues in flight: fix 6 (multi-center shape-level
  anchors + cross-center chaining), fix 7 (columns=relation names, kill
  head/tails), fix 8 (entity capacity back to legacy 120, no small-list
  truncation) — user review round 3 on dumps. These post-date the ship-gate
  run and need their own validation.
- Dump: tmp/failure_phase_review_render_v24_r267g3.md

### EVIDENCE RENDER V2.5: corrections 6+7+8 shipped (2026-08-23)
- C6 SET ANCHORS (Ron Howard specimen, WebQTrn-567_11fd, 29-43-center ?film
  walk): multi-center (?var-expanded) walks anchor overview patterns at the
  SET — one line per (relation, direction) with `(N instances)`, NEVER per
  member; wiring passes anchors=centers + anchor_label=?var token from
  _sg_finalize (raw entities list). Member-started chains merge into one
  set-anchored shape. Single-center behavior unchanged (Missouri/Mandela
  fixtures assert no-regress). Structural fallback (shared-singleton-tail
  reverse merge) intact for non-center groups.
- C7 RELATION COLUMNS: formal head/heads/tail/tails column headers are GONE
  (hard fixture + checker assertion; 'start'/'record' also banned). Block
  TITLES are full shapes (`── ?film --edited_by--> ?x ──`, records get
  `(terminal records)`); column headers = relation short names; first column
  = anchor slot (entity / `?film(43 centers)` / `?node` for multi-start
  blocks); record tables = [anchor col if multi-head] + record-relation col
  (cells = m.ids) + attr cols; edge rows are ANCHOR-SIDE-FIRST (rev rows
  swap cells; all-rev blocks mark the column `<--rel`).
- C8 CAPACITY BACK TO 120: CELL_LIST_CAP 8→120 (= old _MERGE_TAIL_CAP;
  ATTR_LINE_CAP likewise). ≤120 entities per cell/row are ALWAYS fully
  shown — zero `…+N more`/hidden below 120 (the dump's 12-entities-show-8
  bug: model can't bind what it can't see). Only >120 truncates, and then
  WITH the C5 branch ref; row cap (40 folded rows) is a line-count budget,
  not an entity budget. I5 extended: asserts full display at ≤120.
- VALIDATION: tests/test_evidence_display.py 41 green (28 specimens incl.
  Ron Howard unit + FULL 1377-triple multi-center real fixture with anchors
  in tests/evidence_display_real_fixtures.json; Boston-22 now FULL, 137-tail
  + 130-heads refs; 12-entity full-display specimen). Full suite 107 green.
- TRAPS this round: ① fixture relations must not be NAMED "tails"/"head" —
  the C7 literal ban is content-blind; ② checker I3 must compare uniform
  keys against ATTR columns only (the record connector's short name may
  coincide with an attr key, e.g. film.performance.actor ↔ actor); ③
  exact/subset row matching must settle BEFORE reporting (a wrong candidate
  row that is a subset used to fire false C8s); ④ block-truncation markers
  join shape names with '; ' — L1 '|' stays column-only; ⑤ the multi-center
  capture came from reports/render_v24_g3.json (the ?film expansion replays
  deterministically).
- PENDING (GPU-gated on the main 267×3 render_v24_r267g3 run): replay render
  audit (I1-I5+C4-C8 over live captures, anchors forwarded) + 20-control
  re-answer safety re-check.

### V2.5 GATE: RENDERING LINE CLOSED (2026-08-23)
- V2.5 (fixes 6/7/8: set-anchors `?film(N centers)` shape lines — Ron Howard
  83→20 lines; columns=relation names, head/tails literal headers banned;
  entity capacity back to legacy 120, ≤120 zero truncation) full 267×3
  (render_v25_r267g3): meanF1 0.7399 / EM 667/801 / flip 51% / best3 0.8753 /
  anyEM 249 / allEM 193 — every metric WITHIN NOISE of V2.4 (0.7405/666/47%/
  0.8759/248/192), both +28 EM over perf3 baseline. **AND FASTER: wall 2852s
  (V2.4 3118s, −266s), per-case 1413s (−156s)** — shape-collapse context
  reduction outweighs the 120-capacity growth. llm 1782s, dispatch 948s.
- VERDICT: V2.5 is the SHIP — user-mandated semantic correctness (shape-level
  anchors / relation columns / no entity truncation) at V2.4-level quality and
  better wall time. Rendering rewrite line CLOSED after 8 fixes across 3 user
  review rounds; cumulative arc: perf3 baseline 0.7169/639 → V2.5 0.7399/667
  (+2.3pp/+28 EM) with flip 51% and best3 0.875.
- Remaining error families (render_v25_r267g3 dump): 漏绑部分 ~75 / 全部漏绑
  ~102 / OVERSHOOT ~74 / RETRIEVAL ~37 — the answer-layer binding/overshoot
  families are the next quality frontier (ANALYSIS-stage sampling), plus the
  queued: mechanism consolidation on the A/B/C trunk, GTE warm-up+cache-size.

### EVIDENCE RENDER V2.6: correction 9 + raw-path overview + FASTCHECK loop (2026-08-23)
- C9 START-ANCHORED OVERVIEW (Germany specimen, WebQTrn-849): pattern lines
  anchor at the WALK START only. Record back-edges (Poland --adjoin_s--> the
  same record Germany reaches) fold into the record presentation — the
  back-edge entity surfaces as a record attr value (adjoins=(Germany; Poland))
  + a bare-id ref row; NO pattern line of its own. Non-start edges/records/
  chains render in blocks only. Anchor-less calls keep the C4 structural
  fallback (production always passes anchors).
- C-raw REAL PATTERN STRUCTURE (user re-ruling: 模式路径是完整路径): the
  overview consumes PatternEvidence.tree_data paths FIRST
  ({"nodes": [center,...], "relations": [full names]}; _sg_finalize gathers
  top-5 patterns' paths → render_records_compat(patterns=...)). Starts are
  walk centers by construction; hop direction resolved against flattened
  edges; CVT terminal → [N records]; multi-hop shapes come out NATURALLY
  (Germany: `Germany --partially_containedby--> ?x (23 instances)`;
  Ron-Howard set mode: `(A Beautiful Mind; +43 more) <--film-- ?x
  <--edited_by-- ?y --film--> [24 records]`). Flattened-edge inference is a
  SUPPLEMENT, deduped by (rel-short, direction, terminal-kind).
- Block titles now show the DOMINANT pattern shape only (no " / " joined
  direction pairs — L1-confusion risk).
- FASTCHECK LOOP (process ruling): per-bug validation = pytest + 10-case
  tmp/fastcheck.txt run (~2 min; command in the design spec). Big runs are
  milestone-only (main thread). First fastcheck AFTER C9+C-raw: 10/10 done,
  0 failed/crash, COMMIT 8 / ANSWER_READY 5 / REJECT 1 (known family),
  7/10 hit, meanF1 0.545 (hard specimen set).
- VALIDATION: tests 42 green (new: Germany fixture w/ GERMANY_PATHS raw
  structures — all overview lines Germany-anchored, no Poland/Czech lines,
  adjoins attr present; Missouri updated: non-start record lines gone by
  design). Full suite 109 green.
- TRAPS: ① f-string/dict-comp typos in the render path fail SILENTLY into
  dispatch errors ("name 'b' is not defined" surfaced as a dispatch_retrieve_
  subgraph error — check rc.messages tool results when a replay yields 0
  renders); ② evaluator CAPTURE_DUMP used to strip "anchors" when slimming —
  include it or the captures mislead; ③ raw tree paths carry DISPLAY names
  (CVTs expanded "m.xxx: [attrs]") — match by the pre-colon id.

### V2.6 MILESTONE (fixes 9/10 + C-raw + fastcheck loop, 2026-08-24)
- V2.6 = start-anchored pattern lines (record back-edges folded into record
  attrs — Poland/Czech anchor lines eliminated) + overview from REAL walked
  patterns (tree_data paths; Germany shows true 2-hop shapes natively, Ron
  Howard set-anchor 4-hop chains) + STAGE GATE self-analysis pass-through
  (same-turn ANSWER_ANALYSIS + answer accepted directly).
- FASTCHECK LOOP ESTABLISHED (user ruling: no full runs per bug): tmp/
  fastcheck.txt = 10 specimen cases (Germany/Mandela/Missouri/Boston-137/
  RonHoward/Euro/Brad/GMT/ET/CentralAm), single sample, 116s per pass —
  the per-fix validation standard; 48×3/267×3 only at milestones.
- Milestone 48×3 (render_v26_g3): meanF1 0.6448 / EM 112 / flip 58% /
  best3 0.8263 / **anyEM 45 (cohort record)** / allEM 29 — par with V2.5
  (0.6598) inside churn; V2.4's 0.7095 remains the high draw of the band.
- FIX-10 EFFECT VISIBLE AT SCALE: STAGE GATE 75→19 per 144 trajs (~0.4
  turns/case saved), turns mean 7.7 (V2.5 ~8.6-8.9 band), empty 0, coverage
  100%, ≥12-turn tails 13 (was 16-26).
- Dump: tmp/failure_phase_review_render_v26_g3.md (全部漏绑 26/部分 18/
  OVERSHOOT 15/RETRIEVAL 6 — OVERSHOOT trending down).

### EVIDENCE RENDER V2.7: correction 11 SINGLE SOURCE OF TRUTH (2026-08-24)
- C11 (Eleanor specimen, WebQTrn-1392): overview and detail blocks derive
  from ONE source — the parsed tree_data shape groups. build_view synthesizes
  PATTERN BLOCKS per shape (records-terminal → record groups w/ attrs from
  the CVT map + bare-id refs across shapes; 1-hop named → edge groups w/ C2
  folding; multi-hop named → chain groups, one path = one instance row).
  1-hop shapes ABSORB uncovered flattened instances of the same (member,
  rel) — true counts = paths + flattened merge. Flattened data demoted to
  DISPLAY-ONLY supplement (covered edges/records filtered out; no overview
  lines; records detailed in a shape demote to bare ids in supplements).
- C-consist invariant (auditor + fixtures): shape-backed block rows ==
  pattern count (gated by _Pattern.from_shape — structural patterns on
  folded supplement blocks are NOT count-bound: their rows merge multiple
  heads' groups by tail-set); optional candidates= param asserts every
  candidate traceable to block entities / (all:) values / record attr cells
  / bare ids (per-CALL scope — candidates span the case's later subgraphs,
  audit each call against its own render only).
- VALIDATION: tests 43 green (new Eleanor real fixture w/ 74 tree paths —
  counts==rows, chain columns carry the shape's terminal semantics,
  candidates traceable; Germany updated: reverse round-trip edge now lands
  in the supplement block by design — the walk never walked it). Full suite
  110 green. FASTCHECK after C11: 0 crashes, mechanisms normal; this-run
  10 cases 7/10 hit, meanF1 0.674 (pre-C11 run: 0.545 — noise band).
- TRAPS: ① fastcheck OUT RESUMES — `rm tmp/fastcheck_out.json` before each
  fastcheck or the json accumulates batches; ② the b-typo class of bugs
  (dict-comp variable typos) surfaces as silent dispatch errors — when a
  replay yields 0 renders, read the replayed tool-result messages FIRST;
  ③ tree_data paths carry display names — strip at ':' for record ids.

### V2.7 MILESTONE: single-source-of-truth holds (2026-08-24)
- Fix 11 shipped: shape groups (tree_data paths) drive BOTH overview lines and
  detail blocks (instance tables, col k = hop-k endpoint); flat edges demoted
  to uncovered-only supplement (no overview lines, fix-9 anchoring intact);
  C-consist invariants in audit+fixtures (block rows == overview count for
  shape-backed blocks; every candidate traceable to a block/attr/bare-id;
  chain column semantics). Eleanor specimen: counts==rows, student-chain
  instances visible, candidates sourced. 110 tests green.
- Milestone 48×3 (render_v27_g3): meanF1 0.6377 / EM 113 / flip 65% / best3
  0.7744 / anyEM 43 / **allEM 33 (cohort record)** / turns **7.4 (record
  low)** / empty 0 — par within the four-version band (0.6377-0.7095;
  V2.4 remains the high draw). Structural unification cost nothing.
- Rendering line now 11 fixes over 4 user review rounds; candidate ship =
  V2.7. 267×3 terminal gate pending user's call (V2.4 ran 0.7405/667; V2.5
  0.7399/667; V2.7 has fixes 6-11 on top).

### RENDER V3 (main-thread takeover, user ruling: tables lost density) 2026-08-24
- User verdict on V2.x tables: too sparse/redundant (France specimen 208
  lines, same records in 3 blocks; CPI records showed BARE g.xxx ids — attrs
  lost, worse than redundant), SAPS dense form was better. RENDERING TAKEN
  BACK FROM THE AGENT (over-focused on tables). Three rulings: ① dense
  detail lines ② overview capped ≤3 shapes per relation, path-terminal-first
  (last hop == a SELECTED relation), start-anchored ③ CVT attrs must render
  inline, incl. the penultimate-hop rule (path ending in a CVT-attribute hop
  → record shows attrs; unit-verified: `Italy --cpi_inflation_rate-->
  g.11b60sf4fy [value=2.3; year=2011] | ...`).
- V3 = legacy _render_records dense lines (restored as DEFAULT; 120 cap +
  branch refs + (all:) uplift intact) + NEW build_pattern_overview
  (seq_tools: ≤3/relation, terminal-first, ?slots, reverse `<--r--`,
  `[N records]` terminals, direction resolved vs flattened edges) + ──
  separator. SEQ_RENDER_V2=1 keeps tables for A/B. Brad Stevens specimen:
  7 overview lines + dense detail, CVT attrs visible.
- Fastcheck: 9/10 hit, meanF1 0.859 (record). Milestone 48×3 (render_v3_g3):
  meanF1 0.6782 / EM 114 / best3 0.8513 / anyEM 44 / allEM 32 / turns 7.6 /
  ≥12-turn tails 8 (lowest) / empty 0 — top of the V2.4-2.7 band with the
  demanded form. 110 tests green. Dump: tmp/failure_phase_review_render_v3_g3.md
- OPEN: V3 candidate for 267×3 terminal gate (V2.4 full was 0.7405/667).

### RENDER V3.2 FINAL FORM: pattern-grouped ordered triples (2026-08-24)
- User's convergent ruling: trie bloats on intermediate-entity subgraphs,
  tables too complex — THE FORM = ① capped pattern-path overview (≤3/rel,
  terminal-first) ② per-pattern sections of triples IN PATH ORDER (instance
  chains as consecutive edges, global (h,r,t) dedup) ③ facts section = legacy
  dense lines for uncovered 1-hop/records. Hygiene shipped en route: L2
  single-print attr brackets (repeats bare-id), CVT back-edge suppression in
  chain clothing (same-rel swapped-ends = walk backtrack noise, e.g.
  m.0w3_qv3 --teams_coached--> Brad Stevens), hollow shape sections skipped.
- Milestone 48×3 (render_v32_g3): meanF1 0.7037 / EM 115 / **best3 0.8761
  (ALL-TIME cohort record)** / anyEM 45 (record tie) / allEM 31 / flip 58% /
  turns 7.5 / coverage 99% — top of the band WITH the demanded form.
  (V3.0-dense 0.6782/0.8513; V3.1-trie killed before milestone on the
  bloat ruling; fastcheck V3.2-first-draft dipped 0.415 → attr-dup +
  back-edge noise → fixed → 8/10/0.658.)
- Rendering arc closed: V2 tables (11 fixes, 0.6377-0.7095) → V3.2 triples
  (0.7037, best3 record). 110 tests green. Dump:
  tmp/failure_phase_review_render_v32_g3.md. 267×3 terminal gate pending.

### V4 SEMANTIC LAYERS milestone (2026-08-24)
- V4 = V3.2 + semantic layers (fact header / answer-role from the fact's
  ?var slot / answer-candidates-first display / attribute & source layers /
  ?var status line; fid-empty → first-open-fact fallback) + same-prefix
  fan-out folding in chains (Montana official_symbols ×N → one line; global
  edge dedup already shares common prefixes — SAPS-trie effect at line
  density). Layer derivation unit-verified (Mandela ?country→South Africa
  from jurisdiction terminal; Boston ?championship → 17 finals listed first).
- A/B tool finalized (scripts/render_ab_report.py): 8 captures, three
  variants side by side, ZERO LLM; V2-tables renderer CRASHES on 2/8 real
  captures (tuple-attr fragility) — the tool keeps paying for itself.
- Milestone 48×3 (render_v4_g3): meanF1 0.6634 / EM 108 / flip 60% / best3
  0.8061 / anyEM 42 / allEM 29 — IN BAND but low side vs V3.2 (0.7037/115/
  0.8761). Trajectory audit of the 4 any-hit drops: layer headers
  semantically CORRECT in all inspected cases (Freemasonry/Vicksburg/RedHook
  = hard/wrong-gold families, answers reasonable); no mechanical mislead
  found; 302 headers live across 144 trajs. Compression real (Missouri 76→49
  lines, Iowa 105→82).
- VERDICT PENDING 267: cohort n=48 cannot resolve −4pp; the layer overhead
  hypothesis (extra header tokens) vs churn needs the full gate. Fastcheck
  incident en route: vLLM externally killed AGAIN (second time, same SIGTERM
  pattern) — recovered via the established restart (qwen35 binaries, 0.82).

### V4 ATTRIBUTION + FEATURE SPLIT verdict (2026-08-24)
- 3 dropped-cases attribution: Liszt/Vicksburg = lucky-sample non-repro
  (both stacks mostly fail; V3.2 hit 1/3 by draw). Lala Anthony = REAL bug:
  multi-relation selection mixed terminals of different semantics
  (place_of_birth → Red Hook vs people_born_here → residents) in the flat
  answer-candidates header; the model's checkpoint COPIED the polluted list
  verbatim. FIX: per-last-hop-relation groups (`via place_of_birth: … /
  via people_born_here: …`) — harness attributes, model filters.
- Post-fix cohort series: V4 0.6634 / V4b 0.6490 / fold-only (layers OFF
  via SEQ_EVIDENCE_LAYERS, default) 0.6590 — a 0.65-0.66 CLUSTER; V3.2's
  0.7037 reads as a high draw (V2.4's 0.7095 likewise). Cohort cannot
  resolve further; 267 gate is the decider.
- SHIP CONFIG: folding ON (pure compression), semantic layers OFF by
  default (SEQ_EVIDENCE_LAYERS=1 experimental). 110 tests green.
- vLLM externally killed a 2nd time during this arc (same SIGTERM family) —
  recovered via the standing restart procedure.

### RENDER LINE TERMINAL GATE: SHIP (2026-08-24)
- 267×3 (render_v32f_r267g3, ship config = pattern-grouped ordered-triple
  chains + same-prefix fan-out folding + capped overview; semantic layers
  OFF by default): **meanF1 0.7628 / EM 684/801 (85.4%) / flip 47% / best3
  0.8771 (full-267 record) / anyEM 249 / allEM 199 (record, +6) / turns 7.0
  (lowest ever) / wall 2777s + per-case 1358s (fastest of the V2.4/2.5/ship
  trio)**. vs V2.4 0.7405/666 and V2.5 0.7399/667: +2.2pp / +17-18 EM with
  every secondary metric improved — first config to beat the V2.4/2.5 pair
  on ALL points.
- RENDERING ARC CLOSED (V2 tables 11 fixes → V3.0 dense → V3.2 pattern-
  grouped → folding; semantic-layers arm parked behind SEQ_EVIDENCE_LAYERS=1
  with the per-relation candidate-group fix): cumulative from the perf3
  baseline 0.7169/639 → **0.7628/684 (+4.6pp / +45 EM)**, turns 8.1→7.0.
- Dump: tmp/failure_phase_review_render_v32f_r267g3.md. NEXT QUEUE (user's
  call): answer-layer 漏绑/OVERSHOOT families (the remaining error mass),
  mechanism consolidation on the A/B/C trunk, GTE warm-up + cache size,
  THINK_BUDGET (parked by user ruling).

### ANSWER-LAYER PACK ① (None ladder + var status) — FLIP COLLAPSE (2026-08-24)
- Shipped (user design): ① literal `entities: None` intercepted in the A
  phase BEFORE commit/gate/offpool (each dead-ended it differently —
  Anglicanism specimen) → escalation LADDER, model-decided: fall back one
  level (re-select the weakest subgraph's relation set; curated lists are
  never exhaustive) → only then `[explore ✗ none]` restarts the case ONCE
  (dormant restart code re-awakened + §7 teaching restored) → second-attempt
  None = explicit empty (restart contract). ② checkpoint acks carry
  same-subgraph VAR BINDING STATUS ("Subgraph vars: ?founder=bound(1)") —
  information, never enforcement (vars link facts; binding not forced).
  ③ empty answers skip the STAGE GATE (no choice to analyze). 112 tests
  green (ladder routing + restart contract + var status).
- 48×3 milestone (ladder_g3): **flip 67%→44% (−23pp — the variance collapse
  the V21 flip analysis predicted), meanF1 0.6590→0.7075 (+4.9pp), EM
  110→118, allEM 29→35 (COHORT RECORD, was 33), best3 0.8173, turns 7.7,
  empty 0.** none-ladder fired 18×/144 trajs (the family is real); var
  status 0× (standalone checkpoint turns rare — most declarations ride tool
  turns; harmless). High-meanF1 + LOW-flip + record-allEM together = a
  systematic change, not a lucky draw.
- 267×3 gate launched to confirm at scale (baseline: render ship 0.7628/
  684/flip 47%).

### LADDER PACK 267 GATE: WIN — best3 FIRST ABOVE 0.90 (2026-08-24)
- 267×3 (ladder_r267g3): **meanF1 0.7759 (+1.3pp) / EM 688/801 (86.0%) /
  best3 0.9074 (+3.0pp, ALL-TIME record, first >0.90) / anyEM 253 (+4) /
  allEM 203 (record, +4) / flip 47% (full-cohort was already 47 — the
  cohort's −23pp collapse shows up here as ceiling rise) / turns 7.2 /
  empty 3.** none-ladder fired 68×/801, restarts 2 — real work at scale.
- CUMULATIVE ARC: perf3 baseline 0.7169/639/best3 0.8585 → render ship
  0.7628/684/0.8771 → +ladder **0.7759/688/0.9074** (+5.9pp / +49 EM /
  +4.9pp best3 in one day, two packs).
- Dump: tmp/failure_phase_review_ladder_r267g3.md. Queue: ② literal-center
  transparent expansion, mechanism consolidation (answer-phase machine),
  GTE warm-up/cache, THINK_BUDGET (parked).

### EVIDENCE RENDER V3.3: audit-then-redesign, principles 1+2 (2026-08-25)
- USER RULING (stop whack-a-mole): two core principles govern the evidence
  display. P1 ORGANIZE BY SELECTED RELATION, SHORT-TO-LONG — per-relation
  1-hop blocks first, then k-hop path blocks length-ascending, instance-count
  desc within a length. P2 PATH CONSISTENCY — a k-hop block only contains
  instances that COMPLETE its shape; a hop-1-reached entity with no hop-2
  continuation stays in the 1-hop block (truncated OUT of the 2-hop block).
- AUDIT (Fitzgerald specimen WebQTrn-894_fe576…, replayed from
  ladder_r267g3 via render_ab_report): ① build_pattern_overview grouped by
  FIRST-hop rel + terminal-first/count-desc → 1-hop and 2-hop interleaved,
  2-hop(18) printed before 1-hop influenced_by(21) — P1 violation;
  ② render_pattern_chains sorted multi-hop shapes by count only, no length
  tiers — P1; ③ chains rendered only tree-path witnesses (≤24/pattern) —
  hop-2 continuation edges of non-witness hop-1 entities fell into FACTS as
  anchorless fragments (`Ann Beattie --influenced_by--> …` without the
  Fitzgerald --influenced--> anchor) — P2; ④ coverage keys were WALK-ORDER
  while facts filtered CANONICAL triples → direction mismatch double-printed
  instance edges (chain `Clive James --influenced--> Camus` AND facts
  `Camus … --influenced--> Clive James`); ⑤ overview counts were tree-path
  counts (Germany `(75 instances)` vs 11 block rows) — overview/detail
  desync; ⑥ 1-hop selected edges had no per-relation block (scattered dense
  facts lines in arrival order).
- REDESIGN (kgqa/agent/seq_tools.py): ONE unified renderer
  `render_evidence_sections(paths, centers, var_label, all_triples,
  selected_rels)` (~350 lines, seq_tools.py:932) replaces
  build_pattern_overview + render_pattern_chains in _sg_finalize (call site
  seq_tools.py:2831; old pair kept as the A/B before-arm only). Pipeline:
  canonical edge indexes (fwd/rev/display/cvt_attrs) → shape vocabulary from
  tree paths (direction resolved vs canonical edges, selection discipline
  enforced) + 1-hop SYNTHESIS per selected relation from anchor edges →
  instance RECONSTRUCTION per shape from the canonical edges (complete paths
  only, _SHAPE_INSTANCE_CAP=3000 with explicit overflow marker) → ordering
  (1-hop per selected rel first, then length asc / count desc; ≤3 per first
  rel, ≤12 total) → overview lines + detail blocks from the SAME instance
  sets (counts consistent) → covered-edge keys CANONICAL (facts remainder
  can no longer double-print). Folding: shared-prefix tail fold + new
  shared-TAIL-SET fold (prefixes differing in exactly ONE position merge
  into a fanout line — the round-trip family `A --r--> X1..Xn --r2--> A`
  collapses to one line; _merge_edges (r, tail-set) semantics on chains).
  1-hop blocks have NO header (dense line self-describes); multi-hop headers
  keep the `[r1 -- r2]` grammar. CVT terminals inline attrs with (all:)
  uplift for single-valued uniform keys — multi-valued attrs SURVIVE (the
  legacy _collapse_uniform_line last-wins dict collapse lost e.g.
  adjoins=Poland on the Germany records).
- TRAPS fixed en route: normalize() maps '_'→' ' ("m.02sd_zh"→"m.02sd zh")
  which breaks is_cvt_like on NORMALIZED keys → cvt_keys set collected from
  RAW names, membership test; mid-hop coverage marking originally marked
  (prefix[0], r, terminal-tail) for EVERY hop — must be (gk[k], r, gk[k+1]).
- VALIDATION: tests/test_render_pipeline.py NEW (13 assertions: P1 ordering,
  P2 complete-instances-only/GRRM-truncation/no-anchorless-fragments/
  canonical-coverage, selection discipline both sections, count consistency,
  CVT inline+uplift, attr single-print, round-trip folding, multi-center
  tail-set fold, caps, empty-paths fallback, determinism). Suite 125 green
  (112 prior + 13; the 2 pre-existing collection errors unchanged). A/B
  report (scripts/render_ab_report.py now renders V3.2-before + V3.3-after
  side by side, capture hook re-pointed at render_evidence_sections):
  Fitzgerald 165-triple capture — before 35 lines of mixed shapes/fragments
  → after: 4 one-hop dense blocks (21/31/3/7 full tail sets) + [influenced
  --influenced_by] (37 complete instances, Ann Beattie family INSIDE the
  block) + [influenced_by --influenced] (35), round-trip family folded to
  one line, facts reduced to 8 unwalked-shape edges. Germany: [11 records]
  1-hop with per-record attrs (Poland/Netherlands survive), true counts 15.
  Fastcheck 10-case: 0 crash, 8/10 hit, meanF1 0.602 (band 0.545-0.859),
  COMMIT active.
- MILESTONE 48×3 (render_v33_g3, WALK_POOL=4, wall 670s): meanF1 0.6888 /
  EM 115/144 / best3 0.8318 (+1.5pp) / anyEM 44 / allEM 32 / flip 50% /
  turns 8.1 / empty 2 vs ladder_g3 0.7075/118/0.8173/43/35/43.8%/7.7/0 —
  meanF1 −1.9pp INSIDE the documented ±4pp cohort churn band (V4 cluster
  0.65-0.66, V3.2 0.7037, ladder 0.7075); best3 UP; the 2 empties are the
  WebQTrn-452 flip-churn family (ladder hit/miss/hit vs v33 miss/hit/miss
  on the same case — sampling, not renderer). PAR verdict; 267×3 gate is
  the decider if the user wants full-scale confirmation.

### PERFECTIONISM PACK v2: prompt philosophy + two-stage ladder (2026-08-25)
- v1 (evidence-aware first-refusal push) REVERTED by user ruling: forcing the
  answer on the FIRST refusal harms legitimate go-back cases. Correct
  escalation (human analogy): try a few searches → answer from current info
  (partial-but-supported IS a submittable answer) → NONE only for ZERO
  question-relevant evidence.
- §2.7 REWRITTEN as the answering philosophy: "answer the way a person
  answers a lookup question" — partial support submittable / NONE reserved
  for zero relevance / one step-back allowed, then answer from what you
  hold / unobtainable-discriminator waiting produces nothing. Harness ladder
  = BACKSTOP: 1st refusal → re-select (go-back right kept, one-shot);
  2nd refusal → "answer from current support" WITH bindings shown; restart
  contract: post-restart None = terminal explicit empty (accepted at A
  phase — validate rejects empty entities). [NONE]/[Unable...] variants
  normalized (strip []"'()).
- 48×3 (phil_g3): **meanF1 0.7157 (session cohort high) / EM 119 / best3
  0.8617 (+4.4pp) / anyEM 45 (tie record) / allEM 33 / turns 7.9**; ladder1
  13×, ladder2 23× (the conversion works). vs ladder pack 0.7075/118/0.8173.
- Interim 267 gate (perfpack, OLD loop-ladder): 0.7512/674/best3 0.9173
  (record)/anyEM 259 (record) but allEM 183 — the burn-to-budget pathology
  (7/8 ladder cases died at 16 turns) that v2 fixes. Philosophy 267 gate
  launched.

### V3.3 FIXES: phil_r267g3 user audit (Kim Richards / Devil Dog, 2026-08-25)
- ① "already-shown on FIRST retrieval" ROOT CAUSE (WebQTest-1785 sample 1,
  replayed): the walk returned evidence under relation names the model did
  NOT select (tv.regular_tv_appearance.* vs selected tv_regular_personal_
  appearance.*) → no walked shape passed selection discipline, no anchor
  selected-rel edge → zero blocks; the ONLY selected edges left (Show
  --regular_cast--> m.x) lost their attr edges to the selection filter →
  _render_records rendered bare CVT tails → legacy BARE-CVT TAIL DROP
  discarded everything → 0 lines, while the within-call DUPLICATES (each
  pattern pair re-carried the same triples; _canonicalize_triples does not
  dedup) counted 16 on the FRESH shown-set → the false "(all 16 already
  shown in a prior subgraph)" branch fired on the case's first sg call.
  FIX (seq_tools): new pure helper `_select_uncovered(all_triples, covered,
  sel_shorts)` — selected+covered filter, WITHIN-CALL (h,r,t) dedup (ruling
  2026-08-20: cross-call suppression forbidden, re-retrieval re-renders
  full), and CVT ATTR REVIVAL: attr edges (unselected rels) of any CVT the
  facts section displays are fed to _render_records as record payload —
  they only ever surface inside the inline [k=v; …] bracket, never as edge
  lines, so ruling ⑧'s letter holds while ruling ④'s record content stays
  visible. The lying message branch DELETED from _sg_finalize. Kim specimen
  now renders `Hello, Larry --regular_cast--> m.0bngb3y [actor=Kim Richards;
  character=Ruthie Alder]` — the answer family was fully recovered.
- ② CANDIDATE PROVENANCE (Devil Dog specimen: candidate with no visible
  edge → model read absence as disconnection and dropped gold): new pure
  helper `_candidate_provenance(candidates, display_lines, fact_evidence,
  cur_fid)` — after assembly+budget, every candidate NOT visible in this
  render gets labeled in one appended line, grouped by source: `(earlier
  subgraph: sg1)` when ctx.fact_evidence has it (prefers other fids, falls
  back to earlier retrievals of the same fid), else `(walk candidates — no
  visible edge this case)`; closes with "absence from THIS render is not a
  disconnection". Candidates list itself stays clean (no suffixes that
  could leak into answers). Cap 10 missing + count marker.
- ③ max_raw_paths_per_pattern 24→90 (user's edit in logical_paths.py):
  verified against the renderer — instance reconstruction is EDGE-based
  (witness-independent), _SHAPE_INSTANCE_CAP=3000 / lines_per_shape=30 /
  _TREE_LINE_BUDGET=200 all hold (live A/B replay: Germany 390 paths → 36
  lines, Kim 86 → 13, V3.3 sizes ≈ V3.2 ±10%). No adjustment needed.
  NOTE: formatting.py `_select_support_paths(max_paths=24)` still bounds
  tree paths/support edges (upstream of candidates) — untouched, that is
  walk-content scope not rendering.
- VALIDATION: tests/test_render_pipeline.py +4 (attr revival + within-call
  dedup; first-retrieval renders evidence & zero overlap on fresh set;
  cross-call full display idempotence; provenance grouping) — suite 130
  green. Fastcheck 10-case: 0 crash, 8/10 hit, meanF1 0.586 (band), turns
  7.8; live message audit: 22 renders, 0 already-shown, 9 provenance lines
  correctly firing only when candidates are invisible. A/B report on phil
  captures (tmp/render_ab_report.md): Kim before-empty → after 4 record
  lines + provenance; render_ab_report.render_v33 now mirrors production
  (_select_uncovered).

### EVIDENCE-FIX BUNDLE (user audit round, 2026-08-25)
- ① max_raw_paths_per_pattern 24→90 (logical_paths.py:82) — the reintroduced
  branch cap that DROPPED answer-relevant records at the walk layer (Kim
  Richards' Devil Dog appearance never retrieved in f1).
- ② already-shown lie ROOT-CAUSED (agent): not cross-call state — a 3-step
  chain (selection filter killed all shapes → surviving CVT lost its
  unselected-relation attribute edges to the selection filter → legacy
  bare-CVT-tail drop killed the line → within-call duplicates counted as
  overlap → misleading message on the FIRST retrieval). FIXED: new
  _select_uncovered (within-call (h,r,t) dedup ONLY; cross-call always
  full render; CVT ATTRIBUTE REVIVAL — unselected-relation attrs re-enter
  as inline record brackets, never standalone lines, honoring both the
  selection-discipline and record-attrs rulings); the already-shown branch
  DELETED.
- ③ CANDIDATE PROVENANCE (_candidate_provenance): candidates invisible in
  the current render get grouped tags — "(earlier subgraph: sgN)" from
  fact_evidence, else "(walk candidates — no visible edge this case)" —
  plus the fixed line "absence from THIS render is not a disconnection"
  (the Devil Dog join failure). Candidate list body stays clean.
- 130 tests green; fastcheck 8/10/0.586 in-band; 22-render audit: 0
  already-shown, 9 provenance lines correctly placed. Milestone 48×3
  (evfix_g3): meanF1 0.7061 / EM 114 / best3 0.8450 / anyEM 43 / allEM 32
  — par in the phil/ladder band (0.7075-0.7157) with correctness defects
  fixed.
- CURRENT STACK: V3.3 render (per-rel/short-to-long/path-consistent) +
  ladder v2 (§2.7 philosophy, go-back right, 2nd-refusal answer-from-
  support, terminal explicit-empty) + evidence fixes (90/provenance/
  attr-revival/no-already-shown/zero-coverage notes).

### V3.4: Debussy completeness + naming + zero-hit hook (2026-08-25)
- USER AUDIT of perfpack_r267g3 (WebQTest-389, center = the WORK "D'un cahier
  d'esquisses", selected music/base.musiteca composer + book author):
  ① selected relations whose instances are SIBLING edges (neither endpoint a
  center: dozens of works --author--> Claude Debussy) fell wholesale into the
  remainder as one unlabeled merged line; ② the two selected composers share
  the SHORT name "composer" and merged indistinguishably — short-name keying
  was systemic (indexes, shapes, selection, coverage all keyed _short_rel).
- FIX ① (full-name internal keys, seq_tools.render_evidence_sections): ALL
  internal keys switched to FULL dotted relation names (edge indexes, shape
  hops, selection discipline, coverage, _select_uncovered matching); DISPLAY
  tokens shorten via _disp_rel() which disambiguates a short shared by ≥2
  SELECTED relations as `short[family]` (family = first segment):
  `composer[music]` vs `composer[base]`. Branch-ref tokens stay PLAIN short
  (the answer-side _BRANCH_RE expander would not match a bracketed token).
- FIX ② (selected-relation completeness sweep): after the shape blocks, all
  remaining selected-rel named↔named edges whose NEITHER endpoint is a
  center are grouped by shared terminal and rendered terminal-anchored
  reverse dense lines (`Claude Debussy <--author-- En blanc et noir | …`,
  120-cap + branch ref), spliced right after the tier-1 blocks (no overview
  line — overview indexes center-anchored shapes only); covered so the
  remainder never re-dumps them. Selected-relation edges now NEVER appear as
  unlabeled remainder lines.
- FIX ③ (naming, user ruling): the remainder section is renamed `── other
  relations ──` — "facts" is BANNED as a section name (semantic collision
  with the plan's f1/f2/sg fact vocabulary); its content is per-relation
  grouped by _group_facts_by_rel() (`  regular_cast:` headers; token-less
  record lines inherit the preceding relation).
- FIX ④ (all-∅ repair hook): when EVERY selected relation has no instance in
  the evidence (the ∅ lines cover all of them — the Kim-Richards-class
  non-empty-but-all-silent miss), the overview appends the cross-subgraph
  repair guidance (re-call with other candidate relations, or borrow a
  center from any earlier subgraph's evidence). Partial ∅ keeps the plain ∅
  declaration.
- Attr-key display: brackets print SHORT attr keys again (full-name keying
  had leaked `tv.regular_tv_appearance.actor=` into brackets); internal
  keys/coverage stay full.
- VALIDATION: tests/test_render_pipeline.py +3 (completeness+disambiguation
  on the Debussy structure — author family terminal-anchored, zero
  remainder, no bare duplicate short; partial vs all-∅ with the repair
  hook; remainder grouping + zero "facts" naming) — suite 133 green.
  A/B report (tmp/render_ab_report.md, perfpack captures): Debussy before =
  one unlabeled dump line → after = `--composer[music]--> Claude Debussy` +
  `Claude Debussy <--composer[base]-- Pour le piano`; Kim capture renders
  full-name-attr records then short keys. Fastcheck dipped 6/10 / 0.468 —
  per-case audit: all four misses are answer-layer churn (Germany gold vs
  graph-USD mismatch; 567 acted-vs-directed filter miss), mechanisms clean
  (0 already-shown, provenance + other-relations sections firing).
- MILESTONE 48×3 (render_v34_g3, wall 620s, 0 failed) vs evfix_g3 baseline:
  meanF1 0.7051 (par, −0.1pp) / **EM 119/144 (+5)** / **best3 0.8554
  (+1.0pp)** / anyEM 45 (+2) / **allEM 34 (+2)** / flip 52.1% / turns 7.5
  (−0.7) / empty 1 — every hit-family metric improved with the completeness
  form. PAR-PLUS verdict.

### V3.4 + FULL-STACK 267 GATE (2026-08-25)
- V3.4 shipped (Debussy/Kim audit round): full-name internal keys
  (systemic short-name collision — indexes/shapes/selection/coverage all
  short-name-keyed before), display disambiguation `composer[music]` vs
  `composer[base]`, selected-relation completeness invariant (sibling edges
  neither-end-center → terminal-anchored reverse dense rows; selected-relation
  edges NEVER dumped), residuals per-relation under `── other relations ──`
  (zero "facts" strings — naming collision with plan facts resolved), all-∅
  borrow-a-center repair hook, attr-key shortening leak fix. 133 tests green.
  Cohort milestone PAR-PLUS (EM 119 +5, best3 0.8554 +1.0pp, turns 7.5).
- FULL-STACK 267×3 (v34_r267g3: V3.4 + philosophy ladder + evidence fixes):
  meanF1 0.7521 / EM 672 / best3 0.8938 / anyEM 252 / allEM 188 / flip 51% /
  turns 7.2 / empty 9. vs ladder pack 0.7759/688/0.9074/203 — the three
  philosophy-family full gates (phil 0.7653, V3.4 0.7521) sit BELOW the
  ladder pack despite cohort PAR-PLUS. Empty 9 (vs 3) is the worst marker.
- READING: the accumulated display/evidence correctness layers (V3.3/V3.4
  render discipline + 90-witness + provenance) cost ~1.5-2.4pp at full scale
  vs the V3.2f+ladder config, OR this is the philosophy-ladder interaction
  (empty-9 suggests second-stage conversions going empty). The ship-config
  decision (form-correctness vs ladder-pack metrics) is USER's call; the
  bisect option remains (V3.2f render + V3.4 evidence fixes + ladder v1).

### FINAL-TURN + TIE-BREAK PACK (2026-08-26)
- Layered audit of v34 gate: empties 9/9 = budget-end no-answer (the 2nd-
  refusal conversion message got answered with MORE retrieval, not answers);
  variable misalignment 26/116 error trajs — TWO subfamilies: true
  misalignment (Stalin: answered ?person values for a ?nation question) and
  discriminator-unapplied (Taylor Lautner: ?earliest_film never bound).
  Taylor specimen root-caused: f2 relation selection got the WRONG FAMILY
  (award years ≠ release dates — non-empty but semantically wrong return
  defeats both the ∅ hook and walk-empty repair); model's "unobtainable"
  claim was HONEST vs displayed evidence; the actual violation was the
  tie-break ("canonical ordering / most prominent" = world knowledge).
- Shipped: ① BUDGET+1 FINAL TURN (rollout appends one demanded-answer round
  for round-exhausted actives — replaces silent budget death); ② §2.7
  tie-breaks are EVIDENCE-ANCHORED (fame/ordering/world knowledge banned;
  tied candidates submitted together) + "unobtainable must be checked
  against DISPLAYED evidence" (wrong-family retrieval → one re-selection
  for THAT fact before satisficing). Mechanical variable set-alignment
  REJECTED by user (would misfire on legitimate var evolution).
- Milestone 48×3 (finalturn_g3): meanF1 0.6657 / EM 114 / best3 0.8103 /
  allEM 33 / **empty 0 (5 cases got +1, all answered)** — mechanism works,
  mean in the 0.64-0.72 cohort band. 267 gate pending user's call.

### WALK/RENDER DEFECT ROUND (2026-08-26): ABM · Tupac · population · Randy
- USER AUDIT family, four specimens replayed forensically (capture at
  render_evidence_sections, WALK_POOL=0 replay of finalturn_g3 trajectories):
  ① ABM (WebQTrn-567, ?movie 27 centers, subjects+films): overview claimed
  `A Beautiful Mind --subjects--> ?x (4 instances)` while the instances
  anchor at OTHER films. ② Tupac (WebQTrn-2784): [film --starring] rows
  split into hop-1/hop-2 fragments + free-head `Poetic Justice --starring`
  rows. ③ population (WebQTest-212): `Sonora --population--> bare g.xxx`
  free-head rows + `Arizona --population--> [108 records]` mis-attribution.
  ④ Randy (WebQTrn-1731): false `Randy --instrumentalists--> [6 records]`
  overview + `[instruments_played --instrumentalists]` block duplicated
  verbatim + center truncated from a fold.
- ROOT CAUSES (all render layer, seq_tools.render_evidence_sections):
  (a) anchor_label = centers[0] for every shape; (b) formatting.py's
  sibling-CVT display mirror roots continuation paths at the path MID node
  → non-center-anchored 1-hop shapes → free-head rows; (c) whole-path
  selection discipline dropped detour chains (unselected bridge hops) whose
  last hop IS selected → their edges re-rendered detached by the sweep;
  (d) shape key (hops, term_cvt) split identical-instance shapes → twin
  blocks; block headers dropped hop direction → identical headers;
  (e) _EDGE_NOISY_SHORT contained member/role — killed group_membership
  record attrs ([member=Randy; role=Vocals] — the GOLD), broke membership
  chain reconstruction, and silently dropped musical_group.member even when
  SELECTED. (f) ①-risk: _TOP_PATTERNS=5 rank cut could starve a center's
  1-hop selected pattern (no specimen hit, guarantee added).
- DATA-LAYER FACTS (report to user, not fixable walk/render-side): ABM has
  ZERO film.film.subjects edges in the case graph (gold = Village of the
  Giants via q-entity `Child prodigy --film_subject.films--> VOG`); the
  population CVTs (g./m.) carry ZERO attribute edges (no measurement_unit.*
  in test_v4 — bare ids are data-honest, numbers exist only as direct
  topic_server.population_number edges on 3 of 4 centers); there is NO
  (Vocals, instrumentalists, Randy) edge — the gold runs through the
  membership CVT m.01vxjq8 [member=Randy; role=Bass guitar + Vocals].
- FIXES (seq_tools.py): no-free-head gate (tree paths anchor shapes only
  from a CENTER); last-hop-selected discipline replaces whole-path selection
  for chains (detour chains = correctly-lengthed multi-hop shapes, ordered
  after all-selected shapes); shape key = hops alone; direction in block
  headers (`[genre <--child_genres]`); overview head = real anchor
  population (var_label if declared, else folded names); center-priority
  truncation (_center_first before every cap); member/role removed from
  _EDGE_NOISY_SHORT; chain-beats-orphan promotion (≤4 capped shapes lifted
  when their edges would render detached); ① _select_patterns_for_render
  feeding guarantee (1-hop selected witnesses survive the _TOP_PATTERNS=5
  cut, ≤2 extras per selected rel).
- VALIDATION: tests/test_render_pipeline.py +6 (same-anchor overview +
  free-head suppression; Tupac full-prefix chains; direction headers +
  block dedup; center-priority truncation; membership record attrs reach
  the render; feeding-guarantee unit) — suite 140 green (2 pre-existing
  collection errors unchanged). Specimen audit (tmp/audit_specimens.py over
  tmp/captures_postfix.json): all four specimens PASS — ABM renders
  `[languages --language --subjects] Curious George --languages--> English
  <--language-- VOG --subjects--> Child prodigy | Giant`; Randy renders
  `Randy <--member-- m.01vxjq8 [member=Randy Jackson; role=Bass guitar;
  end=…; group=Journey] --role--> Vocals --instrumentalists→ …` (gold hop
  visible); population renders `[<--adjoins --adjoins --population]
  Arizona <--adjoins-- m.046csk9 --adjoins--> Sonora --population--> …`.
  Fastcheck + 48×3 pending below.

### WALK/RENDER DEFECT ROUND — ACCEPTANCE + WALK-SIDE FEEDING GUARANTEE (2026-08-26, this session)
- ACCEPTANCE of the four-defect fixes (successor agent verified the dead
  predecessor's working tree): all four specimen assertion families PASS
  (tmp/audit_specimens.py over fresh captures tmp/captures_postfix.json).
  ① ABM: the graph has ZERO `A Beautiful Mind --film.film.subjects-->` edges
  (49 out-edges, none subjects) — the all_triples-0 is DATA-HONEST; exactly
  4/27 centers have subjects edges and the walk delivered 4/4 in every sg
  call (tmp/audit_walk_hunger.py: per-sg-call graph-vs-walk-vs-render
  comparison). ② Tupac, ③ pop, ④ Randy: 0 walk-starved / 0 render-starved
  edges. Two more data boundaries confirmed: the 127 population CVTs each
  carry exactly ONE edge (population itself — [year=…; value=…] bracket is
  data-impossible; numbers surface via direct center population_number
  edges); no (Vocals, instrumentalists, Randy) edge exists — gold runs
  through membership CVT m.01vxjq8, now rendered with full record bracket.
- REAL walk-layer gap found in the SAME case (sg0): a center's INVERSE
  1-hop family (center = TAIL of the selected relation, `Film
  --produced_by--> Ron Howard` from center Ron) is bounded by the 24-path
  support cap — Option-B's leaf enumeration anchors on the witness's own
  HEAD, never the center — 35 graph edges, 24 carried (7 producer credits
  invisible: Alamo/Chamber/DaVinciCode/DarkTower/GoodLie/LostSymbol/Missing).
- FIX (kgqa/agent/seq_tools.py): `_guarantee_center_direct_edges` +
  call in `_sg_finalize` — backfill EVERY direct (center, selected-rel)
  edge from ctx's full edge arrays into all_triples when the walk missed
  it; qualification = 1-hop pattern instance definition (relation selected
  + one endpoint a center) so pattern-path discipline holds by
  construction; endpoints land in subgraph_entities/all_candidates
  (answerable + legal future centers); schema-prefix filter mirrored;
  dedup both orientations; idempotent. tools.py / logical_paths.py
  UNTOUCHED (walk itself unchanged; the guarantee is admission-side).
- TESTS: tests/test_render_pipeline.py +1
  (test_guarantee_center_direct_edges_backfills_walk_gap) — suite 141
  green (2 pre-existing collection errors unchanged).
- VALIDATION: fastcheck 10×1 meanF1 0.4935 / 6 hit / 0 empty / 0 crash
  (band 0.46-0.59); ABM specimen sample 567_df97 f1 0/0/0 → 1.000
  ("Village of the Giants"). MILESTONE 48×3 (reports/walkfix_g3.json) vs
  finalturn_g3: meanF1 0.7016 (+3.6pp) / EM 120/144 (+6) / best3 0.8109
  (par) / anyEM 43 (par) / allEM 36 (+3) / empty 0 / failed 0 / turns 7.7
  — PAR-PLUS. Specimens in-cohort: Tupac 2784 6/6 f1=1.0, pop 212 3/3
  hit, Randy 1731 3/3 hit (answer layer prints Bass guitar|Keyboard);
  ABM 567 fresh samples still miss at the ANSWER layer (evidence path
  proven by fastcheck hit). A/B four specimens: tmp/render_walkfix_ab.md.

### WALK-FIX FULL-STACK 267 GATE (2026-08-26) — RECOVERY COMPLETE
- Full stack (V3.4 render + philosophy ladder + §2.6 ambiguity-is-not-
  contradiction + evidence fixes incl. _guarantee_center_direct_edges top-up
  + var-mismatch intercept + budget+1 final turn): **meanF1 0.7632 / EM
  684/801 / flip 47% / best3 0.8947 / anyEM 250 / allEM 201 / turns 7.1 /
  empty 1 (best ever)**. vs the ladder pack (0.7759/688/0.9074/203): −1.3pp
  mean / −4 EM, but empty 3→1 and the correctness layers (four user-audited
  defect fixes + honest-evidence discipline) are structural. The phil-family
  full gates now cluster 0.75-0.78 — within churn of the ladder pack.
- OPS: the gate's first launch hung 25min — :8000 hosted a ZOMBIE vLLM from
  08-24 (/v1/models answered but inference dead; round-1 POST futex-hung;
  GTE fine so prelink passed). RULE: health checks must do a REAL
  completion, and stale vllm/EngineCore processes must be reaped before
  runs (705xxx pair was residue). Clean restart (0.82) fixed it; gate
  rerun completed in 2732s.
- READY FOR TRAINING (user directive): baseline numbers set. Reward already
  computed in rollout (f1 + format + efficiency); POLICY LoRA path live.

### SESSION HANDOFF (2026-08-26, before context compaction → training)

## CURRENT STACK (all landed, 141 tests green)
- RENDER V3.4: per-selected-relation blocks, short→long, path-consistent
  chains, whole-chain rows (center prefix → intermediate → folded terminals),
  CVT attr inline + revival, branch refs, 120 entity cap, candidate
  provenance tags, other-relations grouping (no "facts" naming), full-name
  relation keys with disambiguation `composer[music]`, zero-coverage ∅ notes,
  all-∅ borrow-a-center hook, _guarantee_center_direct_edges (walk top-up
  from ctx edge arrays)
- PHILOSOPHY: §2.7 human answering posture (partial support submittable,
  NONE only for zero relevance, tie-breaks evidence-anchored — no
  fame/ordering/world knowledge, unobtainable checked against DISPLAYED
  evidence), §2.6 ambiguity-is-not-contradiction
- LADDER v2: 1st refusal → re-select (go-back right kept); 2nd refusal →
  answer from current support WITH bindings shown; post-restart None =
  terminal explicit empty
- HARNESS INTERCEPTS (mechanically checkable, ALL SHIPPED):
  repeat-gate, purity detector, EXTEND gate, STAGE GATE, early-answer
  reminder (blocking-only), offpool, MID strip, CVT-entity reject, empty
  rescue, branch-ref expansion, freeze gate + hallucination filter,
  None/[NONE]/[Unable→] refusal ladder, var-mismatch (dual-bound),
  literal-conversion guard (bare number + answer_type year/date → named
  entity), unbound-var reminder (answered ?other values when answer var
  unbound), budget+1 final turn
- OPS: :8000 vLLM (VLLM_GPU_MEMORY_UTILIZATION=0.82, qwen35 binaries),
  :8003 GTE (batch window adaptive), GTE client round-batch + dedup,
  walk round-batch coordinator + lane affinity (WALK_POOL=4)

## LATEST 267×3 NUMBERS (walkfix_r267g3 — the current baseline)
  meanF1 0.7632 / EM 684/801 (85.4%) / flip 47% / best3 0.8947 /
  anyEM 250 / allEM 201 / turns 7.1 / empty 1 (best ever)
  vs ladder pack 0.7759/688 (reference high; predates correctness layers)

## ERROR AUDIT RESULTS (walkfix_r267g3, 66 error cases)
- 32 (49%) gold-in-ckpt-no-block: model binds gold but answers wrong —
  TRAINING TARGET (answer selection quality)
- 17 (26%) gold-not-visible: retrieval miss
- 13 (20%) gold-vis-not-ckpt: model didn't bind visible gold
- 4 (6%) harness-suspect: 1 real (CVT guard blocking attribute extraction
  = WebQTrn-3605 pattern), 3 guards working correctly on bad outputs

## DEEP-DIVE: 4 specimens of gold-in-ckpt failures (four different roots)
- Saami: plan didn't capture discriminator constraint (initials sma) →
  world-knowledge guessing
- Liang Qichao: SPARQL same-entity conjunction (Zhuang Zhou IS both
  influencer AND sacred text) vs our variable-chain decomposition loses
  the intersection; 1/3 samples hit by using 3-step decomposition that
  surfaces the entity-level intersection in ANALYSIS
- Super Bowl: ANALYSIS correct (Super Bowl XXXV) but submitted literal
  "2001" (answer_type:year conversion) → literal-conversion guard shipped
- Parish: ANALYSIS correct (Saint Michael Parish) but submitted Rihanna
  (?artist value, answer var ?parish unbound) → unbound-var reminder
  shipped

## KEY ARCHITECTURAL INSIGHT (user + SPARQL analysis)
CWQ compositional questions often require SAME-ENTITY conjunction (X
satisfies A AND B) while our plan decomposition uses variable chains
(?A→?B) that lose the intersection. The model sometimes discovers the
intersection in ANALYSIS (when the decomposition makes both lists
visible), but not reliably. This variance is the training target.

## NEXT: TRAINING (user directive — stable variance)
- Reward already computed in rollout: f1 + 0.1*format_ok + 0.1*efficient
- POLICY LoRA path live in seq_rollout
- Train on rollout batches from current stack; the 32 gold-in-ckpt cases
  are the direct training signal (model knows the answer but doesn't
  select it)
- scripts/train_offline_grpo.py exists; iterated RL path documented

## OPS RULES (accumulated)
- Health check MUST be a real completion (zombie vLLM incident 08-26)
- Reap stale vLLM/EngineCore processes before runs
- CASE_FILTER=tmp/regress267.txt for 267; tmp/v21_cohort.txt for 48;
  tmp/fastcheck.txt for 10-specimen quick check (~3min)
- SEQ_PROMPT=V21 LLM_MODE=http WALK_POOL=4 INFLOW_TARGET=500 (267×3 only)
- SESSION_MEMORY is 4000+ lines — grep for specific topics

## CREDIT-ASSIGNMENT AUDIT + IN-FORMAT TF CALIBRATION (2026-08-28)
- Full analysis: specs/training_credit_audit_20260828.md (audit of
  seq_advantage.py chain + GPT two-work proposal + user's 3 adjustments).
- KEY NEGATIVE RESULT (3rd independent calibration): teacher-forced gold
  probability does NOT improve in-format. 120-rec stratified sample from
  reports/walkfix_r267g3.json, 3 arms (in-format think+FINAL_BINDINGS+
  tool:answer continuation / bare full / bare 15-line trunc):
  corr(pF,F1) 0.251/0.276/0.325; corr(pF−p0,F1) −0.037/+0.085/+0.192;
  p0_info (memory baseline) = STRONGEST single predictor (+0.299 all,
  +0.100 hard). Format is NOT the bottleneck — exact-token reading of
  answer support is (v9 0.02-05 → 0.13-0.33 now, gain from full render +
  per-entity + gold-surface-form normalization).
- VERDICT: log p(gold|·) never becomes the trajectory score (F1 group-norm
  stays); TF only for within-trajectory behavior classification + Work-2
  teacher purification. Gold-bearing LOO exemption MANDATORY (33-38% of
  gold-bearing modules LOO-negative in BOTH formats). Re-mention leak
  (later acks re-render removed edges) mean 0.23 → ΔI biased to 0,
  false-redundant is the failure mode.
- vLLM scoring route VERIFIED (no unload/reload): POST :8000
  /v1/completions {prompt, echo:true, logprobs:1, max_tokens:1} →
  prompt_logprobs per position. Traps: response prompt_token_ids may be
  None (re-encode client-side); Qwen3.5 chat template DISCARDS assistant
  reasoning field (rollout history = content only); template ends
  'assistant\n<think>\n' under add_generation_prompt=True (continuation
  goes INSIDE the think block); NEVER score the entities: copy when
  FINAL_BINDINGS already states gold (copy-fidelity ≈1.0, smoke-verified).
- scripts/informat_tf_calib.py (one-off, gitignored): module-LOO surgery =
  remove sg ack + [fid ✓] checkpoint lines + CANDIDATES(?var) COMMIT lines;
  rr acks kept; full ack text + V21 system (no 15-line cap, no sys_cap).
  Output tmp/informat_tf_calib.json; log logs/informat_tf_calib.log.
- User's cross-trajectory advantage pooling (effective→A_max,
  harmful→A_min, redundant→median/½A_min): audited OK as
  classification(within-traj) × level(group-stats) factorization; 4 knobs
  needed — redundant pricing polarity-coupling (clamp
  min(½|A_min|,|A_max|)), positive-mass scale (Σa⁺ cap ≈1.5·A_max or clip),
  all-fail-group rescue (keep v10.2 measured-gain +min(Δp,0.15)),
  all-success-group ε. See audit doc §6.2.
- Reasoning-field postmortem (user challenge, verified against template
  source): Qwen3.5 template reads history thinking ONLY via key
  `reasoning_content` (we send `reasoning` → dropped by NAME) AND only
  renders think for assistant turns after the LAST user query (our flow
  always has a tool ack after → thin-thinking everywhere). Rollout never
  conditioned on past thinking; content-only scoring prefixes ARE
  same-source. Response-side reasoning return + client capture both fine.
- Redundancy-classification enemies, measured: probability ceiling
  (83% of recs have p0_info>0.6 → prob-domain ΔI squeezed; fix = log-odds
  domain / low-p0 gating / ΔI/(1−p0)) and re-render leak (0.23 mean).
  Exact-duplicate re-calls rare (3% recs / 1% calls) — deprioritized.
- Tool-trace arm + structural gate (scripts/tooltrace_calib.py, run 2):
  context = plan call + tool commands + real acks ONLY (dialogue layer
  excluded → checkpoint/COMMIT leaks gone by construction), bare Answer:
  tail. corr(pF,F1)=+0.215 — third confirmation format is NOT the
  bottleneck. STRUCTURAL GATE validated: undirected anchor→gold
  reachability over parsed ack instance lines (note prose + node1/node2
  templates + ?var placeholders stripped) — 25% of LOO modules necessary
  at zero GPU; rescues 22% of ΔI-redundant verdicts (6/27; bare 7/65);
  13/80 silent (gold unreachable in full). Sequential criterion
  (Δp_k≈0 ⇒ redundant) agrees with LOO 88% — disagreeing 12% → ambiguous.
  Cross-format ΔI corr LOW (0.15-0.25) → probability classification is
  format-noisy; three-level classifier proposed: L0 structure gate →
  L1 ΔI on tool-trace → L2 sequential confirmation, + gold-bearing
  exemption + low-p0 gating. Data: tmp/tooltrace_calib.json,
  logs/tooltrace_calib.log.
- Cross-trajectory alignment + LOO stability (scripts/xtrack_struct_analysis.py):
  pure-LOO VERDICT agreement across contexts only 63-65% (gate or no gate)
  → LOO-only classification carries ~1/3 context-noise; fixes = structural
  gate anchor (25%), wider dead-zone (train only high-confidence), or
  3-context majority vote. Sequential/gain criterion droppable (88% redundant
  with LOO). Disconnected-trajectory judging vs connected reference works:
  91% of 267 cases have ≥1 connected sample; on-path rate bracket
  [16% (union-shortest-path ref) .. 86% (any-connected-module ref)] —
  reference DEFINITION is the design lever; right middle = each connected
  trajectory's own module sequence along its own path. Teacher skeleton
  extraction for Work 2 demonstrated (module chain of connected+correct
  trajectory). Parser caveat: gold-form mismatch mislabels some correct
  trajectories as disconnected (WebQTrn-857 s0 f1=1.0).
- Standalone×LOO 2×2 taxonomy + golden path (scripts/golden_path_analysis.py):
  LOO-removed block scored ALONE (V_alone semantics, alone_gain=p_alone−p0):
  core 24% / duplicate 54% / noise 19% / bridge 4%. Duplicate dominance
  matches re-render leak — modules informative but duplicated. Golden path
  = best connected trajectory's OWN realized anchor→gold path (prefer
  F1-correct, most on-path, fewest off-path modules — NOT shortest);
  available in 243/267 cases (202 correct). Disconnected coverage BIMODAL:
  median 0.00, ≥50% coverage 39-42%, max 1.0 — sharp judgment: same-track
  (partial credit = modules hitting core path) vs off-track-from-start
  (58%). Data: tmp/golden_path.json.
- Credit dry-run (scripts/credit_dryrun.py, offline all-1735-module):
  structural-increment disambiguation (eff_first 45% / red_repeat 8% /
  red_unused 31%), golden-path divergence (harm_divergence+div0 43 mods /
  eff_golden_partial 25), teacher library 243/267 (purified tool traces,
  mean 1.2/3.2 kept — OVER-AGGRESSIVE, relax to on-path∪gold-bearing),
  pooling credits: eff +0.4~0.6 / harm −0.6~−0.8 / red −0.26~−0.30 (target
  shape confirmed). HEADLINE: 46% of cases are all-success groups →
  A_max=0 → ZERO positive signal — training batch MUST select hard groups
  (error cohort) or add absolute ε floor for effective in all-succ.
  rescue 9%. Data: tmp/credit_dryrun.json.
- Constraint-module recovery (user catch, scripts/constraint_recover.py):
  over-aggressive teacher purge confirmed — 21% of off-path modules are
  LOO⁺ (removal drops gold prob: the constraint evidence the structural
  path misses); plan-fact attribution (binding var ≠ answer var) recovers
  223 constraint modules (e.g. ?film vs ?actor conjunction side). New keep
  rule: eff_first ∪ (red_unused ∧ (fact_var≠answer ∨ gold-bearing ∨ LOO⁺));
  kept mean 1.07→1.38; the 223 also move to A_max on the credit side.
- Unified comprehensive classifier (user ruling: multi-indicator fusion,
  never single-test; scripts/unified_classifier.py): 9 indicators with
  calibrated weights (gate +1.0 / first-carrier +0.8 / constraint +0.8 /
  LOO⁺ +0.5 / alone⁺ +0.4 / repeat −0.6 / unused −0.4 / divergence −0.8 /
  LOO⁻ −0.5; gold-bearing = harm veto). Abstain when total vote mass <0.5
  (single weak indicator cannot decide) or |score|/mass <0.7. Result:
  eff 59% / red 7% / harm 4% / ABSTAIN 30% (= the queue needing the
  probability layer). LOO leave-one-out agreement 32% but confusion
  concentrated in fusion-eff × LOO-red — the exact cell where the
  structural gate already proved LOO wrong (leak+ceiling). Decision
  order: structural fusion → abstainers to probability layer → still
  conflicted → dropped. Data: tmp/unified_class.json.
- DESIGN PHILOSOPHY ratified (audit doc §8): module validity = unobservable;
  four orthogonal projection axes (counterfactual/informational/compositional/
  intentional), each with CALIBRATED failure modes (leak .23, ceiling 83%,
  competition 33-38%, duplicate 54%, constraint-blind 21%, self-declare).
  Fusion rules: calibrated weights, deterministic beats noisy EXCEPT in
  deterministic blind spots (constraints covered by intent axis); mechanistic
  bias → veto not averaging (gold-bearing); abstain is first-class (clean
  signal > coverage). Three operating laws: verdict (no single-test) /
  reference (pool consensus judges the unjudgeable) / decoupling (class vs
  level). Falsifiable predictions recorded as acceptance criteria for the
  training stage (§8.5): high-conf trains better; abstain queue resolves
  mostly-redundant; constraint→A_max reduces conjunction-question variance;
  single-axis ablations degrade rescue counts.
- Trajectory-signal manual audit (9 specimens): eff 3/3 + harm 2/2 CORRECT;
  red/repeat exposed two parser failure modes: (1) display economy (folded
  terminals/?x tails → fake cliques) — FIXED via candidates+checkpoint
  channels in parse_edges/module_edges (dist: eff 68%, abstain 25%, conf
  .94; date-discrimination specimen correctly flipped to eff/constraint);
  (2) HUB BLOAT (anchor module walk explodes to 1000+ edges, swallows all
  downstream semantic edges → fake repeat) — fix designed: row-level
  triple increment (same center+rel+row = repeat) + checkpoint closure
  channel ([fid ✗ empty] → redundant). NOT yet wired.
- Trainer optimization audit: loss = advantage-weighted PG, NO ratio/clip/
  KL, epochs=1 default. VERDICT: first-pass at θ=θ_old is EXACTLY one GRPO
  step (group baseline matches) — the 7-round parity was signal-side, not
  optimizer-side. Risks: negative-advantage has NO brake (unlikelihood-ish;
  pooled harm to A_min≈−1.4 = top instability spot), epoch>1 = silent
  off-policy, per-turn denominator batch-wide + Σa⁺ uncapped. Upgrades:
  strict epochs=1; store π_old per-token logprobs via echo+logprobs → add
  ρ-clip in the chunked per-turn path (exact offline GRPO, no new infra).
- DISPLAY-ONLY ruling implemented (user: judge only what is displayed;
  hidden/cropped content excluded): row-level increment via parse_rows
  (counters stripped; pairwise-clique increment废弃 — hub bloat root
  cause), closure channel ([fid ✗ empty] → −0.6), gold display filter.
  Final distribution: eff 65 / red 4 / harm 4 / abstain 27, conf .92.
  Specimens: date-discrim → eff/constraint ✓; Kirk repair → red/closure
  ✓; Lautner films → abstain (anchor module's DISPLAYED candidates already
  contained gold → 1-hop path, downstream full re-presentation = unused —
  self-consistent consequence of the ruling, resolves via probability
  layer). Trainer audit done (§9): first-pass = exact GRPO step; risks
  negative-advantage-no-brake / epoch>1 off-policy / Σa⁺ cap; upgrade =
  stored π_old logprobs + ρ-clip.
- Abstain queue RESOLVED (user reframing: gain/no-gain binary, abstain =
  unmeasured not verdict; scripts/abstain_resolve.py): 466 queue →
  1816 deduped scoring requests; fixed silent BPE-merge span bug (" Belize"
  merges with leading space → empty span → 110 dI=None; score() now uses
  offset mapping). Queue: eff 47%/harm 5%/red 2%; residual 215 decompose =
  noise 44 + near-tie 66 + competition-corrupted 105. Brad Stevens mod@10
  (answer-bearing, alone=+0.589) has dI=−0.064 — pure probability rule
  would brand 32% of queue harmful; veto is what blocks it. TERMINAL
  taxonomy (zero abstain): eff 1350(78%)/red 197(11%)/harm 86(5%)/
  untrainable-corrupted 105(6%, kept out of training). Prereqs remaining:
  all-success-group ruling, π_old+ρ-clip, teacher replay, then batch.
- Competition-corruption resolved (user joint-contribution hypothesis
  CONFIRMED for 37% of pair-testable: pair-LOO dI_pair up to +0.37 where
  single dI=−0.05; scripts/pair_loo.py). Second mechanism: MEMORY CEILING
  (Brad Stevens family — even removing all evidence, p stays: probability
  axis cannot measure "need" on memorized questions) → resolved by the
  within-trajectory CARRIER rule (checkpoint declares ≥1 gold ∧ traj
  f1>0.5 → eff; usage beats need-on-memorized-questions). 105 → joint 10 +
  carrier 64 + truly-untrainable 31. TERMINAL: eff 1424(82%)/red 197(11%)/
  harm 86(5%)/untrained 31(1.8%). Classifier is now FULLY closed.
- USER AUDIT #1 (Brad Stevens specimen) → 4 mechanism rulings implemented:
  (1) ENV-CONTENT is the core (calls=intent, declarations=fallible, acks=
  truth); (2) BINDING OWNERSHIP — checkpoint bindings belong to the
  retrieval that FIRST declared the fact (re-declarations created fake
  1-hop shortcuts evicting the true carrier: @16's re-decl gave @15
  brad→finals edges, on_mod={15}, @10 mis-read unused); (3) necessity gate
  computed for ALL modules (not just scored subset); (4) TRIPLE-level
  increment = pairwise links (h, rel|attr-key, t): chains cartesian-
  flattened + bracket attrs as (owner,k,v) — "X --team--> m [team=Boston]"
  ≡ "X --team--> m --team--> Boston". Plus semantic fix: pure-redundancy
  votes can NEVER yield harm (harm needs div/loo_neg intent) — harm 65→21.
  Specimen now exactly matches the human verdict: @5 eff / @10 eff
  (necessary) / @15 red(repeat). Terminal after chain rerun:
  eff 1430(82%)/red 231(13%)/harm 43(2.5%)/untrainable 31(1.8%).
- ENV ΔG ruling implemented (user #5: increment = actual graph triples, NOT
  ack-text parsing; scripts/replay_delta_g.py): full replay of all 1736 sg
  calls (plan re-dispatched for anchor seeding, checkpoints via
  _update_var_bindings, round-level concurrent walks), 98% coverage, keyed
  by ACK idx. |ΔG|≤3 ⟺ repeat — a ZERO-PARSING mechanical criterion (the
  accumulate layer's cross-call dedup IS the increment). Specimen #1
  env-certified: @5 ΔG=18 eff / @10 ΔG=51 eff+necessary / @15 ΔG=3 repeat.
  Text-layer systematically UNDERESTIMATES redundancy (rendering makes
  re-presentations look new): red 6%→15%. TERMINAL after chain:
  eff 1243+7+52=1302(75%) / red 269+96 abstain-noise≈16-17% / harm 42(2%)/
  untrainable 26(1.5%).
- USER ALL-CLASS AUDIT #2 (18-specimen pack): verdict corrections
  implemented — #16 harm→eff via CHAIN-NECESSITY vote (weight 1.0: later
  call's center introduced by this module's ΔG ⟹ structurally
  indispensable; @5 introduced Mosque = next call's entry point);
  #17 untrainable→red (constraint-mismatched small retrieval |ΔG|≤10 —
  evidence granularity, not model error); #5 eff confirmed (constraint
  worked, failure is answer-layer). TERMINAL: eff 1332(77%)/red 306(18%)/
  harm 28(1.6%)/abstain 52(3%)/untrainable 17(1%).
  FILED for prompt/rendering tracks (NOT classifier): (a) §7.5 CVT-strip
  guidance doesn't teach HOW to re-declare with bracket attrs → model
  retries rr with dead ?var; (b) candidates list not grouped by relation;
  (c) 2-hop rows missing top-level relation header (gnis_feature_id
  specimen); (d) top-3 patterns-per-relation cap too tight — patterns
  beyond top-3 lost.
- USER AUDIT #3 → structure layer switched to ENV GRAPH (cumulative replayed
  ΔG; ownership=first introducer): own-path/necessity/golden/coverage all
  env-based now. All-shortest-path OWNER UNION (single BFS was hijacked by
  vacuous hub routes: tupac—USA—juice beat tupac—perf-record—juice).
  Closure vote subordinate to env (✗empty only when |ΔG|≤3). Constraint
  vote requires yield usage. Zero-signal ⇒ red (not abstain). Specimens
  match human rulings exactly: located-ID @7/@11 eff + @14 red; #17
  @5/@9 eff + @15 red. Distribution: eff 60/red 26/abstain 13/harm 1.
  RETRACTED the "top-3 too tight" item (misread — display may exceed 3).
- SIG channel (user ruling #6): (center, relations) coverage vs golden-route
  steps — center hit ∧ rel-coverage≥0.5 ⇒ sig vote (+0.8); call args are
  env-validated by replay execution. Covers 50% of modules incl. 196
  off-path (disconnected partial credit now hub-noise-immune). Answers:
  shortest path runs on the WHOLE accumulated env increment graph, multi-hop
  (the perf-record hijack WAS the whole-graph BFS + hub; fixed by all-
  shortest owner union). Distribution: eff 64/red 24/abstain 11/harm 1.
- THREE-CLASS CLOSURE (user: "不是应该分到三类吗"): classifier-level
  abstain = pre-resolution queue (132 unmeasured + 47 near-tie + 8 lone-
  alone). After chain rerun TERMINAL = eff 1247(72%)/red 457(26%)/
  harm 21(1.2%)/untrainable 10(0.6%) — zero abstain; the 10 are
  competition-corrupted (pair-stable, non-carrier, |ΔG|>10) kept out of
  training per the clean-over-coverage ruling.
- USER AUDIT #4 → zero-signal rule REVISED: tot==0 ∧ |ΔG|>10 → abstain to
  probability layer (NOT red — specimen: constraint-check module |ΔG|=85
  has real gain). Terminal after chain: eff 1210(70%)/red 418(24%)/
  abstain 87(5%→probability)/harm 20(1%).
- RENDERING REFACTOR SPEC RATIFIED (§6.24, user ruling #7) — NEXT WORK:
  (1) top layer = the CALL's requested relations, one group each;
  (2) inside: patterns by path length ascending, aggregating all paths
  hitting that relation (incl. as last/intermediate hop);
  (3) var-label fallback: multi-center headers show the FACT's declared
  ?var (checkpoint), not just call-arg ?var (seq_tools.py:1432 heads[:4]
  truncation at :1435 to remove — centers are the model's own, never
  truncate); (4) walk-layer question filed: 3-hop pattern with NO CVT
  middle hit (language→primary_language→genre) — chain enumeration
  CVT-gating suspect. Plus 6 prior harness/rendering items (§6.23).
- INCREMENT SEMANTICS FINAL (user ruling #8): ΔG counts ONLY the
  answer-path-relevant part (edges on an anchor→gold shortest path);
  gold-adjacent ΔG edges = strongest positive (gold_adj vote +0.8, fires
  on 1268/1735); raw volume never judges (hub-bloat). sig gated on
  path-relevant NEW info (re-executing the same signature ≠ coverage).
  repeat ⟺ dg_rel≤1. TERMINAL: eff 1420(82%)/red 259(15%)/abstain 35(2%
  probability queue)/harm 21(1%). Specimens: Brad @5/@10 eff + @15 red ✓.
- CLASSIFIER v2 DESIGN RATIFIED (rulings 9-11, §6.26): UNIT = FACT BLOCK
  (rr + sg* grouped by fact; rr relation-choice error = the block's key-
  decision harm). SCORING = structure-level replay (question+plan+calls
  ±removal = the validated tool-trace arm, NOT full dialogue). LOGIC:
  raw ΔG≠0 = base prerequisite; path-relevant ΔG==0 = repeat ⟹ redundant
  (probability readings are duplication artifacts, secondary); break/chain
  ⟹ eff-and-necessary; post-connectivity exploration: ΔG≠0 ∧ removal-
  drops-probability ⟹ eff, ΔG≠0 ∧ no-drop ⟹ redundant; harm = key-decision
  divergence ∨ removal-raises-probability (gold veto). Structure answers
  "does evidence exist", probability answers "was it needed". NEXT WORK:
  v2 rewrite (fact-block grouping → boolean lattice → tool-trace scoring →
  clean full-chain rerun → specimen regression: Brad@5/@10/@15, #16, #17,
  located-ID). Do NOT salvage the weighted-fusion code (audit verdict).
- CLASSIFIER v2 RUN COMPLETE (scripts/classifier_v2.py): 1631 fact-blocks
  (rr+sg* by fact), block-level probability via structure-level replay
  (3357 reqs/1002s). VERDICT FIX: demoted div to marker (it fired 21% harm
  on legitimate post-connectivity exploration); harm = removal-raises-p ∧
  ¬gold-bearing only. TERMINAL: eff 1005(62%)/red 594(36%)/harm 32(2%).
  div=True blocks (477) resolve via probability: red 329/eff 130/harm 18 —
  post-connectivity exploration is mostly redundant, some constraint-eff,
  rarely harmful. Data tmp/classifier_v2.json; review pack tmp/v2_review.md.
  Scoring speed: prefill-compute-bound (~15-25k tok/s ceiling); prompt-array
  batch endpoint verified; next-run levers = 1 gold + scoring truncation
  (~4-5min/run). Golden-path-fork harm semantics to be re-merged when the
  cross-trajectory reference is wired into v2.
- v2 review pack FULL-DETAIL version (scripts/v2_dump.py → tmp/v2_review.md):
  per-block rr+sg calls, ack heads, actual ΔG edges, all readings — user
  specimen (Filaret WebQTrn-2319 s2) auditable: sg1.f1 leader-record→Ukraine
  (nec), sg2.f1 languages (ΔG=32 incl golds); error at official-vs-main
  language discrimination. Batch endpoint wired into classifier_v2 (prompt
  array ×16 ×4 concurrent + client-side offset extraction); next runs add
  1-gold + scoring truncation. Missouri-River rendering-density specimen
  filed into the §6.24 refactor fixtures (35-entity tails, near-inverse
  duplicate blocks, repeated CVT brackets).
- Probability TRIPLE persisted (p0/pF/p_loo per block in tmp/
  classifier_v2.json; shown in tmp/v2_review.md 概率 line) after rerun.
  Batch-endpoint live test: 3357 reqs in 960s ≈ same as single (3.3/s) —
  prefill-compute-bound confirmed; speedup levers remain 1-gold +
  scoring truncation. NOTE: classifier_v2.py's in-code verdict still uses
  the old div→harm rule (21% harm) — the RULING-11 recompute must be
  applied after every run (inline snippet in SESSION_MEMORY §6.27 entry
  pattern) until the script's verdict block is updated; verdicts in the
  saved json are now ruling-11 correct (eff 54%→62% after recompute).
  :8000 server was stopped for a local-engine bench (init failed twice —
  root cause undiagnosed, parked) and RESTARTED with the original command
  line (PID 219933, health-checked with a real completion).
- SPEED BENCHMARK (controlled, 32 identical prompts / 118k tokens):
  HTTP single 7.6k tok/s < HTTP array-batch 10.5k < HTTP 4×8 batch 12.1k ≈
  LOCAL in-process 12.5k — ALL prefill-compute-bound; endpoint choice is
  NOT the lever. Historical "local was fast" (15207 pairs/199s) was due to
  tiny prompts (15-line truncated evidence ≈ 300-500 tok) vs today's 3.7k
  full traces. REAL levers: 1 gold + scoring-specific truncation (~4-5min
  per full run). Local-engine traps (3): needs __main__ guard (spawn);
  CANNOT coexist with :8000 (NCCL); prompt_logprobs OOMs at util=0.85 —
  use 0.75 + max_num_batched_tokens=2048 + max_num_seqs=64 (IG recipe).
  Server :8000 stopped twice for these tests and restarted each time with
  the original command line; verify health (real completion) after any
  such cycle.
- SCORING BUG FIXED (user catch): v2 aggregation read only golds[0] —
  single-gold forcing on multi-gold LIST questions split probability mass
  (sacred-text specimen read pF=0.083 on fully-supported evidence).
  Continuation is now the FULL sorted gold-list string, mean per-token
  logprob over its span (the ratified 拼接文段 convention). Specimen now:
  sg2.f1 pF=0.31 p_loo=0.068 dI=+0.24 (removal collapses the list prob);
  deltas unaffected by list-format entropy. TERMINAL (ruling-11):
  eff 1023(63%)/red 573(35%)/harm 35(2%). classifier_v2 in-code verdict
  block still has the old div rule — apply the ruling-11 recompute after
  each run until fixed.
- ANSWER-CALL LEAK FIXED (user catch): build_trace included `tool: answer`
  calls in the scoring context — every probability was partly a copy-read
  (pF high with no gold in evidence, p_loo flat). Fixed: answer calls
  excluded; probabilities now evidence-only. NOISE FLOOR measured (from
  user-supplied vLLM issue #42019: prompt_logprobs is batch-order
  dependent): our gold-span |Δp| up to 0.029 → dI threshold raised
  0.005→0.05. Prefix caching: design-blocked for prompt_logprobs
  (skip_reading_prefix_cache) + order bug — speed levers remain truncation/
  1-gold. ALONE-GAIN restored per block (p_alone in dump+verdicts).
  Angelina specimen now exactly as user predicted: festival block
  p_alone=0.04 dI=0.026 → RED (wrong-direction walk); Jolie block
  p_alone=0.93 dI=0.786 → eff. TERMINAL: eff 1036(64%)/red 581(36%)/
  harm 14(0.9%). classifier_v2 in-code verdict block still old — apply
  the ruling-11 recompute (now with TH=0.05) after each run.
- TWO STRUCTURE FIXES (user Rome-specimen catch): (A) value literals
  (dates/numbers) were graph NODES — undirected reachability routed through
  them (rome→popCVT→"2011-08:00"→CVT→lazio), defeating the necessity gate;
  now value-literal endpoints are excluded from the env graph. (B) chain
  vote skipped ?var centers — sg2's center "?location" now expands via its
  checkpoint bindings (the values sg1 introduced) → chain fires. Rome
  specimen: sg1 nec+chain → eff; population block dg_rel=0 → red.
  TERMINAL: eff 1338(82%)/red 290(18%)/harm 3(0.2%). v2_dump now shows
  p_alone per block. Recompute script /tmp/recompute_v2.py (transient —
  fold into classifier_v2's structural pass next session).
- CHAIN VOTE BUG FIXED (user Chapter-27 catch): the block's OWN checkpoint
  bindings counted as "later usage" → last-block walks (Scarlett 撒网 267
  edges) falsely earned chain→eff. Now later-usage = ONLY later blocks'
  call centers (?var expanded to bindings declared BEFORE that call).
  Chapter-27 now: sg1 eff (chain+dI.094+alone.77), sg2 eff (dI.056
  borderline — cast=constraint check), sg3 RED (dg_rel=0, alone=.03,
  dI=.046<noise) — the inverse-exploration walk correctly redundant.
  TERMINAL: eff 1226(75%)/red 396(24%)/harm 9(0.6%). HARM RATIONALE
  (user question): failed exploration = REDUNDANT (wasted, ½A_min) unless
  it MISLEADS (golden-path fork = key-decision error, or removal
  significantly RAISES p) — that's why harm is small: most wrong-direction
  walks waste budget without redirecting the trajectory. Alternativity is
  inherently handled: necessity tests removal on the FULL cumulative graph
  (other blocks' routes = alternatives). v2_dump now shows call commands.
- GROUND-TRUTH STRUCTURE LAYER (user anti-whack-a-mole ruling): replay now
  saves per-ack resolved centers (dispatch ground truth, no ?var parsing)
  and entity-tagged links (endpoint ∈ ctx.ents — env's own entity set; the
  isinstance-int tag failed because accumulated_triples stores names).
  Structure graph = entity-entity links only (value-literal routes die
  WITHOUT any regex); chain = later block's resolved centers ∈ earlier ΔG
  entity endpoints (no checkpoint parsing, no self-reference). Both prior
  patches REPLACED by env truth. Specimens all correct: Rome sg1 chain→eff
  (pop-block red); Chapter27 sg1/sg2 eff + sg3(撒网) red; sacred-text
  sg1 nec+chain + sg2 nec. TERMINAL: eff 1239(76%)/red 381(23%)/
  harm 11(0.7%). NOTE: tmp/replay_delta_g.json now has 4-tuple links +
  _c centers; consumers (classifier_v2 structural pass, xtrack/golden
  scripts) need the same ground-truth upgrade when folded in.
- CONSTRAINT-LEG RULE (user Lauren-Conrad specimen): Piper Halliwell is a
  LEGAL anchor (question entity) whose 1-hop route to SF makes the Lauren
  leg off-shortest by design — conjunction verification legs are invisible
  to answer-probability AND path rank. Rule: gold_adj (block ΔG touches
  gold entity on the entity graph) ∧ multi-fact plan ⟹ eff. Verifies all
  four specimen families incl Rome pop-block (user's earlier ruling) and
  keeps Chapter27 sg3(撒网, no gold touch) red. TERMINAL:
  eff 1452(89%)/red 168(10%)/harm 11(0.7%). Seeds fixed to FIRST plan only
  (re-plan entities hijacked shortest paths). recompute script
  /tmp/recompute_v2.py — fold into classifier_v2 next session.
- LION-O SPECIMEN ROOT CAUSE (user catch): Lion-O reached the model via
  sg2's `candidates:` line (walk candidate pool = displayed env output) but
  NEVER entered accumulated_triples → ΔG-based chain can't see the usage
  (next call centered on Lion-O, chain=False, sg2 mislabeled red). CONFIRMED
  empirically: ack@16 ΔG has 0 lion-o links; ack@21 (center Lion-O) uses it.
  FIX DIRECTION (next session): replay must also snapshot per-ack
  ctx.all_candidates DIFF (candidates are env output); chain = later center
  ∈ (ΔG entities ∪ candidate-diff). THREE MORE user items queued:
  (a) CVT-terminal auto-expansion — a CVT as last/intermediate hop's attrs
  ARE part of the subgraph (结果与展示一致 principle);
  (b) v2_dump sampling must be deterministic (sort candidate pool by
  case_id before rng.sample; also fix duplicate user-specimen append);
  (c) BLOCK-INTERNAL per-sg verdicts — a fact-block with multiple sg calls
  (sg2 here: griffin birthplaces + created-characters) needs per-sg
  redundancy/effect split, not one block-level verdict.
- UNIFIED BLOCK STATE (user ruling: 子图实体与候选统一): block entity
  roster = ΔG entity endpoints ∪ candidate-diff (replay now snapshots
  ctx.all_candidates diffs per ack — the candidates line IS the subgraph's
  entities). Chain judges on the unified state, not raw ΔG. Lion-O
  specimen verified: ack@16 cand-diff contains lion-o → sg2(acks 9,16)
  chain=True → eff. TERMINAL: eff 1454(89%)/red 166(10%)/harm 11(0.7%).
  All five audited specimen families now correct (Rome/Lauren/Chapter27/
  sacred-text/Lion-O). Remaining queued: block-internal per-sg verdicts;
  CVT-terminal expansion (= more triples, same unification); fold
  /tmp/recompute_v2.py into classifier_v2 main.
- UNIFIED GRAPH FINAL (user ruling: path necessity on the relations each
  subgraph retrieved; candidate-usage logic retired): block edges =
  walk pattern edges (_w, from bres pe_list — 3-level iteration fix:
  pe_list is per-center list of {pattern_id: PatternEvidence objs}) ∪
  (center→candidate-diff) edges (_c × _cd — candidates are walk output
  whose patterns were top-5-pruned; Lion-O lives ONLY here). Accumulate-
  filtered ΔG retired from structure. Lion-O now: seth→lion-o candidate
  edge = shortest path → sg2 on-path carrier → eff (path semantics, no
  usage tracking). Chapter27 sg2 gained nec (starring pattern edges).
  TERMINAL: eff 1512(92%)/red 107(7%)/harm 12(0.7%). ALL SIX specimen
  families correct. recompute script still /tmp (fold into classifier_v2).
- ENV-ERROR blocks (user ruling + specimen LaLa-#8): error/entity_error
  acks = zero-yield → RED for credit (wasted action — user confirmed) but
  flagged env_error and EXCLUDED from structural-reference construction
  (golden ranking denominators, coverage, teacher library) so they don't
  dilute good trajectories' scores. Flag wired in recompute; golden-rank
  filter folds into classifier_v2 with the rest. LaLa specimen: __seq2
  (entity_error) red+flagged; __seq1 chain=True eff (spouse chain, user
  confirmed dependency).
- KENTUCKY SPECIMEN RESOLVED (user double-ruling): (1) sg1's full ack
  contains NO 'United States, with Territories' — the dI=−0.183 reading is
  no leak; its mechanism = removing the USA distractor evidence raises gold
  prob. The gold WAS displayed in sg2 (model saw W-T, answered USA) —
  answer-selection-layer error (49% family) leaking into block verdict.
  (2) CONJUNCTIVE per-seed necessity implemented: answer must be reachable
  from EVERY anchor; block necessary iff removal breaks ≥1 anchor's
  reachability. Kentucky sg1: Kentucky→W-T dist 3 requires sg1's edges →
  nec=True → eff (dI harm signal overridden by structure — stage isolation
  preserved). TERMINAL: eff 1511/red 111/harm 9.
- OPEN TENSION (user decision needed): conjunctive necessity also flipped
  Chapter27 sg3 (Scarlett 撒网) red→eff — she is a question-entity anchor
  and sg3 is her ONLY connectivity, but the user earlier ruled that walk
  redundant. Refinement direction: conjunctive necessity per PLAN FACT
  (sgN.anchor of open facts), not per raw seed — anchors not declared as
  fact anchors don't confer necessity. Implement next session.
- QWEN TEMPLATE FIX EVALUATED (user direction; froggeric/Qwen-Fixed-Chat-
  Templates v22, downloaded to tmp/qwen_template_fix/): verified on a real
  trajectory — stock template renders 0/4 history reasoning (field-name
  drop confirmed); fixed template renders 4/4 with our `reasoning` key,
  preserves past think by default, multi-format extraction + dedup (4
  identical strings dedup to zero — use distinct markers when testing).
  SIGNIFICANCE: fixes the EXISTING train/serve mismatch (training
  reconstructs full-think history; serving strips it). ADOPTION PATH
  (non-destructive): vLLM --chat-template flag → flat-protocol smoke →
  48-cohort A/B vs 0.6631 → token-cost measure (history thinking per
  turn). NOT yet installed on :8000 (user auditing; classifier scoring
  content-only unaffected).
- PLAN-INDUCTION CONFIRMED (user hypothesis, A/B measured): the plan block
  in scoring prompts contaminates dI by up to ±0.2 (~7x the 0.029 noise
  floor). Without plan: Chapter27 sg3 dI 0.000 (RED, matches human — the
  +0.041 was boundary false-positive); Kentucky blocks collapse to ~0
  (memory-covered; their necessity correctly comes from the STRUCTURAL
  layer, not dI). PROPOSAL (awaiting user ruling): probability layer
  switches to NO-PLAN prompts (question+calls+results) — structure layer
  judges necessity, probability judges pure evidence marginality.
- TOP-5 explained (user question): _TOP_PATTERNS=5 in _sg_finalize — per
  center only top-5 patterns (path-length+relation-hit rank) are rendered
  AND accumulated; cut patterns' edges vanish (display/ΔG/walk-edges all
  miss them) but their candidates stay in ctx.all_candidates → Lion-O
  channel. Noise-guard added in the rendering era (early code had no cap).
  Root of the display ⊉ walk-output invariant violation; belongs to the
  §6.24 refactor batch with the candidates-line-removal proposal (which
  requires the candidate-visibility invariant FIRST).
- PLAN-INDUCTION CONFIRMED (user hypothesis, A/B measured): the plan block
  in scoring prompts contaminates dI by up to ±0.2 (~7x the 0.029 noise
  floor). Without plan: Chapter27 sg3 dI=0.000 → RED (matches human; the
  +0.041 was boundary false-positive); Kentucky blocks collapse to ~0
  (memory-covered — their necessity correctly comes from the STRUCTURAL
  layer, not dI). PROPOSAL awaiting user ruling: probability layer switches
  to NO-PLAN prompts (question + calls + results); structure judges
  necessity, probability judges pure evidence marginality. Rescore-all +
  recompute pending that ruling.
- TOP-5 (user question): _TOP_PATTERNS=5 in _sg_finalize — per center,
  only top-5 patterns (path-length + relation-hit rank) are rendered AND
  accumulated; cut patterns' edges vanish from ALL channels (display, ΔG,
  walk-edges) while their candidates remain in ctx.all_candidates → the
  Lion-O channel. Rendering-era noise guard (early code had no cap);
  root of the display ⊉ walk-output violation; §6.24 refactor batch item
  together with the candidates-line removal (which REQUIRES the
  candidate-visibility invariant first).
- WALK REDESIGN (user CORRECTION 2026-08-31): NOT a traversal redesign —
  the walk stays bit-identical (same beam/order/discovery dynamics); only
  the RECORDING layer is stripped in pass 1 (relation signatures kept,
  intermediate nodes discarded — no raw_paths node lists, no candidate
  collection, no tree_data). Pass 2 = exact instance enumeration for the
  SELECTED relation sequences via CSR edge joins (per-pattern complete;
  the 90-cap retires). Original framing superseded: rank patterns (path length + relation hit);
  Pass 2 = materialize instances ONLY for selected patterns along the
  fixed relation paths. By construction: candidates == instance endpoints
  (truncation-asymmetry root cure, display ⊇ walk-output invariant,
  candidate-diff channel retires), irrelevant entities never enter, path
  counting = complete paths (instances) with a symmetric per-pattern cap.
  ENGINEERING CAVEATS agreed: (1) pass 1 still traverses via entities
  (CSR carrier) — savings = bookkeeping + pass-2-selective materialization;
  (2) explicit bridge construction MUST be kept/strengthened (mixed
  patterns like actor→character→created_by were "beam luck" per
  formatting.py:503) — top regression risk; (3) net cost = 2× on selected
  (~5) patterns vs full materialization. VERIFY: Lion-O specimen (the
  m.0wz3f15 instance must materialize) → Stage-5 GT-recall telemetry →
  48-cohort A/B → six-classifier-specimen regression. Root-cause record:
  logical_paths.py:347-352 asymmetric truncation (candidates from FULL
  raw_paths, triples from TRUNCATED; candidates also capped [:20]).
- TWO-PASS WALK MODE VALIDATED BY PROTOTYPE (/tmp/proto_exact2.py, user
  design): pass-2 EXACT enumeration over fixed relation sequences (CSR
  edge joins with per-hop direction-combo search, cap 4000) on the
  Lion-O call: P1 19/P2 31/P3 31 instances EXACTLY match the walk's
  counts; P4 recovers 8 instances (beam walk found only 1) INCLUDING the
  full Lion-O path 'Seth--m.0wz3f15--Lion-O--TobinWolf' that raw-path
  truncation had dropped. Triple validation: completeness (shape-
  satisfying instances all enumerated), consistency (1-hop counts
  identical to walk), superiority (8x instances on the mixed pattern).
  NEXT: wire pass-1 signature recording + pass-2 exact materialization
  behind SEQ_EXACT_PATTERNS=1 in logical_paths/_sg_finalize → Lion-O
  replay → GT-recall → 48-cohort A/B. The 'no-visible-edge candidates'
  category then disappears by construction.
- SCORING note-strip WIRED (user ruling): build_trace drops each ack's
  instruction `note:` block — scoring context = graph evidence only.
  Measured -25% trace tokens (40 trajs 135.7k→101.7k). PROTOCOL CHANGE:
  dI absolutes shift (pF/p_loo/p_alone consistently) → rescore queued
  TOGETHER with the no-plan ruling (one pass covers both).
- EVIDENCE DISPLAY DESIGN (user observations: overlap/merge/tree/no-edges)
  folded into the §6.24 refactor: (1) merge pattern-paths by RELATION
  SIGNATURE (fwd/rev/multi-hop variants of one relation = one group);
  (2) TRIE rendering of instance paths — fits the two-pass exact-
  enumeration output natively (shared prefixes written once; super-
  relation cross-products collapse to trees); (3) no-edge display:
  relation as group header, entity chains inline; (4) bloat caps by
  DEDUPED entity count (not lines); (h,r,t) shown once regardless of how
  many patterns reach it; terminals ranked by answer-type relevance.
- RENDER A/B HARNESS (/tmp/ab_render2.py) works: swaps ONE sg ack old↔V3.5
  in the real history, generates next action temp=0 via :8000. FINDING:
  model reasoning IS sensitive — under the buggy V3.5 prototype (3 bugs:
  direction arrows not using best combo; entity-name dedup missing →
  same-name multi-index repeats; sig-dedup dropped the mixed pattern
  group) the Lion-O DISCOVERY VANISHED (next action = checkpoint on the
  created list instead of centering Lion-O). This empirically sets the
  HARD acceptance for V3.5: exact-enumerated mixed-pattern groups (the
  P4 tree with 'm.0wz3f15 ─character─▶ Lion-O') MUST render — the
  instance-endpoint visibility is the discovery channel. Compression
  confirmed: 3728→2045 / 2599→1190 / 4722→1186 chars. Next: fix the 3
  renderer bugs → re-A/B (expect Lion-O verification preserved from the
  tree) → then cohort-level A/B.
- RENDER ZERO-LOSS PRINCIPLE (final form, empirically derived through the
  A/B): folding may only fold TREE STRUCTURE, never ENTITY NAMES — every
  named entity inside a folded subtree (INCLUDING intermediate nodes) must
  appear in the fold summary. Three-level loss chain found & fixed in
  /tmp/ab_render3.py: (1) fork nodes count-only → names listed ✓;
  (2) folded-branch terminal endpoints missing → '↳ 折叠枝端点:' lists ✓;
  (3) INTERMEDIATE entities in folded subtrees still hidden (Lion-O is the
    2nd hop of the folded 3-hop path; leaf list only showed Tobin Wolf) —
  LAST FIX QUEUED: _leaves collects ALL subtree nodes, not only leaves.
  Behavioral proof at each level: entity-visibility loss precisely changed
  the model's next action (Lion-O discovery vanished). Compression holds
  (~50-75%). After the last fix, expect Lion-O to appear in the summary
  and the discovery behavior to restore — that is the V3.5 hard
  acceptance test.
- RENDER A/B FINAL: ZERO-LOSS HARD ACCEPTANCE PASSED. All-entities fold
  (folded subtrees list EVERY node incl. intermediates; cycle-guarded) —
  Lion-O case: V3.5 generation = checkpoint-including-Lion-O +
  'retrieve_relations center: Lion-O' — DISCOVERY RESTORED from the tree.
  4-case review pack tmp/render_ab_review.md (full old/new renders +
  3-way next-action). Behaviors: Boston V3.5 → complete correct
  ANSWER_ANALYSIS (2008 NBA Finals) where old-render generation was
  empty; Rome identical (stable). Known cosmetics: fold line + endpoint
  line now duplicate (merge in production); Lion-O case compression only
  7% (all-entity fold cost; Boston/Rome 54%/25%) — intermediate-entity
  listing granularity is a user-taste tradeoff vs zero-loss.
- RENDER v3 fixes complete (user catches): (1) R3 sibling-merge implemented
  — children with identical subtrees merge to ONE subtree line (17 finals
  sharing 'The NBA Finals' child = 1 line, was 6 duplicates); (2) TAIL
  LINES now list ALL names — count-only '+N' folds removed entirely (the
  user's answer-loss catch: 2008/1986/1984 golds were hidden in '+5').
  Zero-loss is now complete on all three levels. Review pack regenerated:
  tmp/render_ab_review.md. Lion-O discovery preserved under V3.5.
- V3.5 LIVE A/B (first, 10-specimen fastcheck, TEMP=0.3 single-sample):
  baseline (SEQ_RENDER_V35 off) meanF1 0.5111 → V3.5 ON 0.5828 (+7.2pp).
  Per-case: +2 gains (WebQTrn-493 0→1.00, WebQTest-1470 0→0.67),
  2 drops (WebQTest-626 1.00→0.25, WebQTrn-25 1.00→0.80), 6 flat.
  CVT attribute brackets now rendered (first-full, reuse-bare id).
  Renderer wired in kgqa/agent/seq_render_v35.py behind SEQ_RENDER_V35=1,
  consumed in _sg_finalize (tree_lines replaced wholesale). NOTE: single
  seed — treat as directional; needs 48-cohort × 3-seed before any
  conclusion. Two drop cases (626/25) need trajectory diff before next
  iteration — candidate causes: CVT bracket content now visible may
  change candidate weighting; entity-only lines may lose the relation-
  semantics context the old dense format carried.
- V3.5 CVT DYNAMIC-ATTR experiment (user principle: coverage × diversity
  ranking, NOT hardcoding): v1 (ALL attrs in brackets) = +7.2pp (0.5828);
  v3 (dynamic score = coverage*diversity, DROP score-0 attrs) = -18.3pp
  (0.3278) — the formula drops structurally-needed attrs that happen to
  have uniform values in a small sibling set. LESSON: the principle is
  "prioritize" not "exclude" — rank attrs (discriminative first) but
  show all. NEXT: change to sort-only (no drop) → re-run fastcheck →
  expect v1-level or better → then 48×3 cohort. Also fixed a UnboundLocal
  scoping bug in the uniform-attrs header (was crashing every sg call
  → 0.0667 meanF1 in one run).
- V3.5 L1 COMPRESSION (user principle correctly implemented): identical
  attrs across all sibling CVTs → one "(all: k=v)" header; diverse attrs
  → per-CVT brackets ranked by distinct-value count. NOTHING dropped.
  fastcheck: 0.5302 (+1.9pp over 0.5111 baseline; v1-all-attrs was
  +7.2pp). CASE 626 FIXED (date_adopted correctly identified as
  discriminative → 1.00); 567_df regressed (0.00, single-seed may be
  variance). v1 and v4 fix DIFFERENT cases — the optimal variant is
  likely the intersection (compress identical + raise bracket cap).
  Four-version summary: baseline 0.5111 / v1 +7.2 / v3 −18.3 / v4 +1.9.
  NEEDS 48×3 seeds before any conclusion. Scoping bug (uniform_attrs
  UnboundLocal) was fixed — it had crashed every sg call (0.0667).
- 567_df REGRESSION ANALYSIS (user audit request): NOT evidence loss —
  Village of the Giants, 'prodigy', 'child' all present in BOTH renders.
  Root cause: ORGANIZATION — old dense format put 'Movie --subjects-->
  Subject' as standalone rows (high salience); V3.5 embeds them deep in
  multi-hop trees (◀─film─ ... ◀─produced_by─ ... ─subjects─▶ Boxing) —
  information present but tree-depth diluted the constraint salience.
  FIX DIRECTION: when last-hop is constraint-type (subjects/genre),
  hoist leaf values to sibling-level annotation (R3-style) rather than
  deep tree embedding. Three V3.5 trajectories dumped for manual review:
  tmp/v35_traj_WebQTrn-567_df.md (regression), ...493_471b.md (gain),
  ...626.md (L1 fix, 70KB).
- V3.5 USER AUDIT (4 catches): (1) 'candidates not shown above' provenance
  line still fires — V3.5 replaces tree_lines but _candidate_provenance
  appends after in _sg_finalize → TWO render layers stacked. (2) Multi-
  entity trees lose the center root + bury constraint leaves at depth 2-3
  (arrow notation ◀─film─ flattens hierarchy). (3) OLD SAPS TREE format
  (├── └── │) was visually superior — center as explicit root, tree
  connectors express depth, constraint leaves visible at branch tips;
  V3.5 should ADOPT SAPS tree connectors (content logic unchanged).
  (4) Unshown candidates: exact enumeration only covers walk-discovered
  patterns; partial-path candidates invisible (same root cause as
  before). FIX DIRECTION: rewrite renderer output to SAPS-style tree
  (├──/└──/│) with center entity as root; remove provenance double-
  render; keep relation-group headers + zero-loss + L1 compression.
- SAPS-TREE V3.5 (full rewrite to ├──└──│ connectors, center as root,
  R3 sibling merge, L1 CVT compression, provenance gated): fastcheck
  0.5362 (+2.5pp). Gains: 493 0→1, 1470 0→0.67, 849 0→1. Drops:
  567_df 1→0 (persistent), 626 1→0.25 (v4 had fixed it, SAPS lost it),
  212/25 minor. STRUCTURAL ISSUES found in SAPS render: (1) INVERSE
  PAIR DUPLICATION — partially_containedby and partially_contains are
  the same relation in opposite directions but render as TWO separate
  groups with identical content (D1 normalization not implemented in
  the tree renderer); doubles output length. (2) Per-state subtrees
  repeat largely-identical CVT sets — needs R3+D1 cross-group merge.
  (3) sg#2 for 626 (location symbols) needs inspection — the date
  discrimination chain may still be buried. Review dumps:
  tmp/saps_traj_WebQTrn_567_df.md (303 lines),
  tmp/saps_traj_WebQTest_626.md (534 lines).
- 567_df ROOT CAUSE CONFIRMED: NOT a rendering regression — PLANNING
  VARIANCE. off run planned 2 facts (films + child-prodigy subject check);
  SAPS run planned only 1 fact (films only, no constraint retrieval).
  TEMP=0.3 single seed → model sometimes decomposes correctly, sometimes
  doesn't. The V3.5 SAPS render of sg#1 is equivalent (same film list);
  the model skipped sg#2 because it never PLANNED it, not because the
  render hid anything. Action: needs multi-seed (48×3) to separate
  planning variance from rendering effect.
- 567_df FULL ROOT CAUSE (user insight: Village of the Giants NOT in
  Howard's produced_by): sg#1 model selected ONLY producing relations
  (produced_by, executive_produced_by) — MISSED acting/starring which is
  how Howard connects to Village of the Giants (he was a child actor,
  character='Genius'). The gold was found in off-version's sg#2 via a
  LUCKY 4-hop walk path: Curious George --languages--> English
  <--language-- Village of the Giants --subjects--> Child prodigy.
  NOT a rendering regression — JOINT rr-selection + walk-coverage gap.
  Fix directions: (a) rr should offer acting/starring alongside
  producing when the question says "did" (ambiguous verb); (b) two-pass
  walk with broader pattern discovery would find Howard's acting path
  directly. V3.5 SAPS render is equivalent — the model didn't plan sg#2
  (planning variance) so the lucky path never triggered.
- V3.6 CANDIDATE-CENTRIC (unified trie) first run: 0.3200 (recursion crash
  on every sg → all errors). Fix (cycle guard + depth limit) → 0.3652
  (−14.6pp). THREE IMPLEMENTATION DEFECTS: (1) relation names lost —
  unified trie merges paths from different patterns, _hop_for can't map
  chain labels to tree depths; (2) everything marked ◂ candidate — marker
  meaningless; (3) entities/triples header duplicated (old _sg_finalize
  still adds its own). FUNDAMENTAL: the unified trie LOSES per-hop
  relation semantics during cross-pattern merge. V3.5 v1 (+7.2pp) remains
  the best — preserves pattern-grouped relation semantics + CVT brackets
  bring attrs to candidates. RENDER VERSION SUMMARY (fastcheck):
  baseline 0.5111 / v1 +7.2 / v4 +1.9 / SAPS +2.5 / v3.6 −14.6.
- V3.6c BREAKTHROUGH (+14.2pp): candidate-centric + pattern-grouped +
  relation-name-preserving = 0.6534 (best ever on fastcheck; baseline
  0.5111, V3.5-v1 0.5828). Three gains (493/1470/849 all 0→1.00),
  567_df still planning-variance (1→0), 212 variance (1→0.50).
  Implementation: per-pattern SAPS trees (NOT unified trie — that lost
  relation names); terminal-only candidate markers (◂); CVT inline
  attrs with L1 uniform compression; header duplication fixed.
  Rendering shows full relation chains per group + named entity trees
  + CVT event blocks. NOTE: still single seed TEMP=0.3 — needs 48×3.

## RENDER V3.6c SESSION HANDOFF (2026-08-31 完整)

### 当前状态
- **V3.6c 候选中心渲染 = 0.6534(+14.2pp)历史最佳**。fastcheck 10标本,
  TEMP=0.3 单种子。3 个 0→1.00(493/1470/849),567_df 仍是规划方差。
- 代码: kgqa/agent/seq_render_v36.py(render_v36_ack),seq_tools.py
  _sg_finalize 门控 SEQ_RENDER_V36=1(entities 置空消重复头)。
- 渲染格式: 按模式分组 SAPS 树,关系名在每个连接符上,候选标 ◂
  (仅真叶子),CVT 内联属性括号,L1 一致压缩,头一次性。

### 六版渲染演化(fastcheck meanF1)
| 版本 | 策略 | F1 | Δ |
|---|---|---|---|
| V3.4 基线 | 模式+稠密 | 0.5111 | — |
| V3.5 v1 | 模式组+全括号 | 0.5828 | +7.2 |
| V3.5 v4 | 模式组+L1 压缩 | 0.5302 | +1.9 |
| V3.5 SAPS | SAPS 树+模式组 | 0.5362 | +2.5 |
| V3.6 v1 | 统一 trie | 0.3652 | −14.6 |
| **V3.6c** | **候选+模式分组** | **0.6534** | **+14.2** |

### V3.6c 设计核心(用户裁决)
- 组织原则: 候选=末跳关系 tail 实体;按模式分组(不走统一 trie——丢关系名)
- CVT 末实体: 事件组作总端(不炸开属性为独立候选)
- CVT 倒数第二跳: 属性内联在候选上
- L1 一致压缩: 全同名 CVT 的同名属性 → "(all: k=v)" 头
- 零丢失: 尾行全名(不折叠计数),折叠枝全实体(含中间节点)
- 关系名在每个树连接符上

### 渲染层已修的关键 bug
1. 答案调用泄漏(scoring prompt 含 tool: answer → 抄写读数)
2. 单金标伪影(多金标题概率分摊 → 改完整列表续接)
3. BPE 合并跨度坍缩(" Belize" 前导空格合并 → offset-mapping 修)
4. prompt_logprobs 批序非确定性(噪声地板 0.029 → dI 阈值 0.05)
5. build_trace 剔除 answer 调用 + note 块(-25% token)
6. V3.6 统一 trie 丢关系名(→ 回模式分组)
7. V3.6 递归超限(→ cycle guard + depth limit)
8. 头重复(→ V36 时 entities 置空)

### 两轮游走(已原型验证,待接线)
- 第一轮: 现有走查只记关系签名(零簿记,中间实体自动废弃)
- 第二轮: 选中关系序列 → CSR 精确连接枚举(完整性+一致性+超越性)
- Lion-O 标本: P4 精确枚举 8 实例(walk 只见 1),Lion-O 路径完整恢复
- 根因: logical_paths.py:347-352 截断不对称(候选全量算/三元组截断后算)

### 判定器 v2(终态)
- 事实块分组 + 裁决十一布尔规则 + 块级概率打分(结构层重放)
- 环境真值: ctx.ents 实体标记(值字面量剔出) + dispatch 真实 center
- 统一图: 块边 = walk 模式边 ∪ (center→候选差分) 边
- 合取必要性: 答案须从每个锚点可达,移除断任一锚点链 ⟹ 必要
- gold_adj 约束腿: ΔG 触及金标 ∧ 多事实 ⟹ 有效
- 终态: eff 1512(92%)/red 107/red 6%/harm 0.7%
- PENDING: /tmp/recompute_v2.py 需并回 classifier_v2 主脚本

### 待办优先级
1. **48-cohort×3 种子验证 V3.6c**(渲染首次多种子)
2. 两轮游走接线(SEQ_EXACT_PATTERNS=1)
3. 打分重跑(无plan+无note 合并一次)
4. 判定差距四方向(噪声边界/事实锚点/约束关系一致性/plan 层)
5. 模板 A/B(froggeric 修复版,已验证 4/4 reasoning 渲染)
6. 训练批次前置(全胜组裁决 → π_old+ρ-clip → 教师库重放)

### 标本家族(六组全对)
Rome / Lauren-Piper / Chapter27 / sacred-text / Lion-O / Kentucky

## RENDER V3.7 会话(2026-08-31 下午:候选中心重构 = 走径忠实组织)

### 触发
用户裁决:V3.6c"还是基于路径的树状结构",要的是**候选为主键**——
`Iowa：关系模式【xxx】`,非 center 根的树。

### 根因链(不是排版问题,是信息源问题)
1. **V3.6 丢弃了走查节点序列**:render_v36_ack 只取每模式 tp[0]的
   RELATIONS,再用 2^k 方向组合×最大实例数重枚举——扇出方向
   ([MR→Iowa→cvt×88],候选埋中层,cvt 记录挂 ◂)压过语义方向
   ([MR←cvt→state×7])。而 walk 的 tree_data["paths"] 本来就带着
   **完整走径节点序列**(`['Missouri River','m.0wg906w: [attrs]','Iowa']`)
   ——语义路径一直都在,v36 自己扔掉的。
2. **V3.6c 多中心 break bug**:zip(centers, pe_list) 后 `break` → 只渲染
   第一个 center。849(Germany 边界+货币) v36c 赢在**证据被隐藏**:
   4 个 ?country 中心只渲染了 Austria,Netherlands 的 USD 边没露出,
   模型 satisfice 到 gold(Austria,CWQ 噪声题)。V37 忠实渲染全部中心
   → 模型合理选了有直接 USD 边的 Netherlands → 0 分。**v36c 的
   0.6534 里有这种 bug-运气成分**。
3. **V36 空-回退崩溃(latent)**:渲染器返回 "(empty)" 时 else 分支
   只设 _ov/_blocks 不设 tree_lines → UnboundLocalError。v36c fastcheck
   live 里有 3 个多中心 ack 是 error JSON(7:9 / 8:14 / 8:18)。
   V37 修了(回退到 v3.3 dense 路径)。

### V3.7 设计(kgqa/agent/seq_render_v37.py,门控 SEQ_RENDER_V37=1)
- **走径忠实**:直接组织 tree_data["paths"] 的节点序列;不做方向
  组合搜索/重枚举。CVT 装饰名 `m.xxx: [k=v, ...]` 解析回 mid+attrs。
- **候选行格式**:`Iowa ◂  Missouri River ←partially_contains─ m.0wg906w ─partially_contained_by→`
  ——候选(组)在行首,链以指向候选的箭头收尾;fan-out 同体候选折叠
  `A | B | C ◂ <共享链>`(结构折叠,实体名全保留)。
- **后缀折叠**:尾部 CVT/值跳剥为记录后缀;len-2 路径 CVT 当候选
  (attrs 内联)。attr 与路径节点重言的丢(administrative_division=Iowa
  这种);组内严格一致 attr → `all records:` 头(L1);每记录 attrs≤6;
  行内 480 字符预算,溢出折 `(+N: 裸值)`。
- **续路径去重**:是更长走径节点后缀的路径丢弃(walk 的 mid-rooted
  continuation);按**基础名**去重(平行关系拼写会以不同 attr 装饰
  同一 mid 走两遍)。
- **组排序**:(跳数升,实体终端优先,实例数降)——最后一跳定义候选
  的组级应用。
- 集成:_sg_finalize V37 分支先于 V36;entities 标题抑制含 V37。

### 离线验证(tmp/rerender_v37.py,重放 v36c fastcheck 走查)
- 保真 24/28 一致(4 差 = 3 个 live 崩溃 + 1 渲染漂移)
- **零丢失:env 候选名在 V37 渲染文本中 0 缺失**(27 ack 全查)
- Missouri ack 22.2k→11.0k;总量 1.6×(多中心忠实渲染的成本,
  v36 是靠丢 6/7 中心换的小)

### 判定结果:48-cohort × 3 种子(2026-08-31 晚,终数)
| 臂 | meanF1 | 说明 |
|---|---|---|
| 基线(v3.3 dense,walkfix_r267g3 子集) | **0.6877** | 144 轨迹 |
| **V37b(修复版)** | **0.6690** | hit(run口径)81.9%,答空率同基线 |
| V37(初版) | 0.6515 | |
| V36c | 0.5904 | fastcheck 0.6534 未能复现(bug 运气) |

- fastcheck 10 上 V37=0.45/0.52 vs v36c 0.6534 是**小样本+bug运气**:
  48×3 判定 V37b 比 V36c +7.9pp。
- V37→V37b 修复(+1.75pp):
  ① 溢出/尾部值**带键**(`character=Jacob Black | film=Abduction`,
    25_892 曾把角色名当实体绑 → entity_error 死循环)
  ② CVT attrs 从**图边重建**(装饰缺失时兜底;链中 CVT 内联 attrs ≤3)
  ③ 修 records/tails 对齐 bug
  修后 2784_b 恢复 [1,1,1](原 [0,0,1]),25_892 恢复(1,1,0.07)
- **残留 −1.9pp vs 基线,家族归类**(非渲染读取失败):
  - 判别属性检索空手:tvrage_id=20997(25_db96)——sg 关系选择没打到
  - 多答案完备性:1171 Darth Vader 配音只绑到 Reiner Schöne(单候站)
  - 与排队中的两轮游走(第二轮精确枚举穿透 CVT)同族
- 所有臂答空率 ~1%(99% 非空)——无格式诱发拒绝

### 陷阱(tmp/ 探针)
- multiprocessing spawn 需 `if __name__=="__main__"` + **文件入口**
  (`python -` heredoc 会 spawn 失败/重跑主模块 → 假 EMPTY)
- 判 NULL 的正确姿势:spawn 坏掉时 render "(empty)" 是伪象,先修 harness

### V3.7 终态交接
- 代码:kgqa/agent/seq_render_v37.py(SEQ_RENDER_V37=1);seq_tools._sg_finalize
  V37 分支 + 空-回退修复(V36 同修)+ entities 标题抑制含 V37
- 运行产物:reports/v37_fastcheck{,2}.json / v37_48x3.json / v37b_48x3.json /
  v36c_48x3.json(基线从 walkfix_r267g3 提取,勿重跑)
- 重放工具:tmp/rerender_v37.py(fastcheck 同走查 A/B diff + 保真检查)
- **待用户裁决**:V37b(候选中心设计正确实现,+7.9pp vs V36c)vs
  dense 基线(−1.9pp)取舍;残留差距族(判别属性检索/多答案完备)
  与两轮游走接线是否合并处理

### V3.7c 用户审核轮修复(2026-09-01)
- **问题1(1171 达斯维达未命中)诊断**:反证重放确认——sg1 只选了 dubbing
  schema(3 关系),rr 候选表里明明有 film.performance.character/actor;
  +performance 反证渲染里 James Earl Jones 立即出现(22 条记录)。
  单候选绑定 + sg2 空手 + satisfice 答案策略 = 0 分。反证C:直接锚
  75th Ranger Regiment 会碎在实体解析('7')。
- **问题2修复(记录行形态)**:CVT/值终端组不再"裸 mid 行首+悬空箭头",
  链完整收入记录:`Darth Vader ←character─ m.04dmkc9 [actor=…; film=…;
  language=…]`;≤2 attr-host 的组跳过 uniform 折叠(单记录组的 attrs
  不再被偷进 all records 头)。
- **问题3实现(多锚点提醒)**:_do_seq_decompose——声明实体 ≥2 且某实体
  从未字面出现在任何 fact 头/sgN.anchor → plan ack note 追加 MULTI-ANCHOR
  提醒(指向 [PLAN EXTEND] 锚定它)。
- **V37c 48×3 = 0.6730**(hit 79.2%):V36c 0.5904 → V37 0.6515 →
  V37b 0.6690 → V37c 0.6730;vs dense 基线 −1.5pp,案例级 14+/13−。
  1171 [0,0,0]→[1,1,1],25_db96 [0,1,1]→[1,1,1](超基线)。
- 审核 dump:tmp/v37c_traj_dump.txt(48 案例 seed0 全轨迹,119 渲染);
  重出:tmp/dump_v37b_traj.py(指向 v37c_48x3.json)。
- fastcheck 冒烟 0.630(该 10 标本噪声大,不作为判定)。

### V3.7d 审核轮二(2026-09-01 晚:Liszt member 消失 + Mandela 终端裁决)
- **Liszt 诊断(1379,用户问"给了 member 为何没有 member 路径")**:重放
  图真值——member 其实走出来了(walk P2/P4/P7/P10 四条模式都以 member
  收尾,图里存在 m.0cr70y2 --member--> Life of Franz Liszt 边)。12 个
  walk 模式只有 2 条节点序列([Liszt,书,m.0cr70y2]×6 / [Liszt,书,
  Catholicism]×6)——同一节点对之间有平行边(based_on/image/gallery/
  fiction × member/member_of/religion)。**渲染器按节点序列去重只保留
  第一个关系拼写,member 输给 member_of 被吃掉**。
- **修复①(平行拼写并集)**:去重时收集同节点序列的全部 rel 元组,
  每跳标签 = 拼写并集 `─member_of/member→`(≤2 个 + "+"号),方向随
  第一变体。
- **修复②(桥 hop 标注)**:walk 的 2-hop 设计故意允许未选首跳作桥
  (Bernie Brewer 语义,logical_paths._hit_paths 注释)——未选 hop 渲染
  为 `─(based_on/image+)→` 括号形式,"给了关系但游走出别的"从此可见。
- **修复③(Mandela 终端裁决)**:删除尾部 CVT 剥除。**终端类型决定行
  形态**:命名实体终端 = 行首候选(◂);CVT/值终端 = 链完整收入的记录
  (attrs 内联,推理时选属性);中间实体留在链中(不再被提到行首导致
  `─containedby→ ←jurisdiction_of_office─` 两箭头相邻、中间节点消失)。
  记录后缀/recs/tr 机械全部移除,渲染器更简。
- 用户确认:**多实体(多中心)机制没问题且优于单路线**(一半中心命中
  答案,另一半子图缺信息;关系命中→准确命中)。
- 离线:零丢失 0 缺失;总量 2.09×v36(CVT 终端内联所致,行预算封顶)。
- V37d 48×3 + dump:见下行补记。
- **V37d 48×3 = 0.6990(hit 80.6%)— 渲染臂首次超过 dense 基线 0.6877**
  (+1.1pp,案例级 13+/11−)。演化:V36c 0.5904 → V37 0.6515 → V37b
  0.6690 → V37c 0.6730 → V37d 0.6990。fastcheck 冒烟 0.761(9/10)。
  1379(Liszt) [0,1,0]→[1,0,1];1470(Mandela) [1,1,1]→[1,.67,0] 需盯
  (终端形态对 gov-position 阅读的影响,seed 级方差待观察);
  1171 与基线平;25_db96 方差翻转。
- 审核 dump:tmp/v37d_traj_dump.txt(48 案例 seed0,117 渲染,10358 行)。

### 去重裁决 + vLLM 重启(2026-09-01 夜)
- **渲染去重核心点(用户裁决)**:walk 每关系维护自己的路径(member 与
  member_of 是两条不同走径)。渲染行合并仅当**走径节点序列完全重合**
  (候选+中间节点都重合,Liszt 六种拼写同序列);**某模式的候选与其他
  模式无重叠时必须单独成行**。已写入 seq_render_v37.py 去重块注释;
  现实现即此语义(节点序列为键,无重叠键不同→不同行)。
- **vLLM 就地重启(另一会话定的 prefill 参数)**:
  `VENV= VLLM_BIN=/root/miniconda3/envs/qwen35/bin/vllm \
   VLLM_GPU_MEMORY_UTILIZATION=0.82 bash scripts/start_local_qwen35_server.sh \
   --max-num-batched-tokens 16384`
  (0.82 保留给 GTE;脚本默认 2048 是内存记录的 prefill 瓶颈)。
  真完成健康检查 200 ✓;冷 4.8k tok prompt 实测 ~10.4k tok/s;
  GTE :8003 未动仍健康。批次运行时看 prefix cache + 并发 prefill 收益。

### 去重裁决修正 + vLLM 8192(2026-09-01 深夜)
- **修正(用户二次裁决,推翻我的拼写并集)**:member 与 member_of 对应
  **不同候选**(边方向不同→候选角色不同),member 的路径不得并入
  member_of 的展示。新键 = **节点序列 + 每跳方向**;仅同向平行拼写
  并集;方向不同必分行各自箭头。桥 hop(未选)方向折叠为中性
  `─(based_on/image+)─`(方向只在选中 hop 上是候选定义性的)。
  Liszt 标本终态:
  `Franz Liszt ─(based_on/image+)─ Life of Franz Liszt ←member─ m.0cr70y2 [organization=Freemasonry]`
  `Franz Liszt ─(based_on/image+)─ Life of Franz Liszt ─member_of→ m.0cr70y2 [organization=Freemasonry]`
- 重放:零丢失 0;总量 2.55×v36(方向分拆的代价,行预算封顶)。
- **vLLM 陷阱**:`--max-num-batched-tokens 16384` 在 9k-token prompt
  (8448 chunk)触发 EngineCore shm_broadcast TimeoutError 崩溃——
  Mamba 混合架构 + 大 chunked prefill 不稳。**降到 8192 稳定**(真完成
  检查 "OK"/finish=stop)。重启竞态:旧进程 shutdown 未完时立即重启
  会失败,等端口/GPU 释放后再起。
- **V37e 48×3 = 0.6348(hit 78.5%)— 方向分拆裁决后回落 −6.4pp**
  (V37d 0.6990 → V37e 0.6348;base 0.6877)。fastcheck 0.468。
  损失集中:452_f79 −0.83 / 1379 −0.67(裁决出发点案例本身
  [1,0,1]→[0,0,0],但失败模式是模型走 organization 路线答
  Freemasonry,gold= Priest,题面噪声)/ 1171 −0.67 / 372 −0.53;
  收益:2540 +0.7 / 25_892 +0.38 / 626_01 +0.33。
  成本来源:同节点序列反向双行(全链重复)+ ack 总量 2.55×v36。
  **待用户裁决**:①维持方向分拆(设计正确,认 −6.4pp);②裁决兼容
  压缩(反向行只渲染差异跳,引用共享前缀);③回 V37d 并集。
  dump:tmp/v37e_traj_dump.txt。

### V3.7f 实体优先(2026-09-01 深夜二:用户终裁"先按实体分")
- **裁决**:渲染主键 = 候选实体——`Reiner Schöne ◂ (N paths)` 块头,
  其模式路径/关系列在实体下;不再按模式分组列实体。记录路径挂
  owner(链上最后命名实体);路径集完全相同的候选折叠共块。
- **multi_anchor 独立字段**:埋在 note 里模型忽略(V37e 1171 标本,
  提醒在场但 plan 未变)→ 拆成 ack 顶层字段。效果:19 个 plan 收到,
  34 次 [PLAN EXTEND] 发射——机制被使用。
- **V37f 48×3 = 0.6939(hit 81.2%)**:方向分拆代价被实体优先组织收回
  (V37e 0.6348 → V37f 0.6939;V37d 并集版 0.6990;base 0.6877)。
  1379(Liszt,member 裁决出发案例)= [1,1,1] 完美。1171 仍 [0,0,0]
  ——失败在 sg1 关系选择(只挑 dubbing schema)+ 75th Ranger 实体
  解析碎('7'),渲染外,归两轮游走/实体解析队列。
- 渲染演化终表(48×3):V36c 0.5904 → V37 0.6515 → V37b 0.6690 →
  V37c 0.6730 → V37d 0.6990(并集)→ V37e 0.6348(分拆+模式组)→
  **V37f 0.6939(分拆+实体优先 = 全裁决实现)**。
- dump:tmp/v37f_traj_dump.txt(109 渲染,11126 行)。

### V3.7g 消费门(2026-09-01 终:用户裁决"拦截一轮再放行")
- **机制**:答案提交时(实质答案,非 None),若 plan 声明 ≥2 实体且有
  实体从未作为任何检索起点(ctx.consumed_anchors,_sg_prepare 记录全部
  解析 centers 含 ?var 展开)→ **单次拦截**:user 消息点出未消费实体,
  给出"现在从它检索(center:'X' 或 [PLAN EXTEND])再重答;若只是约束,
  原样重交——此检查只发一次";第二次直接放行(_ma_gate_fired 单发,
  同 var-mismatch 契约)。
- **V37g 48×3 = 0.6919(hit 81.9%)**:与 V37f 0.6939 噪声带内持平,
  超基线。门触发 17 次,其中 2 次触发后真去检索(多数为约束型 plan
  原样重交,成本一轮);**1171 [0,0,0]→[1,1,0] 目标家族恢复**;
  493/1379 seed 级摇摆。
- dump:tmp/v37g_traj_dump.txt。渲染+交互层终稿待用户确认;
  确认后 → 行为判定(classifier v2 以 V37g 轨迹为语料)。

### V3.7h 同关系回环抑制(2026-09-02 用户裁决)
- **规则**:不同关系形成的回环是合法证据;**同一关系一去一回
  (`A ─members→ m.x ←members─ …`)是退化路径,必须抑制**;同方向重复
  (嵌套 contains→ contains→)保留。实现:收集走径时若同一关系名在
  两条跳上方向相反 → 丢弃该路径。
- 标本(v37g rec54 ack9,Freemasonry):`─members→ m.0cr70y2 ←members─`
  消失;`─(organization)─ m.0cr70y2 ←members─`(异关系)保留 ✓
- 已知微妙点(用户指出,不改):多候选块的链尾箭头不点名具体候选,
  语义归属由块头承担(合并块 = 路径集全同,结构性无损失)。
- 重放零丢失 0;总量 1.99×v36(抑制后回落)。
- **vLLM 崩溃二次证据(2026-09-02)**:8192 也 EngineDeadError(04:40:44,
  V37h 批跑中途 + 另一会话共享负载)→ V37h 0.343 作废(34/144 f1=0 从头
  散布)。结论:**Mamba 混合 + chunked-prefill 抬参(8192/16384)都不稳,
  唯一长期稳定配置 = 不带 --max-num-batched-tokens(默认)**。
  V37h 用无-flag 服务器重跑。另会话已自行重启 8192 实例;prefill 参数
  优化需先解决 Mamba chunk 稳定性(vLLM issue 待查)。
- **V37h 重跑(稳定服务器,取干净 144 条,reports/v37h_48x3_fresh.json)
  = 0.7078(hit 79.9%)— 渲染+交互全栈终稿,全演化最佳**:
  V36c 0.5904 → V37 0.6515 → V37b 0.6690 → V37c 0.6730 → V37d 0.6990 →
  V37f 0.6939 → V37g 0.6919 → **V37h 0.7078(+2.0pp vs dense 基线,
  案例级 12+/14−)**。全裁决栈:实体优先块 / 方向分拆(每关系自己的
  候选)/ 桥中性标注 / CVT 终端记录形态 / 键值溢出 / multi_anchor
  独立字段 / 消费门单次拦截 / 同关系回环抑制。
  陷阱:seq_rollout RESUME 会把崩溃残留拼进同 OUT——重跑先删旧文件
  或取末段(本次 288 条取后 144)。
- dump:tmp/v37h_traj_dump.txt(119 渲染,10667 行)— 渲染+交互层
  终稿审核材料。

### 渲染设计交接文档(2026-09-02,给 Codex 外部审计)
- **specs/render_design_handoff_v37h.md**(59KB,自包含):渲染器全文 +
  SAPS 走查层(_hit_paths/主循环/materialize/tree_data 构建)+ 集成点
  摘录 + 12 条裁决账本 + 度量演化 + 同 walk 两风格标本
  (小/中/超大候选;超大 = 7:9 Taylor 24 中心,V37h 34.6k vs dense 19.2k
  — 用户发现的"候选中心在超大候选上反不如路径"核心矛盾)。
- 用途:用户携文档与 Codex 做渲染设计审计;**只优化渲染,不改现有逻辑**。
- 标本生成工具:tmp/render_specimens.py(V37 vs dense 同走查对照)。

### V3.8 三元组渲染(2026-09-02 用户+Codex 设计①实现与首测)
- **设计**:回归三元组行,压缩仅两形状(同 h+r→多 t / 多 h→同 r+t);
  CVT 展开不变;模式路径总览与强制候选行取消(行内实体即候选)。
  实现:kgqa/agent/seq_render_v38.py(SEQ_RENDER_V38=1),走径忠实边
  (V37h 去重/回环抑制纪律),真实存储方向;排序按关系名。
- **token 大胜**:重放 27 ack 总量 129,280 = **0.75× v36**(V37h 2×);
  超大候选 7:9:V37h 34,563 → V38 9,220。零丢失 0 缺失。
- **48×3 = 0.6706(hit 80.6%)— 低于 V37h 0.7078(−3.7pp),低于基线
  −1.7pp**。V38 vs V37h 掉:241_97b −0.6 / 576_130 −0.52 / 1840 −0.5 /
  25_7cec(award 判别)−0.48 / 537 / 626_01;涨:2570 +0.44 / 2540 /
  1812 / 513。掉分家族 = 判别属性比较(块内 attrs 的候选侧组织被
  压平后,R2-UNRESOLVED 全候选提交增多,576 标本)。
- **结论待用户裁决**:设计①单独上分数不及 V37h;两设计的汇合点 =
  设计②(超量二段展开/阈值切换):常规量走 V37h 实体优先(0.7078),
  证据超阈值时切 V38 三元组压缩(或先模式选择再三元组)。
- 陷阱:pass_render 的 env pop 列表必须含新 flag(漏 pop → 后一 pass
  被污染成同一渲染,dense 列曾整体作废)。

### V3.8b 关系分节变体(2026-09-02 用户设计:选中关系集中+候选花名册)
- 实现:render_v38_ack 尾部改为分节——选中关系各一节(头 `▸ --rel-->
  (retrieved · candidates: <扇出侧花名册≤40>)`),其余走查关系归
  "other walked relations" 节。纯展示重组,零丢失 0,总量 0.82×v36。
- **48×3 = 0.6398** — 三方:V37h 0.7078 / V38flat 0.6706 / V38b 0.6398。
- 案例级:分节+花名册**修复了它的目标家族**(576_130 区号比较
  0.48→1.00,25_7cec award 判别 0.19→0.71,626_01 0.67→1.00)但在别处
  新掉(241/1840/537 未恢复 + 新损失),净 −3pp。
- 结论:候选侧组织(V37h 块)仍是聚合最优;关系花名册是有效部件,
  应并入"超量回退"路径而非全局替换。
- 掉分案例 dump:tmp/v38_drop_dump.txt(V38flat vs V37h 的 15 案例,
  seed0 全轨迹)。

### V38c CVT 属性展开 bug 修复(2026-09-02 用户审核发现)
- **根因**:V38 多尾压缩行 join 了**字典键(裸 mid)**而非 cvt_disp 的
  显示值——≥2 尾的行全部裸 mid,测量值(date/number)不可达
  (241 co2 标本:每国 100+ 裸 g.xxx;212 population 同)。
  单尾行走 heads_of 路径有 attrs,所以只有大扇出行发病。
- 修复:join 显示值 + 行级预算(>900 字符 → 前 500 字符带 attrs,
  尾部折键值 `(+N: date=… | number=…)`,mid 属结构可折)。
  标本验证:g.1245_2gxm [date=1976-08:00; number=9.3065] ✓
- **V38c 48×3 = 0.6720(hit 80.6%)**;四方终表:
  **V37h 0.7078 > V38c 0.6720 ≈ V38flat 0.6706 > V38b 0.6398**。
  三元组家族稳定在 0.67 档(−3.5pp vs V37h),token 0.82-1.14×。
  241(co2) 0.56 仍 < V37h 0.73;576/452/493 恢复至与 V37h 平。
- **渲染终稿待用户裁决**:①V37h 基座(聚合最优)②三元组家族
  (token 优,判别组织弱)③混合(超阈值回退三元组+花名册=设计②)。

### 渲染对照实验(2026-09-02 用户设计:只换渲染重推)
- **方法**:13 个 V38c 降案例,取 V37h 赢的 seed 轨迹,**plan+工具调用
  完全不动**,仅 sg ack 换 V38 渲染重生成,重建对话,temp=0 重推最终答案。
  工具:tmp/counterfactual_render.py → tmp/counterfactual_v38.json。
- **结果:8/13 保持正确答案**(渲染无关,该 13 案例的大头是 plan/轨迹
  采样方差);**5/13 渲染可归因**:
  · 241(co2):三元组行下比较失败 → 答全部国家(f1 0.20)
  · 25_7cec:部分掉(0.33);2784_3a12:日期严格全判 FAIL → 空答案
  · 1379/1557:换渲染后模型在同一节点拒绝作答、要求再检索
    (1379 已绑出 ?position=[Priest]=金标,证据在,组织形态让模型不放心)
- **plan 审计**:两运行机械 plan 错误均 0;内容差异 = TEMP=0.3 采样
  方差(1379 标本:plan 问"positions held"→Priest✓ vs "which
  organization"→Freemasonry✗);plan 阶段输入与渲染无关。
- **LaLa Anthony(452)**:图切片无此人(q_entity=Carmelo Anthony),
  解析器行为正确(给 Anthony 家属消歧);失败在借道恢复导航。
- 净结论:V38c−V37h 的 −3.5pp ≈ −2pp 渲染可归因(比较家族组织)
  + 其余方差;V37h 的候选侧组织对"证据已到、敢不敢答"有真实贡献。

### 思考过程 dump + plan 误读机制(2026-09-02 用户审核)
- **发现:trajectory 一直存着 reasoning 字段**,此前所有 dump 脚本只打
  content——已补:tmp/dump_reasoning.py → tmp/reasoning_dump.txt
  (5437 行,140 个思考回合,7 个 plan 嫌疑案例家族 × 失败 seed × 两运行)。
- **1379 seed0 plan 误读机制(校验结论)**:思考里模型**正确读出了
  career**("the answer might be a position title or description of his
  career")并自我纠正——但 finalize 时原样发回了**第一稿计划**
  (answer_type: organization / ?religious_org_leadership),纠正没有
  传导到最终输出;且思考引用了题面预计算的锚关系提示
  (org_membership/org_founder 系)——组织语义被 priming 放大。
- plan 内容错误 = 第一稿锚定 + 纠正不传导 + 题面关系提示 priming 的
  复合,不是能力性误读;候选缓解(排队,待裁决):plan 门对
  answer_type 与疑问词一致性校验("What was his career"→career/
  profession);plan note 加"finalize 前重读疑问词"。

### 中文对照 plan 实验(2026-09-02 用户多义词假设,已证实)
- **普查**:48 与 267 队列里 career 型疑问词案例只有 1379 一例(孤立
  家族);其 answer_type 与对错相关:organization 恒 0,position 时
  base 1/3、V37h 2/2 正确。
- **实验**(tmp/plan_zh_experiment.py):1379 问题,prelink priming 完全
  一致,仅 user 消息追加中文对照,各 8 采样 plan 回合:
  · 纯英文:answer_type = organization×5 / person×2 / position×1
    → profession 系 **1/8**,org 系 5/8
  · 英文+中文对照(职业 无歧义):position×4 / occupation×1 / person×3
    → profession 系 **5/8**,org 系 **0/8**
- **结论**:英文 career/leading 多义 → plan 第一稿偏向 organization;
  中文对照把 org 系清零、profession 系 ×5。与上一条"第一稿锚定+纠正
  不传导"机制吻合(中文消歧直接改第一稿)。
- **候选缓解(待用户裁决)**:①plan 前注入中文对照问题(需翻译源);
  ②或 plan 门 answer_type×疑问词一致性校验;③或疑问词词典
  (career→profession/position 白名单)。注意 1379 是评测集孤立家族,
  收益面窄,但机制对其他多义疑问词(what is X's role 等)通用。

### 本地模型自译消歧实验(2026-09-02 用户提问,三轮同 prelink 同 seed)
问题:1379,单 prelink 实例,seeds 100-107,仅变中文对照来源:
| 臂 | 对照文本 | plan 结果 |
|---|---|---|
| A 纯英文 | — | org 系 6/8,profession 系 1/8 |
| B 手写消歧中文 | 职业生涯(职业)是什么 | org 系 **0-1/8**,profession 3/8(person 误读×4) |
| C 模型自译(普通指令) | 职业生涯**是怎样的**(保留歧义!) | org 系 6/8 = 与英文全同 |
| D 模型自译+消歧指令 | **是什么职业** | profession 系 **5/8**,org 系 3/8 |
- **结论**:①本地模型朴素自译不消歧——"怎样的"复现英文多义,等于没翻;
  ②**给翻译指令加消歧要求(多义词按真正询问选最具体译法)后,模型能翻对
  ("是什么职业"),plan 随之翻转**(org 6/8→3/8,profession 1/8→5/8)。
  真正起作用的不是中文,是**强制的显式消歧pass**;中文是载体。
- **可部署形态(待裁决)**:零额外调用——plan 指令里加一步"先用一句中文
  重述问题真正询问的东西(多义词选最具体读法),再发 plan";或独立翻译
  预回合(每 case +1 调用)。B 臂的 person 误读提示重述措辞也要规范。

### 关系选择重定义评估 + 中文重述部署首测(2026-09-02/03)
- **金标关系真值**:tmp/gold_relations.json(46/48 案例,问题实体→答案
  实体 1-2 跳图路径关系)。普查:候选池含金标 135/138(98%)——
  **瓶颈在选择不在池**;V37h 选中金标 84%,V38c 79%。
- **hard-miss 家族**:漏选轨迹 22/29 条,但多数经等价编码仍答对;
  **漏选∧失败 = 7 个独立案例**(2152/1797/1171/25_892/567_11fd/
  1379/452_f79)。
- **三分实验**(tmp/threeway_experiment.py,同 rr 列表 4 采样):
  金标落进 Required∪Supporting = **27/28**(旧提示词 7/28),
  6/7 案例修复(2152 除外);代价:平均保留关系数 ×3-10(0.5→12.8)
  ——印证"不能无限扩大",需组级上限(用户设计②:语义组选择+展开)。
- **①中文重述部署首测(V37i)**:格式示例加行,plan 遵循率仅 76/147
  (52%),48×3 = 0.6824(−2.5pp vs V37h);1379 反降(0.67→0.33),
  1171 升。**结论:可选格式行的嵌入版失效**——孤立实验里强制重述
  有效,自由格式下半数不发。待裁决:改成 plan 门强制(缺重述行拒绝,
  同 answer_type 门)或先回退,与三分提示词一起打包 A/B。

### 关系选择机制对比实验终表(2026-09-03 用户裁决的实验组)
同一 7 个 miss∧fail 案例 × 4 采样(28 样本),金标关系落进检索集率:
| 机制 | 金标召回 | 平均集合大小 |
|---|---|---|
| 现状 hard select | 7/28 (25%) | ~2-3 |
| 排序 top-3 | 14/28 (50%) | 3 |
| 排序 top-5 | 16/28 (57%) | 5 |
| 三分+前缀组封顶 | 17/28 (61%) | 9.9 |
| **三分 R∪S(不封顶)** | **23-27/28 (82-96%)** | 11.4 |
| 候选全池 | 28/28 | 20.4 |
- 排序不如三分:线性序表达不了"这几个等价"的集合语义。
- 我的前缀启发式组封顶损失 25% 召回(名称前缀 ≠ 语义等价,
  performance/dubbing_performance 这类跨 schema 等价抓不全)。
- 三分 R∪S 实际只取池的 56%(11.4/20.4),"无限扩大"担忧比预想温和,
  池本身即是上界。**推荐部署:三分 R∪S,可选硬帽 |R∪S|≤10**。
- ①中文对齐标注已离线完成:tmp/zh_questions_48.json(48/48,问题+
  金标→对齐中文疑问句,无思考秒级;3 个退化样本用强制疑问句提示修复)
  — 运行时注入待裁决(独立预处理任务方案,用户已选)。

### 关系选择评估修正(2026-09-03 用户纠偏:真实行为对照)
- **修正**:此前"旧选择 7/28"是孤立重提示的假基线,且误用整题替代
  子问题。重提:从 V37h 轨迹抽取真实 rr→sg 调用对(323 对,修正配对
  状态机顺序:子问题在调用里、候选在 ack 里)。
- **真实行为**:每次调用实选 median 3 / mean 2.5(p90=3,max 15);
  F1 0.7 靠多调用累积(≈2.25 次/案例)+ 等价编码兜底;调用级金标
  捕获 58%(169/292),轨迹级 84%(先前数字,口径不同)。
- **三分 × 真实调用**(60 个真实漏选调用,真子问题+真候选表,
  seed=700 单采样):**回收 37/60(62%)漏选金标;集合 2.1→8.2(×4)**
  。三分的边际价值集中在"累积也失败"的家族(7 个 miss∧fail,
  先前 6/7 可救)。
- 部署建议维持:三分 R∪S + 硬帽 ≤10;×4 集合的走查/渲染成本由
  行预算与池上界兜住。工具:tmp/live_rr_calls.json,
  tmp/threeway_live_calls.py。

### 三分 note 部署首测 = 新最佳(2026-09-03)
- **V37j(V37h 渲染 + 三分关系 note)48×3 = 0.7496(hit 85.4%)**:
  +4.2pp vs V37h 0.7078(hit 79.9%),note-only 改动(零逻辑)。
- **证据没有变多——反而略降**:rels/call 2.4→2.3(median 3→2),
  ack 字符/轨迹 13,912→13,417(−3.6%),turns 17.3→17.1,
  wall 739s→631s(−15%)。**模型没有执行 R∪S 扩张**(仍传 2-3 个),
  提升来自选择质量:等价编码意识("不同名≠不同事实"+director 例)
  改变了挑中的那 2-3 个。
- 案例级 15胜/9负:目标家族大赢——1171 +0.56(performance schema
  终于被选)、25_db96 +0.63、2209 +0.59、2540 +0.39;输家小家族
  452_f79 −0.53、372/1379/25_892 各 −0.33。
- 结论:三分作为"选择质量 nudge"在同等证据预算下 +4.2pp;
  "扩张"分支(R∪S×4)未被模型采用,证据成本反而下降——
  用户"注意实际选择没这么少"的纠偏与结果一致。
- note 位置:_rr_finalize(seq_tools.py ~2936),gate:无(纯提示)。

### V37k 中文题目注入(2026-09-03)
- 实现:_init_messages env 门控 SEQ_ZH_QUESTION=<json路径>,注入
  `(中文对照: {对齐中文疑问句})`;标注 tmp/zh_questions_48.json。
- **V37k 48×3 = 0.7707(hit 88.2%)**:V37j 0.7496 → +2.1pp,
  13胜/8负;收益 452_f79 +0.53、25_892 +0.36、1379/2576/567 各 +0.33;
  输家 2209 −0.59、25_db96/372 −0.33。
- **⚠️ 泄漏警告:标注用了金标答案(question+gold→中文),消歧信息
  来源于答案——这个 +2.1pp 是上界,不能当诚实 eval 数**。
  演化链(V36c 0.5904 → V37h 0.7078 → V37j 0.7496 → V37k 0.7707)
  中 V37k 仅可用于训练语料;诚实 eval 需无答案版标注
  (question-only + 消歧指令 = 自译实验 D 臂,已证能翻对)。
- 待裁决:①重出无答案标注再测(诚实 eval 数字);②V37k 语料直接
  进行为判定(训练用途金标可见合法)。

### V38 全栈重测(2026-09-03 用户裁决:核心渲染=V38 三元组)
- **V38c 0.6720 → V38j(+三分note) 0.7112(hit 81.9%) → V38k(+中文)
  0.7280(hit 84.7%)**;对照 V37 系:V37h 0.7078 → V37j 0.7496 →
  V37k 0.7707。
- **归因干净**:三分 note 对两种渲染增益一致(+3.9~+4.2pp)——交互层
  收益与渲染无关;中文注入两系一致(+1.7~+2.1pp,含泄漏警告);
  **渲染差距稳定 ~4pp(V37 系占优),新交互栈不能闭合**。
- 大候选家族(用户选 V38 的原因):567_11fd V38k 0.00 vs V37k 0.67
  (反而 V38 输!);567_df97 V38k 0.67 vs V37k 0.00(V38 赢)——
  该家族在两渲染间撕裂,非单边优势;token 成本 V38 仍显著低
  (0.82-1.14× vs V37h 2×)。
- dump:tmp/v38k_traj_dump.txt(48 案例 seed0)。
- **待裁决**:核心渲染终稿——①V38k(0.728,token 优,设计裁决)
  ②V37k(0.771,分数优,泄漏上界)③按候选数混合(超阈值切 V38)。

### 审核二问解答 + 溢出配对修复(2026-09-03)
- **①`(+16: actor=…|film=…)` 汤**:V38 行级预算的溢出折叠把尾部记录
  属性对拍平成单一流,记录边界丢失(actor↔film 无法配对)——渲染缺陷。
  已修:折叠记录内 `;` 配对、记录间 `|` 分隔,≤14 记录+省略号。
- **②567_11fd 检索审计**:检索没有问题——sg2(release_date_s)子图里
  金标 The Journey 连同最早日期 1959-08 都在;**Cocoon 的日期边在
  案例图切片里就不存在**(数据集数组验证:m.0j568bc 只有 film=Cocoon)。
  失败=模型在"Journey 有日期 1959 vs Cocoon 无日期"下选了无日期的
  熟悉片——判别缺失下的比较策略问题(UNRESOLVED 家族),非检索非渲染。
  V37k 赢此案是候选块组织让带日期记录更显眼。

### 截断三态实验(2026-09-03 用户"不可随意截断"裁决的测量)
- **V38k 拍平折叠 0.7280 / V38l 无折叠 0.6921 / V38m 记录分组折叠
  0.7257(hit 84.0%)**。ack 均长:V38l 4123 / V38m 3868 字符。
- 结论:①完全去掉行折叠掉 3.6pp——长行(百条记录)稀释注意力,
  结构压缩是功能性需要的;②**记录分组折叠(记录内 `;` 配对、记录间
  `|`,全实体名保留、无上限)= V38k 同分且修复配对丢失**——
  兼得零实体丢失裁决与注意力预算。**V38 族终态 = V38m 形态**。
- 567_11fd 定性补充:数据切片零边(RH↔The Journey 无任何直接边,
  gold 仅经 release-CVT 桥漏入 sg2),属修复/两轮游走队列,
  非检索选择、非渲染。
- 当前全栈演化终表:V38m 0.7257 / V37k 0.7707(泄漏上界)/
  V37j 0.7496(诚实可报的 V37 系)/ dense 基线 0.6877。

### V38n 选中关系成行(2026-09-03 用户审核"关系与游走不对齐")
- **缺陷**:选中关系若其边是 CVT→实体方向(如 dubbing_performance.
  character: m.xxx --character--> Vader),三元组版把它折进 CVT 属性
  → 选中关系在"retrieved"节不可见,反而桥/续路径的边成行——
  "选 A 走出 B"的错位观感(1171 标本)。
- **修复**:选中关系的 CVT→实体边改为成行 `m.xxx [attrs] --rel-->
  entity`(并从属性表排除避免重复);非选中 CVT 边仍折属性。
  标本验证:三个选中关系(actor/character/dubbing_performances)
  全部成行可见。
- **V38n 48×3 = 0.7320(hit 86.1%,V38 族新高)**:V38k 0.7280 →
  V38m 0.7257 → V38n 0.7320;零丢失 0;ack 1.32×v36。
- dump:tmp/v38n_3seeds_dump.txt(48×3 seeds 全轨迹)。

### 恒对 vs 不恒对案例本质判定(2026-09-03 用户问题)
- 48 案例:恒对 19 / 不恒对 29(V38n 3 seeds)。
- token 重叠启发式:两组"近义非金标命中"率 26% vs 22% — 无显著差
  (启发式太粗,且 gold_relations.json 的 2 跳金标本身含噪声)。
- **人工分桶(结合本会话逐案审计)——29 个不恒对案例**:
  · **判别不可表达/近义错配家族 ~11**(你说的"语义相近但对不上"):
    241_a609(GDP deflator 池中只有 cpi_inflation 等近义)、241_97bf
    (per capita emissions)、452_f79(located ID)、452_343e(co2 精确
    值)、537_80c3(netflix_id)、25_892(runtime 比较)、212(population
    数值边界)、1840(initials sma)、3744(undergrad 数值)、60(ISO
    numeric)、1923(部分)——**判别属性在池中无同名关系,只有语义
    近邻**;数值边界读法方差放大。
  · **数据切片缺陷 ~4**:567_11fd(RH↔Journey 零边)、567_df97、
    372(gold=Jesus Christ 经 respected-by 链)、1797(Vicksburg)。
  · **plan/导航方差 ~9**:1171(schema 选择)、2784、2540、2570、
    2152、1812、21、452_5b0f、124。
  · **稳定低分 3**:2209(0.11×3,题面误读 what year→championship)、
    2576(0×3,东部时区+福克兰链)、1731(0.5×3,Eclipse Tour 角色)。
- **结论:不恒对的主体(约 6 成)确实是"判别语义在池中不可表达,
  只有近义关系"家族 + 数据切片缺陷**;纯 plan 方差约 3 成;
  恒对组则金标关系直接在池且无判别错配。你的判断成立——
  这两个家族(判别不可表达/切片零边)是天花板的主要成分,
  修复入口在数据修复与两轮游走,不在渲染。

### 轨迹内部分歧分诊(2026-09-03 用户裁决性问题:计划截断 vs 关系选择截断)
- 方法:29 个不恒对案例,同案例 best-seed vs worst-seed 对比;结构签名
  (answer_type/事实数/锚点/每事实头尾),避免逐字比较的假阳性
  (逐字版 20/29 全是"plan分歧"——TEMP=0.3 措辞必异,作废)。
- **结构重诊结果(29 案例)**:
  · **plan 结构截断 18**——其中事实数截断 ~10(败 seed 拆解不足:
    两约束问题只拆 1 个事实,212/537_80c3/1797/60/21/124…);
    锚点不同 ~8;answer_type 方向 4(1840/626/2152/25_892)。
  · 稳定失败 5(1731/2209/2319/241_a609/2576)
  · 下游(渲染/答题)4(1812/2784/3744/452_5b0f)
  · 池不可表达 1(452_343e);双双漏选但金标在池 1(567_11fd)
- **结论:关系选择截断在三分 note 后已不是案例内失败主因(≈0-1 例);
  主因是 plan 结构截断(75% 的非稳定失败),典型形态 = 欠拆解
  (多约束问题拆成单事实)**。候选缓解(排队):plan 门"约束计数
  ≥事实数"(数值/最高级约束问题要求 ≥2 facts)——比 answer_type 门
  更结构化;或中文对照进一步压 plan 方差(已 +2.1pp 上界)。
- 工具:tmp/divergence_diagnosis.json(逐字版)+ 结构重诊脚本内联。

### 欠拆解思考过程审计(2026-09-03 用户问题:模型是否认知到第二约束)
- **败 seed 思考全都认识到了两个约束**:212 败 seed 思考明确列
  "1.河流流经州 2.人口<965000"并写了 R2 [FILTER];537_80c3 败 seed
  更是主动权衡过("should also consider… second fact for netflix_id…
  Actually… could be part of the same subgraph")后决定不拆。
  **认知在,发射截断**——又是"第一稿锚定+纠正不传导"家族。
- **但发出的 plan 连 R2 行也一起截掉了**(212/537_80c3 败 seed 的
  plan 只有 R1+covers R1)→ 纯 R-覆盖门(declared-but-uncovered)
  看不到被截的需求,不会触发。
- **可部署门(设计,待裁决):问题线索×契约一致性门**——不是硬性
  ≥2(用户约束:单事实数据集不能误伤):统计问题的约束线索
  (数值+比较词 less/greater/first/longest/most/before…),
  expected_min_Rs = 1 + (1 if 数值/比较线索存在);
  declared_Rs < expected → 单次拒绝:"问题携带数值/比较约束(引用
  原文短语)但计划只声明 R1——把该约束作为独立需求+事实重发"。
  单事实问题无线索 → 通过。覆盖欠拆解 ~10 案例的绝大多数
  (965000/60031289/1783503/0.05/29118/1000/132/longest/first/
  most recently 全是线索)。

### Plan 概率分布统计(2026-09-04 用户问题:正确/错误 plan 各自概率)
- **方法**:10 个 plan 分歧案例 × 16 采样(TEMP=0.3+中文对照) + 贪心
  (TEMP=0);按 answer_type|facts 结构签名分类。
- **结果双峰分布(关键发现)**:
  **A 组(7 案例,正确 plan 主导)**:212(14/16 f2), 1840(16/16),
  626(16/16), 2152(12/16), 1797(15/16), 124(16/16), 21(16/16)。
  正确 2-fact plan 是众数,贪心全部正确。失败 = TEMP=0.3 采样尾巴。
  **B 组(3 案例,错误 plan 主导)**:537_80c3(15/16 f1), 25_892
  (15/16 f1), 60(15/16 f1)。**贪心也错误(1-fact)**——正确 2-fact
  plan 只在赢 seed 中以 1/16 概率出现!
- **结论**:用户"可能是采样或概率层面"的假设在 A 组成立(模型
  本来就偏好正确 plan,失败是采样尾巴→降 plan 温度或 plan best-of-N
  即可修),但在 B 组不成立——**模型的 argmax 就是欠拆解**,正确
  行为是低概率事件。B 组 = 训练靶点或线索门靶点。
- 工具:tmp/plan_dist_stats.py → tmp/plan_dist_stats.json

### Plan 概率分布修正(2026-09-04 用户发现偏差)
- **用户抓到的偏差**:V38n 中 537_80c3 有 2/3 seed 正确(2-fact plan),
  但我的孤立实验只测到 1/16——不一致。25_892 同样(V38n 2/3 正确 vs
  实验报告 1/16)。
- **排查**:①prelink 确定(4 次相同);②seed kwarg 被 HTTPChatBatch
  的 `**_` 静默丢弃(16 个"不同 seed"实为同一随机状态的 16 次
  采样,产生相关性偏差);③batch 模式重测(32 样本同批):
  · 537_80c3: 2+facts **3/32(9%)** — 仍低但比 1/16 高
  · 60: 2+facts **4/32(12%)**
  · 25_892: 2+facts **12/32(37%)** — 比原来报告的 1/16 大幅上调!
- **偏差源**:vLLM batch 组合效应——孤立 16 采样 vs 部署环境
  (144 轨迹交织批)的浮点计算序不同,同一温度下采样行为有差异。
  **结论:B 组的"错误 plan 主导"结论需要软化**——25_892 实际是
  37/63 分裂(不是压倒性 1-fact),537 和 60 大约 10% 正确
  (低但不是 1/16);实际部署中的 2/3 正效率与这些概率相容
  (批间方差大)。A 组结论不变(12-16/16 正确主导)。
- **修正后的分组**:A 组(>70% 正确):7 案例,采样尾巴型;
  B 组(<40% 正确):3 案例,模型偏好欠拆解但不是压倒性的——
  正确 plan 概率足够让 3 seeds 拿到 2 个。

### GPT 审计回应 + trace 对齐验证(2026-09-04)
- **GPT 审计正确发现了 dump 中的 case 混合**(626 前缀匹配了 3 个不同
  案例),但根因定位需要修正:
  · **底层报告数据是干净的**——逐 case_id 验证:question 唯一 ✓
    gold 唯一 ✓ F1 重算一致(修 pipe 分割后)✓
  · **dump 脚本 bug**:`startswith('WebQTest-626')` 前缀匹配了
    626_01ad(Tempus/Kansas)、626_5258、626_74344 三个不同案例,
    9 条轨迹混在一起当作一个案例的 3 seeds 展示
  · 已修复:tmp/plan_divergent_dump_v2.txt(精确 case_id 匹配 +
    完整性校验通过)
- **GPT 的 P1/P2/P3/P4 分类和 OSPD 框架被采纳**:
  P1 正确拓扑主模态→降温;P2 正确拓扑存在非主模态→OSPD;
  P3 多拓扑合理但执行质量不同→GCE 全轨迹选择;P4 plan 正确
  但后续错误→非 plan instability;X=实验/trace 污染(已修)
- **GPT 的行为不稳定性精确定义被采纳**:弃用"认知-行为不一致"
  (依赖 hidden reasoning 解释),改为 **behavioral policy instability**
  ="high-quality tool behaviors exist in the model's rollout
  distribution but are assigned insufficient probability mass"
  (可直接实验验证)
- **下一优先级**(GPT 建议):做 rollout 完整性 hash 校验
  (question/prompt/prelink/plan/answer/gold/F1 全链路 hash)
  后再做受控概率重测,才能谈 P(correct plan | same state)

### 行为分类 + 信息增益联合标注(2026-09-04)
- 实现:tmp/infogain_v2.py(证据前缀 + 'Answer: gold' → echo+logprobs →
  逐 sg 调用 ΔP);bug 修复:aiohttp 作用域 + 响应解析用
  logprobs.token_logprobs(prompt_logprobs 键名不对)。
- **关键数字(所有 sg 中 |ΔP|>0.3 的)**:
  · 537_80c3 三个 seed 的 sg2 都是 **ΔP≈+2.7-2.8**(第一个 sg 把
    金标作品带入证据时概率暴涨)——**欠拆 seed0 也有此增益**,说明
    证据获取本身有效,失败在后续过滤缺失
  · 60 三个 seed sg2 ΔP≈+0.86-0.96(金标国家入证据);过拆 seed1
    额外的 sg3 ΔP≈0(冗余行为,无新信息但浪费轮次)
  · 25_892 三个 seed sg2 ΔP≈+3.9-4.3(金标作品入证据);拓扑漂移
    seed0 的额外 sg 调用 ΔP=0(分叉冗余)
  · **1171 s1 sg4 ΔP=-1.27(有害!)**——败 seed 的一个 sg 调用
    主动降低了金标概率(引入了干扰证据)
- dump:tmp/behavior_infogain_dump.txt(4 案例 × 3 seeds,
  行为分类 + ΔP 联合标注,供人工+Codex 审核)
- 分类框架每行为:
  有效(ΔP>0.05) / 有害(ΔP<-0.05) / 冗余(ΔP≈0 且金标已可见) /
  有效-金标可见(ΔP小但首次引入金标)

### LOO 反事实判定(2026-09-04 用户纠正:不要丢掉 classifier v2 方法论)
- **用户指出**:我此前的 ΔP(序列前后差)不是正确指标——正确的是
  LOO(移除此调用后全证据打分)、alone(仅此调用)、结构必要性。
- 实现:tmp/loo_classify.py → tmp/loo_classify.json / tmp/loo_full_dump.txt
  (4 案例 × 3 seeds,每 sg 调用: p_full/p_loo/p_alone/dI/sufficiency
  + 完整轨迹工具输入输出)。
- **关键发现**:
  · **"有害(移除反而提升)" ≠ 真有害**——广撒网调用(如 537 sg0
    检索所有 Hunnam 作品)dI 为负因为全候选池稀释了金标概率;
    但没有它后续过滤调用无从过滤。**需要结构必要性(图可达性)
    联合判定,不能只看概率 LOO**。
  · 赢 seed 的过滤调用(netflix_id 查询)dI 为正(+1.0~+1.5),
    是真正的边际信息增益来源。
  · 1171 败 seed 的 sg 调用 dI ≈ -10(全证据严重稀释金标)——
    证据方向性错误的极端案例。
  · 过拆(60 s1)的额外 sg dI=+0.35(小正)——不是纯冗余,有边际
    信息但成本高于收益。
- **判定规则(v2 修正)**:概率 LOO + 结构必要性联合:
  dI>0 ∧ 结构必要 → 有效; dI<0 ∧ 结构不必要 → 冗余/噪声;
  dI<0 ∧ 结构必要 → "稀释但必要"(广撒网类型,不改判);
  dI>0 ∧ 结构不必要 → 增益但非必要(奢侈证据)。

### 全量行为审计(2026-09-04,基于 GPT 修正分类树)
- **分类树**:对齐成功核心→EFFECTIVE;未对齐但有新证据→REDUNDANT;
  未对齐且无新证据/移除提升→INVALID。监督单位 = 实际 relation-call
  (center+relation+binding),非 plan 文本。
- **全量结果: 342 sg 调用**:
  EFFECTIVE 313(91.5%) / REDUNDANT 16(4.7%) / INVALID 13(3.8%)
- **按 F1 分桶**:
  F1≥0.9: 99% EFFECTIVE, 1% REDUNDANT, 0% INVALID
  F1 0.5-0.9: 98% EFFECTIVE, 0% REDUNDANT, 2% INVALID
  F1<0.5: 70% EFFECTIVE, 16% REDUNDANT, 14% INVALID
- INVALID 集中在: 2209(Brad Stevens,sg0 三seed均inv=多实体无金标);
  2319(Prime Minister,同); 2576(UK Dependencies,sg2 大扇出无金标);
  1171 s1(Reiner Schöne→错误组织空间, dI=-10.17); 452_f79 s1
  (Carmelo Anthony→无金标路径); 241_a609 s2(border_country 重复)
- REDUNDANT 集中在: 2576(6次,东部时区链); 241_a609(3次,GDP关系
  重复); 2152(2次)
- **核心确认**: 成功轨迹的核心调用几乎全为 EFFECTIVE(99%)——
  分类树与 GPT 分析一致;失败轨迹中 EFFECTIVE 仍占 70% 说明多数
  调用本身有效,失败在于关键跳的缺失或方向偏离
- 工具:tmp/classify_allscale.py→classify_allscale.json/.txt

### 子智能体审计验证 + GPT 改判交叉(2026-09-04)
- 子智能体读 tmp/audit_full_dump.txt 逐案验证 GPT 的改判建议:
  6/7 正确,1171 部分正确(GPT 指错调用,真误判在 Darth Vader 跳)。
- **三个系统性修复(子智能体+GPT 一致)**:
  ① 信息量检查前置于 core_align: repeat/subset 或 new_ents=0∧new_gold=0
    不得为 EFFECTIVE(当前 298 个 core_align=True 全部短路,含 8 重复
    +3 空转); 重复检测扩展到关系集子集语义。
  ② 对齐从词法改结构: 必须匹配 (core步位置, center类型, 关系集),
    不是与任意 core 步的关系名重叠; 加硬 INVALID: 未绑定?var center,
    近空结果。
  ③ Core 去冗余: best seed 先做 (center, rel-set) 子集/超集折叠;
    无有效 core 时回退跨 seed 共识。
- GPT 提出的重要补充(待采纳):
  · teacher eligibility ≠ F1==1; 需 answer∧gold_connected∧constraints_closed
  · 轨迹级 MISSING_REQUIRED_ACTION 标签(欠拆解家族的补充行为)
  · 成功核心集合 = {C1..Ck}(多个正确 seed 各贡献结构,非单一 best seed)
  · 判定优先级: 结构必要性 > 结构增益 > 概率/信息增益

### Classifier v3 重构(2026-09-04,子智能体,修三个P0)
- 新文件:tmp/classifier_v3.py(纯结构,无GPU)
- 三个P0修复:
  ①关系保留:每个行为单元携带关系短名集合,匹配/重复检测/金标追踪都用
  ②跨seed核心库:仅从 F1≥0.8 的teacher seed 提取transition,不自我验证
  ③teacher资格:无合格seed→DEFER(8/48案例,60个调用)
- 新分布:EFF 230(67%)/RED 37(11%)/INV 15(4%)/DEFER 60(18%)
- 6个验证案例全过(1171错人/1379空转/537错关系/60重复/626替代路径/25_892)
- 旧vs新:290/342调用改变判定(旧版85%被修正)
- 核心机制:金标切片排他性(同关系但绑定错人不给core match)、
  checkpoint绑定值解析、子集/超集重复检测、重放检测(同关系同结果)

### 概率打分修正(2026-09-04 用户审计:格式+截断双bug)
- **Bug 1**:LOO 用完整 ack 文本(含 note/candidates/provenance 噪声)
  → 概率被噪声干扰
- **Bug 2**:12000 字符截断 → 移除不同调用改变截断位置 → 比较不一致
- **修正**:tmp/prob_clean.py — 只用"子问题+结构三元组"作为证据
  (从 ack 提取 triples 部分,跳过 note/candidates/provenance),无截断
- **验证(1171 s0)**:
  · 修正前: sg0 dI=0.70, sg1 dI=9.31(截断 bug 导致假信号)
  · 修正后: sg0 dI=0.01≈0, sg1 dI=0.004≈0(移除无影响 ✓)
    sg2 dI=3.22>>0(唯一必要 ✓), suff=+0.43(独立充分 ✓)
  · **概率层与结构层完全对齐**

### 概率重算(2026-09-04 修正后全量)
- 工具:tmp/prob_recalc.py(干净证据=子问题+三元组,无截断,batch并发)
- **全量 342 sg 调用**:
  dI>0(有效) 162(47%) / dI≈0(非必要) 82(24%) / dI<0(有害) 98(29%)
  suff>0(独立充分) 269(79%) / suff≤0(不充分) 73(21%)
- **关键案例验证(全部与结构分析对齐)**:
  · 1171 s0: sg0 dI=0.01≈0 sg1 dI=0.002≈0 sg2 dI=3.22>>0 ✓
    (sg2 唯一必要, sg0/1 移除无影响)
  · 1171 s1(败seed): sg1 dI=-1.61(有害) — 军事组织调用引入干扰 ✓
  · 537_80c3 s0: sg0 dI=0.15 sg1 dI=0.45 — 但 s0 缺 netflix_id 过滤
    sg0 suff=2.78(金标入证据) sg1 suff=3.07 — sg1 也有金标(repeat)
  · 60 s1(过拆): sg2 dI=0.20(有轻微增益但非必要) ✓
  · 25_892 s0(拓扑漂移): sg0 dI=-0.05(≈0,TV重做) sg1 dI=3.30(必要)
    sg2 dI=-0.19(unbound变量空调用) ✓
- p(none) 基线因案例而异(-0.6 到 -5.0),不应全局固定阈值

### 概率×轨迹完整审计文档(2026-09-04)
- tmp/prob_traj_audit.md(965KB, 48×3 seeds, PLAN+工具调用+结果+概率+判定)
- 格式: 每 sg 调用显示 dI/suff/gold_in/p(alone)/p(loo)/判定 + 完整三元组
- 判定阈值: dI>+0.1 有效 / dI<-0.1 有害 / 其他=冗余(含 有效*/冗余* 边界)
- 待用户审核后确定最终分类规则→OSPD teacher pool

## 概率打分表示审计 + v2 修复重算(2026-09-04 下午)

### 审计发现(tmp/scoring_prompt_audit.md,含 token 级计分重现)
1. **[P0] 生成 token 混入计分**:`max_tokens=1`+`echo=True` 时 token 列表末尾是
   1 个生成续写 token,旧区间 `tl[gs:]` 把它平均进"答案概率"。单词 gold 下占 50%。
   实证:证据含竞争候选时模型在 "Democracy" 后生成 `,`(想续列名单,-1.52);
   1379 sg1 把 "Priest" 续写成 "Priesthood",`'hood'` 被计入。
2. **[P0] ▸ 段头行候选名单漏进证据**:412 行 `(retrieved · candidates: …)`
   (含 ~18 行超长未闭合)进入打分证据,229/342 调用受影响 —— 稀释效应的载体。
3. **gold 可见性口径不一致**:旧 `gold_in_ack` 在 raw ack 上算;13 个调用 gold 只在
   被打掉的行里(计分器没见过但标 gold_in=1)。
4. p₀ 与 p_full 结构不对称(suff 混入格式效应);55/144 轨迹 subq 数≠调用数
   (位置对齐错位,已加 `subq_aligned` 标记,未修)。
5. 修复对照(4 条目标轨迹):**符号无一翻转,污染压缩幅度不制造效应**;
   但所有旧 suff 被尾 token 系统性压扁,不可比。

### v2 重算(tmp/prob_recalc.py;v1 存档 tmp/prob_recalc_v1_contaminated.json)
- 证据 = 子问题 + 纯结构三元组:▸ 行去掉 roster parenthetical(保留 `▸ --rel-->`),
  error:/entity_error: 回执行也打掉
- 计分区间 = 仅 gold token(`tl[gs:len-1]`),backward 定位也跳过生成 token
- gold_in 改在 cleaned 证据上算(=计分器所见),gold_in_raw 保留
- **全量 342 调用:dI>0 162(47%)/≈0 73(21%)/<0 107(31%)**(v1: 162/82/98,宏观稳定)
- **86/342 越过 ±0.05 带变号**(多为边界小值;1379:s0 sg1/sg2 -0.71/-0.81→+0.22/+0.78
  是 roster 移除的大幅修正)
- **1470:s2 稀释增强**:sg0 dI -0.206→**-0.810**(含金标但有害,suff 也转负);
  sg1 +1.159→+2.502。"含金标但稀释"是真实现象,修复后更清晰
- tmp/prob_traj_audit.md 已用 v2 重建(887KB, 显示证据=计分器所见, 带 subq 未对齐标记)

### 陷阱
- 本机默认 python3=3.8 无 aiohttp;用 `/root/miniconda3/envs/qwen35/bin/python`
- vLLM echo 计分有批次非确定性(重复同 prompt 漂移 ≤0.02);|dI|<0.05 视为噪声带

## 推理规则表示 A/B + 结构连通性层(2026-09-04 傍晚)

### 用户裁定:证据要带原始推理规则(不是单纯拼接)+ 结构连通性判可拆性
- **A/B(4 目标 case)**:plan 头(R*.text + sg*.f* 变量绑定行 + answer:)使
  p_full 全升;1470:s2 sg0 稀释消失(-0.55→+0.18:两 fact 绑同一 ?gov_system,
  scorer 理解为交集约束而非竞争);1379 sg4 必要性更锐(+4.4→+6.0)
- **全量 v3**(tmp/prob_recalc_v3plan.py → tmp/prob_recalc_v3plan.json,plan 头+
  干净证据+gold-only 计分,p₀ 也带 plan 头保 suff 结构一致):
  dI >0 183 / ≈0 83 / <0 76(v2 纯拼接 162/73/107)
- **假稀释 49 个**(v2<0→v3≥0):35 可拆+9 必要+5 无闭包——纯拼接低估了
  agent(它看得见自己的 plan)能提取的价值;v2 保留作 plan-blind 对照,
  两者差值本身是"价值需经结构才可实现"的诊断量
- 仍有害(v3<0)58 个 = 真稀释家族;其中 13 个还是结构必要(必要但噪声大:
  Missouri/Colorado River sg0,gold_in 2-7 金标+竞争者同来)→ 这类不能移除,
  属检索聚焦问题

### 结构连通性层(tmp/struct_connectivity.py → tmp/struct_conn.json)
- 合并无向图(逐调用 LOO 可达性:删该调用边后 question-锚→gold 仍可达?)
  - 锚点 = plan entities ∪ sg*.anchor(**不含**中途发现的 center——删父调用后
    子 center 不再是合法锚,这正是链式情形的正确处理)
  - **CVT 内联属性值必须入图**(节点→attr 值边):Freemasonry/James Earl Jones
    都藏在 `[organization=Freemasonry]` 里,漏了会错判 no_gold + 链式漏检
- 分类:90 必要 / 202 可拆 / 40 无路径 / 10 金标从未入图
- 链式调用 27 个(center ∈ 早期调用节点集),9 个必要;孤立联通检验对链式
  无效(用户预言正确),合并图 LOO 是正确机制
- 用户移除规则落地:可拆 ∧ dI<0 → v2 口径 69 个;v3 口径 34 个(其余 35 个
  是假稀释,plan 头下转正)
- tmp/prob_traj_audit.md 已重建:每调用显示 dI(拼接)/dI(带plan)/结构状态(必要|
  可拆←sg父)/suff/gold_in,seed 摘要以带 plan dI 计

## plan 溯源 / plan 不恰当影响 / 分配合理性评估(2026-09-04 晚)

### plan 溯源
- 144 条轨迹的 plan 全部来自轨迹内 `tool: plan` 消息(agent 运行时自己生成,非外部标注)
- 带 plan dI = "给定 agent 自己的推理框架,该调用的边际价值" — 对 OSPD 是想要的口径,
  但 plan 质量成为测量条件,需单独分层

### plan 不恰当的影响(以结构闭包为 plan 充分性代理)
- closed 125 轨迹/292 调用:ΣdI +0.99,call 层标签可信
- no_path 15/40:结构不通但 ΣdI +3.24 —— **参数化知识泄漏**(LM 文本联想抬高 P(gold),
  非图推理)。此组 dI 为正不代表图证据有效
- no_gold_in_graph 4/10:金标从未入图,call 层无意义
- 实例 1171:s1:plan 分解合理(Darth Vader→配音→军团过滤)但首步检索没捞出金标,
  sg1 dI=-2.4 不能用于 call 判定 → 检索/执行层缺陷
- 规则:call 层分类只在 closed 组做;no_path/no_gold 归轨迹层 P2/P3;55/144 subq
  未对齐(agent 偏离 plan)需带 adherence 标记

### LOO vs Shapley(/tmp/shapley_vs_loo.py,精确 2^n)
- 替代拓扑(两侧独立可达,1470):LOO 双双低估(互相掩护);s0 三路时 LOO Σ=0.84
  vs Shapley Σ=2.01,**sg2 从 LOO -0.12(有害)变 Shapley +0.77(38% 份额)**
  —— LOO 系统性惩罚"第二到达者"
- 互补拓扑(链式,1379):两者一致,价值几乎全归链尾 sg4(109%)
- 混合(1797:s1):LOO Σ≈0.06 抹平信号,Shapley Σ=0.69
- 结论:**分类用 LOO(可拆性=去掉它行不行的操作化);信贷/训练信号用 Shapley**;
  可拆∧Shapley>0 = 冗余备份(不罚),可拆∧Shapley<0 = 真噪声
- 全量精确 Shapley 可行:n≤6 → 每轨迹 ≤64 打分,144 条 ≈5000 请求 ≈20min

## 规则版(无 plan)v4 + LOO 澄清(2026-09-04 深夜)

### 第四变体 v4:只给格式解读规则,不给 plan(tmp/prob_recalc_v4rules.py → v4rules.json)
- RULES = 三元组行读法 + CVT 属性节点说明 + "每块是独立检索,答案须由三元组支撑"(零 plan 信息)
- 分布:>0 176 / ≈0 73 / <0 93(v2 纯拼接 162/73/107;v3 plan 183/83/76)
- 假稀释消失(v2<0→v4≥0)28 个(20 可拆+7 必要);plan 版消 49 个
- 1470:s2 稀释在 rules 下即消失(dI=[+0.23,+0.39] ≈ plan 版 [+0.18,+0.35])
  → 那部分"稀释"主要是证据读法问题;plan 的额外增量 = 组合理解
  (p_full 更高:1379 rules -4.11 vs plan -3.30)+ 冗余识别更干净
  (1379 sg1/sg2: rules +1.4/+1.0 vs plan ≈0)
- **口径矩阵**:v4 rules = plan 无关测量(主判,不受 plan 质量污染);
  v3 plan = agent 视角对照;v3−v4 差值 = plan 质量信号

### LOO/Shapley 澄清(用户"一半"直觉的形式化)
- dI(LOO 边际)只三态:必要>0 / 冗余≈0(零边际,不是负!) / 有害<0(拿走反涨)
- n=2 时恒等式:Shapley_i = ½·suff_i + ½·dI_i,且 ΣShapley = p_full − p0(总量守恒;
  ΣdI 无守恒:替代互压、互补可超)
- 冗余备份的信贷 = 独立价值的一半(n 个替代剩 1/n)——"冗余只剩一半优势"精确成立
- 有害信贷 = ½(suff+dI):独立价值大仍正但缩水,独立价值小转负

## 前缀边际层 + n≥3 + 硬案例判定(2026-09-04 夜)

### 新层:prefix_dI(i) = p(调用1..i) − p(调用1..i−1)(tmp/prefix_marginal.py → prefix_v4.json)
- 顺序敏感边际 = "轮到它时它加了什么"——实现用户原则①"第一个有价值,
  后面冗余的只拿增量";与 LOO(对称,判最终集必要性)互补:
  - prefix>0 loo>0: 141+ 一致有效
  - **prefix>0 loo<0: 35**(当时有用,放全集稀释)
  - **prefix<0 loo>0: 13**(当时有害,但最终集依赖它)
  - prefix≈0: 34(当时就冗余)

### 用户三原则全量落地
- ①顺序:prefix_dI(上)
- ②结构:生长图共享——16 个调用零共享(结构孤岛);+ 连通性 LOO(90必要/202可拆)
- ③信息:**零新节点∪零新边 = 真·零信息 26 个**;其中 18 个 prefix_dI>0.05
  是**重复 priming 伪增益**(重复陈述本身抬高 LM 置信,非新信息)
  — 例:1379:s0 sg2(+1.88)、576:s0 sg2(+0.74,纯重复 sg1 的 1 条边)、
  452:s2 sg0(+0.94,空调用)。**判定优先级:确定性零信息 > 概率增益**
  - 注意:zero_new_nodes 单独不够(可能有新边),必须节点∪边都为零
  - i=0 的零信息 = 空/错 ack(INVALID),i>0 = 纯重复(REDUNDANT)

### n≥3 Shapley
- 守恒仍成立:Σφ = p_full − p0(212:s1: 1.99 = 1.99);"一半"不再有简单式,
  是全部插入顺序的边际平均(替代 n 条各 ≈ suff/n)
- 212:s1(n=3 硬案例):suff=[0.30,1.87,1.83],LOO dI 全正,Shapley 份额
  [5%,46%,49%] — 全部 EFFECTIVE,功劳集中后两个,sg0 锦上添花

### 硬案例(用户:"每个都能定位答案,合起来最好" = p0 < p_alone < p_full)
- 全部调用 suff>0 ∧ LOO dI>0 的轨迹:22 条 → **判全部 EFFECTIVE,不是冗余**
  (每个都带新信息,prefix 阶梯单调升);"麻烦"只在效率维度(非最小轨迹),
  teacher 需要最小化时用 sufficiency point k*(p(prefix_k) ≥ p_full−0.15)截断

## 打分 prompt 溯源确认(2026-09-05)
- tmp/scoring_rules_audit.md:逐字 dump + 来源对照 + Shapley 图解
- **确认:v4 的 4 行 Evidence format rules 是实验时手写的格式说明,
  不是 agent 提示语(V21 485 行)的任何部分**;scorer 上下文 = 问题+4行规则+
  清洗三元组;V21/plan(v3除外)/ack note/候选名单均不可见

## 最终分类级联(结构替代 Shapley,2026-09-05 定稿待确认)

用户裁定 + GPT 分析采纳:Shapley 不进主流程(不可扩展 n!/2^n、非法 coalition、
未来泄露);结构+prefix+LOO 三层覆盖分类,Shapley 仅作短轨迹 sanity check/论文对照;
训练信贷用 prefix(因果方向、O(n)、无未来泄露)。

### 级联规则(全量计数,v4 口径)
- **L0 plan 充分性门(轨迹层)**:closure∈{no_path(15 轨迹/40 调用),
  no_gold_in_graph(4/10)} → call 层 DEFER,轨迹归 P2/P3;此组 dI 含参数化
  泄漏(孤岛可 dI=+8.1),不可作标签
- **L1 确定性结构层(closed 组 292 调用)**:
  1. 结构反事实:删边后锚→金标断 → **必要**(90,概率层免;可加质量旗标:
     必要∧dI<0=22 → 检索聚焦问题家族)
  2. 结构孤岛(零共享 16)→ **游离/无效**;⚠️孤岛≠必然有害(实测 dI 分布
     3负/11正/2零,孤岛子图可含答案文本)
  3. 链式(27):孤立检验不适用,合并图 LOO 已覆盖
- **L2 信息层(可拆 202)**:
  - 零信息(节点∪边均零,26)→ REDUNDANT(确定性,压过 priming 伪增益)
  - LOO dI<0(可拆,54)→ **有害·可移除**;dI>0 → **EFFECTIVE**
  - dI≈0(73)→ **prefix 仲裁**:首载者 prefix>0(28)→ EFFECTIVE·被替代
    (功劳归首载,冗余帽子给后面的重复;实测仅 4/28 是纯零信息重复,其余为
    换角度部分重复);prefix≈0(25)→ REDUNDANT 真死重;prefix<0(15)→ 有害
- **L3 诊断层(不进标签)**:必要∧噪声家族;最佳 seed 合并图路径定位失败
  seed 断链点(路径=仅由已检索关系边构成,天然满足"与检索关系相关")

### 核心问答:LOO 对冗余的盲区
- 移除后不降 ≠ 有效信息丢失(信息经替代者仍在),丢失的只是功劳归属 → prefix 仲裁
- 移除后上升(dI<0)是另一族(有害/稀释),与冗余分开
- 唯一骗过 LOO 的是重复 priming → 零信息确定性判定优先级最高

## checkpoint 绑定入图 + teacher 结构对齐(2026-09-05 下午)

### 结构层盲点修复(P0):checkpoint 绑定入图
- 链条常经过 checkpoint 而非渲染边:537_a52d sg0 只渲染 CVT 片名缺席,
  环境在 `[sg1.f1 ✓] ?movie=[Crimson Peak|…|Abandon|m.0113ygm8|…]` 里展开绑定
- 修复:① checkpoint 星形桥接(值互相连接);② 星节点同时桥接到**产生调用
  自身的节点集**(绑定由该调用证据导出——s1 只含片名不含 mid 时必需);
  ③ checkpoint 与下一条 tool call 同消息时无条件解析(elif 链会跳过)
- 效果:闭包 288→313 调用;no_path 40→21、无金标 10→8;LB 95、DETACH 212
- 剩余 no_path 21 = 真失败(452 Lala Anthony 实体不存在家族等)

### teacher 结构对齐(用户原则验证:与 gold 结构重叠=有价值,发散点=错误步)
- 参考 = 同 case f1≥0.8 seed 的合并边集;逐调用重叠率 = |调用边∩参考|/|调用边|
- closed 轨迹 262 调用:93% 重叠≥50%(行为一致);<10% 的 11 个=已标的冗余/有害
- 失败轨迹三种型:
  1. **发散不回归**(1171:s1 [1.0,1.0,0.04]):错误在 sg2 的关系选择,
     前两步与 teacher 完全一致——不是"锚错实体",是最后一步检索面错
  2. **发散后恢复**(452:s0 [0.0,1.0,1.0] f1=1.0!):sg0 实体错误=断链点,
     sg1/2 重新对齐=正确内容在破碎上下文,agent 甚至答对了
  3. **交错型**(62:s0 [1,0,1,0,1] f1=1.0):空变量调用与正确检索交错
- **L0 门修正**:no_path ∧ f1≥0.8 = 恢复型轨迹,call 层可用 teacher 对齐标注
  (发散步=INVALID,对齐步=EFFECTIVE·恢复);no_path ∧ f1<0.8 才整条归 P2/P3
- 无正确 seed 可对齐(452_f79ffe 全败)= 图/数据缺陷家族

## 结构层改用实际变量(2026-09-05 傍晚,用户裁定:不走文字解析)

### 动机(文字解析的三次翻车实录)
1. checkpoint 绑定不入图 → 537_a52d 误判 no_path(已修,文字层)
2. checkpoint 与下条 tool call 同消息被 elif 跳过
3. walk 候选无渲染边:62:s0 答案只出现在 "candidates not shown
   (walk candidates — no visible edge)" 里,渲染器没出边行 → 文字层 no_path,
   实际 walk 枚举到了(候选 3 个),且 sg2-4 有 Sharon 真实边
   (sibling_s/date_of_death)——轨迹结构健全,no_path 是渲染伪影

### 实际变量回放基础设施(tmp/replay_struct_vars.py)
- SeqReactCase 逐轮回放录制的 assistant 消息(确定性,GTE :8003 实跑)
- 挂钩 _sg_finalize 抓 PatternEvidence:每调用 walk 真实三元组+候选
  (contextvars 防并发竞态——全局 dict 会互相覆盖)
- ctx.var_bindings 直接给校验过的绑定(不再解析 checkpoint 文字)
- base_edges = pilot 子图底边(ctx.h_ids 初始即样本局部图,sg 调用不追加)
- 验证:62:s0 sg0 walk 214 三元组/95 候选;全量 144 后台回放中
  → tmp/struct_vars_full.json

### 结构层数据源切换后的语义变化(重要)
- 连通性判定的图 = base(pilot 子图)∪ 各调用 walk 实际三元组 —— 不再是
  "渲染出来的证据图";walk 枚举到但没渲染的边现在计入
- 交错型(62:s0 [1,0,1,0,1]):最终集 LOO 语义下空调用=可拆/无效,
  不是连通性错误(用户理解正确);62 的 no_path 是渲染伪影
- 位置说明:walk 只在 pilot 子图内游走(cs.h_ids=ctx.h_ids 共享数组),
  所以"案例可解性"是 base 图属性;调用层结构=该调用 walk 覆盖了哪些真实边

## 最终标签表出炉(2026-09-05 晚,四层全合成)

### 数据源(全部落地)
- 结构层 = 实际变量(tmp/struct_conn_vars.py → struct_conn_vars.json):
  图=Σ各调用 walk 实际三元组+中心→候选触达边+绑定星形(var_bindings 归属
  首次建立的调用);base 不算 agent 功劳,只判案例可解性
  → closed 327 / no_path 7 / no_gold 8;必要 92;链式 73(文字层只找到 27)
- 概率层 = v4 规则版(主判);prefix 层 = prefix_v4.json
- 零信息判定在实际变量上重算(walk 三元组∪候选∪绑定增量 vs 已生长集)

### 342 调用最终标签(tmp/final_labels.json)
  EFFECTIVE 家族 230 (67%): 纯有效 111 + 必要 70 + 必要·噪声 22 +
    被替代 21 + 恢复 6
  有害家族 69 (20%): 可移除 59 + prefix仲裁负 10
  REDUNDANT 26 (8%): 零信息 14 + 死重 12
  INVALID 空调用 8 (2%); DEFER(plan-limited) 9 (3%)
- 抽查验证:1470:s2 sg0 在 v4 口径下假稀释消失→EFFECTIVE ✓;
  1379:s0 sg4 必要/sg1-3 零信息 ✓;62:s0 sg0 必要·噪声/sg1 空调用/
  sg3 纯重复(重复 sg2 的四姐妹日期检索)✓;1171:s1(f1=0)整条 DEFER ✓

### 口径链(最终版)
文字渲染证据(v4打分) ↔ 实际检索变量(结构) 双轨;分类主判=实际变量结构
+v4 概率+prefix 仲裁;teacher 对齐处理恢复型与 P2/P3 诊断

## 渲染幽灵候选缺口:机制 + 修复(2026-09-05 深夜)

### 机制(62 Disney 标本全程还原)
- 模型选了错域关系(fictional_universe...children)+ spouse;真实孩子边
  people.person.children 未选,但 walk 经 children/parents/spouse 链枚举到
  Diane/Sharon → 进 lp["candidates"]
- lp["candidates"] = walk 全量叶子聚合(candidate_counts),而边只来自
  ≤24 条 support path(多样性过滤挤掉了家庭链);lp["raw_paths"] 本身也被截
  → 候选有名无边,ack 里只剩 "walk candidates — no visible edge" 注释
- 影响:金标级缺口 5 条轨迹(62:s0 缺口后 4 轮全在重摸金标;1797:s0 金标
  完全不可见);广谱幽灵(75/144 轨迹);缺口轨迹平均 2.80 轮 vs 2.36
  ——多轮部分归因渲染,corpus-wide 非主因

### 修复(kgqa/stages/formatting.py,SEQ_GHOST_EDGES 门控默认开)
- GHOST-CANDIDATE EDGE GUARANTEE:每个被渲染点名的候选必须有 ≥1 条
  可见连接边;缺失时用 lp 自身 rel_chain 约束在本地子图 BFS 重建
  anchor→候选路径(≤4 跳,每模式 ≤60 个),边经 path_edge 通道入
  pat_triples,路径同步进 tree_data.paths(V38 从 tree 渲染,只进 triples
  不可见——踩过这个坑)
- 验证:62:s0 sg0 现在渲染 `Walt Disney --children--> Diane|Sharon`,
  ghost 注释消失;重幽灵 12 条抽样 ghost 调用 17→7(余为 >4 跳/链名
  不匹配长尾);渲染相关测试 70 过,可跑测试共 133 过
  (test_cvt_passthrough 缺 val.pkl、test_skill_aggregation 缺
  subgraph_kgqa 模块,均为环境问题非本改动)
- 待办:带修复的 48×3 重跑测答案级效果(需 LLM 预算)

## 幽灵修复的证据对照 + 概率重测(2026-09-06)

### 证据展示对照(tmp/ghost_render_diff.md;回放 27 条幽灵重灾+62/1797 全 seed)
- 52 个调用证据变化;62:s0 sg0 +4 条家庭边(children/parents 双向);
  1797:s0 参战将军们的 participated_in_conflicts 边 6→13 行
- 捕获:tmp/fixed_acks.json(修复后 ack);62:s0 回放只出 4 个含 triples 的
  ack vs 录制 5(sg1 错误回执无 triples)——对比时注意按含 triples 对齐

### 概率重测(tmp/fixed_rescore.json;27 条,v4 规则口径,新证据)
- **金标可见性:5 个调用 0→有**(此前清洗证据里完全看不到金标)
- dI 频带翻转 17 个:10 个离开有害带(567:s1 sg1 -0.51→+0.20、
  241:s1 sg1 -0.16→+0.64、1797:s1 sg2 -0.16→+0.21),5 个转入有害带
  (多为后继调用:1797:s2 sg1 +2.39→-0.12、626_01ad:s2 sg1 +1.97→-0.07)
- **垄断功劳崩塌模式**(用户预言"渲染影响概率"实锤):前驱证据补上金标边后,
  后继调用的必要性大幅回落——62:s1/s2 sg1 +4.9→+0.9,功劳正确回流 sg0
  (gold 0→1);说明旧口径下这些大 dI 部分是证据缺口的伪影
- 最终标签表这些调用需刷新;完整刷新 = 全量 144 回放+重打分(可跑)

### 下一步
- LLM 全量重跑(48×3,修复渲染)测答案级效果——待用户排期

## 有害带翻转 5 例审核(2026-09-06)
- tmp/harmful_flip_audit.md:5 例终判 = 仅 2152:s2 sg3 真有害·可移除
  (-0.53,league CVT 大杂烩);2 例必要·噪声(626_01ad:s2 sg1 LB、
  sg0 实为绑定生产者);1 例无效·错检索(1797:s2 sg1 选了 place/cause
  而问题需要 date_of_death);1 例噪声带内(-0.06)
- 有害判定收紧(用户原则:有害结构难评估错,须严):①可拆∧dI<-0.15;
  ②结构损害证据;③错检索。首载者(prefix>0)仲裁扩展到轻微负区
- 发现 bug: 独立 checkpoint 消息的绑定所有权错归下一调用
  (626_01ad:s2 sg0 实为 ?setting 生产者,应判必要)

## 结构层 v3:检索中心语义(2026-09-06,用户根本性裁定)

### 裁定内容
- 结构连接**不走变量绑定**,走检索中心:序列调用的中心(变量调用=环境实际
  展开的实体集,walk[].centers 即"工具实际调用的东西")必须落在上一子图的
  检索边缘(walk 三元组端点∪候选)上
- 废除 checkpoint 星形/绑定所有权机制;绑定生产者的必要性自然涌现
  (移除提供边缘的调用,子中心与锚断开)
- anchors = 问题实体+plan 锚+首调用中心;后续新根中心=发散(孤岛标记),
  不得混入锚集;reach 边(中心→候选)不得指向锚或更早调用中心(回边非链)

### 验证要点
- 626_01ad:s2 双锚语义:ctx.anchor=Missouri River(问题第二锚),sg1 边直连
  Kansas↔Missouri → sg0 可拆是正确的(1470 同构);单锚(Tempus)时 sg0=必要
- 链式检出 27→163(中心语义正确捕获变量调用链);必要 89;no_path=0
  (原 no_path 组经候选触达闭包,标签下移到概率层),no_gold 8

### 最终标签 v2(tmp/final_labels.json,v3结构+收紧有害+首载者负区仲裁)
  EFFECTIVE 家族 252 (74%): 纯有效116+必要66+必要·噪声23+被替代39
  有害·可移除 36 (11%)(原69;~23个轻微负转被替代/冗余·噪声)
  REDUNDANT 37 (11%): 零信息24(实际变量口径,只看walk∪候选)+死重13
  冗余·噪声 9 (3%);INVALID 8;DEFER 8
- 已知口径差:标签仍用旧证据 dI(V4);修复渲染后的 27 条重打分
  (fixed_rescore.json)显示垄断功劳崩塌,全量刷新需重回放+重打分
- 1797:s2 sg1 型"错检索"(关系维度错失)尚未自动化检测,暂落有害/冗余桶

## 中心来源三分类 + 四类审计 dump(2026-09-06)

### 用户裁定落地:中心来源分类(342 调用)
- 独立根(问题实体,合法多锚第二链) 167
- 链式(中心∈前驱边缘) 163
- **发散(非问题实体且非前驱边缘) 6** ← 真正可疑,如 1171:s1 sg1
  中心=Reiner Schöne(agent 把自己的错误猜测当检索中心)
- 空调用 5;首调用默认根 1
- 判定规则:问题实体→独立子图根(合法);前驱边缘→链式;两者皆非→发散

### 审计文档 tmp/label_audit_dump.md(639 行)
- 四类各 2-3 条代表轨迹(必要/必要·噪声/被替代/有害·可移除/零信息/
  空调用/DEFER),每调用显示:中心+来源+结构状态+链+dI+prefix+gold_in+
  标签+关系+证据前 10 行;附发散案例专节
- 已知口径差在文档中可见:626_01ad:s2 sg0 旧证据 prefix 判"有害·可移除",
  修复证据 prefix(+2.15)应判"被替代"——全量重打分后此类会翻转

## 传播式 LOO(2026-09-06,用户审计 1379:s0 发现)

### 问题
- 1379:s0 sg0(Franz Liszt→Freemasonry 提供者)被判可拆:sg1-3 的冗余重复检索
  自带回边(m.0cr70y2 --member--> Life of Franz Liszt),移除 sg0 后这些
  来自冗余调用的边让锚→金标仍连通 —— **冗余信息洗掉了提供者的必要性**

### 修复:传播式移除
- 移除调用 i 同时使其下游全部失效(经 chained_to 传递:中心来自 i 边缘的
  调用根本不会存在),LOO 在调用 DAG 上而非边集上做
- 验证:1379:s0 sg0→必要 ✓;626_01ad:s2 sg0→必要 ✓;
  1470:s2 双锚保持可拆(独立链互不依赖)✓;62:s0 sg0 保持必要 ✓
- 必要 89→148;LB∧dI<0(必要·噪声)23→50(链提供者多为入口调用,常带噪声)

### 最终标签 v3(tmp/final_labels.json)
  EFFECTIVE 家族 258 (75%): 必要98+纯有效97+必要·噪声50+被替代13
  有害·可移除 26 (8%);REDUNDANT 37 (11%);冗余·噪声5;INVALID 8;DEFER 8

## 多亲 DAG 传播 + 锚集补全(2026-09-06,用户 DAG 过度移除质疑)

### 用户质疑成立,两种过度移除形态
1. **单亲归属**:chained_to 取最早提供者,中心在多个前驱边缘时(实测 40/158
   链式调用)移除最早者会错杀本可由其他提供者养活的调用 → 假性必要
2. **锚集不全**:hint 只有 ctx.anchor+chains,缺 plan entities 行 →
   第二问题实体(1470 的 Nelson Mandela)被当无提供者发散调用,定点里被
   禁用 → sg0 假性必要(1470:s0 实测复现)

### 修复(v3.2)
- 多亲 DAG:providers=全部提供者;调用禁用 ⟺ 自身被移除或所有中心均
  无存活的提供者(定点迭代);兄弟分支永不互相禁用
- 锚集 = ctx.anchor ∪ chains ∪ **plan entities(问题实体全单)**
- 多中心调用:全部中心需可推导(绑定现实:?var 绑定值来自证据并集)
- 验证:1470:s0/s2 双锚全可拆 ✓;1379:s0 sg0 必要(级联全灭,sg1 唯一
  提供者是 sg0)✓;62:s0/626_01ad:s2/537:s0 sg0 必要 ✓
- 必要 145;最终标签 v4:EFFECTIVE 家族 ~75%、有害·可移除 ~8%

## DAG 过度移除疑虑的最终澄清(2026-09-06,用户两问)

### 问1:同起点双路径部分交集,移除无效者是否伤有效者?
- 不会:移除只经"中心供给"传播,绝不经边缘交集传播。兄弟调用各保留
  自己的提供者。实证 1379:s0:移除 sg1/sg2/sg3 任一都只死自己,
  sg4(金标载体)经 sg0 存活 → 可拆 ✓

### 问2:派生供给(sg1 的实体来自 sg0)是否被当独立提供者?
- 定点迭代 = 用户时序语义:提供者须自身存活才算数。
  静态 providers=[[],[0],[0,1],[0,1,2],[0,1,2,3]] 看似多亲,
  全是派生(假多亲);移除 sg0 级联 [0,1,2,3,4] 全灭 → sg0 必要 ✓
- 全量统计:40 个多亲调用中 39 个假多亲(相依级联死)、仅 1 个真独立
  双供给(452_f79ffe sg4,提供者 [1,3] 互不相依)——即用户"同一起点
  独立检索到,移除一个 sg2 仍成立"的唯一形态,定点让它正确存活
- "额外角度"与零信息层一致:1379 sg1-3 的派生供给无新信息角度,
  结构层判级联死 + 信息层判零信息,两层互相印证

## 分层视图确认(2026-09-06,用户演化视角)
- 用户洞察:同层探索被顺序化成链(sg1 信息被当 sg2 前置)。实证:
  显示层(chained_to=最早引入者)本就分层正确——1379 的 sg1-4 全部 ←sg0
  是兄弟;假链边只存在于静态 providers 多重集(包含语义),定点级联中和
- 全量:28 条轨迹有兄弟组(同引入者),67 个兄弟调用(1379:s0 sg0→[1,2,3,4]、
  537_4346 同构、1797/576 sg0→[1,2] 型);113 条纯链/独立
- 兄弟隔离验证:67 个兄弟调用逐一移除,同层兄弟连带死亡 0 例
  (2570:s2 的"违反"是分组显示粗糙:sg2 中心集混合——FDR来自sg0、
  Truman仅sg1引入——它是 sg1 的真依赖子节点,级联正确)
- struct_conn_v3.json 增 layers 字段(引入者→兄弟组)供后续审计

## 层内选择评估(2026-09-06,用户"拼接比较"想法落地)
- 概念澄清:移除式反事实(实际集中谁不可少=标签)与选择式(最小充分子集
  =层内归因+teacher修剪)是**对偶操作,不冲突**——都是反事实家族,
  聚合不同:LOO 固定"去掉一个",选择枚举"留哪些够"
- 实现(/tmp/layer_select.py → tmp/layer_select.json):每层枚举子集,
  V(S)=P(gold|其余证据∪S),最小充分 S* = 最小的 |S| 使 V(S)≥V(全层)−0.1,
  平局取最早(首载者,与 prefix 一致)
- 结果(28 层):单兄弟即充分 17;**空集即充分 5(整层冗余,层级修剪)**;
  互补型 3(576:s0 sg1+sg2、60:s1、2152:s1 三兄弟全要);
  1379:s0 最小充分=sg1+sg4(sg2/3 可剪)
- 与零信息层一致性:62:s0 层(sg0→[2,3,4])最小充分=sg2,与零信息标签
  (sg3/4=零信息)完全一致;1379 的 sg1 被选择式轻微升级(会员关系块的
  概率框架价值,零信息看不见)——两层互补使用
- teacher 修剪规则:轨迹构建时每层只保留 S*

## "空集充分"5例人工审核 + 判据修正(2026-09-06)

### 审核结论:原5例无一干净,三类病因
1. **判据缺陷(3例)**:ε 带对 v_full 比,而 v_full 被层内稀释者拖低
   (2570:s2 sg1单独-0.30 好于全层-0.43;25_7cec、567_df 同型)
   → 修正:对 **v_best(子集最大值)** 比
2. **失败轨迹平坦带(2576:s2,f1=0)**:全域 -4.2~-5.7,空不空都烂
   → 修正:门控只做 f1≥0.8 的成功轨迹(绝对P下限会错杀1379型
   f1=1.0 但答案词天生低P的案例)
3. **参数化冗余(21_6671:s1)**:sg0 后 P≈0.98,层空集也高,但 sg2 是
   结构必要+正确接地行为 → 修正:**金标可见性守卫**(S* 须保持金标在
   证据中可见),sg2 被强制保留

### 终判(tmp/layer_select.json 已更新)
- 原"空集充分"5例 → 3例修正为单兄弟最小充分(sg1/sg2)、2例门控(失败
  轨迹)、**仅 1 例真整层冗余**(567_df:s2:sg0 的 Ron Howard 片单已含
  金标 Village of the Giants,层重复探索零增益——冗余对象是父调用而非层间互补)
- 28层终态:门控11 | 部分充分16(修剪) | 互补1(576:s0 sg1+sg2 真双要) |
  真整层冗余1
- 用户疑虑("空集vs互补影响很大")验证正确:互补仅1例且为兄弟内互补,
  无"层与层互补被误判空集"的情况

## 约束层打分 + 跨角度互替裁定(2026-09-06,用户三问)

### ① 25_7cec:s2 约束概率(tmp/constr_angle.py 输出)
- 约束探针:C2=小说作者(Stephenie Meyer)、C3=获奖提名、A=答案
- **sg3(award 检索)= 约束闭合者**:P(C2)=-1.34、P(C3)=-0.23 全场最佳
  ——"Based on the Novel by Stephenie Meyer" 就藏在 award CVT 的
  notes_description 属性里,两个约束的证据落在同一侧(用户"两个约束
  同一侧给"证实)
- sg2 = C2 部分支持(-1.98);sg1 = 噪声源(全指标拖低:加它全降)
- sg0+sg2+sg3 是最优子集(P_A=-0.358 优于全层 -0.391)

### ② 567:s2 跨角度移除测试(用户预测证实)
- 移除 sg3: -0.167→-0.296(**降 0.13,sg3 有独立信息贡献**)
- 移除 sg2: -0.147(反而更好——sg3 单侧更强)
- sg2+sg3(无 sg0)= -0.177 ≈ 全集:判别对自身几乎充分
- **裁定:跨角度互替 ≠ 冗余**。sg2(?movie侧)与 sg3(主题侧)是独立
  子图从不同角度到达同一判别证据 → 标"互为替代·独立角度";
  冗余保留给同层同角度重复。层判定已改

### ③ 21_6671 结构优先裁定(用户)
- 层内选择 S* ⊇ {LB 兄弟}:结构必要调用强制保留,选择只在可拆兄弟间
  仲裁——与主级联同构(结构先判,概率后判),替代金标可见性近似
- sg1(Government of Ethiopia --government_for--) = 错检索面(拿不到PM),
  与答案不连通,判冗余

## 统一裁定机制 v5(2026-09-06,用户整体重构指令,替代全部补丁)

### 机制(tmp/unified_adjudication.py → tmp/unified_labels.json,单一连贯实现)
- **L0 案例可解性**:金标在 pilot 底图?否→DEFER(数据集属性)
- **L1 逐锚闭合**(新,修复任一锚闭合漏洞):每个问题实体锚都必须到金标;
  闭合双通道=路径 ∨ 文本共现(锚与金标在同一检索中共现——25_7cec 的
  "Based on the Novel by Stephenie Meyer" 在 award CVT 属性里闭合 R2);
  ?变量不算锚。未闭合→整轨迹 DEFER(锚未闭合)
  → 实测:严格路径版 20 条未闭合;文本共现通道后 4 条(1171失败seed/
  124影展从未浮出/452实体不存在/567误报已修)
- **L2 调用结构**:多亲传播 LOO(引入者供给,锚=plan实体+首调用中心)
- **L3 层内**(用户算法):LB兄弟强制必要;其余按增益 V({sg})−V(∅) +
  重合度(Jaccard walk节点):低重叠有增益=有效;高重叠取强=互替,
  弱=冗余;无增益=冗余。**空集整层冗余废除**(任一成员有增益即非全冗余)
- **L4 有害**:核心路径偏离且断链=有害;偏离未断链=无效探索(非有害)
- 触达边(中心→候选)计入结构图(567 Ron Howard 锚靠它闭合)

### v5 分布(342)
EFFECTIVE 家族 255 (75%): 必要140+纯有效74+层内低重叠23+互替12+被替代6
有害 22 (6%): 可移除20+偏离断链2;无效探索2;冗余家族45 (13%);
INVALID 7;DEFER 11
### 标本终判(全部与人工对齐)
- 21_6671: sg0必要/sg1无增益冗余(错面)/sg2必要 ✓(用户判法)
- 25_7cec: sg0必要/sg1无增益/sg2高重叠弱/sg3互替 ✓(约束分析)
- 1379:s0: sg0必要/sg1-3冗余/sg4必要 ✓
- 62:s0: sg0必要/sg1空调用/sg2互替(首载)/sg3无增益/sg4高重叠(重复sg2) ✓
- 567:s2: sg0冗余·轻微噪声/sg1层内低重叠有增益(金标随绑定展开落入其
  entities行)/sg2低重叠增益/sg3有效 —— sg0/sg1 待用户终审

## 计划符合度维度 + v5 终态(2026-09-06/07)

### 567 缺陷类型查实
- 底图有桥:m.0k7rl9 --film.performance.film--> Village of the Giants
  (正是 sg0 取到的 Ron Howard film CVT)→ **walk 未浮出缺陷**(157候选
  无金标),非数据集缺陷;sg0 行为完全正确,价值经链(sg1 绑定展开)实现

### 计划符合度通道(用户数据缺陷裁定,原则性维度非补丁)
- 符合 = 忠实执行自己的 plan fact 且是该 fact 的**首个证据满足者**
  (证据 = walk 关系语义匹配 fact 子问题 ∨ 绑定增量);重复调用/错面
  调用不得分;优先级:LB > 符合度 > 层内 > 概率
- 归因修正:满足判定基于证据而非绑定记账(62 标本:日期证据在 sg2,
  sg4 重查只重新声明绑定);绑定展开值归浮出调用的 walk

### v5 终态分布(342)
EFFECTIVE 家族 293 (86%): 必要140+推理符合67+纯43+层内17+互替11+被替代3
有害 9;无效探索 2;冗余家族 32 (9%);INVALID 7;DEFER 11
- 标本对齐:567 sg0=推理符合✓ sg3=有效✓;62 sg0必要/sg1空调用/
  sg2互替首载✓;1379 sg0必要/sg1-3冗余/sg4必要✓;21_6671 三判全对✓

### 留给用户终审的两个边界分歧
1. 567:s2 sg1(genre 调用):机制判"层内低重叠有增益"(金标随绑定展开
   落入其 entities 行,V 增益+4.6);用户判冗余/略有问题——
   entities 行算不算该调用的功劳?
2. 62:s0 sg4(重复 sg2 的日期检索):机制判"推理符合"(绑定 ?death_date
   的首个声明者);用户判冗余——事实满足用证据还是绑定声明?

## 缺陷分型 D1-D4(2026-09-07,用户"清晰划分"指令)

### 567 根因完整因果链(逐级核验)
- plan R1.text 把 "did" 解释为 "produced or directed"(过窄)
- → 子问题 "which films did this person produce"
- → GTE 按措辞返回,film.actor.film 不在池(首条 REL 结果实查确认)
- → 无 actor 边可走(金标 Village of the Giants 是 Ron Howard 的
  **出演**作品,base 边 film.actor.film→m.0k7rl9→gold)
- → 金标 ∉ RH 侧枚举集/?movie 绑定 → R1 侧约束从未闭合
- 轨迹仍答对:主题侧(sg2/sg3 Child prodigy→gold)+ 参数化知识
- 结论:**调用忠实,计划解释有缺陷**;此前"walk未浮出缺陷"说法修正

### 分型判据(tmp/defect_partition.py → defect_partition.json)
- D1 渲染:金标∈walk候选 ∧ ∉渲染文本(已修 ghost edges)
- D2 walk枚举:沿已提交关系底图可达 ∧ ∉候选(walk beam/压缩)
- D3a 计划解释:所需关系不在 GTE 池(子问题措辞过窄)——567 实判
- D3b 选择:所需关系在池,未提交
- D4 数据:边不在底图
- **关键语义升级:交集题闭合 = 集合成员关系(金标∈该侧枚举集),
  非无向路径连通**——567 经编辑者巧合路径(RH→影片→Bushelman→gold)
  被假闭合的教训;per-anchor membership closure 已实现

### 全量分型(144)
正常(双侧成员闭合)106 | 单侧未闭合 35(各带 per-side D 标签)|
D3a 1 | D3b 1 | D2 1
- 已知局限:D2/D3a 边界依赖 needed-rels 路径启发,巧合路径可误标
  (567 自动标 D2,手工核验 D3a);时间感知池已实现

## 弃答救援家族(2026-09-07,567 命中机制终查)

### 567:s2 命中的完整机制(逐消息核验)
- 模型三次正确拒绝:ANSWER_ANALYSIS 明确 "R1 UNRESOLVED — Village of
  the Giants NOT in Ron Howard's film list",answer:NONE ×2、再拒 ×2
- harness 弃答梯子:NONE→重探索重启 → "2nd refusal → answer from current
  support" 强制从当前候选作答 → unconsumed-entities gate 逼出主题侧
  sg3(单例候选)→ 被迫答单例 = 金标 → f1=1.0
- **模型行为全程正确(含诚实弃答);命中是救援策略+单例运气的产物,
  R1 侧始终未闭环**

### 全量:弃答救援家族 7/144 轨迹(f1≥0.8 者 4,f1=0 者 3)
- 同案例跨 seed 表现分裂(567:s1=0 / s2=1;2784 三 seed 1/0/1)——
  印证救援命中不稳定,非 grounding 支撑
- OSPD 含义:单侧未闭合家族(35 条)里的"命中"需过此透镜——
  救援命中不做干净 teacher;模型诚实弃答行为本身是好样本

## 审计一(567 主题边入图机制)+ 机制二(关系约束 join)评估(2026-09-07)

### 审计一:Child prodigy→Village 边为何在证据里
- RH 侧电影的 subjects = Television/Freemasonry/Boxing/Substance abuse/
  Pedophilia —— **无一 RH 电影主题是 Child prodigy**,主题边不在锚集合
- 入图机制:sg2 提交 film.film_subject.films(双向)——从 RH 电影的主题
  出发扇出"同主题的所有电影",walk 多跳在主题图里游走出锚集合,
  Village 作为 pattern 终端被枚举(渲染如实展示了 walk 的所作所为)
- 结论:**不是渲染缺陷,是遍历语义缺陷**(提交关系含反向扇出类
  film_subject.films,允许离开锚的候选集);兜底强答恰好用了这个
  越界证据 → 假命中链条:计划解释窄(D3a)→ 遍历越界拉入 gold →
  弃答救援抓单例
### 机制二评估(用户提案:关系约束 join)——合理,双对照验证通过
- 形式化:多锚交集中,候选 J 有效 ⟺ J 从每个锚出发、沿**该锚自己
  提交的关系**可达(首末跳提交,CVT 透明,中间跳透明)
- 567:s2(负对照):RH 侧 False ∧ 主题侧 True → join 无效(正确拒绝,
  与模型自己的 ANSWER_ANALYSIS 判断一致)
- 1470:s2(正对照):Poland 侧 ✓ ∧ Mandela 侧 ✓ → join 有效
- 用途:作答前的 join 门(替代/加固 unconsumed-entities gate 与强答
  兜底)——无效 join 的候选不得被兜底采用,弃答应被接受而非强改
- 实现成本低:累积 walk 图 + 每锚提交关系集的受限 BFS

## D5 遍历越界(2026-09-07,用户判据:关系合法⟺头实体在候选发出路径上)

### 567 桥路实证
- 漂移路径:Cinderella Man(RH电影)→ **English Language(万度枢纽)**
  → Village of the Giants → Child prodigy
- Village 深度2、Child prodigy 深度3 —— 均不在许可集(?movie绑定∪其直接
  主题)内;"Child prodigy --films--> Village" 头实体深度3 = 纯越界边
- sg2: 704 边中 63 越界

### 全量 D5 审计(许可=中心∪深度1)
- 228/342 调用含越界边,共 ~16 万条越界边;148 调用越界占比>20%
- 逃逸枢纽 TOP:m.0z8zbq7(50k!)、Cenischia(28k,地理超枢纽)、
  United States of America(11k)、Europe(3.6k)、Ron Howard(2.1k,
  中心自身成为逃逸节点)
- 危险形态:金标经越界入图(567)→ 为兜底强答提供假接地;
  一般形态:噪声污染(稀释)
### 修复方向(待批,门控)
- walk 端:枢纽感知的许可界(高度过/通用类枢纽 language/country/
  genre/geo 不得作为 2 跳通道)
- 作答端:机制二 join 门(已验证)——双保险,假命中链两头堵

## 游走核心缺陷确认:未提交关系遍历(2026-09-07,用户判据)

### 实证
- 567:s2 桥路两跳骑 film.film.language —— **不在提交集
  {subjects, film_subject.films} 内**
- sg2 边分布:198 subjects + 84 film_subject.films(✓提交)vs
  422 条未提交(produced_by/production_companies/director.film/language…)
  = **60% 边骑在未提交关系上**
- 全量:255/331 调用含未提交关系边,共 **214,230 条**(证据边总量的大多数);
  仅 76 调用纯净

### 为什么被记录:设计内行为
- walk 的多跳 K 路径在深层跳探索未选择关系(SAPS 覆盖策略);
  materialize/evidence build 忠实物化这些链;V38 专门用
  "▸ other walked relations:" 节渲染(seq_render_v38.py:258)——设计自己
  承认越界展示
- 用户裁定:**提交关系 = 遍历许可**。language 类枢纽关系作 2 跳通道
  超越两跳和 CVT 延长跳的合法范畴 —— 此为核心游走缺陷

### 修复方向(待批,stage_5 级改动,需门控+重跑验证)
1. walk 端关系许可:每跳 ∈ 提交集 ∪ CVT 透明延长(不支持链路视为不可通行)
2. 枢纽关系黑名单:language/country/genre 等通用类不得作中转关系
3. 作答端 join 门(机制二,已验证)兜底

## 越界边对金标的影响:双维度审计(2026-09-07)

### 关系维度(边骑未提交关系)
- 轨迹级:**0/144 金标纯靠未提交关系入图** —— 21.4万越界边对金标是
  纯稀释噪声,不带来答案
- 调用级:13 个调用 gold 仅经关系越界(标签影响:推理符合5/必要1/
  互替1/EFFECTIVE1/冗余6)
- 567_df97 复核:其金标经 sg3(Child prodigy 锚的合法调用)入图,
  sg2 的漂移导入是 sg3 的重复——不属此家族

### 实体维度(头实体漂移入图,关系可合法)
- **12 条轨迹金标仅经游走漂移入图**("原本拿不到、靠噪声获得"):
  命中 7(567_11fd:s2、21_6671:s1/s2、1379某seed、1171某seed、1923:s2)
  未中 5(567_11fd:s0/s1、25_892、372、452_f79)
- 行为判定影响:这 7 条命中的 标签(必要/推理符合/互替)建立在
  含漂移金标的证据上——概率层与结构层都看见了不合法到达的金标
- OSPD:与救援命中同族,不做干净 teacher;7+13 为审计黑名单

## 结构过滤屏蔽实验 + 归因裁定落地(2026-09-07)

### 结构过滤(tmp/license_filter.py → license_filter_result.json)
- 许可 = 提交关系 ∪ CVT 透明 ∪ 身份镜像透明(同名实体↔topic/book 管道,
  based_on/representations 限定两端同名;1379:s1 标本:人物事实挂在
  'Life of Franz Liszt' 镜像节点,事实边 profession 是提交关系,只有
  身份桥未提交——管道不是事实)
- 结果:边保留 95%;134 轨迹金标保留(全部合法成功接地完好);
  **7 条金标消失:f1≥0.8 的仅 567_11fd:s1(漂移假接地,过滤后应转为
  诚实弃答),其余 6 条本就 f1=0**
- 结论:过滤温和且精准——只消灭漂移通道,不伤合法证据

### 归因裁定(用户)
- 救援行为归因到 plan:plan 实体命中好 → plan 功劳大;兜底依赖
  plan 双锚判定 + 行为中的提交关系
- 关系命中的救援:归因到对应关系/子图调用
- 完全无关但救援命中:按冗余处理(非零价值)
- 核心目标:行为与实际结构连通性对应(模型行为↔结构判定一致性)
- OSPD 展示暂缓;行为归因先行,后续分强化学习/自蒸馏两支(未到分支点)

### 待批上线项(全部已验证)
1. 渲染端:候选/边按许可过滤展示(屏蔽越界)
2. 作答端:join 门(无效 join 不得被兜底采用,接受弃答)
3. walk 端:关系许可+枢纽中转黑名单(stage_5 级)

## 金标消失 7(9) 条 × 兜底经历核查 + walk 端改动定性(2026-09-07)

### 兜底保护核查
- **8/9 未经历兜底梯子**——它们是自己答错的(噪声/无接地直答),
  与救援家族(7条:2576/567_df:s2/2784×3/1171:s2)基本不重叠
  (仅 567_df 一条重叠:救援了仍错)
- join 门对这些轨迹的作用点在**作答校验**(不限救援路径):
  6 条错误答案→诚实弃答(训练信号从"自信错答"变"知不可解"),
  1 条假命中(567_11fd:s1)→消失

### walk 端改动定性(与前两个的本质区别)
- 渲染过滤=walk 照走、展示屏蔽(回放兼容,agent 影响需 48×3 重跑测量)
- join 门=作答路径环境校验,不动检索
- **walk 端=改检索引擎本体**(stage_5 游走时不再枚举越界边,非事后
  屏蔽——与 ghost 边渲染修复不同类):省计算+源头干净,但整轨迹
  系统性变化,且有过约束风险(feeding guarantee/Option-B/support-path
  裁决均建立在"walk自由枚举+渲染层筛选"架构上)
- 建议顺序:前两个先上+48×3 测量;walk 端二阶段单独门控
  (SEQ_WALK_LICENSE),依前两个数据定优先级

## join 门确认 + 渲染许可过滤上线(2026-09-07)

### join 门机制确认(用户口径)
- 即:A --(A侧提交关系)--> J --(B侧提交关系)--> B —— 两实体间路径
  分段骑各自提交关系,候选 J 是汇合点;不是随便连

### 渲染许可过滤已上线(kgqa/agent/seq_tools.py _display_license_filter,
### SEQ_LICENSE_FILTER 门控默认开)
- 展示变量级:all_triples/candidates/pe_list(tree paths)过滤后才渲染;
  ctx 累积/绑定/join 门不动(展示专用)
- 透明规则:提交关系 ∪ CVT ∪ common.topic.*/user.* 管道 ∪ 同名身份镜像
- 回放验证:567:s2 sg2 漂移行(language/country/Child prodigy 越界)消失✓;
  1379:s0 sg4 Priest 保留(镜像透明)✓;测试 70 过
- **规则冲突提示**:62:s0 sg0 的 children 边被过滤——它是 ghost 修复按
  walk 链补的,但 children 未提交(该 seed 选错关系族),按许可规则属
  越界,过滤正确。含义:ghost 边保障现在只覆盖"许可内候选";越界关系
  的候选不再展示——62 型轨迹重跑时 sg0 看不到家庭,模型会被
  RELATION_MISMATCH 梯子推向重选关系(训练正确行为)。join 门若上线,
  62:s0 会诚实弃答(答案链骑未提交关系)

## join 路径展示原型(2026-09-07,用户设计:直接展示两实体间路径)

### 设计(替代"候选验证"式理解)
- 多锚 plan:在许可累积图上直接枚举 A↔B 的 top-k 最短路径并展示;
  答案 = 路径上的汇合节点,而非单独验证的候选
- 许可图:边合法 ⟺ 关系由走出它的调用提交(∪CVT/身份镜像透明)

### 原型验证(/tmp/join_paths.py,三标本)
- 1470:s2:Poland–**Democracy**–m.0zp3h5p–Mandela(3跳,★金标在路径上)
  ——展示即推理,答案就是汇合点 ✓
- 567:s2:Ron Howard↔Child prodigy **无 join 路径** → 正确导向弃答/重选
  关系(假命中轨迹在展示层即被拦)✓
- 25_7cec:s2:Lautner↔Stephanie Meyer **无路径但轨迹合法**(约束经
  award CVT 的 notes_description 属性文本闭合,不是类型化边)——
  **边界待裁定**:join 路径要不要把 CVT 属性值当伪边?
  (需要的话:解析 CVT 括号 k=v 为 (cvt,attr,v) 边,属性值与锚模糊匹配)

## join 路径 × CVT 穿透语义定稿(2026-09-06,用户纠正)

### 语义(替代"伪边"提案——不需要裁定,是路径本体语义)
- 类型化边逐条计算;命中 CVT(抽象点)时透明穿透:CVT 的角色/属性
  本来就是独立类型边(m.09tz5_t --notes_description--> "Based on the
  Novel by Stephenie Meyer"),穿透=路径沿这些边继续
- 答案 = 关系的实体端点 或 关系命中的 CVT 内邻居(精确命中,精确到边)
- 锚匹配:词级+1编辑距(问题 Stephanie ≈ 图 Stephenie)

### 三标本终验(/tmp/join_paths2.py)
- 1470:s2:Poland–**Democracy**–speechCVT–Mandela ★金标在路径 ✓
- 567:s2:无 join 路径 → 正确弃答 ✓
- 25_7cec:s2:Lautner–perfCVT–**New Moon**–awardCVT–"Based on the Novel
  by Stephenie Meyer" ★金标在路径 ✓(作者约束经穿透精确命中,
  此前的"伪边缺口"不存在——属性就是类型边)

### 机制就绪,待接线
- 作答链(ANSWER_READY/兜底前)展示 A↔B top-k join 路径;
  空路径 → 接受弃答/推向 RELATION_MISMATCH 重选

## 567 改判 + join 递减阶梯 + 嵌入拥挤(2026-09-06)

### 567:s2 缺陷类改判(数据核查推翻纯 D3a)
- 底图直连存在:Ron Howard --actor--> m.0k7rl9 --starring--> Village(2跳)
- **GTE 池全程提供过 film.actor.film/performance.film**(60关系含之;
  仅 sg0 时刻的池因子问题措辞未含)
- 终判:前段 D3a(计划措辞→池缺)+ 后段 D3b(池给了 actor,模型未选)
  = "正确行为 vs 错误数据供给"的混合;选择错误可训练纠正,非数据不可解

### join 递减阶梯(已验证,/tmp/join_ladder.py)
- L1 完美(双侧提交关系):567 无 → L2 单侧(任一提交):无 →
  L3 walk图:language枢纽漂移路径(垃圾,须管道过滤或跳过)→
  L4 底图直连+管道过滤+GTE语义排序:
  **Ron Howard–film–m.0k7rl9–starring–Village–subjects–Child prodigy ★**
  (score 0.7036,次位 0.6430,边际可分)
- 管道过滤 = 寻路时排除 common.*/user.*/base.*/kg.*/type.*/annotation 类
  (过滤前 17 条路径被 TV Episode/annotation 垃圾占据且 GTE 给垃圾最高分)

### 嵌入拥挤(用户观察证实)
- 现象:候选同质(垃圾为主)时 GTE 分挤在 0.60-0.69 难区分;
  管道过滤后同质垃圾消失,分差拉开(0.70 vs 0.64)
- 缓解:管道过滤(首要)+ 边际阈值(Δ≥0.03 才采信排序)+
  关系域加权(待需要时)

## 阶梯全量 + 兜底归因(2026-09-06,用户归因规则落地)

### 归因规则(用户):兜底路径上出现谁的关系,谁是正确侧;
### 没出现的那侧 = 关系选错被兜底拉回;plan 与正确侧记功

### 多锚轨迹阶梯分布(32 条,修正 CVT 入/出许可:入 CVT 须提交关系,出 CVT 展开)
- L1 完美(双侧提交) 7 | L2 单侧 10 | L3 walk图 10 | L4 底图 1 | 不可达 4

### 触发兜底 11 条的效果
- **124(L4,唯一底图兜底):双侧✗选错被兜底** —— Angelina Jolie↔2012
  Berlin 影展,两侧关系都没选对,数据兜底路径存在,f1=0.40(双错最重)
- L3 家族 10 条:walk 图(未选关系)介导的 join —— 同案例 seed 分裂
  再现(1171: 0/1/1;2784: 0/1/1)——不稳定命中,与救援/漂移家族同构
- 567_df:s2 落 L2:主题侧(sg2/sg3 的 subjects/films)承载 join,
  RH 侧贡献为零 = 用户判读("第二个子图没问题,第一个关系没给对")的
  机制化确认
- 归因输出示例(124):两侧 hops=0 → 双侧选错;(567 型):B侧 hops>0,
  A侧=0 → A侧选错被兜底

## 含兜底机制的最终分配 + dump(2026-09-06)

### 约束(用户):兜底只在触发时起作用,不主导分配
- L1/L2 + 单锚(131 轨迹,~311 调用):join 成功合拢/无 join → 原始 v5
  标签原样保留,兜底完全不介入
- L3/L4(13 轨迹,~31 调用):兜底归因区(路径逐跳归侧)

### 阶梯分布(以 unified_labels 144 条口径)
L1 完美 4 | L2 单侧 11 | L3 walk介导 12 | L4 底图 1 | 不可达 4 | 单锚 112
### 分配总览(原始区 vs 兜底区)
必要 133/7,推理符合 53/14,纯有效 37/6,层内各类 17+12+11+10/0,
DEFER 5/3 —— 兜底区体量 ~9%,原始分配不受影响

### dump:tmp/ladder_attribution_dump.md(608 行)
按 L1→单锚 分组;每轨迹 Q/gold/f1/调用标签;L4 带逐侧归因+路径;
L3 家族含 seed 分裂标本(1171: 0/1/1)

## 完整轨迹+分数审计 dump(2026-09-06)

### tmp/allocation_full_audit.md(1597 行/99KB)
- 32 条多锚全量:plan+阶梯等级+兜底归因;每调用=中心/来源/结构状态/
  dI/prefix/gold_in/标签/关系/证据15行;112 条单锚索引
- **dump 立即抓到并修复一个归因真 bug**:逐跳归因须检查节点对全部关系
  (BFS 任选一条会漏记提交关系),且兜底路径应按"侧贡献覆盖"择优
  (k最短中选骑提交关系最多者,前缀容忍)——124 实证:奖杯枢纽路径
  vs directed_by 电影路径,修正后 A/B 双侧✓(3跳),终判从"双选错"
  改为"**join 执行失败**"(两侧各自正确,轨迹内没接上,兜底路径显示
  只差一跳)

### 审计方法论确认(用户):分数必须与轨迹行为并排可审

## 124:s2 审计 → 两修(2026-09-06,用户发现)

### 用户发现:sg1(电影节约束闭合)被标"冗余(死重)",dI 仅 0.04

### 三个原因(两个机制 bug + 一个已知现象)
1. **参数化泄漏(已知)**:sg0 出 4 部导演片后,打分模型凭先验已"知道"
   哪部符合"2012 柏林影展"(波斯尼亚战争片 vs 旅拍/文艺片)→ sg1 的
   约束闭合证据几乎不抬 P → **概率层只测获取,看不见判别**
2. **BUG 1(已修)——符合度偷分**:generic token(如 'film')让
   sg0 满足了"影展 fact"(sg2.f1 的子问题含 'film'),窃走 sg1 的
   推理符合 credit。修:匹配去掉 generic 词表
   (film/movie/this/which/what/person/appear/…)
3. **BUG 2(已修)——任意锚 LOO**:结构必要性只查"移除后金标是否仍
   可从**任一**锚到达"→ 移除 sg1 后 Jolie 锚仍通(festival 锚断了)
   → sg1 判可拆。修:**逐锚闭合检查**——移除后每个锚都必须仍闭合,
   否则判定必要(约束闭合型调用获必要信用)

### 结果
124:s2 终判:sg0=必要, sg1=**必要**(约束闭合,用户判法 ✓)
v5.1(342): EFFECTIVE 288(84%)·冗余 27·DEFER 11·INVALID 7·有害 5·
无效探索 4(原死重 7→1,必要 140→179——约束闭合型调用大面积升必要)

## 124:s2 分数全链诊断 + 判别探针(2026-09-06,用户"基线过高?"质疑验证)

### 完整分数链(回滚后原始数据)
p0=−0.526(P≈0.59!)| p(sg0单独)=−0.128(0.88)| p(sg1单独)=−0.068(0.93)
p_full=−0.084(0.92)| dI(sg1)=+0.043 —— sg1 单独其实是**最强单证据**

### 诊断:双重天花板 + 缺失≠证据
1. **参数先验**:打分模型从问题文本就知道答案(P0≈0.59)
2. **候选列表先验**:sg0 的 4 片单 + 模型知识 → 0.88,约束增幅被压进
   0.88→0.93 的窗口
3. **判别探针**(4 候选相对概率,sg0 vs sg0+sg1):
   - sg1 真实做了判别工作:By the Sea −2.25→−3.56、Unbroken −3.65→−5.08
     (强抑制),金标 −0.51→−0.37(提升)
   - 但 **A Place in Time 纹丝不动(−0.003)**——它没出现在影展行里,
     而"缺失≠证据":约束证据只能抬升在场的候选,不能抑制缺席的
   - 结果:金标仍排第二(0.69 vs 1.00),P(gold) 几乎不动,dI=0.04

### 结论
- dI 低 ≠ sg1 无价值;是指标在参数饱和 + 缺失不可抑制下结构性失明
- 修复方向(用户裁定后实施):约束型调用改用**判别边际**指标
  Δ=|(gold−最强竞争者)的margin| 前后变化,或结构性逐锚闭合(已回滚待裁)

## 567:s2 sg1 的 +4.55 增益来源诊断(2026-09-06,用户审计第三弹)

### token 统计正确性:无 bug
- prefix 链 [−5.05, −0.50, −0.29, −0.17] 全部合法(≤0),
  +4.55 是真实增量(p(sg0单独)=−5.05 → +sg1=−0.50)

### 增益的真实来源 = 漂移导入的答案行
- sg1 证据含:`Village of the Giants --subjects--> Child prodigy | Giant`
  ——关系 subjects 是提交的(合法),但**头实体 Village 是漂移进来的**
  (∉ RH 制片/导演片单;sg1 只提交了 subjects/genre/story_by,
  language 和 film_subject.films 都没提交 → 许可图内到不了 Village)
- 打分器看到答案名+主题约束 → P 从"无法确定"跳到 0.6 → +4.55
- **增益真实,证据被污染**——与 124 的"参数天花板"不同,这是
  "漂移导入"型虚增益

### 生产许可过滤下的后果(推演,待重打分验证)
- 该行会被过滤(Village 不在 sg1 许可集)→ sg1 增益崩塌 → 标签翻转
- sg2 同理(Child prodigy 头实体也是漂移的);sg3(Child prodigy
  锚中心)合法保留 → 与用户判法一致("信息增益角度也该是第三个")
- **根本结论:概率层必须跑在许可过滤后的证据上**(重打分队列的
  具体理由),旧证据上的 dI 对漂移导入型虚增益无免疫力

## 概率层三查:转换/对齐/复现性(2026-09-06,用户审计第四弹)

### ① exp(均值)≠概率 —— 用户"prob/softmax 互换"批评成立
- 四条件 token 对齐完美(同 7 个 token:In/the/Land/of/Blood/and/Honey)
- 但 exp(mean)=每token几何均值,不是答案概率;联合=exp(SUM)
- 124:s2 联合空间:p0=2.8% → sg0=29% → sg1=52.9% → full=59.5%
- **dI(sg1) 联合=+0.719 → 移除sg1: P 60%→29%** —— 约束贡献一目了然!
  均值空间只显示+0.04~0.10 的原因:判别信号集中在首token
  (' In': −1.23→−0.52),均值把它稀释了 7 倍(token数)
- **决定:打分指标从 MEAN 改 SUM(联合 logprob)**——约束探索的
  "提升/移除不明显"问题大幅缓解,无需另造指标

### ② 复现性问题(新发现)
- 2调用轨迹同 prompt 校验(p_loo(sg1)≡p_alone(sg0)):61 一致 /
  24 差>0.02 / 最大差 0.409 —— vLLM echo 打分的批次效应比此前
  认定的 ≤0.02 大得多;概率层需确定性重打(顺序单发或加大边际)

### ③ token 对齐:验证干净,非问题来源

### 下一步(用户同意重新 rollout)
1. SUM 指标全量重打分(改打分脚本,无需 LLM rollout,~1-2h)
2. 许可过滤后的回放重ack + 重打分(567 型漂移增益消失)
3. 完整 48×3 agent 重跑(带过滤渲染,行为级验证,预算项)

## 指标设计三查(2026-09-06,用户:mean/sum偏差 + 非线性)

### 实证确认的三问题
1. **sum 长度塌缩**:17答案金标联合P≈1.5e-26 —— 多答案案例进入死区,
   任何Δ都≈0;语料中位3词但有12条16+词、36条多答案(最大17实体)
2. **mean 稀释/虚高**:判别信号集中首token,均值按token数稀释
   (124:7词稀释7倍);多答案的免费分隔/续写token反向抬高均值
3. **非线性**:logΔ=0.05 在 P≈0.9 区=+4.6pp,在 P≈0.002 区=+0.0pp
   —— 固定log带(±0.05/0.15)跨区间不可比

### 指标方案(定稿)
- **打分单位 = 单个金标实体的联合logP(sum over 该实体token);
  案例分 = 各实体的平均;所有Δ以概率点(pp)报告与判带**
- 性质:长度中立(逐实体)·多答案中立(实体平均)·保留判别力
  (实体内sum,124: +0.719→ΔP 60%→29%)·pp带自适应区间
- 判带(pp):|Δ|<2pp 噪声;2–10pp 轻度;>10pp 强
- 实现:打分脚本逐实体请求(多答案逐实体打分后平均),改 tmp/
  prob_recalc_v4rules → v6;带内比较全部换 pp

## dI 定概率区间 + 多答案聚合实测(2026-09-06,用户裁定)

### ① 124:s2 概率空间(判定翻转,用户预期验证)
P(仅sg0)=29.0% | P(仅sg1)=52.9% | P(full)=59.5%
dI_P(sg1) = **+30.5pp → 强有效**(mean空间曾判"冗余(死重)")
dI_P(sg0) = +6.6pp → 轻度
- 概率空间里约束调用(sg1)比获取调用(sg0)贡献更大——与均值空间
  完全反转,与用户人工判法一致
### ② 多答案聚合:逐实体 vs 拼接整体(212:s2 三实体实测)
- 拼接整体:p0=1.5e-14 → full=1.9e-5(pp 死区,3实体已塌)
- 逐实体:p0≈0 → full: Arizona 7% | Colorado 6% | **Nevada 0%**
  (逐实体还暴露哪个实体无支撑——Nevada 模型从未说出)
### 指标定稿(v6)
- 单实体:联合logP → dI 报 pp;多实体:逐实体概率,案例分=实体平均,
  附逐实体分解;带:>10pp 强 / 2-10pp 轻度 / <2pp 噪声
- 与许可过滤证据+确定性单发合并为一次全量重打

## 冗余→有效翻转验证(概率空间,2026-09-06)

### 7 个翻转,逐个对照实际轨迹
1. **1797:s2 sg2 (+4.5pp)**:重复了 sg1 的 date_of_death 数据但确实把
   "Pemberton 1881-07-13" 这条约束证据再次呈现——概率空间判"轻度有效"
   合理(约束证据重复出现仍有正贡献,但结构上 sg1 已闭合,应判"互替
   弱侧"而非纯冗余)
2. **537_4346 sg2/sg3/sg4 (+4.2/+6.7/+7.7pp)**:三个 netflix_id 层内
   调用各有不同 film 的 release/participant 边——**概率空间正确**:
   各自携带不同候选的分面数据,不是零信息重复;但结构上 sg1(netflix
   过滤)已闭合答案,层内价值应标"互补分面·结构上被覆盖"
3. **2152:s0 sg2/sg3 (+5.4/+2.5pp)**:同层球队 founded 数据不同面
   ( Anaheim 1997 / league 关系 / 历史经理),概率空间有贡献;
   结构上 sg1 已闭合
4. **62:s0 sg3 (+2.2pp)**:**空证据调用**——evidence 为 empty,翻转
   是 header removal 的伪影(去除 "[Sub-question:...]\n(empty)" 块
   本身改变了 prompt),不是真信息贡献 → **应保持冗余,排除翻转**

### 结论
- 概率空间下 7 个翻转中 **6 个真实**(约束/分面证据重复但有正贡献),
  1 个伪影(空证据,header 效应)
- 意味着旧均值空间的"冗余"标签有两类:
  a) 零信息纯重复(62:s0 sg3 型,保持冗余)
  b) 分面互补但结构已闭合(537_4346 sg2-4 型,应改"互补分面·结构已闭合"
     而非"冗余")
- v6 重打后标签表需要这个二分类

## 62:s0 sg4 漏洞 + 全 27 调用原始vs新对照表(2026-09-06)

### sg4 为什么不是冗余(用户抓到的 conformance 漏洞)
- sg4 与 sg2 walk 关系完全相同(date_of_death + sibling_s/sibling)
- sg2 已通过 sem 匹配拿到 fact sg2.f1 的 conformance credit
- 但 ?death_date 的 bind_gain **首次在 sg4** → conformance 又给 sg4 credit
- **漏洞**:sem 已在 sg2 命中同一 fact,sg4 的 bind_gain 不应再给 credit
  (证据已在,只是 agent 延迟声明了绑定)→ sg4 实际是重复调用
- **应修**:当某 fact 的 sem 已被更早调用满足时,后续 bind_gain 不再给
  该 fact 的 conformance credit

### 27 调用对照表(tmp/old_vs_new_scores.md)
- 7 翻转(6真+1伪) + 20 非翻转;原始 dI(mean) 与新 dI_P(pp) 完整对照
- 62:s0 sg3(空证据)的 +2.2pp 伪翻转:去除 header 的 prompt 变化效应

## conformance bind_gain 移除(2026-09-06,用户裁定)

### 裁定:结构层看实际实体和关系,不看绑定声明
- 绑定声明 = agent 记账行为,不是检索行为
- sg4 走了和 sg2 完全相同的 walk 关系 → 就是重复,直接冗余
### 修复:conformance 满足判据 = evidence semantics ONLY(sem 匹配),
### bind_gain 分支整体移除
- 62:s0 sg4:EFFECTIVE(推理符合) → **冗余(层内·高重叠弱增益)** ✓
- 全量:推理符合 67→57(10个曾靠 bind_gain 获得 credit 的重复调用
  被正确降级);必要/其他不变

## 结构层数据源全量审计(2026-09-06,用户"不走文本解析"原则)

### ✓ 已用实际变量的环节(9/14)
结构连通性/逐锚闭合/CVT穿透/许可过滤/零信息/传播LOO/join路径/
绑定数据/调用中心+关系 —— 全部走 struct_vars_full 回放捕获

### ✗ 仍在解析文本的环节(4项,按影响排序)
1. **Teacher对齐边提取(edges_of)**:解析渲染 ack 文本→frozenset 边;
   应改用回放 walk triples(已有数据)——影响 teacher 对齐准确度
2. **概率层 gold_in**:在清洗 ack 文本中搜金标字符串;
   应改用回放 walk candidates/triples——影响金标可见性判定
3. **REL 池提取**:解析录制 REL 结果文本→关系集合(用于 D3a/D3b 分型);
   应在回放中抓 REL 结果(ctx 内部)——目前回放未捕获 REL 调用
4. **Plan 解析(entities/facts/R)**:正则提取 plan 消息文本;
   plan 本身是 agent 输出的文本格式——可在回放中从 ctx 抓
   fact_ids/fact_texts/chains(部分已抓,anchors 有;facts 的 R 规则文本未抓)

### 修复优先级
- 高:edges_of(teacher对齐用) + gold_in(概率层用)——数据已有,改引用即可
- 中:REL 池(需扩展回放捕获)——影响 D3a/D3b 分型
- 低:Plan R 规则文本(ctx 有 fact_ids/fact_texts 但 R 的 .text 未在 ctx 中,
  plan 是 agent 行为输出,文本解析有一定合理性)

## 子智能体全量审计:层内裁定 vs 用户规则(2026-09-06)

### 用户规则(回忆确认)与实现状态

| 规则 | 状态 | 偏差 |
|---|---|---|
| 1. 同层顺序逐个判定结构连通 | **缺失** | 层内无结构连通检查,纯增益+重叠 |
| 2. 唯一联通者=必要 | **缺失** | 唯一联通者若无全局LB,可被判冗余 |
| 3. 首载者优先 | **反转** | 代码用"增益最高者存活",非首载者 |
| 3a. 低重叠+有增益→保留 | **修补** | 重叠参照对象错(全部兄弟vs应为首载者);增益阈值0.02/重叠0.5为魔数 |
| 3b. 高重叠→冗余不论增益 | **修补** | 高重叠时仍保留最高增益者为"互替";平局双存活 |
| 4. 不联通=自动冗余 | **修补** | 不联通但有正增益仍可标EFFECTIVE |

### 结构层数据不一致
- unified_adjudication **不加载** struct_conn_v3.json(独立的LB计算)
- inline 重算用了**更松的边集**:无条件加中心→候选触达边,违反了
  v3 的"回边非链"裁定
- 锚集也不一致(v3含ctx.anchor,unified只有plan实体+首调用中心)

### 额外未授权判据
- 推理符合(conformance)在层逻辑**之前**执行,可覆盖层规则
- L1 文本共现闭合通道(≥4字符token匹配)
- L4 有害判定条件疑似反逻辑(移除不断链→反标有害)

### 关键行为偏差(最大地鼠)
1. 高重叠时"最高增益者存活"而非"首载者存活"
2. 唯一结构联通者可被概率增益判定为冗余
3. 不联通但有正增益的调用被保留为有效
4. layer_select.json 的 f1 门控和最小充分子集 verdict 被忽略
5. any_gain(空集禁令)和 fact_sat 均为死代码(未强制执行)

## 用户规则终稿修正(2026-09-06)

### 规则④修正(不联通的处理)
- 不联通 ≠ 自动冗余
- 不联通的调用走 **teacher 对齐检查**:与正确轨迹的关键信息/边重叠 → 保留
- 不联通 + 不与 teacher 重叠 → 冗余(对答案无结构贡献,也无教学价值)

### 规则③b修正(高重叠的处理)
- 高重叠 → **首载者存活**(不是最高增益者,不是双存活)
- 后续高重叠者全部冗余

### 完整层内裁定规则(终稿)
```
同层裁定 =
  1. 逐个判定结构连通(该调用的边是否承载锚→金标路径)
  2. 不联通 → teacher 对齐检查
     a. 与 teacher 轨迹关键信息重叠 → 保留(教学价值)
     b. 不重叠 → 冗余
  3. 唯一联通 → 必要
  4. 多联通 → 首载者优先
     a. 后续低重叠(与首载者) + 有增益 → 保留(互补分面)
     b. 后续高重叠(与首载者) → 冗余(不论增益)
```

## 层内裁定按用户规则重写完成(2026-09-06)

### 实现的规则(终稿,替换全部补丁版层逻辑)
```
同层裁定 =
  1. 逐个判定结构连通(传播移除后逐锚闭合是否断裂)
  2. 不联通(层内) → 与首连接者比较重叠:
     - 同中心 OR Jaccard≥0.5 → 冗余(高重叠首载优先)
     - 不同中心且低Jaccard → teacher对齐保留(教学价值)
  3. 唯一联通 → 必要
  4. 多联通 → 首载者优先:
     a. 后续低重叠(与首载者) → 保留(互补)
     b. 后续高重叠 → 冗余
```

### 关键设计决定
- **同中心=高重叠**:同层内同中心+同关系的调用,即使walk枚举节点
  有差异(Jaccard 0.375),语义上是同一探索 → 冗余(1379 标本:
  sg1-3和sg4都center=Freemasonry,walk枚举略有不同但意图完全相同)
- **teacher对齐参照=层内首连接者的节点集**(非所有含金标调用)
- **bind_gain已删,conformance只走sem匹配**

### 标本验证
- 1379:s0: sg0必要 | sg1-3冗余(高重叠首载) | sg4必要 ✓
- 62:s0: sg0必要 | sg1空调用 | sg2-4冗余(不联通无对齐) ✓
- 537_4346:s0: sg0必要 | sg1有效(非层内) ✓

## 62:s0 sg2 修复:约束首载者连接者通道(2026-09-06)

### 用户发现:sg2(死亡日期约束)被错判冗余
- sg0 候选中已有金标(Sharon)→ 移除 sg2 不断裂可达性 → 判非连接者 → 冗余
- 但 sg2 是**唯一提供死亡日期证据的调用**——问题"哪个孩子死于2013前"
  没有日期证据就无法判别 → sg2 是约束首载者,必要

### 修复:连接者识别加双通道
- A) 可达性通道:移除后锚→金标断裂(原有)
- B) **事实证据首载者通道**:层内首个 walk 关系匹配 plan fact 语义的调用
  (约束证据不承载可达性——金标已在候选中——但承载判别信息)
- 层内无 A 通道连接者时,B 通道首载者=连接者

### 62:s0 终判
sg0=必要 | sg1=空调用 | **sg2=必要(层内唯一联通=约束首载)** |
sg3=冗余(高重叠) | sg4=冗余(高重叠) ✓

### Jaccard 问题(用户指出)
- 同中心=高重叠规则已处理大部分;但"高度重叠部分有一个核心关系只给出
  一个三元组"的情况——某个关键三元组只出现在一个调用的walk中——
  这个三元组直接决定联通/不联通,Jaccard 不能捕捉 → 已通过 same_center
  + fact-evidence 首载通道绕过

## 子智能体全面评估:核心规范 vs 实现(2026-09-06 终版)

### 用户核心规范(完整整理)
```
L0 结构移除测试(最高优先级):移除动作→起点→答案路径断裂→有效
   多锚:从各自起点到答案(逐锚,非任一锚)
L1 层级细化:同层(同引入者)内:
   结构必要→有效
   非必要→看信息增益
   冗余探索两种:
   a) 唯一联通→其他不联通=冗余
   b) 多联通→交叉度+信息增益:
      低重叠+双正增益→双存活
      高重叠→选第一个
L2 约束层(答案实体已命中):看概率
   独立动作识别(排除重复)→不重叠动作间信息增益:
   双低→冗余;双高+不重叠→双有效
数据:实际实体和关系调用,非文本解析
```

### 实现偏离(完整清单,16项)
1. **移除测试用any-anchor**(应为per-anchor)
2. **层case a违反**:唯一联通不使非联通兄弟冗余(用teacher对齐替代)
3. **增益合取被丢弃**:case b低重叠不检查增益(sib_v/empty_v加载后弃用)
4. **L2约束层未实现**:无约束调用识别,无双增益比较逻辑
5. 移除用传播级联(规范是单动作移除)
6. 结构闭合允许文本共现通道
7. 锚集部分来自文本解析plan消息(应从回放取anchor字段)
8. 标签优先级反转:L4有害/conformance在结构必要之前
9. 同中心冗余捷径(仅用于非连接者分支,不一致)
10. B通道连接者兜底(conformance→首非空调用)
11. 只解析第一条plan消息(重plan忽略)
12. 无向连通+合成中心→候选边
13. 层≥2兄弟才成层;多亲归一亲
14. disabled()任一中心无供→全禁(严格语义)
15. 魔数:Jaccard 0.5, dI 0.05/-0.15, token≥4
16. on_gold_path 命名与实现不一致

### 额外非规范判据(12项)
L0可解性门/L1整案DEFER/L4有害标签/plan-conformance(推理符合)/
事实首载B通道/teacher对齐/概率微标签(被替代等)/同中心捷径/
传播LOO/文本共现闭合/死代码(binds,sib_v,empty_v,fact_sat)/
meta记录

### 结论:需按规范从零重写,非修补

## 干净重写 v2 完成(2026-09-06,子智能体实现+验证)

### 文件:tmp/adjudication_v2.py → adjudication_v2.json
- 从零实现,严格按用户核心规范,无任何非规范判据
- 数据:全部来自 struct_vars_full.json 回放捕获(实际变量)
  + v4rules/prefix_v4 概率(仅用于约束层和独立调用的增益)
- 图 = 调用 walk 三元组 + 中心→候选触达边(base_edges 不入闭合图)

### 规范实现(逐条)
L0: 单动作移除(per-anchor,无传播)→ 必要
L1: 同层 = 同引入者兄弟;连接者 = L0 判必要的兄弟
    唯一连接者 → 其余全冗余
    多连接者 → 首载优先,低重叠+正增益=互补,高重叠=冗余
L2: 约束调用(中心=答案实体)→ 概率空间增益:
    独立动作识别 → 双低=冗余,双高+不重叠=双有效
L5: 独立调用 → dI 阈值
INVALID: 空walk

### 标本全部通过
- 1379:s0: sg0必要 sg1-3层内重复 sg4必要 ✓
- 62:s0: sg0必要 sg1INVALID sg2约束首载 sg3低增益 sg4约束重复 ✓
- 1470:s2: sg0独立增益 sg1独立增益(双锚) ✓
- 21_6671:s1: sg0必要 sg1层内重复 sg2必要 ✓

### v2 分布(342)
必要107 + 约束首载49 = 结构必要156(46%)
约束低增益42 + 无增益21 + 非连接21 + 层内重复6 + 约束重复5 + 约束高重叠1 = 冗余96(28%)
有害36(11%) + 独立增益35(10%) + 约束互补/有效8 + INVALID11

### 与 v5 补丁版对比
- v5: EFFECTIVE 249(73%) / 冗余67(20%) / 有害10+INVALID7+DEFER11
- v2: EFFECTIVE 195(57%) / 冗余96(28%) / 有害36+INVALID11
- 主要变化:去除全部非规范通道后,必要↓(推理符合/teacher对齐/被替代
  等通道消失),冗余↑(更严格的判定),有害↑(独立概率阈值更严格)

## v2 双审计:代码合规 + 轨迹验证(2026-09-06)

### 代码审计结果(12项检查)
PASS: per-anchor移除/无传播/锚来源回放/无文本解析/约束检测/base_edges不入图
CONCERN:
- Step 3c 增益用 logprob dI 而非概率(缺记录默认0)
- walk_nodes 不含三元组端点(218/342调用受影响,Jaccard偏低)
- same_center 用提交字符串比较(?var形如"?child"的两个不同调用=同中心)
FAIL:
- 层标签覆写约束标签(优先级违反:406-414无in labels守卫)
- 两条死代码路径(L0重标签和3b首标签均不可达)
- 3c规则顺序:same_center被低重叠+增益分支遮蔽
- INVALID过宽(非空walk但无中心+无三元组也标INVALID)

### 轨迹审计结果(10条/41调用)
36 CORRECT / 3 INCORRECT / 2 UNCERTAIN(3个子类型不精确)
**无实现bug——独立重算路由完全复现;所有错误均为规范设计的边界case**

### 7个误标模式(规范层需要修的)
1. **重复检测只对比首约束调用**——后续调用的精确重复逃逸
   (537:s1 sg4 = sg2字节级重复,标互补)
2. **刀锋阈值无边际带**——0.0007差距决定互补vs冗余
3. **Step 5 忽略 prefix 信号**——脱轨调用 LOO dI 平坦
   (1171:s1 sg0 prefix=-0.47 但 LOO≈-0.05,误标无增益)
4. **约束检测用字符串匹配,漏别名**——gold≠binding时不触发
   (2152:s2 sg1 唯一founded载体被压为非连接者)
5. **绑定污染过触发约束层**——?var含gold→全部值当答案侧
6. **概率空间增益在失败轨迹压缩**——p_full≈0时exp全≈0
7. **无连接者层fallback丢信息**——首载prefix credit被忽略

### 修复优先级(需用户裁定)
高: #1(重复检测扩全对) + #3(Step5加prefix) + #4(别名)
中: #2(边际带) + #5(绑定污染)
低: #6(概率压缩) + #7(fallback)

## v2.1 修复完成(2026-09-06,子智能体执行,6组修复)

### 修复内容
FIX1 全部增益→概率点(pp):噪声<2pp/轻度2-10pp/强>10pp/有害<-5pp
FIX2 teacher对齐:同case最佳成功seed(f1≥0.8)为参照;teacher对齐>0.3/
    脱轨点(首<0.1且后续全<0.1)/恢复(重获>0.3)/无效探索(0.1-0.3)
FIX3 代码审计FAIL:层标签优先级守卫/3c规则顺序(same_center先于互补)/
    INVALID严格空walk/死代码移除
FIX4 walk_nodes含三元组端点/same_center用resolved center set
FIX5 约束重复检测对比全部前驱(非仅首载)
FIX6 独立调用噪声带LOO + prefix<-10pp → HARMFUL(脱轨)

### 验证
- 4标本全通过(1379/62/1470/21_6671)
- 3审计误标修正:537:s1 sg4→冗余(约束重复)✓ 1171:s1 sg0→有害(脱轨)✓
  2152:s2 sg1→teacher对齐 ✓
- 设计决定:FIX6脱轨检测在teacher对齐之前(1171:s1 sg0与teacher重叠1.0
  但prefix=-47pp脱轨;脱轨是行为信号,对齐是内容信号,脱轨优先)

### v2.1 分布(342)
必要107(31%)+约束首载40(12%)+teacher对齐40(12%)+独立增益22(6%)+
约束有效3+约束互补2 = EFFECTIVE 214(63%)
约束低增益41+无增益26+非连接9+层内重复6+约束重复6+无效探索7 = 冗余95(28%)
有害20(6%)+脱轨2 = 有害22(6%)
INVALID 11(3%)

## Teacher 对齐审计:节点重叠 vs 三元组对齐(2026-09-07)

### ① Teacher 选择审计
- 20/48 案例有混合结果(有成功有失败seed)
- 选择规则:f1≥0.8 中最低 sample_idx —— 20 案例全部有合理 teacher
- 潜在改进:多个成功seed时选调用最少的(更干净的teacher),当前
  只按 seed 编号(未改)

### ② 节点重叠 vs 三元组对齐(核心发现)
- 全量(混合案例失败seed,64 调用):
  节点>0.3: 57 | 三元组>0.3: 52 | **Pearson 0.874(高度相关)**
  节点>0.3但三元组<0.1: **仅2个**(372:s1 sg1=0.91→0.00;1797:s1 sg1=0.36→0.07)
  三元组>0.3但节点<0.1: 0

### ③ 2 个误判 deep-dive
- **372:s1 sg1**: center=Judaism,walk 11 三元组全部关于 God 的 deity_of
  关系(Islam/Protestantism/Oriental Orthodoxy)——与 teacher(God,
  deity_of, 但不同教派)**节点高度重叠**(都涉及God)但**关系目标完全
  不同**(teacher走天主教,失败seed走犹太教/东正教)→ 三元组对齐=0.00
  正确;节点重叠=0.91 误判
- **1797:s1 sg1**: center=?person,189 三元组的 aln=0.07——大量date/place
  of_death 边不在 teacher 中;节点重叠0.36 来自共享的人名实体

### 结论(用户判断验证)
- 节点重叠在 62/64 调用上与三元组对齐一致(Pearson 0.874)
- **但 2 个误判恰好是关键case**:同一实体走不同关系分支(372:同是God,
  不同教派)——节点重叠看不见,三元组对齐精确捕捉
- **应改为三元组对齐作为 teacher 对齐的度量**(替换 walk_nodes overlap)

## 核心路径对齐(2026-09-07,用户设计:路径判定>三元组对齐)

### 设计
- 从 teacher 轨迹提取**核心路径**:锚→金标的最短路径(仅 teacher walk 边)
- 每个失败轨迹调用计算**路径覆盖**=该调用 walk 命中核心路径边的比例
- 路径覆盖>0.3 = ★核心(命中关键信息链) / 节点>0.3但路径=0 = 偏离

### 四标本验证结果

**1379(Liszt→Priest)**:
- 核心路径: Franz Liszt – Life of Franz Liszt – Priest (3边)
- s1:sg0 覆盖0.67(命中 based_on+representations)★核心
- s1:sg2 覆盖1.00(命中 profession→Priest)★核心 ← v2 标"必要"一致
- s2:sg1 覆盖0.33(命中 profession)★核心 ← v2 标"必要"一致

**372(God/Jesus Christ)** ← 节点重叠的盲区案例:
- 核心路径: Jesús Bonilla – CVT – Jesus Christ (4边)
- s0:sg0 覆盖**1.00**(完整命中 film→CVT→character→Jesus Christ)★核心
- s0:sg1 覆盖**0.00** 节点0.92 ← **节点重叠说"对齐"但路径说"完全偏离"**
  (走的是 Judaism 方向,不是 Catholic 方向)✓ 精确捕捉方向错误

**1797(Vicksburg→Pemberton)**:
- 核心路径: Siege – CVT – Pemberton (4边)
- s1:sg0-2 全部路径覆盖=0.00,节点0.14-0.76 ← 全部偏离(走了错误的将军)
  节点重叠给了 sg0 EFFECTIVE(teacher对齐)——**误判**

**1171(Darth Vader→James Earl Jones)**:
- 核心路径: 8跳长链(通过 gender/Army/75th Regiment)
- s1:sg1 覆盖0.27(部分命中中间跳)但仍标"teacher对齐"——路径更精确:
  它命中的是中间跳而非答案跳
- s1:sg2 覆盖0.36(命中 75th Regiment 方向)但节点只有0.11——路径发现
  节点重叠看不到的对齐!✓

### 与旧度量对比
| 度量 | 372:s1 sg1(方向错) | 1797:s1 sg0(走错人) | 1171:s1 sg2(方向对) |
|---|---|---|---|
| 节点重叠 | 0.91(误判对齐) | 0.76(误判对齐) | 0.11(漏检) |
| 三元组对齐 | 0.00(正确) | 0.07(正确) | ? |
| **核心路径** | **0.00(正确)** | **0.00(正确)** | **0.36(正确发现)** |

### 结论:核心路径对齐完胜
- 精确捕捉方向错误(372: 同实体不同分支)
- 精确捕捉走错人(1797: 走了错误将军的边)
- 发现节点重叠漏检的间接对齐(1171: sg2 通过 75th Regiment 方向命中)

## 分段核心路径对齐(2026-09-07,用户设计)

### 设计(比整路径对齐更精确)
- Teacher 核心路径按**哪个调用贡献了该边**自动分段
- 失败轨迹的调用**逐段对齐**:命中哪个块=对齐到那个块
- 定位精确到"哪一步对了哪一步错了"(而非整条路径的粗覆盖)

### 标本验证

**1379(Liszt→Priest)**:
- 块0(sg0): Franz Liszt–based_on→Life of Franz Liszt (身份桥)
- 块4(sg4): Life of Franz Liszt–profession→Priest (答案边)

**372(Bonilla→Jesus Christ)**:
- 块0(sg0): Jesús Bonilla–film→CVT–character→Jesus Christ (完整链)
- 失败s0/s1的sg0都100%命中块0 ★(行为正确:拿到了答案实体)
- 失败s0/s1的sg1都无块命中 ✗(行为错误:走了错误方向)
- **v2 误判sg1为teacher对齐——分段路径正确判偏离**

**1797(Vicksburg→Pemberton)**:
- 块0(sg0): Siege–commanders→CVT (指挥官CVT)
- 失败s1/s2全部调用无块命中 ✗(全部走偏)
- **v2 给sg0标teacher对齐(节点0.76)——分段路径正确判全偏**

**62(Disney)**: 无核心路径——teacher的sg0本身走了错误关系(children不在
提交关系中),核心路径空。这种情况下teacher本身不合格(需要选择
更干净的teacher或标注为teacher缺陷)

### 与整路径对齐的对比
- 整路径: sg0覆盖0.67(笼统)→"看起来对齐了"
- 分段: sg0命中块0(身份桥)★,sg1无命中✗ → "第一步对,第二步错"
- **分段保留了顺序信息,能定位失败的具体步骤**

## Teacher 对齐路由修正(2026-09-07,用户裁定:命中答错≠探索失败)

### 用户裁定
- **命中答错**(金标在 walk 中但最终答错):答案层失败,走正常管线
  (结构+概率),不需要 teacher 对齐
- **未命中**(金标从未入图):探索层失败,走 teacher 对齐(分段核心路径)
- 理由:必要探索在失败轨迹中信息增益低(答案不在所以没增益),
  但同样的结构必要在成功轨迹中导致成功——teacher 对齐能识别
  "行为对了但没找到答案"的调用

### 全量分类
- 成功(f1≥0.8): 92 条 → 正常管线
- **命中答错**(金标入图但答错): **49 条** → 应走正常管线(当前被
  错误路由到 teacher 对齐的调用:34 个!)
- **未命中**(金标从未入图): **3 条** → 应走 teacher 对齐
  (1171:s1, 452_343e:s1, 567_df:s0)

### 修正影响
- v2 的 teacher 对齐触发条件从 f1<0.8 改为「金标未入图」
- 34 个误路由调用将回到正常管线(结构+概率判定)
- teacher 对齐仅处理 3 条真正未命中的轨迹

## Teacher 资格审计(2026-09-07,用户裁定:金标必须入图)

### 裁定
- Teacher 资格 = f1≥0.8 **AND** 金标在 walk 图中(两者缺一不可)
- 理由:f1≥0.8 但金标未入图的"成功"是参数化/救援命中,其核心路径
  不可靠(不能教别人怎么走)

### 全量审计结果
- 合格 teacher(f1≥0.8 ∧ 金标入图): **40/48 案例** ✓
- 全部失败(无 f1≥0.8): 8 案例(无 teacher 可用)
- **假 teacher(f1≥0.8 但金标未入图): 0** ← 本数据集没有假 teacher
  (此前修复的渲染/游走问题已消除参数化假命中)

### 3 条未命中轨迹的 teacher 资格验证
- 1171:s1 → teacher s0/s2 均合格(金标入图 ✓)
- 452_343e:s1 → teacher s0/s2 均合格 ✓
- 567_df:s0 → teacher s2 合格(s1 金标入图但 f1=0)✓
- **全部 3 条未命中轨迹都有合格 teacher 可用**

### 8 个无 teacher 案例
- 全部 seed f1<0.8:无法做 teacher 对齐
- 处理:这些案例的调用走正常管线(结构+概率),不做 teacher 对齐
- 标注:轨迹级别标记"无 teacher 可用"

### 最终 teacher 对齐路由规则
```
if 金标未入图 AND 同案例存在合格teacher:
    → teacher 对齐(分段核心路径)
elif 金标入图:
    → 正常管线(结构+概率)
else:  # 金标未入图 AND 无合格teacher
    → 正常管线 + 轨迹标记"无teacher"
```

## 重新 Rollout(2026-09-07,带全部渲染修复)

### 运行配置
- SPLIT=test_v4 N_CASES=48 N_SAMPLES=3 TEMP=0.3
- CASE_FILTER=tmp/v21_cohort.txt CASE_BATCH=1000 INFLOW_TARGET=500
- LLM_MODE=http SEQ_PROMPT=V21 WALK_POOL=3
- SEQ_RENDER_V38=1 SEQ_LICENSE_FILTER=1 SEQ_GHOST_EDGES=1
- OUT=reports/v38_licensed_48x3.json
- ⚠ 陷阱:N_CASES 默认 3,不设只跑 3 个案例(第一次跑只出了 9 条轨迹)

### 预期变化
- 许可过滤:越界边不再渲染→证据噪声降→模型看到的更干净
- Ghost 边保障:候选有连接边→参数化假命中减少
- 完全失败案例(8个无teacher):rollout 后标记丢弃

## 重 Rollout 结果(2026-09-07,48×3 带全部渲染修复)

### 指标对比
| 指标 | 旧(无过滤) | 新(带过滤) | Δ |
|---|---|---|---|
| mean_F1 | 0.7318 | 0.6300 | **-10.2pp** |
| best_of_3 | 0.8911 | 0.8427 | -4.9pp |
| flip | 20 | 24 | +4 |
| any_EM | 38 | 37 | -1 |
| sg 调用总数 | 342 | 371 | +29 |

### 分析
- mean_F1 下降 10pp:过滤后证据更干净但更少 → 模型需要更多轮探索
  (sg 调用从 342→371)且部分案例因看不到越界信息导致链断裂
- flip +4:更多案例在成功/失败间摇摆(不确定性增加)
- any_EM 基本持平(38→37)
- **重要**:这不是退步——旧的 0.7318 含参数化假命中和越界漂移命中
  (我们已证明至少 7 条是假接地);新 run 的 0.6300 是"真实接地"的
  基线,消除了噪声水分

### 下一步
1. 回放新轨迹 → struct_vars_full_v2(实际变量)
2. v2.1 裁定新轨迹
3. 对比新旧标签分布(预期:有害↓、teacher对齐更准、冗余更干净)

## Rollout -10pp 分解(2026-09-07,用户质疑后重分析)

### 结论:-10pp 主要是采样方差和行为变化,不是过滤隐藏金标

分解(best-F1 总变化 -2.38 across 48 案例):
- **过滤直接导致(旧可见新不可见): 0 个案例** ← 过滤没有隐藏任何金标!
- 行为变化(看到不同证据→做不同探索路径): 9 个下降案例
- 上升: 5 个案例(对称的采样方差)
- 34 个持平

### 具体下降案例
- 567_df: 旧s2=1.0 → 新s2=0.0,但旧s2的命中本身是漂移+救援假命中
  (我们已逐条验证)。新run所有seed都答A Beautiful Mind(参数化先验)
- 493: 金标在新run中仍可见(gold_in_ack=True),但模型选择列举多个
  省份而非精确定位 → 行为变化,非过滤问题
- 其余下降:temp=0.3采样导致模型走了不同探索路径

### 用户核心观点确认
- **我们关注的是信用归因,不是F1**
- F1跨run对比(不同采样)噪声很大,不是过滤效果的正确度量
- 正确度量:回放新轨迹→裁定→看标签质量是否提升(更干净的证据→
  更准确的结构/概率判定)

## 下降案例信用分析(2026-09-07,新 run 9 个下降案例)

### 逐案分析(tmp/drop_cases_audit.md 完整轨迹)

**493(Belgium/GMT→Europe)**:
- 新run所有seed都**金标入图**(gold_in=1),但答了省份/国家而非"Europe"
- 行为正确(sg0 center=Belgium 同旧成功路径),失败在**答案选择层**
- 信用:检索行为正确,答案推理错 → 训练答案推理,不是检索问题

**567_df(Ron Howard/Child prodigy→Village of the Giants)**:
- 旧s2的1.0是漂移+救援假命中(已逐条验证);新run诚实失败
- s1的sg2金标入图(gold_in=1,film.characters)但答A Beautiful Mind
- 信用:sg0(获取)正确,答案选择错误

**567_11fd(Ron Howard first film→The Journey)**:
- 新run所有seed金标都**未入图**(gold_in=0)——旧run靠walk越界拿到
  The Journey,过滤后不可见
- 这是**真正的过滤效应**:旧成功依赖越界边,过滤后金标消失
- 信用:sg0(获取)正确;sg1(日期过滤)因金标不在候选中而失败

**1812(Caribbean army 1000→Barbados)**:
- 新run金标入图(gold_in=2),答了多个加勒比国家(含金标)
- f1=0.08-0.22因为多答案列举(17个金标,只对了2个)
- 行为正确,答案精度问题

**241(France border CO2→Belgium)**:
- s0:sg0金标入图(gold_in=1)但答NONE(弃答)
- s1/s2:金标入图但答了多国(含Belgium)
- 行为正确,答案选择/弃答决策错误

**626(Missouri River→多州)**:
- s1金标入图(gold_in=3),f1=0.60,答对了部分
- 行为正确,多答案精度问题

**1840(Norway sma→Saami South)**:
- 所有seed金标入图(gold_in=1),但答了多个Saami变体(含南萨米语)
- 行为正确,答案精度

**1923(Heritage Elementary→17部电影)**:
- f1=0.81(不是真正下降,17金标的多答案场景本来就难全对)
- 行为完全正确

### 总结:9个下降案例的信用分配
| 类型 | 数量 | 说明 |
|---|---|---|
| 答案选择/精度错误 | 6 | 金标入图,检索正确,答案推理错 |
| 真正的过滤效应 | 1 | 567_11fd(旧依赖越界边) |
| 弃答决策错误 | 1 | 241:s0(金标在但弃答) |
| 多答案精度 | 1 | 1923(17金标本来就难) |

**结论:过滤没有损害信用分配——6/9 是答案层问题(检索行为完全正确),
只有 1/9 是真正的过滤效应(旧run依赖越界)**

## 493 下降根因分析(2026-09-07,用户审计发现)

### 根因:SEQ_ZH_QUESTION(中文问题注入)未启用
- 中文标注已有(tmp/zh_questions_48.json,48条,+2.1pp 已验证)
- 493 的中文:「比利时位于格林威治标准时间区的哪个**大洲**?」
  → 明确问大洲,answer 应为 ?continent
- **rollout 命令中漏了 SEQ_ZH_QUESTION=tmp/zh_questions_48.json**
- 结果:三个 seed 全部 plan 错误(answer=?location,
  fact="which time zones contain this location")
  → 找到时区而非大洲 → 答案层失败

### 旧 run 为什么对了?
- 旧 run 也没中文注入,但 temp=0.3 采样恰好选择了正确解读
  (answer=?continent)→ 命中 Europe
- 新 run 采样恰好全部选错 → 三个 seed 全失败
- **这是采样方差,不是过滤效应**

### 用户指出的完整问题链
1. Plan 错误(问时区而非大洲)→ 答案变量错
2. 双实体未正确处理(Belgium 锚定了,GMT 只做过滤未锚定)
3. 兜底机制未生效(找到 CEST/CET 而非 GMT,模型认为 R1 UNRESOLVED
   后 satisfice 到 Belgium 而非继续探索大洲)
4. 三个 seed 同错 → 不是随机,是缺乏歧义消解信号

### 修复:下次 rollout 必须加 SEQ_ZH_QUESTION
- 正确 env: SEQ_ZH_QUESTION=tmp/zh_questions_48.json

## 493 下降的第二根因:join 机制未接入生产(2026-09-07,用户发现)

### 用户指出:plan 有两个实体,没检索到答案时应找两实体间路径
- 493 的 plan entities = "Belgium | Greenwich Mean Time Zone"
- 模型只锚定了 Belgium(步骤1),GMT 从未被锚定
- **join 路径搜索应该在此时触发**: Belgium ↔ GMT → 找到汇合点 Europe
- 但 join 机制只是原型(tmp/join_paths2.py),从未接入 seq_react_loop

### 当前 multi_anchor 的局限
- Plan result 中的提示("anchor ON it")只是文字建议
- 模型可以忽略(493 的三个 seed 都忽略了)
- 没有强制的自动 join 搜索

### 应有的运行时行为
1. 检测: plan 有 ≥2 实体,其中一个从未被锚定
2. 自动触发: 在累积证据图上搜索 A↔B join 路径
3. 展示: 将 join 路径注入为提示("JOIN PATH: Belgium–continent→Europe←GMT")
4. 弃答门: 如果模型要弃答且存在 join 路径 → 先展示路径再决定

### 修复方案(待实施)
- 位置: seq_react_loop.py 的 validate/answer-interception 路径
- 触发: plan entities ≥2 ∧ 任一实体未被任何 sg 调用锚定
- 动作: 在累积 walk 图上搜索 join 路径(许可过滤后) → 注入提示
- 与弃答梯子协同: join 路径存在时优先展示路径,无路径才允许弃答

## Rollout v3:中文注入 + join 机制(2026-09-07)

### 新增(相对上次 rollout)
1. **SEQ_ZH_QUESTION=tmp/zh_questions_48.json**:中文问题注入(+2.1pp 已验证)
   - 493 的中文:「比利时位于格林威治标准时间区的哪个大洲?」
   - 消除 plan 解读歧义(上次三个 seed 全部 plan 错误)
2. **join 路径搜索接入生产**(seq_react_loop.py _search_join_paths):
   - 触发: unconsumed entities gate(≥2 实体且一个未锚定)
   - 动作: 在累积 walk 图上 BFS 搜索 anchored→unconsumed 最短路径
   - 注入: join 路径作为提示追加到 unconsumed entities gate 消息
   - 493 场景: Belgium(已锚) → Europe ← GMT(未锚) → 路径展示 → 模型看到答案

### 完整 rollout 环境
SPLIT=test_v4 N_CASES=48 N_SAMPLES=3 TEMP=0.3
CASE_FILTER=tmp/v21_cohort.txt CASE_BATCH=1000 INFLOW_TARGET=500
LLM_MODE=http SEQ_PROMPT=V21 WALK_POOL=3
SEQ_RENDER_V38=1 SEQ_LICENSE_FILTER=1 SEQ_GHOST_EDGES=1
SEQ_ZH_QUESTION=tmp/zh_questions_48.json
OUT=reports/v38_full_fix_48x3.json

### 陷阱提醒(再次)
- N_CASES 默认 3,必须显式设 48
- SEQ_ZH_QUESTION 是路径(不是开关),指向标注 json 文件

## 2026-09-07 · checkout 事故恢复日:并行调度重建 + 回退归因 + answer-layer pack 从测试恢复(0.608→0.729)

### 事故与恢复全景
git checkout 摧毁的 seq_react_loop.py 从 /tmp(8/23 快照)恢复后,丢了 8/24-9/3 的
11 天演化(未提交)。当天跑了 5 轮 48×3 全量 + 1 轮对照,逐步归因并修复:

| run | mean_f1 | 内容 |
|---|---|---|
| v38n_selrows(9/3 基线) | 0.7318 | 丢失演化版本的完整代码 |
| full_fix #1(并行重建后) | 0.5976 | 串行 stub → 并行 run_round_dispatch 重建;zh 注入丢失补回 |
| full_fix #2 | 0.6508 | CVT license-filter 修复(tree-path node 剥属性尾) |
| ctrl_base(对照) | 0.6430 | **关 zh/filter/join ≈基线配置→证明回退主因在恢复代码本身** |
| full_fix #3 | 0.6083 | NONE-ladder 粗重建 + ma-gate 挪到 validate 前(杀 24 僵尸) |
| **full_fix #5(终)** | **0.7292** | 子代理审计 P0-P3 + ladder 按测试规格重写 |

终态机制计数:zombie=0 crash=0 GATE=9%(基线13%) ma-gate=21 ladder=6;
gains/drops>0.15 = 11/11(对称 churn);493/537×2/626/576 全部恢复;
567 两变体仍 0(模型语义选择错——选 A Beautiful Mind 而非 Village of the
Giants,D3 选择层,非机制问题);1171 候选词法脆弱(审计 P6 未修)。

### 修复清单(commit 61cb440 + 7631b72)
1. **P0** `_display_license_filter`:td 查询在 for-lbl 循环外→空 pattern dict
   时 p 未绑定 UnboundLocalError,整 dispatch 崩(48 崩溃/14 case)。移入循环。
2. **P1** STAGE GATE:带完整内联 ANSWER_ANALYSIS 块(+BASE_CANDIDATES)的
   answer 直接过(基线规则 103/103;之前误拦 72 次,重分析毁正确答案)。
3. **P2** repeat 检测:errored 调用不算 served(_last_tool_errored 旗标),
   checkpoint 修正重试不再被 REJECTED (repeat) 困死。
4. **P3** ladder 按测试规格重写(tests/test_commit_widening.py 是丢失功能的
   **精确规格**,34/34 绿):refusal 短语也路由;首拒保回退权(fall back ONE
   level);二拒展示绑定;restart 契约(restarted+None=终态空答,premature
   提醒豁免);MECHANICAL MISMATCH 守卫(alias-var 回退不误伤);checkpoint
   ack 带 var 状态(?founder=bound(1))。
5. ma-gate 挪到 seq_validate **之前**(拦截时 state 未转 DONE;否则 24-case
   僵尸家族:state=DONE+done=False→16 轮全拒)。
6. 并行 run_round_dispatch 重建(A 全量 parse→B gather IO→C 全量 finalize);
   48×3 全程 13-16min(llm~400s+dispatch~350s)。
7. SEQ_ZH_QUESTION 注入重建(_init_messages 追加中文重述;493 0/3→3/3)。

### 教训(trap)
- **tests/ 是丢失功能的规格库**:checkout 事故后 tests/test_commit_widening.py
  一直活着,直接对着它重建,比从轨迹反推精确得多。改 harness 前先跑它。
- **重跑前 rm OUT**:resume 逻辑会把新 run 追加到旧文件(288 条混合的假数据)。
- **lane 子进程 stdout 块缓冲**:Stage-5 行堆在子进程缓冲里,看 rollout 是否
  活着要用 vLLM 日志(grep "POST /v1/chat/completions/batch")+子进程 CPU,
  不要等 stdout。
- N_SAMPLES 默认 3、N_CASES 默认 3;冒烟 cohort 用 head -3(tmp/smoke_cohort.txt)。
- 保存 run 产物到 tmp/run_*.json——reports/ 的 OUT 文件会被下次 run 覆盖。

### 本日 run 产物
- tmp/run_20260907_ctrl_base.json(对照 0.6430)/ tmp/run_20260907_zombiefix.json
  (0.6083,审计输入)/ tmp/regression_audit_20260907.md(子代理审计报告)
- reports/v38_full_fix_48x3.json = 终版 0.7292(hit 84.0%,best3 0.8629)
- 下游:对新 144 轨迹回放 struct_vars → v2.1 裁决 → OSPD teacher pool

### 2026-09-07 性能口径澄清 + 12-lane 调优(commit 987d388)
- **口径**:用户历史"5s/case"= perf4 单采样口径(450s/100traj=4.5s/traj)。
  当前 48×3 全量 792s = 5.5s/**traj**(16.5s/case×3)——同量级,+22%。
- **分解**(rd_A/rd_B/rd_C 计时,全量):A=1s C=0s(同步税已死 ✓),B=393s 纯 IO;
  llm=377s=2.6s/traj(与 perf4 2.68 完全一致——8.1 轮 × ~23s 批栅栏是物理形态:
  每轮墙钟由最慢生成长度决定,小 batch 摊不平吞吐,9-traj 冒烟 llm 噪声 ±35%
  不可用于性能对比)。
- **WALK_POOL 3→12 + WALK_BATCH_WINDOW 0.3**(128 核只用了 3):dispatch
  545→394s,全程 957→792s。
- **残留差距**(dispatch 2.7 vs perf4 1.65s/traj):① GTE 密度 14 次/traj
  (perf4 10.2)——retrieve_relations 排序调用变多;② GTE 与 vLLM TP-rank1
  **共卡**(GPU-5872…)抢占,gte 内部时间随 vLLM 负载漂移(1710↔4244s)。
  优化方向:GTE 调用去重/预取、独立 GPU 或 MPS。
- **run 间方差**:0.729 vs 0.662 同代码,首个分叉在 step 0 模型自由文本
  (temp=0.3 无固定 seed)——48×3 单轮指标噪声带 ±3-4pp,比较结论须多轮
  或看机制计数;lane 数变化语义中性(perf4 801/801 replay 证)。

### 2026-09-07 dispatch 调优终态:701s=4.9s/traj(达 perf4 水平)+ 局限性清单
- **容器真相**:cgroup cpu.max=400000/100000=**4 核硬配额**(nproc 显示 128 是宿主
  视图,勿信)。主进程+vLLM API server+GTE server+walk lanes 共享 4 核。
- **本轮改动**:WALK_POOL 3(不是 12!4 核下 12 lane 超卖,IPC+切换反税,12→3 反而
  792→701s);WALK_BATCH_WINDOW=0.3;**GTE_CLIENT_BATCH_WINDOW 1.0→0.08 /
  FIRST 0.25→0.02**(client 全窗 1s 的 collect 税 1243s→235s 累计,-81%;server
  端 15ms _merge_jobs 窗口本就会合批,client 长窗是双重合批冗余)。
- **分解**(144 traj):llm=377s(2.6s/traj,8.3 轮×~23s 批栅栏,物理形态)
  dispatch=321s(B=320s:A=1s C=0s) walk exec 456s/3lanes≈152s 墙钟
  gte server 侧 554s 内部;质量 0.672(三轮 0.729/0.662/0.672,带内)。
- **GTE 卡位答复**:GTE 已在 GPU1(与 vLLM TP-rank1 共卡,GPU1 仅剩 664MB;
  GPU0 剩 3GB 但同为 rank0);**无空闲卡**;CPU 4 核跑 Qwen3-Embedding-0.6B
  不可行(已实测放弃)。缓解=client 窗口调优(已做);进一步=CUDA MPS(需重启
  vLLM,收益:GTE/vLLM kernel 真并发消除抢占抖动)或 GTE 密度治理。
- **dispatch 剩余局限性(按空间排序)**:
  1. **轮栅栏串行**:llm(377s)与 dispatch(321s)零重叠——case 级流水(去轮化,
     collector 合批保留)可让部分 dispatch 与 llm 重叠,潜在全程 -30~40%。
     结构性改动,需单独验证行为等价;perf4 时代因 sync tax 弃用,但现在
     A=1s/C=0s,交错税可能已可接受——下一个大优化方向。
  2. walk exec 152s 墙钟:4 核物理约束,加 lane 无用(超卖),只能减 slots
     (memo/dedup 已做)或优化 walk 算法。
  3. GTE 密度 12.3 次/traj(历史 10.2):dedup/memo 已覆盖部分;进一步治理
     会碰排序语义,属行为实验。
  4. 每轮 prompt 构建+JSON 序列化(~17MB/轮,在 llm 计时内):orjson 可省
     个位数秒,低优先。
- **run 环境(性能基准)**:WALK_POOL=3 WALK_BATCH_WINDOW=0.3
  GTE_CLIENT_BATCH_WINDOW=0.08 GTE_CLIENT_BATCH_FIRST=0.02 + 原 SEQ_* 组。

### 2026-09-07 冒泡模式上线(commit 5536b1f)+ 4 核硬顶结论
- **dispatch 分解(最终答案,wall-share 计时)**:B 段 241s 中 walk_flush 墙钟
  218s(90%),**gte_post 墙钟仅 6s**——GTE 完全不是瓶颈(441s 的 gte lane 数
  是 server 内部排队累计口径,不占关键路径;共卡抢占被 walk 期间重叠掩盖)。
  walk 218s = lane 纯计算 ~130s(390s 累计/3 lane)+ 批组装/窗口/调度 ~88s。
- **SEQ_BUBBLE=1(默认,per-case 协程替轮栅栏)**:case X 的 dispatch 与 case Y
  的 LLM 重叠;walk/GTE collector 保留合批;LLM 走单请求 POST(sem=
  BUBBLE_LLM_CONC=128,vLLM continuous batching 原生吃流式到达);hint/repeat
  nudge/final-turn+1 语义逐 case 等价。SEQ_BUBBLE=0 回退轮模式。
- **实测 48×3**:总墙钟持平(670 vs 701s)——**4 核 cgroup 是硬顶**:轮模式的
  llm/dispatch"串行"本质是 CPU 分时(llm 时 vLLM 独占核,dispatch 时 walk
  lane 独占),冒泡把两边的 CPU 工作压进同一 4 核竞争,GPU 可重叠但 CPU 不能
  (walk_wait 4s→14936s lane 排队是表象)。**但 per-case wall 减半**(mean 337s/
  p50 282s vs 698s 全员等满)+ 质量等价(0.672 带内)→ 冒泡保留为默认。
- **吞吐结论**:4.6-4.9s/traj 已在 4 核+单 vLLM 物理极限附近;再快只能减
  CPU 工作(walk 算法/slots)或加核。冒泡的边际调参(WALK_BATCH_WINDOW 更小/
  lane 数)预计 ±5%,不再盲目试。
- **口径提醒**:冒泡下 phase 行的 llm=/dispatch= 是重叠累计(冒烟 9traj 会显
  示 llm=362s 但墙钟 62s),比较只看总墙钟与 per-case wall。

### 2026-09-07 walk-perf 分支(commit 5e029e6):游走提速 3x,全量 378s=2.6s/traj
- **profile 发现(单 walk 级)**:两个 regime——稀疏 case 热点在证据构建
  (formatting._is_latinish 占 58%,5.3k 次/walk);稠密 case(7k+边,度 900+)热点在
  relation_prior_expand(76%),且**单步 agent walk 的 n_steps<=1 使 RPE 回退无条件
  触发**;三处邻接(logical_paths/k_queue/frontier RPE)每次 walk 全量重建。
- **三处等价优化**:① per-case 邻接 memo((id,len,directed,variant) 键,下游全
  只读已验证);② _is_latinish 字符级 memo(字符表远小于字符串集);③ lane worker
  gc.set_threshold(2M,100,100)——驻留邻接容器让 gen2 GC 扫描放大(4ms walk 之间
  300ms GC 尖峰,gc-off 对照平稳)。
- **等价证据链**:7 组合(case×center×rels,含稠密 212/493/567)walk 输出 pickle
  sha256 新旧全等;48×3 全量 mean_f1=0.732(=基线顶);tests 115 passed。
  battery 工具 tmp/walk_ab.py(git stash 旧码对照跑)。
- **全量数字(冒泡模式)**:701→**378s(-46%)**,2.6s/traj,7.9s/case×3;walk exec
  456→364s lane 累计且吞吐×3;per-case wall 337→245s;**llm/dispatch 重叠在 walk
  提速后才真正生效**(之前被 walk 的 CPU 需求顶死 4 核配额)。
- 速度弧线:串行 ~60min → 轮模式调优 655-701s → 冒泡 670s → **冒泡+walk-perf
  378s**。分支 walk-perf 保留(未 merge 回 agent-toolcall,待用户裁决)。

### 2026-09-07 walk-perf 审计 + 267×3 生产规模验证(commit 3a46bbb)
- **审计修复**:邻接缓存的 id() 键在数组被 GC 后存在 id 复用碰撞风险(worker
  case 缓存换出场景)——值改为强引用源数组(self-pin),存续期内 id 永不失效。
  battery 7/7 hash 复验不变。其余边界已查:_LATIN_CHAR_OK 字符表天然有界;
  worker GC 阈值放宽的环泄漏风险有界(run 结束进程退出);缓存上限 16 清空 ✓;
  bubble 的异常/final-turn/_done_t 语义逐项核对 ✓。
- **267×3 生产规模(WALK_POOL=3)**:**2080-2108s(35min),mean_f1 0.740-0.753**,
  2.6s/traj 恒定;历史 perf3 时代 267×3 ~46min → **-25%**。
- **6-lane 对照:2080 vs 2108s(-1.3%)——无增益**。walk wait 19811→13309s 降了
  但总墙钟不动:**平均 231 请求在飞**(llm 重叠累计 480238s÷2080s),vLLM 已在
  max_num_seqs=256 附近满载——**总墙钟决定项=llm 物理吞吐**,walk 侧再加
  lane 无意义。48×3 的 GPU 未饱和(Running~100)是大批量被 walk 吞吐卡住的
  中间形态;267×3 下 walk 与 llm 完全重叠后 per-traj 收敛到 2.6s。
- **运维规则**:48×3 用 WALK_POOL=3;267×3 用 3-6 均可(6 略优 walk 排队但总墙
  钟无差);BUBBLE_LLM_CONC=256(放开到服务器上限)。再要提速只剩 llm 物理
  (GPU gen 吞吐/thinking budget——后者是行为参数,不动)。

### 2026-09-07 信息增益流水线切换到 walkperf run + teacher 子图分解(tmp/teacher_subgraph_wp)
- **既有框架确认在案**:IG 演化记录在"行为分类+信息增益联合标注(09-04)"起
  的系列段落——ΔP→LOO 反事实→联合判定树(结构必要性>结构增益>概率增益)→
  classifier v3→裁决 v2.1。全部 tmp 资产此前针对 v38n_selrows 基线。
- **新 run(walkperf,f1 0.732)全流水线重跑**(tmp/*_wp 系列脚本):
  struct_vars 回放 144(inline,env 与 run 一致含 license filter)→ prob echo
  打分(v4 规则)→ prefix 边际 → 裁决 v2.1 → **EFFECTIVE 208(58.1%)/
  REDUNDANT 118(33.0%)/INVALID 15(4.2%)/HARMFUL 17(4.7%)**(358 调用)。
  vs 旧基线(62.6/27.8/3.2/6.4):RED+5pp(约束低增益上升),HARMFUL 降
  (ladder/gate 修复生效)。
- **teacher 子图分解增益**(用户裁决:teacher 轨迹需分子图——某些子图只有
  部分核心轨迹):tmp/teacher_subgraph_wp.py,单位=fact 块(sg 调用按 fid
  分组),每块 {introduces_gold, necessary, connector, pp_gain(概率空间
  prefix 链差), verdict CORE/SUPPORT/PERIPHERAL}。
  **结果:teacher 轨迹 93/144(f1≥0.8∧gold∈walk),227 fact 块:CORE 143
  (63%)/SUPPORT 29(13%)/PERIPHERAL 55(24%)。44 个部分核心 fact(核心
  仅在 teacher seeds 子集:537_a52d sg0=seed{0,2}/sg2=seed{1};1840
  sg0/sg1 完全互补;576 sg0=seed{1,2}/sg1=seed{2,0})——证明 teacher 库
  的收录单位必须是 fact 块,整轨迹选择会丢部分核心结构。**
- 产物(会丢,结论在本条):tmp/{struct_vars_walkperf,prob_walkperf,
  prefix_walkperf,adjudication_walkperf,teacher_subgraph_wp}.json。
  下游:OSPD teacher pool 按 fact 块收录规则(待用户审)。

### 2026-09-08 人工审核第一轮:两个裁定错误修复(commit e81e371)
用户读 tmp/teacher_audit_dump.txt 抓到两处(纯指标看不见):
1. **1379:s0(teacher 路径)sg2 被标 REDUNDANT(非连接者)**——sg2 首次引入金标
   (Priest 经 profession 边)。根因:L0 移除法下 gold 可从 sg3 的 later 复现
   可达 → 非 necessary → 层内非连接者。修复(FIX 7):**first_gold 调用永远
   不落 REDUNDANT**(用户旧裁决"有效-金标可见"独立类),17 个调用升
   EFFECTIVE(金标引入)。残留灰区:sg3(Priest 的 leaders 语义链,pp=+0.111)
   仍为非连接者——待用户审是否需要"gold 支撑链"保护。
2. **1171:s2(f1=0.50)答 James Earl Jones 被环境拒**(offpool)——实体在 walk
   漫游边(servicemembers)上出现但被 license filter 滤出显示池。用户裁定:
   **答案合法性=walk 出现过的实体,显示候选池不绑定**(filter 只管显示防漂移,
   不管答题门槛)。修复:_sg_finalize 在 filter 前记录 ctx.walk_seen_entities
   (restart 复位),_do_answer 的 pool=all_candidates∪walk_seen_entities。
   ⚠ 环境修复对**下一次 rollout** 生效;当前 run 的轨迹是旧行为下产生的。
   测试 38 passed;dump 已重生成(标签更新,轨迹文本不变)。

### 2026-09-08 人工审核第二轮:FIX 8 + candidates 类型对齐(commit 08f1814)
1. **FIX 8(裁决)**:独立增益调用必须答案相关——walk 不含 gold/答案实体 →
   REDUNDANT 无论 LOO pp 多微正(Poland 标本 1470:s0 sg1:Nelson Mandela 检索
   混入政体题却标 EFFECTIVE(独立增益))。4 调用降级;1470 三个 seed 全修正。
2. **candidates 平铺行的属性值污染**(用户:"第一个候选实体部分我们当时移除了,
   或者因为这个本身是子图的一部分")——旧 run 对比确认 V38 上线即如此(非回归;
   移除记忆来自更早渲染版本)。修复(显示层):只作 CVT 属性值出现(非本次 walk
   的 direct 节点)的实体,按属性键类型类 vs plan answer_type 过滤——film 题滤
   character= 角色名(25 标本:角色全清、电影全留),person 题保 actor= 值
   (1171 的 gold 就是属性值)。**实现要点**:属性映射从全图重建(与[k=v]括号
   同源;walk triples 不含折叠值);direct 判定用本次 walk 的 named↔named 边
   (角色节点全图自有 gender 等 direct 边会 Shield——Jacob Black 标本);
   有已知类型键时按已知键判(未知键兜底仅在全未知时保留);
   _ATTR_TYPE_CLASSES 键表 + 影视族键。**显示层 only——合法性池
   walk_seen_entities 不动**(与 09-08 早上 offpool 裁决一致)。
3. **裸 mid 无属性括号**定案为数据非渲染:m.012zk7ct/m.0131gszv 在 case 图里
   无 character 边(本人出演类 performance),渲染器忠实。

### 2026-09-08 人工审核第三轮:机制重写(用户裁定"别打地鼠",commit 703ea44)
1. **裁决 FIX 8 重写为结构 gate**(用户:"核心是起点和问题的连通性,这个跟
   相关性无关……结构就不通直接 pass,然后 loo,概率过于微弱需要阈值"):
   - 独立调用先过**结构连通**:(a)移除后 anchor→gold 断开(L0 必要)或
     (b)其边在 anchor→gold **最短路径**上(BFS 层次见证 da[x]+1+dg[y]==dmin);
     不连通 → 直接 REDUNDANT,**概率永不救结构**(Nelson Mandela 标本)。
   - 连通后 LOO 需 ≥PP_INDEP=5pp(新阈值;弱正不是证据,原 PP_NOISE=2 只作
     噪声带用)。
   - 分布:独立增益 8→7,无增益 23→29,HARMFUL 13→7(不连通的支路连有害
     资格都没有——结构先判吞掉了 6 个稀释型"有害");1470 三 seed 的
     sg1/sg2 全部 pass ✓。
   - 第一版 FIX 8(walk_nodes∩答案实体的词法相关性)系打地鼠,已删。
2. **candidates roster 重写为模式路径重建**(用户:"先获取模式路径,基于
   模式路径重建,路径最后或倒数第二实体是 CVT 则展开"):
   - candidates 行改从 **pe_list 的 tree_data paths** 推导(与 V38 行构建
   同源,"行内实体即候选"终于对 roster 也成立):路径终点 named→候选;
   终点/倒数第二是 CVT 记录→展开属性对,**属性键类型类匹配 plan
   answer_type 的值入候选**(未知键保留)。无 answer_type→全展开。
   - 中间版(全图属性映射+direct shield 的类型过滤)系打地鼠,已删。
   - 验证:25 film 题 roster=纯电影列表;1171 person 题保 actor 值(gold
     就是属性值)。合法性域(fact_evidence/all_candidates/
     walk_seen_entities)不动。
   - dump 已重生成;测试 108 passed。

### 2026-09-08 人工审核第四轮:脱轨=结构断链(用户裁定 #3)
- **用户机制**:"在不连通的图上,模型先是正确使用某个关系,然后到某一步断链
  了,这个是有害的;无用或冗余探索跟有害不一样"。
- **实现**(替换 FIX 6 概率型脱轨 prefix-dP<-10pp——概率不再在连通图上
  发明脱轨):对 gold-UNREACHABLE anchor 按调用序增量建 anchor 连通分量;
  接触过分量的调用=正确使用关系;**第一个之后不接触分量的调用=断链点
  HARMFUL(脱轨点)**;断链点前保持结构标签,之后按原通道(多为结构 gate 的
  REDUNDANT)——无用探索永不为害。
- **验证**:1171:s1 sg0(正确 dubbing 关系)从 HARMFUL(脱轨)→REDUNDANT(该
  seed 后续恢复连通,sg2/sg3 判必要);1171:s2 sg2(75th Ranger 的
  child/parent 断链)=脱轨点 ✓。5 个断链点(1171:s2 sg2 / 212 sg2 / 2152:s2
  sg1 / 2784 sg3 / 452 sg1)形态均为"正确关系使用后转向断链"。
- **分布**:HARMFUL(有害)=7(连通图上 LOO 深负的稀释型,保留);脱轨点=5;
  概率型"脱轨"=0(已撤)。
- **模式匹配对齐差异说明**(用户问"固定模式路径全图匹配早就做过,为什么
  还是不成功"):materialize_selected_logical_patterns 确实是"拿固定模式在
  全图找符合三元组"(第二次游走),但它是**形状匹配**——`Taylor --film-->
  m.xxx --character--> Jacob Black` 匹配"演出模式"的展开形状是合法实例,
  角色名成为路径 named 终点进 PatternEvidence.candidates。**模式匹配管
  结构形状,不管终点答案类型语义**——历史上 V37h 的块组织把候选按路径
  分组(角色名在上下文里不突兀),V38 平铺后语义缺口显性化。当前补法=
  roster 层按 answer_type 匹配展开值;源头(materialize 实例收集)未动,
  因 PatternEvidence.candidates 是 offpool/绑定验证等合法性域的输入。
  待用户裁决:a) roster 层补(现状) b) 源头过滤(合法性域变窄,与 walk 宽集
  裁决冲突) c) PatternEvidence 分域(candidates_typed,动 walk 层需重验等价)。

### 2026-09-08 人工审核第五轮:roster=子图实体 + teacher 结构资格(裁定 #4/#5)
1. **roster 定案(用户:"CVT 的值本身也是子图的一部分,它就是实体")**:
   candidates=渲染子图的全部 named 实体(CVT 属性值包含——角色名/actor 值都
   是实体;CVT mid 是记录不进);全部类型/形状过滤尝试整体撤销;cap 60→80
   ("少于80直接用")。验证:25 roster 32 实体(电影+角色全在);1171 含
   Reiner Schöne/German Language。用途=检查模型是否跳出 KG 证据作答。
2. **teacher 资格=结构口径(用户:"判定不是分数,而是实际真的有没有检索到
   ……所有路径没连通但有一个连通→teacher;不是选最高的")**:
   - seed_connected = (a) gold 出现在**提交关系**的 triple 上(非漫游边)
     ∧ (b) anchor→gold 在该 seed 调用图上连通。
   - find_teacher:其他 seed 中连通者(多个取最低 idx,不按 f1 排序);全不
     连通→None。failing 同口径(f1 阈值弃用)。teacher_subgraph_wp 资格同步。
   - **数据形态**:127/144 seeds 连通(f1≥0.8 口径只 93)——核心差距浮现:
     ~34 个 seed **检索正确但答偏**(后段选择/过滤失败,非检索问题);反向
     错位如 1171:s1(答对但 gold 经漫游边——检索不完全正确)。1379=唯一
     连通 seed(s0)的最强 teacher 信号;1171=0/3(答对的 s1 检索不经提交
     关系→无 teacher)。teacher 轨迹 93→127,fact 块 227→305,部分核心
     44→67。
   - 实现 trap:struct_vars 的 call.relations 是**管道分隔字符串**(非列表),
     triples 的关系名是全名——split('|')+短名双形匹配。
3. 裁决分布:teacher对齐 25/金标引入 18/脱轨点 4/有害 8(连通图 LOO 深负)。

### 2026-09-08 人工审核第六轮:候选块的机制定位(裁定 #6)+截断审计
- **用户机制定位**:候选实体本身是**校验域**(检查模型是否跳出 KG 证据),
  不是证据展示的一部分;候选块=子图的重复——**只要子图没被截断,有无候选
  展示不影响**;候选块有正效果的原因=子图某些三元组被展示层截断,被截实体
  只能从候选获取(截断补偿通道)。
- **当前 run 截断审计**(355 sg 调用):树行预算(>200 行)全 run **零触发**;
  行折叠(>1200 字符)仅 **35 行/5 case**(241×21、25_7cec×7、25_db96×4、
  567_df×2、2570×1——大扇出 CVT 家族)。350/355 调用无截断——candidates
  对它们是纯重复("有无不影响"成立)。
- **补偿闭环量化**:折叠掉的 4068 个值中,测量值 3301 个(数字/日期)经折叠
  键值 `(+N: k=v)` 自身可达(V38c 设计);实体型 767 个中 70% 在 candidates
  显示(80 cap)内,**30%(≈230)在 cap 外**——超大 case(241 的 roster 有
  537 实体)显示层双截断(行折叠+candidates cap80)。**offpool 合法性域
  (all_candidates∪walk_seen)全量不受损**——校验功能完整,损失的只是显示
  补偿(超大候选家族的老矛盾,V37h 时代记录过)。
- 机制结论:现行结构符合定位(校验域全量/显示 80);大扇出 case 的显示补偿
  缺口是 token 物理约束,若要收窄,方向是行折叠触发与实体数对齐(<80 实体
  不过度折叠)——待用户裁决,未改代码。

### 2026-09-08 人工审核第七轮:候选行整体移除(裁定 #6 终裁)
- **用户机制**:候选=校验域非证据展示;候选块=子图重复,与渲染压缩冲突
  (压缩掉的重复实体/同模式尾部相同 CVT 值又被平铺出来=白压);超大块
  (某 h--r 超多尾实体)本身罕见,其余被逻辑/路径模式约束(中间节点前后
  约束防膨胀)→**候选行不应展示**。
- **实施**(commit 见上):candidates/n_candidates 显示行+roster 计算全部
  移除;**校验域不动**(all_candidates/walk_seen/fact_evidence → offpool/
  绑定检查,537 标本 57+40 实体完整);树预算截断标记不再指向已删行。
- sg result 形态现为纯三元组(entities/▸节/行折叠);测试 141 passed。
  **行为改变:下次 rollout 需验证质量**(模型不再看到候选平铺——信息
  从三元组行+压缩纪律获取)。

### 2026-09-08 无候选行 rollout 验证 + 信息增益校验
- **无候选行 48×3**(382s,2.7s/traj):mean_f1=0.661,hit 79.2%——带内
  (带候选行三轮 0.729/0.672/0.662,均值 0.688,差 -2.7pp 单轮噪声)。
  **无机制性事故**:offpool 拒绝仅 2/144(校验域宽集正常),空答案 0。
  case 级掉幅 8 个 >0.3(与 run 间翻转幅度一致)。候选行移除保留。
- **IG 校验**(两 run:walkperf 358 调用 / noroster 378 调用):
  - **标签-增益一致性**:EFFECTIVE pp 中位 +0.165/+0.155;REDUNDANT 中位
    -0.000/-0.000(仅 2-3% 超 0.2——结构判冗余概率微正的少数=结构优先
    设计的预期);INVALID ~0;first_gold 中位 **+0.286/+0.283**(金标引入=
    最大增益源,58/60% 超 0.2)。
  - **跨 run 稳定性**:分布形态几乎相同——IG 计算可复现。
  - 口径注意:HARMFUL 的 prefix pp 中位正(+0.108/+0.062)非矛盾——有害
    判定用 **LOO**(移除后全证据概率升的稀释型),prefix 边际可同时为正
    (早期加入时点)。两指标回答不同问题,校验时分开看。

### 2026-09-08 人工审核第八轮:join 兜底机制重写(1171:s0 标本,commit 47d1911)
- **用户审核发现**:s0 卡死于"R2 UNRESOLVED→satisfice 答错",gate 触发却
  零 join 路径——"为什么没有兜底,两个实体间为什么没有路径"。
- **根因(双重)**:旧 _search_join_paths ①解析**渲染文本**取边(括号属性
  实体丢失,违反"结构层用实际变量"纪律)②只在**已检索 walk 图**上搜——
  未检索实体(75th Ranger)在图里无节点,路径永不存在。而 case 全图上
  75th--servicemembers-->m.0t5m05b--military_person-->James Earl Jones
  **距离=2**。
- **重写**:
  ① 路径搜索改 **case 数组建邻接**(结构无文本),BFS unconsumed→reached
  (候选池∪绑定值),桥标注"可能巧合"(US-Army→Band-of-Brothers→German
  类桥真实但语义无关);
  ② **_unconsumed_edge_hint(可行动兜底)**:未消费实体自身一跳出边+CVT
  属性**按键聚合**——`'75th Ranger Regiment' --servicemembers-->
  military_person=Cory Remsburg | James Earl Jones | Alejandro
  Villanueva`(gold 直接可见)。自指值过滤;按键值数排序。
- gate 消息结构:UNCONSUMED 提醒 + JOIN PATHS(如有) + RETRIEVAL HINT。
  测试 34 passed。**行为改变:下次 rollout 验证**。

### 2026-09-08 人工审核第九轮:dump 截断误导 + 时间线澄清
- **用户审核 1171:s2 两个疑问的核验**:
  1. "答案没在子图上出现为什么还能感知"——Jones **在** sg3 完整渲染行里
     (servicemembers 392 字符行的行尾 m.0t5m05b [military_person=James
     Earl Jones])——**dump 工具每行 200 字符截断把行尾藏了**(审核工具
     缺陷,非渲染缺实体);offpool 拒绝是 walkperf run 旧行为(当时池=
     license-filtered 候选,漫游关系属性值不在)——今早 walk_seen 宽集
     修复后放行。
  2. "候选块为什么还展示"——用户审的是 walkperf run(9/7),候选行移除
     (9/8 上午)晚于它;noroster run 已无候选行。
- **dump 修正**:输入切到 noroster run+对应标注链(adjudication/
  prefix/teacher_subgraph _nr 系列);sg 渲染行宽 200→520(行尾 roster
  不再被藏)。**教训:审核 dump 的行截断本身会制造"实体消失"的假象**。

### 2026-09-08 人工审核第十轮:join 搜索对齐原始设计(用户裁定 #2)
- **用户校准**:"当时设置的是有限——模型在子图中检索的关系即路径包含
  检索的关系有限;路径越短越优先;还有用 GTE 和问题对路径做个排序"。
- **实施**:①可检索关系域=噪声前缀过滤+**hub 度 cap(>120)**——巧合桥
  (Band-of-Brothers→German 类管道节点)不再出现,1171 标本的真桥
  `75th--servicemembers-->m.0t5m05b--military_person-->James Earl Jones`
  浮出;②BFS 分层=最短优先;③GTE 对 question 排序(gate 改 async 延迟执行
  —_gate_deferred 经 _parse_prepare 交接,state 仍不在 gate 前转换)。
- 顺带修:consumed_anchors 大小写不匹配(Vader 被重复计为未消费);edge
  hint 按实体分组(多未消费实体时标签不再错位)。
- gate 消息终形态:UNCONSUMED 提醒 + JOIN PATHS(语义桥)+ RETRIEVAL
  HINT(roster 直见 gold)。测试 110 passed。行为改变待 rollout 验证。

### 2026-09-08 join 机制终验(rollout v38_joinfix)
- **语义定案(用户裁定 #3)**:join 兜底=**两个起点实体间**的未闭合桥
  (75th↔Vader),非实体→答案;hub cap 豁免路径端点(锚天然高度,Vader 172
  被自己的 cap 滤掉过)。
- **rollout 验证**(359s,0.664 带内):gate 16 轨迹,11 给出锚间路径,
  **9 个 f1=1.00**;1171:s0 历史 0.00→1.00(gate 显示 75th→Jones→Vader
  桥+roster,模型走通)。5 个无路径=图上真断(4 跳内无可检索桥),由
  RETRIEVAL HINT 兜底。统计 trap:run trajectory 只存 gate 短标记
  ('+ join_paths'),完整消息在 messages(未存 run)——按标记统计。

### 2026-09-08 join 信用机制(用户设计恢复)
- **gate trajectory 记录增强**:从短标记改为完整 JOIN PATHS+RETRIEVAL
  HINT 文本(审核+裁决都可读)。
- **裁决 JOIN-CREDIT pass**(tmp/adjudication_v2_jf.py):解析 gate 记录的
  path 边(仅 JOIN PATHS 段,按 hop 分割,序号剥离不动实体前导数字);
  gate **之后**的 sg 调用若 center/walk 命中 path 节点 → REDUNDANT 升
  EFFECTIVE(join桥执行);已有效标签保持(命中佐证)。
- 生效条件:下次 rollout 的轨迹(含完整 paths)——joinfix run 的 gate
  记录是旧短标记,pass 零触发(预期)。
- dump 产物:tmp/teacher_audit_dump_joinfix.txt(15395 行,joinfix run
  完整标注链;1171:s0 f1=1.00 的翻转已入档)。

### 2026-09-08 人工审核第十一轮:漫游候选补全(1797 标本)
- **用户审核发现**:gold Pemberton 只以"candidates not shown above"(walk
  漫游候选)出现;?fighter 展开域=显示实体(20 人,该图切片中恰好无人有
  date 边)→ rr 候选池永远无 date_of_death(Pemberton 的 date 边是全图
  唯一 date 源)→ 时间约束题死路。另:rr note 的"Do NOT pick attribute
  relations (date/name/type/role)"仅是模型侧提示,真排除发生在池构建
  (2-hop 可达域)——date 边不在 20 人邻域。
- **修复**:sg 渲染时把 not-shown walk 候选记 ctx.walk_extra(restart
  复位);?var 展开追加 ledger——漫游候选成为合法 center,其边进入关系池
  与 walk。1797 全 20 绑定端到端验证:ledger 捕获 Pemberton,下一次 rr
  候选含 date_of_death ✓。
- **1379 约束微妙性(用户观察)**:sg2(Priest 日期检索)标 REDUNDANT(约束
  低增益),但约束在问题语义上有效(gold 满足)——图里 **Liszt 本人的
  Priest 日期不存在**(m.011x94bw 无 leader 属性且 1956-58 非 Liszt);
  模型 UNRESOLVED→无矛盾保留→恰好答对。裁决问题待用户定:约束执行
  尝试(即使 discriminator 数据缺失)是否应记有效而非低增益。

### 2026-09-08 CVT 属性 GTE top-K 过滤(用户设计)
- **设计**:问题→属性键 GTE 排序(每 case 一次,缓存 on ctx);renderer 的
  cvt_disp 只显示 top-K 键的属性(SEQ_CVT_ATTR_TOPK,默认 3,0=关闭)+
  提交关系的**全部点分段**(inverse 方向覆盖:film.actor.dubbing_
  performances 豁免 actor 键)。
- **基线统计**:平均 96 个不同 CVT 属性键/case;随机 top-3 覆盖 5% gold
  键,GTE top-3 覆盖 **50%**;top-5=60%,top-10=70%。
- **验证**:1171(person 题)actor=Reiner Schöne 可见(组件豁免);25(movie
  题)character 角色名正确抑制。**发现的独立问题**:25 的电影名(Twilight
  等)对 1-hop walk 不可见——walk 只到 CVT mid 层,named 端点之前靠候选行
  兜底(已移除)→ walk 层需修(CVT→named 端点的枚举/渲染)。

### 2026-09-08 CVT 穿透边渲染修复(用户审核:25 标本)
- **根因**:walk 的 p.triples 有 54 条 CVT→named 边(m.xxx --film-->
  Twilight 等),但 tree_data 路径是**步骤关系约束的**——只记录
  anchor→CVT→anchor 往返,穿透到 named 端点的边不进路径。V38 renderer
  只从 tree_data 取边→named 端点不可见(之前被候选行掩盖)。
- **修复**:V38 renderer 的边集增加 p.triples 的全部 CVT↔named 边
  (storage orientation via hop_dir)。25 标本现在渲染
  `m.xxx [actor=...] --film--> Twilight` 全部 19 部电影可见。
- 1171 不变(sel_cvt 已覆盖);top-K=3 同开(character 抑制/movie Q)。
- 测试 65 passed。

### 2026-09-08 GTE 关系选择优化评估(用户设计迭代)
- **用户否决**:域过滤和类型感知匹配(都需要额外 LLM 调用,不靠谱)。
- **用户新方向**:优先选最终属性(attribute-first)——子问题→属性名(如
  "actor")→找中心实体子图中产出该属性的关系→展示时不给模型看域前缀
  只看属性名。
- **评估数据**:
  1. GTE 属性名 vs 全关系名:top-1 = 89% vs 8-15%(6-10x 提升);
     actor vs character 作为独立词完全可区分(作为前缀共享的全名不可区分)。
  2. 中心约束(2-hop+CVT)属性→关系映射:中位数 2 个(p75=4,p90=8),
     仅 'film'(max 14)和 'country'(max 12)会膨胀——均在 15 候选内。
  3. 属性名去重显示:15 全名→10 属性(1171 标本),跨域碰撞仅 1 个
     (character from film+tv,语义相同)。
- **方案**:retrieve_relations 改为按属性分组展示:
  `actor ← film.dubbing_performance.actor, film.performance.actor`
  `character ← film.dubbing_performance.character, ...`
  全名保留在括号内供模型提交。待实施。

### 2026-09-08 实体中心属性策略统计(用户验证:能否避免 film 膨胀)
- **center-direct(1-hop+CVT) vs full-pool(2-hop+CVT)**:
  产出关系数 mean=1.3 vs 1.8;max=**9** vs 14;**>10 的查询 = 0/163**。
  film 属性:Ron Howard 9(多角色)、普通人 2-4;**完全消除膨胀**。
- **gold 覆盖代价**:center-direct 53% vs full-pool 75%(22% 的 gold 在
  2-hop 路径上)——由后续 fact 的 ?var 多实体展开自然覆盖。
- **LLM 负担**:从"15 个混合域全名"降到"中位 1 个/属性组、max 9",
  且按属性名分组(actor/character/voice_actor 天然可分)。
- 方案定稿:retrieve_relations 改为属性分组展示 + center-direct 索引
  + 2-hop 补充(仅 >10 时 GTE 精排)。待实施。

### 2026-09-08 属性分组关系候选(实施,用户设计)
- **机制**:retrieve_relations 单次 GTE 调用同时排属性名+全关系名(无额外
  调用);按属性分组渲染(grouped_relations 字段),组内子排序,>5 截断
  top-5。candidate_relations(平铺)保留兼容。
- **验证**:1171 voice_actor←game_performance 排#1;25 film←actor.film
  精准分组。测试 65 passed。
- 索引→名称 bug 已修(cands 是 int 索引)。

### 2026-09-08 属性族选择实验(用户设计:选属性不选关系)
- **attrgroup rollout 两轮**:第一轮 0.569(note 丢了旧指令),修复后
  0.587——仍比基线低 7.7pp。原因:模型仍需从组内挑具体关系,挑错率
  高(RELATION_MISMATCH 25 vs 18)。
- **用户新方案**:模型只选 1-2 个属性族(如 "actor"),系统自动展开
  该属性族的全部池内关系进行 walk。
- **模拟数据**(oracle 选 gold 属性):
  pick-1: walk 1.3 关系,gold 覆盖 75%,漏 23%
  pick-2: walk 3.1 关系,gold 覆盖 96%(仅漏 4%),数据量 31-94 triples
  vs 当前 ~100-300 triples
- **优势**:gold 覆盖从 80%→96%,数据量降 3-10 倍,模型从"15 全名挑
  2-10 个"降到"12 属性名挑 1-2 个"。
- 待实施:_sg_prepare 属性名自动展开。

### 2026-09-08 属性族选择实施(commit 待定)
- **机制**:_sg_prepare 检测无点号的 relation 提交(如 'actor')→展开为
  中心池中所有 last-component 匹配的关系(cap 10/属性)。rr note 引导
  模型选 1-2 个属性名。
- **验证**:1171 relations=['actor'] → James Earl Jones(gold)可见;
  25 relations=['film'] → 全部电影可见。
- 待 rollout 验证质量。

### 2026-09-08 属性族 rollout 三轮总结
- attrgroup1: 0.569(分组显示,旧note丢失)→修复后 attrgroup2: 0.587
- attrfamily1: 0.591(全图展开)→attrfamily2(pool约束): 0.462
- **根因**:属性展开只抓 last-component 终点关系(CVT→person),漏掉
  CVT 桥接(center→CVT)——walk 无法从 center 到达 CVT,sg 结果 707 chars
  vs 基线 2884(4x 缩水)。用属性的轨迹 f1=0.431 vs 不用=0.636。
- **机制缺陷**:模型提交全名时天然包含桥接+终点(film.actor.film |
  film.performance.actor);属性展开只有终点(film.performance.actor),
  缺 film.actor.film → walk 无法穿透。
- 待用户裁决:回退 joinfix(0.664) 或修展开加桥接。

### 2026-09-08 attrfamily3(早期验证 bug 修复后)
- **0.603**,hit 78.5%——比 bug 版(0.462)恢复 +14.1pp。属性展开真正工作:
  sg 结果 3128 chars(基线 2884),"no valid" 错误 2(之前大量),用属性轨迹
  f1=0.606 > 不用=0.583(正向)。
- 剩余 6.1pp 差距的两个源:①CVT 桥接缺口(属性展开缺 center→CVT 第一跳);
  ②RELATION_MISMATCH 28 vs 18(属性匹配到池中关系但 walk 从 center 不可达)。
- dump: tmp/teacher_audit_dump_attrfamily3.txt(18543 行,无 IG 标注的
  raw 轨迹)。

### 2026-09-09 CVT 桥接修复(用户裁决:修展开加桥接)
- **人工审计结论**(attrfamily3 dump 复核):①dump 折叠了工具结果,看不见
  GTE 展示/模型选择;②CVT 选择展开大量未生效。
- **用户位置规则(纠正判定框架)**:CVT 展开是**位置规则**——CVT 是路径最后
  或倒数第二个实体 → 展开;与跳数无关。2 跳是**关系选择**的预算;有 CVT 时
  可延长一条边(3 边窗)判定关系是否作为路径。
- **根因**:族名匹配用 `_seq_pool_relids`(含 2-hop+CVT 透明跳),匹配到的
  终点边(`film.performance.actor`)不触 center → walk 0 边 → RELATION_
  MISMATCH。修法:`_sg_prepare` 族名展开改为邻接扫描——直连匹配(触 center,
  cap 10)+ **桥接**(center→载体:邻居触族名,或 CVT 邻居的 behind 实体触
  族名,cap 6)。终点边不进 rel_idxs(不触 center,walk 的既有穿透揭示它)。
  ctx 记忆化:`_rel_last_memo`(rel→末组件)+`_fam_expand_memo`((centers,族)
  →展开)。
- **展开回显**:sg 结果新增 `relation_expansion`(族→{direct,bridge}),
  RELATION_MISMATCH 错误路径同样带——模型可自审,轨迹可审计。
- **顺手修**:族名零匹配时 `rel_names[0]` IndexError(旧代码潜伏 bug)。
- **dump 可见性**:`scripts/dump_teacher_audit.py`(gitignored)——全 case
  全量未折叠 dump(GTE 候选列表/分组/think/调用/三元组),标签嗅探。
  旧 run 重dump:tmp/teacher_audit_dump_attrfamily3_full.txt(70400 行)。
- 测试:tmp/test_bridge_smoke.py 合成图 7 检查全过;套件 141 passed
  (test_cvt_passthrough 依赖丢失的 data pkl,test_skill_aggregation 的
  subgraph_kgqa 导入为历史遗留)。
- **rollout**:reports/v38_attrbridge_48x3.json(桥接版,结果待出)。

### 2026-09-09 attrbridge rollout 结果(桥接版)
- **0.6165 / hit 78.5%**(attrfamily3 0.6033 → +1.3pp;joinfix 0.664 仍差
  4.8pp;best-of-3 0.746 vs joinfix 0.808;配对 23胜/37负/84平)。
- **机制验证(桥接完全生效)**:族名提交后 walk 空 **30 → 0**;RELATION_
  MISMATCH 总数 **43 → 15**(低于 joinfix 的 18);relation_expansion 回显
  280 条;sg 调用 420→382(重试减少)。缺失族名榜(countries_within/region/
  time_zones/basin_countries)清零。
- **剩余差距定位 = OVER-EMIT 翻倍**:attrbridge 32 / attrfamily3 33 vs
  joinfix 16(PARTIAL 66/67 vs 79)。族名展开取回面宽(≤10 直连+≤6 桥接)
  → 候选多 → 模型多答。桥接不是瓶颈了,精度是。
- dump: tmp/teacher_audit_dump_attrbridge.txt(新 run,全量未折叠)。
- 待用户裁决:①族展开收窄(GTE 对问题排序取 top 而非邻接序);②答题侧
  约束(候选须满足全部开放事实才发);③回退 joinfix。

### 2026-09-09 人工审核第十一轮:类型+属性句柄 + ZH 泄露清洗
- **用户三发现**(attrbridge dump 审核):①分组只用末组件,类型语义丢失
  (producer.film 与 director.film 都叫 film;division/facility/league/
  location teams 混为一个)——from/to 语义靠类型组件;②ZH 中文标注
  泄露答案(212 的中文枚举三个金标州);③子图边显示 --teams--> 无法
  区分来源关系。
- **ZH 泄露清洗**:tmp/zh_questions_48.json 共 5 条泄露(212/Trn-60/2784_
  b642/452_f79f/452_343e,中文枚举或英文字面金标),全部改写为无枚举的
  忠实重述,复扫零泄露。ZH 注入本身承重(+2.1pp,修 493 类 plan 歧义),
  joinfix/attrfamily3/attrbridge 均带泄露跑——绝对值略虚高,对照内部一致。
- **类型+属性句柄**(commit 318fa50):rr 分组键=末两组件(type.attribute),
  属性 GTE 秩定组序;_sg_prepare 支持 typed 名精确匹配(一个语义族),
  裸属性=全族(宽),全名直通;direct 恢复 2-hop 池语义(hop-2 关系是合法
  路径边——桥接重构时曾误收窄),桥接保持邻接扫描;v38 边短名=type.
  attribute(行可溯源),CVT 属性排除保持裸键对比。
- 测试:tmp/test_bridge_smoke.py 12 检查全过(typed 精确/裸宽/全名直通/
  桥接保留);套件 141 passed。
- **rollout**: reports/v38_typedgroup_48x3.json(结果待出)。

### 2026-09-09 typedgroup→unibridge 两轮 rollout(句柄统一收口)
- **typedgroup 0.5901(hit 75%)回归**。分层:ZH 清洗 5 例 -10.75pp =
  诚实化(attrbridge 在那 5 例靠泄露偷分);其余 43 例 -1.7pp = 真回归。
  机制归因:**29/35 mismatch 是纯全名提交**(模型照抄分组列表成员名),
  typed 句柄本身 84 次提交 0 mismatch。全名直通绕过桥接——attrfamily2/3
  的病换了入口回来。
- **统一桥接修复**(commit "unified bridge expansion"):桥接是 (center,
  relation) 的可达性属性,与名字形式无关——bare/typed/全名统一走池匹配+
  载体桥接;不在池的全名保持直通(walk 反馈本就正确);全名仅带桥时回显。
- **unibridge 0.6361 / hit 79.9%(全场最高)**。诚实对照(43 无泄露例):
  **unibridge 0.6668 ≈ joinfix 0.6660(追平基线)**,attrbridge 0.6215,
  typedgroup 0.6045。机制:全名 mismatch 29→3,sg 调用 407→380,
  EMPTY 1(此前 0 但带泄露)。泄露 5 例组掉到 0.3719 = 无泄露辅助的真实
  水平,该组样本少(15)噪声大。
- 模型提交偏好:全名 438 / typed 118 / bare 4——全名照抄是主导行为,
  统一桥接正是为此设计;typed 精准(0 mismatch)保留为可选精度工具。
- dump: tmp/teacher_audit_dump_unibridge.txt(含 relation_expansion 回显
  +typed 分组 + 渲染 type.attribute 边短名)。
- OVER-EMIT 31 仍高于 joinfix(裸族宽展开面),为下一步审计点。

### 2026-09-09 人工审核第十二轮:多实体工作流恢复 + 三层排序
- **用户三发现**(unibridge dump 审核):①多实体工作流 0 触发(380 次 sg
  仅 8 次多中心且多为误传 m.xxx);②排序需三层:属性秩→属性组→组内
  类型+属性;③V21 提示语缺多实体段。
- **根因(③)**:V21 是 V2.1 重写时新生成的文件(仅一次提交史 dda5d50),
  旧 SEQ_AGENTS.md 的多实体段落(多中心同调用/多绑定整体处理/何时多子图)
  从未搬入——§0 工具规范只示范单实体 center。运行时支持一直在
  (_sg_prepare 多中心解析 + "COMPARE them" note)。
- **修复**:V21 §0 加多中心语法(center: A | B 共享关系集,一次比较) +
  ?var 全绑定展开规则;§6 加多绑定 HEAD 处理(一次调用比较,不逐实体
  迭代)。rr 排序:属性 GTE 秩 → 组内 typed 键字典序;candidate_
  relations 平铺列表同序(原为裸 GTE 序)。
- **multientity rollout**: f1 0.6412(整体 +0.5pp),hit 75.7%(-4.2pp),
  rest43 0.6499(-1.7pp,带内)。**机制生效**:多中心调用 8→32(4×),
  sg 380→360,使用多中心的轨迹 f1 **0.691 vs 0.632(+6pp)**;
  **OVER-EMIT 31→15(减半)**——上一轮遗留审计点解决。代价 UNDER 10→15
  /hit 降:判别方向偶尔过度收窄。
- dump: tmp/teacher_audit_dump_multientity.txt。
- 待用户审计:过度收窄案例(判别规则微调 vs 接受现状)。

### 2026-09-09 人工审核第十三轮:速度审计 + gate 环境耦合解耦
- **速度审计(用户问:是否又串行?)**——不是串行:bubble 并行一直在跑
  (总墙≈最慢 case 2076s,非串行求和)。真因是**每轮 LLM 延迟 4×**:
  joinfix 29.2s/turn → unibridge 126.6s(multientity 120.9s),轮数不变
  (8.4→7.9)。上下文膨胀:每 case 工具结果 14.5K→31.7K(2.2×),sg 结果
  3.3K→9.6-9.9K(3×,统一桥接取回更宽 + typed 行更长),144 并发下 vLLM
  prefill 排队放大。待用户裁决收窄手段(渲染行是承重证据,不可轻砍)。
- **gate 环境耦合(用户发现:多实体下联通规则 0 触发)**:`_ma_gate_
  would_fire` 用 consumption(plan_entities∖consumed_anchors 非空)做触发,
  而 `_sg_prepare` 把多中心调用的**每个 center** 记入 consumed_anchors——
  多实体工作流一启动全部锚"消费",gate 永不触发。消费≠连通。
- **修复**(commit "decouple join gate from consumption"):触发加第二条件
  ——答题时全部锚已消费但**累积游走图上锚点不连通**(accumulated_
  triples 名字图 BFS,`_anchors_disconnected`);`_search_join_paths` 加
  targets= 支持锚点→锚点闭合(用户裁定 #3 的起实体间闭合);全消费模式
  消息改为连通框架("若两侧独立解答即可作答"),不再给 retrieval hint。
- 冒烟:tmp/test_gate_decouple.py 6 检查全过(断连触发/连通抑制/经典
  未消费路径保留/单锚抑制/闩锁/空图触发);套件 141 passed。
- **rollout**: reports/v38_gatefix_48x3.json(结果待出)。

### 2026-09-09 gatefix rollout 结果(解耦后首验)
- **f1 0.6575 / hit 78.5% / rest43 0.6701——首次诚实超过 joinfix 基线**
  (0.6660),历轮最优:multientity 0.6499 < joinfix 0.6660 < gatefix 0.6701。
- gate 形态:unconsumed-gate 12(不变),connectivity-gate 0——但审计证明
  这是**正确抑制**而非失效:27 个多锚 case 中 13 个"全锚已消费+无 gate",
  离线重建其证据图,5 个疑似未连通 case 全部 f1=1.00(交集型问题:两侧
  通过**答案实体本身**在累积图连通,如 FDR 同时在 Roosevelt 与 WWII 子图)
  ——`_anchors_disconnected` 判连通抑制正确。connectivity 模式武装的是
  真失败形态(两侧从未合并仍作答),本 cohort 未出现。
- 速度(bubble 日志实锤并行:"118 in flight"):gatefix wall_mean 905s,
  与 multientity 持平——每轮延迟仍 ~120s,收窄手段待用户裁决。
- 注意:离线重建渲染图时不能剥 m.xxx 节点(CVT 是连接器,剥掉会假报
  未连通)。

### 2026-09-09 人工审核第十四轮:CVT 答案漏网根因 = 终端恢复推翻防线
- **用户发现**(multientity run, WebQTest-1923 s0):答案 = 18 个 m.xxx,
  f1=0.00。问:CVT 不能当答案,harness/提示语为什么没拦?
- **审计结论**:提示语有(§0 never answer or bind),harness 有两道且**都
  触发了**——①checkpoint §7.5 剥离+警告;②answer 工具全 mid 一次性拒绝
  (tools.py:2077)。真凶是 **rescue_terminal_answer**:`_last_answer_
  entities` 用正则读轨迹原文恢复答案,不做 mid 剥离——被拒绝的 mid 列表
  原样捞回(rescued=True),两道防线被终端恢复推翻。
- **修复**(commit "strip event-node mids from terminal answer recovery"):
  恢复的三个来源(answer 调用/ANSWER: 行/checkpoint 行)全部剥 [mg]. id;
  全 mid 来源落到下一来源(干净 checkpoint),全 mid case 恢复为空。
- 冒烟:tmp/test_rescue_midstrip.py 4 检查全过;套件 141 passed。
- 规模:0-2 例/run(joinfix 也有 2),全部 f1=0——老失败模式,非新回归。
- **次要展示缺口(未修,待裁决)**:tier-1 direct 行 `Miley --actor.film-->
  [mids]` 尾集是 CVT 但无属性括号(片名在后续 starring/music 行)——模型
  "忠实于所见"答 mid。可选修:direct 行 mid 尾补 `[film=...]` 括号。

### 2026-09-09 人工审核第十五轮:CVT 尾压缩 A/B + 实体优先(四轮 rollout)
- **用户三项裁决**:①同意 CVT 压缩(GTE 关系向量×问题向量排属性);②A/B
  属性内联 vs 独立块;③plan 工作流实体优先(实体越多定位越简单)。
- **实现**:≥4 CVT 尾的 (h,r) 行整尾集折叠为单条摘要——按键的 GTE 秩取
  top 键,键内列**不同值**(cap 8),单值跨全集折叠 `k=v (×n)`(重叠消除);
  `SEQ_CVT_STYLE=inline|block` 门控(block=行内指针+尾部 event attributes
  段);<4 尾保持逐 mid 括号。V21 §3 加 ENTITY-FIRST(枚举问题实体→
  contract 之前,实体=锚,交集定位)。
- **四轮结果**(48×3,f1/hit/rest43):
  | run | f1 | rest43 | 形态 |
  |---|---|---|---|
  | cvtinline | 0.6836 | 0.7006 | 显示 bug:摘要丢失只显 __evt0(mid 洪消失本身+3pp) |
  | cvtblock | 0.6707 | 0.6699 | 块版,rest43 与 gatefix 持平 |
  | cvtinline3 | 0.6570 | 0.6589 | 摘要被 sel_bare 排除污染:character 领街误导 |
  | **cvtinline4** | **0.6849** | 0.6900 | **摘要读 cvt_graph_all,族键(film:)领街——终版** |
- **A/B 结论:inline 胜**(block rest43 持平 gatefix,inline 全面高)。
- **两个过程 bug 教训**:①rows 初始化顺序(UnboundLocalError→整个 v38 渲染
  崩→legacy 路径→0.4324,套件 141 绿但未覆盖 v38 路径——新增直测
  tmp/test_cvt_compress_render.py 8 检查);②摘要键源继承括号排除规则
  (1171)导致选中族键缺席——摘要需要族键,括号维持排除,两者分流
  (cvt_graph vs cvt_graph_all)。
- 压缩行 189 个/run,mid 答案 0;dump:tmp/teacher_audit_dump_cvtinline4.txt。
- 终态弧线:joinfix 0.6640(带泄露)→ gatefix 0.6575/0.6701 →
  **cvtinline4 0.6849/0.6900(诚实最优,hit 79.9%)**。

### 2026-09-09 速度审计 + 环境恢复(用户:游走/GTE 优化是否被丢)
- **代码层优化全部在位**(逐一验证):traversal 邻接 memo(5e029e6/3a46bbb
  后零改动)、_is_latinish 字符 memo、lane GC 2M/100/100、walk 批协调器
  (sticky lane+跨 sample memo+MISS reship)、GTE 批客户端。
- **真丢的是调优运行环境**:历次 rollout 命令没带 GTE_CLIENT_BATCH_
  WINDOW=0.08/FIRST=0.02(默认 1.0s)→ GTE collect 1967s/run。恢复后
  **162s(-92%)**,dispatch 内 gte 2256→273s,p50 墙钟 1005→885s(-12%)。
- **反例实验(勿再试)**:WALK_POOL=4+WALK_BATCH_WINDOW=0.3 → mean 墙钟
  +18%(784→961s):4 核争用(exec +19%)+ 小窗口碎片化打包(burst 62→29)。
  结论与 2026-09-07 一致:4 核 cgroup 下 3 lane + 默认 1.0s 窗口就是最优。
- **慢的本体是工作量**(质量的代价):walk exec 364s(walk-perf 基线)→
  1733-2165s(×4.8-6)——统一桥接/族展开使每 sg 调用关系集 1-3 条→5-16
  条(slots 1998-2343,0.87-0.92s/slot);上下文 2.2× 使每轮 LLM 29→121s。
  48×3 墙钟 378s(旧机制)→ ~18-20min(新机制,f1 0.664→0.685)。
- **锁定基准 env**(后续 rollout 必带):
  `WALK_POOL=3 GTE_CLIENT_BATCH_WINDOW=0.08 GTE_CLIENT_BATCH_FIRST=0.02`
  + 原 SEQ_* 组;WALK_BATCH_WINDOW 不设(默认 1.0)。
- 唯一进一步杠杆=收窄展开上限(direct 10→6/bridges 6→4)——行为改变,
  需 A/B 验证质量是否保留,待用户裁决。
- 三 run 对照:cvtinline4 0.6849/784s | perfenv(4lane+0.3w)0.6751/961s |
  perffinal 0.6606/829s/p50 885s(rest43 0.68-0.69 带内,批窗口纯调度)。

### 2026-09-10 游走成本模型验证(用户架构判断逐条核实)
- **用户模型正确**:RPE(frontier.py relation_prior_expand)的桥跳可以走
  任何非选中关系——遍历就是**全 3-hop 环境游走**,关系集只决定段终止;
  **游走成本与关系集宽度无关**。桥接/族宽度不是成本源(提交均值 1.4 个
  关系,direct 几乎全 1,echo 展开宽 1-7)。
- **LLM 不慢**:纯 LLM 21.6s/turn(llm=24k s÷144÷7.7);墙钟每轮 121s 是
  dispatch 排队——之前把墙钟/轮归因 LLM 是误判。
- **slot 爆炸真凶** = ?var 展开的 **walk_extra 无界账本**(每次 sg 单调
  追加不展示候选,晚期 ?var 调用游走 30-50 中心;343 请求→2343 slots,
  71 次调用 6-15+ 中心)。
- **修复**:walk_extra 近因 cap 6(SEQ_WALLEXTRA_CAP,绑定不设限——多实体
  设计保留;1797 机制只需紧邻前次的游荡者)。slots 2343→1796,**质量
  新高 f1 0.6930/rest43 0.6948**(噪声中心↓证据更紧),exec 基本不变
  (2165→2152)——砍掉的是廉价叶子,贵在 hub。
- **下一杠杆(用户设计,walk-algo 分支)**:exec 集中在 hub 绑定环境×
  不同关系集重试的**整环境重游**(memo 只认精确 (center,relset) 对)。
  方向=环境级复用:同中心一次环境展开缓存 + 每关系集段记账(RPE 段终止
  逻辑后置)。等价验证用 walk-perf 的 pickle-sha256 battery。
- dump:tmp/teacher_audit_dump_perffinal.txt。

### 2026-09-10 变量延展游走:第一版设计被否(用户纠正)与修正方向
- **用户否决**:我实现"从原点 2 步链式"(hop1=via 关系,hop2=新关系)——
  用户指出**第一子图本质 2 跳深**(锚→中间→绑定在深度 2),从原点重走
  两跳=**回退**:把跳数预算烧在重达绑定上,且 via 单跳根本到不了深度 2
  的绑定。已全部回退(工作区=wallexcap 态,141 测试绿)。
- **修正方向(用户"模式图粗化/融合"的正确落点)**:**边界状态延展**——
  第一子图的游走已经到达绑定(绑定是其 hop-2 端点);延展应携带**已走
  模式图作为前缀状态**:从每个绑定游走时,第一子图的节点集作为 mask,
  指向已走领地的边只记录为连接证据**不再展开**,预算全部投向绑定之外的
  **新增疆域**。共享前缀一次游走,多绑定探索在共享状态上融合。
- **实施面**:worker 侧按 (case, origin) 缓存已走节点/边集;RPE 的 BFS
  加 prefix_nodes 参数(入前缀的边记录不展开)。**非结果等价**(穿前缀
  的路径被截断)→ A/B + walk 级 pickle 对照量化差异。
- **先测量再实现**:instrument 一遍"绑定游走的边有多少已在原点模式图里"
  (稀疏图重叠小收益小;hub 稠密图重叠大——而 exec 恰好集中在 hub)。

### 2026-09-10 模式态前缀延展:实现+A/B 判决(负收益,默认关)
- **实现**(commit "pattern-prefix continuation"):_sg_finalize 记 walk_seen
  增量 per fid;checkpoint 绑 var → pattern_state(节点并集);单一 ?var 调
  用携带前缀(协调器 slot 键含前缀,worker 建 cs.prefix_nodes);RPE 前缀
  邻点只记目标边不展开。冒烟 4 语义全过(基线穿共享/mask 留新边疆/不入
  前缀/目标边入前缀记录)。
- **A/B 判决**(patprefix vs wallexcap):速度零增益(exec 2408 vs 2152s,
  墙钟 804 vs 809s,slots 1867≈1796),**f1 -2.4pp(0.6930→0.6692)**,
  sg 结果反而更大(8.5K vs 7.3K)。根因:RPE 大头成本=每绑定 3-hop
  **新边疆**(hop2-3 不在前缀内),mask 只省 hop1 回头路;穿共享领地的
  合法路径被截断损证据。**默认关**(SEQ_PATTERN_PREFIX=1 可开)。
- **结论**:用户的方向(状态保持)在 RPE 3-hop 全环境模型下没有可收割
  的重叠——省的(hop1 回边)不是贵的(hop2-3 新边疆)。剩余路径:①深改
  beam/剪枝(行级);②C 层(igraph)替换 BFS。均属 walk-algo 分支工程。
- 当前最优配置 = wallexcap:f1 0.6930 / hit 77.1% / rest43 0.6948,
  wall_mean 809s。

### 2026-09-10 模式层游走(集合态+关系转移)原型验证 — 判决:合适
- **用户抽象**:三元组图 → 集合节点+关系转移的模式图;实体不作搜索节点,
  藏在 pattern node 的 member bitmap 里;一次 O(E) 建关系索引
  (rel→head/tail bitmap + 按关系邻接),之后所有 fact 查询 = bitmap 集合
  交 + relation join;witness 只在最后按 top-K 模式延迟实例化。
- **原型**(tmp/proto_pattern_walk.py):CaseIndex(O(E))+pattern_walk
  (集合态 BFS,桥=任意非目标关系,终止=目标关系命中,RPE 段语义保留,
  CVT 终点穿透)+_materialize(按模式反向重建实体链)。
- **回放 harness**:wallexcap run 的 87 个真实多绑定 ?var 调用(≥4 绑定),
  现后端(_walk_case_steps 逐绑定)vs 模式后端:
  **109.0s → 6.3-8.9s,12-17× 提速**。
- **"金标召回 178→27"是伪影**:抽到的判别型调用(2209 查决赛日期、567 查
  候选电影 genre)gold=输入绑定本身;现后端把中心回显进候选被计为命中,
  模式游走按设计只出模式答案(dates/genres——语义正确)。567 可见
  rating→genre、produced_by→genre 等**反先验桥路径完整保留**。
- **语义差(真实)**:模式后端只出选中关系的聚焦答案+witness;现后端附带
  3-hop 全环境("other walked relations" 噪声——上下文 3× 膨胀的来源)。
  聚焦化是速度+上下文双重收益,但模型能否消费新证据形态需 rollout A/B。
- **生产集成设计(下一步,待裁决后实施)**:
  ①触发:centers=单 var 绑定集(≥4)的 sg 调用 → 模式游走;
  ②模式排序:support × GTE(问题,终止关系),top-K(8-12);
  ③重实例化:每模式 K 条 witness 链 → 渲染"模式头+链行"证据视图
  (用户:模式路径重新实例化为子图);
  ④兜底:模式空 → 回退逐绑定现后端。
- 交接文档:docs/codex_walk_optimization_handoff.md(给 Codex 的分析包)。

### 2026-09-10 单中心游走慢的真相 + 模式游走三轮 A/B 终判
- **用户质疑成立,profile 定罪**:hub 单中心(Ron Howard,度 877,4 关系)
  单走 4.5s,**97% 在证据构建 build_pattern_evidence_triples**,游走本身
  毫无罪——CVT 展开同边重复打分(_expand_endpoint_cvt 10 万次/走、_add
  70 万、_is_latinish 200 万,唯一边仅几千)。cProfile 下 28.7s 是 5960
  万调用的放大假象。
- **三处静态 memo(结果逐字节等价)**:(h,r,t) 静态过滤结果、每 CVT 静态
  打分边表(每调用只重算 witness 位)、sibling selected 判定。
  **sha256 相同(b672b5445767),4.48s→2.39s(-47%)**,141 套件绿,已提交。
- **模式游走三轮 A/B**(全部 vs wallexcap 0.6930):
  | 版本 | f1 | slots | 判定 |
  |---|---|---|---|
  | v1 全终止集 | 0.6508 | 461 | 桥当终止→噪声霸榜 |
  | v2 direct-only 终止 | 0.6269 | 458 | 召回损失更差 |
  | v3 +tier-1 织入 | 0.6548 | 572 | +0.4pp 仍 -3.8pp |
  速度地板真实(slots 1796→572,墙钟 -18%),失败模式同构
  (PARTIAL 107/109)——聚焦证据的部分对答案成分更差,逐绑定环境对模型
  判别是承重的。**默认关(SEQ_PATTERN_WALK=1 可开)**。
- 速度弧线收口:结果等价层全部入袋(walk_extra cap / GTE 窗口 / 证据
  memo),质量换速度的模式游走待新思路(逐绑定 witness 全覆盖?)或
  Codex 剪枝方案。
- patwalk 系列 run:reports/v38_patwalk{,_2,_3,_s1}_48x3.json。

### 2026-09-10 三问解答 + memo 升 case 级(用户提议落地)
- **为何 10 万次**:`_expand_sibling_cvts` 按(模式×路径)跑,每条触 CVT 的
  路径重新展开该 CVT 的整个 sibling 家族(同 (head,rel));路径数千 × 家族
  数百 ≈ 10 万;去重(seen_set)在管线**末端**——工作先做 100 遍再丢 99 遍。
- **评分是什么**:_add 的门=模式-路径纪律(r∈sel 或 cvt_attr 通道)+
  schema 噪声拒绝 + **latinish(滤非拉丁实体名,CJK/垃圾)** + normalize
  长度;_expand_endpoint_cvt 的 score=边的入场优先序(witness∈路径 >
  非meta > 拉丁 > 短名)。latinish 单次无关紧要(字符 memo,~1µs),
  200 万次量的成本;cProfile 里 27.7s 是调用开销放大,真实 ~0.8s。
- **真实时间**(无 profile 失真,Ron Howard 标本):修前 4.48s → build
  memo 1.58s(冷)/1.29s(热)→ case 级 memo 后第二次调用 1.26s。
  残余 = 每调用 witness 排序(O(家族)×万级调用),字节等价约束下的地板。
- **case 级 memo**(commit "promote … to CASE level"):打分边表与 (h,r,t)
  静态结果按 pin 的数组键存 `_CASE_STATIC_MEMO`——同 case 后续 sg 调用
  不再展开 CVT(用户:CVT 展开一次,展示按需调整)。sha 全程等价。

### 2026-09-10 witness 排序流程拆解(用户)+ 家族去重(第四刀)
- **流程**:39 模式 × ≤24 support path → _expand_sibling_cvts 7221 次 →
  每条路径对每个 CVT 节点重walk同 (head,rel) 家族(Ron:guest_roles 70/
  award_nom 53/starring 45/film 29…)→ 每兄弟 _expand_endpoint_cvt
  (兄弟度均值 6.2:witness 位 + tuple + sorted + add)。量=路径×家族×度
  ≈ 130-200 万边级操作;单次排序 6.2 元素,贵在乘法。
- **拆解洞察**:_add 接受条件全静态(schema/latinish/normalize/sel_ids),
  witness 位只改序不改成员 → **同一 adder(模式)内,家族后续触碰的
  add 全是 seen_set 空操作**——第一触摸序即结果。把 per-call 的
  expanded_rels 提为 per-adder(_add._fam_done)→ 7221 次收缩为每模式
  首触。**5 标本 sha 全等**;Ron 1.26→1.03s,次级 case -60-66%。
- **失败教训**:先试了 build 级去重——sha 变了:_make_adder 是**每模式**
  一个(pat_triples/pat_seen 独立),后续模式必须保留自己的首触。
- **四刀弧线(Ron Howard 标本,全字节等价)**:4.48s → 静态 memo 2.39s
  → case 级 1.26s → per-adder 家族去重 **1.03s(-77%)**。

### 2026-09-10 第五刀(显示串 memo)+ 方法学发现(pickle-sha 顺序敏感)
- **残余 1s 拆解**:profile 显示新热点=显示串构建——_cvt_attr_display
  10.4 万次(每模式每路径重建同一 CVT 的属性列表)+ _node_display 12 万
  次 + is_cvt_like 回升 126 万(纯调用量)。
- **第五刀**:_cvt_attr_display → case 级 memo(纯 (cvt_idx, 数组) 函数,
  limit 恒 20);_node_display → 每模式 memo(cvt_attrs 模式内固定)。
  **Ron Howard 1.03 → 0.36s;五刀总弧 4.48 → 0.36s(-92%)**。
- **方法学发现**:验证时 sha 在"同内容不同历史"下漂移——深挖证明:
  游走层/compress/materialize 哈希稳定,pe 内容(triples/candidates/
  tree_data)== 完全相等,**差异纯属 dict/set 插入序置换**(缓存冷热
  改变累积顺序;pickle 保序而 == 不看序)。该置换类在 walk-perf 时代
  就存在(基线复现)。**正确验收标准 = 内容相等 + 同态字节稳定**
  (两者均过;141 套件绿)。pickle-sha 只在匹配状态下可作字节等价证据。
- 教训:bisect 恢复用 `git checkout HEAD -- file` 会抹掉未提交工作区
  (第五刀曾因此丢失重做);跨进程对比 sha 需固定 PYTHONHASHSEED。

### 2026-09-10 五刀终验 rollout(v38_speed5)——速度质量双收
- **速度**:wall_mean 809→**361s(-55%)**,p50 372s,max 551s,总墙
  ~9.5min(此前 ~19-20min);**walk exec 2152→331s(-85%)**,wait 5 万→
  721s,dispatch 9.5k(此前 72-95k)。llm 成为主要相位(GPU 饱和,符合
  设计——dispatch 不再阻塞,LLM 并发重叠充分)。
- **质量**(内容等价,差异=采样带):**f1 0.6978(新高)/ hit 79.9% /
  rest43 0.7100**(wallexcap 0.6930/77.1%/0.6948);OVER-EMIT 15。
- dump: tmp/teacher_audit_dump_speed5.txt(144 case 全量)。
- **速度弧线收官**:walk-perf 378s(旧机制)→ 质量弧线膨胀到 ~1200s →
  五刀+环境恢复+walk_extra cap → **~570s 总墙 / 361s mean**。
  下一杠杆只剩 LLM 端(上下文瘦身,待用户逐项裁决)。

### 2026-09-10 Belgium 证据爆炸审计(用户)— 两层修复均负,已门控关
- **用户发现**:Belgium 提交 countries.continent|location.containedby 两
  关系,证据却爆出 adjoins/战斗/部分包含等十余无关段。
- **机制**:①选择层——behind-CVT 载体判定过松(Belgium 的 CVT 共同端点
  全是携带 countries.continent 的大国)→ 桥接把无关关系塞进 rel_idxs,
  渲染成 "(retrieved)";②证据层——RPE 桥段末跳(Luxembourg --containedby--)
  与 sibling 展开行失去中心锚定形状(用户:应"以中心实体实例化抽象路径
  重建",路径一致性)。
- **A/B 判决(全部 vs speed5 0.6978)**:
  | 修复 | f1 | 判定 |
  |---|---|---|
  | direct-first(中心直连即免桥) | 0.6541(-4.4pp) | 桥接游走的穿透喂判别证据 |
  | +tier-1 锚定降级 | 0.6539 | CVT 穿透行被埋(修正后 0.6661) |
  | 锚定修正版 | 0.6661(-3.2pp) | 环境行仍承重 |
- **结论**:Belgium 爆炸在指标上是**净生产力**——与模式游走/patwalk 同一
  教训:游走宽度(桥接+环境行)承重。两个修复均门控关(SEQ_DIRECT_FIRST /
  SEQ_TIER_ANCHOR),**站立配置 = speed5(0.6978/79.9%/361s)**。
- 保质量的替代方向(未试):**链形渲染**——多跳路径渲染为
  `Belgium --adjoin→Luxembourg --containedby→ Europe` 单行(保留全部行,
  标注来源),信息不减只加形状。
- dumps:tmp/teacher_audit_dump_{speed5,pathcons,directfirst}.txt。

### 2026-09-10 speed5 失败分解(用户裁决:先修三元组层)
- **58 失败/144 = 三元组层 19(gold 从未进 sg 证据)+ 编排层 39(gold 在,
  模型选错)**。抽查验证 ABSENT 属实:452(Baltimore)/1379(Priest)全
  工具面缺失;212(三州)/25(Nick&Jessica)仅 rr 候选列表出现、sg 渲染
  从未到达(模型靠 rr 残余部分答对)。
- **三元组层修复目标清单**(gold 全缺):452×2(Baltimore)、1379(Priest)、
  21×2(Hailemariam)、25×2(Nick&Jessica)、2319×2(三语言)、2576
  (Americas)、1731(Bass guitar/Vocals)、3084(Canada)、3744/1557(大学)、
  212×2(三州,部分)。
- 编排层 39 例的复查入口(dump 行号):567 s1=15460(Village of Giants
  在证据但答 A Beautiful Mind)、2576 s1=5105(答 Western Europe)。
- dump:tmp/teacher_audit_dump_speed5.txt。

### 2026-09-11 三元组层再分类(用户裁决:环境错配 vs 模型能力)
- **裁决标准**:关系选对但游走/渲染没出答案=环境 bug;关系选错或展示
  充分下推理错=模型能力,非环境。
- **深验结果(10 样本)**:
  | 类 | 案例 | 证据 |
  |---|---|---|
  | 模型能力(移出) | 452 s0/s2、1379 s2、21 s1/s2、212 s0、2319 | 452:Brooklyn(出生)与 Baltimore(居住,[location=Baltimore] 括号在)都在渲染,模型选错"home"语义;2319 金标连接边=documents/keys 噪声,图本身薄 |
  | 环境-判别器属性缺失 | 25 家族(tvrage_id)、452(located ID 在城市实体第二跳,不在 CVT) | 答案可达但判别键被 CVT top-K 滤掉/需要第二跳 |
  | 环境-截断(嫌疑) | 25 s1/s2 | gold 走 film.starring 家族,模型提交了 film 族但未出渲染——roster 40-cap/beam 截断待查 |
  | 待定 | 2576 s1(Americas 2-hop) | 未深验 |
- **环境修复方向(下一步)**:①判别器属性保障——问题含约束数字/id 时,
  CVT/实体属性展示保底含约束键(比照 submitted-components 豁免机制);
  ②roster/beam 截断审计(25 标本)。

### 2026-09-11 前缀 bug 修正:三元组层 19→8(工具错误,非管线)
- **工具 bug**:presence 检查只认 `triples:` 开头,而带 fact_id 的 sg 结果
  以 `fact_id: sgN` 开头→大量假 ABSENT。2576 结案:金标 Americas 直接在
  tier-1(`Falkland Islands --containedby--> Americas | …`),模型答 UK
  =读错成员,**模型能力**。
- **修正后真 ABSENT 仅 8 例**:21 s2(Hailemariam)、3744 s0(Wisconsin)、
  1379 s2(Priest)、452 s0(Baltimore)、25 s2(Nick&Jessica)、567×3
  (The Journey——同一 case 三采样全缺,最像真环境缺口)。58 失败重新
  分为 **8 三元组层 + 50 编排/模型层**。
- 25 s1 的金标在 pe 但被 CVT 压缩每键 8 值 cap 截断(已证);s2 同 case
  另一形态。教训:**审计工具自身要先验证**(452 s2 曾因同名前缀漏检
  被误判)。

### 2026-09-11 最佳路径审计终判(8 例 ABSENT 归因闭环)
- **方法(用户)**:锚→金标 BFS 最短路(CVT 透明),三问:给过(rr)?
  走过(提交)?展示(渲染)?
- **567×3(Q: Ron Howard 最早电影)**:无直连,正路 VIA-CVT film 族;
  Ron 60+ 电影,*The Journey* 字母序 T 位 → **与 25 s1 同款:CVT 压缩
  每键 8 值 cap**;三采样全缺=确定性截断。
- **3744 s0**:金标 Wisconsin 在渲染两处(wandered 注记+?college 行)
  → 第二个工具 bug(normalize 金标 vs 原始文本,多词名假阴性)→ 假
  ABSENT,实为模型判别(人数比较)。
- **终分类**:环境=**仅一个机制(CVT 压缩 8 值 cap,567×3+25 s2=5/8)**;
  模型=21 s2/1379 s2/452 s0(路径给过没提交)+3744(在渲染判错)。
- **修复待裁决**:压缩摘要的提交族键 cap 8→40(或 100,对齐旧叶子
  纪律);次要键维持 8。判别器属性(plan 缺口)另案。

### 2026-09-11 族键 cap 40 修复落地 + 阶段漏斗(用户:阶段决定推理可见)
- **修复**(SEQ_CVT_VALCAP=40):压缩摘要中键∈提交族末组件 → 值 cap 40
  (叶子纪律),次键维持 8。valcap40 run:**f1 0.6923(带内)/hit 81.2%
  (+1.3pp)/wall 334s**。567_11fd The Journey **可见性恢复**✓,但仍答
  Splash——判别器深度(release_date 只对部分电影在渲染)。
  25_892ff 仍不可见(另一形态,待最佳路径)。
- **阶段漏斗**(推理侧可见内容的全部决定点):
  | 阶段 | 决定点(参数@代码) |
  |---|---|
  | S0 图 | build_context:expand_cvt_leaves(CVT 叶展开) |
  | S1 rr 候选 | 池=_seq_pool_relids(2-hop+CVT 透明);attr_ranked+rel_ranked 合排;candidate_relations **top-15**;grouped **≤12 组/组内 ≤5** (seq_tools:3009,3102) |
  | S2 提交展开 | direct **≤10** + bridges **≤6/名**;echo 回显 |
  | S3 游走 | 主 logical_paths(beam 80/hop2);RPE 兜底(max_hops 3, beam 80, **per_branch 5**);support paths **≤24/模式**(formatting:492);模式保留 **top-5**(seq_tools:3870) |
  | S4 证据 | build_pattern_evidence_triples **max_grouped_lines=120**;sibling per-adder 首触;CVT attr 全量(显示层再滤) |
  | S5 渲染 v38 | tier-1 选中段 + roster **≤40**;CVT 压缩(≥4 尾):键 **top-K=3**(GTE)+提交组件豁免,**族键值 cap 40**(本次修复),次键 8;行预算 **200**;license filter |
  | S6 消息 | note 固定文本+relation_expansion+pattern_paths(关) |
- 待办:25_892ff 最佳路径;567 判别器深度(全电影 release_date 保底?);
  452/25 的约束键(tvrage_id 类)plan 缺口课题。

### 2026-09-11 Ron Howard 颁奖爆炸案(用户:为何两关系重建一堆子图)

### 2026-09-11 游走设计对齐实验(specs/walk_realignment_spec.md)——两轮,判决:门控关
- **诊断(用户,正确)**:agent 路径强制 n_steps=1 → 引擎的前向验证
  (chain_expand lookahead)/顺序检查/_check_order 全部闲置;到达只能靠
  "桥当终止"。四支柱(路径纪律/模式路径/一致性/CVT 双设计)引擎全在,
  agent 未用——这是五次桥实验负收益的共同根源。
- **实施**:①无直连支持的 center 推导多步序列(BFS ≤3 命名跳,CVT
  透明,结尾=家族)→ 多步 step_relations(前向验证原生生效);②桥退役
  (SEQ_BRIDGE_TERMINAL=0);③CVT 命中键置顶(支柱 4b,保留在产)。
- **两轮 A/B 判决(门控关,SEQ_MULTISTEP=0/SEQ_BRIDGE_TERMINAL=1)**:
  | run | f1 | mismatch | 问题 |
  |---|---|---|---|
  | realign(仅族名门控) | 0.6683 | 48 | 全名提交无多步无桥 |
  | realign2(全提交+3跳) | **0.6349** | **76** | 更差——序列步行到达不足 |
  引擎原生多步+前向验证在本 cohort 上**到达能力显著弱于** RPE 松终止
  单步(f1 -4.6pp vs speed5)。上下文收益真实(sg_p90 4.5K vs 12.7K,
  -65%)但质量代价不可接受。
- **留下的资产**:specs/walk_realignment_spec.md(设计北极星+判决链);
  CVT 命中键置顶(支柱 4b)在产;多步推导/序列 step 管线代码留存门后,
  供 walk-algo 分支深改(问题=多步序列的到达覆盖,可能是每跳单关系
  太窄/需要并行多序列)。
- **六次收紧/重排实验完整弧线**:免桥 -4.4 / 降级 -3.2 / 标注 -3.4 /
  遍历-only mm39 / 提交终止 -5.5hit / 引擎多步 mm76——全部指向同一
  结论:**RPE 单步松终止是当前唯一测得可行的到达模型**;设计完全体
  需要算法级重构(walk-algo 分支),不是参数或管线重排。

### 2026-09-11 realign3:并行跳合并——计算不可行(rollout 终止)
- **实施**(用户:r1 可多种,每跳全并行入集):BFS 收集各深度全部
  关系,按层合并为 frozenset——前向验证接受任一关系。
- **判决**:rollout **t=1764s 仅 36/144**,walk worker 饱和(GPU 52%
  但 spawn 进程空闲=queue 堵)。宽跳集(可能数百关系/层)× 多步前向
  验证的路径枚举 = 指数爆炸。已终止,代码门后留存。
- **架构边界确认**:path-enumeration 游走(chain_expand/k_queue)无法
  扩展到并行跳多步——RPE 的 beam-limited 单步之所以可行,正是因为
  beam 剪枝在指数曲线上截断。设计完全体(模式层 + 并行跳 + 一致性)
  需要非枚举型算法(集合态/关系代数),这正是 pattern_walk 模块的
  bitmap 方向——但它自己的证据密度不够(-3.8pp)。**下一步是合并
  两者的强项:bitmap 集合态的搜索 + RPE 级的证据枚举**。

### 2026-09-11 realign4:模式层枚举(用户修正)——5case 快验通过
- **用户修正**:实体 BFS 是错误实现——模式层=纯关系序列枚举(去重
  (r1,family) 对,support 排序,top-K),一跳命中只有一种,两跳不该
  超百;毫秒级,无实体路径爆炸。
- **实现**:`_derive_multistep_seq` 重写为关系层:1-hop 邻接(含 CVT
  透明)→ 枚举 (r1, family) 对→ support 排序 top-3 → 每模式=独立
  multi-step step → pe 按 center 合并。
- **5case 快验**(realign4_s5): **f1 0.6889 vs speed5 同 case 0.6678,
  mismatch 仅 2,墙钟 53s/case**,1923 提升 0.89→1.00。无爆炸。
- 门控:SEQ_MULTISTEP=1(快验参数);待全量 48×3 验证后定默认。
- **全量 48×3 判决**(realign4):f1 0.6499 / **mismatch 72**——5case
  快验的 5 案恰好是简单模式结构,全量暴露覆盖不足:枚举只找 2-hop
  (r1, family) 对,而 RPE 松终止允许任意 3-hop 桥接终止。**第八次
  实验确认同一结论**。门控关,站立恢复 topk5。
- **机制**:提交 director.film|producer.film → 桥扫描逐邻居检查 → 颁奖
  CVT 的共同端点(Brian Grazer 等)携带 film.producer.film → behind-CVT
  命中 → award_winner/award_nominations 作为桥进 rel_idxs(≤6/名)→
  tier-1 渲染成 "(retrieved)"。Belgium 同根,这次踩好莱坞社交图
  (共同提名人是制片人几乎恒真)。
- **第三次判决链**:direct-first(免桥)-4.4pp;tier-1 锚定降级 -3.2pp;
  **纯标注"(bridge context)"hit 82.6→79.2(-3.4pp)**——连降低注意力
  的标签都损失命中。**结论坐实:behind-CVT 桥洪是付账的噪声**,
  三种抑制方式全部负收益,标注已门控关(SEQ_BRIDGE_LABEL)。
- 站立配置 = topk5(f1 0.6802/hit 82.6%/316s);bridgelabel run 留档
  reports/v38_bridgelabel_48x3.json。

### 2026-09-11 第四次桥实验:遍历-only(用户设计:路径以提交关系结尾)
- **设计**(用户):模式层检索以提交关系为**最后一条**的纯关系路径;
  实体重建;award 类不应符合路径纪律 → 桥只应可遍历、不应为终止。
- **实现**:桥不进 rel_idxs(RPE 中段跳本就允许任意非目标关系,
  遍历无需成员资格;进集合=获得终止地位=award 段合法)。
  SEQ_BRIDGE_TERMINAL 门控。
- **判决(最差配置)**:f1 0.6798 但 **mismatch 39(vs 1)、hit 76.4%
  (-6.2pp)**——RPE 中段桥跳不能自给找到载体路径;**桥的终止地位
  正是 unibridge 修 mismatch 的机制本体**。默认已翻回终止桥。
- **四配置完整判决链**:终止桥(站立,mismatch 1)/ 免桥 -4.4pp /
  降级 -3.2pp / 标注 -3.4pp hit / **遍历-only mismatch 39, -6.2pp hit**。
  结论:RPE 的到达能力依赖松终止;award 洪是其测得代价。用户纪律的
  完全体 = 模式层游走(SEQ_PATTERN_WALK,曾 -3.8pp)——根本张力在
  RPE 的到达模型本身,留作 walk-algo 分支课题。

### 2026-09-11 CVT 键 top-K 3→5 + 机制对照表(用户:各影响什么)
- **验证**:GTE 对 "released first" 排 initial_release_date #3、
  release_date #4——top-3 刚好卡在判别键外面,提到 5 纳入。
- **topk5 run**:f1 0.6802(带内低沿)/ **hit 82.6%(+2.7pp,新高)** /
  wall 316s;25_892ff 首次出现 1.0 采样;567_11fd 仍 0(日期可见但
  "最早"推理仍错=模型侧)。hit 升 f1 微降:更多 case 命中但组成分
  略降——保留(用户以命中为重)。
- **机制对照表**(每闸门影响什么,详见上表 S0-S6):
  - roster ≤40:**只裁 tier-1 段头的候选名单行**(扇出侧实体的一眼
    总览),正文行不受它管(归行预算/1200 折叠);
  - 键 top-K=5:每 CVT 括号/摘要显示哪些**属性键**——判别键入口;
  - 提交族豁免:所问键永不被滤;
  - 族键值 cap 40/次键 8:每键列多少**值**(567 修复);
  - ×n 折叠:单一值键折叠(重叠消除,已有);
  - 压缩 ≥4 尾触发:何时折叠 mid 尾集;
  - direct ≤10/bridges ≤6:单次提交的游走宽度;
  - RPE hops3/beam80/per_branch5:探索深度/宽度/同尾路径多样性;
  - support ≤24/模式、模式 top-5:喂证据的路径与模式数;
  - max_grouped 120 / 行预算 200 / 1200 折叠:构建与渲染的量闸。

## 2026-09-08 SESSION HANDOFF(压缩前完整状态)

### 当前分支与代码状态
- **分支**: walk-perf(领先 agent-toolcall ~15 commits)
- **最后一次完整 rollout**: attrfamily3(0.603)——属性族选择+CVT 穿透边+
  属性分组 rr+无候选行+CVT attr top-K+join 兜底全开
- **基线对照**: joinfix run(0.664) = 属性分组之前的一切修复(jump fix +
  CVT 穿透 + wandered candidate + no-roster)
- **测试**: 34-61 passed(各子集);无红色

### 属性族实验完整弧线
| run | f1 | 关键改动 |
|-----|-----|---------|
| joinfix(基线) | 0.664 | — |
| attrgroup1 | 0.569 | 分组显示,旧 note 丢失 |
| attrgroup2 | 0.587 | note 修复(+旧分类指令) |
| attrfamily1 | 0.591 | 属性提交+全图展开(展开被早验证杀) |
| attrfamily2 | 0.462 | pool 约束+早验证杀属性(核心 bug) |
| **attrfamily3** | **0.603** | 早验证延后,展开真正工作 |

### 待决事项(用户裁决)
1. **属性族方案**:0.603 vs 基线 0.664——差距 6.1pp。源:①CVT 桥接缺口
   (属性展开缺 center→CVT 第一跳)②RELATION_MISMATCH 28 vs 18。
   选项:回退 joinfix / 修展开加桥接 / 接受现状
2. **GTE 维度**:最优 256-384(top1 8%→15%),未实施到生产
3. **约束执行尝试的裁决规则**(1379 微妙性)
4. **OSPD teacher pool**:fact 块收录规则待定

### 产物路径(会丢,重要结论在 SESSION_MEMORY)
- reports/v38_attrfamily3_48x3.json(最新 run)
- reports/v38_joinfix_48x3.json(基线 run)
- tmp/teacher_audit_dump_attrfamily3.txt(最新 dump,18543 行)
- tmp/struct_vars_joinfix.json(基线 IG 链)
- tmp/*_jf.py 系列(joinfix IG 链脚本)
- tmp/dim_test.json + /tmp/rel_embs.npy(维度扫描数据)

### 服务器运维
- vLLM :8000(Qwen3.5-9B, TP2, 0.82 util)
- GTE :8003(Qwen3-Embedding-0.6B, GPU1 与 vLLM 共卡)
- 4核 cgroup(128 核视图但 400000/100000 配额)
- rollout 环境:WALK_POOL=3 WALK_BATCH_WINDOW=0.3
  GTE_CLIENT_BATCH_WINDOW=0.08 GTE_CLIENT_BATCH_FIRST=0.02
  BUBBLE_LLM_CONC=256(大批量) SEQ_ZH_QUESTION=tmp/zh_questions_48.json
  SEQ_CVT_ATTR_TOPK=3(0=off) SEQ_JOIN_GATE=1(0=off)

### 2026-09-15 全量 48×3 首战(全修复栈)
- **f1 0.6967 / hit 79.2%**——历史单轮最高(f1 超 relseq 均值 0.6709
  达 +2.6pp,超旧栈 +4.5pp);hit 79.2% 超三 run 带顶 78.5。
- 判别器家族:deflator **1.00**(历史首满)、Saami **1.00**;
  24353bbc 0.71/027d777f 0.33 持平;1278d3da 0.13(答案层)。
- 单轮 vs 三 run 均值——需复跑确认。r2/r3 待跑。
- **三 run 均值终判**: f1=0.6816/hit=77.8% (spread 0.6640-0.6967/77.1-79.2)
  - **超 relseq-auto +1.1pp** (0.6709→0.6816)
  - **距单步栈仅 0.1pp** (0.6826 vs 0.6816) — 统计上已持平
  - 逐 case vs 单步栈: 赢 18/输 15/平 15
  - **判别器家族决定性**: deflator 0.80, Saami 0.94, tvrage 0.79
    (三 run 稳定,从未达到过的高度)
  - 剩余差距: 1278d3da 0.27 (答案层 tie) + hit 差 2.8pp (精确度)
  - **判决: 新站立配置** (多步栈首次追平单步栈)

### 2026-09-15 十一补:环境块折叠渲染修复(f2906e3)
- 用户发现环境块(one-head-per-line)逐条渲染——Missouri×6行official_symbols
- 修复:同(head, relation)折叠为一行合并尾集(与模式行同格式)
- **1278d3da 0.73(s0=1.0/s2=1.0)——模型首次在 CO2 证据上稳定选出 Belgium**

### 2026-09-15 十二补:实体块渲染(821b8f6)
- **用户设计**:不做候选标记;模式路径做索引行放顶上;三元组按
  实体成块——同实体的全部边(双向)+CVT属性展开归入该实体的块。
- **排序信号**:带判别边的实体优先,然后按度数;锚/上下文最后。
- **值实体不自成块**(日期/数字归入 CVT 载体的块,治 ──1997-08:00── 孤块)。
- **验证**:24353bbc **0.87**(s0=1.0);Nebraska 块自带
  date_adopted=1929+Kind_of_symbol+symbol;Missouri 块自带 1927;
  模型在块内即可比较——不需要跨段拼。
- 1278d3da 0.27(CO2 值行在 CVT 载体块内但模型仍不匹配——
  答案层)。

### 2026-09-15 实体块渲染全量判决
- f1=0.6606/hit=75.7% — 比无实体块的 fullstack 首轮(0.6967)低 3.6pp
- **分型明确**: 24353bbc 0.87/deflator 0.62/Saami 0.83/tvrage 0.67
  (属性比较型受益) vs 1278d3da 0.13(CO2 值匹配型受损)
- **实体块渲染是分型优化的权衡**:
  - 属性比较题(state symbol/date): 实体块赢(信息自包含)
  - 值匹配题(CO2=10.1267): 模式段平铺赢(值行连续可扫)
- **最佳策略:混合渲染** — 实体块做主体+判别值行保持平铺(不塞入块内)
- 当前保留实体块(24353bbc 家族收益大于 1278d3da 损失);
  混合渲染留待下一迭代
