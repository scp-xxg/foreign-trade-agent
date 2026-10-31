"""Real HTTP regression for owner-bound generated file downloads and previews."""
import inspect
import pytest
from fastapi import FastAPI,Request
from fastapi.testclient import TestClient
from starlette.responses import FileResponse
from api.routes import files
from core.auth.backend import UserContext
from core.db.engine import get_db

@pytest.fixture
def downloads(tmp_path,monkeypatch):
    path=tmp_path/'sample.glb';path.write_bytes(b'owned-artifact-bytes')
    monkeypatch.setattr(files,'_load_artifact_item',lambda *args:{'path':str(path),'name':'sample.glb','mime_type':'model/gltf-binary','size':20,'metadata':{'user_id':'owner','source':'blender-mcp'}})
    monkeypatch.setattr(files,'_record_audit',lambda **kw:None)
    monkeypatch.setattr(files,'_build_direct_download_response',lambda **kw:FileResponse(path))
    app=FastAPI();app.include_router(files.router)
    app.dependency_overrides[get_db]=lambda:None
    def identity(request:Request):
        name=request.headers.get('x-test-user')
        return UserContext(user_id=name,user_center_id=name,username=name) if name else None
    for endpoint in (files.download_file,):
        app.dependency_overrides[inspect.signature(endpoint).parameters['user'].default.dependency]=identity
    with TestClient(app) as client:yield client


def test_anonymous_download_is_denied(downloads):
    assert downloads.get('/files/sample').status_code==401
    assert downloads.get('/files/sample?inline=true').status_code==401
    assert downloads.get('/files/sample?mode=presigned').status_code==401


def test_owner_download_gets_original_bytes(downloads):
    response=downloads.get('/files/sample',headers={'x-test-user':'owner'})
    assert response.status_code==200 and response.content==b'owned-artifact-bytes'


def test_other_account_download_is_denied(downloads):
    response=downloads.get('/files/sample',headers={'x-test-user':'other'})
    assert response.status_code==403 and b'owned-artifact-bytes' not in response.content

@pytest.mark.parametrize('metadata',[{'owner_id':'owner'},{'user_id':'owner'},{'source':'local_project_reference'}])
def test_owned_previews_also_require_auth(metadata):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:files._authorize_access(item={'metadata':metadata},file_id='file',user=None,db=None,denied_action='file.preview.denied')
    assert error.value.status_code==401
