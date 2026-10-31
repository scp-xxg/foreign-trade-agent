"""Business boundary and snapshot tests; real engine acceptance is documented separately."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]/'extensions/blender'
sys.path.insert(0,str(HERE))
from model import parameters,build_script,DEFAULT
from bridge import checked_revision,scope_folder,write_state,read_state,validate_export,parse_result

@pytest.mark.parametrize('value',[{'width_cm':True},{'height_cm':float('nan')},{'depth_cm':float('inf')},{'compartments':2.5},{'compartments':True},{'compartments':9},{'color':'red'},{'wall_mm':0},{'width_cm':61},{'path':'/etc/passwd'},{'width_cm':3,'compartments':8,'wall_mm':8}])
def test_rejects_invalid_or_unsupported_inputs(value):
    with pytest.raises(ValueError):parameters(value)

def test_two_round_changes_preserve_other_parameters():
    first=parameters(dict(DEFAULT));second=parameters({'height_cm':10,'color':'green'},first)
    assert first==DEFAULT
    assert second=={**DEFAULT,'height_cm':10,'color':'green'}

def test_stale_revision_never_updates():
    for revision in (None,True,0,1):
        with pytest.raises(ValueError):checked_revision({'revision':2},revision)
    checked_revision({'revision':2},2)

def test_persisted_state_survives_new_process_and_separates_actors(tmp_path):
    first=scope_folder(tmp_path,'a','chat');second=scope_folder(tmp_path,'b','chat')
    assert first!=second
    assert scope_folder(tmp_path,'../a','../../b').is_relative_to(tmp_path/'blender/sessions')
    state={'revision':2,'parameters':parameters({'height_cm':10}),'history':[{'revision':1}]}
    write_state(first,state)
    assert read_state(first)==state and read_state(second) is None

def test_empty_or_external_resource_glb_rejected(tmp_path):
    path=tmp_path/'model.glb';path.write_bytes(b'glTF')
    with pytest.raises(ValueError):validate_export(path)
    content=json.dumps({'meshes':[{}],'buffers':[{'uri':'http://example.com/a.bin'}]}).encode()
    path.write_bytes(struct.pack('<4sII',b'glTF',2,len(content)+20)+struct.pack('<II',len(content),0x4E4F534A)+content)
    with pytest.raises(ValueError,match='外部资源'):validate_export(path)

def test_symlink_cannot_be_published(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'x')
    path=tmp_path/'model.glb';path.symlink_to(source)
    with pytest.raises(ValueError):validate_export(path)

def test_generated_code_exports_selected_product_and_actual_dimensions(tmp_path):
    text=build_script(DEFAULT,2,tmp_path)
    compile(text,'blender-script','exec')
    assert "use_selection=True" in text and "export_apply=True" in text
    assert "HUG_MODEL_FACTS:" in text and "HUG_EXPORT_COMPLETE" in text
    assert "parts.append(obj)" in text
    assert "scene.cycles.device='CPU'" in text

def test_missing_execution_receipt_is_failure():
    from types import SimpleNamespace
    receipt=SimpleNamespace(is_error=False,content=[SimpleNamespace(text='Error executing code: offline')])
    with pytest.raises(RuntimeError):parse_result(receipt)

def test_chat_context_required(monkeypatch,tmp_path):
    from bridge import check_actor
    monkeypatch.delenv('CURRENT_USER_ID',raising=False)
    monkeypatch.delenv('CURRENT_CHAT_ID',raising=False)
    with pytest.raises(PermissionError):check_actor(tmp_path)
