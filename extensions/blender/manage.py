"""Manage only the public checkout's isolated Blender/Xvfb/MCP dependencies."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RUNTIME=ROOT/'.runtime'
VERSION='5.2.3'
ARCHIVE='blender-'+VERSION+'-linux-x64.tar.xz'
DIGEST='78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec'
ADDON_DIGEST='6c2917c157c26d7549adcbd480243db2154a9b06bc580664f090530c8ef3801f'
BINARY=RUNTIME/('blender-'+VERSION+'-linux-x64')/'blender'
MCP_PYTHON=RUNTIME/'blender-mcp-venv/bin/python'
PID=RUNTIME/'blender-process.json'


def setup():
    if sys.platform!='linux':raise RuntimeError('请在 Linux/WSL 中运行。')
    if shutil.which('xvfb-run') is None:raise RuntimeError('请先安装 xvfb xauth 及文档列出的图形库。')
    RUNTIME.mkdir(exist_ok=True)
    path=RUNTIME/ARCHIVE
    if not path.exists():
        temp=path.with_suffix('.download')
        with urllib.request.urlopen('https://mirror.blender.org/release/Blender5.2/'+ARCHIVE,timeout=60) as remote,temp.open('wb') as dst:shutil.copyfileobj(remote,dst)
        temp.replace(path)
    if hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=DIGEST:raise RuntimeError('官方压缩包 SHA256 不匹配；停止安装。')
    if not BINARY.exists():
        with tarfile.open(path) as source:source.extractall(RUNTIME,filter='data')
    if not MCP_PYTHON.exists():subprocess.run([sys.executable,'-m','venv',str(MCP_PYTHON.parents[1])],check=True)
    subprocess.run([str(MCP_PYTHON),'-m','pip','--isolated','install','--index-url','https://pypi.org/simple','-r',str(HERE/'requirements-mcp.txt')],check=True)
    package=json.loads(subprocess.check_output([str(MCP_PYTHON),'-c',"import blender_mcp,pathlib,json;print(json.dumps(str(pathlib.Path(blender_mcp.__file__).parent/'bundled/addon.py')))"],text=True))
    source=Path(package)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=ADDON_DIGEST:raise RuntimeError('上游插件内容与固定版本不符。')
    destination=RUNTIME/'blender-mcp-upstream/addon.py';destination.parent.mkdir(exist_ok=True)
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest()!=ADDON_DIGEST:raise RuntimeError('已有 addon.py 与版本不符，不覆盖。')
    if not destination.exists():shutil.copyfile(source,destination)
    print(subprocess.check_output([str(BINARY),'--version'],text=True).splitlines()[0])
    return {'ok':True,'blender':VERSION,'mcp':'2.2.6','sdk':'1.30.0','addon_sha256':ADDON_DIGEST}


def health():
    try:
        with socket.create_connection(('127.0.0.1',9876),timeout=2) as connection:
            connection.settimeout(5)
            connection.sendall(json.dumps({'type':'get_scene_info','params':{}}).encode())
            data=b''
            while len(data)<1024*1024:
                part=connection.recv(65536)
                if not part:break
                data+=part
                try:result=json.loads(data);break
                except ValueError:continue
            else:return None
            if result.get('status')=='success' and isinstance(result.get('result'),dict):return result['result']
    except (OSError,ValueError,UnboundLocalError):pass
    return None


def owned():
    if not PID.exists():return None
    record=json.loads(PID.read_text())
    proc=Path('/proc')/str(record['pid'])
    if not proc.exists():return None
    args=(proc/'cmdline').read_bytes().split(b'\0')
    if str(BINARY).encode() not in args or str(HERE/'bootstrap.py').encode() not in args or (proc/'cwd').resolve()!=ROOT:
        raise RuntimeError('PID 不属于此公开项目，不接管。')
    return record


def start():
    if owned() and health():return {'ok':True,'status':'already_running','pid':owned()['pid']}
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',9876))==0:raise RuntimeError('9876 已被其他/异常进程占用，不接管。')
    if not BINARY.exists() or not MCP_PYTHON.exists():raise RuntimeError('先运行 setup。')
    if hashlib.sha256((RUNTIME/'blender-mcp-upstream/addon.py').read_bytes()).hexdigest()!=ADDON_DIGEST:raise RuntimeError('插件校验失败。')
    env=os.environ.copy();env.update({'DISABLE_TELEMETRY':'true','LIBGL_ALWAYS_SOFTWARE':'1','PYTHONUNBUFFERED':'1','WAYLAND_DISPLAY':'','XDG_SESSION_TYPE':'x11'})
    for name in ('CONFIG','SCRIPTS','DATAFILES'):
        directory=RUNTIME/'blender-user'/name.lower();directory.mkdir(parents=True,exist_ok=True)
        env['BLENDER_USER_'+name]=str(directory)
    # Xvfb-run's shell execs Blender as a child: record the real Blender PID, not a guessed shell PID.
    with (RUNTIME/'blender-linux.log').open('ab') as log:
        child=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1280x1024x24',str(BINARY),'--factory-startup','-noaudio','--python',str(HERE/'bootstrap.py')],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    for _ in range(100):
        if child.poll() is not None:raise RuntimeError('Blender 启动失败，请检查 .runtime/blender-linux.log。')
        if health():
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:args=(proc/'cmdline').read_bytes().split(b'\0')
                except OSError:continue
                if args and args[0]==str(BINARY).encode() and str(HERE/'bootstrap.py').encode() in args and (proc/'cwd').resolve()==ROOT:
                    record={'pid':int(proc.name),'supervisor_pid':child.pid};PID.write_text(json.dumps(record));return {'ok':True,'status':'started',**record,'host':'127.0.0.1','port':9876}
        time.sleep(0.3)
    raise RuntimeError('Blender 未就绪，检查日志。')


def stop():
    record=owned()
    if record is None:return {'ok':True,'status':'not_running'}
    os.kill(record['pid'],signal.SIGTERM)
    return {'ok':True,'status':'stopping','pid':record['pid']}


def install(home,username):
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home,3002))
    from core.db.engine import SessionLocal
    from core.db.models import UserShadow
    from features import register_package_sources,register_resource_owners,register_run_capabilities
    register_package_sources();register_resource_owners();register_run_capabilities()
    from features.desktop.local.plugins import service
    with SessionLocal() as db:
        row=db.query(UserShadow).filter(UserShadow.username==username).one_or_none()
        if row is None:raise ValueError('账号不存在；请先在 HugAgent 创建自己的账号。')
        user=row.user_id
    package=RUNTIME/'blender-plugin';package.mkdir(exist_ok=True)
    shutil.copytree(HERE/'plugin',package,dirs_exist_ok=True)
    config={'mcpServers':{'blender':{'type':'stdio','command':str(ROOT/'.venv/bin/python'),'args':[str(HERE/'bridge.py'),'--app-home',str(home)]}}}
    (package/'mcp.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    from core.capabilities.skills.installation import compute_install_id
    from features.desktop.capabilities import registry
    identifier=registry.install_id('plugin','local',compute_install_id('foreign-trade-blender',user))
    previous=next((p for p in service.list_plugins(user) if p['install_id']==identifier),None)
    if previous:result=service.update(user,previous['install_id'],str(package),previous['revision'])
    else:result=service.install(user,str(package))
    service.set_presentation(user,result['install_id'],{'display_name':'外贸 3D 打样（Blender）','category':'设计创意'})
    result=service.get(user,result['install_id'])
    return {'ok':True,'install_id':result['install_id'],'enabled':result['enabled'],'version':result['version'],'components':result['components']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','start','stop','status','install'])
    parser.add_argument('--app-home',type=Path)
    parser.add_argument('--username')
    args=parser.parse_args()
    if args.action=='install':
        if not args.app_home or not args.username:parser.error('install 需要 --app-home 和 --username。')
        home=args.app_home.expanduser().resolve()
        if not (home/'data.db').is_file():parser.error('已有 HugAgent 数据目录不存在。')
        result=install(home,args.username)
    else:result={'setup':setup,'start':start,'stop':stop,'status':lambda:{'managed':bool(owned()),'ready':health() is not None}}[args.action]()
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
