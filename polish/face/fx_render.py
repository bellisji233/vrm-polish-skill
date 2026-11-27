"""Front render of the built character for drawing its anime face effects (fx_cutout.py cuts them out).

The camera is the head profile's decal camera (PROFILE/fx/fx.json), carried into this character through the head frame,
so the decals project back onto this face with the same camera and need no warp. The old decal faces (FX_*) are left
out of the render.
usage: blender -b work/character-built.blend --python fx_render.py -- PROFILE_FX_DIR OUT.png s tx ty tz
"""
import bpy, bmesh, sys, json, math
from mathutils import Vector
argv = sys.argv[sys.argv.index('--') + 1:]; FX0, OUT, s, tx, ty, tz = argv[0], argv[1], *map(float, argv[2:6])
info = json.load(open(FX0 + '/fx.json')); c = info['image']['camera']; W, H = info['image']['size']; x0, y0, x1, y1 = c['crop']
h = bpy.data.objects['Head']; me = h.data
fx = {i for i, m in enumerate(me.materials) if m and m.name.startswith('FX_')}
bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in fx], context='FACES'); bm.to_mesh(me); bm.free()
scn = bpy.context.scene
scn.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
for o in bpy.data.objects:
    if o.type == 'MESH': o.hide_render = o.name not in ('Head', 'Hair', 'Body')
prof = lambda p: Vector((p[0] * s + tx, p[1] * s + ty, p[2] * s + tz))
pos = prof((c['pos'][0], -c['pos'][2], c['pos'][1])); tgt = prof((c['target'][0], -c['target'][2], c['target'][1]))
cd = bpy.data.cameras.new('fx'); cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(c['fov'])
cam = bpy.data.objects.new('fx', cd); scn.collection.objects.link(cam); scn.camera = cam
cam.location = pos; cam.rotation_euler = (tgt - pos).to_track_quat('-Z', 'Y').to_euler()
FW = int(round(W / (x1 - x0))); scn.render.resolution_x = FW; scn.render.resolution_y = H
scn.render.use_border = True; scn.render.use_crop_to_border = True
scn.render.border_min_x, scn.render.border_max_x, scn.render.border_min_y, scn.render.border_max_y = x0, x1, 0.0, 1.0
scn.world = scn.world or bpy.data.worlds.new('W'); scn.world.use_nodes = True
bg = scn.world.node_tree.nodes.get('Background'); bg.inputs[0].default_value = (1, 1, 1, 1); bg.inputs[1].default_value = 1.0
scn.view_settings.view_transform = 'Standard'; scn.render.film_transparent = False
scn.render.filepath = OUT; bpy.ops.render.render(write_still=True)
print('FX_RENDER', FW, H)
