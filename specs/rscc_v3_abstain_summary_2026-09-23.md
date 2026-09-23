# RSCC v3 abstain 通路人审摘要 — 2026-09-23

scorer v3(RSCC_TAU_LIFT=0.02): 通路 lift 锚 L=p_F(本通路)−p0 全 gold < τ 时
整条通路概率通道 abstain(弃权保留)。本表供人审 τ_lift 校准。

## abstain 通路总数: 57  |  负 lift(L_max<0,证据有害): 55  |  零/微 lift(合取型,|L|≈0): 2

## A. 零/微 lift 型(合取候选 — 1731 同型,真弃权合理)
case                           branch             L(per-gold)
WebQTest-576_906ad6be7bec9d2   central america    [+0.017 -0.048 -0.087 -0.003 -0.003 -0.016]
WebQTrn-1864_67ecd1c247c3b2c   anadyr time zone   [+0.002]

## B. 负 lift 型(通路证据压低 gold 概率 — v2.1 harmful 家族,弃权语义待裁定)
case                           branch             L(per-gold)          abstain块
WebQTest-1384_744a496b907e40   ovadia yosef       [-0.048            ] 块0
WebQTest-1384_744a496b907e40   ovadia yosef       [-0.012            ] 块0
WebQTest-1384_744a496b907e40   ovadia yosef       [-0.012            ] 块0
WebQTest-1686_29e74083744b36   arizona            [-0.195            ] 块0
WebQTest-1686_29e74083744b36   george w p hunt    [-0.196            ] 块1
WebQTest-1797_68a33792b0a1e1   montgomery         [-0.099            ] 块1
WebQTest-1797_68a33792b0a1e1   montgomery         [-0.087            ] 块1
WebQTest-538_49b4e9304f18a0a   west reading el    [-0.055 -0.009 -0.013 -0.002 -0.006] 块0
WebQTest-538_49b4e9304f18a0a   west reading el    [-0.054 -0.009 -0.012 -0.002 -0.006] 块0
WebQTest-538_49b4e9304f18a0a   west reading el    [-0.055 -0.010 -0.012 -0.002 -0.007] 块0
WebQTest-576_01e2da60a2779c4   central america    [-0.129            ] 块1
WebQTest-576_01e2da60a2779c4   central america    [-0.123            ] 块1
WebQTest-590_6aad73acb74f304   libya libya liby   [-0.046            ] 块0
WebQTest-590_6aad73acb74f304   libya libya liby   [-0.043            ] 块0
WebQTest-590_6aad73acb74f304   prime minister o   [-0.002            ] 块1,2
WebQTest-590_6aad73acb74f304   libya libya liby   [-0.044            ] 块1
WebQTest-61_09020cbb000c86fd   indonesia          [-0.026            ] 块0
WebQTrn-1077_0c34ca057060e35   badakhshan provi   [-0.037 -0.025     ] 块0
WebQTrn-1077_0c34ca057060e35   badakhshan provi   [-0.036 -0.024     ] 块0
WebQTrn-1077_0c34ca057060e35   badakhshan provi   [-0.036 -0.024     ] 块0
WebQTrn-1077_f4a9e5f1e0dcfb8   afghan national    [-0.018 -0.027     ] 块0
WebQTrn-1077_f4a9e5f1e0dcfb8   afghan national    [-0.017 -0.027     ] 块0
WebQTrn-1077_f4a9e5f1e0dcfb8   afghan national    [-0.018 -0.027     ] 块0
WebQTrn-1259_1997cb4922db719   country nation w   [-0.006            ] 块0
WebQTrn-1259_1997cb4922db719   country nation w   [-0.006            ] 块0
WebQTrn-1259_1997cb4922db719   country nation w   [-0.006            ] 块0
WebQTrn-1864_9dc4e22121d3a46   country            [-0.002            ] 块1
WebQTrn-1864_9dc4e22121d3a46   asean common tim   [-0.000            ] 块0,1
WebQTrn-2069_0fa727f3b282196   michelle bachele   [-0.007 -0.020 -0.000 -0.015 -0.005] 块0
WebQTrn-2069_0fa727f3b282196   m 0n8r1qn          [-0.008 -0.019 -0.000 -0.018 -0.006] 块2
WebQTrn-2069_0fa727f3b282196   michelle bachele   [-0.007 -0.019 -0.000 -0.013 -0.006] 块0,1
WebQTrn-2069_0fa727f3b282196   michelle bachele   [-0.007 -0.019 -0.000 -0.012 -0.005] 块0,1
WebQTrn-21_660138373d19bbffd   dire dawa          [-0.327            ] 块0,1
WebQTrn-21_660138373d19bbffd   dire dawa          [-0.321            ] 块0,1
WebQTrn-21_660138373d19bbffd   dire dawa          [-0.330            ] 块0,1
WebQTrn-241_dfb6c97ac9bf2f0a   nijmegen           [-0.029            ] 块1
WebQTrn-241_dfb6c97ac9bf2f0a   nijmegen           [-0.027            ] 块1
WebQTrn-2722_8babdaa9ecd05a7   dewitt high scho   [-0.013            ] 块1
WebQTrn-2722_8babdaa9ecd05a7   dewitt high scho   [-0.004            ] 块1
WebQTrn-3100_143c89d70679c3e   dominican republ   [-0.072            ] 块0
WebQTrn-3100_143c89d70679c3e   dominican republ   [-0.070            ] 块0
WebQTrn-3136_a2debf685e0c504   down district co   [-0.065            ] 块1
WebQTrn-557_960c16ffdb29e173   winged monkey 7    [-0.058            ] 块2
WebQTrn-557_960c16ffdb29e173   winged monkey 7    [-0.045            ] 块1
WebQTrn-557_960c16ffdb29e173   winged monkey 7    [-0.065            ] 块1
WebQTrn-567_693feb48c0515cd0   ron howard         [-0.002            ] 块0
WebQTrn-567_693feb48c0515cd0   ron howard         [-0.002            ] 块0
WebQTrn-567_693feb48c0515cd0   ron howard         [-0.002            ] 块0
WebQTrn-662_7a992044f94b39ed   2008 fifa club w   [-0.022            ] 块0
WebQTrn-662_7a992044f94b39ed   2008 fifa club w   [-0.029            ] 块0
WebQTrn-662_7a992044f94b39ed   2008 fifa club w   [-0.019            ] 块0
WebQTrn-710_c264a6d11d795674   larry baer         [-0.043            ] 块0
WebQTrn-962_032f61bfcfed69da   jenny s father     [-0.005            ] 块1
WebQTrn-962_032f61bfcfed69da   jenny s father     [-0.004            ] 块1
WebQTrn-962_032f61bfcfed69da   jenny s father     [-0.009            ] 块1
