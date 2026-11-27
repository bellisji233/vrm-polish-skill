"""Measure a Charakuru weight result for the polish build: head frame, neck, colliders, fingers, waist, sleeves,
mesh pieces (skin / cloth) and spring parts.

usage: blender -b PROJECT/work/weights/weighted.blend --python measure.py -- PROFILE_DIR OUT.json

All positions are in the head profile's frame (x_profile = (x - t) / s), the frame the build runs in.
Rules were fitted on two finished bodies (purple dress, lavender denim) whose settings were tuned by eye;
measure.json records the raw numbers next to each derived value so a reviewer can see where it came from.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

PROFILE, OUT = sys.argv[sys.argv.index('--') + 1:][:2]
PROFILE = Path(PROFILE)
prof = json.loads((PROFILE / 'profile.json').read_text(encoding='utf-8'))
res = {'profile': str(PROFILE)}
r4 = lambda v: [round(float(x), 4) for x in v]

rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.name.startswith('CharaKit_Weights_') and o.name.endswith('_Rig'))
res['rig'] = rig.name
res['collection'] = rig.users_collection[0].name if rig.users_collection else rig.name[:-4]

# ---------------------------------------------------------------- head frame
# Same head as the profile (same mesh): fit vertex to vertex. Another head: find its parts and face landmarks
# (polish/face/locate.py), fit the landmarks to the profile's, and write this head's own part data to work/measure/.
import importlib.util, os
head = bpy.data.objects['Head']
X = np.array([(head.matrix_world @ v.co)[:] for v in head.data.vertices])
# a starter profile (assets/head-profile) carries no head mesh: every head is a new head for it
R = np.load(PROFILE / 'head_rest.npy') if (PROFILE / 'head_rest.npy').is_file() else np.zeros((0, 3))
s, t = 1.0, np.zeros(3)
if len(X) == len(R) and not os.environ.get('POLISH_FORCE_NEW_HEAD'):
    Rm, Xm = R.mean(0), X.mean(0)
    s = float(((R - Rm) * (X - Xm)).sum() / ((R - Rm) ** 2).sum())
    t = Xm - s * Rm
    rms = float(np.sqrt(((s * R + t - X) ** 2).sum(1).mean()))
    res['head_fit_rms_mm'] = round(rms * 1000, 3)
    res['same_head'] = rms < 0.002 * s
else:
    res['same_head'] = False
if res['same_head']:
    res['frame'] = {'s': round(s, 5), 't': [round(float(x), 5) for x in t]}
    if abs(s - 1) < 1e-4 and np.abs(t).max() < 1e-4:
        res['frame'] = None
elif 'landmarks' in prof:
    _sp = importlib.util.spec_from_file_location('polish_locate', Path(__file__).resolve().parents[1] / 'face' / 'locate.py')
    loc = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(loc)
    kit = os.environ.get('KIT') or str(Path(bpy.data.filepath).resolve().parents[4])
    comps_h, bounds_h = loc.kit_parts(kit, head.data)
    vcol_h, _, _ = loc.vertex_colours(head)
    found = loc.locate(X, comps_h, bounds_h, vcol_h)
    fr, err = loc.fit_frame(found['landmarks'], prof['landmarks'])
    s, t = fr['s'], np.array(fr['t'])
    res['frame'] = fr
    res['new_head'] = {'roles': found['roles'], 'landmarks': found['landmarks'], 'landmark_error_m': err}
    # this head's own skin colour (the profile's face tone belongs to another character)
    res['new_head']['face_tone'] = [round(float(x), 4) for x in np.median(vcol_h[comps_h[found['roles']['skin']]], axis=0)]
    MD = Path(OUT).parent
    json.dump(comps_h, open(MD / 'head-components.json', 'w'))
    rl = found['roles']
    json.dump(sorted([dict(n=len(lv), vs=lv) for lv in bounds_h[rl['skin']]], key=lambda d: -d['n']), open(MD / 'head-skin-boundaries.json', 'w'))
    # cheek crease: convex folds of the skin near the profile's crease line (carried into this head's frame)
    import bmesh as _bmesh
    from mathutils.kdtree import KDTree as _KD
    Xf = (X - t) / s
    prior = np.array(prof.get('crease_prior', []))
    pairs = []
    if len(prior):
        kd = _KD(len(prior))
        for i_, p_ in enumerate(prior): kd.insert(p_, i_)
        kd.balance()
        skin_set = set(comps_h[rl['skin']])
        hb = _bmesh.new(); hb.from_mesh(head.data)
        for e in hb.edges:
            a_, b_ = e.verts[0].index, e.verts[1].index
            if a_ not in skin_set or b_ not in skin_set or len(e.link_faces) != 2 or e.calc_face_angle_signed() <= 0:
                continue
            if math.degrees(e.calc_face_angle()) < 8:
                continue
            if kd.find((Xf[a_] + Xf[b_]) / 2)[2] < 0.004:
                pairs.append([a_, b_])
        hb.free()
    json.dump({'pairs': pairs}, open(MD / 'crease-pairs.json', 'w'))
    res['new_head']['crease_edges'] = len(pairs)
    # this head's own assembly -> world transform (places its hair)
    asm = Path(bpy.data.filepath).resolve().parents[1] / 'assembly.blend'
    with bpy.data.libraries.load(str(asm), link=False) as (_src, _dst):
        _dst.objects = ['Head', 'Hair']
    ah = _dst.objects[0]
    for _slot in (_dst.objects[1].material_slots if _dst.objects[1] else []):
        for _nd in (_slot.material.node_tree.nodes if _slot.material and _slot.material.use_nodes else []):
            if _nd.type == 'TEX_IMAGE' and _nd.image:
                if _nd.image.packed_file is not None and tuple(_nd.image.size) == (4096, 4096):
                    res['new_head']['hair_packed'] = True          # the build uses the assembly's own 4K hair image
                _fp = Path(bpy.path.abspath(_nd.image.filepath, start=str(asm.parent))).resolve() if _nd.image.filepath else None
                if _fp and _fp.is_file():
                    res['new_head']['hair_texture'] = str(_fp)
    Aa = np.array([(ah.matrix_world @ v.co)[:] for v in ah.data.vertices])
    if len(Aa) == len(X):
        Am_, Xm_ = Aa.mean(0), X.mean(0)
        S_ = float(((Aa - Am_) * (X - Xm_)).sum() / ((Aa - Am_) ** 2).sum()); T_ = Xm_ - S_ * Am_
        np.save(MD / 'head_affine_own.npy', np.vstack([np.eye(3) * S_, T_[None, :]]))
        res['new_head']['own_affine'] = {'S': round(S_, 5), 'T': r4(T_)}
    bpy.data.objects.remove(ah, do_unlink=True)
else:
    res['head_note'] = 'not the profile head, and the profile has no landmarks (make it again with make_profile.py)'
if res.get('frame'):
    M = Matrix.Diagonal((1 / s, 1 / s, 1 / s, 1.0)) @ Matrix.Translation(-Vector(tuple(t)))
    for o in bpy.data.objects:
        if o.parent is None and o.type in ('MESH', 'ARMATURE', 'EMPTY'):
            o.matrix_world = M @ o.matrix_world
    bpy.context.view_layer.update()

RW = rig.matrix_world
bone = {b.name: np.array((RW @ b.head_local)[:]) for b in rig.data.bones}
tail = {b.name: np.array((RW @ b.tail_local)[:]) for b in rig.data.bones}
res['bones'] = {n: r4(bone[n]) for n in ('hips', 'spine', 'chest', 'upperChest', 'neck', 'head', 'shoulder.L', 'shoulder.R',
                                        'upper_arm.L', 'upper_arm.R', 'lower_arm.L', 'lower_arm.R', 'hand.L', 'hand.R', 'upper_leg.L')}
span = float(bone['upper_arm.L'][0] - bone['upper_arm.R'][0])
k = span / 0.2372                     # body scale against the purple body the offsets were taken from
res['body_scale'] = round(k, 4)

body = bpy.data.objects['Body']
BW = body.matrix_world
dg = bpy.context.evaluated_depsgraph_get()
me = body.evaluated_get(dg).to_mesh()
tree = BVHTree.FromPolygons([(BW @ v.co) for v in me.vertices], [p.vertices for p in me.polygons])

# ---------------------------------------------------------------- neck
# The flare starts just under the lowest point of the head (both tuned bodies: within 5 mm of chin + 2 mm); the
# straight part starts at the front collar, so its lower edge stays covered. The axis is the centre of the neck
# section at the flare height.
def ring(cx, cy, z, n=72):
    hits = []
    for i in range(n):
        th = 2 * math.pi * i / n
        h = tree.ray_cast(Vector((cx, cy, z)), Vector((math.sin(th), math.cos(th), 0)), 0.12 * k)
        if h[0] is None:
            return None
        hits.append((h[0].x, h[0].y))
    return np.array(hits)
def centre_at(z):
    c = bone['neck'][:2].copy()
    for _ in range(4):
        h = ring(c[0], c[1], z)
        if h is None:
            return None, None
        c = h.mean(0)
    return c, np.linalg.norm(h - c, axis=1)
chin = float(min((head.matrix_world @ v.co).z for v in head.data.vertices))
top = None
z = bone['neck'][2] + 0.005 * k
while z < chin + 0.06 * k:
    c, rr = centre_at(z)
    if c is None or rr.max() > 0.08 * k:
        break
    top = z; z += 0.0025 * k
if top is None:
    raise SystemExit('neck: no closed neck section above the neck joint')
zf = min(chin + 0.002 * k, top - 0.005 * k)
cf, rr = centre_at(zf)
# ---------------------------------------------------------------- hair colliders on the body (offsets from purple)
OFF = {'neck': ((0.0, -0.0002, 0.0132), 0.045), 'upperChest': ((0.0, 0.0069, 0.0218), 0.085),
       'shoulder.L': ((0.0124, 0.0022, -0.012), 0.04), 'shoulder.R': ((-0.0127, 0.0022, -0.012), 0.04)}
res['hair_colliders'] = [{'bone': b, 'center': r4(bone[b] + k * np.array(o)), 'radius': round(rad * k, 4)} for b, (o, rad) in OFF.items()]

# ---------------------------------------------------------------- fingers, waist
prox = [abs(bone[f'{f}_proximal.{sd}'][0]) for f in ('index', 'middle', 'ring', 'little') for sd in ('L', 'R')]
res['finger_clean'] = {'x_min': round(max(prox) + 0.005 * k, 4), 'dominant': 0.5, 'min_bleed': 0.02}
res['waist_blend'] = {'z': [round(bone['hips'][2] + 0.03 * k, 3), round(bone['spine'][2] + 0.035 * k, 3)]}

# ---------------------------------------------------------------- texture colours of faces, mesh pieces
bm = bmesh.new(); bm.from_mesh(body.data); bm.faces.ensure_lookup_table(); uvl = bm.loops.layers.uv.active
mats = [m.name if m else '' for m in body.data.materials]
imgs = {}
def image_of(mi):
    if mi not in imgs:
        arr = None
        mat = body.data.materials[mi]
        for n in (mat.node_tree.nodes if mat and mat.use_nodes else []):
            if n.type == 'TEX_IMAGE' and n.image and n.image.has_data:
                im = n.image; arr = np.empty(im.size[0] * im.size[1] * 4, np.float32); im.pixels.foreach_get(arr)
                arr = arr.reshape(im.size[1], im.size[0], 4); break
        imgs[mi] = arr
    return imgs[mi]
def colour(f):
    a = image_of(f.material_index)
    if a is None:
        return np.array([0.5, 0.5, 0.5])
    H, W = a.shape[:2]
    u = np.mean([l[uvl].uv.x for l in f.loops]); v = np.mean([l[uvl].uv.y for l in f.loops])
    x = int(np.clip((u % 1) * W, 0, W - 1)); y = int(np.clip((v % 1) * H, 0, H - 1))
    return a[max(0, y - 2):y + 3, max(0, x - 2):x + 3, :3].reshape(-1, 3).mean(0)
tone = np.array((res.get('new_head') or {}).get('face_tone') or prof.get('face_tone', [0.945, 0.753, 0.745]))
def skin_like(c):
    return c.mean() > 0.45 and np.abs(c / c.sum() - tone / tone.sum()).max() < 0.035
isl = [-1] * len(bm.faces); n_isl = 0
for f in bm.faces:
    if isl[f.index] >= 0: continue
    st = [f]; isl[f.index] = n_isl
    while st:
        g = st.pop()
        for e in g.edges:
            for h in e.link_faces:
                if isl[h.index] < 0: isl[h.index] = n_isl; st.append(h)
    n_isl += 1
ctr = np.array([(BW @ f.calc_center_median())[:] for f in bm.faces])
members = {}
for f in bm.faces: members.setdefault(isl[f.index], []).append(f)
def nearest_island(p):
    return isl[int(np.argmin(((ctr - p) ** 2).sum(1)))]
def front_point(x, z, back=False):
    o = Vector((x, 0.6 if back else -0.6, z)); d = Vector((0, -1 if back else 1, 0))
    h = tree.ray_cast(o, d, 1.2)
    return None if h[0] is None else np.array(h[0][:]) + np.array([0, 0.01 if back else -0.01, 0])
cx = float(bone['hips'][0])
ul = bone['upper_leg.L']; ll = bone['lower_leg.L']
sites = {
    'neck': np.array([cf[0], cf[1], zf + 0.025 * k]),
    'chest': front_point(cx, bone['chest'][2] + 0.07 * k),
    'belly': front_point(cx, bone['spine'][2] - 0.01 * k),
    'back': front_point(cx, bone['chest'][2] + 0.05 * k, back=True),
    'hip': front_point(cx, bone['hips'][2] - 0.04 * k),
    'thigh': front_point(ul[0], ul[2] - 0.6 * (ul[2] - ll[2])),
    'shin': front_point(ll[0], ll[2] - 0.4 * (ll[2] - bone['foot.L'][2])),
    'upper_arm': np.array([(bone['upper_arm.L'][0] + bone['lower_arm.L'][0]) / 2, bone['upper_arm.L'][1], bone['upper_arm.L'][2] + 0.06 * k]),
    'forearm': np.array([(bone['lower_arm.L'][0] + bone['hand.L'][0]) / 2, bone['lower_arm.L'][1], bone['lower_arm.L'][2] + 0.05 * k]),
}
pieces = {}
for name, p in sites.items():
    if p is None:
        continue
    ii = nearest_island(p)
    fs = members[ii]
    cols = [colour(f) for f in fs[:: max(1, len(fs) // 1500)]]
    frac = float(np.mean([skin_like(c) for c in cols]))
    warm = float(np.mean([c[0] - c[2] > 0.03 and c.mean() >= 0.42 for c in cols]))   # faces region_paint cloth would repaint
    b0, b1 = ctr[[f.index for f in fs]].min(0), ctr[[f.index for f in fs]].max(0)
    e = pieces.setdefault(ii, {'island': ii, 'sites': [], 'faces': len(fs), 'skin_fraction': round(frac, 3), 'warm_fraction': round(warm, 3),
                                'bounds': [r4(b0), r4(b1)], 'point': r4(p), 'materials': sorted({mats[f.material_index] for f in fs})})
    e['sites'].append(name)
neck_isl = nearest_island(sites['neck'])
for e in pieces.values():
    (x0, y0, z0), (x1, y1, z1) = e['bounds']
    # the neck stump piece: skin by position (inside the collar, around the neck axis) and mostly skin-coloured
    e['auto'] = 'skin' if e['island'] == neck_isl and x1 - x0 < 0.2 * k and z0 > bone['upperChest'][2] and e['skin_fraction'] > 0.6 else None
    # a cool-coloured garment where warm faces are rare: those faces are skin colour projected onto it (hem, cuff, hood edges)
    if e['auto'] is None and e['faces'] > 500 and e['skin_fraction'] < 0.05 and e['warm_fraction'] < 0.1:
        e['auto'] = 'cloth'
# a belt: the top of a garment piece is mostly dark while the rest is not -> one colour band (region_paint.band)
for e in pieces.values():
    if e['auto'] != 'cloth':
        continue
    fs = members[e['island']]
    zc = ctr[[f.index for f in fs], 2]
    dark = np.array([colour(f).mean() < 0.42 for f in fs])
    top = zc.max(); bins = []
    for z0 in np.arange(top - 0.12 * k, top, 0.01 * k):
        m_ = (zc >= z0) & (zc < z0 + 0.01 * k)
        bins.append((round(float(z0), 3), float(dark[m_].mean()) if m_.sum() > 20 else 0.0))
    rest = float(dark[zc < top - 0.12 * k].mean()) if (zc < top - 0.12 * k).any() else 1.0
    # the run of mostly-dark bins closest to the top (a waistband edge may sit above it)
    run = []
    for z0, fr in reversed(bins):
        if fr > 0.3:
            run.append(z0)
        elif run:
            break
    e['band_scan'] = {'bins': [[z0, round(fr, 2)] for z0, fr in bins], 'rest': round(rest, 3)}
    if run and top - max(run) < 0.045 * k and max(fr for z0, fr in bins if z0 in run) > 0.45 and rest < 0.1:
        e['band'] = {'z_min': round(min(run) - 0.02 * k, 3), 'dark_below_band': round(rest, 3)}
res['pieces'] = list(pieces.values())
# small separate pieces around the neck base (necklace beads, pendants): listed for a look, never painted automatically
small = [ii for ii, fs in members.items() if len(fs) <= 150 and ii not in pieces]
near_neck = [ii for ii in small if all(np.hypot(ctr[f.index][0] - cf[0], ctr[f.index][1] - cf[1]) < 0.09 * k
                                       and bone['upperChest'][2] < ctr[f.index][2] < zf for f in members[ii])]
if near_neck:
    pts = ctr[[f.index for ii in near_neck for f in members[ii]]]
    res['neck_accessory'] = {'pieces': len(near_neck), 'box': [r4([pts[:, i].min() - 0.005, pts[:, i].max() + 0.005]) for i in range(3)]}

# straight part of the neck sleeve starts under the front collar (faces of other pieces close around the neck)
d_ax = np.hypot(ctr[:, 0] - cf[0], ctr[:, 1] - cf[1])
ang = np.degrees(np.arctan2(ctr[:, 0] - cf[0], ctr[:, 1] - cf[1]))
not_neck = np.array([isl[i] != neck_isl for i in range(len(isl))])
near = not_neck & (d_ax > 0.02 * k) & (d_ax < 0.075 * k) & (ctr[:, 2] > bone['upperChest'][2]) & (ctr[:, 2] < zf + 0.06 * k)
front = near & (np.abs(ang) > 150)
collar = float(ctr[front, 2].max()) if front.any() else zf - 0.03 * k
res['neck'] = {'chin_z': round(chin, 4), 'closed_up_to': round(top, 4), 'front_collar_top': round(collar, 4),
               'radius': round(float(np.median(rr)), 4)}
res['neck_loft'] = {'axis': [round(float(cf[0]), 4), round(float(cf[1]), 4)],
                    'z_neck': round(min(zf - 0.03 * k, collar - 0.002 * k), 4), 'z_flare': round(zf, 4)}

# ---------------------------------------------------------------- sleeves: forearm covered by cloth?
elbow_x, wrist_x = float(bone['lower_arm.L'][0]), float(bone['hand.L'][0])
fore = [f for f in bm.faces if elbow_x + 0.05 * k < abs(ctr[f.index][0]) < wrist_x - 0.02 * k]
fore_skin = float(np.mean([skin_like(colour(f)) for f in fore[:: max(1, len(fore) // 800)]])) if fore else 1.0
sleeve_mats = {}
for f in fore:
    sleeve_mats[mats[f.material_index]] = sleeve_mats.get(mats[f.material_index], 0) + 1
res['sleeves'] = {'forearm_faces': len(fore), 'forearm_skin_fraction': round(fore_skin, 3),
                  'long': len(fore) > 50 and fore_skin < 0.5,
                  'material': max(sleeve_mats, key=sleeve_mats.get) if sleeve_mats else None,
                  'min_abs_x': round(elbow_x - 0.06 * k, 3), 'delete_min_abs_x': round(wrist_x - 0.075 * k, 3)}

# ---------------------------------------------------------------- spring parts from the kit
# kind and name come from the kit's classification (work/classify.json): skirt, ribbon (a bow: knot then tails), strap.
# The swinging part starts this far down from the top of the part (fitted on the purple skirt and bow, denim strings).
ROOT = {'skirt': 0.15, 'ribbon': 0.35, 'strap': 0.15, 'other': 0.15}
groups = {}
cls = Path(bpy.data.filepath).parents[1] / 'classify.json'
if cls.is_file():
    for g in json.loads(cls.read_text(encoding='utf-8'))['classification'].get('springGroups', []):
        groups[g['id']] = g
springs = []
torso = ['hips', 'spine', 'chest', 'upperChest', 'neck']
for o in bpy.data.objects:
    if o.type == 'MESH' and o.name.startswith('Spring_') and o.parent == rig:
        P = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
        z0, z1 = float(P[:, 2].min()), float(P[:, 2].max())
        parent = max((b for b in torso if bone[b][2] <= z1), key=lambda b: bone[b][2], default='hips')
        g = groups.get(o.name.split('_', 2)[-1], {})
        kind = g.get('kind') or ('skirt' if 'skirt' in o.name.lower() else 'other')
        springs.append({'mesh': o.name, 'kind': kind, 'name': g.get('name', ''), 'z': [round(z0, 4), round(z1, 4)],
                        'z_root': round(z1 - ROOT.get(kind, 0.15) * (z1 - z0), 3), 'parent': parent, 'verts': len(P)})
res['springs'] = springs
bm.free()

# ---------------------------------------------------------------- trousers: one garment around both legs
# Vertices on the midline below the hip joints belong to a garment joining the legs (trousers, shorts): its crotch is
# measured for the crotch weights (build: crotch_blend). The kit gives those vertices to the legs only, unevenly
# left/right and with a hard step to the hips, so the crotch stretches when a leg lifts (人物2, 11-20).
_BP = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
_Lx, _Rx = float(bone['upper_leg.L'][0]), float(bone['upper_leg.R'][0]); _cx = 0.5 * (_Lx + _Rx); _hz = float(bone['upper_leg.L'][2])
_mid = (np.abs(_BP[:, 0] - _cx) < 0.15 * abs(_Lx - _Rx)) & (_BP[:, 2] < _hz) & (_BP[:, 2] > float(bone['lower_leg.L'][2]))
if _mid.sum() > 20:
    # the crotch reaches down at most 45 % of the thigh (a dropped crotch); midline vertices lower down are trouser
    # legs touching each other (wide legs at the knees), not the crotch
    _floor = _hz - 0.45 * (_hz - float(bone['lower_leg.L'][2]))
    _seam = float(_BP[_mid & (_BP[:, 2] >= _floor), 2].min()) if (_mid & (_BP[:, 2] >= _floor)).any() else _hz
    _mid &= _BP[:, 2] >= _seam
if _mid.sum() > 20:
    res['crotch'] = {'cx': round(_cx, 4), 'seam_z': round(float(_BP[_mid, 2].min()), 4), 'hip_z': round(_hz, 4),
                     'top_z': round(float(bone['hips'][2]), 4), 'half_span': round(0.75 * abs(_Lx - _Rx) / 2, 4), 'verts': int(_mid.sum())}

# ---------------------------------------------------------------- hands: keep the generated hand unless its fingers are fused
# Web between neighbouring fingers as a share of the first finger segment (0 knuckle, 1 middle knuckle). Natural hands
# and the three Tripo hands so far measure 0.3-0.4; above 0.6 the fingers read as fused and the template hand is used.
_spec = importlib.util.spec_from_file_location('finger_gap', Path(__file__).resolve().parents[1] / 'hand' / 'finger_gap.py')
_fg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_fg)
_hands = _fg.finger_gap(bpy.data.objects['Body'], rig)
_webs = [h_['web'] for h_ in _hands.values() if 'web' in h_]
res['hands'] = dict(_hands, fused=(not _webs) or max(_webs) > 0.6)
Path(OUT).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
print('MEASURE_OK ' + json.dumps({k_: res[k_] for k_ in ('same_head', 'frame', 'neck_loft', 'finger_clean', 'waist_blend', 'hands')}))
if res.get('new_head'):
    nh = res['new_head']
    print('NEW_HEAD ' + json.dumps({'landmark_error_mm': {k_: round(v_ * 1000, 1) for k_, v_ in nh['landmark_error_m'].items()},
                                   'crease_edges': nh['crease_edges'], 'own_affine': nh.get('own_affine')}))
