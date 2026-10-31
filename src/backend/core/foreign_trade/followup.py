"""Stateless follow-up proposals and evidence-linked reply routing; never sends."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal
from pydantic import Field, field_validator, model_validator
from core.foreign_trade.buyer_search import StrictModel, domain
from core.foreign_trade.lead_outreach import LeadInput, prioritize
from core.foreign_trade.acquisition import now

Intent = Literal['opt_out', 'not_interested', 'wrong_contact', 'out_of_office', 'request_quote', 'request_sample', 'interested', 'unknown']

def aware(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('时间必须包含时区')
    return value

class ReplyInput(StrictModel):
    buyer_id: str = Field(min_length=1, max_length=200)
    reply_text: str = Field(min_length=1, max_length=12000)
    source_reference: str = Field(min_length=1, max_length=500)
    received_at: datetime
    confirmed_intent: Intent | None = None
    evidence_excerpt: str = Field(default='', max_length=2000)

    @field_validator('received_at')
    @classmethod
    def timestamp(cls, value): return aware(value)

    @model_validator(mode='after')
    def evidence(self):
        if not self.reply_text.strip() or not self.source_reference.strip() or not self.buyer_id.strip():
            raise ValueError('买家、回复原文及来源不得为空')
        if self.confirmed_intent and (not self.evidence_excerpt.strip() or self.evidence_excerpt not in self.reply_text):
            raise ValueError('人工确认分类必须引用回复原文中的证据片段')
        return self

# Conservative suggestions, not a learned classifier. Quoted text may trigger a
# safety hold; an ambiguous message always requires a human to review its scope.
PATTERNS = {
    'opt_out': r'\bunsubscribe\b|remove me|do not contact|stop (?:emailing|contacting)|退订|不要再联系|停止联系',
    'not_interested': r'not interested|no interest|不感兴趣|不需要',
    'wrong_contact': r'wrong (?:person|contact)|not the right person|找错人|非本人负责',
    'out_of_office': r'out of (?:the )?office|automatic reply|auto.?reply|休假|自动回复',
    'request_quote': r'quotation|\bquote\b|price list|报价|价格表',
    'request_sample': r'\bsamples?\b|样品|寄样',
    'interested': r'\binterested\b|send (?:me |us )?(?:a |the |your )?catalog|感兴趣|发.*目录',
}
ACTIONS = {
    'opt_out': '停止联系；记录待同步的拒绝联系标记，不生成营销回复',
    'not_interested': '停止本轮跟进；未来重启须取得用户明确指示',
    'wrong_contact': '暂停原渠道；返回联系人发现，不猜测新邮箱',
    'out_of_office': '暂停计划；人工核对返岗日期与时区后重新规划',
    'request_quote': '转询盘处理；补齐规格、数量、包装、目的国、交期和贸易条款',
    'request_sample': '转样品需求处理；确认规格、数量、地址、费用及交期',
    'interested': '转人工沟通；明确下一步和所需资料',
    'unknown': '暂停跟进；人工阅读原文并确认意图',
}

def triage_reply(req: ReplyInput):
    matches = [{'intent': key, 'excerpt': match.group()} for key, pattern in PATTERNS.items()
               if (match := re.search(pattern, req.reply_text, re.I))]
    detected = {m['intent'] for m in matches}
    # Any opt-out cue blocks marketing even if another intent was supplied.
    intent = 'opt_out' if 'opt_out' in detected else req.confirmed_intent or 'unknown'
    suggested = ('opt_out' if 'opt_out' in detected else 'not_interested' if 'not_interested' in detected
                 else matches[0]['intent'] if len(matches) == 1 else 'unknown')
    confirmed = bool(req.confirmed_intent and req.confirmed_intent == intent)
    return dict(buyer_id=req.buyer_id, intent=intent, suggested_intent=suggested,
                matches=matches, evidence_excerpt=req.evidence_excerpt,
                needs_review=not confirmed, do_not_contact=intent == 'opt_out',
                pause_sequence=True, next_action=ACTIONS[intent],
                missing_fields=(['规格', '数量', '包装', '目的国', '交期', '贸易条款'] if intent == 'request_quote' else []),
                rule_version='reply-rules-v1-uncalibrated', classification_mode='rules_and_human_review',
                confidence=None, created_at=now(), input_snapshot=req.model_dump(mode='json'),
                sending_status='not_sent', persistence='not_saved',
                warnings=['规则只给候选分类；否定、引用邮件与多意图须人工核对，不声明模型准确率。'])

class ContactInput(StrictModel):
    channel: str = Field(min_length=1, max_length=2048)
    channel_type: Literal['email', 'contact_page']
    source_url: str = Field(min_length=1, max_length=2048)
    retrieved_at: datetime
    purpose_confirmed: bool = False

    @field_validator('retrieved_at')
    @classmethod
    def timestamp(cls, value): return aware(value)

    @model_validator(mode='after')
    def valid(self):
        if not domain(self.source_url): raise ValueError('联系渠道须附公开来源')
        if self.channel_type == 'email' and not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', self.channel):
            raise ValueError('邮箱格式无效')
        if self.channel_type == 'contact_page' and not domain(self.channel): raise ValueError('联系页无效')
        return self

class CadenceInput(StrictModel):
    lead: LeadInput
    contact: ContactInput
    timezone: str = Field(min_length=1, max_length=100)
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    initial_sent_at: datetime | None = None
    followup_sent_at: list[datetime] = Field(default_factory=list, max_length=3)
    max_followups: int = Field(default=3, ge=0, le=3, strict=True)
    bounced: bool = False
    reply: ReplyInput | None = None

    @field_validator('as_of', 'initial_sent_at')
    @classmethod
    def timestamp(cls, value): return aware(value) if value else value

    @model_validator(mode='after')
    def valid(self):
        try: ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError('请提供有效 IANA 时区，如 Europe/Berlin')
        for sent in self.followup_sent_at: aware(sent)
        if self.initial_sent_at and self.initial_sent_at > self.as_of: raise ValueError('首次发送时间不能晚于评估时间')
        if self.followup_sent_at and not self.initial_sent_at: raise ValueError('跟进记录需要首次发送时间')
        if self.followup_sent_at != sorted(set(self.followup_sent_at)): raise ValueError('实际跟进时间必须按顺序且不重复')
        if any(sent <= self.initial_sent_at or sent > self.as_of for sent in self.followup_sent_at): raise ValueError('跟进时间必须在首次发送之后、评估时间之前')
        if self.contact.retrieved_at > self.as_of: raise ValueError('渠道获取时间不能晚于评估时间')
        if self.reply and self.reply.buyer_id != self.lead.buyer_id: raise ValueError('回复与线索必须属于同一买家')
        if self.reply and self.reply.received_at > self.as_of: raise ValueError('回复时间不能晚于评估时间')
        return self


def plan_cadence(req: CadenceInput):
    score = prioritize(req.lead)
    reply = triage_reply(req.reply) if req.reply else None
    if score['priority'] == 'stop' or req.bounced or (reply and reply['intent'] in {'opt_out', 'not_interested'}):
        status, reason = 'stopped', '拒绝联系、硬排除、不适合、退信或明确拒绝，停止本轮计划'
    elif reply:
        status, reason = 'paused_reply', reply['next_action']
    elif score['priority'] != 'follow_up':
        status, reason = 'blocked_priority', score['next_action']
    elif not req.contact.purpose_confirmed:
        status, reason = 'needs_channel_review', '请核对该渠道归属和联系用途'
    elif not req.initial_sent_at:
        status, reason = 'awaiting_initial_send', '尚无实际首封发送记录；先审核首封，发送后再规划时间'
    elif len(req.followup_sent_at) >= req.max_followups:
        status, reason = 'exhausted', '已达到本轮跟进上限，等待回复或人工复盘'
    else:
        status, reason = 'planned', '日历建议待审核；不是后台任务或发送承诺'
    steps = []
    if status == 'planned':
        tz = ZoneInfo(req.timezone)
        anchor = req.initial_sent_at.astimezone(tz)
        previous = (req.followup_sent_at[-1] if req.followup_sent_at else req.initial_sent_at).astimezone(tz)
        for index in range(len(req.followup_sent_at), req.max_followups):
            target = max(anchor + timedelta(days=[3, 7, 14][index]), previous + timedelta(days=3))
            target = target.replace(hour=9, minute=30, second=0, microsecond=0)
            while target.weekday() >= 5: target += timedelta(days=1)
            steps.append(dict(step=index+1, due_at=target.isoformat(),
                              status='overdue_review' if target <= req.as_of else 'proposed',
                              purpose=['核对负责人及是否收到', '征询是否需要目录或规格', '礼貌收尾并暂停本轮'][index],
                              approval_required=True))
            previous = target
    return dict(buyer_id=req.lead.buyer_id, status=status, reason=reason, score=score, reply=reply,
                steps=steps, timezone=req.timezone, rule_version='cadence-v1-uncalibrated',
                created_at=now(), input_snapshot=req.model_dump(mode='json'),
                do_not_contact=req.lead.do_not_contact or bool(reply and reply['do_not_contact']),
                sending_status='not_sent', scheduling_status='not_scheduled', persistence='not_saved',
                metrics=dict(actual_followups=len(req.followup_sent_at), proposed_followups=len(steps), overdue_reviews=sum(s['status']=='overdue_review' for s in steps)),
                warnings=['3/7/14天为未校准默认值；跳过周末，不校验当地节假日。', '仅按提供的记录计算；换渠道不代表可重新联系，需用户核对全部历史。'])
