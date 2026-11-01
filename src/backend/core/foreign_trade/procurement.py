"""Evidence-linked procurement preparation; no purchasing, messaging or payment mutations."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import json
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

STAGES = {
    'requirements': 'trade-procurement-requirements',
    'sourcing': 'trade-supplier-sourcing',
    'capability': 'trade-supplier-capability',
    'comparison': 'trade-procurement-cost-comparison',
    'quality': 'trade-procurement-quality-planning',
    'delivery': 'trade-procurement-delivery-tracking',
    'settlement': 'trade-procurement-acceptance-settlement',
}
Text = Annotated[str, Field(min_length=1, max_length=1000)]
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, max_digits=24, decimal_places=8)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, max_digits=24, decimal_places=8)]
class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Source(Model):
    id: Text
    reference: Text
    text: str = Field(min_length=1, max_length=60000)
class Evidence(Model):
    source_id: Text
    excerpt: str = Field(min_length=1, max_length=6000)
class Supported(Model):
    evidence: list[Evidence] = Field(min_length=1, max_length=20)
class Fact(Supported):
    field: Text
    value: Text
    confirmed: bool = False
class Requirement(Supported):
    id: Text
    sku: Text
    revision: Text
    quantity: Positive
    unit: Text
    need_by: AwareDatetime
    destination: Text
    facts: list[Fact] = Field(default_factory=list, max_length=100)
    available_stock: Nonnegative | None = None
    confirmed_inbound: Nonnegative | None = None
    safety_stock: Nonnegative | None = None
    inventory_confirmed: bool = False
    capability_checks: list[Text] = Field(default_factory=list, max_length=100)
    quality_checks: list[Text] = Field(default_factory=list, max_length=100)
class Criterion(Model):
    name: Text
    required: bool = True
class Assessment(Supported):
    name: Text
    state: Literal['met', 'not_met', 'unknown']
    basis: Literal['supplier_claim', 'document', 'independent_check'] = 'supplier_claim'
    observed_at: AwareDatetime
    valid_until: AwareDatetime
    @model_validator(mode='after')
    def dates(self):
        if self.valid_until < self.observed_at: raise ValueError('能力证据有效期错误')
        return self
class Capacity(Supported):
    line_id: Text
    revision: Text
    unit: Text
    total: Nonnegative
    committed: Nonnegative
    available_by: AwareDatetime
    valid_until: AwareDatetime
    independently_checked: bool = False
class Supplier(Supported):
    id: Text
    legal_name: Text
    country: Text
    registration_id: str = Field(default='', max_length=100)
    website: str = Field(default='', max_length=1000)
    # Identity result is a supplied, separately reviewed result, not a tool lookup.
    identity_reviewed: bool = False
    capacities: list[Capacity] = Field(default_factory=list, max_length=100)
    assessments: list[Assessment] = Field(default_factory=list, max_length=100)
class FX(Supported):
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    rate: Positive
    observed_at: AwareDatetime
    valid_until: AwareDatetime
    @model_validator(mode='after')
    def dates(self):
        if self.valid_until < self.observed_at: raise ValueError('汇率有效期错误')
        return self
class Offer(Supported):
    id: Text
    line_id: Text
    supplier_id: Text
    revision: Text
    quantity: Positive
    unit: Text
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    unit_price: Nonnegative
    moq: Nonnegative
    valid_until: AwareDatetime
    cost_basis: Text
    # Explicit absolute amounts in quote currency, not inferred percentages.
    costs: dict[str, Nonnegative | None] = Field(default_factory=dict, max_length=30)
    reviewed: bool = False
class QualityCheck(Supported):
    id: Text
    line_id: Text
    revision: Text
    name: Text
    stage: Literal['sample', 'preproduction', 'production', 'preshipment']
    standard: Text
    method: Text
    owner: Text
    state: Literal['pending', 'passed', 'failed'] = 'pending'
    reviewed: bool = False
    sample_version: Text
    measured_value: Decimal | None = Field(default=None, allow_inf_nan=False, max_digits=24, decimal_places=8)
    lower_limit: Decimal | None = Field(default=None, allow_inf_nan=False, max_digits=24, decimal_places=8)
    upper_limit: Decimal | None = Field(default=None, allow_inf_nan=False, max_digits=24, decimal_places=8)
    measurement_unit: str = Field(default='', max_length=100)
    @model_validator(mode='after')
    def bounds(self):
        if self.lower_limit is not None and self.upper_limit is not None and self.lower_limit>self.upper_limit: raise ValueError('质量上下限错误')
        if any(v is not None for v in [self.measured_value,self.lower_limit,self.upper_limit]) and not self.measurement_unit: raise ValueError('质量测量缺单位')
        return self
class Milestone(Supported):
    id: Text
    line_id: Text
    revision: Text
    name: Text
    owner: Text
    planned_at: AwareDatetime
    actual_at: AwareDatetime | None = None
    observed_at: AwareDatetime
    # Supplied estimate, never guessed by the tool. Calendar elapsed hours.
    remaining_hours: Nonnegative | None = None
    depends_on: list[Text] = Field(default_factory=list, max_length=30)
class Order(Supported):
    line_id: Text
    order_id: Text
    supplier_id: Text
    revision: Text
    quantity: Positive
    unit: Text
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    unit_price: Nonnegative
    approved: bool = False
class Receipt(Supported):
    id: Text
    document_number: Text
    line_id: Text
    order_id: Text
    revision: Text
    unit: Text
    batch: Text
    received: Nonnegative
    accepted: Nonnegative
    rejected: Nonnegative
    returned: Nonnegative = Decimal(0)
    reviewed: bool = False
    @model_validator(mode='after')
    def quantities(self):
        if self.accepted+self.rejected > self.received or self.returned > self.accepted:
            raise ValueError('验收或退货数量超出范围')
        return self
class Invoice(Supported):
    id: Text
    number: Text
    line_id: Text
    order_id: Text
    supplier_id: Text
    revision: Text
    unit: Text
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    quantity: Positive
    unit_price: Nonnegative
    charges: Nonnegative = Decimal(0)
    reviewed: bool = False
class Adjustment(Supported):
    id: Text
    line_id: Text
    order_id: Text
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    kind: Literal['payment', 'credit']
    amount: Nonnegative
    confirmed: bool = False
class ProcurementInput(Model):
    case_id: Text
    as_of: AwareDatetime
    sources: list[Source] = Field(default_factory=list, max_length=100)
    requirements: list[Requirement] = Field(default_factory=list, max_length=100)
    required_fields: list[Text] = Field(default_factory=lambda: ['name','material','specification','packaging'], max_length=100)
    criteria: list[Criterion] = Field(default_factory=list, max_length=100)
    suppliers: list[Supplier] = Field(default_factory=list, max_length=100)
    comparison_currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')] = 'CNY'
    cost_basis: str = Field(default='', max_length=1000)
    required_costs: list[Text] = Field(default_factory=list, max_length=30)
    fx: list[FX] = Field(default_factory=list, max_length=50)
    offers: list[Offer] = Field(default_factory=list, max_length=200)
    quality_checks: list[QualityCheck] = Field(default_factory=list, max_length=300)
    milestones: list[Milestone] = Field(default_factory=list, max_length=300)
    progress_freshness_hours: Positive = Decimal(48)
    orders: list[Order] = Field(default_factory=list, max_length=100)
    receipts: list[Receipt] = Field(default_factory=list, max_length=300)
    invoices: list[Invoice] = Field(default_factory=list, max_length=300)
    adjustments: list[Adjustment] = Field(default_factory=list, max_length=300)
    @model_validator(mode='after')
    def links(self):
        def unique(values):
            if len(values)!=len(set(values)): raise ValueError('重复标识或重复业务单据')
        for seq,key in [(self.sources,'id'),(self.requirements,'id'),(self.suppliers,'id'),(self.criteria,'name'),(self.fx,'currency'),(self.offers,'id'),(self.quality_checks,'id'),(self.milestones,'id'),(self.orders,'line_id'),(self.receipts,'id'),(self.invoices,'id'),(self.adjustments,'id')]:
            unique([getattr(x,key) for x in seq])
        unique(self.required_fields); unique(self.required_costs)
        sources={x.id:x.text for x in self.sources}
        lines={x.id for x in self.requirements}; suppliers={x.id for x in self.suppliers}
        def walk(obj):
            if isinstance(obj,Evidence):
                if obj.source_id not in sources or obj.excerpt not in sources[obj.source_id]: raise ValueError('证据不是来源原文')
                return
            if isinstance(obj,Fact) and not any(obj.value in e.excerpt for e in obj.evidence): raise ValueError('字段值未出现在引用中')
            if isinstance(obj,BaseModel):
                for name in type(obj).model_fields: walk(getattr(obj,name))
            elif isinstance(obj,list):
                for x in obj: walk(x)
        walk(self)
        for r in self.requirements:
            unique(r.capability_checks); unique(r.quality_checks)
        for supplier in self.suppliers:
            unique([a.name for a in supplier.assessments])
            unique([c.line_id for c in supplier.capacities])
            if any(c.line_id not in lines for c in supplier.capacities): raise ValueError('未知产能需求行')
        for seq in [self.offers,self.quality_checks,self.milestones,self.orders,self.receipts,self.invoices,self.adjustments]:
            for x in seq:
                if x.line_id not in lines: raise ValueError('未知采购需求行')
                if hasattr(x,'supplier_id') and x.supplier_id not in suppliers: raise ValueError('未知供应商')
        for x in [*self.receipts,*self.invoices,*self.adjustments]:
            order=next((o for o in self.orders if o.line_id==x.line_id),None)
            if not order or order.order_id!=x.order_id: raise ValueError('单据未关联当前采购订单')
        unique([(x.supplier_id,x.number,x.line_id) for x in self.invoices])
        unique([(x.document_number,x.line_id,x.batch) for x in self.receipts])
        nodes={x.id:x for x in self.milestones}
        visiting=set(); done=set()
        def visit(key):
            if key in visiting: raise ValueError('进度依赖有环')
            if key in done:return
            visiting.add(key)
            for dep in nodes[key].depends_on:
                if dep not in nodes or nodes[dep].line_id!=nodes[key].line_id: raise ValueError('进度依赖不属于同一采购行')
                visit(dep)
            visiting.remove(key);done.add(key)
        for key in nodes:visit(key)
        return self

def prepare(req: ProcurementInput, action: str):
    if action not in STAGES:raise ValueError('未知采购步骤')
    scope=sha256(json.dumps(req.model_dump(mode='json'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    result=dict(case_id=req.case_id,stage=action,input_hash=scope,as_of=req.as_of.isoformat(),status='needs_input',items=[],
        approval_required=True,executed_external_action=False,metrics={'accuracy':None,'business_effect':None},
        warnings=['仅核对传入证据与声明，不独立认证供应商、质检或到账；不自动下单、联系、扣款、付款或建立定时监控。'])
    def issue(code, **extra): return dict(code=code,**extra)
    def facts(line):
        grouped=defaultdict(list)
        for f in line.facts:grouped[f.field].append(f)
        good={};problems=[]
        for key,entries in grouped.items():
            if len({x.value for x in entries})>1:problems.append(issue('conflicting_fact',field=key))
            elif not all(x.confirmed for x in entries):problems.append(issue('unconfirmed_fact',field=key))
            else:good[key]=entries[0].value
        problems.extend(issue('missing_required_fact',field=f) for f in req.required_fields if f not in good)
        if not req.required_fields:problems.append(issue('missing_requirements_policy'))
        return good,problems
    def purchase_quantity(line):
        if line.inventory_confirmed and all(v is not None for v in [line.available_stock,line.confirmed_inbound,line.safety_stock]):
            return max(Decimal(0),line.quantity+line.safety_stock-line.available_stock-line.confirmed_inbound)
        return None
    if action in {'sourcing','capability'}:
        if not req.requirements:
            result['issues']=[issue('missing_requirements')];return result
        for supplier in req.suppliers:
            problems=[];rows=[]
            if not req.criteria:problems.append(issue('missing_sourcing_criteria'))
            if not supplier.identity_reviewed:problems.append(issue('identity_review_required'))
            keys={c.name for c in req.criteria if c.required}
            if action=='capability':
                for line in req.requirements:
                    keys.update(line.capability_checks)
                    if not line.capability_checks:problems.append(issue('missing_capability_policy',line_id=line.id))
            keys.update(c.name for c in req.criteria)
            assessments={a.name:a for a in supplier.assessments}
            for name in sorted(keys):
                a=assessments.get(name)
                state='unknown' if a is None else 'not_current' if not a.observed_at<=req.as_of<=a.valid_until else a.state
                verified=bool(a and a.basis!='supplier_claim' and state=='met')
                required=name in {c.name for c in req.criteria if c.required} or any(name in r.capability_checks for r in req.requirements)
                if required and not verified:problems.append(issue('capability_not_verified' if action=='capability' else 'criterion_not_verified',name=name,state=state))
                rows.append(dict(name=name,state=state,required=required,basis=a.basis if a else None,evidence=a.model_dump(mode='json')['evidence'] if a else [],verified_from_supplied_evidence=verified))
            capacity_rows=[]
            if action=='capability':
                for line in req.requirements:
                    cap=next((c for c in supplier.capacities if c.line_id==line.id),None)
                    available=max(Decimal(0),cap.total-cap.committed) if cap else None
                    needed=purchase_quantity(line)
                    capacity_ok=bool(cap and cap.independently_checked and cap.revision==line.revision and cap.unit==line.unit and req.as_of<=cap.valid_until and cap.available_by<=line.need_by and needed is not None and available>=needed)
                    capacity_rows.append(dict(line_id=line.id,available=str(available) if available is not None else None,quantity_needed=str(needed) if needed is not None else None,supported=capacity_ok))
                    if not capacity_ok:problems.append(issue('capacity_unverified_or_insufficient',line_id=line.id))
            peers=[s.id for s in req.suppliers if s.id!=supplier.id and s.country.casefold()==supplier.country.casefold() and ((s.registration_id and s.registration_id==supplier.registration_id) or s.legal_name.casefold()==supplier.legal_name.casefold())]
            if peers:problems.append(issue('possible_duplicate_supplier',supplier_ids=peers))
            demand_issues = []
            for line in req.requirements:
                _, found=facts(line);demand_issues.extend(dict(x,line_id=line.id) for x in found)
            problems.extend(demand_issues)
            result['items'].append(dict(supplier_id=supplier.id,legal_name=supplier.legal_name,assessments=rows,capacities=capacity_rows,issues=problems,status='needs_completion' if problems else 'candidate_review_required',independently_verified=False))
    else:
        for line in req.requirements:
            good,problems=facts(line)
            row=dict(line_id=line.id,sku=line.sku,revision=line.revision,issues=problems)
            if action=='requirements':
                net=purchase_quantity(line)
                if net is None:problems.append(issue('inventory_basis_unconfirmed'))
                row.update(confirmed_facts=good,ordered_demand=str(line.quantity),unit=line.unit,net_purchase_quantity=str(net) if net is not None else None,inventory_basis='supplied_confirmed_snapshot' if net is not None else 'unknown',rfq_draft=dict(line_id=line.id,sku=line.sku,revision=line.revision,quantity=str(net if net is not None else line.quantity),unit=line.unit,destination=line.destination,need_by=line.need_by.isoformat(),specifications=good))
            elif action=='comparison':
                offers=[]
                needed=purchase_quantity(line)
                if needed is None:problems.append(issue('inventory_basis_unconfirmed'))
                if needed==0:problems.append(issue('no_purchase_needed'))
                if not req.cost_basis or not req.required_costs:problems.append(issue('missing_cost_policy'))
                for offer in [o for o in req.offers if o.line_id==line.id]:
                    errors=[]
                    if offer.revision!=line.revision:errors.append('revision_mismatch')
                    if offer.quantity!=needed or offer.unit!=line.unit:errors.append('quantity_or_unit_not_comparable')
                    if offer.quantity<offer.moq:errors.append('below_moq')
                    if offer.valid_until<req.as_of:errors.append('expired_quote')
                    if offer.cost_basis!=req.cost_basis:errors.append('cost_basis_mismatch')
                    if not offer.reviewed:errors.append('quote_review_required')
                    missing=[k for k in req.required_costs if offer.costs.get(k) is None]
                    if missing or any(v is None for v in offer.costs.values()):errors.append('unknown_costs')
                    rate=Decimal(1) if offer.currency==req.comparison_currency else None
                    if rate is None:
                        fx=next((f for f in req.fx if f.currency==offer.currency and f.observed_at<=req.as_of<=f.valid_until),None)
                        if fx:rate=fx.rate
                        else:errors.append('missing_current_fx')
                    subtotal=offer.quantity*offer.unit_price
                    known=subtotal+sum((v for v in offer.costs.values() if v is not None),Decimal(0))
                    comparable=not errors and not problems
                    offers.append(dict(offer_id=offer.id,supplier_id=offer.supplier_id,goods_subtotal=str(subtotal),known_cost_total=str(known),quote_currency=offer.currency,normalized_known_cost=str(known*rate) if rate is not None else None,comparison_currency=req.comparison_currency,missing_costs=missing,issues=errors,comparable=comparable,cost_rank=None))
                eligible=sorted([o for o in offers if o['comparable']],key=lambda o:Decimal(o['normalized_known_cost']))
                for i,o in enumerate(eligible,1):o['cost_rank']=i
                if not offers:problems.append(issue('missing_quotes'))
                if any(o['issues'] for o in offers):problems.append(issue('quotes_need_completion'))
                row.update(offers=offers,ranking_scope='仅相同需求数量与口径的已确认成本，不代表供应商准入或采购授权',rfq_draft=dict(specifications=good,required_costs=req.required_costs,cost_basis=req.cost_basis))
            elif action=='quality':
                checks=[c for c in req.quality_checks if c.line_id==line.id]
                if not line.quality_checks:problems.append(issue('missing_quality_policy'))
                for name in line.quality_checks:
                    matches=[c for c in checks if c.name==name and c.revision==line.revision]
                    if not matches:problems.append(issue('missing_quality_check',name=name))
                measurements=[]
                for c in checks:
                    numeric=None
                    if c.measured_value is not None and (c.lower_limit is not None or c.upper_limit is not None):
                        numeric=(c.lower_limit is None or c.measured_value>=c.lower_limit) and (c.upper_limit is None or c.measured_value<=c.upper_limit)
                        if not numeric:problems.append(issue('measurement_out_of_bounds',check_id=c.id))
                    if c.measured_value is None and (c.lower_limit is not None or c.upper_limit is not None):problems.append(issue('measurement_missing',check_id=c.id))
                    measurements.append(dict(check_id=c.id,numeric_within_limits=numeric))
                    if c.revision!=line.revision:problems.append(issue('stale_quality_revision',check_id=c.id))
                    if not c.reviewed or c.state!='passed':problems.append(issue('quality_not_approved',check_id=c.id,state=c.state))
                row.update(measurements=measurements,checklist=[c.model_dump(mode='json') for c in checks],sample_versions=sorted({c.sample_version for c in checks}),sampling_plan='未自动推断AQL；按企业确认标准填写检查方法',production_released=False)
            elif action=='delivery':
                milestones=[m for m in req.milestones if m.line_id==line.id]; by_id={m.id:m for m in milestones};reports=[]
                if not milestones:problems.append(issue('missing_progress'))
                for m in milestones:
                    flags=[]
                    if m.revision!=line.revision:flags.append('stale_revision')
                    if m.observed_at>req.as_of or m.actual_at and m.actual_at>req.as_of:flags.append('future_record')
                    if m.actual_at and m.actual_at>m.observed_at:flags.append('completion_after_observation')
                    blocked=[d for d in m.depends_on if by_id[d].actual_at is None or by_id[d].actual_at>req.as_of]
                    if blocked:flags.append('dependency_unfinished')
                    if m.actual_at:
                        if m.actual_at>m.planned_at:flags.append('completed_late')
                        if any(by_id[d].actual_at and by_id[d].actual_at>m.actual_at for d in m.depends_on):flags.append('dependency_completed_after_child')
                    else:
                        if m.planned_at<req.as_of:flags.append('overdue')
                        if Decimal(str((req.as_of-m.observed_at).total_seconds()))/3600>req.progress_freshness_hours:flags.append('stale_progress')
                        if m.remaining_hours is None:flags.append('remaining_duration_unknown')
                        elif Decimal(str((line.need_by-req.as_of).total_seconds()))/3600<m.remaining_hours:flags.append('delivery_at_risk')
                    reports.append(dict(milestone_id=m.id,name=m.name,owner=m.owner,flags=flags,blocked_by=blocked,completed_on_time=m.actual_at<=m.planned_at if m.actual_at and not any(f in flags for f in ['future_record','completion_after_observation','dependency_unfinished','dependency_completed_after_child','stale_revision']) else None))
                    problems.extend(issue(f,milestone_id=m.id) for f in flags)
                row.update(milestones=reports,monitor_created=False,estimate_basis='用户提供的剩余自然小时，不是工作日排产预测')
            elif action=='settlement':
                order=next((o for o in req.orders if o.line_id==line.id),None)
                if not order:
                    problems.append(issue('missing_purchase_order'));row.update(net_accepted=None,billed_quantity=None,balance=None)
                else:
                    if not order.approved:problems.append(issue('order_review_required'))
                    if order.revision!=line.revision or order.unit!=line.unit:problems.append(issue('order_spec_mismatch'))
                    receipts=[r for r in req.receipts if r.line_id==line.id]; bills=[b for b in req.invoices if b.line_id==line.id];adjs=[a for a in req.adjustments if a.line_id==line.id]
                    if not receipts:problems.append(issue('missing_receipts'))
                    if not bills:problems.append(issue('missing_invoices'))
                    for r in receipts:
                        if r.revision!=order.revision or r.unit!=order.unit or not r.reviewed:problems.append(issue('receipt_unreviewed_or_mismatch',receipt_id=r.id))
                    for b in bills:
                        if (b.supplier_id,b.revision,b.unit,b.currency,b.unit_price)!=(order.supplier_id,order.revision,order.unit,order.currency,order.unit_price) or not b.reviewed:problems.append(issue('invoice_unreviewed_or_mismatch',invoice_id=b.id))
                    received=sum((r.received for r in receipts),Decimal(0)); accepted=sum((r.accepted-r.returned for r in receipts),Decimal(0)); rejected=sum((r.rejected for r in receipts),Decimal(0)); pending=sum((r.received-r.accepted-r.rejected for r in receipts),Decimal(0)); billed=sum((b.quantity for b in bills),Decimal(0))
                    if received!=order.quantity:problems.append(issue('received_quantity_difference',difference=str(received-order.quantity)))
                    if pending:problems.append(issue('inspection_pending',quantity=str(pending)))
                    if rejected or any(r.returned for r in receipts):problems.append(issue('quality_exception',rejected=str(rejected)))
                    if billed!=accepted:problems.append(issue('invoice_acceptance_difference',difference=str(billed-accepted)))
                    deductions=Decimal(0)
                    for a in adjs:
                        if a.currency!=order.currency or not a.confirmed:problems.append(issue('adjustment_unconfirmed_or_currency_mismatch',adjustment_id=a.id))
                        else:deductions+=a.amount
                    extra=sum((b.charges for b in bills),Decimal(0))
                    if extra:problems.append(issue('invoice_charges_require_contract_review',amount=str(extra)))
                    invoice_amount=sum((b.quantity*b.unit_price+b.charges for b in bills),Decimal(0))
                    balance=invoice_amount-deductions
                    if balance<0:problems.append(issue('credit_or_overpayment_balance'))
                    row.update(received_quantity=str(received),net_accepted=str(accepted),pending_inspection=str(pending),billed_quantity=str(billed),invoice_amount=str(invoice_amount),confirmed_payments_and_credits=str(deductions),declared_balance=str(balance),currency=order.currency,reconciled_balance=str(balance) if not problems else None,payment_authorized=False,exceptions=[x for x in problems if x['code'] in {'quality_exception','invoice_acceptance_difference','received_quantity_difference'}])
            row['status']='needs_completion' if problems else 'review_required'
            result['items'].append(row)
    if result['items']:
        result['status']='needs_completion' if any(x['issues'] for x in result['items']) else 'review_required'
    return result
