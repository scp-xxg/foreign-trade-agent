"""General capability, isolation mounts and version/receipt regressions."""
import json
from pathlib import Path
import sys
import pytest
HERE=Path(__file__).resolve().parents[1]/'extensions/blender'
sys.path.insert(0,str(HERE))
from general import namespace_command,require_revision,facts,scene_folder,MAX_CODE
from bridge import error_message


def test_generic_plugin_does_not_advertise_an_object_whitelist():
    manifest=json.loads((HERE/'plugin/plugin.json').read_text())
    assert manifest['version']=='0.2.0'
    names={t['name'] for t in manifest['extensions']['org.hugagent']['mcp']['blender']['tools']}
    assert names=={'blender_scene_info','blender_scene_execute','blender_scene_export'}
    skill=(HERE/'plugin/skills/product-3d-sampling/SKILL.md').read_text()
    assert '不限定物体类别' in skill and '旗袍' in skill and 'GLB' in skill


def test_namespace_exposes_only_own_workspace_and_readonly_runtime(monkeypatch,tmp_path):
    monkeypatch.setattr('general.shutil.which',lambda name:'/usr/bin/'+name)
    args=namespace_command(tmp_path)
    bind_positions=[i for i,x in enumerate(args) if x=='--bind']
    assert len(bind_positions)==1
    assert args[bind_positions[0]+1:bind_positions[0]+3]==[str(tmp_path),'/workspace']
    assert '--clearenv' in args and '--unshare-pid' in args and '--disable-autoexec' in args
    for i,value in enumerate(args):
        if value=='--ro-bind':assert args[i+1] not in ['/','/home','/mnt/c']
    assert 'GH_TOKEN' not in args and 'CURRENT_USER_ID' not in args


def test_missing_isolation_has_no_unsafe_fallback(monkeypatch,tmp_path):
    monkeypatch.setattr('general.shutil.which',lambda name:None)
    with pytest.raises(RuntimeError,match='no unsafe fallback'):namespace_command(tmp_path)

@pytest.mark.parametrize('value',[None,True,1,3])
def test_revision_guard_rejects_missing_boolean_and_stale(value):
    with pytest.raises(ValueError):require_revision({'revision':2},value)


def test_new_scene_zero_and_resumed_scene_revision():
    require_revision(None,0);require_revision({'revision':2},2)


def test_scene_receipt_parses_actual_upstream_prefix():
    result=facts('Code executed successfully: HUG_SCENE_FACTS:'+json.dumps({'mesh_count':7}))
    assert result=={'mesh_count':7}
    with pytest.raises(RuntimeError):facts('Code executed successfully: no scene receipt')


def test_nested_sdk_errors_keep_repairable_cause():
    wrapped=ExceptionGroup('task group',[ExceptionGroup('inner',[ValueError('Safe mode rejected script: import os')])])
    assert error_message(wrapped)=='Safe mode rejected script: import os'


def test_account_chat_paths_are_independent_and_not_model_paths(tmp_path):
    assert scene_folder(tmp_path,'a','chat')!=scene_folder(tmp_path,'b','chat')
    assert scene_folder(tmp_path,'a','chat')!=scene_folder(tmp_path,'a','other')
    assert scene_folder(tmp_path,'../../a','../../chat').is_relative_to(tmp_path/'blender/sessions')
