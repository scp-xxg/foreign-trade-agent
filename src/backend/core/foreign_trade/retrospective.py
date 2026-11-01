"""Evidence-linked review drafts and explicit observation-window funnel arithmetic."""
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from core.foreign_trade.buyer_search import StrictModel
from core.foreign_trade.communication import Source

STAGES = {
    'deal-timeline': 'trade-deal-timeline',
    'funnel-analysis': 'trade-funnel-analysis',
    'win-loss-analysis': 'trade-win-loss-analysis',
    'improvement-planning': 'trade-improvement-planning',
    'playbook-learning': 'trade-playbook-learning',
}
Stage = Literal['lead', 'reply', 'inquiry', 'quote', 'sample', 'trial', 'won']

class Evidence(StrictModel):
    source_id: str = Field(min_length=1, max_length=80)
    excerpt: str = Field(min_length=1, max_length=3000)

class Event(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    deal_id: str = Field(min_length=1, max_length=100)
    at: AwareDatetime
    kind: Literal['planned', 'actual']
    stage: Stage
    description: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default='', max_length=200)
    version: str = Field(default='', max_length=100)
    evidence: list[Evidence] = Field(min_length=1, max_length=10)

class Deal(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    channel: str = Field(default='unknown', min_length=1, max_length=100)
    outcome: Literal['open', 'paused', 'won', 'lost', 'unknown'] = 'unknown'
    outcome_evidence: list[Evidence] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def supported(self):
        if self.outcome in {'won', 'lost'} and not self.outcome_evidence:
            raise ValueError('赢丢单状态必须提供证据')
        return self

class Reason(StrictModel):
    deal_id: str = Field(min_length=1, max_length=100)
    category: Literal['product', 'price', 'delivery', 'quality', 'trust', 'payment', 'purchase_change', 'execution', 'unknown']
    explanation: str = Field(min_length=1, max_length=2000)
    kind: Literal['customer_statement', 'observed_factor', 'hypothesis'] = 'hypothesis'
    controllable: Literal['yes', 'no', 'unknown'] = 'unknown'
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    counterevidence: list[Evidence] = Field(default_factory=list, max_length=10)
    verification_question: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def supported(self):
        if self.kind != 'hypothesis' and not self.evidence:
            raise ValueError('客户陈述及观察因素必须提供证据')
        return self

class Action(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    problem: str = Field(min_length=1, max_length=2000)
    evidence: list[Evidence] = Field(min_length=1, max_length=10)
    hypothesis: str = Field(default='', max_length=1000)
    owner: str = Field(default='', max_length=200)
    due_at: AwareDatetime | None = None
    deliverable: str = Field(default='', max_length=1000)
    acceptance: str = Field(default='', max_length=1000)
    metric: str = Field(default='', max_length=500)
    baseline: str = Field(default='', max_length=500)
    target: str = Field(default='', max_length=500)
    population: str = Field(default='', max_length=500)
    comparison: str = Field(default='', max_length=1000)
    guardrail: str = Field(default='', max_length=500)
    check_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    completion_evidence: list[Evidence] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def supported(self):
        if self.completed_at and not self.completion_evidence:
            raise ValueError('完成动作必须提供实际执行证据')
        if self.check_at and self.due_at and self.check_at < self.due_at:
            raise ValueError('效果检查时间不得早于执行截止时间')
        return self

class Lesson(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=3000)
    applicability: str = Field(default='', max_length=1000)
    exceptions: str = Field(default='', max_length=1000)
    deal_ids: list[str] = Field(min_length=1, max_length=100)
    evidence: list[Evidence] = Field(min_length=1, max_length=10)
    validation_evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    requested_tier: Literal['case', 'hypothesis', 'validated'] = 'case'
    reviewer: str = Field(default='', max_length=200)
    version: str = Field(default='1', min_length=1, max_length=80)
    review_at: AwareDatetime | None = None

class RetrospectiveInput(StrictModel):
    scope: Literal['deal', 'period'] = 'deal'
    goal: str = Field(default='', max_length=2000)
    as_of: AwareDatetime
    period_start: AwareDatetime | None = None
    period_end: AwareDatetime | None = None
    observation_days: int = Field(default=30, ge=1, le=3650, strict=True)
    stage_order: list[Stage] = Field(default_factory=lambda: ['lead', 'reply', 'inquiry', 'quote', 'sample', 'trial', 'won'], min_length=2, max_length=7)
    sources: list[Source] = Field(default_factory=list, max_length=100)
    events: list[Event] = Field(default_factory=list, max_length=1000)
    deals: list[Deal] = Field(default_factory=list, max_length=500)
    reasons: list[Reason] = Field(default_factory=list, max_length=100)
    actions: list[Action] = Field(default_factory=list, max_length=100)
    lessons: list[Lesson] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def linked(self):
        for rows in [self.sources, self.events, self.deals, self.actions, self.lessons]:
            if len({r.id for r in rows}) != len(rows):
                raise ValueError('同类记录ID不得重复')
        if len(set(self.stage_order)) != len(self.stage_order):
            raise ValueError('阶段顺序不能重复')
        if bool(self.period_start) != bool(self.period_end):
            raise ValueError('统计起止时间必须同时提供')
        if self.period_start and (self.period_start >= self.period_end or self.period_end > self.as_of):
            raise ValueError('统计区间必须为start < end <= as_of')
        sources = {s.id: s for s in self.sources}
        refs = []
        for rows, names in [(self.events, ['evidence']), (self.deals, ['outcome_evidence']),
                            (self.reasons, ['evidence', 'counterevidence']),
                            (self.actions, ['evidence', 'completion_evidence']),
                            (self.lessons, ['evidence', 'validation_evidence'])]:
            for row in rows:
                for name in names:
                    refs.extend(getattr(row, name))
        for ref in refs:
            if ref.source_id not in sources or not ref.excerpt.strip() or ref.excerpt not in sources[ref.source_id].text:
                raise ValueError('证据必须引用已提供来源的原文子串')
        ids = {d.id for d in self.deals}
        if any(r.deal_id not in ids for r in [*self.events, *self.reasons]):
            raise ValueError('事件及原因必须关联已提供商机')
        if any(i not in ids for lesson in self.lessons for i in lesson.deal_ids):
            raise ValueError('案例必须关联已提供商机')
        if any(a.completed_at and a.completed_at > self.as_of for a in self.actions):
            raise ValueError('未来计划不能标记为已完成')
        return self


def review(req: RetrospectiveInput, action: str):
    if action not in STAGES:
        raise ValueError('不支持的复盘操作')
    sources = {s.id: s for s in req.sources}
    def evidence(refs):
        return [dict(**r.model_dump(), reference=sources[r.source_id].reference) for r in refs]
    def row(item):
        result = item.model_dump(mode='json')
        for field in ['evidence', 'counterevidence', 'outcome_evidence', 'completion_evidence', 'validation_evidence']:
            if hasattr(item, field): result[field] = evidence(getattr(item, field))
        return result
    result = dict(stage=action, scope=req.scope, as_of=req.as_of.isoformat(), goal=req.goal,
                  status='draft_review_required', saved=False, sent=False, approval_required=True,
                  rule_version='retrospective-v1', metrics={'business_effect': None},
                  warnings=['原文关联仅检查引用，不能独立证明字段、时间、结果或因果真实。未连接完整业务数据库，统计仅覆盖本次提供的材料。'])
    if action == 'deal-timeline':
        seen = set(); timeline = []; duplicates = []
        for event in sorted(req.events, key=lambda e: (e.at, e.id)):
            key = (event.deal_id, event.at, event.kind, event.stage, event.description, event.actor, event.version)
            if key in seen:
                duplicates.append(event.id)
                continue
            seen.add(key)
            timeline.append(dict(**row(event), temporal_state='future' if event.at > req.as_of else 'recorded'))
        groups = {}
        for event in req.events:
            key = (event.deal_id, event.stage, event.version)
            groups.setdefault(key, []).append(event)
        comparisons = []
        for (deal_id, stage, version), events in groups.items():
            planned = [e for e in events if e.kind == 'planned']
            actual = [e for e in events if e.kind == 'actual' and e.at <= req.as_of]
            # Pair only unambiguous single events; repeated versions need human reconciliation.
            if len(planned) == 1 and len(actual) <= 1:
                p = planned[0]; a = actual[0] if actual else None
                comparisons.append(dict(deal_id=deal_id, stage=stage, version=version, planned_id=p.id,
                    actual_id=a.id if a else None, status='matched_pending_review' if a else 'overdue_unconfirmed' if p.at < req.as_of else 'planned',
                    delay_hours=round((a.at-p.at).total_seconds()/3600, 2) if a else None))
            elif planned:
                comparisons.append(dict(deal_id=deal_id, stage=stage, version=version,status='requires_reconciliation'))
        result.update(timeline=timeline, duplicate_candidates=duplicates, plan_comparisons=comparisons,
                      next_actions=['核对同版本事件及转折点；未来actual记录不可视为已发生，逾期未见回执不等于确认未执行。'])
    elif action == 'funnel-analysis':
        if req.scope == 'deal':
            return dict(result, status='skipped_single_deal', reason='单商机使用时间线与原因分析，不据此推断整体转化')
        if not req.period_start:
            return dict(result, status='needs_scope', missing_fields=['period_start', 'period_end'])
        actual = [e for e in req.events if e.kind == 'actual' and e.at <= req.as_of]
        first = {}
        for e in actual:
            key = (e.deal_id, e.stage)
            first[key] = min(first.get(key, e.at), e.at)
        def analyze(ids):
            activity = {stage: len({e.deal_id for e in actual if e.deal_id in ids and e.stage == stage and req.period_start <= e.at < req.period_end}) for stage in req.stage_order}
            conversions = []
            for start, end in zip(req.stage_order, req.stage_order[1:]):
                cohort = [(i, first[i,start]) for i in ids if (i,start) in first and req.period_start <= first[i,start] < req.period_end]
                mature = [(i,t) for i,t in cohort if t + timedelta(days=req.observation_days) <= req.as_of]
                converted = [(i,t,first[i,end]) for i,t in mature if (i,end) in first and t <= first[i,end] <= t+timedelta(days=req.observation_days)]
                duration = [(u-t).total_seconds()/86400 for i,t,u in converted]
                denominator = len(mature); numerator = len(converted)
                conversions.append(dict(from_stage=start,to_stage=end,cohort_count=len(cohort),denominator=denominator,numerator=numerator,
                    pending_observation=len(cohort)-denominator,rate_pct=str((Decimal(numerator)*100/denominator).quantize(Decimal('0.01'))) if denominator else None,
                    median_days=round(median(duration),2) if duration else None,
                    out_of_order_ids=[i for i,t in cohort if (i,end) in first and first[i,end]<t]))
            return dict(activity=activity,conversions=conversions)
        ids = {d.id for d in req.deals}
        channels = sorted({d.channel for d in req.deals})
        result.update(unit='deal',period={'start_inclusive':req.period_start.isoformat(),'end_exclusive':req.period_end.isoformat()},
            observation_days=req.observation_days, sample_size=len(ids), **analyze(ids),
            by_channel={c:analyze({d.id for d in req.deals if d.channel==c}) for c in channels},
            outcome_counts={state:sum(d.outcome==state for d in req.deals) for state in ['open','paused','won','lost','unknown']},
            evidence_coverage={'deals_with_actual_events':len({e.deal_id for e in actual}),'supplied_deals':len(ids)},
            next_actions=['活动量与同批转化不能混用；分母仅包含完整观察期的商机，未成熟单独列出。跳过不适用阶段可调整stage_order，不补造中间事件。小样本不排名，不直接归因渠道效果。'])
    elif action == 'win-loss-analysis':
        deals = {d.id:d for d in req.deals}
        reasons = [dict(**row(r),outcome=deals[r.deal_id].outcome,
                   assessment='hypothesis_to_verify' if r.kind=='hypothesis' else 'source_linked_factor_not_proven_cause') for r in req.reasons]
        result.update(status='needs_evidence' if not reasons else 'draft_review_required', reasons=reasons,
            missing_reason_deals=[d.id for d in req.deals if not any(r.deal_id==d.id for r in req.reasons)],
            next_actions=['复核客户陈述、观察因素与假设；推进中只分析障碍，不标丢单。保留反证，客户沉默不能证明价格导致丢单。'])
    elif action == 'improvement-planning':
        actions = []
        required = ['owner','due_at','deliverable','acceptance','metric','baseline','target','check_at']
        for a in req.actions:
            missing = [f for f in required if not getattr(a,f)]
            experiment_missing = [f for f in ['hypothesis','population','comparison','guardrail'] if not getattr(a,f)]
            actions.append(dict(**row(a), missing_fields=missing, experiment_missing_fields=experiment_missing,
                status='completed_evidence_pending_review' if a.completed_at else 'overdue' if a.due_at and a.due_at<req.as_of else 'planned',
                executable=not missing, experiment_ready=not missing and not experiment_missing, business_effect=None))
        result.update(status='needs_actions' if not actions else 'draft_review_required',actions=actions,
            next_actions=['先为每个问题草拟可执行动作，缺负责人或期限由用户确认；完成不等于效果改善。未提供实验结果不声称显著有效；这里只生成任务与检查计划，不创建提醒。'])
    else:
        lessons = []; titles = {}
        for lesson in req.lessons:
            normalized = lesson.title.strip().casefold()
            titles.setdefault(normalized, []).append(lesson.id)
            missing = [f for f in ['applicability','exceptions','reviewer','review_at'] if not getattr(lesson,f)]
            validation_missing = []
            if lesson.requested_tier == 'validated':
                if len(set(lesson.deal_ids)) < 2: validation_missing.append('multiple_distinct_deals')
                if not lesson.validation_evidence: validation_missing.append('validation_evidence')
            lessons.append(dict(**row(lesson),publication_status='candidate_pending_review',missing_fields=missing,
                validation_missing_fields=validation_missing,tier='case' if len(set(lesson.deal_ids))<2 else 'hypothesis',
                requested_tier_requires_review=lesson.requested_tier=='validated',
                review_due=bool(lesson.review_at and lesson.review_at<req.as_of)))
        result.update(status='needs_lessons' if not lessons else 'draft_review_required',lessons=lessons,
            duplicate_title_candidates=[ids for ids in titles.values() if len(ids)>1],
            knowledge_base_check='not_performed',saved=False,
            next_actions=['只对本次条目检查同名候选；未检索现有知识库不能声称已查重。单次赢单仅形成案例，多次引用也不自动证明因果；审核后另行授权写入知识库或修改技能。'])
    return result
