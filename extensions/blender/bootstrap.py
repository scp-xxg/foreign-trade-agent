"""Load the pinned upstream add-on in a GUI Blender on Xvfb, bound to loopback."""
import importlib.util
import os
from pathlib import Path
import sys
import bpy
os.environ['DISABLE_TELEMETRY']='true'
root=Path(__file__).resolve().parents[2] if not os.environ.get('HUG_BLENDER_ADDON') else Path('/')
addon=Path(os.environ.get('HUG_BLENDER_ADDON',str(root/'.runtime/blender-mcp-upstream/addon.py')))
project=os.environ.get('HUG_BLENDER_PROJECT_FILE','')
if project and Path(project).is_file():
    bpy.ops.wm.open_mainfile(filepath=project,use_scripts=False)
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
spec=importlib.util.spec_from_file_location('hug_blender_mcp',addon)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
module.register()
bpy.context.preferences.filepaths.use_scripts_auto_execute=False
bpy.context.scene.blendermcp_auto_start_server=False
server=module.BlenderMCPServer(host='127.0.0.1',port=int(os.environ.get('HUG_BLENDER_PORT','9876')))
bpy.types.blendermcp_server=server
server.start()
bpy.context.scene.blendermcp_server_running=server.running
print('HUG_BLENDER_READY',server.running,flush=True)
