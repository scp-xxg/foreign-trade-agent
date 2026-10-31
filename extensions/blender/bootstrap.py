"""Load the pinned upstream add-on in a GUI Blender on Xvfb, bound to loopback."""
import importlib.util
import os
from pathlib import Path
import sys
import bpy
os.environ['DISABLE_TELEMETRY']='true'
root=Path(__file__).resolve().parents[2]
addon=root/'.runtime/blender-mcp-upstream/addon.py'
spec=importlib.util.spec_from_file_location('hug_blender_mcp',addon)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
module.register()
bpy.context.preferences.filepaths.use_scripts_auto_execute=False
bpy.context.scene.blendermcp_auto_start_server=False
server=module.BlenderMCPServer(host='127.0.0.1',port=9876)
bpy.types.blendermcp_server=server
server.start()
bpy.context.scene.blendermcp_server_running=server.running
print('HUG_BLENDER_READY',server.running,flush=True)
