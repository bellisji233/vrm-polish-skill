"""Are the Tripo fingers separate? Decides between keeping the generated hand and the template hand.

Planes across the four fingers, stepped along their first segments (proximal phalanges) from the knuckles to the
middle knuckles, cut the hand mesh; for each pair of neighbouring fingers the highest plane where both bones sit in the
same piece of the cut is the top of the web between them.

usage (inside Blender, file with the kit's weighted rig and Body):
    blender -b weighted.blend --python finger_gap.py -- OUT.json
library: finger_gap(body, rig) -> {'L': {...}, 'R': {...}}
"""
import bpy, bmesh, json, sys
import numpy as np
from mathutils import Vector

FINGERS = ('index', 'middle', 'ring', 'little')


def _cut(bm, origin, normal, near, radius):
    """Segments of faces within radius of near crossing the plane, joined by shared mesh edges."""
    segs = {}                                                  # edge index -> point where the plane crosses it
    for e in bm.edges:
        a, b = e.verts[0].co, e.verts[1].co
        if (a - near).length > radius and (b - near).length > radius:
            continue
        da, db = (a - origin).dot(normal), (b - origin).dot(normal)
        if da * db < 0:
            segs[e.index] = a + (b - a) * (da / (da - db))
    parent = {k: k for k in segs}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]; k = parent[k]
        return k
    for f in bm.faces:
        es = [e.index for e in f.edges if e.index in segs]
        for i in range(1, len(es)):
            parent[find(es[i])] = find(es[0])
    groups = {}
    for k, p in segs.items():
        groups.setdefault(find(k), []).append(p)
    return [np.array([tuple(p) for p in g]) for g in groups.values() if len(g) >= 3]


def finger_gap(body, rig, steps=11):
    """Per side: for each pair of neighbouring fingers, how far up the first segment they are joined (web), as a
    fraction of the first segment from the knuckle (0) to the middle knuckle (1)."""
    RW = rig.matrix_world
    bm = bmesh.new(); bm.from_mesh(body.data); bm.transform(body.matrix_world)
    mats = [m.name if m else '' for m in body.data.materials]
    acc = {i for i, n in enumerate(mats) if 'accessor' in n.lower()}
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in acc], context='FACES')
    bm.edges.ensure_lookup_table(); bm.edges.index_update()
    out = {}
    for side in ('L', 'R'):
        bones = {f: rig.data.bones.get(f'{f}_proximal.{side}') for f in FINGERS}
        if not all(bones.values()):
            out[side] = dict(error='finger bones missing'); continue
        axis = (RW @ bones['middle'].tail_local - RW @ bones['middle'].head_local).normalized()
        joined_up_to = {f'{a}-{b}': 0.0 for a, b in zip(FINGERS, FINGERS[1:])}
        for k in range(steps):
            t = k / (steps - 1)                                  # 0 knuckle .. 1 middle knuckle
            pts = {f: RW @ (b.head_local.lerp(b.tail_local, t)) for f, b in bones.items()}
            origin = sum(pts.values(), Vector()) / 4
            span = max((pts['index'] - pts['little']).length, 1e-3)
            pieces = _cut(bm, origin, axis, origin, 1.2 * span + 0.01)
            owner = {}
            for f, m in pts.items():
                ds = [np.linalg.norm(P - np.array(tuple(m)), axis=1).min() for P in pieces]
                owner[f] = int(np.argmin(ds)) if ds else -1
            for a, b in zip(FINGERS, FINGERS[1:]):
                if owner[a] == owner[b]:
                    joined_up_to[f'{a}-{b}'] = t
        web = max(joined_up_to.values())
        out[side] = dict(web=round(web, 2), pairs={k: round(v, 2) for k, v in joined_up_to.items()})
    bm.free()
    return out


if __name__ == '__main__' and '--' in sys.argv:
    dst = sys.argv[sys.argv.index('--') + 1]
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and 'hand.L' in o.data.bones)
    res = finger_gap(bpy.data.objects['Body'], rig)
    json.dump(res, open(dst, 'w'), indent=1)
    print('FINGER_GAP', json.dumps(res))
