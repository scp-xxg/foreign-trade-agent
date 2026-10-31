"""HugAgent stdio tools bound to the authenticated user and conversation."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import engine


def actor():
    user=os.environ.get('CURRENT_USER_ID','');chat=os.environ.get('CURRENT_CHAT_ID','')
    if not user or not chat:raise PermissionError('请从已登录的HugAgent对话使用此工具。')
    from core.db.engine import SessionLocal
    from core.db.models import ChatSession
    with SessionLocal() as db:
        if not db.query(ChatSession).filter(ChatSession.chat_id==chat,ChatSession.user_id==user,ChatSession.deleted_at.is_(None)).one_or_none():raise PermissionError('会话不存在或不属于当前账号。')
    from core.capabilities.skills.installation import compute_install_id
    from features.desktop.capabilities import registry
    from features.desktop.local.plugins import service
    identifier=registry.install_id('plugin','local',compute_install_id('foreign-trade-tripo',user))
    if not service.get(user,identifier).get('enabled'):raise PermissionError('请先启用高质量3D生成插件。')
    return user,chat


def error_text(exc):
    if isinstance(exc,BaseExceptionGroup):return '; '.join(error_text(x) for x in exc.exceptions)[:1500]
    if isinstance(exc,asyncio.TimeoutError):return '服务超时；保留当前计划，只查询同一任务，不重新生成。'
    return str(exc)[:1500]


async def run(home):
    from mcp import types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    def tool(name,description,fields,required):return types.Tool(name=name,description=description,input_schema={'type':'object','properties':fields,'required':required,'additionalProperties':False})
    tools=[tool('tripo_account_status','只读检查当前Hug账号绑定的Tripo服务是否登录、余额及本次免费预算。不能用聊天模型额度代替3D额度。',{},[]),tool('tripo_prepare_asset','准备高质量云端3D生成计划，只做官方CLI预检，不上传/扣积分。提供title及reference_file_id（当前账号的PNG/JPEG/WebP图）或prompt。使用Tripo H3.1、PBR详细贴图、12万面、单候选。返回plan_id与官方估算积分；参考图不是3D结果。',{'title':{'type':'string'},'prompt':{'type':'string'},'reference_file_id':{'type':'string'}},['title']),tool('tripo_submit_asset','用户要求实际生成且当前账号本次积分预算已核验后（免费试用或明确授权的付费预算），提交已准备计划。只接受plan_id；重复调用复用原任务，不新建、不自动充值。成功提交不等于完成，必须再查tripo_asset_status。',{'plan_id':{'type':'string'}},['plan_id']),tool('tripo_asset_status','查询同一计划的真实Tripo任务，wait=true可等待最多90秒；完成后自动下载并通过隔离Blender真实渲染，发布GLB、PNG和Blend文件。生成/交付失败不假称成功、不重复创建。',{'plan_id':{'type':'string'},'wait':{'type':'boolean'}},['plan_id'])]
    async def listing(ctx,params):return types.ListToolsResult(tools=tools)
    async def calling(ctx,params):
        try:
            user,chat=actor();args=params.arguments or {}
            schema=next((t for t in tools if t.name==params.name),None)
            if schema is None or set(args)-set(schema.input_schema['properties']):raise ValueError('未知工具或参数。')
            if params.name=='tripo_account_status':result=await engine.account_status(home,user)
            elif params.name=='tripo_prepare_asset':result=await engine.prepare(home,user,chat,**args)
            elif params.name=='tripo_submit_asset':result=await engine.submit(home,user,chat,args['plan_id'])
            else:result=await engine.status(home,user,chat,args['plan_id'],bool(args.get('wait',False)))
            return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(result,ensure_ascii=False))],is_error=not result.get('ok',False))
        except Exception as exc:return types.CallToolResult(is_error=True,content=[types.TextContent(type='text',text=json.dumps({'ok':False,'error':error_text(exc),'type':type(exc).__name__},ensure_ascii=False))])
    server=Server('foreign-trade-tripo',version='0.1.0',instructions='Real Tripo generation with a verified free-credit budget. Prepare, submit once, query the same task, deliver actual owned files. No template fallback or invented success. Never request or expose an API key in chat.',on_list_tools=listing,on_call_tool=calling)
    async with stdio_server() as (reader,writer):await server.run(reader,writer,server.create_initialization_options())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app-home',required=True,type=Path);args=parser.parse_args();home=args.app_home.expanduser().resolve()
    if not (home/'data.db').is_file():parser.error('Existing public app home required.')
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home,3002))
    from features import register_run_capabilities
    register_run_capabilities()
    asyncio.run(run(home))
if __name__=='__main__':main()
