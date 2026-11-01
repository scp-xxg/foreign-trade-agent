# 采购工具输入与衔接

调用`trade_procurement_prepare(action, data)`。输入Schema见schema.json，严格字段校验，未知键拒绝。所有日期必须带时区，金额数量为有限Decimal，建议JSON用十进制字符串；数量单位按明确原值比较，不自动猜换算。

最小输入：{"case_id":"P1","as_of":"2026-11-01T08:00:00+08:00","sources":[],"requirements":[]}。空列表只返回needs_input，不能宣称完成。

来源sources=[{id,reference,text}]。所有Supported对象需evidence=[{source_id,excerpt}]，excerpt必须是来源原文子串。facts的value还必须出现在引用中。数值、状态及确认标记其余仅是输入声明，不独立验证语义、真实性、审批权限或当前状态。模型只在有用户确认或真实已审核记录时填写confirmed/reviewed/approved等。

统一requirements行{id,sku,revision,quantity,unit,need_by,destination,facts,evidence}；facts=[{field,value,confirmed,evidence}]，默认必填name/material/specification/packaging，可用真实企业required_fields替换。quantity始终为毛需求，不能以净需求覆盖后再扣库存。报价quantity和产能需求与计算出的净采购量比较；净量为0无需采购，库存未确认不参与比价。库存可选available_stock/confirmed_inbound/safety_stock/inventory_confirmed，任何缺项不计算净采购量。capability_checks和quality_checks为企业明确要求的检查项。每个阶段传相同case_id、当前完整资料及as_of，别只传上阶段摘要。

sourcing/capability使用criteria=[{name,required}]和suppliers=[{id,legal_name,country,registration_id?,website?,identity_reviewed,assessments,capacities,evidence}]。assessment={name,state:met|not_met|unknown,basis:supplier_claim|document|independent_check,observed_at,valid_until,evidence}。capacity={line_id,revision,unit,total,committed,available_by,valid_until,independently_checked,evidence}。按本次需求/期间提供容量，不把静态宣传产能当承诺交期；同一供应商多个产品共享设备时须先扣除共同占用，本工具不实现全厂排产。

comparison使用comparison_currency、cost_basis、required_costs、fx、offers。fx={currency,rate,observed_at,valid_until,evidence}，rate是该币种一单位折合comparison_currency。offer={id,line_id,supplier_id,revision,quantity,unit,currency,unit_price,moq,valid_until,cost_basis,costs:{费用名:绝对金额或null},reviewed,evidence}。汇率及费用只核对传入资料，不联网抓取；本工具不选择报价的有效版本，提供当前候选并保留历史来源。

quality使用quality_checks=[{id,line_id,revision,name,stage:sample|preproduction|production|preshipment,standard,method,owner,state:pending|passed|failed,reviewed,sample_version,measured_value?,lower_limit?,upper_limit?,measurement_unit,evidence}]。同一关键要求的多个阶段检查均须完成；所有测量值与边界同单位。无测量的passed只代表输入中已审核结论，不代表工具做了物理检验。

delivery使用milestones=[{id,line_id,revision,name,owner,planned_at,actual_at?,observed_at,remaining_hours?,depends_on:[],evidence}]。remaining_hours为从当前as_of到本采购行可交付的完整剩余自然小时估计，不是某工序耗时；变更截至时刻须更新估计。progress_freshness_hours默认48，可按真实业务调整。无实时生产系统或定时任务。

settlement使用orders=[{line_id,order_id,supplier_id,revision,quantity,unit,currency,unit_price,approved,evidence}]；receipts=[{id,document_number,line_id,order_id,revision,unit,batch,received,accepted,rejected,returned,reviewed,evidence}]；invoices=[{id,number,line_id,order_id,supplier_id,revision,unit,currency,quantity,unit_price,charges,reviewed,evidence}]；adjustments=[{id,line_id,order_id,currency,kind:payment|credit,amount,confirmed,evidence}]。均为本次订单行累计记录，不混入其他订单，聚合到相同发票/采购行后传入。未传付款不代表已证明从未付款，余额是所提供记录范围，完整性由财务审核。

结果含case_id/stage/input_hash/items/status/issues/metrics。status仅needs_input/needs_completion/review_required/candidate_review_required，均非已准入、已投产或已付款。input_hash绑定包含截至时间的完整输入版本；它是结果追溯指纹，不是签名或审批凭证。修改资料后复核相关声明与受影响步骤，不能仅改revision使旧审核“匹配”。

工作流依赖：需求→寻源→企业身份核验(复用)→生产能力→报价→样品质量→谈判及采购单审批(复用)→交期→验收结算。已合格复购可依真实规则跳过寻源，说明依据。库存计算若改变采购数量，先确认并更新需求版本后重新询价。缺材料可完成独立部分；阻塞不自动设成已批准。输出待审资料包，文件导出须真实创建附件，不伪造URL；不发消息、不下单、不付款、不写ERP、不创建提醒。
