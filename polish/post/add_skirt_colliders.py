"""Add arm and hand colliders to the skirt chains of an already registered spring rig (in place).

blender -b character.blend --disable-autoexec --python-exit-code 1 -P add_skirt_colliders.py -- CONFIG.json
The kit's skirt plan keeps the skirt off the legs; hands and forearms hanging beside the hips went
through it. Each entry is a capsule along part of a bone (fractions of the head->tail segment, the
tail can be extended to another bone's tail) or a sphere at a fraction of a bone, optionally moved
by a rest-pose world offset. One group
"Skirt/arms" is added to every listed chain; existing colliders and groups are kept.
"""
import json
import sys
import uuid
from pathlib import Path

import bpy
from mathutils import Vector

cfg = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
rig = bpy.data.objects[cfg['armature']]
sb = rig.data.vrm_addon_extension.spring_bone1
if any(g.vrm_name == cfg['group'] for g in sb.collider_groups):
    raise ValueError('group already present; start from the saved baseline')
springs = {s.vrm_name: s for s in sb.springs}
missing = [c for c in cfg['chains'] if c not in springs]
if missing:
    raise ValueError('missing chains: ' + ', '.join(missing))


def world_head_tail(name):
    b = rig.data.bones[name]
    return rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local


ids = []
for item in cfg['colliders']:
    h, t = world_head_tail(item['bone'])
    if item.get('to_tail_of'):
        t = world_head_tail(item['to_tail_of'])[1]
    # a wide pad offset to the outside of the arm (rest-pose world direction): its inner surface sits
    # just inside the arm, so skirt joints under a hanging arm are pressed in, not passed through
    off = Vector(item.get('offset_world', (0, 0, 0)))
    h, t = h + off, t + off
    c = sb.colliders.add()
    c.uuid = uuid.uuid4().hex
    c.node.bone_name = item['bone']
    capsule = item['shape'] == 'capsule'
    c.shape_type = 'Capsule' if capsule else 'Sphere'
    c.reset_bpy_object(bpy.context, rig)
    parent = rig.matrix_world @ rig.pose.bones[item['bone']].matrix
    inv = parent.inverted()
    if capsule:
        c.shape.capsule.offset = inv @ h.lerp(t, item['from'])
        c.shape.capsule.tail = inv @ h.lerp(t, item['to'])
        c.shape.capsule.radius = item['radius']
    else:
        c.shape.sphere.offset = inv @ h.lerp(t, item['at'])
        c.shape.sphere.radius = item['radius']
    ids.append(c.uuid)
g = sb.collider_groups.add()
g.uuid = uuid.uuid4().hex
g.vrm_name = cfg['group']
for i in ids:
    g.colliders.add().collider_uuid = i
for name in cfg['chains']:
    ref = springs[name].collider_groups.add()
    ref.collider_group_uuid = g.uuid
bpy.context.view_layer.update()
r = bpy.ops.wm.save_mainfile()
if 'FINISHED' not in r:
    raise RuntimeError('save failed')
print('EXTRA_COLLIDERS_OK', len(ids))
