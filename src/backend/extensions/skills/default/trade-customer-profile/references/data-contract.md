# 数据约定和决策算法

输入模板为字段提示，不是强制表单。输出结构见 ../assets/profile-output.json。

## 顶层输出字段

- schema_version：当前为 1.0；profile_id 为稳定 ID，version 随规则修改更新，created_at 为带时区时间。
- status：draft / calibrated / evaluated。
- merchant_facts：field、value、evidence_ids；未知 value 为 null。
- buyer_profiles：id、buyer_type、markets、fit_reason、constraints、hypotheses。
- search_plan：market、language、queries、channels、rule_ids、validation_status。
- evidence：id、type（user_statement / document / public_source）、locator（路径及页码或 URL）、excerpt、source_date、retrieved_at；日期未知为 null。
- missing_information：field、impact、question。
- candidate_checks：company、domain、rule_results、decision、reasons；rule_results 采用下文逐条判断结构。
- evaluation：status（not_run / completed）、dataset、report_path；completed 不等于验收通过。

交付前检查 rule_id 和 evidence.id 唯一，所有引用均存在，规则枚举合法，假设未升级为硬条件，候选决策与聚合算法一致。示例模板是空白起点，不是正式客户画像或实测结果。

## 规则字段

每条规则包含：

- rule_id：版本内唯一标识。
- level：must（必须满足）、exclude（命中排除）、should（偏好）。
- field：如 operating_markets、buyer_type、product_categories、supports_private_label。经营市场和注册地址分别记录。
- operator：in、contains_any、equals、gte、lte，须定义枚举或单位及适用范围。
- value：目标值；exclude 的 value 表示需排除的值。
- basis：user_constraint、documented_capability、hypothesis；hypothesis 不得设为硬条件。
- evidence_ids：制定规则的来源，不代表某家买家符合规则的证明。
- verification：判断买家是否符合时需要查什么证据。
- unknown_action：硬条件为 needs_review；偏好为 neutral。

数值比较先统一单位、币种、价格口径；无法统一时为 unknown。用户明确的排除名单须注明覆盖范围、日期，域名存在别名疑问时不强行判定。

## 候选企业逐条判断

must 用 pass / fail / unknown；exclude 用 hit / clear / unknown；should 用 match / no_match / unknown。每项记录 rule_id、result、evidence_ids、reason。

决策顺序：

1. 任一 must=fail 或 exclude=hit → rejected，说明决定性证据。
2. 没有已知拒绝条件，但任一硬条件为 unknown → needs_review。
3. 所有 must=pass 且所有 exclude=clear → qualified。
4. 没有实质性硬条件时 → needs_review，空规则不能自动合格。

should 只解释优先级，不能覆盖硬条件。网页没有提及通常是 unknown，不能据此判 clear。每项候选判断的证据须覆盖对应命题。信息不足和事实冲突都保持 unknown。

## 工程实现

- 大模型：抽取产品用途、识别经营模式、提出画像、根据引用解释语义匹配。
- 确定性逻辑：字段与证据引用校验、域名/单位标准化、精确名单匹配、三态聚合、指标计算。
- 搜索及网页读取：获得可追溯公开证据；摘要用于发现，关键事实尽量读取原页。
- 存储：JSON 文件即可起步；接入数据库时保留规则版本、证据时间和人工修改记录。

本包提供 Agent 工作流、模板和评测计算器；搜索接口、文档解析及生产规则执行服务由宿主接入，并未随本包部署。
