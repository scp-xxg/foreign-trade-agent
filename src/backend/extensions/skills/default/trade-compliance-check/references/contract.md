# 输入与证据契约

详见可运行的[保温杯德国发品示例](example-input.json)。所有时间必须带时区，as_of为检查截至时间。

| 字段 | 约定 |
|---|---|
| case_id/as_of | 采购/销售/发品案标识与检查时间，必填 |
| product | id、revision必填；category可为drinkware/electronics/lighting/machinery/textile/toy/chemical/other，真实类别不明时省略；不可把明显电气产品故意标为other |
| product.features | food_contact、children、medical、environmental_claim，每项true/false/null；未知留空或null；模型可提出候选但不能自行确定用途 |
| markets | 两位大写目的国代码，GB代表英国；EU可初步路由，但须补具体国家；多个国家分别生成检查行 |
| channel | email/alibaba/amazon/website/social/offline；具体站点和社媒平台在证据中补充；其他渠道提示缺少覆盖 |
| stage | outreach/communication/listing/contract/procurement/shipment/retrospective；复盘需回到原业务阶段检查 |
| fields | 与敏感词技能一致，每个字段{id,text,placement?}；不得把图片路径冒充OCR文本 |
| evidence | [{id,reference,text,retrieved_at,valid_until}]，可含产品记录、官方原文和真实审核记录；有效期是本次复核窗口，不冒充法定有效期 |
| reviews | 当前每检查项最多一条，含check_id、scope_hash、rule_hash、evidence_hash、evidence_ids、decision、reviewer、note、reviewed_at、valid_until |

完整的review字段都必填。decision为satisfied/not_applicable/failed。没有真实审核时留空reviews。not_applicable须有依据，不能用它避开未知范围。

首次运行获得check_id/scope_hash/rule_hash。审核后evidence_hash通过以下方式计算（check.py的digest辅助函数可直接调用）：

`digest([evidence_by_id[id] for id in sorted(review.evidence_ids)])`

digest为JSON sort_keys=true、ensure_ascii=false、紧凑分隔符编码UTF-8后SHA-256。更新任一所引用证据的内容、来源、日期或有效期会使绑定失效。审核时间须不早于证据取得时间，且证据和审核在as_of时均有效。报告evidence_manifest可用于逐份比较证据变更，不等于审核身份验证。

程序只接受上述结构，没有“已合规”或放行标志。输入原文与确认均为声明，脚本无法验证签章、证书真实性和审批人身份。

## 输出

每个检查项保留市场、selection、status、scope_hash、rule_hash、证据要求和官方研究入口。

- evidence_required：已选主题尚无可复用审核。
- scope_confirmation_required：未知条件可能适用，先补上下文。
- review_invalidated：旧审核在范围、规则、证据或时间上失效，issues说明原因。
- reviewed_with_supplied_evidence：输入审核记录可复用，仅限该主题范围。
- not_applicable_per_supplied_review：有当前审核依据声明不适用。
- issue_reported：输入审核指出问题。

总状态needs_review或scoped_checklist_reviewed，均不代表全法规合规或发布授权。coverage_gaps列缺口，excluded_checks列范围不符主题，ignored_previous_reviews列当前不再适用的旧审核，不能把这些旧审核算作复用。sensitive_scan为真实敏感词脚本结果；有命中始终保留上下文复核。

scope_hash绑定产品及用途、市场、渠道和阶段；depends_on_text=true的检查额外绑定文案。不会复用跨国家结论。为保守起见，产品特征变化会使所有该产品检查重审；未承诺精确到每个法规事实依赖。as_of不加入scope_hash，但每次独立核对时间有效性。

CLI返回0表示运行成功，不是合规；2为错误。输出文件只新建不覆盖。输入文件最多3MB，不联网、不保存数据库、不自动修改文案。
