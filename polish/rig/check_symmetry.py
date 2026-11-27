"""Check Tripo's returned rig for one-sided joint offsets, and optionally fix fingers.

Tripo sometimes places one hand's finger joints ~1.4 cm off (purple, 11-11). Run this on
the returned FBX before the kit's import-bones step.

usage: blender -b --factory-startup --python check_symmetry.py -- RETURNED.fbx [FIXED.fbx]
  Prints every left/right pair whose mirrored positions differ by more than 1 % of the rig
  height (Tripo's normal noise stays under 0.7 %; the bad purple hand was 1.6-1.9 %). For finger chains over the limit, the
  side whose joints sit closer to the middle of the finger mesh is kept; with FIXED.fbx the
  other side is replaced by its mirror image and written out. Arms, legs and the rest are
  only reported.
"""
import json
import sys

import bpy
import numpy as np
from mathutils.kdtree import KDTree

FINGERS = ('Thumb', 'Index', 'Middle', 'Ring', 'Little')
LIMIT = 0.01  # of rig height; Tripo's own quantisation noise stays under 0.7 %


def main(src, dst=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=src)
    arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    bones = arm.data.bones
    pairs = [(b.name, b.name.replace('_L_', '_R_')) for b in bones
             if '_L_' in b.name and b.name.replace('_L_', '_R_') in bones]
    if not pairs:
        raise SystemExit('no _L_/_R_ bone pairs found')
    head = lambda n: np.array(bones[n].head_local, dtype=float)
    lh, rh = head('J_Bip_L_Hand'), head('J_Bip_R_Hand')
    ax = int(np.argmax(np.abs(lh - rh)))
    centre = float(np.median([(head(l)[ax] + head(r)[ax]) / 2 for l, r in pairs]))
    up = int(np.argmax(np.abs(head('J_Bip_C_Head') - head('J_Bip_L_Foot'))))
    height = abs(head('J_Bip_C_Head')[up] - min(head(n)[up] for n in bones.keys() if 'Toe' in n or 'Foot' in n))
    limit = LIMIT * height

    def mir(v):
        w = np.array(v, float)
        w[ax] = 2 * centre - w[ax]
        return w

    # Mesh in armature space, for judging which side sits inside the fingers.
    inv = arm.matrix_world.inverted()
    pts = []
    for o in bpy.context.scene.objects:
        if o.type == 'MESH':
            m = inv @ o.matrix_world
            pts += [m @ v.co for v in o.data.vertices]
    tree = KDTree(len(pts))
    for i, p in enumerate(pts):
        tree.insert(p, i)
    tree.balance()
    pts = np.array(pts)

    def off_centre(name):
        found = tree.find_n(head(name), 40)
        return float(np.linalg.norm(pts[[i for _, i, _ in found]].mean(0) - head(name)))

    report = dict(mirror_axis=ax, centre=round(float(centre), 5), height=round(float(height), 4),
                  limit=round(float(limit), 5), over=[], fix={})
    for l, r in pairs:
        d = float(np.linalg.norm(mir(head(l)) - head(r)))
        if d > limit:
            report['over'].append([l.replace('_L_', '_?_'), round(float(d / height * 100), 2)])
    for f in FINGERS:
        chain = [n for n, _ in pairs if f'_L_{f}' in n]
        if not chain:
            continue
        worst = max(float(np.linalg.norm(mir(head(n)) - head(n.replace('_L_', '_R_')))) for n in chain)
        if worst <= limit:
            continue
        cl = sum(off_centre(n) for n in chain)
        cr = sum(off_centre(n.replace('_L_', '_R_')) for n in chain)
        report['fix'][f] = dict(keep='L' if cl <= cr else 'R', worst_pct=round(worst / height * 100, 2),
                                off_centre_L=round(cl / len(chain) / height * 100, 2),
                                off_centre_R=round(cr / len(chain) / height * 100, 2))
    print('SYMMETRY ' + json.dumps(report))
    if not dst or not report['fix']:
        return
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    for f, info in report['fix'].items():
        good, bad = ('_L_', '_R_') if info['keep'] == 'L' else ('_R_', '_L_')
        for n in [b.name for b in eb if f'{good}{f}' in b.name]:
            g, b = eb[n], eb[n.replace(good, bad)]
            b.head, b.tail, b.roll = mir(g.head), mir(g.tail), -g.roll
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.ops.export_scene.fbx(filepath=dst, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             add_leaf_bones=False, bake_anim=False, path_mode='STRIP', embed_textures=False)
    print('SYMMETRY_FIXED ' + dst)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:][:2])
