"""Visible, non-blocking integration of an account's own lexicon checks."""
from copy import deepcopy
import hashlib
import json

CHECK_FAILED = '敏感词检查未完成，请人工核对当前账号词库；不能据此认定未命中。'

def scan_output(db, user_id, fields):
    try:
        from core.foreign_trade.lexicon import scan_fields, format_notice
        report = scan_fields(db, user_id, fields)
        return report, format_notice(report)
    except Exception:
        # Provider, database and document errors may contain private content.
        return {'status':'error','matches':[],'match_count':0}, CHECK_FAILED

def scan_chat_output(user_id, text):
    try:
        from core.db.engine import SessionLocal
        with SessionLocal() as db:
            return scan_output(db, user_id, {'body':text})
    except Exception:
        return {'status':'error','matches':[],'match_count':0}, CHECK_FAILED

def attach_notice(payload, report, notice):
    payload['sensitive_terms'] = deepcopy(report)
    if notice:
        warnings = payload.get('warnings')
        payload['warnings'] = list(warnings) if isinstance(warnings,list) else []
        if notice not in payload['warnings']:
            payload['warnings'].append(notice)
    return payload

def _identity(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]

def append_review_feedback(feedback, rules, report, channel):
    if report.get('status') == 'not_configured':
        return
    source_name = str(report.get('source_name') or '当前账号敏感词库')
    version = str(report.get('version') or 'unavailable')
    matches = report.get('matches') or []
    failed = report.get('status') == 'error'
    # Preserve existing annotations and the bounded review receipt contract.
    capacity = max(0,min(100,500-len(feedback['text_annotations'])))
    total = max(len(matches), int(report.get('match_count') or 0))
    candidates = matches if not failed else [{'rule_id':'check_unavailable','field':'body','match':'','level':'L1','reason':CHECK_FAILED,'suggestion':'检查词库配置或人工核对原文后重试。'}]
    visible = candidates[:capacity]
    report['review_visible_count'] = len(visible)
    report['review_truncated'] = (1 if failed else total)>len(visible)
    summary_pending = not visible and (failed or total > 0)
    if report['review_truncated']:
        report['review_notice'] = (CHECK_FAILED + ' 当前审核批注容量已满，检查状态以摘要显示。' if failed else
            f'敏感词命中 {total} 处，受审核批注容量限制展示 {len(visible)} 条；未展示项仍待人工确认，扫描摘要及保留命中见审核JSON中的sensitive_terms；超出扫描保留上限的内容请分段检查。')
    evidence = {}
    for hit in visible:
        rid = 'lexicon.'+_identity([report.get('source_sha256'),hit.get('rule_id')])
        level = hit.get('level','L1')
        severity = {'L1':'info','L2':'low','L3':'medium','L4':'high'}.get(level,'info')
        if rid not in evidence:
            evidence[rid]={'rule_id':rid,'rule_version':version,'status':'active','category':'sensitive_terms','channels':[channel],
                'title':source_name+' · '+str(hit.get('rule_id','检查状态')),
                'summary':'当前账号提供的词库匹配提示；命中不等于违法、平台处罚或认证结论。',
                'source_url':str(hit.get('source_url') or report.get('source_url') or ''),
                'source_publisher':'用户提供的敏感词库','verified_at':'','effective_from':'',
                'scope_note':'依据 '+str(hit.get('source_section') or '词库检查状态')+'；需要结合目标平台、市场和真实证据人工复核。'}
        feedback['text_annotations'].append({'annotation_id':'annotation_'+_identity([rid,hit.get('field'),hit.get('start'),hit.get('end'),len(feedback['text_annotations'])]),
            'rule_id':rid,'category':'sensitive_terms','field':hit.get('field','body'),'quote':str(hit.get('match') or '')[:240],
            'severity':severity,'status':'needs_confirmation','message':'用户词库提示（需核实适用范围）：'+str(hit.get('reason') or ''),
            'suggestion':'仅供参考，不得新增未证实事实：'+str(hit.get('suggestion') or ''),
            'level':level,'source_rule_id':str(hit.get('rule_id') or ''),'source_section':str(hit.get('source_section') or ''),'source_line':hit.get('source_line'),'start':hit.get('start'),'end':hit.get('end')})
    if not visible:
        rid='lexicon.'+_identity([report.get('source_sha256'),'check_unavailable' if failed else 'scan'])
        evidence[rid]={'rule_id':rid,'rule_version':version,'status':'active','category':'sensitive_terms','channels':[channel],
            'title':('敏感词检查未完成（待人工核对）' if failed else f'敏感词命中 {total} 处（批注容量已满，待确认）' if summary_pending else source_name),
            'summary':report.get('review_notice') or '已执行词库检查；没有命中不等于完整合规。','source_url':str(report.get('source_url') or ''),
            'source_publisher':'用户提供的敏感词库','verified_at':'','effective_from':'','scope_note':'自动匹配覆盖范围以当前词库及检查结果为准。'}
    ranks={'info':0,'low':1,'medium':2,'high':3}
    for rid, rule in evidence.items():
        rules.append(rule)
        found=[a for a in feedback['text_annotations'] if a['rule_id']==rid]
        feedback['checks'].append({'rule_id':rid,'status':'needs_confirmation' if found or summary_pending else 'passed','annotation_count':len(found)})
        if found:
            feedback['risk_labels'].append({'code':rid,'label':rule['title'],'severity':max((a['severity'] for a in found),key=ranks.get),'count':len(found)})
        elif summary_pending:
            feedback['risk_labels'].append({'code':rid,'label':rule['title'],'severity':'medium','count':min(500,max(1,total))})
    issues=sum(a['status']=='issue' for a in feedback['text_annotations'])
    confirmations=len(feedback['text_annotations'])-issues
    feedback['summary']={'issue_count':issues,'needs_confirmation_count':confirmations,'review_status':'needs_revision' if issues else 'needs_confirmation' if confirmations else 'no_issues_detected'}


async def finish_chat_notice(turn, chunk):
    """Emit the exact same suffix that will be saved in the assistant message."""
    if chunk.get('manual_compaction') or not turn.full_response.strip():
        return None
    import asyncio
    report, notice = await asyncio.to_thread(scan_chat_output,turn.user_id,turn.full_response)
    if notice and not turn.full_response.endswith(notice):
        suffix='\n\n'+notice
        turn.full_response+=suffix
        turn.segments.add_text(suffix)
        await turn.emit({'type':'content','event':'ai_message','delta':suffix,'chat_id':turn.chat_id})
    return report

async def finish_child_notice(user_id, text, emit=None):
    if not text.strip():
        return text
    import asyncio
    _, notice = await asyncio.to_thread(scan_chat_output,user_id,text)
    if notice and not text.endswith(notice):
        suffix='\n\n'+notice
        if emit is not None:
            emit({'sub_type':'content','delta':suffix})
        return text+suffix
    return text
