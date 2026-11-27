"""Finish the kit's weight transfer when small loose pieces sit inside the hand region.

The kit's transfer-weights job ends with an automatic (bone heat) pass on a copy of each hand and wrist.
Bone heat gives no weights to small disconnected islands floating there (bracelet beads, a watch), and the
whole hand region can fail, and the kit then stops with "Automatic hand weights missing". This script runs the
same finish stage on the job's transferred checkpoint with one change: when bone heat leaves vertices empty, it is
solved again on a copy without the accessory pieces (faces using the accessories texture group's material) and other
small loose islands, and those pieces take the weights of the nearest skin vertex. The finish stage itself is the
kit's transfer.finish, called unchanged.

usage: blender -b <job>/backups/transfer-*/weighted.blend --python finish_weights.py -- KIT OUT_DIR
       writes OUT_DIR/weighted.blend and OUT_DIR/weighted-review.fbx, prints FINISH_OK with the hands that needed it
"""
import bpy, bmesh, sys, json, math, importlib.util
from pathlib import Path
from mathutils import kdtree

KIT, OUT = sys.argv[sys.argv.index('--') + 1:][:2]
SCRIPTS = Path(KIT) / 'skills/avatar-weight-transfer/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


filled = []


def _islands(mesh):
    adj = [[] for _ in mesh.vertices]
    for e in mesh.edges:
        i, j = e.vertices
        adj[i].append(j); adj[j].append(i)
    lab = [-1] * len(adj); out = []
    for s0 in range(len(adj)):
        if lab[s0] >= 0:
            continue
        stack = [s0]; lab[s0] = len(out); part = []
        while stack:
            v = stack.pop(); part.append(v)
            for w in adj[v]:
                if lab[w] < 0:
                    lab[w] = lab[s0]; stack.append(w)
        out.append(part)
    return out


def _copy_weights(scratch, src, index_map):
    """Write src's vertex groups onto scratch: mapped vertices by index, the rest from the nearest mapped one."""
    names = {g.index: g.name for g in src.vertex_groups}
    rows = [{names[g.group]: g.weight for g in v.groups if g.weight > 1e-8} for v in src.data.vertices]
    kd = kdtree.KDTree(len(index_map))
    for new, old in enumerate(index_map):
        kd.insert(scratch.data.vertices[old].co, new)
    kd.balance()
    back = {old: new for new, old in enumerate(index_map)}
    for v in scratch.data.vertices:
        new = back.get(v.index)
        if new is None:
            _, new, _ = kd.find(v.co)
        for n, w in rows[new].items():
            (scratch.vertex_groups.get(n) or scratch.vertex_groups.new(name=n)).add([v.index], w, 'REPLACE')


def patched_parent_set(*args, **kwargs):
    """The kit's ARMATURE_AUTO on its hand copy; if bone heat fails because loose pieces float in the region,
    solve on a copy without the small islands and carry the weights back."""
    result = bpy.ops.object.parent_set(*args, **kwargs)
    scratch = next((o for o in bpy.context.selected_objects if o.name.startswith('HandHeat')), None)
    if scratch is None or kwargs.get('type') != 'ARMATURE_AUTO':
        return result
    rig = next(o for o in bpy.context.selected_objects if o.type == 'ARMATURE')
    deform = {b.name for b in rig.data.bones if b.use_deform}
    groups = {g.index: g.name for g in scratch.vertex_groups}
    empty = [v.index for v in scratch.data.vertices
             if sum(g.weight for g in v.groups if groups.get(g.group) in deform) <= 1e-8]
    if not empty:
        return result
    # leave out the accessory pieces (their own texture group) and any other small loose island
    loose = set()
    for body in bpy.data.objects:
        if body.type != 'MESH' or body == scratch or not body.data.materials:
            continue
        acc = {i for i, m in enumerate(body.data.materials) if m and 'accessor' in m.name.lower()}
        if not acc:
            continue
        pts = {tuple(round(c, 6) for c in (body.matrix_world @ body.data.vertices[i].co))
               for f in body.data.polygons if f.material_index in acc for i in f.vertices}
        for v in scratch.data.vertices:
            if tuple(round(c, 6) for c in (scratch.matrix_world @ v.co)) in pts:
                loose.add(v.index)
    parts = sorted(_islands(scratch.data), key=len, reverse=True)
    rest = [p for p in parts if not loose.issuperset(p)]
    for p in rest[1:]:
        if len(p) < 0.25 * len(rest[0]):
            loose.update(p)
    keep = sorted(set(range(len(scratch.data.vertices))) - loose)
    bm = bmesh.new(); bm.from_mesh(scratch.data); bm.verts.ensure_lookup_table()
    drop = [bm.verts[i] for i in set(range(len(bm.verts))) - set(keep)]
    bmesh.ops.delete(bm, geom=drop, context='VERTS')
    clean = bpy.data.meshes.new('HandHeatClean'); bm.to_mesh(clean); bm.free()
    tmp = bpy.data.objects.new('HandHeatClean', clean)
    bpy.context.scene.collection.objects.link(tmp); tmp.matrix_world = scratch.matrix_world
    try:
        bpy.ops.object.select_all(action='DESELECT')
        tmp.select_set(True); rig.select_set(True); bpy.context.view_layer.objects.active = rig
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        _copy_weights(scratch, tmp, keep)
    finally:
        bpy.data.objects.remove(tmp, do_unlink=True)
        bpy.data.meshes.remove(clean)
        bpy.ops.object.select_all(action='DESELECT')
        scratch.select_set(True); rig.select_set(True); bpy.context.view_layer.objects.active = rig
    filled.append(dict(region_vertices=len(scratch.data.vertices), loose_vertices=len(loose)))
    return result


class _Ops:
    def __getattr__(self, name):
        sub = getattr(bpy.ops, name)
        if name != 'object':
            return sub
        class _Obj:
            def __getattr__(self, op):
                return patched_parent_set if op == 'parent_set' else getattr(bpy.ops.object, op)
        return _Obj()


class _Bpy:
    ops = _Ops()

    def __getattr__(self, name):
        return getattr(bpy, name)


tr = load('transfer')
# The kit's own finish stage (transfer.finish), run as is; only the body_finish module it loads gets the bpy wrapper
# above, so its parent_set call retries without the loose pieces.
_spec_orig = importlib.util.spec_from_file_location


def _spec(name, path, *a, **k):
    spec = _spec_orig(name, path, *a, **k)
    if name == 'body_finish':
        _exec = spec.loader.exec_module

        def exec_module(mod):
            _exec(mod)
            mod.bpy = _Bpy()
        spec.loader.exec_module = exec_module
    return spec


importlib.util.spec_from_file_location = _spec
try:
    col = next(c for c in bpy.data.collections if c.name.startswith('CharaKit_Weights_'))
    report = tr.finish({'collection': col.name, 'output_dir': OUT})
finally:
    importlib.util.spec_from_file_location = _spec_orig
out = Path(report['output'])
for f in ('weighted.blend', 'weighted-review.fbx'):
    (Path(OUT) / f).write_bytes((out / f).read_bytes())
print('FINISH_OK', json.dumps({'hands_resolved_without_loose_pieces': filled,
                               'fingers': (report.get('bodyFinishing') or {}).get('fingers')}))
