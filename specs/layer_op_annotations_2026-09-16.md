# 层操作标注评估集 v2（信息模块对答案的帮助，待人审）

来源: `reports/v06_aligned_full_48x3.json`；脚本: `scripts/annotate_layer_ops.py`；图参照: `/zhaoshu/subgraph/data/cwq_processed/test_v4_repaired.pkl`。

**v2 语义（用户裁定 2026-09-16）**: 评估对象是每次操作交付的信息模块对回答问题的帮助，不是操作形式（extend/update/repeat只是设计侧分类）。

- **helpful（有效）**: 该信息模块在当前序列下推进答案——gold 覆盖增量 p_gain>0（p_gain=本op新增gold覆盖/|gold|），或其新实体被最终命中的 answer 引用（中间链贡献）
- **nohelp-repeat（无效·重复）**: 零新信息（width=0，信息已在序列中）——与操作是否标记 repeat 无关
- **nohelp-irrelevant（无效·无关）**: 有新实体但零 gold 推进、零命中引用
- **harmful-break（有害·断链点）**: 仅未命中 case——Tier2 图参照（锚→gold 最短链并集=有效路径），实际探索第一个偏离有效路径的 op；其后的偏离记 nohelp-irrelevant，在路径上的 op 仍helpful（败在答案层不在游走）

汇总: {'helpful': 22, 'nohelp-repeat': 33, 'nohelp-irrelevant': 91, 'helpful-midchain': 14}；Σp_gain=19.38。Tier2: 0 个未命中 case 有图参照，7 个 gold 图上不可达（无法定断链）。

## 全量层操作表

| case | s | idx | root | action | width | gold | p_gain | on_path | necessary | label |
|---|---|---|---|---|---|---|---|---|---|---|
| WebQTrn-2209_c13 | 0 | 9 | Brad Stevens | extend | 18 | first | 1.0 | adv | yes | helpful |
| WebQTrn-2209_c13 | 1 | 9 | Brad Stevens | extend | 19 | first | 1.0 | adv | yes | helpful |
| WebQTrn-2209_c13 | 1 | 13 | Brad Stevens | extend | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-2209_c13 | 1 | 17 | ? | update layer 1 (replaced | 0 | - | 0.0 | - | no | nohelp-repeat |
| WebQTrn-2209_c13 | 2 | 9 | Brad Stevens | extend | 18 | first | 1.0 | adv | yes | helpful |
| WebQTrn-2209_c13 | 2 | 14 | ? | update layer 1 (replaced | 0 | - | 0.0 | - | no | nohelp-repeat |
| WebQTest-1923_2d | 0 | 9 | Heritage Elementary Scho | extend | 9 | first | 0.294 | adv | yes | helpful |
| WebQTest-1923_2d | 1 | 10 | Heritage Elementary Scho | extend | 9 | first | 0.294 | adv | yes | helpful |
| WebQTest-1923_2d | 2 | 9 | Heritage Elementary Scho | extend | 11 | first | 0.647 | adv | yes | helpful |
| WebQTrn-2576_872 | 0 | 13 | United Kingdom | extend | 21 | re | 0.0 | - | n/a | nohelp-irrelevant |
| WebQTrn-2576_872 | 1 | 9 | Falkland Islands | extend | 35 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2576_872 | 1 | 16 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-2576_872 | 2 | 11 | Falkland Islands | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-1731_4ee | 0 | 13 | Randy Jackson | extend | 9 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-1731_4ee | 0 | 17 | Eclipse Tour | update layer 1 (replaced | 4 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-1731_4ee | 1 | 13 | Randy Jackson | extend | 2 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-1731_4ee | 1 | 17 | ? | update layer 1 (replaced | 11 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-1731_4ee | 2 | 13 | Randy Jackson | update layer 1 (replaced | 10 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-3084_026 | 0 | 9 | Japan | extend | 14 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-3084_026 | 1 | 9 | Japan | extend | 14 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-3084_026 | 2 | 7 | Japan | extend | 14 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-21_6671d | 0 | 9 | Ethiopian birr | extend | 8 | first | 1.0 | adv | yes | helpful |
| WebQTrn-21_6671d | 1 | 9 | Ethiopian birr | extend | 8 | first | 1.0 | adv | yes | helpful |
| WebQTrn-21_6671d | 2 | 9 | Ethiopian birr | extend | 8 | first | 1.0 | adv | yes | helpful |
| WebQTrn-1392_6fb | 0 | 9 | Eleanor Roosevelt | extend | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-1392_6fb | 1 | 9 | Eleanor Roosevelt | extend | 2 | first | 1.0 | adv | yes | helpful |
| WebQTrn-1392_6fb | 2 | 9 | Eleanor Roosevelt | extend | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-567_df97 | 0 | 9 | Ron Howard | extend | 10 | - | 0.0 | - | n/a | nohelp-irrelevant |
| WebQTrn-567_df97 | 0 | 11 | ? | repeat | 0 | - | 0.0 | - | n/a | nohelp-repeat |
| WebQTrn-567_df97 | 0 | 15 | Ron Howard | update layer 2 (replaced | 8 | - | 0.0 | - | n/a | nohelp-irrelevant |
| WebQTrn-567_df97 | 0 | 24 | Child prodigy | extend | 13 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-567_df97 | 1 | 9 | Ron Howard | extend | 18 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-567_df97 | 2 | 9 | Ron Howard | extend | 13 | re | 0.0 | - | yes | helpful-midchain |
| WebQTest-212_016 | 0 | 9 | Colorado River | extend | 44 | first | 1.0 | adv | no | helpful |
| WebQTest-212_016 | 0 | 15 | Colorado River | extend | 100 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-212_016 | 0 | 19 | ? | repeat | 6 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_a52 | 1 | 10 | Charlie Hunnam | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_a52 | 2 | 9 | Charlie Hunnam | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2152_52a | 0 | 9 | American League West | extend | 2 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2152_52a | 1 | 9 | ? | extend | 2 | first | 1.0 | adv | yes | helpful |
| WebQTrn-2152_52a | 2 | 9 | American League West | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-124_6655 | 0 | 9 | Angelina Jolie | extend | 20 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-124_6655 | 1 | 9 | Angelina Jolie | extend | 20 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-124_6655 | 1 | 14 | ? | repeat | 48 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-124_6655 | 2 | 9 | Angelina Jolie | extend | 40 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-3744_1bc | 0 | 9 | Russell Wilson | extend | 1 | first | 1.0 | adv | yes | helpful |
| WebQTrn-3744_1bc | 1 | 9 | Russell Wilson | extend | 1 | first | 1.0 | adv | yes | helpful |
| WebQTrn-3744_1bc | 2 | 9 | Russell Wilson | extend | 1 | first | 1.0 | adv | yes | helpful |
| WebQTrn-2784_b64 | 0 | 14 | Kirk M. Petruccelli | extend | 1 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-2784_b64 | 2 | 17 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-62_bce88 | 0 | 9 | Walt Disney | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-62_bce88 | 0 | 13 | ? | repeat | 2 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-62_bce88 | 0 | 18 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-62_bce88 | 1 | 9 | Walt Disney | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-62_bce88 | 1 | 14 | ? | repeat | 2 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-62_bce88 | 2 | 9 | Walt Disney | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1379_25 | 0 | 9 | ? | extend | 1 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTest-1379_25 | 0 | 13 | ? | extend | 10 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTest-1379_25 | 0 | 18 | ? | extend | 10 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTest-1379_25 | 1 | 13 | Freemasonry | update layer 1 (replaced | 0 | - | 0.0 | ? | n/a | nohelp-repeat |
| WebQTest-1379_25 | 1 | 17 | ? | update layer 1 (replaced | 4 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTest-1379_25 | 1 | 21 | Freemasonry | extend | 0 | - | 0.0 | ? | n/a | nohelp-repeat |
| WebQTest-1379_25 | 1 | 29 | ? | extend | 0 | - | 0.0 | ? | n/a | nohelp-repeat |
| WebQTest-1379_25 | 2 | 13 | Franz Liszt Academy of M | extend | 0 | - | 0.0 | ? | n/a | nohelp-repeat |
| WebQTest-1379_25 | 2 | 20 | ? | extend | 10 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTest-576_130 | 0 | 9 | Central America | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-513_78ac | 0 | 9 | Amanda Rollins | extend | 42 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-513_78ac | 1 | 10 | Amanda Rollins | extend | 65 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-513_78ac | 2 | 10 | Amanda Rollins | extend | 48 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-1557_a48 | 0 | 10 | Charles R. Drew | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-1557_a48 | 1 | 9 | Charles R. Drew | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-1557_a48 | 2 | 9 | Charles R. Drew | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 0 | 9 | Eleanor Roosevelt | extend | 8 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 0 | 13 | Eleanor Roosevelt | update layer 2 (replaced | 3 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 0 | 19 | Eleanor Roosevelt | update layer 2 (replaced | 1 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 1 | 7 | Eleanor Roosevelt | extend | 35 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 1 | 11 | Eleanor Roosevelt | update layer 2 (replaced | 9 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 2 | 9 | Eleanor Roosevelt | extend | 10 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 2 | 14 | Eleanor Roosevelt | update layer 2 (replaced | 3 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2570_195 | 2 | 18 | Eleanor Roosevelt | update layer 2 (replaced | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2540_1af | 0 | 9 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-2540_1af | 1 | 9 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-2540_1af | 2 | 9 | ? | repeat | 0 | re | 0.0 | - | n/a | nohelp-repeat |
| WebQTrn-2319_cdb | 2 | 9 | Acting Prime Minister of | extend | 24 | first | 1.0 | adv | yes | helpful |
| WebQTrn-2319_cdb | 2 | 15 | Acting Prime Minister of | update layer 2 (replaced | 0 | - | 0.0 | - | no | nohelp-repeat |
| WebQTest-537_80c | 0 | 15 | Charlie Hunnam | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_80c | 1 | 10 | Charlie Hunnam | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_80c | 2 | 10 | Charlie Hunnam | extend | 6 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1840_3d | 0 | 12 | Norway | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1840_3d | 1 | 10 | Norway | extend | 11 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1840_3d | 2 | 9 | Norway | extend | 8 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-60_6b8ef | 1 | 9 | Portuguese Language | extend | 16 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-60_6b8ef | 2 | 9 | Portuguese Language | extend | 16 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-626_01a | 0 | 9 | Tempus Unbound | extend | 40 | re | 0.0 | - | yes | helpful-midchain |
| WebQTest-626_01a | 1 | 9 | Tempus Unbound | extend | 31 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-626_01a | 1 | 13 | Tempus Unbound | extend | 21 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-626_01a | 2 | 13 | Tempus Unbound | extend | 91 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-241_a609 | 0 | 9 | France | extend | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-241_a609 | 0 | 14 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-241_a609 | 1 | 9 | France | extend | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-241_a609 | 1 | 12 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-241_a609 | 2 | 9 | France | extend | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTest-1797_2f | 0 | 10 | Siege of Vicksburg | extend | 33 | first | 1.0 | adv | yes | helpful |
| WebQTest-1797_2f | 0 | 15 | ? | repeat | 0 | - | 0.0 | - | no | nohelp-repeat |
| WebQTest-1797_2f | 1 | 10 | Siege of Vicksburg | extend | 31 | first | 1.0 | adv | yes | helpful |
| WebQTest-1797_2f | 1 | 15 | Siege of Vicksburg | update layer 2 (replaced | 3 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1797_2f | 2 | 13 | Siege of Vicksburg | extend | 36 | first | 1.0 | adv | yes | helpful |
| WebQTest-1797_2f | 2 | 17 | Siege of Vicksburg | update layer 2 (replaced | 1 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1470_88 | 0 | 11 | Poland | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1470_88 | 1 | 14 | Nelson Mandela | extend | 1 | re | 0.0 | - | n/a | nohelp-irrelevant |
| WebQTest-626_743 | 2 | 9 | Missouri River | extend | 7 | re | 0.143 | - | no | helpful |
| WebQTrn-452_f79f | 0 | 9 | Michelle Anthony | extend | 14 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTrn-452_f79f | 0 | 14 | Michelle Anthony | extend | 3 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTrn-452_f79f | 1 | 10 | Carmelo Anthony | extend | 6 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTrn-452_f79f | 1 | 16 | ? | update layer 1 (replaced | 10 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTrn-452_f79f | 2 | 10 | Carmelo Anthony | extend | 0 | - | 0.0 | ? | n/a | nohelp-repeat |
| WebQTrn-452_f79f | 2 | 14 | Carmelo Anthony | extend | 6 | - | 0.0 | ? | n/a | nohelp-irrelevant |
| WebQTest-626_525 | 0 | 11 | Missouri River | extend | 7 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-626_525 | 0 | 16 | Missouri River | update layer 2 (replaced | 3 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-626_525 | 2 | 9 | Missouri River | extend | 6 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-626_525 | 2 | 11 | Missouri River | update layer 2 (replaced | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-626_525 | 2 | 13 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-25_db969 | 0 | 9 | Taylor Lautner | extend | 7 | re | 0.0 | - | yes | helpful-midchain |
| WebQTest-537_434 | 0 | 10 | Charlie Hunnam | extend | 2 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_434 | 1 | 10 | Charlie Hunnam | extend | 2 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_434 | 1 | 14 | Charlie Hunnam | update layer 2 (replaced | 3 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_434 | 1 | 19 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTest-537_434 | 1 | 23 | ? | update layer 2 (replaced | 1 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_434 | 1 | 28 | Charlie Hunnam | extend | 2 | - | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-537_434 | 2 | 10 | Charlie Hunnam | extend | 2 | re | 0.0 | - | yes | helpful-midchain |
| WebQTest-537_434 | 2 | 19 | Charlie Hunnam | update layer 2 (replaced | 6 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTest-1171_08 | 0 | 10 | Darth Vader | extend | 9 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-124_9a35 | 1 | 9 | Angelina Jolie | extend | 6 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-25_7cec3 | 0 | 15 | Taylor Lautner | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-25_7cec3 | 0 | 22 | ? | repeat | 6 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-25_7cec3 | 1 | 16 | Taylor Lautner | extend | 12 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-25_7cec3 | 2 | 10 | Taylor Lautner | extend | 17 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-25_892ff | 0 | 9 | ? | extend | 3 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-25_892ff | 0 | 16 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-25_892ff | 1 | 13 | ? | extend | 3 | first | 1.0 | adv | yes | helpful |
| WebQTrn-2784_3a1 | 0 | 10 | Tupac Shakur | extend | 12 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2784_3a1 | 0 | 19 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-2784_3a1 | 1 | 9 | Tupac Shakur | extend | 13 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-2784_3a1 | 2 | 10 | Tupac Shakur | extend | 12 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-452_5b0f | 1 | 13 | ? | update layer 1 (replaced | 1 | re | 0.0 | - | yes | helpful-midchain |
| WebQTrn-452_5b0f | 1 | 17 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |
| WebQTrn-452_5b0f | 2 | 11 | ? | repeat | 2 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-452_5b0f | 2 | 21 | ? | extend | 47 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-567_11fd | 0 | 9 | Ron Howard | extend | 4 | - | 0.0 | - | n/a | nohelp-irrelevant |
| WebQTrn-567_11fd | 0 | 12 | ? | repeat | 3 | - | 0.0 | - | n/a | nohelp-irrelevant |
| WebQTrn-567_11fd | 1 | 8 | Ron Howard | extend | 0 | - | 0.0 | ? | n/a | nohelp-repeat |
| WebQTrn-567_11fd | 2 | 9 | Ron Howard | extend | 22 | - | 0.0 | - | n/a | nohelp-irrelevant |
| WebQTrn-241_97bf | 0 | 9 | France | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-241_97bf | 1 | 9 | France | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-241_97bf | 2 | 10 | France | extend | 1 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-452_343e | 0 | 7 | ? | repeat | 0 | - | 0.0 | - | no | nohelp-repeat |
| WebQTrn-452_343e | 0 | 11 | Carmelo Anthony | extend | 0 | - | 0.0 | - | no | nohelp-repeat |
| WebQTrn-452_343e | 0 | 15 | ? | repeat | 14 | first | 1.0 | adv | no | helpful |
| WebQTrn-452_343e | 0 | 19 | Carmelo Anthony | extend | 10 | re | 0.0 | - | no | nohelp-irrelevant |
| WebQTrn-452_343e | 0 | 23 | ? | repeat | 0 | re | 0.0 | - | no | nohelp-repeat |

## 按家族汇总

| family | s | f1 | hit | #ops | labels |
|---|---|---|---|---|---|
| WebQTrn-2209_c1374f3 | 0 | 0.11 | True | 1 | {'helpful': 1} |
| WebQTrn-2209_c1374f3 | 1 | 0.11 | True | 3 | {'helpful': 1, 'nohelp-repeat': 2} |
| WebQTrn-2209_c1374f3 | 2 | 0.11 | True | 2 | {'helpful': 1, 'nohelp-repeat': 1} |
| WebQTest-1923_2d0773 | 0 | 0.46 | True | 1 | {'helpful': 1} |
| WebQTest-1923_2d0773 | 1 | 0.00 | False | 1 | {'helpful': 1} |
| WebQTest-1923_2d0773 | 2 | 0.00 | False | 1 | {'helpful': 1} |
| WebQTrn-2576_872253e | 0 | 0.00 | False | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-2576_872253e | 1 | 1.00 | True | 2 | {'nohelp-irrelevant': 1, 'nohelp-repeat': 1} |
| WebQTrn-2576_872253e | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-1731_4eea981 | 0 | 1.00 | True | 2 | {'helpful-midchain': 1, 'nohelp-irrelevant': 1} |
| WebQTrn-1731_4eea981 | 1 | 0.80 | True | 2 | {'helpful-midchain': 1, 'nohelp-irrelevant': 1} |
| WebQTrn-1731_4eea981 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-3084_026bed8 | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-3084_026bed8 | 1 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-3084_026bed8 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-21_6671d5347 | 0 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-21_6671d5347 | 1 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-21_6671d5347 | 2 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-1392_6fb4733 | 0 | 1.00 | True | 1 | {'nohelp-repeat': 1} |
| WebQTrn-1392_6fb4733 | 1 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-1392_6fb4733 | 2 | 1.00 | True | 1 | {'nohelp-repeat': 1} |
| WebQTrn-567_df97b91c | 0 | 0.00 | False | 4 | {'nohelp-irrelevant': 3, 'nohelp-repeat': 1} |
| WebQTrn-567_df97b91c | 1 | 0.00 | False | 1 | {'helpful-midchain': 1} |
| WebQTrn-567_df97b91c | 2 | 1.00 | True | 1 | {'helpful-midchain': 1} |
| WebQTest-212_01600f3 | 0 | 0.50 | True | 3 | {'helpful': 1, 'nohelp-irrelevant': 2} |
| WebQTest-537_a52d362 | 1 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-537_a52d362 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-2152_52aec01 | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-2152_52aec01 | 1 | 0.00 | False | 1 | {'helpful': 1} |
| WebQTrn-2152_52aec01 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-124_6655b537 | 0 | 1.00 | True | 1 | {'helpful-midchain': 1} |
| WebQTrn-124_6655b537 | 1 | 1.00 | True | 2 | {'helpful-midchain': 2} |
| WebQTrn-124_6655b537 | 2 | 1.00 | True | 1 | {'helpful-midchain': 1} |
| WebQTrn-3744_1bc38ed | 0 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-3744_1bc38ed | 1 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-3744_1bc38ed | 2 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-2784_b64250a | 0 | 1.00 | True | 1 | {'helpful-midchain': 1} |
| WebQTrn-2784_b64250a | 2 | 0.00 | False | 1 | {'nohelp-repeat': 1} |
| WebQTrn-62_bce880153 | 0 | 1.00 | True | 3 | {'nohelp-irrelevant': 2, 'nohelp-repeat': 1} |
| WebQTrn-62_bce880153 | 1 | 1.00 | True | 2 | {'nohelp-irrelevant': 2} |
| WebQTrn-62_bce880153 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-1379_255da8 | 0 | 0.00 | False | 3 | {'nohelp-irrelevant': 3} |
| WebQTest-1379_255da8 | 1 | 0.00 | False | 4 | {'nohelp-repeat': 3, 'nohelp-irrelevant': 1} |
| WebQTest-1379_255da8 | 2 | 0.00 | False | 2 | {'nohelp-repeat': 1, 'nohelp-irrelevant': 1} |
| WebQTest-576_13008c4 | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-513_78acb100 | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-513_78acb100 | 1 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-513_78acb100 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-1557_a4800ce | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-1557_a4800ce | 1 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-1557_a4800ce | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-2570_195e50e | 0 | 0.67 | True | 3 | {'nohelp-irrelevant': 3} |
| WebQTrn-2570_195e50e | 1 | 1.00 | True | 2 | {'nohelp-irrelevant': 2} |
| WebQTrn-2570_195e50e | 2 | 1.00 | True | 3 | {'nohelp-irrelevant': 3} |
| WebQTrn-2540_1af5839 | 0 | 1.00 | True | 1 | {'nohelp-repeat': 1} |
| WebQTrn-2540_1af5839 | 1 | 0.67 | True | 1 | {'nohelp-repeat': 1} |
| WebQTrn-2540_1af5839 | 2 | 1.00 | True | 1 | {'nohelp-repeat': 1} |
| WebQTrn-2319_cdbcc6b | 2 | 0.25 | True | 2 | {'helpful': 1, 'nohelp-repeat': 1} |
| WebQTest-537_80c32b0 | 0 | 0.50 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-537_80c32b0 | 1 | 0.50 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-537_80c32b0 | 2 | 0.50 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-1840_3d474a | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-1840_3d474a | 1 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-1840_3d474a | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-60_6b8ef173b | 1 | 0.50 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-60_6b8ef173b | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-626_01ad908 | 0 | 1.00 | True | 1 | {'helpful-midchain': 1} |
| WebQTest-626_01ad908 | 1 | 1.00 | True | 2 | {'nohelp-irrelevant': 2} |
| WebQTest-626_01ad908 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-241_a6090427 | 0 | 1.00 | True | 2 | {'nohelp-repeat': 2} |
| WebQTrn-241_a6090427 | 1 | 1.00 | True | 2 | {'nohelp-repeat': 2} |
| WebQTrn-241_a6090427 | 2 | 1.00 | True | 1 | {'nohelp-repeat': 1} |
| WebQTest-1797_2fb9e2 | 0 | 0.00 | False | 2 | {'helpful': 1, 'nohelp-repeat': 1} |
| WebQTest-1797_2fb9e2 | 1 | 0.00 | False | 2 | {'helpful': 1, 'nohelp-irrelevant': 1} |
| WebQTest-1797_2fb9e2 | 2 | 0.00 | False | 2 | {'helpful': 1, 'nohelp-irrelevant': 1} |
| WebQTest-1470_888604 | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-1470_888604 | 1 | 0.00 | False | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-626_74344bd | 2 | 0.73 | True | 1 | {'helpful': 1} |
| WebQTrn-452_f79ffe93 | 0 | 0.00 | False | 2 | {'nohelp-irrelevant': 2} |
| WebQTrn-452_f79ffe93 | 1 | 0.00 | False | 2 | {'nohelp-irrelevant': 2} |
| WebQTrn-452_f79ffe93 | 2 | 0.00 | False | 2 | {'nohelp-repeat': 1, 'nohelp-irrelevant': 1} |
| WebQTest-626_5258a16 | 0 | 0.50 | True | 2 | {'nohelp-irrelevant': 2} |
| WebQTest-626_5258a16 | 2 | 0.80 | True | 3 | {'nohelp-irrelevant': 2, 'nohelp-repeat': 1} |
| WebQTrn-25_db9695c22 | 0 | 1.00 | True | 1 | {'helpful-midchain': 1} |
| WebQTest-537_4346bf5 | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTest-537_4346bf5 | 1 | 1.00 | True | 5 | {'nohelp-irrelevant': 4, 'nohelp-repeat': 1} |
| WebQTest-537_4346bf5 | 2 | 1.00 | True | 2 | {'helpful-midchain': 1, 'nohelp-irrelevant': 1} |
| WebQTest-1171_08b211 | 0 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-124_9a3568f8 | 1 | 1.00 | True | 1 | {'helpful-midchain': 1} |
| WebQTrn-25_7cec3b1d3 | 0 | 0.40 | True | 2 | {'nohelp-irrelevant': 2} |
| WebQTrn-25_7cec3b1d3 | 1 | 0.00 | False | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-25_7cec3b1d3 | 2 | 0.33 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-25_892ff2031 | 0 | 1.00 | True | 2 | {'nohelp-irrelevant': 1, 'nohelp-repeat': 1} |
| WebQTrn-25_892ff2031 | 1 | 1.00 | True | 1 | {'helpful': 1} |
| WebQTrn-2784_3a12729 | 0 | 1.00 | True | 2 | {'nohelp-irrelevant': 1, 'nohelp-repeat': 1} |
| WebQTrn-2784_3a12729 | 1 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-2784_3a12729 | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-452_5b0f29b4 | 1 | 0.67 | True | 2 | {'helpful-midchain': 1, 'nohelp-repeat': 1} |
| WebQTrn-452_5b0f29b4 | 2 | 1.00 | True | 2 | {'nohelp-irrelevant': 2} |
| WebQTrn-567_11fd073d | 0 | 0.00 | False | 2 | {'nohelp-irrelevant': 2} |
| WebQTrn-567_11fd073d | 1 | 0.00 | False | 1 | {'nohelp-repeat': 1} |
| WebQTrn-567_11fd073d | 2 | 0.00 | False | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-241_97bfe74d | 0 | 0.00 | False | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-241_97bfe74d | 1 | 0.00 | False | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-241_97bfe74d | 2 | 1.00 | True | 1 | {'nohelp-irrelevant': 1} |
| WebQTrn-452_343ed3d9 | 0 | 1.00 | True | 5 | {'nohelp-repeat': 3, 'helpful': 1, 'nohelp-irrelevant': 1} |
