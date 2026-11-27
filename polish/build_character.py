"""Build work/character.blend from the weight-transfer result (denim copy of the purple build, 11-19).

blender --background work/weights/weighted.blend --python-exit-code 1 --python work/build_character.py -- CONFIG.json

1. Face: round the cheek crease, add an under-jaw surface, swap in the repaired head texture
   (same procedure as the approved prototype, run in the assembly head space and mapped back).
2. Hair: bring the assembly hair in with the head's placement, bind it to the rig.
3. Spring bones and weights for hair, skirt and the chest-bow ribbon tails (bones are authored
   here; registration and checks are done afterwards by the kit's spring-setup.py).
4. Hair colliders (head, neck, chest, shoulders), MToon on every mesh, save.
Helper rigs from the weight job are kept but hidden and marked non-VRM so that only one
VRM 1.0 humanoid remains.
"""
import importlib.util
import json
import math
import sys
import uuid
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

cfg = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
KIT = Path(cfg['kit'])
report = {}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mtoon = load('mtoon_export', KIT / 'scripts/mtoon-export.py')


def _face_module(path, name):
    """Face helper modules ship in polish/face/; a config may still point at its own copy."""
    if path and Path(path).is_file():
        return Path(path)
    return Path(__file__).resolve().parent / 'face' / f'{name}.py'
def _work_dir(name):
    """generated images go to this project's work folder, never into a head profile"""
    d = Path(cfg['output_blend']).parent / name
    d.mkdir(parents=True, exist_ok=True)
    return d
mtoon.enable_vrm()
rig = bpy.data.objects[cfg['rig']]
RW = rig.matrix_world

# --- helper rigs and meshes from the weight job: removed, so the file holds exactly one humanoid
# rig (the expression integration requires a single armature in the scene) ------------------
SKIRT_MESH = (cfg.get('skirt') or {}).get('mesh', 'Spring_01_skirt')
keep_meshes = {'Body', 'Head'} | set(cfg.get('keep_meshes', ['Spring_01_skirt', 'Spring_02_ribbon']))
helpers = [o for o in bpy.data.objects
           if (o.type == 'ARMATURE' and o != rig)
           or o.name.startswith(('Backup_', 'DonorBody_')) or o.name in ('Cube', 'TripoJointReference')]
for o in bpy.data.objects:
    if o.name in keep_meshes:
        for m in o.modifiers:
            target = getattr(m, 'object', None)
            if target in helpers:
                raise RuntimeError(f'{o.name}: modifier {m.name} uses helper {target.name}')
        if o.parent in helpers:
            mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
report['helpersRemoved'] = sorted(o.name for o in helpers)
for o in helpers:
    bpy.data.objects.remove(o, do_unlink=True)

# --- head frame (11-19): the head is the purple version's head at another scale and position. Move the whole
# scene (only the top-level objects; children follow the rig) into the purple head frame, so every head-space
# setting, constant and helper file of the purple build applies unchanged; everything is moved back before saving.
FR = cfg.get('frame')
if FR:
    _s = FR['s']
    Mfr = Matrix.Diagonal((1 / _s, 1 / _s, 1 / _s, 1.0)) @ Matrix.Translation(-Vector(FR['t']))
    for o in bpy.data.objects:
        if o.parent is None and o.type in ('MESH', 'ARMATURE', 'EMPTY'):
            o.matrix_world = Mfr @ o.matrix_world
    bpy.context.view_layer.update()
    report['frame'] = dict(s=_s, t=FR['t'])
RW = rig.matrix_world.copy()

# --- arm joints: Tripo placed them ~4.5 cm above and 2 cm behind the sleeve centre, so the puffy
# sleeve swung into the torso when the arms came down. Move shoulder->upper arm->forearm->wrist
# joints onto the measured sleeve centre line (x unchanged); hand bone keeps its length.
if cfg.get('arm_joints'):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    eb = rig.data.edit_bones
    inv = RW.inverted()
    moved = {}
    for side in ('L', 'R'):
        for joint, yzx in cfg['arm_joints'].items():
            y, z = yzx[0], yzx[1]
            b = eb[f'{joint}.{side}']
            head_w = RW @ b.head
            x = math.copysign(yzx[2], head_w.x) if len(yzx) > 2 else head_w.x
            new_head = inv @ Vector((x, y, z))
            d = new_head - b.head
            b.head = new_head
            if joint == 'hand':
                b.tail = b.tail + d
            moved[b.name] = [round(x, 4) for x in (RW @ b.head)]
        eb[f'shoulder.{side}'].tail = eb[f'upper_arm.{side}'].head
        eb[f'upper_arm.{side}'].tail = eb[f'lower_arm.{side}'].head
        eb[f'lower_arm.{side}'].tail = eb[f'hand.{side}'].head
    bpy.ops.object.mode_set(mode='OBJECT')
    report['armJoints'] = moved

# --- cuffs: the end of each sleeve follows the hand partly, so the opening tilts with the wrist
# instead of cutting through the palm when the wrist bends far. Sleeve vertices are the ones the
# forearm dominates; the share ramps up towards the rim, which sits past the wrist joint.
if cfg.get('cuff_follow'):
    cf = cfg['cuff_follow']
    body_o = bpy.data.objects['Body']
    BWm = body_o.matrix_world
    changed = 0
    for side, sg in (('L', 1), ('R', -1)):
        wrist = RW @ rig.data.bones[f'hand.{side}'].head_local
        elbow = RW @ rig.data.bones[f'lower_arm.{side}'].head_local
        axis_v = (wrist - elbow).normalized()
        g_hand = body_o.vertex_groups[f'hand.{side}']
        g_fore = body_o.vertex_groups[f'lower_arm.{side}']
        for v in body_o.data.vertices:
            pw = BWm @ v.co
            along = (pw - wrist).dot(axis_v)                 # <0 towards the elbow
            if not (-cf['back'] <= along <= cf['front']):
                continue
            cur = {e.group: e.weight for e in v.groups}
            if cur.get(g_fore.index, 0.0) < 0.5:
                continue                                     # hand and wrist skin keep their weights
            t = min(1.0, max(0.0, (along + cf['back']) / (cf['back'] + cf['full_at'])))
            wh = cf['max'] * t * t * (3 - 2 * t)
            for gi_ in list(cur):
                cur[gi_] *= (1 - wh)
            cur[g_hand.index] = cur.get(g_hand.index, 0.0) + wh
            tot = sum(cur.values())
            for gi_, w in cur.items():
                body_o.vertex_groups[gi_].add([v.index], w / tot, 'REPLACE')
            changed += 1
    report['cuffFollow'] = changed

T = np.load(cfg['head_affine'])
S = float(np.cbrt(np.linalg.det(T[:3])))
TV = Vector(T[3].tolist())


def to_world(a):
    return a * S + TV


def to_asm(w):
    return (w - TV) / S


# =========================== 1. face ======================================================
head = bpy.data.objects['Head']
HM = head.matrix_world
HMi = HM.inverted()
me = head.data
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
uv = bm.loops.layers.uv.active
dl = bm.verts.layers.deform.verify()
head_group = head.vertex_groups['head'].index
for v in bm.verts:
    v.co = to_asm(HM @ v.co)

seen = set()
best = []
for f in bm.faces:
    if f.index in seen:
        continue
    st = [f]
    seen.add(f.index)
    isl = []
    while st:
        c = st.pop()
        isl.append(c)
        for e in c.edges:
            for g in e.link_faces:
                if g.index not in seen:
                    seen.add(g.index)
                    st.append(g)
    if len(isl) > len(best):
        best = isl
skin_faces = set(best)
skin_verts = {v for f in best for v in f.verts}


def jaw_vert(v):
    return v.co.y > -0.22 and v.co.z < 0.44 and abs(v.co.x) < 0.21


bedges = [e for e in bm.edges if len(e.link_faces) == 1 and e.link_faces[0] in skin_faces]
jaw_edges = [e for e in bedges if all(jaw_vert(v) for v in e.verts)]
jaw_vs = {v for e in jaw_edges for v in e.verts}

pairs = json.loads(Path(cfg['crease_pairs']).read_text())['pairs']
cedges = []
for a, b in pairs:
    e = bm.edges.get((bm.verts[a], bm.verts[b]))
    if e is None:
        raise ValueError('Crease edge missing; head topology differs from the prototype')
    cedges.append(e)
W = {}
ring = {v for e in cedges for v in e.verts}
for w in (1.0, 0.6, 0.3):
    for v in ring:
        W.setdefault(v, w)
    ring = {e.other_vert(v) for v in ring for e in v.link_edges} - set(W)
act = [v for v in W if v in skin_verts and not v.is_boundary and v not in jaw_vs]
for _ in range(10):
    new = {}
    for v in act:
        nb = [e.other_vert(v) for e in v.link_edges]
        avg = sum((n.co for n in nb), Vector()) / len(nb)
        new[v] = v.co + (avg - v.co) * 0.5 * W[v]
    for v, co in new.items():
        v.co = co

C2 = Vector((0.0, 0.0))
probe = Vector((0.13, -0.16, 0.33))
pv = min((v for v in skin_verts if v not in jaw_vs), key=lambda v: (v.co - probe).length)
skin_uv = pv.link_loops[0][uv].uv.copy()
copies = {}
new_verts = []
for v in jaw_vs:
    inner = [e.other_vert(v) for e in v.link_edges if e.other_vert(v) in skin_verts and not e.other_vert(v).is_boundary]
    t = (v.co - sum((n.co for n in inner), Vector()) / len(inner)).normalized() if inner else Vector((0, 0, -1))
    ringv = [bm.verts.new(v.co + t * 0.010)]
    for s_, dz in ((0.66, -0.012), (0.32, -0.018)):
        xy = C2 + (v.co.xy - C2) * s_
        ringv.append(bm.verts.new((xy.x, xy.y, v.co.z + dz)))
    copies[v] = ringv
    new_verts += ringv
for e in jaw_edges:
    f = e.link_faces[0]
    for l in f.loops:
        if l.edge == e:
            va, vb = l.vert, l.link_loop_next.vert
    chain = [(va, vb)] + [(copies[va][i], copies[vb][i]) for i in range(3)]
    for (a0, b0), (a1, b1) in zip(chain, chain[1:]):
        nf = bm.faces.new((b0, a0, a1, b1))
        nf.material_index = f.material_index
        nf.smooth = True
        for l in nf.loops:
            l[uv].uv = skin_uv
band = set(jaw_vs) | {copies[v][0] for v in jaw_vs} | {copies[v][1] for v in jaw_vs}
band |= {e.other_vert(v) for v in jaw_vs for e in v.link_edges if e.other_vert(v) in skin_verts}
for _ in range(4):
    for lam in (0.5, -0.53):
        upd = {}
        for v in band:
            nb = [e.other_vert(v) for e in v.link_edges]
            avg = sum((n.co for n in nb), Vector()) / len(nb)
            upd[v] = v.co + (avg - v.co) * lam
        for v, co in upd.items():
            v.co = co
for v in new_verts:
    v[dl][head_group] = 1.0
for v in bm.verts:
    v.co = HMi @ to_world(v.co)
bm.normal_update()
bm.to_mesh(me)
me.update()
with bpy.context.temp_override(object=head, active_object=head, selected_objects=[head], selected_editable_objects=[head]):
    if me.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
for p in me.polygons:
    p.use_smooth = True
img = bpy.data.images.load(cfg['head_texture'])
img.pack()
_fpx = np.empty(img.size[0] * img.size[1] * 4, np.float32); img.pixels.foreach_get(_fpx)
_fpx = _fpx.reshape(-1, 4)[:, :3]
_warm = (_fpx[:, 0] - _fpx[:, 2] > 0.04) & (_fpx.mean(-1) > 0.6) & (_fpx[:, 0] > _fpx[:, 1])
face_tone = np.median(_fpx[_warm], axis=0).astype(np.float32)   # skin tone used for neck, nape and hands
del _fpx, _warm
report['faceTone'] = [round(float(x), 3) for x in face_tone]
swapped = 0
for m in me.materials:
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and tuple(n.image.size) == (4096, 4096):
            n.image = img
            swapped += 1
report['face'] = dict(creaseBandVerts=len(act), jawEdges=len(jaw_edges), newVerts=len(new_verts), textureNodes=swapped)

# --- eye white behind the iris: never visible in the generated model, so it is painted with iris and skin colours
# in large patches; it shows once the iris moves (gaze). Texels of the white that something else covers from the
# front by the iris take the colour of the visible white next to the iris at the same height (median over
# height bins, pink corners and lash shadow excluded). Skin folded inside the opening behind the iris (Tripo socket
# skin) is filled the same way. Visible texels stay.
ew = cfg.get('eye_white_fill')
if ew:
    from mathutils.bvhtree import BVHTree as _BVHe
    comps_e = json.loads(Path(ew['components']).read_text())
    HMw = head.matrix_world
    Pw = np.array([HMw @ v.co for v in me.vertices])
    iris_set = {v for c in ew['iris'] for v in comps_e[c]}
    bmE = bmesh.new(); bmE.from_mesh(me); bmE.transform(HMw); bmE.faces.ensure_lookup_table()
    treeE = _BVHe.FromBMesh(bmE)
    sclera_all = {v for c in ew['sclera'] for v in comps_e[c]}
    face_white = np.array([all(v.index in sclera_all for v in f.verts) for f in bmE.faces])
    face_iris = np.array([all(v.index in iris_set for v in f.verts) for f in bmE.faces])
    skin_e = set(comps_e[ew['skin']]); loops_e = {d['n']: d['vs'] for d in json.loads(Path(ew['boundaries']).read_text())}
    from collections import Counter as _Ce
    skin_edges = _Ce()
    for p_ in me.polygons:
        vs_ = list(p_.vertices)
        if all(v in skin_e for v in vs_):
            for i_ in range(len(vs_)): skin_edges[frozenset((vs_[i_], vs_[(i_ + 1) % len(vs_)]))] += 1
    bmE.free()
    Wt, Ht = img.size
    tpx = np.empty(Wt * Ht * 4, np.float32); img.pixels.foreach_get(tpx); tpx = tpx.reshape(Ht, Wt, 4)
    uvE = me.uv_layers.active.data
    me.calc_loop_triangles()
    fill = {}
    Umask = np.zeros((Ht, Wt), bool); Kmask = np.zeros((Ht, Wt), bool)
    for ci in ew['sclera']:
        sset = set(comps_e[ci]); vis_z, vis_x, vis_c, hid = [], [], [], []
        lv_ = set(loops_e[ew['openings'][str(ci)]]); adj_ = {v: [] for v in lv_}
        for e_, c_ in skin_edges.items():               # boundary edges of the skin only; drop spurs, keep the cycle
            if c_ == 1 and all(v in lv_ for v in e_):
                a_, b_ = tuple(e_); adj_[a_].append(b_); adj_[b_].append(a_)
        while True:
            ends = [v for v, w in adj_.items() if len(w) < 2]
            if not ends: break
            for v in ends:
                for w in adj_.pop(v):
                    if w in adj_: adj_[w].remove(v)
        start_ = next(iter(adj_)); order_ = [start_]; prev_ = None
        while True:
            nxt = [w for w in adj_[order_[-1]] if w != prev_]
            if not nxt or nxt[0] == start_: break
            prev_ = order_[-1]; order_.append(nxt[0])
        ring = Pw[order_][:, [0, 2]]
        def _in_open(x, z):
            c_ = False
            for i_ in range(len(ring)):
                (xa, za), (xb, zb) = ring[i_], ring[(i_ + 1) % len(ring)]
                if (za > z) != (zb > z) and x < (xb - xa) * (z - za) / (zb - za + 1e-12) + xa: c_ = not c_
            return c_
        xc = float(np.mean([Pw[v, 0] for c in ew['iris'] for v in comps_e[c] if (Pw[v, 0] > 0.003) == (Pw[list(sset), 0].mean() > 0.003)]))
        nfold = 0
        for lt in me.loop_triangles:
            vs_ = list(lt.vertices)
            if all(v in sset for v in vs_):
                fold = False
            elif all(v in skin_e for v in vs_):
                cw_ = Pw[vs_].mean(0)
                h_ = treeE.ray_cast(Vector(cw_) + Vector((0, -0.05, 0)), Vector((0, 1, 0)), 0.1)[2]
                if not (_in_open(cw_[0], cw_[2]) and h_ is not None and face_iris[h_]):
                    continue
                fold = True; nfold += 1
            else:
                continue
            U = np.array([uvE[li].uv[:] for li in lt.loops]) * [Wt, Ht]
            X = Pw[list(lt.vertices)]
            x0, y0 = np.floor(U.min(0)).astype(int); x1, y1 = np.ceil(U.max(0)).astype(int)
            gx, gy = np.meshgrid(np.arange(max(x0, 0), min(x1, Wt - 1) + 1) + 0.5, np.arange(max(y0, 0), min(y1, Ht - 1) + 1) + 0.5)
            q = np.c_[gx.ravel(), gy.ravel()]
            T_ = np.array([U[1] - U[0], U[2] - U[0]]).T
            if abs(np.linalg.det(T_)) < 1e-9:
                continue
            bc = np.linalg.solve(T_, (q - U[0]).T).T
            w0 = 1 - bc.sum(1); inside = (bc >= -1e-6).all(1) & (w0 >= -1e-6)
            q, bc, w0 = q[inside], bc[inside], w0[inside]
            P3 = w0[:, None] * X[0] + bc[:, :1] * X[1] + bc[:, 1:] * X[2]
            for (px_, py_), p3 in zip(q.astype(int), P3):
                hit = treeE.ray_cast(Vector(p3) + Vector((0, -0.05, 0)), Vector((0, 1, 0)), 0.1)[2]
                if fold or (hit is not None and face_iris[hit]):  # under the lids the painted shadow stays
                    hid.append((py_, px_, p3[2], p3[0])); Umask[py_, px_] = True
                    continue
                if hit is not None and not face_white[hit]:
                    continue
                if tpx[py_, px_, :3].mean() > 0.45:               # visible white (not the dark iris rim): boundary
                    Kmask[py_, px_] = True
                if abs(p3[0] - xc) < ew['near_iris']:
                    c_ = tpx[py_, px_, :3]
                    if c_.mean() > 0.55 and c_[0] - c_[1] < 0.15:
                        vis_z.append(p3[2]); vis_x.append(p3[0]); vis_c.append(c_.copy())
        if not hid or not vis_z:
            continue
        vz, vc = np.array(vis_z), np.array(vis_c)
        edges = np.arange(vz.min(), vz.max() + ew['bin'], ew['bin']); mids, meds = [], []
        for a_, b_ in zip(edges[:-1], edges[1:]):
            sel = (vz >= a_) & (vz < b_)
            if sel.sum() >= 5:
                mids.append(0.5 * (a_ + b_)); meds.append(np.median(vc[sel], axis=0))
        mids, meds = np.array(mids), np.array(meds)
        # at each height, blend between the visible white just left and just right of the hidden texel, so the fill
        # carries the white's left-right shading and meets the painted white without a seam (a single colour per
        # height showed as a pale band with straight edges when the iris moved); one side only near the corners;
        # the per-height median where no sample is at that height
        vx = np.array(vis_x); nb2 = 0
        for py_, px_, z_, x_ in (hid if ew.get('fill', 'harmonic') != 'height' else []):
            near = np.abs(vz - z_) < 1.5 * ew['bin']
            col = None
            if near.sum() >= 4:
                xs, cs = vx[near], vc[near]; L, R = xs < x_, xs > x_
                sides = []
                for m_ in (L, R):
                    if m_.sum() >= 2:
                        k_ = np.argsort(np.abs(xs[m_] - x_))[:4]
                        sides.append((float(np.abs(xs[m_][k_] - x_).mean()), np.median(cs[m_][k_], axis=0)))
                if len(sides) == 2:
                    (dl, cl), (dr, cr) = sides; col = (cl * dr + cr * dl) / (dl + dr); nb2 += 1
                elif sides:
                    col = sides[0][1]
            tpx[py_, px_, :3] = col if col is not None else [np.interp(z_, mids, meds[:, k]) for k in range(3)]
        # smooth fill: harmonic relaxation of the hidden texels against the visible white around them, so the fill
        # meets the painted white exactly (no seam) and has no per-height bands
        ys_, xs_ = np.array([h_[0] for h_ in hid]), np.array([h_[1] for h_ in hid])
        y0_, y1_ = max(ys_.min() - 2, 0), min(ys_.max() + 3, Ht); x0_, x1_ = max(xs_.min() - 2, 0), min(xs_.max() + 3, Wt)
        Ub = Umask[y0_:y1_, x0_:x1_].copy(); Kb = Kmask[y0_:y1_, x0_:x1_] & ~Ub
        A_ = tpx[y0_:y1_, x0_:x1_, :3].copy(); V_ = (Ub | Kb).astype(np.float32)
        if ew.get('fill', 'harmonic') == 'height':
            for py_, px_, z_, x_ in hid: tpx[py_, px_, :3] = [np.interp(z_, mids, meds[:, k]) for k in range(3)]
        for _ in range(ew.get('relax', 900) if ew.get('fill', 'harmonic') != 'height' else 0):
            Ap = np.pad(A_ * V_[..., None], ((1, 1), (1, 1), (0, 0))); Vp = np.pad(V_, 1)
            ssum = Ap[:-2, 1:-1] + Ap[2:, 1:-1] + Ap[1:-1, :-2] + Ap[1:-1, 2:]
            nsum = Vp[:-2, 1:-1] + Vp[2:, 1:-1] + Vp[1:-1, :-2] + Vp[1:-1, 2:]
            upd = Ub & (nsum > 0)
            A_[upd] = ssum[upd] / nsum[upd][:, None]
        if ew.get('fill', 'harmonic') != 'height':           # height mode already wrote the per-height colours
            blk = tpx[y0_:y1_, x0_:x1_, :3]; blk[Ub] = A_[Ub]; tpx[y0_:y1_, x0_:x1_, :3] = blk
        fill[ci] = dict(hidden=len(hid), visible=len(vis_z), bins=len(mids), twoSided=nb2, boundary=int(Kb.sum()), irisX=round(xc, 4), ring=len(order_), ringAll=len(lv_), folds=nfold)
    # the iris disc is larger than the opening: its top and bottom sat under the lids and are painted with lid/skin
    # colours (the visible bottom edge too, a thin pink/brown band); they show when the iris moves.
    from mathutils.kdtree import KDTree as _KDe
    for ci in ew['iris_main']:
        iset = set(comps_e[ci]); vis_p, vis_c, hid = [], [], []
        for lt in me.loop_triangles:
            vs_ = list(lt.vertices)
            if not all(v in iset for v in vs_):
                continue
            U = np.array([uvE[li].uv[:] for li in lt.loops]) * [Wt, Ht]; X = Pw[vs_]
            x0, y0 = np.floor(U.min(0)).astype(int); x1, y1 = np.ceil(U.max(0)).astype(int)
            gx, gy = np.meshgrid(np.arange(max(x0, 0), min(x1, Wt - 1) + 1) + 0.5, np.arange(max(y0, 0), min(y1, Ht - 1) + 1) + 0.5)
            q = np.c_[gx.ravel(), gy.ravel()]; T_ = np.array([U[1] - U[0], U[2] - U[0]]).T
            if abs(np.linalg.det(T_)) < 1e-9:
                continue
            bc = np.linalg.solve(T_, (q - U[0]).T).T; w0 = 1 - bc.sum(1); inside = (bc >= -1e-6).all(1) & (w0 >= -1e-6)
            q, bc, w0 = q[inside], bc[inside], w0[inside]
            P3 = w0[:, None] * X[0] + bc[:, :1] * X[1] + bc[:, 1:] * X[2]
            for (px_, py_), p3 in zip(q.astype(int), P3):
                hit = treeE.ray_cast(Vector(p3) + Vector((0, -0.05, 0)), Vector((0, 1, 0)), 0.1)[2]
                c_ = tpx[py_, px_, :3]
                iris_like = c_[1] >= c_[0] - 0.02 or c_[2] >= c_[0] - 0.02  # green / navy; lid pink and lash brown are not
                if hit is not None and (face_iris[hit] or face_white[hit]):
                    if iris_like:                         # visible texels are never changed; iris-coloured ones are samples
                        vis_p.append((p3[0], 0.0, p3[2])); vis_c.append(c_.copy())
                else:
                    hid.append((py_, px_, p3[0], p3[2]))
        if not hid or not vis_p:
            continue
        # hidden bottom half: at the same normalised radius, the colour of the nearest visible angle (the outline stays
        # at the rim, the inside stays light); hidden top half keeps its painted lid shadow.
        IP = Pw[list(iset)]; xc_, zc_ = 0.5 * (IP[:, 0].min() + IP[:, 0].max()), 0.5 * (IP[:, 2].min() + IP[:, 2].max())
        ax_, az_ = 0.5 * np.ptp(IP[:, 0]), 0.5 * np.ptp(IP[:, 2])
        def _polar(x_, z_):
            u_, w_ = (x_ - xc_) / ax_, (z_ - zc_) / az_
            return float(np.hypot(u_, w_)), float(np.arctan2(w_, u_))
        NB = 48; bins_ = [[] for _ in range(NB)]; vc = np.array(vis_c)
        for i_, (x_, _, z_) in enumerate(vis_p):
            r_, a_ = _polar(x_, z_); bins_[min(NB - 1, int(r_ * NB / 1.05))].append((a_, i_))
        bins_ = [(np.array([a for a, _ in b]), np.array([i for _, i in b])) if b else None for b in bins_]
        kept = []
        for py_, px_, x_, z_ in hid:
            if z_ > zc_:
                continue
            r_, a_ = _polar(x_, z_); b0 = min(NB - 1, int(r_ * NB / 1.05)); cand_a, cand_i = [], []
            for b in (b0 - 1, b0, b0 + 1):
                if 0 <= b < NB and bins_[b] is not None:
                    cand_a.append(bins_[b][0]); cand_i.append(bins_[b][1])
            if not cand_a:
                continue
            ca, ci_ = np.concatenate(cand_a), np.concatenate(cand_i)
            da = np.abs((ca - a_ + np.pi) % (2 * np.pi) - np.pi); k_ = np.argsort(da)[:6]; w_ = 1.0 / (da[k_] + 0.02)
            tpx[py_, px_, :3] = (vc[ci_[k_]] * w_[:, None]).sum(0) / w_.sum(); kept.append((py_, px_))
        hid = [(py_, px_, 0, 0) for py_, px_ in kept]
        # soften the seam between kept and filled texels: box-mean iterations on the filled texels only
        hy = np.array([h_[0] for h_ in hid]); hx = np.array([h_[1] for h_ in hid])
        y0_, y1_, x0_, x1_ = hy.min() - 2, hy.max() + 3, hx.min() - 2, hx.max() + 3
        A_ = tpx[y0_:y1_, x0_:x1_, :3].copy(); M_ = np.zeros(A_.shape[:2], bool); M_[hy - y0_, hx - x0_] = True
        for _ in range(ew.get('iris_soften', 24)):
            P_ = np.pad(A_, ((1, 1), (1, 1), (0, 0)), mode='edge')
            S_ = sum(P_[1 + dy:P_.shape[0] - 1 + dy, 1 + dx:P_.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
            A_[M_] = S_[M_]
        tpx[y0_:y1_, x0_:x1_, :3] = A_
        fill['iris%d' % ci] = dict(hidden=len(hid), visible=len(vis_p))
    # upper-lid skin under the lash strip: hidden at rest, it carries painted lash/liner remnants that slide out when the
    # lid closes and read as a dark cut (user, 11-13). Texels behind the lash strip get the lid skin around them
    # (harmonic fill, visible skin texels as the boundary); nothing visible at rest changes.
    lf = ew.get('lid_fill')
    if lf:
        lash_set = {v for c in lf['lash'] for v in comps_e[c]}
        bmL = bmesh.new(); bmL.from_mesh(me); bmL.transform(HMw); bmL.faces.ensure_lookup_table()
        treeL = _BVHe.FromBMesh(bmL); face_lash = np.array([all(v.index in lash_set for v in f.verts) for f in bmL.faces])
        face_skin = np.array([all(v.index in skin_e for v in f.verts) for f in bmL.faces]); bmL.free()
        LU = np.zeros((Ht, Wt), bool); LK = np.zeros((Ht, Wt), bool); nlid = 0
        for lt in me.loop_triangles:
            vs_ = list(lt.vertices)
            if not all(v in skin_e for v in vs_): continue
            X = Pw[vs_]; cw_ = X.mean(0)
            if not (lf['z'][0] < cw_[2] < lf['z'][1] and lf['absx'][0] < abs(cw_[0] - 0.003) < lf['absx'][1] and cw_[1] < -0.05): continue
            U = np.array([uvE[li].uv[:] for li in lt.loops]) * [Wt, Ht]
            x0, y0 = np.floor(U.min(0)).astype(int); x1, y1 = np.ceil(U.max(0)).astype(int)
            gx, gy = np.meshgrid(np.arange(max(x0, 0), min(x1, Wt - 1) + 1) + 0.5, np.arange(max(y0, 0), min(y1, Ht - 1) + 1) + 0.5)
            q = np.c_[gx.ravel(), gy.ravel()]; T_ = np.array([U[1] - U[0], U[2] - U[0]]).T
            if abs(np.linalg.det(T_)) < 1e-9: continue
            bc = np.linalg.solve(T_, (q - U[0]).T).T; w0 = 1 - bc.sum(1); inside = (bc >= -1e-6).all(1) & (w0 >= -1e-6)
            q, bc, w0 = q[inside], bc[inside], w0[inside]
            P3 = w0[:, None] * X[0] + bc[:, :1] * X[1] + bc[:, 1:] * X[2]
            for (px_, py_), p3 in zip(q.astype(int), P3):
                hit = treeL.ray_cast(Vector(p3) + Vector((0, -0.05, 0)), Vector((0, 1, 0)), 0.1)[2]
                if hit is not None and face_lash[hit]: LU[py_, px_] = True; nlid += 1
                elif hit is not None and face_skin[hit]: LK[py_, px_] = True
        LK &= ~LU
        if LU.any():
            ys_, xs_ = np.where(LU); y0_, y1_ = max(ys_.min() - 3, 0), min(ys_.max() + 4, Ht); x0_, x1_ = max(xs_.min() - 3, 0), min(xs_.max() + 4, Wt)
            Ub, Kb = LU[y0_:y1_, x0_:x1_], LK[y0_:y1_, x0_:x1_]; A_ = tpx[y0_:y1_, x0_:x1_, :3].copy(); V_ = (Ub | Kb).astype(np.float32)
            for _ in range(lf.get('relax', 700)):
                Ap = np.pad(A_ * V_[..., None], ((1, 1), (1, 1), (0, 0))); Vp = np.pad(V_, 1)
                ssum = Ap[:-2, 1:-1] + Ap[2:, 1:-1] + Ap[1:-1, :-2] + Ap[1:-1, 2:]; nsum = Vp[:-2, 1:-1] + Vp[2:, 1:-1] + Vp[1:-1, :-2] + Vp[1:-1, 2:]
                upd = Ub & (nsum > 0); A_[upd] = ssum[upd] / nsum[upd][:, None]
            blk = tpx[y0_:y1_, x0_:x1_, :3]; blk[Ub] = A_[Ub]; tpx[y0_:y1_, x0_:x1_, :3] = blk
        fill['lid'] = dict(hidden=int(LU.sum()), boundary=int(LK.sum()))
    _ni = bpy.data.images.new('head-basecolor-eyewhite-tmp', Wt, Ht, alpha=False)
    _ni.pixels.foreach_set(tpx.ravel()); _ni.filepath_raw = ew['out']; _ni.file_format = 'PNG'; _ni.save()
    bpy.data.images.remove(_ni)
    img_new = bpy.data.images.load(ew['out']); img_new.pack()      # repacking the old datablock kept the old pixels
    for m_ in me.materials:
        for n_ in (m_.node_tree.nodes if m_ and m_.node_tree else []):
            if n_.type == 'TEX_IMAGE' and n_.image == img:
                n_.image = img_new
    img = img_new
    report['eyeWhiteFill'] = fill

# =========================== 2. hair ======================================================
with bpy.data.libraries.load(cfg['assembly_blend'], link=False) as (src, dst):
    dst.objects = ['Hair']
hair = dst.objects[0]
bpy.data.collections[cfg['collection']].objects.link(hair)
hair.data = hair.data.copy()
hair.parent = None
hair.matrix_world = Matrix.Identity(4)
if cfg.get('hair_affine'):
    # another head than the profile's: its hair sits by this project's own assembly transform, then the head frame
    _Th = np.load(cfg['hair_affine']); _Sh = float(np.cbrt(np.linalg.det(_Th[:3])))
    hair.data.transform((Mfr if FR else Matrix.Identity(4)) @ Matrix.Translation(Vector(_Th[3].tolist())) @ Matrix.Scale(_Sh, 4))
else:
    hair.data.transform(Matrix.Translation(TV) @ Matrix.Scale(S, 4))
for g in list(hair.vertex_groups):
    hair.vertex_groups.remove(g)
for mod in list(hair.modifiers):
    hair.modifiers.remove(mod)
hair.parent = rig
hair.matrix_parent_inverse = RW.inverted()
hair['charakitRole'] = 'hair'
# The appended MToon node tree arrives without its MToon settings; rebuild a plain material on the
# same 4K base colour so apply_mtoon converts it like every other part.
from bpy_extras.node_shader_utils import PrincipledBSDFWrapper
hair_img = None
for slot in hair.material_slots:
    t = PrincipledBSDFWrapper(slot.material).base_color_texture
    if t and t.image:
        hair_img = t.image
if hair_img is None or not hair_img.has_data or tuple(hair_img.size) != (4096, 4096):
    # an MToon node tree hides its base colour from the wrapper: take the 4K image node itself (packed in the assembly)
    hair_img = None
    for slot in hair.material_slots:
        for n in (slot.material.node_tree.nodes if slot.material and slot.material.use_nodes else []):
            if n.type == 'TEX_IMAGE' and n.image and hair_img is None:
                if not n.image.has_data:
                    n.image.pixels[0]                    # an appended packed image loads on first pixel read
                if n.image.has_data and tuple(n.image.size) == (4096, 4096):
                    hair_img = n.image
if hair_img is None:
    hair_img = bpy.data.images.load(cfg['hair_texture'])
if cfg.get('hair_texture_clean'):
    # same atlas with the dark streaks/blotches between strands refilled (work/hair/)
    hair_img = bpy.data.images.load(cfg['hair_texture_clean'])
    hair_img.name = 'hair-basecolor-clean.jpg'
hair_img.pack()
hm = bpy.data.materials.new('Material_hair_mtoon')
hm.use_nodes = True
nt = hm.node_tree
bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
tex = nt.nodes.new('ShaderNodeTexImage')
tex.image = hair_img
nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
hair.data.materials.clear()
hair.data.materials.append(hm)
for poly in hair.data.polygons:
    poly.material_index = 0
report['hairTexture'] = hair_img.name
am = hair.modifiers.new('Armature', 'ARMATURE')
am.object = rig
am.use_vertex_groups = True

# --- hair fragments that Tripo left inside the face around the mouth and nose: removed, the open mouth
# cavity needs that space and they showed as grey patches inside the mouth.
# A head other than the profile's takes the box from its own mouth (work/measure/measure.json): the profile's box sat
# in front of 人物2's mouth pocket, and hair strands inside the pocket showed through the open mouth (11-25).
_ms = Path(cfg['output_blend']).parent / 'measure' / 'measure.json'
if cfg.get('hair_affine') and _ms.is_file():
    _L = (json.loads(_ms.read_text()).get('new_head') or {}).get('landmarks') or {}
    if all(k_ in _L for k_ in ('mouth', 'mouthR', 'mouthL', 'chin', 'noseTip')):
        # landmarks are in the world; this build runs in the head frame (lengths / s)
        _fs, _ft = (FR['s'], FR['t']) if FR else (1.0, [0.0, 0.0, 0.0])
        _L = {k_: [(v_[i_] - _ft[i_]) / _fs for i_ in range(3)] for k_, v_ in _L.items()}; _u = 1.0 / _fs
        _w = abs(_L['mouthL'][0] - _L['mouthR'][0]); _m = _L['mouth']
        cfg['hair_cavity_box'] = dict(x=_m[0], half_x=1.0 * _w, z=[_L['chin'][2], _L['noseTip'][2]], y_min=_m[1] - 0.03 * _u, y_max=_m[1] + 0.08 * _u,
                                      hard=dict(half_x=0.75 * _w, z=[_m[2] - 0.02 * _u, _m[2] + 0.015 * _u], y=[_m[1] - 0.004 * _u, _m[1] + 0.06 * _u]), parity=True)
        report['hairCavityBox'] = 'this head'
if cfg.get('hair_cavity_box'):
    from mathutils.bvhtree import BVHTree as _BVH
    hb_ = bmesh.new(); hb_.from_mesh(head.data); hb_.transform(head.matrix_world); t_face = _BVH.FromBMesh(hb_)
    bx = cfg['hair_cavity_box']
    hbm = bmesh.new(); hbm.from_mesh(hair.data); hbm.verts.ensure_lookup_table()
    gone = []
    for v in hbm.verts:
        pw = hair.matrix_world @ v.co
        if not (abs(pw.x - bx['x']) < bx['half_x'] and bx['z'][0] < pw.z < bx['z'][1] and bx['y_min'] < pw.y < bx['y_max']):
            continue
        hard = bx.get('hard')
        if hard and abs(pw.x - bx['x']) < hard['half_x'] and hard['z'][0] < pw.z < hard['z'][1] and hard['y'][0] < pw.y < hard['y'][1]:
            gone.append(v)                      # inside the mouth cavity volume
            continue
        hit = t_face.ray_cast(pw + Vector((0, -1e-5, 0)), Vector((0, -1, 0)), 0.3)
        if hit[0] is not None and hit[1].y < 0:
            gone.append(v)
        elif bx.get('parity'):                  # a closed head: inside it when a ray crosses its surface an odd number of times
            n_, o_ = 0, pw.copy()
            for _ in range(24):
                h_ = t_face.ray_cast(o_, Vector((0, -1, 0)), 0.5)
                if h_[0] is None: break
                n_ += 1; o_ = h_[0] + Vector((0, -1e-5, 0))
            if n_ % 2 == 1:
                gone.append(v)
    bmesh.ops.delete(hbm, geom=gone, context='VERTS')
    hbm.to_mesh(hair.data); hair.data.update()
    report['hairCavityRemoved'] = len(gone)

# =========================== 2b. closed skull =============================================
# The Tripo head is a face mask: the back and top of the skull are open and show through gaps in the
# hair. Add a round cranium: an ellipsoid fitted to the mask's cranium and the inside of the back hair,
# kept just inside the face where the mask exists and just under the hair elsewhere. Hair colour on
# top, skin colour towards the nape (vertical gradient texture).
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from mathutils import geometry as mgeo


def bvh(obj):
    b = bmesh.new()
    b.from_mesh(obj.data)
    b.transform(obj.matrix_world)
    b.faces.ensure_lookup_table()
    return BVHTree.FromBMesh(b), b


_img_cache = {}


def img_array(img):
    if img.name not in _img_cache:
        w, hgt = img.size
        px = np.empty(w * hgt * 4, np.float32)
        img.pixels.foreach_get(px)
        _img_cache[img.name] = px.reshape(hgt, w, 4)
    return _img_cache[img.name]


def face_image(obj, poly):
    mat = obj.data.materials[poly.material_index]
    return next(n_.image for n_ in mat.node_tree.nodes if n_.type == 'TEX_IMAGE' and n_.image and n_.image.size[0] >= 4)


def color_at(obj, bmw, face_index, point, blur=3):
    """Texture colour of obj's surface at a world point on face face_index (bmw: world-space bmesh)."""
    f = bmw.faces[face_index]
    poly = obj.data.polygons[face_index]
    uvl = obj.data.uv_layers.active.data
    co = [l.vert.co for l in f.loops]
    uv = [Vector(uvl[li].uv) for li in poly.loop_indices]
    best = None
    for k in range(1, len(co) - 1):
        w = mgeo.barycentric_transform(point, co[0], co[k], co[k + 1], Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        err = sum(abs(min(0.0, x)) for x in w)
        if best is None or err < best[0]:
            best = (err, w, uv[0], uv[k], uv[k + 1])
    _, w, a_, b_, c_ = best
    u = a_ * w.x + b_ * w.y + c_ * w.z
    arr = img_array(face_image(obj, poly))
    hgt, wd = arr.shape[:2]
    x = int(np.clip((u.x % 1) * wd, 0, wd - 1))
    y = int(np.clip((u.y % 1) * hgt, 0, hgt - 1))
    return arr[max(0, y - blur):y + blur + 1, max(0, x - blur):x + blur + 1, :3].reshape(-1, 3).mean(0)


if cfg.get('skull'):
    sk_cfg = cfg['skull']
    t_head, b_head = bvh(head)
    t_hair, b_hair = bvh(hair)
    # ellipsoid fit: cranium part of the mask skin + points just inside the back hair
    cx = sk_cfg['center'][0]
    isl_seen, best_isl = set(), []
    for f in b_head.faces:
        if f.index in isl_seen:
            continue
        st, comp = [f], []
        isl_seen.add(f.index)
        while st:
            q = st.pop()
            comp.append(q)
            for e in q.edges:
                for g in e.link_faces:
                    if g.index not in isl_seen:
                        isl_seen.add(g.index)
                        st.append(g)
        if len(comp) > len(best_isl):
            best_isl = comp
    pts = [v.co.copy() for v in {v for f in best_isl for v in f.verts} if v.co.z > sk_cfg['fit_mask_z']]
    c_guess = Vector(sk_cfg['center'])
    for az in (range(-70, 71, 10) if sk_cfg.get('fit_hair', True) else ()):
        for el in range(-10, 61, 10):
            d = Vector((math.sin(math.radians(az)) * math.cos(math.radians(el)), math.cos(math.radians(az)) * math.cos(math.radians(el)), math.sin(math.radians(el))))
            if t_head.ray_cast(c_guess, d, 0.5)[0] is not None:
                continue
            r = t_hair.ray_cast(c_guess, d, 0.5)
            if r[0] is not None:
                pts.append(r[0] - d * sk_cfg.get('fit_hair_inset', 0.012))
    kr = sk_cfg.get('fit_ry_ratio')
    if kr:
        # depth tied to width (the back of the cranium is missing from the mask)
        X = np.array([[(q.x - cx) ** 2 + q.y ** 2 / kr ** 2, q.z ** 2, q.y, q.z] for q in pts])
        coef, *_ = np.linalg.lstsq(X, np.ones(len(pts)), rcond=None)
        A_, C_, D_, E_ = coef
        B_ = A_ / kr ** 2
    else:
        X = np.array([[(q.x - cx) ** 2, q.y ** 2, q.z ** 2, q.y, q.z] for q in pts])
        coef, *_ = np.linalg.lstsq(X, np.ones(len(pts)), rcond=None)
        A_, B_, C_, D_, E_ = coef
    cy, cz = -D_ / (2 * B_), -E_ / (2 * C_)
    kk = 1 + B_ * cy * cy + C_ * cz * cz
    ea, eb, ec = math.sqrt(kk / A_), math.sqrt(kk / B_), math.sqrt(kk / C_)
    c0 = Vector((cx, cy, cz))
    nf = sk_cfg.get('nape_fit')
    if nf:
        # Below and behind the ears the mask (and the back end of the jaw strip) hangs as two flat flaps
        # under the round cranium; they show behind the jaw when the head tilts up. Mask vertices there
        # that lie outside the ellipsoid move onto it (radially from its centre), fading in behind the jaw
        # angle and below the ears. The ears stay. Only positions change (vertex ids are used later).
        def s01(t):
            t = min(1.0, max(0.0, t))
            return t * t * (3 - 2 * t)
        ear = nf['ear']
        HMw = head.matrix_world
        HMwi = HMw.inverted()
        isl_ids = {v.index for f in best_isl for v in f.verts}
        moved, dmax = 0, 0.0
        for vi in isl_ids:
            v = head.data.vertices[vi]
            p = HMw @ v.co
            w = s01((p.y - nf['y'][0]) / (nf['y'][1] - nf['y'][0])) * s01((nf['z'][0] - p.z) / (nf['z'][0] - nf['z'][1]))
            fe = ear['feather']
            e_ = (s01((abs(p.x - cx) - ear['x_min'] + fe) / fe) * s01((p.y - ear['y'][0] + fe) / fe)
                  * s01((ear['y'][1] - p.y + fe) / fe) * s01((p.z - ear['z_min'] + fe) / fe))
            w *= 1 - e_
            if w <= 0:
                continue
            q = p - c0
            s = math.sqrt((q.x / ea) ** 2 + (q.y / eb) ** 2 + (q.z / ec) ** 2)
            if s <= 1:
                continue
            tgt = c0 + q / s + q.normalized() * nf.get('out', 0.001)
            np_ = p.lerp(tgt, w)
            dmax = max(dmax, (np_ - p).length)
            v.co = HMwi @ np_
            moved += 1
        head.data.update()
        isl_faces = [f.index for f in best_isl]
        t_head, b_head = bvh(head)
        best_isl = [b_head.faces[i] for i in isl_faces]
        report['napeFit'] = dict(moved=moved, maxMoveMm=round(dmax * 1000, 1))
    sb = bmesh.new()
    bmesh.ops.create_uvsphere(sb, u_segments=sk_cfg.get('segments', 64), v_segments=sk_cfg.get('rings', 40), radius=1.0)
    sb.verts.ensure_lookup_table()
    n = len(sb.verts)
    dirs = [v.co.normalized() for v in sb.verts]
    rt = np.array([1.0 / math.sqrt((d.x / ea) ** 2 + (d.y / eb) ** 2 + (d.z / ec) ** 2) for d in dirs])
    rmax = np.full(n, 1.0)
    on_mask = np.zeros(n, bool)
    for i, d in enumerate(dirs):
        h = t_head.ray_cast(c0, d, 0.5)
        if h[0] is not None:
            rmax[i] = min(rmax[i], h[3] - sk_cfg.get('inside_face', 0.003))
            on_mask[i] = True
        r = t_hair.ray_cast(c0, d, 0.5)
        if r[0] is not None:
            rmax[i] = min(rmax[i], r[3] - sk_cfg.get('under_hair', 0.006))
    nb = [[e.other_vert(v).index for e in v.link_edges] for v in sb.verts]
    # mask directions are fixed (just inside the mask); the open part relaxes towards the ellipsoid
    # while meeting the mask edge, so no rim is left standing (screened smoothing), always under the hair
    rr = np.where(on_mask, rmax, np.minimum(rt, rmax))
    alpha = sk_cfg.get('blend', 0.85)
    for _ in range(sk_cfg.get('smooth', 40)):
        nbm = np.array([np.mean(rr[nb[i]]) for i in range(n)])
        rr = np.where(on_mask, rmax, np.minimum(alpha * nbm + (1 - alpha) * rt, rmax))
    rr = np.maximum(rr, sk_cfg.get('r_min', 0.04))
    for i, v in enumerate(sb.verts):
        v.co = c0 + dirs[i] * float(rr[i])
    if sk_cfg.get('eye_clear'):
        # the radial fit can leave the skull in front of the eye whites at the eye corners, where it shows
        # through the opening; any skull point seen from the front there moves back until a white covers it
        ec_ = sk_cfg['eye_clear']; moved = 0
        sb.faces.ensure_lookup_table()
        t_clear = t_head
        if ec_.get('ignore_iris') and cfg.get('eye_white_fill'):
            # the iris moves (gaze): skull behind it must be hidden by the white or the lids, not by the iris
            _ce = json.loads(Path(cfg['eye_white_fill']['components']).read_text())
            _iris_v = {v for c in cfg['eye_white_fill']['iris'] for v in _ce[c]}
            _bc = bmesh.new(); _bc.from_mesh(head.data); _bc.transform(head.matrix_world); _bc.verts.ensure_lookup_table()
            bmesh.ops.delete(_bc, geom=[f for f in _bc.faces if all(v.index in _iris_v for v in f.verts)], context='FACES_ONLY')
            t_clear = BVHTree.FromBMesh(_bc); _bc.free()
        def _seen(f):                                   # any sample of the face visible from the front
            cs = [v.co for v in f.verts]; ctr = sum(cs, Vector()) / len(cs)
            for q in [ctr] + [(ctr + c) * 0.5 for c in cs]:
                if t_clear.ray_cast(q + Vector((0, -0.0002, 0)), Vector((0, -1, 0)), 0.3)[0] is None:
                    return True
            return False
        for _ in range(int(ec_.get('max', 0.02) / 0.001)):
            push = set()
            for f in sb.faces:
                ctr = f.calc_center_median()
                if ec_['x'][0] < abs(ctr.x - cx) < ec_['x'][1] and ec_['z'][0] < ctr.z < ec_['z'][1] and ctr.y < c0.y and _seen(f):
                    push |= set(f.verts)
            if not push:
                break
            for v in push:
                v.co.y += 0.001
            moved += len(push)
        report['skullEyeClear'] = moved
    if sk_cfg.get('mouth_pocket'):
        mp = sk_cfg['mouth_pocket']
        for v in sb.verts:
            rx, rz = (v.co.x - mp['x']) / mp['rx'], (v.co.z - mp['z']) / mp['rz']
            r2 = rx * rx + rz * rz
            if r2 < 1 and v.co.y < mp['y_front']:
                v.co.y += (1 - r2) ** 2 * mp['depth']
    huv = hair.data.uv_layers.active.data
    hair_uvs = [huv[li].uv[:] for poly in hair.data.polygons for li in poly.loop_indices
                if (hair.matrix_world @ hair.data.vertices[hair.data.loops[li].vertex_index].co).z > sk_cfg['hair_sample_z']]
    harr = img_array(hair_img)
    hu = np.asarray(hair_uvs)
    hair_rgb = np.median(harr[np.clip((hu[:, 1] % 1) * harr.shape[0], 0, harr.shape[0] - 1).astype(int),
                              np.clip((hu[:, 0] % 1) * harr.shape[1], 0, harr.shape[1] - 1).astype(int), :3], axis=0) * sk_cfg.get('hair_shade', 0.85)
    # skin: head texture around the back of the jaw
    skin_samples = []
    for f in best_isl:
        cw = f.calc_center_median()
        if sk_cfg['skin_sample_box'][0] < cw.z < sk_cfg['skin_sample_box'][1] and cw.y > sk_cfg['skin_sample_box'][2]:
            skin_samples.append(color_at(head, b_head, f.index, cw, blur=1))
    skin_rgb = np.median(np.array(skin_samples), axis=0) if skin_samples else hair_rgb
    if sk_cfg.get('skin_tone') == 'face':
        skin_rgb = face_tone
    gw, gh = 4, 256
    zlo = min(v.co.z for v in sb.verts) - 0.005
    zhi = max(v.co.z for v in sb.verts) + 0.005
    za, zb = sk_cfg['nape']
    grad = np.zeros((gh, gw, 4), np.float32)
    for row in range(gh):
        z = zlo + (zhi - zlo) * (row + 0.5) / gh
        t = min(1.0, max(0.0, (z - za) / (zb - za)))
        t = t * t * (3 - 2 * t)
        grad[row, :, :3] = skin_rgb * (1 - t) + hair_rgb * t
        grad[row, :, 3] = 1
    gimg = bpy.data.images.new('scalp-gradient.png', gw, gh, alpha=False)
    gimg.pixels.foreach_set(grad.ravel())
    gimg.filepath_raw = str(_work_dir('hair') / 'scalp-gradient.png')
    gimg.file_format = 'PNG'
    gimg.save()
    gimg.pack()
    sm = bpy.data.materials.new('Material_scalp')
    sm.use_nodes = True
    snt = sm.node_tree
    sbsdf = next(n_ for n_ in snt.nodes if n_.type == 'BSDF_PRINCIPLED')
    sbsdf.inputs['Base Color'].default_value = (1, 1, 1, 1)      # the VRM add-on exports these as factors
    sbsdf.inputs['Emission Color'].default_value = (0, 0, 0, 1)
    stex = snt.nodes.new('ShaderNodeTexImage')
    stex.image = gimg
    snt.links.new(stex.outputs['Color'], sbsdf.inputs['Base Color'])
    head.data.materials.append(sm)
    mat_index = len(head.data.materials) - 1
    hb2 = bmesh.new()
    hb2.from_mesh(head.data)
    uvl = hb2.loops.layers.uv.active
    dfl = hb2.verts.layers.deform.verify()
    HMi2 = head.matrix_world.inverted()
    vmap = {}
    for v in sb.verts:
        nv = hb2.verts.new(HMi2 @ v.co)
        nv[dfl][head_group] = 1.0
        vmap[v] = nv
    for f in sb.faces:
        nf = hb2.faces.new([vmap[v] for v in f.verts])
        nf.material_index = mat_index
        nf.smooth = True
        for l in nf.loops:
            zw = (head.matrix_world @ l.vert.co).z
            l[uvl].uv = (0.5, min(1.0, max(0.0, (zw - zlo) / (zhi - zlo))))
    hb2.normal_update()
    hb2.to_mesh(head.data)
    head.data.update()
    report['skull'] = dict(fitPoints=len(pts), verts=n, ellipsoid=dict(center=[round(x, 4) for x in c0], radii=[round(ea, 4), round(eb, 4), round(ec, 4)]),
                           rMin=round(float(rr.min()), 4), rMax=round(float(rr.max()), 4),
                           hairRGB=[round(float(x), 3) for x in hair_rgb], skinRGB=[round(float(x), 3) for x in skin_rgb])

# =========================== 2d3. paint by mesh piece (11-19 denim) ========================
# The 4K retexture projects front/back pictures onto each texture group, so small or hidden surfaces next to skin
# (hem and cuff undersides, the hood opening, the bead necklace) pick up skin colour, and a colour test cannot tell
# those from real skin (user: skin colour along the clothing edges, the necklace smeared). Decide by mesh piece
# instead: skin pieces get the skin tone, cloth pieces lose every skin-coloured face to the surrounding fabric colour,
# the necklace beads are painted metal. Pieces are picked by the face nearest to a point (head-frame coordinates).
rp = cfg.get('region_paint')
def _rp_box(x, r, ax):
    pad = [(r + 1, r) if i == ax else (0, 0) for i in range(x.ndim)]
    c = np.cumsum(np.pad(x, pad, mode='edge'), axis=ax); n_ = x.shape[ax]
    return (np.take(c, range(2 * r + 1, 2 * r + 1 + n_), axis=ax) - np.take(c, range(0, n_), axis=ax)) / (2 * r + 1)
def _rp_blur(x, sig):
    r = max(1, int(round(sig * 0.87)))
    for _ in range(3): x = _rp_box(_rp_box(x, r, 0), r, 1)
    return x
if rp:
    body_o = bpy.data.objects['Body']; BWm = body_o.matrix_world; BR = BWm.to_3x3()
    _bm = bmesh.new(); _bm.from_mesh(body_o.data); _bm.faces.ensure_lookup_table(); _uv = _bm.loops.layers.uv.active
    _isl = [-1] * len(_bm.faces); _n = 0
    for f_ in _bm.faces:
        if _isl[f_.index] >= 0: continue
        st_ = [f_]; _isl[f_.index] = _n
        while st_:
            g_ = st_.pop()
            for e_ in g_.edges:
                for h_ in e_.link_faces:
                    if _isl[h_.index] < 0: _isl[h_.index] = _n; st_.append(h_)
        _n += 1
    _ctr = [BWm @ f_.calc_center_median() for f_ in _bm.faces]
    _members = {}
    for f_ in _bm.faces: _members.setdefault(_isl[f_.index], []).append(f_)
    def _pick(pt):
        pt = Vector(pt); i_ = min(range(len(_ctr)), key=lambda k: (_ctr[k] - pt).length_squared); return _isl[i_]
    _mats = [m.name if m else '' for m in body_o.data.materials]
    _imgs = {}
    def _img_of(mi):
        if mi not in _imgs:
            p0 = next(p_ for p_ in body_o.data.polygons if p_.material_index == mi)
            im = face_image(body_o, p0); _imgs[mi] = dict(img=im, arr=img_array(im).copy())
        return _imgs[mi]
    def _fc(f_):
        a_ = _img_of(f_.material_index)['arr']; H_, W_ = a_.shape[:2]
        u_ = np.mean([l[_uv].uv.x for l in f_.loops]); v_ = np.mean([l[_uv].uv.y for l in f_.loops])
        x_ = int(np.clip((u_ % 1) * W_, 0, W_ - 1)); y_ = int(np.clip((v_ % 1) * H_, 0, H_ - 1))
        return a_[max(0, y_ - 2):y_ + 3, max(0, x_ - 2):x_ + 3, :3].reshape(-1, 3).mean(0)
    def _mask(faces, shape, grow=0.0):
        H_, W_ = shape; M_ = np.zeros((H_, W_), bool)
        for f_ in faces:
            q = [(l[_uv].uv.x % 1 * W_, l[_uv].uv.y % 1 * H_) for l in f_.loops]
            for k in range(1, len(q) - 1):
                (x0, y0), (x1, y1), (x2, y2) = q[0], q[k], q[k + 1]
                xa, xb = int(max(0, np.floor(min(x0, x1, x2)) - 1)), int(min(W_ - 1, np.ceil(max(x0, x1, x2)) + 1))
                ya, yb = int(max(0, np.floor(min(y0, y1, y2)) - 1)), int(min(H_ - 1, np.ceil(max(y0, y1, y2)) + 1))
                gx, gy = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
                den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if abs(den) < 1e-12: continue
                a_ = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den; b_ = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
                M_[ya:yb + 1, xa:xb + 1] |= (a_ >= -grow) & (b_ >= -grow) & (a_ + b_ <= 1 + grow)
        return M_
    rep_ = {}
    # 1. cloth pieces: every skin-coloured face takes the median colour of the nearest clean faces of the same piece
    for cs in rp.get('cloth', []):
        ii = _pick(cs['point']); faces = [f_ for f_ in _members[ii] if abs(_ctr[f_.index].x) <= cs.get('abs_x', 9.0)]   # cuffs are left to cuff_lining
        warm = cs.get('warm', 0.03); keep_dark = cs.get('keep_dark_below', 0.0)
        def _bad(c_): return c_[0] - c_[2] > warm and c_.mean() >= keep_dark
        cols = {f_.index: _fc(f_) for f_ in faces}
        # the rest of the garment: other mesh pieces of the same material and colour next to it (sleeves, sleeve linings,
        # collar). The T-shirt's sleeve linings are pieces of their own; they kept skin-coloured texels from the arm
        # inside them, which showed when the arm went up (人物2, 11-26)
        sib_n = 0
        if cs.get('siblings', True) and faces:
            _mset = {f_.material_index for f_ in faces}; _med = np.median(np.array([cols[f_.index] for f_ in faces]), 0)
            _P0 = np.array([_ctr[f_.index][:] for f_ in faces]); _lo0, _hi0 = _P0.min(0) - 0.03, _P0.max(0) + 0.03
            for jj, mem in _members.items():
                if jj == ii or len(mem) < 20 or mem[0].material_index not in _mset: continue
                fs_ = [f_ for f_ in mem if abs(_ctr[f_.index].x) <= cs.get('abs_x', 9.0)]
                if len(fs_) < 20: continue
                P_ = np.array([_ctr[f_.index][:] for f_ in fs_])
                if (P_.max(0) < _lo0).any() or (P_.min(0) > _hi0).any(): continue
                c_ = {f_.index: _fc(f_) for f_ in fs_}; cm_ = np.median(np.array(list(c_.values())), 0)
                if np.linalg.norm(cm_ - _med) > cs.get('sibling_colour', 0.12) or np.mean([_bad(v) for v in c_.values()]) > 0.5: continue
                faces = faces + fs_; cols.update(c_); sib_n += 1
        bad = [f_ for f_ in faces if _bad(cols[f_.index])]; good = [f_ for f_ in faces if not _bad(cols[f_.index])]
        if bad and good:
            from mathutils.kdtree import KDTree as _KD
            kd_ = _KD(len(good))
            for i_, f_ in enumerate(good): kd_.insert(_ctr[f_.index], i_)
            kd_.balance()
            by_mi = {}
            for f_ in bad:
                nb = kd_.find_n(_ctr[f_.index], cs.get('neighbours', 10))
                c_ = np.median(np.array([cols[good[i_].index] for _, i_, _ in nb]), 0) * cs.get('shade', 0.92)
                by_mi.setdefault(f_.material_index, []).append((f_, c_))
            for mi, items in by_mi.items():
                d_ = _img_of(mi)
                for f_, c_ in items:
                    m_ = _mask([f_], d_['arr'].shape[:2], 0.12); d_['arr'][m_, :3] = c_
        # texel level: a face is judged by the colour at its centre, but its UV triangle can run past the painted area
        # into unpainted light texels (人物2, 11-25: white triangles on the T-shirt hem once it lifted). Inside the
        # piece's own triangles, skin-coloured texels, and on faces neither picture saw (occluded or facing away from
        # the front and the back; a print on the chest stays) texels far lighter than the piece, take the colour of the
        # clean texels around them.
        n_tx = 0
        if cs.get('texels', True) and good:
            Lp = float(np.median([cols[f_.index].mean() for f_ in good]))
            if '_rp_tree' not in globals():
                _bmt = _bm.copy(); _bmt.transform(BWm); _rp_tree = BVHTree.FromBMesh(_bmt); _bmt.free()
            def _seen(f_):
                n_ = (BR @ f_.normal).normalized(); c_ = _ctr[f_.index]
                for d_ in (Vector((0, -1, 0)), Vector((0, 1, 0))):
                    if n_.dot(d_) > 0.05 and _rp_tree.ray_cast(c_ + d_ * 0.0005, d_, 2.0)[0] is None: return True
                return False
            # faces at the piece's outline in the front or back picture: the mesh outline runs a little past the drawn
            # one, so they took the picture's white background (人物2, 11-25: white spots at the T-shirt hem)
            _pv = list(dict.fromkeys(v_ for f_ in faces for v_ in f_.verts)); _pidx = {v_.index: i_ for i_, v_ in enumerate(_pv)}
            _ptree = BVHTree.FromPolygons([BWm @ v_.co for v_ in _pv], [[_pidx[v_.index] for v_ in f_.verts] for f_ in faces])
            _off = cs.get('outline_mm', 20) / 1000.0 / (FR['s'] if FR else 1.0)      # world mm; this step runs in the head frame
            def _outline(f_):
                # next to it, in the picture's direction, the first surface of the piece is missing or on another layer
                # (the back hem seen below the front hem)
                c_ = _ctr[f_.index]; n_ = (BR @ f_.normal).normalized()
                for sy_ in ((-1.0,) if n_.y <= 0 else (1.0,)):
                    for dx_, dz_ in ((_off, 0), (-_off, 0), (0, _off), (0, -_off)):
                        h_ = _ptree.ray_cast(Vector((c_.x + dx_, c_.y + sy_ * 10.0, c_.z + dz_)), Vector((0, -sy_, 0)), 20.0)
                        if h_[0] is None or abs(h_[0].y - c_.y) > _off: return True
                return False
            edge_f = {f_ for f_ in faces if not _seen(f_) or _outline(f_)}
            for mi in {f_.material_index for f_ in faces}:
                d_ = _img_of(mi); a_ = d_['arr']; M_ = _mask([f_ for f_ in faces if f_.material_index == mi], a_.shape[:2], 0.0)
                E_ = _mask([f_ for f_ in edge_f if f_.material_index == mi], a_.shape[:2], 0.0)
                c3 = a_[..., :3]
                badm = M_ & (((c3[..., 0] - c3[..., 2] > warm) & (c3.mean(-1) >= keep_dark)) | (E_ & (c3.mean(-1) > Lp + cs.get('light_over', 0.35))))
                if not badm.any(): continue
                n_tx += int(badm.sum())
                # whole UV islands can be unpainted, with no clean texel near: the search widens, and what is still
                # left takes the piece's median colour
                left_ = badm.copy()
                for sig_ in (cs.get('texel_sigma', 6), 24, 96):
                    okm = (M_ & ~left_).astype(np.float32)
                    den_ = _rp_blur(okm, sig_); got_ = left_ & (den_ > 0.02)
                    for ch in range(3):
                        num_ = _rp_blur(c3[..., ch] * okm, sig_)
                        a_[..., ch] = np.where(got_, num_ / np.maximum(den_, 1e-4), a_[..., ch])
                    left_ &= ~got_
                    if not left_.any(): break
                if left_.any():
                    a_[left_, :3] = np.median(np.array([cols[f_.index] for f_ in good]), 0)
        # faces none of the four pictures saw (inner thighs, the crotch, under the arms: turned away from the front and
        # back pictures and hidden from the sides by the other leg or the body) come out darker than the piece around
        # them (denim inner thigh 0.57 against 0.71 in front, 人物2 0.26 against 0.32; user, 11-25: inner thighs too
        # dark). Their texels take the colour of the seen part of the piece nearby, channel by channel (the painted
        # shadow is also more saturated: brightness alone turned it violet on the lavender denim); the weave is kept.
        n_lift = 0; hid_f = []
        lh = cs.get('lift_hidden', {})
        if cs.get('texels', True) and good and lh is not False:
            lh = dict(dict(facing=0.3, sigma=12, ref_sigma=64, gain=(0.25, 3.0), darker=0.97, warmer=0.05), **(lh if isinstance(lh, dict) else {}))
            _dirs4 = (Vector((0, -1, 0)), Vector((0, 1, 0)), Vector((-1, 0, 0)), Vector((1, 0, 0)))
            def _seen4(f_):
                n_ = (BR @ f_.normal).normalized(); c_ = _ctr[f_.index]
                for d_ in _dirs4:
                    if n_.dot(d_) > lh['facing'] and _rp_tree.ray_cast(c_ + d_ * 0.0005, d_, 2.0)[0] is None: return True
                return False
            hid_f = [f_ for f_ in faces if not _seen4(f_)]
            _lw = np.array([0.299, 0.587, 0.114], np.float32)
            for mi in {f_.material_index for f_ in hid_f}:
                d_ = _img_of(mi); a_ = d_['arr']; sh_ = a_.shape[:2]
                M_ = _mask([f_ for f_ in faces if f_.material_index == mi], sh_, 0.0)
                Hm = M_ & _mask([f_ for f_ in hid_f if f_.material_index == mi], sh_, 0.0)
                Sm = (M_ & ~Hm).astype(np.float32); Mf = M_.astype(np.float32)
                if not Hm.any() or not Sm.any(): continue
                den_ = _rp_blur(Sm, lh['ref_sigma']); dl_ = np.maximum(_rp_blur(Mf, lh['sigma']), 1e-4)
                med_ = np.median(a_[..., :3][Sm > 0], 0)
                ref_ = np.stack([np.where(den_ > 0.02, _rp_blur(a_[..., ch] * Sm, lh['ref_sigma']) / np.maximum(den_, 1e-4), med_[ch]) for ch in range(3)], -1)
                loc_ = np.stack([_rp_blur(a_[..., ch] * Mf, lh['sigma']) / dl_ for ch in range(3)], -1)
                # only where the hidden part is darker than the seen cloth around it, or warmer (skin from the arm or leg
                # inside it: 人物2's sleeve lining); feathered over a few texels
                rL_, lL_ = ref_ @ _lw, loc_ @ _lw
                wd_ = np.clip((lh['darker'] * rL_ - lL_) / np.maximum(0.1 * rL_, 1e-3), 0, 1)
                wd_ = np.maximum(wd_, np.clip(((loc_[..., 0] - loc_[..., 2]) - (ref_[..., 0] - ref_[..., 2]) - lh['warmer']) / 0.06, 0, 1))
                w_ = (np.clip(2.0 * _rp_blur(Hm.astype(np.float32), 3), 0, 1) * Mf * wd_)[..., None]
                g_ = 1.0 + (np.clip(ref_ / np.maximum(loc_, 1e-3), *lh['gain']) - 1.0) * w_
                n_lift += int((Hm & (w_[..., 0] > 0.05)).sum())
                a_[..., :3] = np.clip(a_[..., :3] * g_, 0, 1)
        rep_['cloth_' + cs['name']] = dict(island=ii, faces=len(faces), repainted=len(bad), texelsFilled=n_tx, unseenFaces=len(edge_f) if cs.get('texels', True) and good else 0,
                                           hiddenFaces=len(hid_f), texelsLifted=n_lift, siblingPieces=sib_n)
    from mathutils.kdtree import KDTree as _KD2
    # 1b. a band of one colour inside a cloth piece (the belt): per direction, the height band of its colour is
    # found from the faces that have it; faces inside the band take the median colour of those faces nearby
    for bs in rp.get('band', []):
        ii = _pick(bs['point']); faces = _members[ii]; ax_ = bs.get('axis', (0.0, 0.0)); nsec = bs.get('sectors', 36)
        def _is(c_): return c_.mean() < bs.get('max_mean', 0.42) and c_[0] >= c_[2]
        cols = {f_.index: _fc(f_) for f_ in faces}
        def _sec(c_): return int(((math.degrees(math.atan2(c_.x - ax_[0], c_.y - ax_[1])) + 180) % 360) / 360 * nsec) % nsec
        zs = {}
        for f_ in faces:
            c_ = _ctr[f_.index]
            if c_.z >= bs['z_min'] and _is(cols[f_.index]): zs.setdefault(_sec(c_), []).append(c_.z)
        bands = {k: (float(np.percentile(v, 8)) - bs.get('pad', 0.002), 9.0 if bs.get('to_top') else float(np.percentile(v, 92)) + bs.get('pad', 0.002)) for k, v in zs.items() if len(v) >= 3}   # to_top: nothing of this piece shows above the band
        if bands:                                  # directions without enough belt-coloured faces borrow the nearest band
            for k in range(nsec):
                if k not in bands:
                    near = min(bands, key=lambda j: min((j - k) % nsec, (k - j) % nsec)); bands[k] = bands[near]
        inside = [f_ for f_ in faces if _sec(_ctr[f_.index]) in bands and bands[_sec(_ctr[f_.index])][0] <= _ctr[f_.index].z <= bands[_sec(_ctr[f_.index])][1]]
        src = [f_ for f_ in inside if _is(cols[f_.index])]; dst = [f_ for f_ in inside if not _is(cols[f_.index])]
        if src and dst:
            kd_ = _KD2(len(src))
            for i_, f_ in enumerate(src): kd_.insert(_ctr[f_.index], i_)
            kd_.balance()
            for f_ in dst:
                nb = kd_.find_n(_ctr[f_.index], 8); c_ = np.median(np.array([cols[src[i_].index] for _, i_, _ in nb]), 0)
                d_ = _img_of(f_.material_index); m_ = _mask([f_], d_['arr'].shape[:2], 0.12); d_['arr'][m_, :3] = c_
        rep_['band_' + bs['name']] = dict(island=ii, sectors=len(bands), inside=len(inside), filled=len(dst))
    # 1c. downward-facing faces of a cloth piece below a height (the hem underside, never seen by the front/back
    # pictures): the median colour of the nearest faces the pictures did see, a little darker
    for us in rp.get('underside', []):
        ii = _pick(us['point']); faces = _members[ii]
        cols = {f_.index: _fc(f_) for f_ in faces}
        nrm = {f_.index: (BR @ f_.normal).normalized() for f_ in faces}
        dst = [f_ for f_ in faces if _ctr[f_.index].z <= us['z_max'] and abs(_ctr[f_.index].x) <= us.get('abs_x', 9) and nrm[f_.index].z < -us.get('min_down', 0.4)]
        src = [f_ for f_ in faces if _ctr[f_.index].z <= us['z_max'] + us.get('src_above', 0.05) and abs(nrm[f_.index].y) > 0.5 and nrm[f_.index].z > -0.3]
        if src and dst:
            uni_ = np.median(np.array([cols[f_.index] for f_ in src]), 0) * us.get('shade', 0.8)   # one even shade: no facets
            kd_ = _KD2(len(src))
            for i_, f_ in enumerate(src): kd_.insert(_ctr[f_.index], i_)
            kd_.balance()
            for f_ in dst:
                if us.get('uniform'):
                    c_ = uni_
                else:
                    nb = kd_.find_n(_ctr[f_.index], 12); c_ = np.median(np.array([cols[src[i_].index] for _, i_, _ in nb]), 0) * us.get('shade', 0.8)
                d_ = _img_of(f_.material_index); m_ = _mask([f_], d_['arr'].shape[:2], 0.12); d_['arr'][m_, :3] = c_
        rep_['underside_' + us['name']] = dict(island=ii, filled=len(dst), sources=len(src))
    # 2. skin pieces: the skin tone with the painted light and dark detail kept (navel, collarbones)
    tgt_ = np.asarray(face_tone, np.float32)   # runs before the neck transition, which then samples this neck colour
    for ss in rp.get('skin', []):
        ii = _pick(ss['point']); faces = _members[ii]
        for mi in {f_.material_index for f_ in faces}:
            d_ = _img_of(mi); a_ = d_['arr']; M_ = _mask([f_ for f_ in faces if f_.material_index == mi], a_.shape[:2], 0.05)
            L_ = a_[..., 0] * 0.299 + a_[..., 1] * 0.587 + a_[..., 2] * 0.114; Mf = M_.astype(np.float32)
            sig = ss.get('sigma', 12); Lb = _rp_blur(L_ * Mf, sig) / np.maximum(_rp_blur(Mf, sig), 1e-4)
            Lt = float(tgt_ @ np.array([0.299, 0.587, 0.114], np.float32)); Lm = float(np.median(Lb[M_]))
            Ln = Lt * (Lb / Lm) ** ss.get('broad', 0.25) * np.clip(L_ / np.maximum(Lb, 1e-3), *ss.get('detail_clip', (0.6, 1.3))) ** ss.get('detail', 0.8)
            a_[M_, :3] = np.clip(tgt_[None, :] * (Ln[M_] / Lt)[:, None], 0, 1)
        b0 = [min(_ctr[f_.index][k] for f_ in faces) for k in range(3)]; b1 = [max(_ctr[f_.index][k] for f_ in faces) for k in range(3)]
        rep_['skin_' + ss['name']] = dict(island=ii, faces=len(faces), bounds=[[round(x, 3) for x in b0], [round(x, 3) for x in b1]])
    # 3. metal pieces: small pieces inside a box (the bead necklace), shaded by facing
    for ms in rp.get('metal', []):
        (x0, x1), (y0, y1), (z0, z1) = ms['box']
        pieces = [ii for ii, fs in _members.items() if len(fs) <= ms.get('max_faces', 150)
                  and all(x0 <= _ctr[f_.index].x <= x1 and y0 <= _ctr[f_.index].y <= y1 and z0 <= _ctr[f_.index].z <= z1 for f_ in fs)]
        lit = Vector(ms.get('light', (0.3, -0.8, 0.5))).normalized(); hi = np.array(ms.get('light_color', (0.93, 0.94, 0.96))); lo = np.array(ms.get('dark_color', (0.42, 0.44, 0.5)))
        nf = 0
        for ii in pieces:
            for f_ in _members[ii]:
                k_ = max(0.0, (BR @ f_.normal).normalized().dot(lit)); c_ = lo + (hi - lo) * (0.25 + 0.75 * k_)
                d_ = _img_of(f_.material_index); m_ = _mask([f_], d_['arr'].shape[:2], 0.08); d_['arr'][m_, :3] = c_; nf += 1
        rep_['metal_' + ms['name']] = dict(pieces=len(pieces), faces=nf)
    _bm.free()
    for mi, d_ in _imgs.items():
        im = d_['img']; im.pixels.foreach_set(d_['arr'].ravel())
        im.filepath_raw = str(Path(cfg['output_blend']).parent / 'retexture' / f'{_mats[mi]}-regions.jpg'); im.file_format = 'JPEG'; im.save()
        if im.packed_file: im.unpack(method='REMOVE')
        im.filepath = im.filepath_raw; im.reload(); im.pack(); _img_cache.pop(im.name, None)
    report['regionPaint'] = rep_


# =========================== 2c. neck-to-head transition ==================================
# Head and body are generated separately: the neck is a thin stump pushed into a flat-bottomed head.
# Add a skin sleeve around the upper neck: from inside the collar it lies 0.6 mm over the neck's own
# surface (sampled row by row, same colour), and above the point where the neck becomes cylindrical it
# flares out to the underside of the closed head (wider at the sides and back, like a real nape).
# Colour runs from the sampled neck colour to the head colour at each angle; weights run from the
# neck skin's weights to the head bone.
if cfg.get('neck_loft'):
    nl = cfg['neck_loft']
    body = bpy.data.objects['Body']
    nw = cfg.get('neck_widen')
    if nw and abs(nw.get('factor', 1.0) - 1.0) > 1e-3:
        # (人物2, 11-20) the neck is thinner than in the three views: the neck piece above the collar is widened about
        # the neck axis, from nothing at the collar to the full factor ramp higher up; the loft then joins the wider neck
        _bw = bmesh.new(); _bw.from_mesh(body.data); _bw.faces.ensure_lookup_table(); _bw.verts.ensure_lookup_table()
        _BWw = body.matrix_world; _BWi = _BWw.inverted()
        _tb, _ = bvh(body)
        _l, _n, _fi, _ = _tb.find_nearest(Vector((nl['axis'][0], nl['axis'][1], nl['z_flare'])))
        _isl = {_fi}; _st = [_bw.faces[_fi]]
        while _st:
            _f = _st.pop()
            for _e in _f.edges:
                for _g in _e.link_faces:
                    if _g.index not in _isl:
                        _isl.add(_g.index); _st.append(_g)
        _vs = {v for i in _isl for v in _bw.faces[i].verts}
        _ax = Vector((nl['axis'][0], nl['axis'][1], 0.0)); _nw = 0
        for v in _vs:
            pw = _BWw @ v.co
            t_ = (pw.z - nw['z_from']) / nw.get('ramp', 0.02)
            if t_ <= 0:
                continue
            t_ = min(1.0, t_); t_ = t_ * t_ * (3 - 2 * t_)
            d_ = Vector((pw.x - _ax.x, pw.y - _ax.y, 0.0))
            pw = pw + d_ * ((nw['factor'] - 1.0) * t_)
            v.co = _BWi @ pw; _nw += 1
        _bw.to_mesh(body.data); _bw.free(); body.data.update()
        report['neckWiden'] = dict(factor=nw['factor'], verts=_nw)
    t_body, b_body = bvh(body)
    t_head2, b_head2 = bvh(head)          # includes the cranium
    # rays from the neck axis sample the neck piece only: under a low collar a ray through a gap of the stump
    # would otherwise land on the shirt
    _bmn = bmesh.new(); _bmn.from_mesh(body.data); _bmn.transform(body.matrix_world); _bmn.faces.ensure_lookup_table()
    t_body_full = t_body
    _loc, _nrm, _fi, _ = t_body.find_nearest(Vector((nl['axis'][0], nl['axis'][1], nl['z_flare'])))
    _isl = {_fi}; _st = [_bmn.faces[_fi]]
    while _st:
        _f = _st.pop()
        for _e in _f.edges:
            for _g in _e.link_faces:
                if _g.index not in _isl:
                    _isl.add(_g.index); _st.append(_g)
    bmesh.ops.delete(_bmn, geom=[f for f in _bmn.faces if f.index not in _isl], context='FACES')
    t_neck_only = BVHTree.FromBMesh(_bmn); _bmn.free()
    BW = body.matrix_world
    ngi0 = body.vertex_groups['neck'].index
    neck_vs = [v for v in body.data.vertices if any(e.group == ngi0 and e.weight > 0.3 for e in v.groups)]
    kd = KDTree(len(neck_vs))
    for v in neck_vs:
        kd.insert(BW @ v.co, v.index)        # loft weights come from neck skin only, not the collar
    kd.balance()
    axis = Vector((nl['axis'][0], nl['axis'][1], 0))
    K, Mrows = nl.get('around', 72), nl.get('along', 14)
    z_s, z_f, lift = nl['z_neck'], nl['z_flare'], nl.get('lift', 0.0006)
    # the sleeve starts where the neck is closed all round: a long neck under a low collar has no skin modelled
    # below the stump (only the shirt), so the start moves up until every direction meets the neck
    def _closed(z, tree):
        return all(tree.ray_cast(Vector((axis.x, axis.y, z)), Vector((math.sin(2 * math.pi * k / K), math.cos(2 * math.pi * k / K), 0)), 0.2)[0] is not None
                   for k in range(K))
    _z0 = z_s
    if not _closed(z_s, t_body_full):
        # rays from the axis would leave through the stump and land on the shirt: sample the neck piece only
        t_body = t_neck_only
        while not _closed(z_s, t_body) and z_s < z_f - 0.004:
            z_s += 0.001
    stump_cols = None
    z_bot = z_s                    # lowest sleeve row
    if z_s != _z0 and nl.get('cover_stump', True):
        # 11-25 (人物2, user: "two necks joined together"): the sleeve used to start where the neck closes (4.4 cm
        # above the collar) and the original neck showed below it, another surface with a seam and jagged faces. The
        # sleeve now starts at the measured height inside the collar; below the closed height, where no neck skin was
        # modelled at some angles, it keeps the radius found higher up and stays inside the shirt. Every neck face it
        # covers is removed, so only one neck shows.
        z_bot = _z0
        report['neckLoftStart'] = dict(measured=round(_z0, 4), closed_from=round(z_s, 4), sleeveFrom=round(z_bot, 4))
    elif z_s != _z0:
        report['neckLoftStart'] = dict(measured=round(_z0, 4), closed_from=round(z_s, 4))
        # the sleeve now starts above the collar, in view: its lowest row takes the neck's own colour there
        stump_cols = []
        for k in range(K):
            d_ = Vector((math.sin(2 * math.pi * k / K), math.cos(2 * math.pi * k / K), 0))
            hs_ = t_body_full.ray_cast(Vector((axis.x, axis.y, z_s)), d_, 0.2)
            stump_cols.append(np.array(color_at(body, b_body, hs_[2], hs_[0]))[:3] if hs_[0] is not None else None)
        _ok = [c_ for c_ in stump_cols if c_ is not None]
        stump_cols = np.array([c_ if c_ is not None else np.median(_ok, 0) for c_ in stump_cols], np.float32)
    ring = []
    for k in range(K):
        th = 2 * math.pi * k / K
        d = Vector((math.sin(th), math.cos(th), 0))          # th 0 = back (+Y), +X at 90 deg
        hf = t_body.ray_cast(Vector((axis.x, axis.y, z_f)), d, 0.2)
        if hf[0] is None:
            raise RuntimeError(f'neck ring: no neck surface at angle {k}')
        r_f = (Vector((hf[0].x, hf[0].y, 0)) - axis).length
        wb, wf, ws = max(0.0, math.cos(th)) ** 2, max(0.0, -math.cos(th)) ** 2, math.sin(th) ** 2
        delta = nl['flare_front'] * wf + nl['flare_side'] * ws + nl['flare_back'] * wb
        up = (None,)
        while delta >= 0:       # shrink the flare until it lands under the head within the allowed rise
            q = axis + d * (r_f + delta)
            up = t_head2.ray_cast(Vector((q.x, q.y, z_s - 0.03)), Vector((0, 0, 1)), 0.3)
            if up[0] is not None and up[0].z <= z_s + nl.get('max_rise', 0.11):
                break
            delta -= 0.002
        if up[0] is None:
            raise RuntimeError(f'neck ring: no head underside at angle {k}')
        _, vi, _ = kd.find(hf[0])
        wn = {body.vertex_groups[e.group].name: e.weight for e in body.data.vertices[vi].groups}
        ring.append(dict(d=d, p1=up[0].copy(), ch=color_at(head, b_head2, up[2], up[0]), w=wn))
    # smooth the head ring (radius, height) and head colour around the circle
    def gauss(sig):
        kk = np.exp(-0.5 * (np.arange(-int(3 * sig), int(3 * sig) + 1) / sig) ** 2)
        return kk / kk.sum()
    def circ(vals, ker):
        vals = np.asarray(vals, float)
        pad = len(ker) // 2
        ext = np.concatenate([vals[-pad:], vals, vals[:pad]], axis=0)
        if vals.ndim == 1:
            return np.convolve(ext, ker, mode='valid')
        return np.stack([np.convolve(ext[:, c], ker, mode='valid') for c in range(vals.shape[1])], -1)
    kr, kc = gauss(nl.get('ring_smooth', 3.0)), gauss(nl.get('color_smooth', 6.0))
    r1s = circ([(Vector((rg['p1'].x, rg['p1'].y, 0)) - axis).length for rg in ring], kr)
    z1s = circ([rg['p1'].z for rg in ring], kr) + nl.get('sink', 0.003)
    chs = circ([rg['ch'] for rg in ring], kc)
    _front = [k for k, rg in enumerate(ring) if rg['d'].y < -0.3]
    jaw_tone = np.median(np.array([ring[k]['ch'] for k in _front]), axis=0).astype(np.float32)
    report['jawTone'] = [round(float(x), 3) for x in jaw_tone]
    neck_tone = jaw_tone if nl.get('tone') == 'jaw' else face_tone   # neck continues the jaw underside tone
    if cfg.get('hair_affine') and (cfg.get('region_paint') or {}).get('skin') and not (cfg.get('hand_skin') or {}).get('neck', True):
        # a new head whose neck piece was painted by region_paint with the face tone (人物2, 11-25: a pale band under
        # the transition with a hard top edge): the transition keeps that tone
        neck_tone = face_tone
        report['neckToneFrom'] = 'face (neck piece painted with it)'
    # rows, three parts per angle (all G1 continuous):
    #  A. on the neck surface (lift above it) from inside the collar up to z_flare
    #  B. a cubic Hermite curve in the radial plane from the neck (tangent along the neck) to the head underside
    #     (tangent along the head surface)
    #  C. along the head underside outward, just outside it, the last row tucked under the surface
    nA, nB = nl.get('rows_neck', 5), nl.get('rows_flare', 9)
    ext = nl.get('ext', [0.003, 0.006, 0.009, 0.012])
    ext_off = nl.get('ext_offset', [0.0004, 0.0004, 0.0002, -0.0005])
    off1 = nl.get('top_offset', 0.0004)
    def under(k_, r_):
        d_ = ring[k_]['d']; q = axis + d_ * r_
        hu = t_head2.ray_cast(Vector((q.x, q.y, z_s - 0.03)), Vector((0, 0, 1)), 0.3)
        if hu[0] is None:
            return None
        n_ = hu[1].normalized()
        if n_.z > 0:
            n_ = -n_                                    # face the ray origin (outside, below the head)
        return hu[0], n_
    top, exts = [], []
    for k, rg in enumerate(ring):
        r1 = float(r1s[k]); h1 = under(k, r1)
        if h1 is None:
            raise RuntimeError(f'neck ring: no head underside at angle {k}')
        top.append(h1[0] + h1[1] * off1)
        row = []
        for m, (dr, o) in enumerate(zip(ext, ext_off)):
            hm = under(k, r1 + dr)
            prev = row[-1] if row else top[-1]
            if hm is None or abs(hm[0].z - prev.z) > nl.get('ext_jump', 0.005):
                row.append(prev.copy())                     # missed or jumped onto another surface (ear, jaw edge)
            else:
                row.append(hm[0] + hm[1] * o)
        exts.append(row)
    top = np.array([[v.x, v.y, v.z] for v in top])
    exts = np.array([[[v.x, v.y, v.z] for v in row] for row in exts])     # K x n_ext x 3
    top = circ(top, kr)
    for m in range(exts.shape[1]):
        exts[:, m] = circ(exts[:, m], kr)
    covering = z_bot < z_s
    if covering:
        # rows from inside the collar: as many below the closed height as fit at the spacing above it
        _dz = (z_f - z_s) / (nA - 1)
        nA = nA + max(1, int(math.ceil((z_s - z_bot) / _dz)))
        _zA = np.linspace(z_bot, z_f, nA)
        RA = np.full((K, nA), np.nan)
        for k, rg in enumerate(ring):
            for j, z in enumerate(_zA):
                hh = t_body.ray_cast(Vector((axis.x, axis.y, z)), rg['d'], 0.2)
                if hh[0] is not None:
                    RA[k, j] = (Vector((hh[0].x, hh[0].y, 0)) - axis).length
        hitN = ~np.isnan(RA); RA_hit = RA.copy()
        for k in range(K):
            for j in range(nA - 2, -1, -1):             # no neck skin at this angle: the radius found higher up
                if np.isnan(RA[k, j]): RA[k, j] = RA[k, j + 1]
            if np.isnan(RA[k]).any():
                raise RuntimeError(f'neck ring: no neck surface at angle {k}')
        RA = circ(RA, kr)                                  # around the neck
        # along it, smoothed enough to take out the generated Adam's apple (user, 11-20: too prominent; it came back
        # when the sleeve followed the neck, as a notch under the chin in profile); the neck faces it then leaves
        # outside are removed with a wider margin there
        _kz = gauss(nl.get('cover_smooth_rows', 1.6)); _pz = len(_kz) // 2
        for k in range(K):
            sm_ = np.convolve(np.r_[[RA[k, 0]] * _pz, RA[k], [RA[k, -1]] * _pz], _kz, mode='valid')
            RA[k, :-1] = sm_[:-1]
        # at the collar the neck widens towards the shoulders (no bump): there the sleeve keeps the neck's size, or a gap
        # opened between it and the collar and showed the collar's inside (11-25)
        _low = _zA <= z_s + nl.get('cover_keep_above_closed', 0.01)
        RA = np.where(hitN & _low[None, :], np.maximum(RA, np.nan_to_num(RA_hit)), RA)
        RA_excess = np.where(hitN, np.clip(np.nan_to_num(RA_hit) - RA, 0, None), 0.0)
        _shirt = 0
        for k, rg in enumerate(ring):                      # where no neck skin was hit, inside the shirt (hidden)
            for j, z in enumerate(_zA):
                if hitN[k, j]: continue
                hs = t_body_full.ray_cast(Vector((axis.x, axis.y, z)), rg['d'], 0.2)
                if hs[0] is not None:
                    r_out = (Vector((hs[0].x, hs[0].y, 0)) - axis).length
                    if RA[k, j] + lift > r_out - 0.0015:
                        RA[k, j] = r_out - 0.0015 - lift; _shirt += 1
        report['neckLoftStart']['rowsBelowClosed'] = int((_zA < z_s).sum()); report['neckLoftStart']['keptInsideShirt'] = _shirt
        # weights per row from the nearest neck-piece vertex (the collar end of the neck is shared with the chest)
        _isl_vs = sorted({v.index for f in body.data.polygons if f.index in _isl for v in [body.data.vertices[i] for i in f.vertices]})
        kd_a = KDTree(len(_isl_vs))
        for vi in _isl_vs: kd_a.insert(BW @ body.data.vertices[vi].co, vi)
        kd_a.balance()
    grid, wts, rowW = [], [], []
    for k, rg in enumerate(ring):
        d = rg['d']
        col = []
        rn = None
        roww = []
        for j in range(nA):                             # A
            if covering:
                z = float(_zA[j]); rn = float(RA[k, j])
                pw_ = np.array([axis.x + d.x * (rn + lift), axis.y + d.y * (rn + lift), z]); col.append(pw_)
                _, vi_, _ = kd_a.find(Vector(pw_))
                roww.append({body.vertex_groups[e.group].name: e.weight for e in body.data.vertices[vi_].groups})
                continue
            z = z_s + (z_f - z_s) * j / (nA - 1)
            hh = t_body.ray_cast(Vector((axis.x, axis.y, z)), d, 0.2)
            if hh[0] is not None:
                rn = (Vector((hh[0].x, hh[0].y, 0)) - axis).length
            if rn is None:
                raise RuntimeError(f'neck ring: no neck surface below the collar line at angle {k}')
            col.append(np.array([axis.x + d.x * (rn + lift), axis.y + d.y * (rn + lift), z]))
        rowW.append(roww)
        def rz(pt):
            return np.array([(Vector((pt[0], pt[1], 0)) - axis).length, pt[2]])
        P0, P1 = rz(col[-1]), rz(top[k])
        Pn = rz(col[-2]); T0 = (P0 - Pn) / max(np.linalg.norm(P0 - Pn), 1e-6)
        Pe = rz(exts[k, 0]); T1 = (Pe - P1) / max(np.linalg.norm(Pe - P1), 1e-6)
        L = np.linalg.norm(P1 - P0)
        for j in range(1, nB + 1):                      # B
            t = j / nB
            h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
            pr = h00 * P0 + h10 * L * T0 + h01 * P1 + h11 * L * T1
            # never pinched in below the line from the neck to the head: arriving along a jaw underside that sits at
            # the throat's radius, the curve dipped 6 mm inward and showed as a notch under the chin (人物2, 11-25)
            pr[0] = max(pr[0], P0[0] + (P1[0] - P0[0]) * t - 0.001)
            hb = t_body.ray_cast(Vector((axis.x, axis.y, pr[1])), d, 0.2)   # never inside the neck stump
            if hb[0] is not None and not covering:      # (covered: the stump goes, and its top runs into the old chin)
                pr[0] = max(pr[0], (Vector((hb[0].x, hb[0].y, 0)) - axis).length + lift)
            col.append(np.array([axis.x + d.x * pr[0], axis.y + d.y * pr[0], pr[1]]))
        for m in range(exts.shape[1]):                  # C
            col.append(exts[k, m])
        if stump_cols is not None and not covering:
            # The covered stump is removed below. Following its irregular cut
            # edge here would bake a ledge into the visible throat.
            if k == 0:
                curve_module = load('neck_curve', Path(__file__).parent / 'face' / 'neck_curve.py')
            col = curve_module.fit_column(col, nA + nB - 1, 2, abs(d.x))
        grid.append([Vector(tuple(c)) for c in col])
        nt_ = len(col)
        wt = []
        for j in range(nt_):
            if j < nA:
                s_ = 0.0
            elif j < nA + nB:
                s_ = (j - nA + 1) / nB; s_ = s_ * s_ * (3 - 2 * s_)
            else:
                s_ = 1.0
            wt.append(s_)
        wts.append(wt)
    Mrows = len(grid[0])
    # one colour: the face skin tone (neck skin on the body texture is recoloured to the same tone)
    gh2 = 32
    tex2 = np.zeros((gh2, K, 4), np.float32)
    jB0, jB1 = nA - 1, nA + nB
    for row in range(gh2):
        jf = (row + 0.5) / gh2 * (Mrows - 1)
        s_ = float(np.clip((jf - jB0) / (jB1 - jB0), 0, 1)); s_ = s_ * s_ * (3 - 2 * s_)
        base_ = neck_tone[None, :]
        if stump_cols is not None and not covering and jf < jB0:
            a_ = float(np.clip(jf / max(jB0, 1e-6), 0, 1)); a_ = a_ * a_ * (3 - 2 * a_)
            base_ = circ(stump_cols, kc) * (1 - a_) + neck_tone[None, :] * a_
        tex2[row, :, :3] = base_ * (1 - s_) + chs[:, :3] * s_
    tex2[..., 3] = 1
    nimg = bpy.data.images.new('neck-blend.png', K, gh2, alpha=False)
    nimg.pixels.foreach_set(tex2.ravel())
    nimg.filepath_raw = str(_work_dir('hair') / 'neck-blend.png')
    nimg.file_format = 'PNG'
    nimg.save()
    nimg.pack()
    nm = bpy.data.materials.new('Material_neck_blend')
    nm.use_nodes = True
    nnt = nm.node_tree
    nbsdf = next(n_ for n_ in nnt.nodes if n_.type == 'BSDF_PRINCIPLED')
    nbsdf.inputs['Base Color'].default_value = (1, 1, 1, 1)      # default 0.8 would darken the neck
    nbsdf.inputs['Emission Color'].default_value = (0, 0, 0, 1)
    ntex = nnt.nodes.new('ShaderNodeTexImage')
    ntex.image = nimg
    nnt.links.new(ntex.outputs['Color'], nbsdf.inputs['Base Color'])
    head.data.materials.append(nm)
    nmi = len(head.data.materials) - 1
    for gname in {g for rg in ring for g in rg['w']} | {g for col_ in rowW for w_ in col_ for g in w_}:
        if gname not in head.vertex_groups:
            head.vertex_groups.new(name=gname)
    gidx = {g.name: g.index for g in head.vertex_groups}
    hb3 = bmesh.new()
    hb3.from_mesh(head.data)
    uvl3 = hb3.loops.layers.uv.active
    dfl3 = hb3.verts.layers.deform.verify()
    HMi3 = head.matrix_world.inverted()
    vg = []
    for k, col in enumerate(grid):
        vcol = []
        for j, pw in enumerate(col):
            nv = hb3.verts.new(HMi3 @ pw)
            s_ = wts[k][j]
            w = {g: x * (1 - s_) for g, x in (rowW[k][j] if covering and j < len(rowW[k]) else ring[k]['w']).items()}
            w['head'] = w.get('head', 0) + s_
            tot = sum(w.values())
            for g, x in w.items():
                if x / tot > 1e-4:
                    nv[dfl3][gidx[g]] = x / tot
            vcol.append(nv)
        vg.append(vcol)
    for k in range(K):
        k2 = (k + 1) % K
        for j in range(Mrows - 1):
            f = hb3.faces.new([vg[k][j], vg[k2][j], vg[k2][j + 1], vg[k][j + 1]])
            f.material_index = nmi
            f.smooth = True
            for l, (kk_, jj) in zip(f.loops, [(k, j), (k + 1, j), (k + 1, j + 1), (k, j + 1)]):
                l[uvl3].uv = ((kk_ + 0.5) / K, (jj / (Mrows - 1)) * (gh2 - 1) / gh2 + 0.5 / gh2)
    hb3.normal_update()
    f0 = next(f for f in hb3.faces if f.material_index == nmi)
    c_w = head.matrix_world @ f0.calc_center_median()
    n_w = head.matrix_world.to_3x3() @ f0.normal          # compare in world space
    if n_w.dot(c_w - Vector((axis.x, axis.y, c_w.z))) < 0:
        for f in hb3.faces:
            if f.material_index == nmi:
                f.normal_flip()
    hb3.to_mesh(head.data)
    head.data.update()
    report['neckLoft'] = dict(around=K, along=Mrows, zNeck=z_s, zFlare=z_f,
                              zHead=[round(float(top[:, 2].min()), 4), round(float(top[:, 2].max()), 4)])
    if covering:
        # every neck face inside the sleeve goes (same test for what is covered and what is removed: inside the
        # sleeve's radius at that angle and height, above its lowest row)
        _cols = [np.array([[(Vector((c_[0], c_[1], 0)) - axis).length, c_[2]] for c_ in col_]) for col_ in grid]
        _bmb = bmesh.new(); _bmb.from_mesh(body.data); _bmb.faces.ensure_lookup_table()
        _cut = []
        # loose bits next to the neck (Tripo leaves single faces) are tested like the neck piece
        _zt = max(float(c_[:, 1].max()) for c_ in _cols); _cand = set(_isl); _seen2 = set()
        for f0_ in _bmb.faces:
            if f0_.index in _seen2 or f0_.index in _cand: continue
            c0_ = BW @ f0_.calc_center_median()
            if not (z_bot - 0.01 < c0_.z < _zt and (Vector((c0_.x, c0_.y, 0)) - axis).length < 0.12): continue
            comp_ = {f0_.index}; st_ = [f0_]
            while st_ and len(comp_) <= 20:
                for e_ in st_.pop().edges:
                    for g_ in e_.link_faces:
                        if g_.index not in comp_: comp_.add(g_.index); st_.append(g_)
            _seen2 |= comp_
            if len(comp_) <= 20: _cand |= comp_
        for i in sorted(_cand):
            c_ = BW @ _bmb.faces[i].calc_center_median()
            th_ = math.atan2(c_.x - axis.x, c_.y - axis.y) % (2 * math.pi)
            rz_ = _cols[int(round(th_ / (2 * math.pi) * K)) % K]
            if c_.z < rz_[0, 1] - 0.001: continue
            if c_.z >= min(rz_[:, 1].max(), z_f):         # above the flare start the neck piece only runs into the head
                _cut.append(_bmb.faces[i]); continue
            r_lim = 0.0                                   # widest sleeve segment at this height (the profile can turn)
            for (r0_, z0_), (r1_, z1_) in zip(rz_[:-1], rz_[1:]):
                if min(z0_, z1_) - 1e-6 <= c_.z <= max(z0_, z1_) + 1e-6:
                    t_ = 0.0 if abs(z1_ - z0_) < 1e-9 else (c_.z - z0_) / (z1_ - z0_)
                    r_lim = max(r_lim, r0_ + t_ * (r1_ - r0_), r0_ if abs(z1_ - z0_) < 1e-9 else 0.0, r1_ if abs(z1_ - z0_) < 1e-9 else 0.0)
            _k_ = int(round(th_ / (2 * math.pi) * K)) % K
            _ex = float(np.interp(c_.z, _zA, RA_excess[_k_])) if c_.z <= _zA[-1] else 0.0
            if (Vector((c_.x, c_.y, 0)) - axis).length <= r_lim + 0.003 + _ex:
                _cut.append(_bmb.faces[i])
        bmesh.ops.delete(_bmb, geom=_cut, context='FACES_ONLY')
        _loose = [v for v in _bmb.verts if not v.link_faces]
        bmesh.ops.delete(_bmb, geom=_loose, context='VERTS')
        _bmb.to_mesh(body.data); _bmb.free(); body.data.update()
        report['neckLoft']['neckFacesCovered'] = len(_cut)
    elif stump_cols is not None:
        # the sleeve lies 0.6 mm over the stump above its start; in view (above the collar) the two surfaces
        # flicker through each other, so the stump faces it covers are removed
        _bmb = bmesh.new(); _bmb.from_mesh(body.data); _bmb.faces.ensure_lookup_table()
        _cut = [_bmb.faces[i] for i in _isl if all((BW @ v.co).z > z_s + 0.002 for v in _bmb.faces[i].verts)]
        bmesh.ops.delete(_bmb, geom=_cut, context='FACES_ONLY')
        _loose = [v for v in _bmb.verts if not v.link_faces]
        bmesh.ops.delete(_bmb, geom=_loose, context='VERTS')
        _bmb.to_mesh(body.data); _bmb.free(); body.data.update()
        report['neckLoft']['stumpFacesRemoved'] = len(_cut)
        # the neck left below the transition (above the collar, in view) is another material: same colour, different
        # shading, so it showed as a pale band with a hard edge (人物2, 11-25). It takes the transition's material, at
        # the colour of the transition's lowest row at its angle, so the two read as one surface.
        if nl.get('stump_material', True):
            if nm.name not in [m_.name for m_ in body.data.materials if m_]:
                body.data.materials.append(nm)
            _bmi = [m_.name if m_ else '' for m_ in body.data.materials].index(nm.name)
            _bmb = bmesh.new(); _bmb.from_mesh(body.data); _bmb.faces.ensure_lookup_table()
            _uvb = _bmb.loops.layers.uv.active; _nst = 0
            _keep = set(range(len(_bmb.faces)))
            _bt, _ = bvh(body)
            _l0, _n0, _fi0, _ = _bt.find_nearest(Vector((nl['axis'][0], nl['axis'][1], z_s - 0.004)))
            _isl2 = {_fi0}; _stk = [_bmb.faces[_fi0]]
            while _stk:
                _f = _stk.pop()
                for _e in _f.edges:
                    for _g in _e.link_faces:
                        if _g.index not in _isl2 and _g.material_index == _bmb.faces[_fi0].material_index:
                            _isl2.add(_g.index); _stk.append(_g)
            _zlow = z_s - nl.get('stump_band', 0.05)
            for _i in _isl2:
                _f = _bmb.faces[_i]
                _c = BW @ _f.calc_center_median()
                if not (_zlow < _c.z <= z_s + 0.002):
                    continue
                _f.material_index = _bmi
                for _l in _f.loops:
                    _p = BW @ _l.vert.co
                    _th = math.atan2(_p.x - axis.x, _p.y - axis.y) % (2 * math.pi)
                    _l[_uvb].uv = ((_th / (2 * math.pi)) % 1.0, 0.5 / gh2)
                _nst += 1
            _bmb.to_mesh(body.data); _bmb.free(); body.data.update()
            report['neckLoft']['stumpRecoloured'] = _nst


# =========================== 2c2. template hands ==========================================
# 11-17: Tripo hands read as stuck together (finger webs up to the middle knuckle, palm side nearly one slab, one flat
# skin colour) and a hand grafted onto an outfit showed seams at the cuff. The MakeHuman (CC0) hands, fitted once onto
# this rig with this character's finger lengths (work/hand/make_template_hand.py), replace them on every build: the
# old hand faces go (transplanted Material_hand faces, and skin past the wrist on the skin material), the template
# (own material, baked finger-gap shading and nails, 6 cm forearm stub inside the cuff) is joined into Body.
if cfg.get('template_hand'):
    th = cfg['template_hand']
    body_o = bpy.data.objects['Body']; BWm = body_o.matrix_world
    wrist_x = abs((RW @ rig.data.bones['hand.L'].head_local).x)
    mats_ = [m.name if m else '' for m in body_o.data.materials]
    skin_mi = mats_.index(th.get('skin_material', 'Material_upper_body')) if th.get('skin_material', 'Material_upper_body') in mats_ else -1
    sk_arr = img_array(face_image(body_o, next(p for p in body_o.data.polygons if p.material_index == skin_mi))) if skin_mi >= 0 else None
    tb = bmesh.new(); tb.from_mesh(body_o.data); tuv = tb.loops.layers.uv.active
    def _tcol(f_):
        IH_, IW_ = sk_arr.shape[:2]; u_ = np.mean([l[tuv].uv.x for l in f_.loops]); v_ = np.mean([l[tuv].uv.y for l in f_.loops])
        x_ = int(np.clip((u_ % 1) * IW_, 0, IW_ - 1)); y_ = int(np.clip((v_ % 1) * IH_, 0, IH_ - 1))
        return sk_arr[max(0, y_ - 2):y_ + 3, max(0, x_ - 2):x_ + 3, :3].reshape(-1, 3).mean(0)
    def _tskin(c_): return c_[0] - c_[2] > 0.06 and c_.mean() > 0.5 and c_[0] > c_[1]
    cut_x = wrist_x - th.get('cut', 0.03)
    old_hand = [f_ for f_ in tb.faces if mats_[f_.material_index] == 'Material_hand'
                or (f_.material_index == skin_mi and abs((BWm @ f_.calc_center_median()).x) > cut_x and _tskin(_tcol(f_)))]
    bmesh.ops.delete(tb, geom=old_hand, context='FACES')
    bmesh.ops.delete(tb, geom=[v_ for v_ in tb.verts if not v_.link_faces], context='VERTS')
    tb.to_mesh(body_o.data); tb.free(); body_o.data.update()
    with bpy.data.libraries.load(th['blend'], link=False) as (src_, dst_):
        dst_.objects = ['HandTpl']
    hand_o = dst_.objects[0]; bpy.context.scene.collection.objects.link(hand_o)
    n_tucked = 0
    if th.get('tone_from') == 'forearm':
        # bare forearms: the template's forearm stub (meant to sit inside a cuff) would show its end. The part past
        # the cut goes 2.5 mm under the forearm skin, so only the forearm's own cut edge meets the hand.
        for side_ in ('L', 'R'):
            h0 = RW @ rig.data.bones[f'hand.{side_}'].head_local; e0 = RW @ rig.data.bones[f'lower_arm.{side_}'].head_local
            ax_ = (h0 - e0).normalized(); lim_ = wrist_x - cut_x
            for v_ in hand_o.data.vertices:
                if (v_.co.x > 0) != (h0.x > 0): continue
                d_ = (v_.co - h0).dot(ax_)
                if d_ < -lim_ - 0.002:
                    t_ = min(1.0, (-lim_ - 0.002 - d_) / 0.006); t_ = t_ * t_ * (3 - 2 * t_)
                    c_ = h0 + ax_ * d_; r_ = v_.co - c_
                    if r_.length > 1e-6:
                        v_.co = v_.co - r_.normalized() * 0.0025 * t_; n_tucked += 1
    hand_o.matrix_world = BWm.copy(); hand_o.data.transform(BWm.inverted())   # template is in world coordinates
    if body_o.data.uv_layers.active and hand_o.data.uv_layers.active:
        hand_o.data.uv_layers.active.name = body_o.data.uv_layers.active.name
    n_hand_v = len(hand_o.data.vertices)
    with bpy.context.temp_override(active_object=body_o, selected_editable_objects=[body_o, hand_o], object=body_o):
        bpy.ops.object.join()
    # tone: the template texture is painted around a fixed skin colour; scale it so its median skin matches this
    # character's face tone (outfits are matched to their own skin again after the build)
    tm_ = next(m for m in body_o.data.materials if m and m.name == 'Material_hand_tpl')
    timg = next(n_.image for n_ in tm_.node_tree.nodes if n_.type == 'TEX_IMAGE' and n_.image)
    tpx = np.empty(timg.size[0] * timg.size[1] * 4, np.float32); timg.pixels.foreach_get(tpx); tpx = tpx.reshape(-1, 4)
    near_ = np.linalg.norm(tpx[:, :3] - np.array([0.945, 0.753, 0.745]), axis=1) < 0.14
    tmed = np.median(tpx[near_, :3], 0) if near_.sum() > 100 else np.array([0.945, 0.753, 0.745])
    hand_tone = np.asarray(face_tone, np.float32)
    if th.get('tone_from') == 'forearm' and sk_arr is not None:
        # bare forearms: the skin just above the cut (on the body's own texture) sets the hand colour
        fb_ = bmesh.new(); fb_.from_mesh(body_o.data); fuv_ = fb_.loops.layers.uv.active
        _fc = []
        for f_ in fb_.faces:
            if f_.material_index != skin_mi: continue
            ax_ = abs((BWm @ f_.calc_center_median()).x)
            if cut_x - 0.08 < ax_ < cut_x - 0.005:
                IH_, IW_ = sk_arr.shape[:2]; u_ = np.mean([l[fuv_].uv.x for l in f_.loops]); v_ = np.mean([l[fuv_].uv.y for l in f_.loops])
                c_ = sk_arr[int(np.clip((v_ % 1) * IH_, 0, IH_ - 1)), int(np.clip((u_ % 1) * IW_, 0, IW_ - 1)), :3]
                if c_[0] - c_[2] > 0.06 and c_[0] > c_[1]: _fc.append(c_)     # all skin texels, shaded ones too
        fb_.free()
        if len(_fc) > 30:
            hand_tone = np.median(np.array(_fc), 0).astype(np.float32)
    tgain = np.clip(hand_tone / np.maximum(tmed, 1e-3), 0.6, 1.25)
    tpx[:, :3] = np.clip(tpx[:, :3] * tgain, 0, 1)
    timg2 = bpy.data.images.new('hand-tpl-toned', timg.size[0], timg.size[1], alpha=True); timg2.pixels.foreach_set(tpx.ravel())
    timg2.filepath_raw = str(Path(cfg['output_blend']).parent / 'retexture' / 'hand-tpl-toned.png'); timg2.file_format = 'PNG'; timg2.save()
    timg2.source = 'FILE'; timg2.filepath = timg2.filepath_raw; timg2.reload(); timg2.pack()
    for n_ in tm_.node_tree.nodes:
        if n_.type == 'TEX_IMAGE' and n_.image is timg: n_.image = timg2
    if th.get('tone_from') == 'forearm':
        # the template material carries emission and a 0.8 base factor (both exported into MToon): next to bare forearm
        # skin the hand then reads brighter. Same settings as the body skin.
        for n_ in tm_.node_tree.nodes:
            if n_.type == 'BSDF_PRINCIPLED':
                n_.inputs['Base Color'].default_value = (1, 1, 1, 1)
                n_.inputs['Emission Color'].default_value = (0, 0, 0, 1)
                if 'Emission Strength' in n_.inputs: n_.inputs['Emission Strength'].default_value = 0.0
                for l_ in list(n_.inputs['Emission Color'].links): tm_.node_tree.links.remove(l_)
    report['templateHand'] = dict(oldFacesRemoved=len(old_hand), templateVerts=n_hand_v, cutX=round(cut_x, 3),
                                  tone=[round(float(x), 3) for x in hand_tone], gain=[round(float(x), 3) for x in tgain],
                                  toneFrom=th.get('tone_from', 'face'), stubTucked=n_tucked)


# =========================== 2d. hand skin tone ===========================================
# The Tripo texture paints the back of each hand pale and the palm salmon with hard edges at the UV
# seams, so the hands show colour bands along their sides. Hand skin texels are recoloured to the
# face skin tone; fine light/dark detail (knuckles, nails, finger gaps) is kept and broad shading is
# compressed. Hand skin = upper-body faces past the wrist that are warm and bright, plus faces that
# are surrounded by them (nails, tiny fingertip triangles).
def _box(x, r, ax):
    pad = [(r + 1, r) if i == ax else (0, 0) for i in range(x.ndim)]
    c = np.cumsum(np.pad(x, pad, mode='edge'), axis=ax)
    n_ = x.shape[ax]
    return (np.take(c, range(2 * r + 1, 2 * r + 1 + n_), axis=ax) - np.take(c, range(0, n_), axis=ax)) / (2 * r + 1)


def _blur(x, sig):
    r = max(1, int(round(sig * 0.87)))
    for _ in range(3):
        x = _box(_box(x, r, 0), r, 1)
    return x


# 11-17: hands and neck can sit on different textures (outfits: transplanted base hands on Material_hand, the outfit's
# own neck on Material_upper_body). One pass per material; with one material it is a single pass as before.
def _skin_pass(hs, mat_name, do_hands, do_neck, out_name, rep_key):
    target = face_tone
    body_o = bpy.data.objects['Body']
    BWm = body_o.matrix_world
    forearm = do_hands and hs.get('tone_from') == 'forearm'
    mi_ub = next((i for i, m in enumerate(body_o.data.materials) if m.name == mat_name), -1)
    _p0 = next((p for p in body_o.data.polygons if p.material_index == mi_ub), None)
    if _p0 is None:                                       # e.g. Material_hand after the template hands replaced it
        report[rep_key] = dict(material=mat_name, skipped='no faces'); return
    ub_img = face_image(body_o, _p0)
    arr = img_array(ub_img)
    IH, IW = arr.shape[:2]
    hb_ = bmesh.new()
    hb_.from_mesh(body_o.data)
    huv = hb_.loops.layers.uv.active

    def fcol(f):
        u = np.mean([l[huv].uv.x for l in f.loops]); v = np.mean([l[huv].uv.y for l in f.loops])
        x = int(np.clip((u % 1) * IW, 0, IW - 1)); y = int(np.clip((v % 1) * IH, 0, IH - 1))
        return arr[max(0, y - 2):y + 3, max(0, x - 2):x + 3, :3].reshape(-1, 3).mean(0)

    def is_skin(c):
        return c[0] - c[2] > 0.06 and c.mean() > 0.5 and c[0] > c[1]

    if forearm:
        # bare forearms (the generated hand kept): every warm texel past the wrist is hand skin, the darker palm and
        # finger gaps too, and the hand takes the colour of the forearm skin next to it
        _fc = []
        for side_ in ('L', 'R'):
            w_ = RW @ rig.data.bones[f'hand.{side_}'].head_local; e_ = RW @ rig.data.bones[f'lower_arm.{side_}'].head_local
            ax_ = (w_ - e_); ln_ = ax_.length; ax_ = ax_ / max(ln_, 1e-6)
            for f in hb_.faces:
                if f.material_index != mi_ub:
                    continue
                d_ = (BWm @ f.calc_center_median() - w_).dot(ax_)
                if -0.35 * ln_ < d_ < -0.05 * ln_ and (BWm @ f.calc_center_median() - (w_ + ax_ * d_)).length < 0.06:
                    c_ = fcol(f)
                    if c_[0] - c_[2] > 0.04 and c_[0] >= c_[1]:
                        _fc.append(c_)
        if len(_fc) > 20:
            target = np.median(np.array(_fc), 0).astype(np.float32)

        def is_skin(c):
            return c[0] - c[2] > 0.04 and c[0] >= c[1] - 0.01 and c.mean() > 0.12

    sel = set()
    for side, sg in ((('L', 1), ('R', -1)) if do_hands else ()):
        wrist = RW @ rig.data.bones[f'hand.{side}'].head_local
        # reach: the hand itself, wrist to the tip of the middle finger, with a margin (a large hand reached past 0.2)
        _tipb = rig.data.bones.get(f'middle_distal.{side}')
        reach = max(hs.get('reach', 0.2), 1.25 * ((RW @ _tipb.tail_local) - wrist).length) if _tipb else hs.get('reach', 0.2)

        def near(f, m=-1.0, reach=reach):
            c = BWm @ f.calc_center_median()
            return (c.x - wrist.x) * sg > m and (c - wrist).length < reach

        side_sel = {f for f in hb_.faces if f.material_index == mi_ub and near(f, 0.0) and is_skin(fcol(f))}
        stack = list(side_sel)
        while stack:                                          # skin running back under the cuff
            f = stack.pop()
            for e in f.edges:
                for g in e.link_faces:
                    if g not in side_sel and g.material_index == mi_ub and near(g) and is_skin(fcol(g)):
                        side_sel.add(g); stack.append(g)
        for _ in range(3):
            vs = {v for f in side_sel for v in f.verts}
            for f in list(side_sel):
                for v in f.verts:
                    for g in v.link_faces:
                        if g in side_sel or g.material_index != mi_ub:
                            continue
                        c = fcol(g)
                        if c[2] < c[0] + 0.02 and all(w in vs for w in g.verts):
                            side_sel.add(g)
        sel |= side_sel
    n_arm = 0
    if forearm and hs.get('arms', True):
        # 11-25 (人物2, short sleeves): the upper arm inside the sleeve kept the generated texture, painted darker (in
        # the sleeve's shadow in the pictures), and showed as a brown patch with a hard edge when the arms went up. All
        # bare-arm skin from the shoulder joint to the wrist takes the hands' tone (painted detail kept).
        for side_ in ('L', 'R'):
            _ub = rig.data.bones.get(f'upper_arm.{side_}')
            if _ub is None: continue
            s_ = RW @ _ub.head_local; w_ = RW @ rig.data.bones[f'hand.{side_}'].head_local
            ax_ = w_ - s_; ln_ = ax_.length; ax_ = ax_ / max(ln_, 1e-6)
            _BR = BWm.to_3x3()
            for f in hb_.faces:
                if f.material_index != mi_ub or f in sel: continue
                c_ = BWm @ f.calc_center_median(); t_ = (c_ - s_).dot(ax_); r_ = c_ - (s_ + ax_ * t_)
                # skin faces away from the arm's axis; the sleeve lining around the upper arm faces it (11-26, 人物2: the
                # lining's shadowed, skin-like texels took the hand tone and showed as pale patches in raised sleeves)
                if 0.0 <= t_ <= ln_ and r_.length < hs.get('arm_radius', 0.075) and (_BR @ f.normal).normalized().dot(r_.normalized()) > 0.2 \
                        and is_skin(fcol(f)):
                    sel.add(f); n_arm += 1
    if do_neck:                                           # neck skin: same tone as the face and the neck loft
        g_neck = body_o.vertex_groups['neck'].index
        dfl_ = hb_.verts.layers.deform.active
        nsel = {f for f in hb_.faces if f.material_index == mi_ub and all(v[dfl_].get(g_neck, 0) > 0.3 for v in f.verts)
                and is_skin(fcol(f))}
        if hs.get('skin_all'):     # 11-19 denim: chest V, midriff and ankles show skin too; tone all of it like the neck
            _ax = hs.get('skin_all_max_abs_x', 9.0)     # sleeves cover the arms: skin colour out there is cuff lining
            nsel |= {f for f in hb_.faces if f.material_index == mi_ub and abs((BWm @ f.calc_center_median()).x) < _ax
                     and is_skin(fcol(f))}
            _db = hs.get('skin_dark_box')       # skin under a hem carries the hem's painted shadow: darker, still warm
            if _db:
                def _inb(f):
                    c_ = BWm @ f.calc_center_median()
                    return all(lo <= x <= hi for x, (lo, hi) in zip((c_.x, c_.y, c_.z), _db))
                def _warm(c): return c[0] - c[2] > 0.06 and c[0] > c[1] and c.mean() > hs.get('skin_dark_min_mean', 0.25)
                nsel |= {f for f in hb_.faces if f.material_index == mi_ub and _inb(f) and _warm(fcol(f))}
        if hs.get('neck_flood') and nsel:
            # outfits (11-17): the collar is welded to the neck and pale lace passes is_skin, so the forest collar turned
            # pink. Keep only skin connected to the top of the neck and close to the colour found there.
            _nz = {f: (BWm @ f.calc_center_median()).z for f in nsel}
            _top = max(_nz.values())
            seeds = [f for f, z in _nz.items() if z > _top - 0.012]
            nref = np.median(np.array([fcol(f) for f in seeds]), 0)
            keep = set(seeds); stack = list(seeds)
            while stack:
                f = stack.pop()
                for e in f.edges:
                    for g in e.link_faces:
                        if g in keep or g.material_index != mi_ub:
                            continue
                        c_ = fcol(g)   # lace is paler and greyer than skin; darker skin shading still counts as skin
                        if ((c_[0] - c_[2]) >= 0.65 * (nref[0] - nref[2]) and c_.mean() <= nref.mean() + 0.05
                                and any(v[dfl_].get(g_neck, 0) > 0.1 for v in g.verts)):
                            keep.add(g); stack.append(g)
            report['neckFlood'] = dict(before=len(nsel), seeds=len(seeds), kept=len(keep), ref=[round(float(x), 3) for x in nref])
            nsel = keep
        report['neckSkinFaces'] = len(nsel)
    else:
        nsel = set()
    def raster(faces):
        M = np.zeros((IH, IW), bool)
        for f in faces:
            q = [(l[huv].uv.x % 1 * IW, l[huv].uv.y % 1 * IH) for l in f.loops]
            for k in range(1, len(q) - 1):
                (x0, y0), (x1, y1), (x2, y2) = q[0], q[k], q[k + 1]
                xa, xb = int(max(0, np.floor(min(x0, x1, x2)))), int(min(IW - 1, np.ceil(max(x0, x1, x2))))
                ya, yb = int(max(0, np.floor(min(y0, y1, y2)))), int(min(IH - 1, np.ceil(max(y0, y1, y2))))
                gx, gy = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
                den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if abs(den) < 1e-12:
                    continue
                a_ = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
                b_ = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
                inside = (a_ >= -0.02) & (b_ >= -0.02) & (a_ + b_ <= 1.02)
                M[ya:yb + 1, xa:xb + 1] |= inside
        return M
    L_ = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
    out = arr.copy()
    def recolor(M, tgt):
        """Texels in M take the tone tgt; fine light/dark detail kept, broad shading compressed."""
        if not M.any():
            return
        Mf = M.astype(np.float32)
        sig = hs.get('sigma', 12)
        Lb = _blur(L_ * Mf, sig) / np.maximum(_blur(Mf, sig), 1e-4)
        Lt = float(tgt @ np.array([0.299, 0.587, 0.114], np.float32))
        Lm = float(np.median(Lb[M]))
        Ln = Lt * (Lb / Lm) ** hs.get('broad', 0.4) * np.clip(L_ / np.maximum(Lb, 1e-3), 0.5, 1.4) ** hs.get('detail', 1.0)
        out[M, :3] = np.clip(tgt[None, :] * (Ln[M] / Lt)[:, None], 0, 1)
        ring = M.copy()                                       # bleed margin around the islands
        for _ in range(4):
            ring[1:] |= ring[:-1]; ring[:-1] |= ring[1:]; ring[:, 1:] |= ring[:, :-1]; ring[:, :-1] |= ring[:, 1:]
        out[ring & ~M & ~M_all, :3] = tgt
    M_hand, M_neck = raster(sel), raster(nsel)
    M_all = M_hand | M_neck
    recolor(M_hand, target)
    recolor(M_neck & ~M_hand, neck_tone if 'neck_tone' in globals() else target)
    hb_.free()
    M = M_all
    ub_img.pixels.foreach_set(out.ravel())
    ub_img.filepath_raw = str(Path(cfg['output_blend']).parent / 'retexture' / out_name)
    ub_img.file_format = 'JPEG'
    ub_img.save()
    if ub_img.packed_file:                                    # pack() keeps old packed bytes; repack from disk
        ub_img.unpack(method='REMOVE')
    ub_img.filepath = str(Path(cfg['output_blend']).parent / 'retexture' / out_name)
    ub_img.reload()
    ub_img.pack()
    _img_cache.pop(ub_img.name, None)
    report[rep_key] = dict(material=mat_name, faces=len(sel), armFaces=n_arm, neckFaces=len(nsel), texels=int(M.sum()), target=[round(float(x), 3) for x in target],
                           toneFrom='forearm' if forearm else 'face')

if cfg.get('hand_skin'):
    _hs = cfg['hand_skin']; _mh = _hs.get('material', 'Material_upper_body'); _mn = _hs.get('neck_material', _mh)
    if _mn == _mh:
        _skin_pass(_hs, _mh, True, _hs.get('neck', True), 'upper-body-handtone.jpg', 'handSkin')
    else:
        _skin_pass(_hs, _mh, True, False, 'upper-body-handtone.jpg', 'handSkin')
        _skin_pass(_hs, _mn, False, _hs.get('neck', True), 'outfit-necktone.jpg', 'neckSkin')
    for _m in _hs.get('skin_extra_materials', []):
        _skin_pass(dict(_hs, skin_all=True, neck_flood=False), _m, False, True, f'{_m}-skintone.jpg', 'skin_' + _m)


# =========================== 2d2. cuff lining (11-19 denim) ================================
# The 4K retexture projects the front/back references onto the mesh, so the inside of a short cuff picks up the
# hand's skin colour and shows as jagged pink slivers around the wrist once the template hand is in. The arms are
# covered by the sleeves, so skin colour past cuff_lining.min_abs_x on the sleeve material is lining: paint it with the
# median colour of the lining around it.
for cl in ([cfg['cuff_lining']] if cfg.get('cuff_lining') else []) + cfg.get('lining_regions', []):
    body_o = bpy.data.objects['Body']; BWm = body_o.matrix_world
    mi_ = next(i for i, m in enumerate(body_o.data.materials) if m and m.name == cl.get('material', 'Material_upper_body'))
    _img = face_image(body_o, next(p_ for p_ in body_o.data.polygons if p_.material_index == mi_))
    _arr = img_array(_img); IH_, IW_ = _arr.shape[:2]
    _bm = bmesh.new(); _bm.from_mesh(body_o.data); _uv = _bm.loops.layers.uv.active
    def _fc(f_):
        u_ = np.mean([l[_uv].uv.x for l in f_.loops]); v_ = np.mean([l[_uv].uv.y for l in f_.loops])
        x_ = int(np.clip((u_ % 1) * IW_, 0, IW_ - 1)); y_ = int(np.clip((v_ % 1) * IH_, 0, IH_ - 1))
        return _arr[max(0, y_ - 2):y_ + 3, max(0, x_ - 2):x_ + 3, :3].reshape(-1, 3).mean(0)
    def _sk(c_): return c_[0] - c_[2] > cl.get('warm', 0.02) and c_.mean() < cl.get('max_mean', 9.0)   # lavender is always bluer than red
    def _in(f_):
        c_ = BWm @ f_.calc_center_median()
        if 'box' in cl:
            (x0, x1), (y0, y1), (z0, z1) = cl['box']
            return x0 <= c_.x <= x1 and y0 <= c_.y <= y1 and z0 <= c_.z <= z1
        return abs(c_.x) > cl.get('min_abs_x', 0.3)
    arm_f = [f_ for f_ in _bm.faces if f_.material_index == mi_ and _in(f_)]
    bad = {f_ for f_ in arm_f if _sk(_fc(f_))}
    for _ in range(cl.get('grow', 1)):                     # include the darker rim faces next to them
        bad |= {g for f_ in list(bad) for e in f_.edges for g in e.link_faces if g.material_index == mi_ and g in set(arm_f)
                and (_fc(g)[0] - _fc(g)[2]) > 0.0}
    good = [f_ for f_ in arm_f if f_ not in bad]
    from mathutils.kdtree import KDTree as _KD
    kd_ = _KD(len(good))
    for i_, f_ in enumerate(good): kd_.insert(BWm @ f_.calc_center_median(), i_)
    kd_.balance()
    out_ = _arr.copy(); painted = 0
    for f_ in bad:
        near_ = kd_.find_n(BWm @ f_.calc_center_median(), cl.get('neighbours', 12))
        col_ = np.median(np.array([_fc(good[i_]) for _, i_, _ in near_]), 0) * cl.get('shade', 0.9)
        q = [(l[_uv].uv.x % 1 * IW_, l[_uv].uv.y % 1 * IH_) for l in f_.loops]
        for k in range(1, len(q) - 1):
            (x0, y0), (x1, y1), (x2, y2) = q[0], q[k], q[k + 1]
            xa, xb = int(max(0, np.floor(min(x0, x1, x2)) - 1)), int(min(IW_ - 1, np.ceil(max(x0, x1, x2)) + 1))
            ya, yb = int(max(0, np.floor(min(y0, y1, y2)) - 1)), int(min(IH_ - 1, np.ceil(max(y0, y1, y2)) + 1))
            gx, gy = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-12: continue
            a_ = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den; b_ = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
            ins = (a_ >= -0.15) & (b_ >= -0.15) & (a_ + b_ <= 1.15)
            sub = out_[ya:yb + 1, xa:xb + 1]; sub[ins, :3] = col_; painted += int(ins.sum())
    if cl.get('delete'):            # 11-19: the jagged lining rim pokes out past the cuff; the template forearm stub fills the opening
        _del = [f_ for f_ in bad if abs((BWm @ f_.calc_center_median()).x) > cl.get('delete_min_abs_x', 0.5)]
        bmesh.ops.delete(_bm, geom=_del, context='FACES')
        bmesh.ops.delete(_bm, geom=[v_ for v_ in _bm.verts if not v_.link_faces], context='VERTS')
        _bm.to_mesh(body_o.data); body_o.data.update(); report['cuffLiningDeleted'] = len(_del)
    _bm.free()
    _img.pixels.foreach_set(out_.ravel())
    _img.filepath_raw = str(Path(cfg['output_blend']).parent / 'retexture' / f"upper-body-lining-{cl.get('name', 'cuff')}.jpg"); _img.file_format = 'JPEG'; _img.save()
    if _img.packed_file: _img.unpack(method='REMOVE')
    _img.filepath = _img.filepath_raw; _img.reload(); _img.pack(); _img_cache.pop(_img.name, None)
    report['lining_' + cl.get('name', 'cuff')] = dict(faces=len(bad), texels=painted)


# =========================== 2e. finger weights ===========================================
# Tripo's finger weights bleed into the neighbouring fingers (mean 3-5%, 15-30% on ~20 verts per finger), so a
# bending finger drags the next one along and the hand reads as a mitten (user, 11-16). Past the knuckles keep only
# the finger's own chain; the removed share goes back to that chain so the hand/palm weights are untouched.
if cfg.get('finger_clean'):
    fc = cfg['finger_clean']
    bo = bpy.data.objects['Body']; BM = bo.matrix_world
    _fn = ['thumb', 'index', 'middle', 'ring', 'little']
    gname = {g.index: g.name.lower() for g in bo.vertex_groups}
    def _finger(n):
        for f in _fn:
            if f in n: return f
        return None
    cleaned = 0; moved = 0.0
    for v in bo.data.vertices:
        if abs((BM @ v.co).x) < fc.get('x_min', 0.655): continue
        ws = [(g.group, g.weight) for g in v.groups]
        fw = {}
        for gi, w in ws:
            f = _finger(gname.get(gi, ''))
            if f: fw[f] = fw.get(f, 0.0) + w
        if not fw: continue
        dom = max(fw, key=fw.get)
        if fw[dom] < fc.get('dominant', 0.5): continue
        other = sum(w for f, w in fw.items() if f != dom)
        if other < fc.get('min_bleed', 0.02): continue
        own = [(gi, w) for gi, w in ws if _finger(gname.get(gi, '')) == dom]
        for gi, w in ws:
            if _finger(gname.get(gi, '')) not in (None, dom):
                bo.vertex_groups[gi].remove([v.index])
        tot = sum(w for _, w in own)
        for gi, w in own:
            bo.vertex_groups[gi].add([v.index], w + other * (w / tot if tot > 0 else 1.0 / len(own)), 'REPLACE')
        cleaned += 1; moved += other
    report['fingerClean'] = dict(verts=cleaned, movedWeight=round(moved, 3))


# =========================== 2f. helper bones =============================================
# 11-17: one skeleton for the character and every outfit, so the joint helpers live on the rig, not on the clothes.
# Each helper sits at a joint with the rest frame of the child bone, is parented like it and copies half of its
# rotation (VRM 1.0 rotation constraint, exported from Copy Rotation local/local ADD; must be a deform bone). Body
# weights at the joint are split three ways: with s = child share, parent (1-s)^2, helper 2s(1-s), child s^2. The mean
# rotation of every vertex stays the same, but the blend spans half the angle, so the joint keeps its volume instead of
# folding (Unity/MMD "twist/assist" bones). band: s is rebuilt from the position along the limb (clean, even band of
# +-half around the joint; same rule for skin and every clothing layer at that spot); split: the original weights.
def _twist_chain(hb, body_o, bco_):
    """Forearm twist spread over the forearm (bare forearms; user, 11-26: the wrist twisted into a thin line in 极乐净土).
    The player moves the whole forearm turn onto the hand bone (so long sleeves do not wring), which left a bare forearm
    turning within the few centimetres of the wrist band. Here `count` bones along the forearm (children of the lower
    arm) take k / count of the hand's own turn about the forearm axis (copy rotation on the bone axis only, exported as
    VRM roll constraints); the skin along the forearm is weighted between neighbouring ones, from no turn at `start` of
    the forearm to the full turn at the wrist, where the hand takes over within +- `band` (bend blended there)."""
    rep_ = {}
    N = hb.get('count', 4); t0 = hb.get('start', 0.1); band = hb.get('band', 0.03)
    for s_ in ('L', 'R'):
        lo, src = f"{hb.get('parent', 'lower_arm')}.{s_}", f"{hb['source']}.{s_}"
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        eb_ = rig.data.edit_bones; lb_ = eb_[lo]; e_, w_ = lb_.head.copy(), lb_.tail.copy(); names = []
        for k in range(1, N + 1):
            tk = t0 + (1.0 - t0) * k / N
            nb = eb_.new(f"{hb['name']}{k}.{s_}"); nb.head = e_ + (w_ - e_) * min(tk, 0.97); nb.tail = nb.head + (w_ - e_).normalized() * 0.03
            nb.roll = lb_.roll; nb.parent = lb_; nb.use_deform = True; nb.use_connect = False; names.append(nb.name)
        bpy.ops.object.mode_set(mode='OBJECT')
        for k, nm in enumerate(names, 1):
            con = rig.pose.bones[nm].constraints.new('COPY_ROTATION')
            con.target = rig; con.subtarget = src; con.use_x = con.use_z = False; con.use_y = True; con.mix_mode = 'ADD'
            con.owner_space = con.target_space = 'LOCAL'; con.influence = k / N
        h_ = np.array((RW @ rig.data.bones[lo].head_local)[:]); tl_ = np.array((RW @ rig.data.bones[lo].tail_local)[:])
        L_ = float(np.linalg.norm(tl_ - h_)); ax_ = (tl_ - h_) / L_; bt = band / L_
        gi = {g.name: g.index for g in body_o.vertex_groups}
        g_lo, g_hand = gi.get(lo), gi.get(src)
        hgs = [body_o.vertex_groups.get(nm) or body_o.vertex_groups.new(name=nm) for nm in names]
        nodes = [g_lo] + [g.index for g in hgs]                 # node k carries k / N of the turn
        changed = 0
        for v in body_o.data.vertices:
            ws = {e.group: e.weight for e in v.groups}; tot = sum(ws.values())
            wl, wh = ws.get(g_lo, 0.0), ws.get(g_hand, 0.0)
            if tot <= 0 or wl + wh < 0.85 * tot or wl <= 0.0:
                continue
            p = bco_[v.index] - h_; t = float(p @ ax_) / L_; rr = float(np.linalg.norm(p - float(p @ ax_) * ax_))
            if t < t0 - 0.02 or t > 1.0 + bt or rr > hb.get('radius', 0.12):
                continue
            x_ = min(1.0, max(0.0, (t - (1.0 - bt)) / (2 * bt))); hw = x_ * x_ * (3 - 2 * x_)      # hand share at the wrist
            if t > 1.0 - 2 * bt: hw = max(hw, wh / (wl + wh))                           # past the wrist the hand keeps its share
            phi = min(1.0, max(0.0, (t - t0) / (1.0 - t0))) * N; k0 = min(int(phi), N - 1); f_ = phi - k0
            T_ = wl + wh; rest = (1.0 - hw) * T_
            new = {g: 0.0 for g in nodes}; new[nodes[k0]] += rest * (1 - f_); new[nodes[k0 + 1]] += rest * f_
            for g, w in new.items():
                if w > 1e-4: body_o.vertex_groups[g].add([v.index], w, 'REPLACE')
                elif g in ws: body_o.vertex_groups[g].remove([v.index])
            if g_hand is not None:
                if hw * T_ > 1e-4: body_o.vertex_groups[g_hand].add([v.index], hw * T_, 'REPLACE')
                elif g_hand in ws: body_o.vertex_groups[g_hand].remove([v.index])
            changed += 1
        rep_[f"{hb['name']}.{s_}"] = dict(verts=changed, mode='twist', bones=N)
    return rep_


if cfg.get('helper_bones'):
    body_o = bpy.data.objects['Body']; BWm = body_o.matrix_world
    bco_ = np.array([(BWm @ v.co)[:] for v in body_o.data.vertices])
    helper_rep = {}
    for hb in cfg['helper_bones']:
        if hb.get('mode') == 'twist':
            helper_rep.update(_twist_chain(hb, body_o, bco_))
            continue
        for s_ in ('L', 'R'):
            src = f"{hb['source']}.{s_}"; hname = f"{hb['name']}.{s_}"
            bpy.context.view_layer.objects.active = rig
            bpy.ops.object.mode_set(mode='EDIT')
            eb_ = rig.data.edit_bones; sb = eb_[src]
            nb = eb_.new(hname); nb.head = sb.head.copy(); nb.tail = sb.head + (sb.tail - sb.head).normalized() * 0.04
            nb.roll = sb.roll; nb.parent = sb.parent; nb.use_deform = True; nb.use_connect = False
            bpy.ops.object.mode_set(mode='OBJECT')
            con = rig.pose.bones[hname].constraints.new('COPY_ROTATION')
            con.target = rig; con.subtarget = src; con.use_x = con.use_y = con.use_z = True; con.mix_mode = 'ADD'
            con.owner_space = con.target_space = 'LOCAL'; con.influence = hb.get('influence', 0.5)
            # weights
            h_ = np.array((RW @ rig.data.bones[src].head_local)[:]); tl_ = np.array((RW @ rig.data.bones[src].tail_local)[:])
            ax_ = (tl_ - h_) / np.linalg.norm(tl_ - h_)
            inner = {f"{n}.{s_}" if n in ('shoulder', 'upper_arm', 'lower_arm', 'hand') else n for n in hb['inner']}
            gi = {g.name: g.index for g in body_o.vertex_groups}
            inner_idx = {gi[n] for n in inner if n in gi}; out_idx = gi.get(src)
            hg = body_o.vertex_groups.get(hname) or body_o.vertex_groups.new(name=hname)
            half = hb.get('half', 0.04); changed = 0
            for v in body_o.data.vertices:
                ws = {e.group: e.weight for e in v.groups}
                wi = sum(w for g_, w in ws.items() if g_ in inner_idx); wo = ws.get(out_idx, 0.0); tot = sum(ws.values())
                if tot <= 0 or wi + wo < 0.85 * tot:
                    continue
                p = bco_[v.index] - h_; tt = float(p @ ax_); rr = float(np.linalg.norm(p - tt * ax_))
                if hb.get('mode', 'split') == 'band':
                    if abs(tt) > 2 * half or rr > hb.get('radius', 0.15):
                        continue
                    x_ = min(1.0, max(0.0, (tt + half) / (2 * half))); s = x_ * x_ * (3 - 2 * x_)
                else:
                    if wi <= 0 or wo <= 0:
                        continue
                    s = wo / (wi + wo)
                T_ = wi + wo
                for g_ in inner_idx:
                    if g_ in ws:
                        body_o.vertex_groups[g_].add([v.index], ws[g_] / wi * (1 - s) ** 2 * T_ if wi > 0 else 0.0, 'REPLACE')
                if wi <= 0 and (1 - s) > 1e-4:                    # band mode can give a parent share to an arm-only vertex
                    pn = next(iter(n for n in inner if n in gi and n.endswith('.' + s_)), None)
                    if pn: body_o.vertex_groups[gi[pn]].add([v.index], (1 - s) ** 2 * T_, 'REPLACE')
                if out_idx is not None:
                    body_o.vertex_groups[out_idx].add([v.index], s * s * T_, 'REPLACE')
                hg.add([v.index], 2 * s * (1 - s) * T_, 'REPLACE'); changed += 1
            helper_rep[hname] = dict(verts=changed, mode=hb.get('mode', 'split'), influence=hb.get('influence', 0.5))
    report['helperBones'] = helper_rep


# =========================== 3. spring bones ==============================================
def add_chain(prefix, parent, joints):
    names = []
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    eb = rig.data.edit_bones
    inv = RW.inverted()
    prev = eb[parent]
    for k in range(len(joints) - 1):
        b = eb.new(f'{prefix}_{k + 1}')
        b.head = inv @ joints[k]
        b.tail = inv @ joints[k + 1]
        b.parent = prev
        b.use_connect = k > 0
        b.use_deform = True
        names.append(b.name)
        prev = b
    bpy.ops.object.mode_set(mode='OBJECT')
    return names


def ang_of(p, c):
    return math.degrees(math.atan2(p[0] - c[0], p[1] - c[1]))  # 0 = back (+Y), + toward +X (character left)


def angdiff(a, b):
    return (a - b + 180) % 360 - 180


def centroid(P, A, c_ang, z, half_ang, half_z):
    m = (np.abs([angdiff(a, c_ang) for a in A]) <= half_ang) & (np.abs(P[:, 2] - z) <= half_z)
    return P[m].mean(0) if m.sum() >= 3 else None


def chain_weights(z, z_root, z_tip, nb, blend):
    """(fixed share, per-bone shares) along one chain for a vertex at height z."""
    if z >= z_root + blend:
        return 1.0, [0.0] * nb
    u = max(0.0, (z_root - z) / max(z_root - z_tip, 1e-6) * nb)
    w = [max(0.0, 1 - abs(u - (k + 0.5))) for k in range(nb)]
    if u <= 0.5:
        w = [1.0] + [0.0] * (nb - 1)
    if u >= nb - 0.5:
        w = [0.0] * (nb - 1) + [1.0]
    s = sum(w)
    w = [x / s for x in w]
    fixed = min(1.0, max(0.0, (z - (z_root - blend)) / (2 * blend))) if z > z_root - blend else 0.0
    return fixed, [x * (1 - fixed) for x in w]


def assign(obj, fixed_bone, chains, angle_fn, front_fade=None):
    """chains: list of dict(angle, bones, z_root, z_tip). Angular blend between neighbouring chains."""
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    groups = {fixed_bone: obj.vertex_groups.new(name=fixed_bone)}
    for c in chains:
        for b in c['bones']:
            groups[b] = obj.vertex_groups.new(name=b)
    angles = [c['angle'] for c in chains]
    cyclic = cfg_cyclic = (max(angles) - min(angles)) > 300
    order = sorted(range(len(chains)), key=lambda i: angles[i])
    M = obj.matrix_world
    acc = {}
    for v in obj.data.vertices:
        p = M @ v.co
        a = angle_fn(p)
        sa = sorted(angles)
        # neighbours
        if cyclic:
            k = max([i for i, x in enumerate(sa) if x <= a], default=len(sa) - 1)
            i0, i1 = order[k], order[(k + 1) % len(sa)]
            span = (angles[i1] - angles[i0]) % 360 or 360
            t = ((a - angles[i0]) % 360) / span
        else:
            if a <= sa[0]:
                i0 = i1 = order[0]; t = 0.0
            elif a >= sa[-1]:
                i0 = i1 = order[-1]; t = 0.0
            else:
                k = max(i for i, x in enumerate(sa) if x <= a)
                i0, i1 = order[k], order[k + 1]
                t = (a - angles[i0]) / (angles[i1] - angles[i0])
        fade = front_fade(a) if front_fade else 1.0
        w = {}
        fixed_total = 0.0
        pair = [(i0, 1 - t), (i1, t)] if i0 != i1 else [(i0, 1.0)]
        live = [(ci, wc) for ci, wc in pair if p.z >= chains[ci].get('z_floor', -1e9)]
        if live and len(live) < len(pair):
            pair = [(live[0][0], 1.0)]
        for ci, wc in pair:
            c = chains[ci]
            fx, bw = chain_weights(p.z, c['z_root'], c['z_tip'], len(c['bones']), c['blend'])
            fixed_total += wc * (fx + (1 - fade) * (1 - fx))
            for b, x in zip(c['bones'], bw):
                w[b] = w.get(b, 0) + wc * x * fade
        w[fixed_bone] = fixed_total
        s = sum(w.values())
        for b, x in w.items():
            if x / s > 1e-4:
                groups[b].add([v.index], x / s, 'REPLACE')
                acc[b] = acc.get(b, 0) + 1
    return acc


# hair -----------------------------------------------------------------------------------
HP = np.array([(hair.matrix_world @ v.co)[:] for v in hair.data.vertices])
hc = (RW @ rig.data.bones['head'].head_local)
HA = [ang_of(p, (hc.x, hc.y)) for p in HP]
hz_root, hz_tip = cfg['hair']['z_root'], float(HP[:, 2].min())
if cfg['hair'].get('root') == 'head_width':
    # (人物2, 11-20: short hair swung from the crown like a wig) the chains start where the head is widest (about the
    # top of the ears); hair above rests on the skull and stays with the head
    _HD = np.array([(head.matrix_world @ v.co)[:] for v in head.data.vertices])
    _HD = _HD[_HD[:, 2] > hc.z]
    _rad = np.hypot(_HD[:, 0] - hc.x, _HD[:, 1] - hc.y); _zb = np.round(_HD[:, 2] / 0.005).astype(int)
    _bins = {b: float(np.percentile(_rad[_zb == b], 95)) for b in np.unique(_zb) if (_zb == b).sum() >= 8}
    hz_root = round(max(_bins, key=_bins.get) * 0.005, 4)
    report['hairRootFromHead'] = hz_root
hblend = cfg['hair'].get('blend', 0.015)
front = cfg['hair'].get('front')
hair_angles = list(cfg['hair']['angles']) + ([front['angle']] if front else [])
hair_chains = []
for i, a in enumerate(hair_angles):
    is_front = front is not None and i == len(hair_angles) - 1
    root = front['z_root'] if is_front else hz_root
    sector = np.abs([angdiff(x, a) for x in HA]) <= (front['tip_sector'] if is_front else 22.5)
    tip = float(HP[sector, 2].min()) if sector.sum() else hz_tip
    nb = front['bones'] if is_front else cfg['hair']['bones']
    joints = []
    zs = np.linspace(root, tip + 0.004, nb + 1)
    for z in zs:
        c = centroid(HP, HA, a, z, 16, 0.015)
        if c is None and joints:
            c = np.array([joints[-1].x, joints[-1].y, z])
        if c is None:
            r = 0.11
            c = np.array([hc.x + r * math.sin(math.radians(a)), hc.y + r * math.cos(math.radians(a)), z])
        joints.append(Vector((float(c[0]), float(c[1]), float(z))))
    name = f'hair_{i:02d}'
    bones = add_chain(f'Hair{i:02d}', 'head', joints)
    phys = dict(cfg['hair']['physics'], **(front.get('physics', {}) if is_front else {}))
    lp = cfg['hair'].get('length_physics')
    if lp:
        # shorter strands swing less: stiffer, lighter and more damped, in proportion to the length below the root
        f_ = float(np.clip((root - tip) / lp['ref'], 0.15, 1.0))
        phys = dict(phys, stiffness=round(min(4.0, phys['stiffness'] / f_), 3), gravityPower=round(phys.get('gravityPower', 0.12) * f_, 3),
                    dragForce=round(min(0.8, phys.get('dragForce', 0.35) + 0.35 * (1 - f_)), 3))
    c = dict(name=name, angle=a, bones=bones, z_root=root, z_tip=tip, blend=hblend, physics=phys)
    if is_front:
        c['z_floor'] = tip - front.get('floor_margin', 0.02)
    hair_chains.append(c)
fa, fb = cfg['hair']['front_fade']
fmin = cfg['hair'].get('front_fade_min', 0.0)
hair_acc = assign(hair, 'head', hair_chains, lambda p: ang_of(p, (hc.x, hc.y)),
                  front_fade=lambda a: fmin + (1 - fmin) * min(1.0, max(0.0, (fb - abs(a)) / (fb - fa))))
# Hair surfaces hidden behind the face (the inner cap and a stray strip at mouth height) would poke
# through the face once they swing; keep them on the head, easing over two edge rings.
from mathutils.bvhtree import BVHTree
hbm = bmesh.new()
hbm.from_mesh(head.data)
hbm.transform(head.matrix_world)
htree = BVHTree.FromBMesh(hbm)
hidden = set()
for v in hair.data.vertices:
    p = hair.matrix_world @ v.co
    if p.y >= cfg['hair'].get('hidden_max_y', 0.0):
        continue
    loc, nor, _, _ = htree.ray_cast(p + Vector((0, -1e-5, 0)), Vector((0, -1, 0)), 0.4)
    if loc is not None and nor.y < 0:
        hidden.add(v.index)
nbr = {}
for e in hair.data.edges:
    a, b = e.vertices
    nbr.setdefault(a, set()).add(b)
    nbr.setdefault(b, set()).add(a)
ring1 = {n for i in hidden for n in nbr.get(i, ())} - hidden
ring2 = {n for i in ring1 for n in nbr.get(i, ())} - hidden - ring1
head_gi = hair.vertex_groups['head'].index
for idx_set, f in ((hidden, 1.0), (ring1, 0.67), (ring2, 0.33)):
    for i in idx_set:
        v = hair.data.vertices[i]
        cur = {e.group: e.weight for e in v.groups}
        for gidx in list(cur):
            if gidx != head_gi:
                cur[gidx] *= (1 - f)
        cur[head_gi] = f + (1 - f) * cur.get(head_gi, 0.0)
        s_ = sum(cur.values())
        for gidx, w in cur.items():
            g = hair.vertex_groups[gidx]
            if w / s_ > 1e-4:
                g.add([i], w / s_, 'REPLACE')
            else:
                g.remove([i])
report['hairHiddenPinned'] = dict(hidden=len(hidden), ring1=len(ring1), ring2=len(ring2))
sp_ = cfg['hair'].get('scalp_pin')
if sp_:
    # hair lying on the scalp stays with the head: full within sp_[0] of the head surface, fading out by sp_[1]
    n_sp = 0
    for v in hair.data.vertices:
        p = hair.matrix_world @ v.co
        if p.z >= hz_root + hblend:
            continue
        loc, nor, _, d = htree.find_nearest(p)
        if loc is None or d >= sp_[1]:
            continue
        f = 1.0 if d <= sp_[0] else 1 - (d - sp_[0]) / (sp_[1] - sp_[0]); f = f * f * (3 - 2 * f)
        cur = {e.group: e.weight for e in v.groups}
        for gidx in list(cur):
            if gidx != head_gi:
                cur[gidx] *= (1 - f)
        cur[head_gi] = f + (1 - f) * cur.get(head_gi, 0.0)
        s_ = sum(cur.values())
        for gidx, w in cur.items():
            g = hair.vertex_groups[gidx]
            if w / s_ > 1e-4:
                g.add([v.index], w / s_, 'REPLACE')
            else:
                g.remove([v.index])
        n_sp += 1
    report['hairScalpPinned'] = n_sp
report['hair'] = dict(chains=[(c['name'], c['angle'], c['bones'], round(c['z_root'], 3), round(c['z_tip'], 3)) for c in hair_chains], weightedVerts=hair_acc, zRoot=hz_root, zTip=hz_tip)

# skirt ----------------------------------------------------------------------------------
hipc = RW @ rig.data.bones['hips'].head_local     # also used by the waist blend when there is no skirt
skirt_chains = []
if cfg.get('skirt'):
    sk = bpy.data.objects[SKIRT_MESH]
    SP = np.array([(sk.matrix_world @ v.co)[:] for v in sk.data.vertices])
    hipc = RW @ rig.data.bones['hips'].head_local
    SA = [ang_of(p, (hipc.x, hipc.y)) for p in SP]
    sz_root = cfg['skirt']['z_root']
    skirt_chains = []
    for i, a in enumerate(cfg['skirt']['angles']):
        m = np.abs([angdiff(x, a) for x in SA]) <= 22.5
        z_tip = float(SP[m, 2].min())
        joints = []
        for z in np.linspace(sz_root, z_tip + 0.004, cfg['skirt']['bones'] + 1):
            c = centroid(SP, SA, a, z, 15, 0.02)
            if c is None:
                c = np.array([joints[-1].x, joints[-1].y, z])
            joints.append(Vector((float(c[0]), float(c[1]), float(z))))
        parent = 'hips'
        lc = cfg['skirt'].get('leg_constraint')
        if lc:
            # Long skirts (11-17): spring colliders cannot keep an ankle-length skirt over a knee-high step. Each chain
            # hangs from 1-2 root bones at its own head that copy a share of the thigh rotation (VRM 1.0 rotation
            # constraint, exported from Blender Copy Rotation, local/local, influence = share). Roots copy the thigh's
            # rest frame, so the local delta is the same world rotation; the skirt swings from the waistband with the
            # leg and the springs add the sway on top.
            for s_, centre in (('L', lc['angle']), ('R', -lc['angle'])):
                share = lc['max'] * max(0.0, math.cos(math.radians(angdiff(a, centre)))) ** lc.get('power', 1.5)
                if share < lc.get('min', 0.05):
                    continue
                bpy.context.view_layer.objects.active = rig
                bpy.ops.object.mode_set(mode='EDIT')
                eb_ = rig.data.edit_bones; leg = eb_[f'upper_leg.{s_}']
                rname = f'SkirtRoot{i:02d}{s_}'; rb_ = eb_.new(rname)
                M_ = leg.matrix.copy(); M_.translation = RW.inverted() @ joints[0]
                rb_.length = 0.06; rb_.matrix = M_; rb_.parent = eb_[parent]; rb_.use_deform = True   # non-deform bones are dropped by the VRM export
                bpy.ops.object.mode_set(mode='OBJECT')
                pb_ = rig.pose.bones[rname]
                con = pb_.constraints.new('COPY_ROTATION')
                con.target = rig; con.subtarget = f'upper_leg.{s_}'
                con.use_x = con.use_y = con.use_z = True; con.mix_mode = 'ADD'
                con.owner_space = con.target_space = 'LOCAL'; con.influence = share
                report.setdefault('skirtLegConstraint', {})[rname] = round(share, 3)
                parent = rname
        bones = add_chain(f'Skirt{i:02d}', parent, joints)
        skirt_chains.append(dict(name=f'skirt_{i:02d}', angle=a, bones=bones, z_root=sz_root, z_tip=z_tip, blend=0.015))
    skirt_acc = assign(sk, 'hips', skirt_chains, lambda p: ang_of(p, (hipc.x, hipc.y)))
    if cfg.get('skirt_leg_follow'):
        lf = cfg['skirt_leg_follow']
        gl = {s_: (sk.vertex_groups.get(f'upper_leg.{s_}') or sk.vertex_groups.new(name=f'upper_leg.{s_}')) for s_ in ('L', 'R')}
        nlf = 0
        for v in sk.data.vertices:
            pw = sk.matrix_world @ v.co
            a = ang_of(pw, (hipc.x, hipc.y))
            fz = min(1.0, max(0.0, (lf['z_top'] - pw.z) / (lf['z_top'] - lf['z_full'])))
            fz = fz * fz * (3 - 2 * fz)
            if 'z_off' in lf:                  # long skirts (11-17): follow the thigh only near the hips, fade out above the knee
                fo = min(1.0, max(0.0, (pw.z - lf['z_zero']) / (lf['z_off'] - lf['z_zero'])))
                fz *= fo * fo * (3 - 2 * fo)
            if fz <= 0:
                continue
            for s_, centre in (('L', lf['angle']), ('R', -lf['angle'])):
                fa = max(0.0, 1 - abs(angdiff(a, centre)) / lf['width'])
                wl = lf['max'] * fa * fz
                if wl <= 1e-3:
                    continue
                cur = {e.group: e.weight for e in v.groups}
                for gi_ in list(cur):
                    cur[gi_] *= (1 - wl)
                cur[gl[s_].index] = cur.get(gl[s_].index, 0.0) + wl
                tot = sum(cur.values())
                for gi_, w in cur.items():
                    sk.vertex_groups[gi_].add([v.index], w / tot, 'REPLACE')
                nlf += 1
        report['skirtLegFollow'] = nlf
    report['skirt'] = dict(chains=[(c['name'], c['angle'], c['bones'], round(c['z_tip'], 3)) for c in skirt_chains], weightedVerts=skirt_acc)

# ribbon tails ---------------------------------------------------------------------------
ribbon_chains = []
if cfg.get('ribbon'):
    rb = bpy.data.objects[cfg['ribbon'].get('mesh', 'Spring_02_ribbon')]
    RP = np.array([(rb.matrix_world @ v.co)[:] for v in rb.data.vertices])
    for g in list(rb.vertex_groups):
        rb.vertex_groups.remove(g)
    fixed = rb.vertex_groups.new(name=cfg['ribbon']['parent'])
    ribbon_chains = []
    rz_root = cfg['ribbon']['z_root']
    _rsplit = cfg['ribbon'].get('split')      # 11-17: a strap looping front and back splits by depth (axis 1) instead of left/right
    _rsides = (((_rsplit['names'][0], RP[:, _rsplit['axis']] < _rsplit['at']), (_rsplit['names'][1], RP[:, _rsplit['axis']] >= _rsplit['at']))
               if _rsplit else (('L', RP[:, 0] > 0), ('R', RP[:, 0] <= 0)))
    for side, sel in _rsides:
        P = RP[sel]
        if sel.sum() < 20:                      # one-sided parts (11-17: a shoulder-bag strap on the left only)
            for vi in np.nonzero(sel)[0]: fixed.add([int(vi)], 1.0, 'REPLACE')
            continue
        z_tip = float(P[:, 2].min())
        joints = []
        for z in np.linspace(rz_root, z_tip + 0.003, cfg['ribbon']['bones'] + 1):
            m = np.abs(P[:, 2] - z) <= 0.012
            c = P[m].mean(0) if m.sum() else np.array([joints[-1].x, joints[-1].y, z])
            joints.append(Vector((float(c[0]), float(c[1]), float(z))))
        bones = add_chain(f"{cfg['ribbon'].get('bone_prefix', 'Ribbon')}_{side}", cfg['ribbon']['parent'], joints)
        groups = [rb.vertex_groups.new(name=b) for b in bones]
        idx = np.nonzero(sel)[0]
        for vi in idx:
            z = RP[vi, 2]
            fx, bw = chain_weights(z, rz_root, z_tip, len(bones), 0.01)
            if fx > 1e-4:
                fixed.add([int(vi)], fx, 'REPLACE')
            for g, x in zip(groups, bw):
                if x > 1e-4:
                    g.add([int(vi)], x, 'REPLACE')
        ribbon_chains.append(dict(name=f"{cfg['ribbon'].get('chain_prefix', 'ribbon')}_{side}", bones=bones, z_tip=z_tip))
    report['ribbon'] = dict(chains=[(c['name'], c['bones'], round(c['z_tip'], 3)) for c in ribbon_chains])

# earrings ---------------------------------------------------------------------------------
# The cross earrings are three islands per side inside the Head mesh (hook ring, stud, pendant), skinned rigidly to
# the head. They stay in the Head mesh (removing vertices would renumber everything the expression scripts address)
# and only get re-weighted: ring -> Earring_X_1 (hangs from the ear), stud + pendant -> Earring_X_2 (swings at the
# stud). Islands are picked by position and size, not by vertex index.
earring_chains = []
if cfg.get('earring'):
    ec = cfg['earring']
    hd = bpy.data.objects['Head']; HM = hd.matrix_world
    HP = np.array([(HM @ v.co)[:] for v in hd.data.vertices])
    _par = np.arange(len(HP))
    def _find(a):
        while _par[a] != a:
            _par[a] = _par[_par[a]]; a = _par[a]
        return a
    for e in hd.data.edges:
        a, b = e.vertices; ra, rb = _find(a), _find(b)
        if ra != rb: _par[ra] = rb
    _isl = {}
    for i in range(len(HP)): _isl.setdefault(_find(i), []).append(i)
    cand = []
    for idx in _isl.values():
        P = HP[idx]; c = P.mean(0); sz = P.max(0) - P.min(0)
        if (ec['x'][0] <= abs(c[0]) <= ec['x'][1] and ec['z'][0] <= c[2] <= ec['z'][1] and ec['y'][0] <= c[1] <= ec['y'][1]
                and sz.max() <= ec['max_size'] and len(idx) <= ec['max_verts']):
            cand.append((c, idx, P))
    for side, sgn in (('L', 1), ('R', -1)):
        parts = sorted([t for t in cand if (t[0][0] > 0) == (sgn > 0)], key=lambda t: -t[0][2])     # top island first
        if len(parts) < 2:
            report.setdefault('earring', {})[side] = 'not found'; continue
        top = parts[0][2]; stud = parts[1][2]; pend = np.vstack([t[2] for t in parts[1:]])
        j1 = Vector((float(top[:, 0].mean()), float(top[:, 1].mean()), float(top[:, 2].max())))   # hook meets the ear
        j2 = Vector((float(stud[:, 0].mean()), float(stud[:, 1].mean()), float(stud[:, 2].mean())))   # hinge
        j3 = Vector((float(pend[:, 0].mean()), float(pend[:, 1].mean()), float(pend[:, 2].min())))    # pendant tip
        bones = add_chain(f'Earring_{side}', ec['parent'], [j1, j2, j3])
        vgs = [hd.vertex_groups.get(b) or hd.vertex_groups.new(name=b) for b in bones]
        for k, (_, idx, _) in enumerate(parts):
            g = vgs[0] if k == 0 else vgs[1]
            for vi in idx:
                for gi in [x.group for x in hd.data.vertices[vi].groups]:
                    hd.vertex_groups[gi].remove([int(vi)])
                g.add([int(vi)], 1.0, 'REPLACE')
        earring_chains.append(dict(name=f'earring_{side}', bones=bones))
        report.setdefault('earring', {})[side] = dict(bones=bones, islands=[len(t[1]) for t in parts],
                                                      joints=[[round(float(x), 4) for x in j] for j in (j1, j2, j3)])

# =========================== 3b. layer fit (clipping) =====================================
# Waist: the waistband follows the spine, the skirt top the hips and the tucked-in top a mix, so
# the layers slide through each other when the body bends or twists. Every layer in the waist band
# gets the same split over the torso bones, averaged from the body at that height and angle; the
# skirt keeps its chain share and only its fixed (hips) share is split.
from mathutils.bvhtree import BVHTree
TORSO_BONES = ['hips', 'spine', 'chest', 'upperChest']
wb = cfg.get('waist_blend')
if wb:
    body = bpy.data.objects['Body']
    OWb = body.matrix_world
    BPw = np.array([(OWb @ v.co)[:] for v in body.data.vertices])
    z0, z1, fe, zb, nsec = wb['z'][0], wb['z'][1], wb['feather'], wb['bin'], wb['sectors']
    nz = int(math.ceil((z1 - z0 + 2 * fe) / zb)) + 1
    def wsplit(obj, v):
        names = {e.group: obj.vertex_groups[e.group].name for e in v.groups}
        return {names[e.group]: e.weight for e in v.groups}
    def bins(p):
        iz = min(nz - 1, max(0, int((p[2] - (z0 - fe)) / zb)))
        isec = int(((ang_of(p, (hipc.x, hipc.y)) + 180.0) % 360.0) / 360.0 * nsec) % nsec
        return iz, isec
    F = np.zeros((nz, nsec, len(TORSO_BONES))); C = np.zeros((nz, nsec))
    for v in body.data.vertices:
        p = BPw[v.index]
        if not (z0 - fe <= p[2] <= z1 + fe):
            continue
        w = wsplit(body, v); tot = sum(w.values()); s = sum(w.get(b, 0.0) for b in TORSO_BONES)
        if tot <= 0 or s < 0.98 * tot:
            continue
        iz, isec = bins(p)
        F[iz, isec] += [w.get(b, 0.0) / s for b in TORSO_BONES]; C[iz, isec] += 1
    # fill empty bins from neighbours, then smooth over height and angle
    for _ in range(60):
        empty = C == 0
        if not empty.any():
            break
        Fs = np.zeros_like(F); Cs = np.zeros_like(C)
        for dz, da in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            Fr, Cr = np.roll(np.roll(F, dz, 0), da, 1), np.roll(np.roll(C, dz, 0), da, 1)
            if dz == 1: Fr[0] = 0; Cr[0] = 0
            if dz == -1: Fr[-1] = 0; Cr[-1] = 0
            Fs += Fr; Cs += Cr
        F[empty] = Fs[empty]; C[empty] = Cs[empty]
    Fn = F / np.maximum(C, 1e-9)[..., None]
    for _ in range(wb['smooth']):
        Fn = (2 * Fn + np.roll(Fn, 1, 1) + np.roll(Fn, -1, 1) + np.concatenate([Fn[:1], Fn[:-1]]) + np.concatenate([Fn[1:], Fn[-1:]])) / 6
    Fn /= Fn.sum(-1, keepdims=True)
    def blend_amount(z):
        if z < z0 - fe or z > z1 + fe:
            return 0.0
        if z < z0:
            t = (z - (z0 - fe)) / fe
        elif z > z1:
            t = ((z1 + fe) - z) / fe
        else:
            return 1.0
        return t * t * (3 - 2 * t)
    changed = {}
    for obj, only_fixed in ((body, False),) + (((bpy.data.objects[SKIRT_MESH], True),) if wb.get('skirt', True) else ()):
        OWo = obj.matrix_world
        grp = {b: (obj.vertex_groups.get(b) or obj.vertex_groups.new(name=b)) for b in TORSO_BONES}
        n = 0
        for v in obj.data.vertices:
            p = OWo @ v.co
            k = blend_amount(p.z)
            if k <= 0:
                continue
            w = wsplit(obj, v); tot = sum(w.values()); s = sum(w.get(b, 0.0) for b in TORSO_BONES)
            if tot <= 0 or s <= 1e-6 or (not only_fixed and s < 0.98 * tot):
                continue
            iz, isec = bins(p)
            tgt = Fn[iz, isec] * s
            for bi, b in enumerate(TORSO_BONES):
                x = (1 - k) * w.get(b, 0.0) + k * tgt[bi]
                if x > 1e-4:
                    grp[b].add([v.index], x / tot, 'REPLACE')
                elif b in w:
                    grp[b].remove([v.index])
            n += 1
        changed[obj.name] = n
    report['waistBlend'] = dict(changed=changed, profile={round(z0 - fe + (i + 0.5) * zb, 3): [round(float(x), 2) for x in Fn[i].mean(0)] for i in range(nz)})

# Crotch of trousers (user, 11-20: the crotch stretched in a squat). Near the midline between the hip joints and the
# lowest point of the crotch, the weights become an even left/right split of the legs by side, with a hips share that
# grows from pelvis_min at the crotch bottom to all hips at the hip joints, so the seam stays between the legs and
# moves half as far as either leg. Fades out sideways (by half_span) and above the hips bone.
cb = cfg.get('crotch_blend')
if cb:
    body = bpy.data.objects['Body']; OWc = body.matrix_world
    gn = {g.index: g.name for g in body.vertex_groups}
    LEGS = ('hips', 'upper_leg.L', 'upper_leg.R')
    grp = {b: body.vertex_groups.get(b) or body.vertex_groups.new(name=b) for b in LEGS}
    sm = lambda t: (lambda u: u * u * (3 - 2 * u))(min(1.0, max(0.0, t)))
    rise = max(cb['hip_z'] - cb['seam_z'], 1e-3); n_c = 0
    for v in body.data.vertices:
        p = OWc @ v.co
        lat = (p.x - cb['cx']) / cb['half_span']
        if abs(lat) >= 1.0 or p.z < cb['seam_z'] - 0.3 * rise or p.z > cb['top_z']:
            continue
        m_ = (1 - sm((abs(lat) - 0.45) / 0.55)) * sm((p.z - (cb['seam_z'] - 0.3 * rise)) / (0.3 * rise)) * (1 - sm((p.z - cb['hip_z']) / max(cb['top_z'] - cb['hip_z'], 1e-3)))
        if m_ <= 1e-3:
            continue
        w = {gn[e.group]: e.weight for e in v.groups}; tot = sum(w.values())
        if tot <= 0 or sum(w.get(b, 0.0) for b in LEGS) < 0.9 * tot:
            continue                                    # only body parts carried by the hips and legs
        pel = cb['pelvis_min'] + (1 - cb['pelvis_min']) * sm((p.z - cb['seam_z']) / rise)
        left = sm((lat + 1) / 2)
        tgt = {'hips': pel, 'upper_leg.L': (1 - pel) * left, 'upper_leg.R': (1 - pel) * (1 - left)}
        for b in LEGS:
            x = (1 - m_) * w.get(b, 0.0) / tot + m_ * tgt[b]
            if x > 1e-4:
                grp[b].add([v.index], x, 'REPLACE')
            elif b in w:
                grp[b].remove([v.index])
        n_c += 1
    report['crotchBlend'] = dict(verts=n_c, **{k: cb[k] for k in ('cx', 'seam_z', 'hip_z', 'half_span')})

# Skirt contact: where the skirt lies on the body (waistband, hips, the buttocks at the back) it
# takes the body's weights at the nearest surface point, fading out with distance; the free part
# keeps its spring weights. The skirt then moves with the hips and thighs it rests on instead of
# letting them through.
scw = cfg.get('skirt_contact')
if scw:
    body = bpy.data.objects['Body']; sk = bpy.data.objects[SKIRT_MESH]
    OWb = body.matrix_world; OWs = sk.matrix_world
    bmats = [m.name for m in body.data.materials]
    bP = [OWb @ v.co for v in body.data.vertices]
    polys = [list(pl.vertices) for pl in body.data.polygons
             if bmats[pl.material_index] in scw['materials'] and min(bP[i].z for i in pl.vertices) < scw['z_max']]
    tree = BVHTree.FromPolygons([tuple(p) for p in bP], polys)
    bname = {g.index: g.name for g in body.vertex_groups}
    bW = [{bname[e.group]: e.weight for e in v.groups} for v in body.data.vertices]
    d0, d1 = scw['full'], scw['none']
    n = 0
    for v in sk.data.vertices:
        p = OWs @ v.co
        q, nrm, fi, dist = tree.find_nearest(p, d1)
        if q is None:
            continue
        c = 1.0 if dist <= d0 else 1.0 - (dist - d0) / (d1 - d0)
        c = c * c * (3 - 2 * c)
        if c <= 1e-3:
            continue
        pv = polys[fi]
        # inverse-distance weights of the polygon corners at the closest point
        ws = [1.0 / max((bP[i] - q).length, 1e-6) for i in pv]; sw_ = sum(ws)
        tgt = {}
        for i, wi in zip(pv, ws):
            for g_, x in bW[i].items():
                tgt[g_] = tgt.get(g_, 0.0) + x * wi / sw_
        cur = {sk.vertex_groups[e.group].name: e.weight for e in v.groups}
        out = {g_: (1 - c) * cur.get(g_, 0.0) + c * tgt.get(g_, 0.0) for g_ in set(cur) | set(tgt)}
        tot = sum(out.values())
        for g_, x in out.items():
            grp = sk.vertex_groups.get(g_) or sk.vertex_groups.new(name=g_)
            if x / tot > 1e-4:
                grp.add([v.index], x / tot, 'REPLACE')
            elif g_ in cur:
                grp.remove([v.index])
        n += 1
    report['skirtContact'] = n

# Sleeves: modelled in the T pose, their puffy inner side lies inside the torso, the waist and the
# skirt top once the arms come down. For a set of arms-down poses, sleeve vertices found inside
# (or closer than a small gap to) those surfaces are moved out in the rest shape through the
# inverse of their skinning transform, so in those poses the sleeve lies against the body as if
# pressed. "Inside" is measured radially from the surface's bone axis (mesh winding is not
# consistent). Offsets are smoothed over the sleeve and stay zero at the shoulder and cuff seams.
sf = cfg.get('sleeve_fit')
if sf:
    body = bpy.data.objects['Body']; me = body.data; OWb = body.matrix_world.copy(); O3i = OWb.to_3x3().inverted()
    nV = len(me.vertices)
    gname = {g.index: g.name for g in body.vertex_groups}
    mats = [m.name for m in me.materials]
    vmat = np.full(nV, -1)
    for poly in me.polygons:
        for vi in poly.vertices:
            vmat[vi] = poly.material_index
    def dom(v):
        return gname[max(v.groups, key=lambda e: e.weight).group] if v.groups else ''
    HANDB = ('hand', 'thumb', 'index', 'middle', 'ring', 'little')
    def region(v):
        m = mats[vmat[v.index]] if vmat[v.index] >= 0 else ''
        d = dom(v)
        if m in ('Material_upper_body', 'Material_hand', 'Material_hand_tpl'):     # hands count as upper body
            if d.startswith(HANDB): return 'hand'
            if d.startswith(('upper_arm', 'lower_arm')): return 'sleeve' + d[-1]
            return 'torso'
        if m == 'Material_lower_body':
            return 'leg' if d.startswith(('upper_leg', 'lower_leg', 'foot', 'toes')) else 'waist'
        return 'acc'
    REG = [region(v) for v in me.vertices]
    co0 = np.array([v.co[:] for v in me.vertices])
    W0 = OWb @ Matrix.Identity(4)
    Pw0 = np.array([(OWb @ v.co)[:] for v in me.vertices])
    # welded adjacency (duplicate vertices at the same position count as one)
    from mathutils import kdtree
    kd = kdtree.KDTree(nV)
    for i in range(nV): kd.insert(Pw0[i], i)
    kd.balance()
    weld = np.arange(nV)
    for i in range(nV):
        for (c_, j, d_) in kd.find_range(Pw0[i], 1e-6):
            if j < weld[i]: weld[i] = j
    nbr = [set() for _ in range(nV)]
    for e in me.edges:
        a, b = weld[e.vertices[0]], weld[e.vertices[1]]
        if a != b: nbr[a].add(b); nbr[b].add(a)
    def ring_set(pred, rings):
        front = {int(weld[i]) for i in range(nV) if pred(i)}
        seen = set(front)
        for _ in range(rings):
            front = {u for v_ in front for u in nbr[v_]} - seen; seen |= front
        return seen
    # region polygons and their open edges (B surfaces)
    def region_polys(rname, obj=None):
        if obj is not None:
            return [list(p.vertices) for p in obj.data.polygons]
        out = []
        for poly in me.polygons:
            rs = [REG[i] for i in poly.vertices]
            if max(set(rs), key=rs.count) == rname:
                out.append(list(poly.vertices))
        return out
    def open_edges(polys, wmap):
        cnt = {}
        for pv in polys:
            for a, b in zip(pv, pv[1:] + pv[:1]):
                k = (min(wmap[a], wmap[b]), max(wmap[a], wmap[b])); cnt[k] = cnt.get(k, 0) + 1
        return {k for k, c in cnt.items() if c == 1}
    sk = bpy.data.objects[SKIRT_MESH]
    skw = np.arange(len(sk.data.vertices))
    B = {}
    for rname in sf['targets']:
        if rname == 'skirt':
            polys = region_polys(None, sk); B[rname] = dict(obj=sk, polys=polys, open=open_edges(polys, skw), wmap=skw)
        else:
            polys = region_polys(rname); B[rname] = dict(obj=body, polys=polys, open=open_edges(polys, weld), wmap=weld)
    def posed_world(obj):
        dg = bpy.context.evaluated_depsgraph_get(); ev = obj.evaluated_get(dg); m = ev.to_mesh()
        P = np.empty(len(m.vertices) * 3); m.vertices.foreach_get('co', P); ev.to_mesh_clear()
        M = np.array(obj.matrix_world); return P.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    def axis_pts(rname):
        hd = lambda b: RW @ rig.pose.bones[b].head
        if rname == 'skirt':
            h = hd('hips'); return [h + Vector((0, 0, 0.3)), h - Vector((0, 0, 0.7))]
        return [hd(b) for b in (['hips', 'spine', 'chest', 'upperChest', 'neck'] if rname == 'torso' else ['hips', 'spine', 'chest'])]
    def closest_axis(q, pts):
        best = None
        for a, b in zip(pts, pts[1:]):
            ab = b - a; t = max(0.0, min(1.0, (q - a).dot(ab) / max(ab.length_squared, 1e-12))); c = a + ab * t
            if best is None or (q - c).length < (q - best).length: best = c
        return best
    def seg_dist(q, a, b):
        ab = b - a; t = max(0.0, min(1.0, (q - a).dot(ab) / max(ab.length_squared, 1e-12))); return (q - (a + ab * t)).length
    def set_arm_pose(down, swing, flex):
        for pb in rig.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        for s_, sg in (('L', 1), ('R', -1)):
            for bn, R in ((f'upper_arm.{s_}', Matrix.Rotation(math.radians(-swing), 4, 'X') @ Matrix.Rotation(math.radians(sg * down), 4, 'Y')),
                          (f'lower_arm.{s_}', Matrix.Rotation(math.radians(-flex), 4, 'X'))):
                pb = rig.pose.bones[bn]; h = RW @ pb.head
                pb.matrix = RW.inverted() @ Matrix.Translation(h) @ R @ Matrix.Translation(-h) @ RW @ pb.matrix
                bpy.context.view_layer.update()
    gidx = {g.name: g.index for g in body.vertex_groups}
    VW = [[(gname[e.group], e.weight) for e in v.groups if e.weight > 1e-5] for v in me.vertices]
    report_fit = {}
    O = np.zeros((nV, 3))   # object-space offsets
    act_all = [i for i in range(nV) if REG[i] in ('sleeveL', 'sleeveR')]
    pinned = ring_set(lambda i: REG[i] in ('torso', 'hand'), sf['seam_rings'])
    # bows, flowers and pearls sewn on the sleeve are separate small islands: they are not fitted
    # themselves but move rigidly with the sleeve surface under them
    comp = {}; islands = []
    act_set = {int(weld[i]) for i in act_all}
    for s0 in act_set:
        if s0 in comp:
            continue
        stack = [s0]; comp[s0] = len(islands); members = [s0]
        while stack:
            u = stack.pop()
            for w_ in nbr[u]:
                if w_ in act_set and w_ not in comp:
                    comp[w_] = len(islands); members.append(w_); stack.append(w_)
        islands.append(members)
    deco = set()
    for members in islands:
        if len(members) < sf['deco_max_verts']:
            deco.update(members)
    free_all = [i for i in act_all if int(weld[i]) not in pinned and int(weld[i]) not in deco]
    shell = np.array([i for i in act_all if int(weld[i]) not in deco])
    from mathutils import kdtree as _kd
    kd_shell = _kd.KDTree(len(shell))
    for k_, i in enumerate(shell): kd_shell.insert(Pw0[i], k_)
    kd_shell.balance()
    deco_islands = [[i for i in act_all if int(weld[i]) in set(m)] for m in islands if len(m) < sf['deco_max_verts']]
    deco_anchor = [[shell[k_] for (c_, k_, d_) in kd_shell.find_n(Vector(Pw0[isl].mean(0)), 6)] for isl in deco_islands]
    report_fit['decoIslands'] = len(deco_islands)
    free_mask = np.zeros(nV, bool); free_mask[free_all] = True
    for ps in range(sf['passes']):
        npush = 0; maxneed = 0.0
        for down, swing, flex in sf['poses']:
            set_arm_pose(down, swing, flex)
            Pb = posed_world(body)
            trees = {}
            for rname, bd in B.items():
                P_ = Pb if bd['obj'] == body else posed_world(bd['obj'])
                trees[rname] = (BVHTree.FromPolygons([tuple(x) for x in P_], bd['polys']), P_, axis_pts(rname))
            Mi = {pb.name: (RW @ pb.matrix @ rig.data.bones[pb.name].matrix_local.inverted() @ RW.inverted()).to_3x3() for pb in rig.pose.bones}
            for i in free_all:
                p = Vector(Pb[i]); best = None
                for rname, (tree, P_, axp) in trees.items():
                    q, nrm, fi, dist = tree.find_nearest(p, sf['reach'])
                    if q is None:
                        continue
                    bd = B[rname]; pv = bd['polys'][fi]; wm = bd['wmap']
                    if any((min(wm[a], wm[b]), max(wm[a], wm[b])) in bd['open'] and seg_dist(q, Vector(P_[a]), Vector(P_[b])) < 1e-5 for a, b in zip(pv, pv[1:] + pv[:1])):
                        continue
                    rr = q - closest_axis(q, axp)
                    if rr.length < 1e-5:
                        continue
                    rr.normalize(); d = (p - q).dot(rr); need = sf['gap'][rname] - d
                    if need > 0 and (best is None or need > best[0]):
                        best = (need, rr)
                if best:
                    A = Matrix(((0, 0, 0), (0, 0, 0), (0, 0, 0)))
                    for bn, w in VW[i]:
                        if bn in Mi:
                            A = A + Mi[bn] * w
                    try:
                        d_rest = A.inverted() @ (best[1] * best[0])
                    except ValueError:
                        continue
                    O[i] += np.array(O3i @ d_rest); npush += 1; maxneed = max(maxneed, best[0])
        # smooth over the sleeve; pinned and non-sleeve vertices hold zero
        for _ in range(sf['smooth']):
            On = O.copy()
            for i in free_all:
                nb = [j for j in nbr[weld[i]]]
                if nb:
                    On[i] = 0.5 * O[i] + 0.5 * O[nb].mean(0)
            O = On; O[~free_mask] = 0
            # duplicates follow their weld representative
            O = O[weld]
        # limits: total offset and compression towards the arm axis
        for i in free_all:
            ow = np.array(OWb.to_3x3() @ Vector(O[i])); L = np.linalg.norm(ow)
            if L > sf['max']:
                O[i] *= sf['max'] / L
        for side in ('L', 'R'):
            ax0 = [RW @ rig.data.bones[b].head_local for b in (f'upper_arm.{side}', f'lower_arm.{side}', f'hand.{side}')]
            for i in free_all:
                if REG[i] != 'sleeve' + side:
                    continue
                p0 = Vector(Pw0[i]); r0_ = min(seg_dist(p0, a, b) for a, b in zip(ax0, ax0[1:]))
                p1 = OWb @ Vector(co0[i] + O[i]); r1 = min(seg_dist(p1, a, b) for a, b in zip(ax0, ax0[1:]))
                if r1 < sf['min_radius_frac'] * r0_:
                    O[i] *= max(0.0, (r0_ - sf['min_radius_frac'] * r0_) / max(r0_ - r1, 1e-9))
        for isl, anc in zip(deco_islands, deco_anchor):
            O[isl] = O[anc].mean(0)
        for i in act_all:
            me.vertices[i].co = Vector(co0[i] + O[i])
        me.update()
        report_fit.setdefault('passes', []).append(dict(pushes=npush, maxNeedMm=round(maxneed * 1000, 1),
            maxOffsetMm=round(float(np.max(np.linalg.norm(O[act_all] * 1.0, axis=1)) * OWb.to_scale()[0] * 1000), 1)))
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    report['sleeveFit'] = report_fit

# =========================== 4. hair colliders ============================================
sb = rig.data.vrm_addon_extension.spring_bone1


def sphere(bone, world_center, radius):
    c = sb.colliders.add()
    c.uuid = uuid.uuid4().hex
    c.node.bone_name = bone
    c.shape_type = 'Sphere'
    c.reset_bpy_object(bpy.context, rig)
    parent = RW @ rig.pose.bones[bone].matrix
    c.shape.sphere.offset = parent.inverted() @ world_center
    c.shape.sphere.radius = radius
    return c.uuid


ids = []
for item in cfg['hair_colliders']:
    ids.append(sphere(item['bone'], Vector(item['center']), item['radius']))
g = sb.collider_groups.add()
g.uuid = uuid.uuid4().hex
g.vrm_name = 'Hair/HeadBody'
for i in ids:
    g.colliders.add().collider_uuid = i
report['hairColliders'] = len(ids)

# =========================== 4b. loose faces ===============================================
# Body pieces of one or two faces are debris: after the neck and head steps two triangles of the generated throat
# were left on their own, carrying eye weights, and showed under the chin through the neck transition (人物2, 11-25).
_bo = bpy.data.objects.get('Body')
if _bo is not None:
    _bmd = bmesh.new(); _bmd.from_mesh(_bo.data); _bmd.faces.ensure_lookup_table(); _seen3 = set(); _deb = []
    for f0_ in _bmd.faces:
        if f0_.index in _seen3: continue
        comp_ = {f0_.index}; st_ = [f0_]
        while st_ and len(comp_) <= 2:
            for e_ in st_.pop().edges:
                for g_ in e_.link_faces:
                    if g_.index not in comp_: comp_.add(g_.index); st_.append(g_)
        _seen3 |= comp_
        if len(comp_) <= 2: _deb += [_bmd.faces[i] for i in comp_]
    if _deb:
        bmesh.ops.delete(_bmd, geom=_deb, context='FACES')
        _bmd.to_mesh(_bo.data); _bo.data.update()
    _bmd.free()
    report['looseFacesRemoved'] = len(_deb)

# =========================== 5. MToon and save ============================================
meshes = [bpy.data.objects[n] for n in ['Body', 'Head'] + sorted(keep_meshes - {'Body', 'Head'}) if n in bpy.data.objects] + [hair]
mtoon.apply_mtoon(meshes)
for o in meshes:
    o.hide_render = False
bpy.context.view_layer.update()
spring_cfg = dict(
    armature=rig.name,
    chains=[dict(name=c['name'], bones=c['bones'], colliderGroups=['Hair/HeadBody'], **c['physics']) for c in hair_chains]
    + [dict(name=c['name'], bones=c['bones'], colliderGroups=[], **cfg['skirt']['physics']) for c in skirt_chains if cfg.get('skirt')]
    + [dict(name=c['name'], bones=c['bones'], colliderGroups=[], **cfg['ribbon']['physics']) for c in ribbon_chains if cfg.get('ribbon')]
    + [dict(name=c['name'], bones=c['bones'], colliderGroups=[], **cfg.get('earring', {}).get('physics', {})) for c in earring_chains],
    targets=[dict(mesh=hair.name, source='hair', mode='spring', chains=[c['name'] for c in hair_chains])]
    + ([dict(mesh='Spring_01_skirt', source='Spring_01_skirt', mode='spring', chains=[c['name'] for c in skirt_chains])] if skirt_chains else [])
    + ([dict(mesh=cfg['ribbon'].get('mesh', 'Spring_02_ribbon'), source=cfg['ribbon'].get('mesh', 'Spring_02_ribbon'), mode='spring', chains=[c['name'] for c in ribbon_chains])] if ribbon_chains else [])
    + ([dict(mesh='Head', source='head', mode='spring', chains=[c['name'] for c in earring_chains])] if earring_chains else []))
if FR:   # spring hit radii are lengths in the model's own frame
    for _c in spring_cfg['chains']:
        if 'hitRadius' in _c: _c['hitRadius'] = round(_c['hitRadius'] * FR['s'], 5)
Path(cfg['spring_config_out']).write_text(json.dumps(spring_cfg, ensure_ascii=False, indent=1), encoding='utf-8')
report['skirtChainBones'] = {c['name']: c['bones'] for c in skirt_chains}
# the double-eyelid line pieces get their own blended materials (one per eye), so closing the eye can fade them:
# closed, the line sits right above the lashes and the painted dark red reads as a cut (user, 11-13)
if cfg.get('crease'):
    _hd = bpy.data.objects['Head'].data
    _cc = json.loads(Path(cfg['crease']['components']).read_text())
    _src = next(m for m in _hd.materials if m and m.name.startswith('Material_head'))
    report['crease'] = {}
    for _side, _ci in cfg['crease']['pieces'].items():
        _m = _src.copy(); _m.name = 'Crease_' + _side
        if hasattr(_m, 'blend_method'): _m.blend_method = 'BLEND'
        if _m.vrm_addon_extension.mtoon1.enabled: _m.vrm_addon_extension.mtoon1.alpha_mode = 'BLEND'
        _hd.materials.append(_m); _slot = len(_hd.materials) - 1; _vs = set(_cc[_ci]); _n = 0
        for _p in _hd.polygons:
            if all(v in _vs for v in _p.vertices): _p.material_index = _slot; _n += 1
        report['crease'][_side] = _n
# round the jaw corners below the ears (see jaw_round.py)
if cfg.get('jaw_round'):
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('jaw_round', str(_face_module(cfg['jaw_round'].get('module'), 'jaw_round')))
    _jr = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_jr)
    report['jawRound'] = _jr.round_jaw(bpy.data.objects['Head'], cfg['jaw_round'])
# brows over the bangs: a copy of the brow pieces with its own material (see brow_overlay.py)
if cfg.get('brow_overlay'):
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('brow_overlay', str(_face_module(cfg['brow_overlay'].get('module'), 'brow_overlay')))
    _bo = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_bo)
    report['browOverlay'] = _bo.add_brow_overlay(bpy.data.objects['Head'], cfg['brow_overlay'])
# iris painted on the eyeball: its own layer, the white under it repainted (see iris_layer.py)
if cfg.get('iris_layer'):
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('iris_layer', str(Path(__file__).parent / 'face' / 'iris_layer.py'))
    _il = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_il)
    report['irisLayer'] = _il.add_iris_layer(bpy.data.objects['Head'], dict(cfg['iris_layer'], out_dir=str(Path(cfg['output_blend']).parent / 'retexture')))
    if not cfg.get('face_fx'):
        mtoon.apply_mtoon([bpy.data.objects['Head']])
# anime face effects as decals (see face_fx.py)
if cfg.get('face_fx'):
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('face_fx', str(_face_module(cfg['face_fx'].get('module'), 'face_fx')))
    _fx = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_fx)
    report['faceFx'] = _fx.add_fx(bpy.data.objects['Head'], bpy.data.objects.get(cfg['face_fx'].get('hair_object', 'Hair')), cfg['face_fx'])
    mtoon.apply_mtoon([bpy.data.objects['Head']])        # the decal materials were added after section 5; converted ones are kept
Path(cfg['report_out']).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
if FR:
    Mback = Mfr.inverted()
    for o in bpy.data.objects:
        if o.parent is None and o.type in ('MESH', 'ARMATURE', 'EMPTY'):
            o.matrix_world = Mback @ o.matrix_world
    for _c in rig.data.vrm_addon_extension.spring_bone1.colliders:     # offsets are already in armature space; radii are lengths
        if _c.shape_type == 'Sphere':
            _c.shape.sphere.radius *= FR['s']
        else:
            _c.shape.capsule.radius *= FR['s']
    bpy.context.view_layer.update()
    report['frameRestored'] = [list(map(lambda x: round(x, 6), r)) for r in rig.matrix_world]
r = bpy.ops.wm.save_as_mainfile(filepath=cfg['output_blend'], copy=True)
if 'FINISHED' not in r:
    raise RuntimeError('save failed')
print('BUILD_OK', json.dumps({k: v for k, v in report.items() if k in ('face', 'hairColliders')}))
