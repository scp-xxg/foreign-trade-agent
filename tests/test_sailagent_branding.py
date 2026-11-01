"""Persistent brand migration must not reset authored business copy or upstream credit."""
from copy import deepcopy
from types import SimpleNamespace
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.db.engine import Base
from core.db.models import ContentBlock
from core.files.content import branding

@pytest.fixture
def brand_db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:yield db
    engine.dispose()


def test_branding_survives_restart_without_overwriting_business_copy(brand_db,monkeypatch):
    monkeypatch.setattr(branding,'settings',SimpleNamespace(edition=SimpleNamespace(edition='ce')))
    original={'branding':{'product_name':'HugAgentOS','page_title':'HugAgentOS','logo_url':'/icon.png','hero_title':'Human edited business title','hero_subtitle':'Human subtitle','product_subtitle':'Human product subtitle','disclaimer':'Do not overwrite'},'homepage':{'logo_url':'/icon.png','suggested_questions':['Human question']},'navigation':{'admin_header':{'title':'HugAgentOS — 后台管理','subtitle':'Keep'},'admin_platform':{'product_name':'HugAgentOS','config_label':'Keep config label'},'sidebar_items':['trade_inquiries']},'auth':{'allow_register':False}}
    brand_db.add(ContentBlock(id='page_config',payload=deepcopy(original)));brand_db.commit()
    assert branding.enforce_ce_branding(brand_db)
    value=brand_db.get(ContentBlock,'page_config').payload
    assert value['branding']['product_name']=='SailAgent'
    assert value['branding']['logo_url']=='/brand/sailagent-mark.svg'
    assert value['branding']['favicon_url']=='/brand/sailagent-favicon.png'
    for key in ('hero_title','hero_subtitle','disclaimer','product_subtitle'):assert value['branding'][key]==original['branding'][key]
    assert value['homepage']['suggested_questions']==['Human question']
    assert value['navigation']['sidebar_items']==['trade_inquiries']
    assert value['navigation']['admin_platform']['config_label']=='Keep config label'
    assert value['auth']==original['auth']
    assert branding.enforce_ce_branding(brand_db) is False


def test_prompt_identity_changes_do_not_rebrand_the_attribution():
    from foreign_trade.brand_identity import identity_parts
    original=[{'part_id':'system/00_role','content':'你是 HugAgentOS 外贸助手，基于 HugAgentOS 开源框架。保留 HugAgentOS 署名。'},{'part_id':'system/40_format','content':'以"HugAgentOS"身份输出。'},{'part_id':'custom','content':'Human instruction. Powered by HugAgentOS'}]
    saved=deepcopy(original);result=identity_parts(original)
    assert original==saved
    assert '你是 SailAgent' in result[0]['content'] and '基于 HugAgentOS' in result[0]['content']
    assert '以"SailAgent"身份' in result[1]['content']
    assert result[2]==original[2]
    assert identity_parts(result)==result
