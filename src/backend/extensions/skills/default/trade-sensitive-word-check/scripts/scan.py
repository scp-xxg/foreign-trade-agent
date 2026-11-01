"""Local lexical candidate scanner. No network, rewriting, sending or legal verdicts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT = 200000
MAX_HITS = 2000

def normalize(text):
    """NFKC per character, retaining original Python code-point offsets."""
    chars, starts, ends = [], [], []
    for i, char in enumerate(text):
        if char in '\u200b\u200c\u200d\ufeff':
            continue
        for c in unicodedata.normalize('NFKC', char):
            chars.append(c); starts.append(i); ends.append(i + 1)
    return ''.join(chars), starts, ends

def validate(data):
    if not isinstance(data, dict) or set(data) - {'fields', 'context'}:
        raise ValueError('输入必须是包含 fields 和可选 context 的对象')
    fields = data.get('fields')
    if not isinstance(fields, list) or not 1 <= len(fields) <= 100:
        raise ValueError('fields需要1至100个文本字段')
    ids = set(); size = 0
    for item in fields:
        if not isinstance(item, dict) or set(item) - {'id', 'text', 'placement'}:
            raise ValueError('字段仅接受id/text/placement')
        for key in ['id', 'text']:
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError('id和text必须是非空字符串')
        if len(item['id']) > 200 or item['id'] in ids:
            raise ValueError('字段id重复或过长')
        if 'placement' in item and (not isinstance(item['placement'], str) or len(item['placement']) > 200):
            raise ValueError('placement必须是不超过200字符的字符串')
        ids.add(item['id']); size += len(item['text'])
    if size > MAX_TEXT:
        raise ValueError('文本总长度超过200000字符，请拆分')
    context = data.get('context', {})
    if not isinstance(context, dict) or set(context) - {'platform', 'market', 'language', 'category', 'purpose'}:
        raise ValueError('context仅支持platform/market/language/category/purpose')
    if any(not isinstance(v, str) or len(v) > 500 for v in context.values()):
        raise ValueError('context各项必须是不超过500字符的字符串')
    return fields, context

def scan(data):
    fields, context = validate(data)
    raw = (ROOT / 'references/rules.json').read_bytes()
    bundle = json.loads(raw)
    if hashlib.sha256((ROOT / 'references/source-lexicon-v4.0.md').read_bytes()).hexdigest() != bundle['source_sha256']:
        raise ValueError('原始词库校验失败，请更新规则版本与来源哈希')
    hits = []; truncated = False
    for field in fields:
        text = field['text']; norm, starts, ends = normalize(text)
        for rule in bundle['rules']:
            for match in re.finditer(rule['pattern'], norm):
                if len(hits) >= MAX_HITS:
                    truncated = True; break
                start, end = starts[match.start()], ends[match.end()-1]
                line = text.count('\n', 0, start) + 1
                col = start - text.rfind('\n', 0, start)
                review = {'platform': 'platform_applicability_review', 'context': 'context_review', 'evidence': 'evidence_review'}[rule['context']]
                hits.append(dict(rule_id=rule['id'], level=rule['level'], category=rule['category'],
                    field_id=field['id'], placement=field.get('placement', 'unspecified'),
                    match=text[start:end], span=[start, end], line=line, column=col,
                    context=text[max(0,start-60):min(len(text),end+60)],
                    reason=rule['reason'], suggestion=rule['suggestion'], review_status=review,
                    applicability='not_determined', source_section=rule['source_section'],
                    related_rule_ids=[rule['id']]))
            if truncated: break
        if truncated: break
    # Merge exact identical spans only; separate and nested claims remain inspectable.
    merged = {}
    for hit in hits:
        key = (hit['field_id'], *hit['span'])
        old = merged.get(key)
        if old:
            related = old['related_rule_ids'] + hit['related_rule_ids']
            if int(hit['level'][1]) > int(old['level'][1]): merged[key] = hit
            merged[key]['related_rule_ids'] = related
        else: merged[key] = hit
    order = {field['id']: i for i,field in enumerate(fields)}
    hits = sorted(merged.values(), key=lambda h: (order[h['field_id']],h['span'][0],-int(h['level'][1])))
    levels = {level:sum(h['level']==level for h in hits) for level in ['L1','L2','L3','L4']}
    missing = [k for k in ['platform','market','language','category','purpose'] if not context.get(k)]
    high = levels['L3'] + levels['L4'] > 0
    return dict(schema_version=1, rule_version=bundle['version'], rules_sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256=bundle['source_sha256'], input_sha256=hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        status='incomplete' if truncated else 'review_required' if hits else 'no_lexical_hits',
        recommended_action='hold_for_review' if high or truncated else 'review_in_context' if hits else 'continue_context_review',
        scan_complete=not truncated, scanned_field_ids=[f['id'] for f in fields] if not truncated else list(dict.fromkeys(h['field_id'] for h in hits)),
        counts=levels, hits=hits, context=context, missing_context=missing,
        coverage=dict(rule_count=len(bundle['rules']), mode='text_pattern_candidates', semantic_review='not_performed',
                      evidence_verification='not_performed', image_ocr='not_performed', legal_or_platform_approval=False),
        external_action_executed=False, metrics=dict(precision=None,recall=None,rewrite_acceptance=None),
        limitations=['命中为用户词库风险候选，等级是内部复核优先级，不是违法结论。',
            '未命中不代表合规；图片、地图、符号、事实真实性、最新法规和上下文需另行审核。',
            '不自动采用邻近白名单，不自动改写、删除、发布或阻断其他应用。',
            '仅覆盖规则文件列出的模式；多语种为有限示例，不是完整语义或词形覆盖。'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,help='UTF-8 JSON file, or - for stdin')
    parser.add_argument('--output',help='Write report to a new JSON file; otherwise stdout')
    args=parser.parse_args()
    try:
        if args.input == '-': raw=sys.stdin.read(1500001)
        else:
            if Path(args.input).stat().st_size > 1500000: raise ValueError('输入JSON过大')
            raw=Path(args.input).read_text(encoding='utf-8')
        if len(raw)>1500000: raise ValueError('输入JSON过大')
        report=scan(json.loads(raw))
        payload=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
        if args.output:
            with Path(args.output).open('x',encoding='utf-8') as f:f.write(payload)
        else: print(payload,end='')
    except (ValueError,OSError,TypeError,KeyError,re.error) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
    return 0
if __name__=='__main__':sys.exit(main())
