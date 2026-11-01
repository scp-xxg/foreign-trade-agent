# 评测方法

## 数据准备

先用约 10–15 家检查可行性，再积累 50–100 家人工审核样本。这是起步建议，不是统计充分性保证。覆盖不同买家类型和边界情况；真实运营抽样和刻意构造的边界集分开报告。

业务员在不看模型判断时标注 suitable / unsuitable / insufficient，附理由、证据和日期，分歧复核。按域名/集团去重，同一集团不跨校准集和留出集。冻结规则后运行留出集；若根据留出结果调规则，另换留出集。

## 指标和试运行目标

| 指标 | 定义 | 初版目标 |
|---|---|---|
| 推荐准确率 precision | qualified 且 suitable / qualified 且真值可判定 | ≥80% |
| 合格名单真值覆盖率 | qualified 且真值可判定 / 全部 qualified | 同时公开，避免未知标签掩盖问题 |
| 召回率 recall | qualified 且 suitable / 全部 suitable | 与业务基线比较，防止过严漏选 |
| 待核实率 | needs_review / 全部样本 | 监测自动化覆盖，不盲目降低 |
| 硬性条件违规率 | qualified 且人工确认违规 / 全部 qualified | 0，并要求硬条件审核覆盖率100% |
| 事实证据支持率 | 有有效证据支持的事实数 / 被审计事实数 | ≥95%，附审计覆盖率 |
| 可执行规则率 | 有明确字段及核验路径的规则 / 全部规则 | 人工逐条核验 |
| 人工时间降幅 | 1 − 新流程人工秒数 / 原流程人工秒数 | ≥30%，包含核验及纠错 |
| 有效线索单位成本 | 搜索、模型、验证及人工成本 / 确认适合的线索数 | 不劣于原流程 |

以上为建议目标，非行业标准或实测效果。分母为0返回 null。precision 不是全样本 accuracy；脚本同时报告保守适合占比（确认适合 / 全部 qualified），防止未知标签抬高结果。

## 使用计算器

CSV 为 UTF-8，可带 BOM，列名见 ../assets/evaluation-demo.csv：

- case_id：唯一。
- prediction：qualified / rejected / needs_review。
- gold_label：人工真值 suitable / unsuitable / insufficient。
- hard_violation：人工硬条件审核 true / false / unknown；没审核必须 unknown。
- factual_claims / supported_claims：人工审计事实总数和证据支持数，非负整数，后者不大于前者；未审计两项均留空，已审计无事实两项均为0。

在 Skill 目录执行：

```bash
python3 scripts/evaluate.py assets/evaluation-demo.csv --output /tmp/profile-evaluation.json
```

演示数据刻意包含错误及未知情况，仅验证计算逻辑。脚本不核实事实、不生成真值、不自动宣告验收通过。输出分子/分母、混淆矩阵和 precision/recall 的95% Wilson区间，小样本须说明不确定性。

## 人工和业务验收

确认画像能解释买家如何采购/转售；硬条件有依据；搜索计划能执行；判断可追溯；未知项保留。正式运行前替换模板中的演示假设。

固定名单的离线评测不等于搜索产出实验。另用同产品、市场、时间及预算，对比普通搜索和画像指导搜索的有效线索数量、成本、人工时间；记录去重和分组规则。正向回复及询盘率继续追踪，但受到触达、价格和沟通质量影响，不能单独归因于画像。
