"""Authenticated Hug tools -> isolated upstream Blender MCP, SDKs never mixed."""
from __future__ import annotations
import argparse
import asyncio
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
from uuid import uuid4

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from model import parameters,build_script

LIMIT=32*1024*1024
SLUG='foreign-trade-blender'


def check_actor(home):
    # Set by Hug's per-conversation MCP transport, never supplied by the model.
    user=os.environ.get('CURRENT_USER_ID','')
    chat=os.environ.get('CURRENT_CHAT_ID','')
    if not user or not chat:raise PermissionError('请从已登录的 HugAgent 对话调用此插件。')
    from core.db.engine import SessionLocal
    from core.db.models import ChatSession
    from features.desktop.local.plugins import service
    with SessionLocal() as db:
        row=db.query(ChatSession).filter(ChatSession.chat_id==chat,ChatSession.user_id==user,ChatSession.deleted_at.is_(None)).one_or_none()
        if row is None:raise PermissionError('当前会话不存在或不属于当前账号。')
    from core.capabilities.skills.installation import compute_install_id
    from features.desktop.capabilities import registry
    identifier=registry.install_id('plugin','local',compute_install_id(SLUG,user))
    if not service.get(user,identifier).get('enabled'):
        raise PermissionError('请先安装并启用外贸 3D 打样插件。')
    return user,chat


def scope_folder(home,user,chat):
    # Identifiers are not interpreted as filesystem names.
    return home/'blender'/'sessions'/hashlib.sha256((user+'\0'+chat).encode()).hexdigest()


def read_state(folder):
    path=folder/'model.json'
    if not path.exists():return None
    return json.loads(path.read_text(encoding='utf-8'))


def write_state(folder,state):
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=folder/('state-'+uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
    tmp.replace(folder/'model.json')


def checked_revision(state,expected):
    if state is None:raise ValueError('当前对话还没有模型，请先 create。')
    if type(expected) is not int or expected!=state['revision']:
        raise ValueError('模型版本已变化或未提供。请先 get，使用最新 expected_revision。')


def validate_export(path):
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=LIMIT:
        raise ValueError('导出缺失、文件过大或不是普通文件。')
    data=path.read_bytes()
    if path.suffix=='.glb':
        if len(data)<20 or struct.unpack('<4sII',data[:12])!=(b'glTF',2,len(data)):
            raise ValueError('GLB 头部或长度无效。')
        length,kind=struct.unpack('<II',data[12:20])
        if kind!=0x4E4F534A or length>len(data)-20:raise ValueError('GLB JSON chunk 无效。')
        doc=json.loads(data[20:20+length])
        if not doc.get('meshes'):raise ValueError('GLB 没有网格。')
        if any('uri' in item for item in doc.get('buffers',[])+doc.get('images',[])):
            raise ValueError('GLB 含外部资源引用。')
    elif path.suffix=='.png':
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            if image.format!='PNG' or image.size!=(1024,768):raise ValueError('展示图格式或尺寸不正确。')
            image.verify()
    elif path.suffix=='.blend':
        # Blender may compress .blend, so rely on a nonempty file and GLB readback.
        if len(data)<64:raise ValueError('Blend 文件不完整。')
    else:raise ValueError('不支持此导出类型。')
    return {'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def parse_result(result,export=False):
    text='\n'.join(getattr(x,'text','') for x in result.content)
    if result.is_error or not text.startswith('Code executed successfully:'):
        raise RuntimeError('Blender 执行失败：'+text[:1800])
    facts=None
    for line in text.splitlines():
        if 'HUG_MODEL_FACTS:' in line:facts=json.loads(line.split('HUG_MODEL_FACTS:',1)[1])
    if facts is None or (export and 'HUG_EXPORT_COMPLETE' not in text):
        raise RuntimeError('Blender 未返回完整的建模/导出回执。')
    return facts


def decorate_preview(path,p,revision):
    from PIL import Image,ImageDraw
    with Image.open(path) as source:image=source.convert('RGB')
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,1024,48),fill='white')
    draw.text((20,17),f"CONCEPT SAMPLE | v{revision} | {p['width_cm']:g} x {p['depth_cm']:g} x {p['height_cm']:g} cm | {p['color']} | {p['compartments']} compartments",fill='#17324d')
    draw.rectangle((0,731,1024,768),fill='white')
    draw.text((20,744),'Not production CAD or a material/certification claim. Powered by HugAgentOS + Blender.',fill='#455466')
    image.save(path,'PNG')


async def perform(remote,home,name,args):
    user,chat=check_actor(home)
    folder=scope_folder(home,user,chat)
    root=home/'blender';root.mkdir(exist_ok=True,mode=0o700)
    with (root/'engine.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Blender 正在处理另一请求，请稍后重试；本次未写入模型。')
        state=read_state(folder)
        if name=='blender_product_model':
            if set(args)-{'action','parameters','expected_revision'}:raise ValueError('未知参数。')
            action=args.get('action')
            if action=='get':
                if state is None:return {'ok':True,'model':None,'supported':'有底、开顶的直立分格桌面收纳盒；尺寸为外尺寸。'}
                return {'ok':True,'model':state,'notice':'保存的版本；export 会重新构建并核对 Blender 实际尺寸。'}
            if action=='create':
                if state is not None:raise ValueError('本会话已存在模型，请 get 后 update；新款请新建会话。')
                p=parameters(args.get('parameters'));revision=1;history=[]
            elif action=='update':
                checked_revision(state,args.get('expected_revision'))
                p=parameters(args.get('parameters'),state['parameters']);revision=state['revision']+1
                history=state.get('history',[])+[{'revision':state['revision'],'parameters':state['parameters'],'facts':state['facts']}]
            else:raise ValueError('action 必须为 create/update/get。')
            result=await remote.call_tool('execute_blender_code',{'code':build_script(p,revision),'user_prompt':'Create/update the explicitly requested parametric desk organizer concept sample.'})
            facts=parse_result(result)
            if facts['actual_dimensions_cm']!=[p[x] for x in ('width_cm','depth_cm','height_cm')]:
                raise RuntimeError('Blender 实际尺寸不匹配，未保存新版本。')
            state={'revision':revision,'parameters':p,'facts':facts,'history':history,'demo':True,'kind':'desk-organizer'}
            write_state(folder,state)
            return {'ok':True,'model':state,'notice':'概念打样，非生产 CAD；颜色不表示已验证材料。未关联 SKU、未改报价。'}
        if name=='blender_export_product':
            if set(args)-{'expected_revision'}:raise ValueError('未知参数。')
            checked_revision(state,args.get('expected_revision'))
            target=folder/'exports'/('v'+str(state['revision'])+'-'+uuid4().hex)
            target.mkdir(parents=True,mode=0o700)
            result=await remote.call_tool('execute_blender_code',{'code':build_script(state['parameters'],state['revision'],target),'user_prompt':'Export the requested current product concept revision as GLB, PNG and Blender source.'})
            facts=parse_result(result,export=True)
            expected=[state['parameters'][x] for x in ('width_cm','depth_cm','height_cm')]
            if facts['actual_dimensions_cm']!=expected:raise RuntimeError('导出模型尺寸不匹配。')
            decorate_preview(target/'preview.png',state['parameters'],state['revision'])
            # Validate all outputs before registering any download.
            checked={f:validate_export(target/f) for f in ('model.glb','preview.png','scene.blend')}
            from core.files.artifacts.generated import store_generated_file_path
            refs=[]
            for filename,mime in [('model.glb','model/gltf-binary'),('preview.png','image/png'),('scene.blend','application/x-blender')]:
                ref=store_generated_file_path(target/filename,name='desk-organizer-v'+str(state['revision'])+'-'+filename,mime_type=mime,user_id=user,source='blender-mcp',extra_metadata={'chat_id':chat,'revision':state['revision'],'demo':True,'sha256':checked[filename]['sha256']})
                if ref is None:raise RuntimeError('文件已生成，但下载登记失败，请重试导出。')
                refs.append({**ref,'sha256':checked[filename]['sha256']})
            return {'ok':True,'revision':state['revision'],'parameters':state['parameters'],'facts':facts,'artifacts':refs,'notice':'GLB 不含灯光、相机和地面；PNG 为同版本实渲染概念图。非生产/认证文件。'}
        raise ValueError('未知工具。')


async def run(home):
    from mcp import Client,StdioServerParameters,types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    env={'DISABLE_TELEMETRY':'true','BLENDER_MCP_SAFE_MODE':'1','BLENDER_HOST':'127.0.0.1','BLENDER_PORT':'9876'}
    upstream=StdioServerParameters(command=str(ROOT/'.runtime/blender-mcp-venv/bin/python'),args=['-m','blender_mcp.server'],env=env)
    async with Client(upstream,read_timeout_seconds=240) as remote:
        discovered=await remote.list_tools()
        if 'execute_blender_code' not in {x.name for x in discovered.tools}:raise RuntimeError('Pinned Blender MCP tool unavailable')
        pfields={'width_cm':{'type':'number'},'depth_cm':{'type':'number'},'height_cm':{'type':'number'},'wall_mm':{'type':'number'},'compartments':{'type':'integer'},'color':{'type':'string','enum':['blue','green','white','black','orange']}}
        tool_list=[types.Tool(name='blender_product_model',description='通过真实 Blender MCP 创建/修改当前对话的桌面分格收纳盒概念模型。action=create/update/get；parameters 为明确修改的外尺寸厘米、壁厚毫米、分格数和颜色。省略字段沿用当前值或工具默认值；create 前说明默认值，update 必须提供最新 expected_revision。不能用于任意物体/服装仿真、工艺或认证结论。',input_schema={'type':'object','properties':{'action':{'type':'string','enum':['create','update','get']},'parameters':{'type':'object','properties':pfields,'additionalProperties':False},'expected_revision':{'type':'integer'}},'required':['action'],'additionalProperties':False}),types.Tool(name='blender_export_product',description='实际重新构建并导出当前版本的 GLB、1024x768 PNG 实渲染展示图和 .blend 源文件，校验后返回当前账号可下载的 /files 链接及 SHA256。expected_revision 必须等于最新模型版本。',input_schema={'type':'object','properties':{'expected_revision':{'type':'integer'}},'required':['expected_revision'],'additionalProperties':False})]
        async def listing(ctx,params):return types.ListToolsResult(tools=tool_list)
        async def calling(ctx,params):
            try:
                result=await perform(remote,home,params.name,params.arguments or {})
                return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(result,ensure_ascii=False))])
            except Exception as exc:
                return types.CallToolResult(is_error=True,content=[types.TextContent(type='text',text=json.dumps({'ok':False,'error':str(exc)[:2000],'type':type(exc).__name__,'action':'检查参数/版本；若连接失败，运行 extensions/blender/manage.py start。'},ensure_ascii=False))])
        server=Server('foreign-trade-blender',version='0.1.0',instructions='Use Chinese input to create and revise a parametric concept. Only actual tool artifacts are downloadable; never invent URLs or claim CAD/garment simulation.',on_list_tools=listing,on_call_tool=calling)
        async with stdio_server() as (reader,writer):await server.run(reader,writer,server.create_initialization_options())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-home',required=True,type=Path)
    args=parser.parse_args();home=args.app_home.expanduser().resolve()
    if not (home/'data.db').is_file():parser.error('Existing public HugAgent home required')
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home,3002))
    from features import register_run_capabilities
    register_run_capabilities()
    asyncio.run(run(home))

if __name__=='__main__':main()
