"""Head-to-body ratio: measure it on a built VRM; scale the head of a weight result to a chosen ratio.

  python3 head_ratio.py measure BUILT.vrm
      heads tall = stature / head height. Head height: top of the skull (head and scalp materials; hair, neck blend,
      eyes and decals left out) down to the chin; stature: the same top down to the soles.
  python3 head_ratio.py plan BUILT.vrm TARGET [CURRENT_SCALE]
      the head scale (about the head joint) that gives TARGET heads, as JSON; CURRENT_SCALE is the scale the build
      already carries (work/weights/head_scale.json), so the result applies to the original weight result
  blender -b weighted.blend --python head_ratio.py -- apply SCALE OUT.blend
      scales what the head bone carries about the head joint: every vertex by its share of head weight (the head and
      hair parts are rigid, the neck blends), and the bones under the head. The proportion step of Charakuru would
      need a new rig and weight transfer for the same change (11-26, 人物2 8.9 -> 8.0 heads).
pipeline/head_ratio.sh wraps these.
"""
import json
import struct
import sys

import numpy as np

HEAD_MAT = ('Material_head', 'Material_scalp')        # skull surfaces; hair, neck blend, eyes and decals are not head height


def read_glb(path):
    b = open(path, 'rb').read()
    n = struct.unpack_from('<I', b, 12)[0]
    J = json.loads(b[20:20 + n])
    o = 20 + n
    binlen = struct.unpack_from('<I', b, o)[0]
    BIN = b[o + 8:o + 8 + binlen]

    def acc(i):
        a = J['accessors'][i]
        v = J['bufferViews'][a['bufferView']]
        k = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a['componentType']]
        off = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        return np.frombuffer(BIN[off:off + a['count'] * k * np.dtype(dt).itemsize], dt).reshape(a['count'], k).astype(float)
    return J, acc


def node_world(J):
    """world matrices of all nodes (glTF y-up)"""
    W = [None] * len(J['nodes'])
    parent = {c: i for i, nd in enumerate(J['nodes']) for c in nd.get('children', [])}

    def local(nd):
        if 'matrix' in nd:
            return np.array(nd['matrix']).reshape(4, 4).T
        T = np.eye(4)
        x, y, z, w = nd.get('rotation', [0, 0, 0, 1])
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        T[:3, :3] = R * np.array(nd.get('scale', [1, 1, 1]))
        T[:3, 3] = nd.get('translation', [0, 0, 0])
        return T

    def get(i):
        if W[i] is None:
            W[i] = (get(parent[i]) if i in parent else np.eye(4)) @ local(J['nodes'][i])
        return W[i]
    for i in range(len(J['nodes'])):
        get(i)
    return W


def measure(path):
    J, acc = read_glb(path)
    W = node_world(J)
    allY, head = [], []
    for i, nd in enumerate(J['nodes']):
        if 'mesh' not in nd:
            continue
        for pr in J['meshes'][nd['mesh']]['primitives']:
            P = acc(pr['attributes']['POSITION'])
            P = P @ W[i][:3, :3].T + W[i][:3, 3] if 'skin' not in nd else P     # skinned meshes are in bind space
            name = J['materials'][pr['material']]['name'] if 'material' in pr else ''
            allY.append(P[:, 1].min())
            if name.startswith(HEAD_MAT):
                head.append(P)
    if not head:
        raise SystemExit('no head material (' + ', '.join(HEAD_MAT) + ') in ' + path)
    H = np.vstack(head)
    top = float(H[:, 1].max())
    face = H[H[:, 2] > np.median(H[:, 2])]          # the chin is on the front half (a neck stub behind is not)
    chin = float(face[:, 1].min())
    foot = float(min(allY))
    hb = J['extensions']['VRMC_vrm']['humanoid']['humanBones']['head']['node']
    pivot = float(W[hb][1, 3])
    stature, hh = top - foot, top - chin
    return dict(stature=round(stature, 4), head_height=round(hh, 4), heads=round(stature / hh, 2), top=round(top, 4),
                chin=round(chin, 4), foot=round(foot, 4), head_joint=round(pivot, 4))


def plan(m, target, current=1.0):
    # scaling about the head joint by k: top' = j + k (top - j), chin' = j + k (chin - j), soles stay
    # target = (stature + (k - 1) a) / (k h), a = top - j  ->  k = (stature - a) / (target h - a)
    a = m['top'] - m['head_joint']
    k = (m['stature'] - a) / (target * m['head_height'] - a)
    return dict(target=target, step=round(k, 4), scale=round(current * k, 4), heads_before=m['heads'])


def apply(scale, out):
    import bpy
    from mathutils import Vector
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.name.startswith('CharaKit_Weights_') and o.name.endswith('_Rig'))
    hb = rig.data.bones['head']
    sub = {hb.name} | {b.name for b in hb.children_recursive}
    RW = rig.matrix_world
    P = RW @ hb.head_local
    moved = {}
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.parent != rig:
            continue
        gi = {g.index: g.name for g in o.vertex_groups}
        MW, MWi = o.matrix_world, o.matrix_world.inverted()
        keys = o.data.shape_keys.key_blocks if o.data.shape_keys else []
        n = 0
        for v in o.data.vertices:
            tot = sum(g.weight for g in v.groups)
            w = sum(g.weight for g in v.groups if gi.get(g.group) in sub)
            if tot <= 0 or w <= 0:
                continue
            f = 1 + (scale - 1) * w / tot
            v.co = MWi @ (P + f * (MW @ v.co - P))
            for kb in keys:
                kb.data[v.index].co = MWi @ (P + f * (MW @ kb.data[v.index].co - P))
            n += 1
        if n:
            moved[o.name] = n
    bpy.context.view_layer.objects.active = rig
    for o in bpy.context.selected_objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    Pl = RW.inverted() @ P
    for name in sub:
        eb = rig.data.edit_bones[name]
        if name != hb.name:
            eb.head = Pl + scale * (eb.head - Pl)
        eb.tail = Pl + scale * (eb.tail - Pl)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print('HEAD_SCALE_OK ' + json.dumps(dict(scale=scale, joint=[round(x, 4) for x in P], bones=sorted(sub), vertices=moved)))


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    if args[0] == 'measure':
        print(json.dumps(measure(args[1])))
    elif args[0] == 'plan':
        print(json.dumps(plan(measure(args[1]), float(args[2]), float(args[3]) if len(args) > 3 else 1.0)))
    elif args[0] == 'apply':
        apply(float(args[1]), args[2])
