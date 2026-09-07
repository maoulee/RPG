# 模块行为分类器全息审计(2026-08-29,子智能体独立审计,主线程存档)

审计范围:unified_classifier.py 现行代码 + 全部裁决(§6.12-6.25, R1-R9)
+ 消解链条(abstain_resolve/pair_loo/dump_all_classes)交叉验证。
结论:加权融合定类机制本身是漂移根源,建议改布尔格判定。

## 核心发现(四大硬矛盾)
1. **chain+repeat → 终局 red(20 个)**:同时违反裁决 #16(链不可分⟹eff)
   和 R9(结构票单独不定案应交概率层)——既非 eff 也无复核,刀锋算术
   (1.0−0.6=0.4<0.5)直接终局。
2. **255 个模块由单票终局定案**(repeat→red 160、gold_adj→eff 46…),
   与"综合判定不单测"的立国原则直接矛盾。
3. **gold_adj+repeat+dI≈0 → red(13 个)**:R8 定义的最强正信号被一个
   零读数概率推翻——"确定性胜噪声"反向实现。
4. **§6.24 保护双重失效**:big_dg 参数从未接线(死参数);大|ΔG|离路径
   约束模块经 repeat 票落 red——#17/§6.24 两轮人工审计盯住的标本类
   正被批量误标。

## 其他缺陷
- 死代码:gold_bearing 否决块、own_path 导入、unused 票(连通域不可达);
- sig 门在不连通分支失效(fallback dg_rel=原始|ΔG|,枢纽膨胀放行);
- lx 展示层 necessary 以权重 1.0 OR 进环境票(被 §6.20 废弃的层);
- 四种"小增量"语义并存(ENV_MIN=3 / dg_rel==0 / |ΔG|≤3 / ≤10);
- gpath 仍是单条 BFS(枢纽劫持在黄金参照上未修);
- joint_eff 不升级搭档、carrier 无 R2 所有权、第一层 red 永不复核
  ——同行为不同标签取决于落层;
- dI 只按 golds[0]、dI=None 落 red "noise" ——多实体问题口径漂移;
- **tmp 数据跨代混接**(pair_loo.json 早于现役 unified_class.json)。

## 规范化程序建议(布尔格,保留全部 9 条裁决)
```
gain     = (dg_rel ≥ 1) ∨ (dI > θ) ∨ (alone > θ)     # 增益二分
measured = dI ≠ None
1. harm    ⟺ 意图负票(div ∨ (dI<−θ ∧ ¬gold_bearing))
2. eff     ⟺ gain ∧ ≥1 结构/意图票(necessary ∨ chain ∨ 首载 ∨ gold_adj
            ∨ sig ∨ constraint-被使用)
3. red     ⟺ ¬gain ∧ measured
4. abstain ⟺ ¬measured(无条件,不论 |ΔG| 与结构票)
5. 消解:成对 dI_pair>θ ⇒ 双方 eff;joint 搭档同步升级;carrier(R2
   所有权)⇒ eff;其余不训
6. 权重仅做置信排序与训练过滤,不参与类别判定
```
丢弃:加权融合定类(±0.5 阈值/中间默认 red/tot/conf 门)、ENV_MIN=3 与
≤10 双阈值、big_dg 特例、文本回退(走 abstain)、lx 展示层 necessary。
保留:θ=0.005、gold-bearing 否决(限 loo_neg 语义)、R2 所有权(统一)。

## 训练批次前 Top 5 风险
1. tmp 数据跨代混接(切批次前必须重跑 pair_loo→dumps);
2. red 是终局且是冲突默认值(约 14-15% 模块刀锋定案,难组下冗余价
   系统性压制检索——§6.2 警告的失败模式);
3. 约束模块群体被批量误标 red(§6.11 找回的 A_max 对象被污染);
4. 轨迹内标签矛盾直接进梯度(rr+sg 单元继承);
5. 概率层口径漂移(单 gold、None→red)。
