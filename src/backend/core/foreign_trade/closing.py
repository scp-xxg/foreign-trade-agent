"""Evidence-linked closing checks and document drafts; no business mutations."""
import re
from decimal import Decimal
from functools import cache
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from core.foreign_trade.buyer_search import StrictModel
from core.foreign_trade.retrospective import Evidence

STAGES = {
    'closing-readiness': 'trade-closing-readiness',
    'order-reconciliation': 'trade-order-reconciliation',
    'sales-document-drafting': 'trade-sales-document-drafting',
    'order-confirmation': 'trade-order-confirmation',
    'payment-verification': 'trade-payment-verification',
    'order-handoff': 'trade-order-handoff',
}

class Source(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    reference: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=50000)
    kind: Literal['user_document', 'bank_record', 'finance_confirmation', 'approved_policy', 'approved_template'] = 'user_document'

class Requirement(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    phase: Literal['readiness', 'signature', 'payment', 'handoff']
    label: str = Field(min_length=1, max_length=500)
    required: bool = True
    state: Literal['confirmed', 'pending', 'conflict', 'not_applicable'] = 'pending'
    owner: str = Field(default='', max_length=200)
    due_at: AwareDatetime | None = None
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    policy_evidence: list[Evidence] = Field(min_length=1, max_length=10)
    depends_on: list[str] = Field(default_factory=list, max_length=30)
    note: str = Field(default='', max_length=1000)

class Term(StrictModel):
    field: str = Field(min_length=1, max_length=80, pattern=r'^[a-z][a-z0-9_]*$')
    value: str = Field(min_length=1, max_length=3000)
    document_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    confirmed: bool = False
    evidence: list[Evidence] = Field(min_length=1, max_length=10)

class Line(StrictModel):
    sku: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    quantity: str = Field(pattern=r'^\d{1,12}(\.\d{1,6})?$')
    unit: str = Field(min_length=1, max_length=40)
    unit_price: str = Field(pattern=r'^\d{1,12}(\.\d{1,6})?$')
    evidence: list[Evidence] = Field(min_length=1, max_length=10)

class Template(StrictModel):
    kind: Literal['pi', 'contract']
    version: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=30000)
    approved: bool = False
    evidence: list[Evidence] = Field(min_length=1, max_length=10)

class Account(StrictModel):
    account_id: str = Field(min_length=1, max_length=200)
    beneficiary: str = Field(min_length=1, max_length=200)
    approved: bool = False
    evidence: list[Evidence] = Field(min_length=1, max_length=10)

class Payment(StrictModel):
    transaction_id: str = Field(min_length=1, max_length=200)
    order_id: str = Field(min_length=1, max_length=200)
    kind: Literal['promise', 'remittance_slip', 'bank_credit', 'finance_verified']
    amount: str = Field(pattern=r'^\d{1,12}(\.\d{1,6})?$')
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    payer: str = Field(min_length=1, max_length=200)
    account_id: str = Field(min_length=1, max_length=200)
    at: AwareDatetime
    evidence: list[Evidence] = Field(min_length=1, max_length=10)

class ClosingInput(StrictModel):
    order_id: str = Field(min_length=1, max_length=200)
    as_of: AwareDatetime
    sources: list[Source] = Field(default_factory=list, max_length=100)
    requirements: list[Requirement] = Field(default_factory=list, max_length=150)
    terms: list[Term] = Field(default_factory=list, max_length=300)
    required_fields: list[str] = Field(default_factory=lambda: ['seller','buyer','product','quantity','unit','currency','price','payment_terms','delivery','incoterm'], max_length=80)
    lines: list[Line] = Field(default_factory=list, max_length=100)
    template: Template | None = None
    account: Account | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    payment_method: Literal['advance','installment','lc','credit'] = 'advance'
    expected_due: str | None = Field(default=None, pattern=r'^\d{1,12}(\.\d{1,6})?$')
    due_evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    expected_payer: str = Field(default='', max_length=200)
    payments: list[Payment] = Field(default_factory=list, max_length=100)
    handoff_required_fields: list[str] = Field(default_factory=lambda: ['product','quantity','unit','packaging','inspection','delivery'], max_length=80)

    @model_validator(mode='after')
    def linked(self):
        sources={s.id:s for s in self.sources}
        if len(sources)!=len(self.sources): raise ValueError('来源ID重复')
        for rows,field in [(self.requirements,'id'),(self.payments,'transaction_id'),(self.lines,'sku')]:
            if len({getattr(r,field) for r in rows})!=len(rows): raise ValueError('记录ID重复，款项不得重复认领')
        refs=list(self.due_evidence)
        for item in [*self.requirements,*self.terms,*self.lines,*self.payments,self.template,self.account]:
            if item is not None:
                refs.extend(item.evidence)
                if isinstance(item,Requirement):refs.extend(item.policy_evidence)
        for ref in refs:
            if ref.source_id not in sources or not ref.excerpt.strip() or ref.excerpt not in sources[ref.source_id].text:
                raise ValueError('证据须为已提供来源的原文子串')
        if any(sources[e.source_id].kind!='approved_policy' for r in self.requirements for e in r.policy_evidence):
            raise ValueError('必备条件须引用企业已批准规则')
        if any(r.state in {'confirmed','not_applicable'} and not r.evidence for r in self.requirements):
            raise ValueError('确认及不适用状态必须提供证据')
        ids={r.id for r in self.requirements}
        deps={r.id:r.depends_on for r in self.requirements}
        checked=set()
        def visit(i,path):
            if i in checked:return
            if i in path:raise ValueError('依赖关系存在循环')
            for d in deps[i]:
                if d not in ids:raise ValueError('依赖条件不存在')
                visit(d,path|{i})
            checked.add(i)
        for i in ids:visit(i,set())
        if any(Decimal(l.quantity)<=0 for l in self.lines):raise ValueError('数量须大于0')
        if self.template and self.template.approved:
            if not any(sources[e.source_id].kind=='approved_template' and self.template.text in sources[e.source_id].text for e in self.template.evidence):
                raise ValueError('批准模板须包含完整模板原文')
        if self.account and self.account.approved and not any(sources[e.source_id].kind=='approved_policy' for e in self.account.evidence):
            raise ValueError('受控账户须引用批准资料')
        if self.expected_due is not None and not self.due_evidence:raise ValueError('应收金额须有条款证据')
        return self


def close_order(req: ClosingInput, action: str):
    if action not in STAGES:raise ValueError('不支持的成交阶段')
    sources={s.id:s for s in req.sources}
    def row(item):
        result=item.model_dump(mode='json')
        for f in ['evidence','policy_evidence']:
            if hasattr(item,f):result[f]=[dict(**e.model_dump(),reference=sources[e.source_id].reference) for e in getattr(item,f)]
        return result
    result=dict(order_id=req.order_id,as_of=req.as_of.isoformat(),stage=action,status='draft_review_required',
                sent=False,saved=False,execution_started=False,approval_required=True,rule_version='closing-v1',
                metrics={'accuracy':None,'business_effect':None},
                warnings=['仅核对本次材料及原文关联，来源类型与批准状态是输入声明，未独立验证真伪或实时银行、CRM、签署及产能状态。所有结论待授权人员审核。'])
    byfield={}
    for t in req.terms:byfield.setdefault(t.field,[]).append(t)
    def terms_check(fields):
        out=[]
        for field in dict.fromkeys([*fields,*byfield]):
            entries=byfield.get(field,[]); values={t.value.strip() for t in entries}
            state='missing' if not entries else 'conflict' if len(values)>1 else 'pending_confirmation' if not all(t.confirmed for t in entries) else 'consistent_pending_review'
            out.append(dict(field=field,state=state,entries=[row(t) for t in entries]))
        return out
    def checks(phases):
        lookup={r.id:r for r in req.requirements}
        @cache
        def satisfied(i):
            r=lookup[i]
            return r.state in {'confirmed','not_applicable'} and all(satisfied(d) for d in r.depends_on)
        rows=[dict(**row(r),dependency_blockers=[d for d in r.depends_on if not satisfied(d)],
                   overdue=bool(r.due_at and r.due_at<req.as_of and not satisfied(r.id)),
                   satisfied=satisfied(r.id)) for r in req.requirements if r.phase in phases]
        blocking=[r['id'] for r in rows if r['required'] and not r['satisfied']]
        missing_phases=[p for p in phases if not any(r.phase==p and r.required for r in req.requirements)]
        return rows,blocking,missing_phases
    if action in {'closing-readiness','order-confirmation','order-handoff'}:
        phases=['readiness'] if action=='closing-readiness' else ['signature'] if action=='order-confirmation' else ['readiness','signature','payment','handoff']
        rows,blocking,missing=checks(phases)
        result.update(checklist=rows,blocking_ids=blocking,missing_rule_phases=missing,
                      status='needs_rules' if missing else 'blocked' if blocking else 'conditions_supported_pending_review')
        if action=='order-confirmation':
            result.update(next_actions=[dict(requirement_id=r['id'],owner=r['owner'],due_at=r['due_at'],
                draft_message=f"请协助确认：{r['label']}。如已完成，请提供对应订单与版本的有效记录。") for r in rows if not r['satisfied']],
                signature_authenticity='not_verified')
        if action=='order-handoff':
            matrix=terms_check(req.handoff_required_fields)
            missing_terms=[r['field'] for r in matrix if r['state']!='consistent_pending_review']
            result.update(handoff_terms=matrix,missing_or_conflicting_fields=missing_terms,
                handoff_status='needs_completion' if missing or blocking or missing_terms else 'draft_ready_for_acceptance',
                capacity_check='not_performed',recipient_acceptance='not_recorded',
                next_actions=['交付各部门审核与接收；规格变更后重新核对受影响文档和前置条件。真实启动须走企业执行流程。'])
    elif action=='order-reconciliation':
        matrix=terms_check(req.required_fields)
        result.update(matrix=matrix,issues=[r['field'] for r in matrix if r['state']!='consistent_pending_review'],
                      status='needs_documents' if not req.terms else 'draft_review_required',
                      next_actions=['保留所有版本，不自动选最新覆盖冲突；语义、单位等价及交期起算条件需结合原文审核。'])
    elif action=='sales-document-drafting':
        template=req.template
        if not template or not template.approved:
            return dict(result,status='needs_approved_template',draft=None)
        matrix=terms_check(req.required_fields)
        conflicts=[r['field'] for r in matrix if r['state']!='consistent_pending_review']
        values={f:ts[0].value for f,ts in byfield.items() if len({t.value for t in ts})==1 and all(t.confirmed for t in ts)}
        # Never source account fields from correspondence, even when marked confirmed.
        for key in list(values):
            if any(part in key for part in ['bank','account','beneficiary','swift','iban']):del values[key]
        account=req.account
        if account and account.approved:values.update(account_id=account.account_id,beneficiary=account.beneficiary)
        lines=[dict(**row(l),line_total=format(Decimal(l.quantity)*Decimal(l.unit_price),'f')) for l in req.lines]
        total=sum((Decimal(l['line_total']) for l in lines),Decimal(0))
        if lines and req.currency and values.get('currency')==req.currency:
            values.update(line_items='\n'.join(f"{l['sku']} | {l['description']} | {l['quantity']} {l['unit']} | {l['unit_price']} | {l['line_total']}" for l in lines),subtotal=format(total,'f'))
        placeholders=set(re.findall(r'{{\s*([a-z][a-z0-9_]*)\s*}}',template.text))
        missing=sorted(placeholders-values.keys())
        draft=re.sub(r'{{\s*([a-z][a-z0-9_]*)\s*}}',lambda m: values.get(m[1],f"【待确认：{m[1]}】"),template.text)
        result.update(document_kind=template.kind,template_version=template.version,template_evidence=row(template)['evidence'],
            draft='【内部草稿，须审核】\n'+draft,missing_fields=missing,term_issues=conflicts,line_items=lines,
            subtotal=format(total,'f') if lines else None,currency=req.currency,
            totals_scope='仅货品小计，未自动计算折扣、税费、运保费或汇率；不作为最终应收',
            status='needs_confirmation' if missing or conflicts else 'draft_review_required',
            next_actions=['确认模板内固定条款与账户；编号、账户变更、签章及最终法律商业审核由授权人员完成。'])
    else:
        due=Decimal(req.expected_due) if req.expected_due is not None else None
        account=req.account
        entries=[];total=Decimal(0)
        for p in req.payments:
            reasons=[]
            kinds={sources[e.source_id].kind for e in p.evidence}
            if p.kind not in {'bank_credit','finance_verified'}:reasons.append('not_arrival_evidence')
            if p.kind=='bank_credit' and 'bank_record' not in kinds:reasons.append('missing_bank_record')
            if p.kind=='finance_verified' and 'finance_confirmation' not in kinds:reasons.append('missing_finance_confirmation')
            if p.order_id!=req.order_id:reasons.append('different_order')
            if not req.currency or p.currency!=req.currency:reasons.append('currency_mismatch_or_unknown')
            if not req.expected_payer or p.payer!=req.expected_payer:reasons.append('payer_mismatch_or_unknown')
            if not account or not account.approved or p.account_id!=account.account_id:reasons.append('account_unapproved_or_mismatch')
            if p.at>req.as_of:reasons.append('future_record')
            if not reasons:total+=Decimal(p.amount)
            entries.append(dict(**row(p),included=not reasons,exceptions=reasons))
        checklist,blocking,missing=checks(['payment'])
        difference=due-total if due is not None else None
        status='needs_terms' if due is None or not req.currency else 'non_cash_conditions_pending_review' if req.payment_method in {'lc','credit'} else 'amount_supported_pending_review' if difference==0 else 'short_payment' if difference>0 else 'overpayment_pending_review'
        result.update(status=status,payment_method=req.payment_method,entries=entries,matched_amount=format(total,'f'),
            expected_due=req.expected_due,currency=req.currency,difference=format(difference,'f') if difference is not None else None,
            payment_checklist=checklist,blocking_ids=blocking,missing_rule_phases=missing,
            payment_condition='pending_review' if due is not None and (req.payment_method in {'lc','credit'} or difference==0) and not blocking and not missing and not any(e['exceptions'] for e in entries) else 'unconfirmed',
            due_evidence=[dict(**e.model_dump(),reference=sources[e.source_id].reference) for e in req.due_evidence],
            next_actions=['财务复核原始记录、订单分配及付款条件；到账不自动允许投产。水单与承诺不能算到账；信用证及账期按已批准条件审核。'])
    return result
