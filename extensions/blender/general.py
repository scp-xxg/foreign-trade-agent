"""Object-independent scene tools, with one isolated filesystem per operation.
Model-authored bpy runs only in bubblewrap, never with access to the user's home.
"""
from __future__ import annotations
import asyncio
import base64
import io
from contextlib import asynccontextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from uuid import uuid4

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PORT=9877
MAX_CODE=48000

INSPECT="""import bpy,json
from mathutils import Vector
objects=[]
for obj in bpy.context.scene.objects:
    if obj.type in {'MESH','CURVE','SURFACE','FONT','META'}:
        objects.append({'name':obj.name,'type':obj.type,'display_only':bool(obj.get('hug_display_only',False)),'dimensions_m':[round(v,5) for v in obj.dimensions],'vertices':len(obj.data.vertices) if obj.type=='MESH' else 0,'materials':[m.name for m in obj.data.materials if m]})
if not objects:
    raise ValueError('Scene has no geometry. Create actual mesh, curve or text geometry before saving/exporting.')
if len(objects)>500 or sum(o['vertices'] for o in objects)>1000000:
    raise ValueError('Concept scene exceeds 500 meshes / 1M vertices; simplify before export.')
print('HUG_SCENE_FACTS:'+json.dumps({'objects':objects,'mesh_count':sum(1 for o in objects if o['type']=='MESH'),'geometry_count':len(objects),'camera':bpy.context.scene.camera.name if bpy.context.scene.camera else None,'images':[{'name':im.name,'size':list(im.size),'packed':bool(im.packed_file)} for im in bpy.data.images if im.type!='RENDER_RESULT']}))
"""

EXPORT="""import bpy,math,json
from mathutils import Vector
scene=bpy.context.scene
geometry=[o for o in scene.objects if o.type in {'MESH','CURVE','SURFACE','FONT','META'} and not o.hide_render and not o.get('hug_display_only',False)]
meshes=[o for o in geometry if o.type=='MESH']
temporary=[]
# Export evaluated copies of curves/text while retaining editable source objects.
depsgraph=bpy.context.evaluated_depsgraph_get()
for obj in geometry:
    if obj.type!='MESH':
        data=bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
        copy=bpy.data.objects.new(obj.name+'_GLBMesh',data)
        copy.matrix_world=obj.matrix_world.copy()
        scene.collection.objects.link(copy)
        temporary.append(copy)
        meshes.append(copy)
if not meshes:
    raise ValueError('No visible product meshes to export.')
bpy.context.view_layer.update()
points=[o.matrix_world@Vector(v) for o in meshes for v in o.bound_box]
low=Vector(tuple(min(v[i] for v in points) for i in range(3)))
high=Vector(tuple(max(v[i] for v in points) for i in range(3)))
center=(low+high)/2
span=max(high-low)
if span<0.00001:
    raise ValueError('Model bounds are empty.')
if scene.camera is None:
    bpy.ops.object.camera_add(location=center+Vector((span*1.25,-span*2.8,span*0.9)))
    camera=bpy.context.object
    camera.name='Hug_Display_Camera'
    camera['hug_display_only']=True
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO'
    camera.data.ortho_scale=span*1.55
    scene.camera=camera
if not any(o.type=='LIGHT' for o in scene.objects):
    for name,delta,energy in [('Key',(1,-2,3),150),('Fill',(-2,-1,1),70)]:
        bpy.ops.object.light_add(type='AREA',location=center+Vector(delta)*span)
        light=bpy.context.object
        light.name='Hug_Display_'+name
        light['hug_display_only']=True
        light.data.energy=energy*span*span
        light.data.size=span*2
        light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
if scene.world is None:
    scene.world=bpy.data.worlds.new('Hug_Display_World')
scene.world.color=(0.1,0.1,0.1)
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=24
scene.render.threads_mode='FIXED'
scene.render.threads=4
scene.render.resolution_x=1024
scene.render.resolution_y=768
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.film_transparent=False
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
for image in bpy.data.images:
    if image.type!='RENDER_RESULT' and image.size[0]>0:
        image.pack()
bpy.ops.file.pack_all()
bpy.ops.export_scene.gltf(filepath='/workspace/model.glb',export_format='GLB',use_selection=True,export_apply=True)
for copy in temporary:
    bpy.data.objects.remove(copy,do_unlink=True)
scene.render.filepath='/workspace/preview.png'
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath='/workspace/scene.blend')
print('HUG_EXPORT_COMPLETE')
"""


def namespace_command(workspace):
    binary=ROOT/'.runtime/blender-5.2.3-linux-x64'
    addon=ROOT/'.runtime/blender-mcp-upstream/addon.py'
    if not shutil.which('bwrap'):raise RuntimeError('Install bubblewrap before using general scene tools; no unsafe fallback.')
    command=['bwrap','--die-with-parent','--unshare-user','--unshare-pid','--unshare-uts','--unshare-ipc',
        '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64',
        '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/etc','--ro-bind','/etc/ld.so.cache','/etc/ld.so.cache',
        '--ro-bind',str(binary),'/opt/blender','--ro-bind',str(addon),'/opt/addon.py',
        '--ro-bind',str(HERE/'bootstrap.py'),'/opt/bootstrap.py','--bind',str(workspace),'/workspace','--chdir','/workspace',
        '--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/workspace',
        '--setenv','LANG','C.UTF-8','--setenv','LIBGL_ALWAYS_SOFTWARE','1','--setenv','PYTHONUNBUFFERED','1',
        '--setenv','DISABLE_TELEMETRY','true','--setenv','WAYLAND_DISPLAY','',
        '--setenv','HUG_BLENDER_ADDON','/opt/addon.py','--setenv','HUG_BLENDER_PROJECT_FILE','/workspace/scene.blend',
        '--setenv','HUG_BLENDER_PORT',str(PORT),'--','xvfb-run','-a','-s','-screen 0 1280x1024x24',
        '/opt/blender/blender','--factory-startup','--disable-autoexec','-noaudio','--python','/opt/bootstrap.py']
    return command


@asynccontextmanager
async def worker(workspace):
    # The MCP socket is loopback only; the isolated Blender sees no home/project/database.
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',PORT))==0:raise RuntimeError('General Blender port is occupied; will not attach to an unknown process.')
    command=namespace_command(workspace)
    with (workspace/'engine.log').open('ab') as log:
        process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        for _ in range(160):
            if process.poll() is not None:raise RuntimeError('Isolated Blender exited; inspect this operation engine.log. No version was committed.')
            with socket.socket() as connection:
                if connection.connect_ex(('127.0.0.1',PORT))==0:break
            await asyncio.sleep(.15)
        else:raise RuntimeError('Isolated Blender startup timed out.')
        from mcp import Client,StdioServerParameters
        params=StdioServerParameters(command=str(ROOT/'.runtime/blender-mcp-venv/bin/python'),args=['-m','blender_mcp.server'],env={'DISABLE_TELEMETRY':'true','BLENDER_MCP_SAFE_MODE':'1','BLENDER_HOST':'127.0.0.1','BLENDER_PORT':str(PORT)})
        async with Client(params,read_timeout_seconds=210) as client:yield client
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:await asyncio.to_thread(process.wait,3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                await asyncio.to_thread(process.wait)
        # The namespace supervisor may exit just before its socket-owning child.
        for _ in range(40):
            with socket.socket() as connection:
                if connection.connect_ex(('127.0.0.1',PORT))!=0:break
            await asyncio.sleep(.1)
        else:raise RuntimeError('Isolated Blender socket did not close; no version committed.')


async def execute(client,code,prompt):
    result=await client.call_tool('execute_blender_code',{'code':code,'user_prompt':prompt})
    text='\n'.join(getattr(item,'text','') for item in result.content)
    if result.is_error or not text.startswith('Code executed successfully:'):
        raise RuntimeError(text[:3000])
    return text


def facts(text):
    for line in text.splitlines():
        if 'HUG_SCENE_FACTS:' in line:return json.loads(line.split('HUG_SCENE_FACTS:',1)[1])
    raise RuntimeError('Missing actual Blender scene receipt.')


def require_revision(state,value):
    current=state['revision'] if state else 0
    if type(value) is not int or value!=current:raise ValueError('Version conflict: call blender_scene_info and use its current expected_revision.')


def save_json(path,value):
    tmp=path.with_name('.'+uuid4().hex+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)


def scene_folder(home,user,chat):
    key=hashlib.sha256((user+'\0'+chat).encode()).hexdigest()
    return home/'blender/sessions'/key/'general'


async def perform(home,user,chat,name,args):
    root=home/'blender';root.mkdir(exist_ok=True,mode=0o700)
    folder=scene_folder(home,user,chat);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    state_path=folder/'scene.json'
    with (root/'general-engine.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Blender is busy with another conversation. No scene was modified; retry shortly.')
        state=json.loads(state_path.read_text()) if state_path.exists() else None
        if name=='blender_scene_info':
            if set(args):raise ValueError('scene_info takes no model arguments.')
            return {'ok':True,'revision':state['revision'] if state else 0,'scene':state,'capability':'General bpy geometry, materials, UV/image textures, scene inspection, iterative edits, GLB/PNG/Blend exports. No fixed object category.'}
        if name=='blender_scene_execute':
            if set(args)-{'code','expected_revision','user_prompt'}:raise ValueError('Unknown arguments.')
            code=args.get('code');prompt=args.get('user_prompt')
            if not isinstance(code,str) or not code.strip() or len(code)>MAX_CODE:raise ValueError('Provide nonempty bpy code, at most 48000 characters.')
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>3000:raise ValueError('Include the user modeling request in user_prompt.')
        elif name=='blender_scene_export':
            if set(args)-{'expected_revision'}:raise ValueError('Unknown arguments.')
            if state is None:raise ValueError('Create actual geometry first with blender_scene_execute.')
            prompt='Export the current confirmed concept scene as GLB, PNG and editable Blender source.'
        else:raise ValueError('Unknown scene tool.')
        require_revision(state,args.get('expected_revision'))
        workspace=folder/'operations'/uuid4().hex;workspace.mkdir(parents=True,mode=0o700)
        if state:
            source=folder/'versions'/state['snapshot']/'scene.blend'
            if source.is_symlink() or not source.is_file():raise RuntimeError('Current scene snapshot is missing; no scene was overwritten.')
            shutil.copyfile(source,workspace/'scene.blend')
        async with worker(workspace) as client:
            if name=='blender_scene_execute':
                output=await execute(client,code,prompt)
                inspection=facts(await execute(client,INSPECT,prompt))
                await execute(client,"import bpy\nfor image in bpy.data.images:\n    if image.type!='RENDER_RESULT' and image.size[0]>0:\n        image.pack()\nbpy.ops.file.pack_all()\nbpy.ops.wm.save_as_mainfile(filepath='/workspace/scene.blend')\nprint('HUG_SNAPSHOT_SAVED')",prompt)
            else:
                output=await execute(client,EXPORT,prompt)
                if 'HUG_EXPORT_COMPLETE' not in output:raise RuntimeError('Export did not complete.')
                inspection=facts(await execute(client,INSPECT,prompt))
        if name=='blender_scene_execute':
            snapshot='v'+str((state['revision'] if state else 0)+1)+'-'+uuid4().hex
            dest=folder/'versions'/snapshot;dest.mkdir(parents=True)
            shutil.copyfile(workspace/'scene.blend',dest/'scene.blend')
            state={'revision':(state['revision'] if state else 0)+1,'snapshot':snapshot,'facts':inspection,'last_request':prompt,'history':(state.get('history',[]) if state else [])+([{'revision':state['revision'],'snapshot':state['snapshot']}] if state else []),'demo':True,'kind':'general-scene'}
            save_json(state_path,state)
            return {'ok':True,'revision':state['revision'],'facts':inspection,'output':output[:12000],'notice':'Scene geometry is created by Blender, not by a fixed object template. Concept only; inspect the preview and iterate.'}
        from bridge import validate_export
        from PIL import Image,ImageDraw
        with Image.open(workspace/'preview.png') as image:
            image=image.convert('RGB');draw=ImageDraw.Draw(image);draw.rectangle((0,738,1024,768),fill='white');draw.text((16,748),'CONCEPT | revision '+str(state['revision'])+' | Powered by HugAgentOS + Blender | Not production CAD or garment pattern',fill='#334455');image.save(workspace/'preview.png')
        checked={filename:validate_export(workspace/filename) for filename in ('model.glb','preview.png','scene.blend')}
        from core.files.artifacts.generated import store_generated_file_path
        refs=[]
        for filename,mime in [('model.glb','model/gltf-binary'),('preview.png','image/png'),('scene.blend','application/x-blender')]:
            ref=store_generated_file_path(workspace/filename,name='concept-v'+str(state['revision'])+'-'+filename,mime_type=mime,user_id=user,source='blender-mcp',extra_metadata={'chat_id':chat,'revision':state['revision'],'demo':True,'sha256':checked[filename]['sha256']})
            if ref is None:raise RuntimeError('Export exists but download registration failed.')
            refs.append({**ref,'sha256':checked[filename]['sha256']})
        with Image.open(workspace/'preview.png') as preview:
            preview.thumbnail((640,480));buffer=io.BytesIO();preview.save(buffer,'PNG')
        return {'_preview_image_b64':base64.b64encode(buffer.getvalue()).decode('ascii'),'ok':True,'revision':state['revision'],'facts':inspection,'artifacts':refs,'notice':'Visible scene meshes exported, except objects tagged hug_display_only. Render uses the scene camera; textures embedded where supported by glTF. Not manufacturing CAD, fit simulation or a garment pattern.'}
