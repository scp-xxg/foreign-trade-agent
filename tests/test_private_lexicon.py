"""Lexicon import and matching tests use synthetic data, not private uploaded files."""
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from core.db.engine import Base
from core.db.models.foreign_trade_lexicon import ForeignTradeLexicon
from core.foreign_trade.lexicon import compile_markdown,scan_bundle,activate,scan_fields,format_notice

def source():
    # A deliberately tiny independently authored fixture.
    rules=[('S301',r'(?i)\bbest\s+price\b','L3','price claim','do not invent proof'),
           ('S402',r'(?i)\bfda\s+approved\b','L4','approval claim','check evidence'),
           ('S404',r'(?i)\b(cure|treat|heal)\b','L4','health claim','check evidence'),
           ('S302',r'(?i)\b(#1|no\.?\s*1)\b','L3','rank','check evidence')]
    return '版本：**v4.0**\n'+chr(96)*3+'python\nRULES = '+repr(rules)+'\n'+chr(96)*3+'\n## 3. Terms\n| 英文 | 建议替换 |\n|---|---|\n| best | evidence |\n'

def bundle():return compile_markdown(source(),'synthetic.md')

def test_scanner_reports_source_offsets_and_preserves_input():
    text='🙂 FDA approved; best price; cures; #1.'
    result=scan_bundle(bundle(),{'body':text})
    assert {h['rule_id'] for h in result['matches']}=={'S301','S402','S404','S302'}
    for hit in result['matches']:
        assert text[hit['start']:hit['end']]==hit['match']
        assert hit['source_line']>0 and hit['source_section']
    assert result['mode']=='warn_only'
    assert '敏感词提示' in format_notice(result)
    assert all('不要' not in h['match'] for h in result['matches'])

def test_greeting_and_registration_do_not_whitelist_neighboring_claims():
    assert scan_bundle(bundle(),{'body':'Best regards. FDA registered facility.'})['match_count']==0
    result=scan_bundle(bundle(),{'body':'Best regards. Our best price. FDA registered; FDA approved.'})
    assert {h['rule_id'] for h in result['matches']}=={'S301','S402'}

def test_uploaded_python_is_not_executed(tmp_path):
    marker=tmp_path/'must-not-exist'
    malicious=source().replace('RULES =','__import__("pathlib").Path('+repr(str(marker))+').touch()\nRULES =')
    compile_markdown(malicious,'untrusted.md')
    assert not marker.exists()
    with pytest.raises((ValueError,SyntaxError)):
        compile_markdown(chr(96)*3+'python\nRULES = __import__("os").system("echo bad")\n'+chr(96)*3,'bad.md')

def test_owner_and_version_isolation():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert scan_fields(db,'b',{'body':'FDA approved'})['status']=='not_configured'
        id1=activate(db,'a',bundle(),'kb-a','doc-a')
        assert scan_fields(db,'a',{'body':'FDA approved'})['match_count']==1
        assert scan_fields(db,'b',{'body':'FDA approved'})['status']=='not_configured'
        assert activate(db,'a',bundle(),'kb-a','doc-a')==id1
        next_bundle=compile_markdown(source().replace('v4.0','v4.1'),'synthetic.md')
        activate(db,'a',next_bundle,'kb-a','doc-a')
        assert db.query(ForeignTradeLexicon).filter_by(owner_user_id='a',active=True).count()==1
        assert scan_fields(db,'a',{'body':'FDA approved'})['version']=='v4.1'
    engine.dispose()

def test_scan_caps_are_explicit_and_expensive_pattern_times_out():
    with pytest.raises(ValueError):scan_bundle(bundle(),{'body':'x'*100001})
    evil=bundle();evil['rules'][0]['pattern']='(a+)+$'
    with pytest.raises(TimeoutError):scan_bundle(evil,{'body':'a'*30000+'!'})
    result=scan_bundle(bundle(),{'body':'FDA approved. FDA approved.'},max_hits=1)
    assert result['match_count']==2 and result['truncated'] and len(result['matches'])==1
