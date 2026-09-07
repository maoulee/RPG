# 图证据展示 V3.5 设计草案(2026-08-31,供人工审核)

依据裁决:关系签名合并组 / 实例路径前缀树 / 无边展示 / 去重实体上限 /
候选=实例端点 / note 移出 ack / 变量标签优先、center 不截断。

## 文法

```
子图头:  fact: sgN.fM   var: ?x(展开 center 数)   [组数]
组头:    ▸ 关系[|变体...]  N实例/M去重实体          ← 同一关系的全部
                                                       模式变体合并为一组
实体树:  缩进=一跳;同父兄弟用 " | " 连一行;
         链延伸 = 子行缩进(trie:共享前缀只写一次)
CVT:     m.xxx [k=v; ...] 首次全写;再出现只写 id
尾集:    >12 个折叠为 "代表3个 + 计数";答案类型相关终实体优先
note:    移到系统提示(一次性);ack 纯证据
候选:    候选 = 实例端点,一行计数;不再罗列
```

## 标本一:Missouri River(超级关系膨胀)

**现在(~40 行,重复逆块+35实体单行)**:
```
Missouri River --near_travel_destination--> Bismarck --contains--> Aakers Business College, Bismarck Cathedral Area Historic District | Bismarck Civic Auditorium | ...(35个)
[partially_containedby --adjoin_s]  (26 instances)
  Missouri River --partially_containedby--> Iowa --adjoin_s--> m.02tbl_w [adjoins=North Dakota; adjoins=South Dakota] | m.02tbm0j [...] | ...(11个全括号)
[<--partially_contains --adjoin_s]  (26 instances)
  Missouri River <--partially_contains-- Iowa --adjoin_s--> m.02tbl_w | m.02tbm0j | ...(同批记录重列)
```

**V3.5(逆变体并组 + trie + CVT 复用)**:
```
fact: sg1.f1  var: ?x
▸ near_travel_destination→contains  35实例/38实体
  Missouri River
    → Bismarck
        ⊃ Aakers Business College | Bismarck Cathedral Area HD | Bismarck Civic Auditorium | +32
▸ partially_containedby(∪ partially_contains)  26实例/11实体
  Missouri River
    ⊃ Iowa
        ⊳ adjoin_s: m.02tbl_w [adjoins=ND; SD] | m.02tbm0j | m.02th1cp | m.02th04h | +7
    ⊃ Kansas
        ⊳ adjoin_s: m.02tgy1h | m.02tbm09 | +5
    ⊃ Missouri
        ⊳ adjoin_s: m.02th1cp | m.02tgv4f | +7
候选: 49(=实例端点,去重)
```
要点:两个逆块 → 一组;11 条 CVT 记录只写一次;35 实体折叠为代表+计数;
"⊃"= containment 类关系的树形子行(无边展示)。

## 标本二:Seth MacFarlane(多模式合并 + 精确枚举)

**现在**:4 个模式各渲染,候选行 25 个实体,Lion-O 只在"no visible edge"标记里。

**V3.5(两轮游走后)**:
```
fact: sg2.f1  var: ?character
▸ fictional_characters_created(∪ character_created_by)  31实例/21实体
  Seth MacFarlane
    ⊳ created: Avery Bullock | Brian Griffin | Chris Griffin | Cleveland Brown | +17
▸ tv 出演→角色(∪ 反向)  8实例/9实体        ← 精确枚举(beam 曾只见1)
  Seth MacFarlane
    ⊳ actor: m.05st1cc [Family Guy; Voice] | m.0wz3f15 [Robot Chicken] | +6
      m.0wz3f15 ⊳ character: Lion-O          ← 实例路径在树里自然可见
      m.05st1cc ⊳ character: g.120yrd_6
候选: 30(=实例端点)
```
要点:创造与出演各自成组(不同关系签名);Lion-O 作为实例端点出现在树里,
"no visible edge"类别消失;候选行只是一行计数。

## 标本三:Rome(containedby 交叉积)

**现在**:`Rome <--containedby-- ?x (52 instances)` 多行交叉重列。

**V3.5**:
```
▸ containedby  52实例/9实体
  Rome
    ⊂ Italy
        ⊃ Abruzzo | Tuscany | Lombardy | +14        ← 共享前缀一次
    ⊂ Lazio
        ⊃ Rome | Province of Rome
    ⊂ Metropolitan City of Rome
候选: 9
```
要点:交叉积坍缩为树;上限按 9 个去重实体而非 52 行。

## 不变量(V3.5 验收)
I1 单次打印:任何 (h,r,t) 恰一次(跨模式/跨变体);
I2 展示 ⊇ 精确枚举产出(两轮游走后构造成立);
I3 候选 = 实例端点(去重);
I4 折叠只发生在尾集且带显式计数;
I5 组 = 关系签名(变体合并),树深度 = 路径跳数。

## 多跳分叉渲染(2026-08-31 补,用户审核点)

问题:3 跳路径,前两跳相同、末跳关系一致但实体变化 → 多条路径;中跳也可能分叉。

**渲染单位 = (路径前缀, 剩余关系签名) 的等价类**。规则:

R1 前缀共享:相同前缀链只写一次(竖直树,│├└ 连接符);
R2 中跳分叉:分叉节点用 ├─ 并列,各自子树;
R3 **同签名尾合并**:分叉兄弟的尾集相同时上提——
```
  A
  ├─ B1 | B2 | B3                ← 尾集相同的兄弟合并
  │    └─ ⊳ rel3: t1 | t2 | +12
```
R4 **异尾分叉展开**:尾集不同则各自子树——
```
  A
  ├─ B1
  │    └─ ⊳ rel3: t1 | t2 | +12
  ├─ B2
  │    └─ ⊳ rel3: +8
  └─ B3
       └─ ⊳ rel3: t9 | t10
```
R5 分叉爆炸压缩:分叉数 >6 → 按实例数排序,展 top-5 +
`└─ +N forks(各 M_i 实例)`;答案类型相关分叉永不折叠;
R6 尾集折叠阈值 12 不变;R7 树深度=跳数,CVT 中介算一跳。

**机械性**:精确枚举的实例路径列表 → 建 trie → 应用 R3-R5 压缩 →
渲染。无人工干预,直接可编程。

### 三跳真实例(Freebase 结构,A=中心)
```
▸ country→administrative_divisions→country  47实例/31实体
  Rome
  ├─ Italy
  │    └─ ⊳ divisions: Abruzzo | Tuscany | Lombardy | +14
  ├─ Lazio
  │    └─ ⊳ divisions: Rome | Province of Rome
  └─ Metropolitan City of Rome
       └─ ⊳ contains: Rome
```
(前缀共享一次;Italy 的 17 个行政区是一行尾集而非 17 行;
三个中跳分叉各自的尾集不同 → R4 各自子树。)

## 方向约定(2026-08-31 补二,用户审核点:反向怎么办)

两个机制:

D1 **组内方向规范化**:schema 逆对(partially_contains /
partially_containedby 这类互逆关系名)在并组时**改写为规范方向**,
树内统一单向——这正是它们能合并为一组的前提;x --p_contains--> y
≡ y --p_containedby--> x,保留一个规范名一个方向。

D2 **逐跳方向连接符**:真正的混合方向模式(一跳正一跳反,如
Seth 的 出演→角色→创造者)每个树级带方向连接符:
  `─rel─▶`  父 --rel--> 本节点(正向)
  `◀─rel─`  本节点 --rel--> 父(反向:子是边的 SUBJECT)

**trie 合并判据含方向**:(父, 关系, 方向) 三元签名——同关系不同
方向**不合并**(它们是不同签名)。

### 例:Seth 的三跳混合方向模式(反向→正向→反向)
```
▸ 出演→角色→创造者  8实例/9实体
Seth MacFarlane
  ◀─actor─ m.05st1cc [Family Guy; Voice] | m.0wz3f15 [Robot Chicken] | +6
      m.05st1cc ──character──▶ g.120yrd_6
      m.0wz3f15 ──character──▶ Lion-O
          Lion-O ◀─created_by─ Tobin Wolf
```
读法:m.0wz3f15 --actor--> Seth(反向,子是主语);m.0wz3f15
--character--> Lion-O(正向);Tobin Wolf --created_by--> Lion-O?
不——Lion-O ◀─created_by─ Tobin Wolf 读作 **Tobin Wolf --created_by-->
的反向,即该边为 Lion-O --created_by--> Tobin Wolf?规范:◀ 标记
永远读"子 --rel--> 父"。故此行 = Lion-O --created_by--> Tobin Wolf
✓(Lion-O 的创造者是 Tobin Wolf,与 KG 一致)。

Rome 例的 `⊂` 同理升级为显式连接符:
```
▸ containedby  52实例/9实体
Rome
  ◀─containedby─ Italy        ← Italy --containedby--> Rome? 否:
```
containedby 的存储方向是 (x, containedby, Rome)——即子节点 Italy
--containedby--> 父 Rome,`◀─containedby─` 语义成立 ✓。全部
`⊃/⊂/→/←` 简写统一替换为 `─rel─▶` / `◀─rel─` 两种带关系名的
连接符(简写只用于组头摘要)。
