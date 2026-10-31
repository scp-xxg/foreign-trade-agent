"""Bounded parametric sample geometry, executed through the real upstream MCP.
No model-authored Python, paths, imports or paid/remote asset calls.
"""
import json
import math

COLORS={'blue':(0.025,0.19,0.65,1),'green':(0.035,0.36,0.20,1),'white':(0.82,0.84,0.86,1),'black':(0.025,0.03,0.04,1),'orange':(0.9,0.25,0.035,1)}
DEFAULT={'width_cm':20.0,'depth_cm':10.0,'height_cm':8.0,'compartments':3,'wall_mm':3.0,'color':'blue'}

def parameters(value,base=None):
    if not isinstance(value,dict) or not value:raise ValueError('请明确提供至少一个模型参数。')
    if set(value)-set(DEFAULT):raise ValueError('不支持的参数：'+','.join(sorted(set(value)-set(DEFAULT))))
    result=dict(base or DEFAULT)
    for key,num in value.items():
        if key=='color':
            if num not in COLORS:raise ValueError('color 支持 blue/green/white/black/orange。')
        elif key=='compartments':
            if type(num) is not int or not 1<=num<=8:raise ValueError('分格数必须是 1–8 的整数。')
        elif type(num) not in (int,float) or not math.isfinite(num):raise ValueError('尺寸必须是有限数字，不能是布尔值。')
        result[key]=num
    for key in ('width_cm','depth_cm','height_cm'):
        if not 3<=result[key]<=60:raise ValueError('外尺寸限定为 3–60 厘米。')
    if not 1<=result['wall_mm']<=8:raise ValueError('壁厚限定为 1–8 毫米。')
    if (result['width_cm']*10-(result['compartments']+1)*result['wall_mm'])/result['compartments']<10:
        raise ValueError('每格净宽不能低于 10 毫米，请减少分格或加宽。')
    return result


def build_script(p,revision,export=None):
    """Dimensions are outside bounds, in meters; staging never enters the GLB."""
    code='''import bpy, math, json
from mathutils import Vector
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for material in list(bpy.data.materials):
    if material.users == 0:
        bpy.data.materials.remove(material)
P = __PARAMS__
W,D,H,T = P['width_cm']/100, P['depth_cm']/100, P['height_cm']/100, P['wall_mm']/1000
mat=bpy.data.materials.new('Product_'+P['color'])
mat.diffuse_color=__COLOR__
mat.use_nodes=True
shader=mat.node_tree.nodes.get('Principled BSDF')
shader.inputs['Base Color'].default_value=__COLOR__
shader.inputs['Roughness'].default_value=0.35
parts=[]
def block(name,size,location):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object
    obj.name=name
    obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(mat)
    bevel=obj.modifiers.new('Rounded sample edges','BEVEL')
    bevel.width=min(T*0.18,0.0008)
    bevel.segments=3
    obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    parts.append(obj)
    return obj
block('Product_Base',(W,D,T),(0,0,T/2))
block('Product_Left',(T,D,H-T),(-W/2+T/2,0,(H+T)/2))
block('Product_Right',(T,D,H-T),(W/2-T/2,0,(H+T)/2))
block('Product_Back',(W-2*T,T,H-T),(0,D/2-T/2,(H+T)/2))
block('Product_Front',(W-2*T,T,H-T),(0,-D/2+T/2,(H+T)/2))
inner=(W-(P['compartments']+1)*T)/P['compartments']
for i in range(1,P['compartments']):
    x=-W/2+T+i*inner+(i-0.5)*T
    block('Product_Divider_'+str(i),(T,D-2*T,H-T),(x,0,(H+T)/2))
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.unit_settings.length_unit='CENTIMETERS'
scene['demo_revision']=__REV__
scene['demo_parameters']=json.dumps(P)
scene['demo_notice']='Concept sample only; no manufacturing, certification or material claim. Powered by HugAgentOS.'
# Ground, camera and lights are display-only.
bpy.ops.mesh.primitive_plane_add(size=max(W,D)*5,location=(0,0,-0.0005))
ground=bpy.context.object
ground.name='Stage_Ground'
ground_mat=bpy.data.materials.new('Stage_White')
ground_mat.diffuse_color=(0.78,0.81,0.85,1)
ground.data.materials.append(ground_mat)
bpy.ops.object.camera_add(location=(W*1.6,-D*2.8,H*3.2))
cam=bpy.context.object
cam.name='Stage_Camera'
cam.rotation_euler=(Vector((0,0,H*0.4))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO'
cam.data.ortho_scale=max(W,D,H)*1.7
cam.data.lens=50
scene.camera=cam
for name,loc,power,size in [('Key',(W,-D*2,H*4),8,max(W,D)*2),('Fill',(-W,D,H*3),4,max(W,D)*2)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    light=bpy.context.object
    light.name='Stage_'+name
    light.data.energy=power
    light.data.shape='DISK'
    light.data.size=size
    light.rotation_euler=(Vector((0,0,H/2))-light.location).to_track_quat('-Z','Y').to_euler()
scene.world.color=(0.35,0.35,0.35)
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=16
scene.render.threads_mode='FIXED'
scene.render.threads=4
scene.render.resolution_x=1024
scene.render.resolution_y=768
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.view_settings.view_transform='AgX'
bpy.ops.object.select_all(action='DESELECT')
for obj in parts:
    obj.select_set(True)
bpy.context.view_layer.objects.active=parts[0]
points=[obj.matrix_world@Vector(corner) for obj in parts for corner in obj.bound_box]
actual=[round((max(v[i] for v in points)-min(v[i] for v in points))*100,4) for i in range(3)]
print('HUG_MODEL_FACTS:'+json.dumps({'revision':__REV__,'actual_dimensions_cm':actual,'product_meshes':len(parts),'compartments':P['compartments'],'color':P['color'],'wall_mm':P['wall_mm'],'demo':True}))
'''.replace('__PARAMS__',repr(p)).replace('__COLOR__',repr(COLORS[p['color']])).replace('__REV__',str(revision))
    if export:
        code+='\nbpy.ops.export_scene.gltf(filepath='+repr(str(export/'model.glb'))+",export_format='GLB',use_selection=True,export_apply=True)\n"
        code+='bpy.ops.wm.save_as_mainfile(filepath='+repr(str(export/'scene.blend'))+')\n'
        code+='scene.render.filepath='+repr(str(export/'preview.png'))+'\nbpy.ops.render.render(write_still=True)\n'
        code+="print('HUG_EXPORT_COMPLETE')\n"
    return code
