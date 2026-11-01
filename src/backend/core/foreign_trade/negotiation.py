"""Evidence-linked negotiation drafts and decimal concession checks. No external writes."""
from decimal import Decimal
from typing import Literal
from pydantic import Field, StrictBool, model_validator
from core.foreign_trade.communication import CommunicationInput
from core.foreign_trade.buyer_search import StrictModel

STAGES = {'negotiation-strategy':'trade-negotiation-strategy','objection-resolution':'trade-objection-resolution','concession-planning':'trade-concession-planning','sample-trial':'trade-sample-trial'}

class Offer(StrictModel):
    version: str = Field(min_length=1,max_length=80)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    unit_price: Decimal = Field(gt=0,allow_inf_nan=False,max_digits=16,decimal_places=4)
    unit_cost: Decimal = Field(ge=0,allow_inf_nan=False,max_digits=16,decimal_places=4)
    quantity: int = Field(gt=0,le=100000000,strict=True)
    extra_cost: Decimal = Field(default=Decimal('0'),ge=0,allow_inf_nan=False,max_digits=16,decimal_places=4)
    minimum_unit_price: Decimal = Field(gt=0,allow_inf_nan=False,max_digits=16,decimal_places=4)
    minimum_margin_pct: Decimal = Field(ge=0,le=100,allow_inf_nan=False)
    max_discount_pct: Decimal = Field(ge=0,le=100,allow_inf_nan=False)
    proposed_unit_price: Decimal = Field(gt=0,allow_inf_nan=False,max_digits=16,decimal_places=4)
    exchange_condition: str = Field(min_length=1,max_length=1000)
    basis: str = Field(min_length=1,max_length=3000)
    authority_confirmed: StrictBool = False

class NegotiationInput(CommunicationInput):
    goal: str = Field(default='',max_length=1000)
    offer: Offer | None = None

    @model_validator(mode='after')
    def offer_basis(self):
        if self.offer and not any(self.offer.basis in s.text for s in self.sources):
            raise ValueError('成本与授权口径必须引用提供的原文来源')
        return self

STAGE_RULES = [('order_confirmed','order_confirmation'),('commercial_terms','commercial_negotiation'),('sample_requested','sample_validation'),('quote_requested','proposal_evaluation'),('requirements_confirmed','requirements_confirmation')]
OBJECTIONS = {'price':'核对同规格、贸易术语、运费和付款口径，再考虑价值证明或条件交换', 'quality':'确认验收标准，复用已确认检测证据或样品验证', 'delivery':'核对需求日期与已确认产能，未知交期交商家确认', 'trust':'提供真实身份与履约证明，不虚构客户案例', 'payment':'核对付款要求与商家授权政策，不自行授信', 'approval':'确认审批角色与节点，不将联系人视作最终决策人', 'unknown':'先询问客户顾虑，不把推测记为原因'}

def negotiate(req: NegotiationInput, action: str):
    if action not in STAGES: raise ValueError('不支持的谈单操作')
    sources={s.id:s for s in req.sources}
    facts=[dict(**c.model_dump(),reference=sources[c.source_id].reference) for c in req.claims]
    result=dict(stage=action,buyer_id=req.buyer_id,status='review_required',facts=facts,
                approval_required=True,sent=False,saved=False,rule_version='negotiation-v1',
                metrics={'linked_claims':len(facts),'business_accuracy':None},
                warnings=['原文关联不证明事实真实或仍有效；全部策略为内部待审建议。'])
    if req.do_not_contact:
        return dict(result,status='stopped',next_actions=['停止客户触达，可内部整理纪要'])
    if action=='negotiation-strategy':
        fields={c.field for c in req.claims}
        candidates=[dict(stage=stage,evidence=[f for f in facts if f['field']==field]) for field,stage in STAGE_RULES if field in fields]
        result.update(opportunity_stage=candidates[0]['stage'] if candidates else 'unknown',stage_candidates=candidates,
                      diagnosis='依据输入事实字段的规则候选，须结合完整往来人工核对，不是成交预测',
                      unknowns=[f for f in ['decision_role','purchase_date','budget','blocker'] if f not in fields],
                      next_goal=req.goal or '确认下一轮推进目标',next_actions=['根据已证实卡点选择报价、异议、让步或样品分支；推测先验证'])
    elif action=='objection-resolution':
        objections=[]
        for f in facts:
            if f['field'].startswith('objection:'):
                category=f['field'].split(':',1)[1]
                if category not in OBJECTIONS:category='unknown'
                objections.append(dict(category=category,evidence=f,status='unresolved',strategy=OBJECTIONS[category],
                                       cause='unknown',verification_question='请确认具体比较条件或尚未满足的要求。'))
        result.update(status='needs_evidence' if not objections else 'review_required',objections=objections,
                      next_actions=['复用有据答复生成草稿，缺依据先追问；仅客户后续明确反馈才能记录异议解决'])
    elif action=='concession-planning':
        if not req.offer:return dict(result,status='needs_cost_and_authority',next_actions=['补充同币种同单位、相同数量的完整成本、报价版本、授权底线与交换条件'])
        o=req.offer
        def calc(price):
            revenue=price*o.quantity;cost=o.unit_cost*o.quantity+o.extra_cost
            return revenue,cost,revenue-cost,(revenue-cost)/revenue*100
        revenue,cost,profit,margin=calc(o.proposed_unit_price)
        old=calc(o.unit_price)
        discount=(o.unit_price-o.proposed_unit_price)/o.unit_price*100
        breaches=[]
        if o.proposed_unit_price<o.minimum_unit_price:breaches.append('below_price_floor')
        if margin<o.minimum_margin_pct:breaches.append('below_margin_floor')
        if discount>o.max_discount_pct:breaches.append('discount_exceeds_authority')
        if not o.authority_confirmed:breaches.append('authority_unconfirmed')
        result.update(status='approval_required' if breaches else 'within_supplied_limits_pending_review',
                      internal_only=True,offer_version=o.version,currency=o.currency,exchange_condition=o.exchange_condition,
                      calculations={k:str(v.quantize(Decimal('0.01'))) for k,v in dict(revenue=revenue,total_cost=cost,profit=profit,margin_pct=margin,discount_pct=discount,profit_reduction=old[2]-profit).items()},breaches=breaches,
                      next_actions=['上述测算只适用于当前数量、成本及币种；改变数量、运费、付款或汇率后重新核算。客户草稿不得泄露成本、底线和让步梯度。不得把待审方案表述为接受。'])
    else:
        fields={c.field for c in req.claims}
        required=['sample_goal','sample_spec','sample_fees','acceptance_criteria','feedback_owner','feedback_date']
        missing=[f for f in required if f not in fields]
        events=[f for f in facts if f['field'] in {'sample_dispatched','sample_received','sample_passed','sample_failed','trial_order'}]
        result.update(status='needs_confirmation' if missing else 'sample_plan_pending_review',missing_fields=missing,
                      recorded_events=events,actual_state='requires_reconciliation' if len({f['field'] for f in events})>1 else events[0]['field'] if events else 'not_recorded',
                      next_actions=['核对验证目标、规格版本、费用、验收标准及反馈负责人和日期；计划不等于实际寄出。事件时间、冲突及版本需对照原文确认；复用跟进技能安排建议，不自动发样。'])
    return result
