# Fit the MakeHuman (CC0) hands onto this character's rig, once, and save them for every build.
# usage: blender -b weighted.blend -P make_template_hand.py -- MH_DIR OUT_DIR
#   MH_DIR: base.obj, default.mhskel, default_weights.mhw (MakeHuman 1.x assets, CC0) + mh_raw.npz/mh_faces.json
#   OUT_DIR: template_hand.blend, hand-tpl-basecolor.png, template_hand.json (report)
# Each MakeHuman hand bone is mapped onto the matching bone of our rig: the template bone frame (axis + back-of-hand
# direction) is rotated onto ours, scaled along the bone to our bone length and across it by the knuckle-span ratio.
# Vertices blend those mappings with MakeHuman's own weights, so knuckles and the palm keep their shape. Finger
# lengths come from this character's own hand (farthest vertex of each fingertip), not from the bone tails.
import bpy, bmesh, json, sys, numpy as np
from pathlib import Path
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
MH, OUT = Path(argv[0]), Path(argv[1]); OUT.mkdir(parents=True, exist_ok=True)
_HD = MH if (MH / 'mh_raw.npz').is_file() else MH.parent / 'hand'
raw = np.load(_HD / 'mh_raw.npz'); V, VT = raw['V'], raw['VT']
F = [[tuple(c) for c in f] for f in json.load(open(_HD / 'mh_faces.json'))['faces']]
sk = json.load(open(MH / 'default.mhskel'))
J = {k: V[np.array(v)].mean(0) for k, v in sk['joints'].items()}
BH = {k: (J[b['head']], J[b['tail']]) for k, b in sk['bones'].items()}
MW = json.load(open(MH / 'default_weights.mhw'))['weights']

rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE'); RW = rig.matrix_world
body = bpy.data.objects['Body']; BW = body.matrix_world
bco = np.array([(BW @ v.co)[:] for v in body.data.vertices])
def ours(name):
    b = rig.data.bones[name]; return np.array((RW @ b.head_local)[:]), np.array((RW @ b.tail_local)[:])
def nrm(v): return v / np.linalg.norm(v)
def frame(x, dorsal):
    x = nrm(x); z = nrm(dorsal - x * dorsal.dot(x)); y = np.cross(z, x); return np.column_stack([x, y, z])

FINGERS = ['thumb', 'index', 'middle', 'ring', 'little']
OUR_J = ['proximal', 'intermediate', 'distal']
report = {}
hands = []
for side, sgn in (('L', 1.0), ('R', -1.0)):
    mh = lambda n: n + '.' + side
    # our fingertip: farthest vertex (along the distal bone) that the distal bone carries
    def tip(bn):
        h, t = ours(bn); d = nrm(t - h); g = body.vertex_groups[bn].index
        ids = [v.index for v in body.data.vertices if any(e.group == g and e.weight > 0.5 for e in v.groups)]
        proj = (bco[ids] - h) @ d if ids else np.array([np.linalg.norm(t - h)])
        return h + d * max(float(proj.max()), 0.6 * np.linalg.norm(t - h))
    Wo = ours('hand.' + side)[0]; Ko = ours('middle_proximal.' + side)[0]
    Io = ours('index_proximal.' + side)[0]; Lo = ours('little_proximal.' + side)[0]
    Wt = BH[mh('wrist')][0]; Kt = BH[mh('finger3-1')][0]; It = BH[mh('finger2-1')][0]; Lt = BH[mh('finger5-1')][0]
    dors_o = sgn * nrm(np.cross(Io - Lo, Ko - Wo)); dors_t = sgn * nrm(np.cross(It - Lt, Kt - Wt))
    k = np.linalg.norm(Io - Lo) / np.linalg.norm(It - Lt)          # metres per template unit across the hand
    maps = {}
    def add(mbones, Ht, xt, Ho, xo, sa):
        Ft, Fo = frame(xt, dors_t), frame(xo, dors_o); R = Fo @ Ft.T; ax = nrm(xt)
        S = sa * np.outer(ax, ax) + k * (np.eye(3) - np.outer(ax, ax))
        for b in mbones: maps[b] = (Ht, Ho, R @ S)
    elbow_o = ours('lower_arm.' + side)[0]
    add([mh('lowerarm01'), mh('lowerarm02')], Wt, Wt - BH[mh('lowerarm02')][0], Wo, Wo - elbow_o, k)
    add([mh('wrist')] + [mh(f'metacarpal{i}') for i in range(1, 5)], Wt, Kt - Wt, Wo, Ko - Wo,
        np.linalg.norm(Ko - Wo) / np.linalg.norm(Kt - Wt))
    fing_len = {}
    for fi, fn in enumerate(FINGERS):
        for ji, jn in enumerate(OUR_J):
            mb = mh(f'finger{fi + 1}-{ji + 1}'); ob = f'{fn}_{jn}.{side}'
            Ht, Tt = BH[mb]; Ho, To = ours(ob)
            if jn == 'distal': To = tip(ob)
            add([mb], Ht, Tt - Ht, Ho, To - Ho, np.linalg.norm(To - Ho) / np.linalg.norm(Tt - Ht))
            fing_len[ob] = round(float(np.linalg.norm(To - Ho)), 4)
    # vertices: weight mostly on the mapped bones, not more than 6 template cm up the forearm from the wrist
    fax = nrm(Wt - BH[mh('lowerarm02')][0])
    wsum = {}
    for b in maps:
        for vi, w in MW.get(b, []): wsum.setdefault(vi, {})[b] = w
    def keep(vi):
        ws = wsum.get(vi); return ws is not None and sum(ws.values()) >= 0.6 and (V[vi] - Wt) @ fax >= -0.6
    faces = [f for f in F if all(keep(c[0]) for c in f)]
    vids = sorted({c[0] for f in faces for c in f}); remap = {v: i for i, v in enumerate(vids)}
    P = np.zeros((len(vids), 3)); weights = []
    for i, vi in enumerate(vids):
        ws = wsum[vi]; tot = sum(ws.values()); p = np.zeros(3)
        for b, w in ws.items():
            Ht, Ho, M = maps[b]; p += (w / tot) * (Ho + M @ (V[vi] - Ht))
        P[i] = p; weights.append({b: w / tot for b, w in ws.items()})
    # MakeHuman bone -> our bone
    def our_name(b):
        n = b[:-2]
        if n.startswith('lowerarm'): return 'lower_arm.' + side
        if n == 'wrist' or n.startswith('metacarpal'): return 'hand.' + side
        fi, ji = int(n[6]) - 1, int(n[8]) - 1; return f'{FINGERS[fi]}_{OUR_J[ji]}.{side}'
    me = bpy.data.meshes.new('HandTpl_' + side); bm = bmesh.new()
    bv = [bm.verts.new(Vector(p)) for p in P]; bm.verts.ensure_lookup_table()
    for f in faces:
        try: bm.faces.new([bv[remap[c[0]]] for c in f])
        except ValueError: pass
    bm.normal_update(); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('HandTpl_' + side, me); bpy.context.scene.collection.objects.link(ob)
    for i, ws in enumerate(weights):
        agg = {}
        for b, w in ws.items(): agg[our_name(b)] = agg.get(our_name(b), 0) + w
        t = (V[vids[i]] - Wt) @ fax
        if t < -0.3: agg = {'lower_arm.' + side: 1.0}                           # the stub end stays with the forearm
        for g, w in agg.items():
            vg = ob.vertex_groups.get(g) or ob.vertex_groups.new(name=g); vg.add([i], float(w), 'REPLACE')
    hands.append(ob)
    report[side] = dict(verts=len(vids), faces=len(me.polygons), knuckle_scale=round(float(k), 5), finger_len=fing_len)

# one object, smart UV, ambient occlusion baked from the hand alone
bpy.ops.object.select_all(action='DESELECT')
for o in hands: o.select_set(True)
bpy.context.view_layer.objects.active = hands[0]; bpy.ops.object.join(); hand = bpy.context.view_layer.objects.active
hand.name = 'HandTpl'; hand.data.name = 'HandTpl'
for p in hand.data.polygons: p.use_smooth = True
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02); bpy.ops.object.mode_set(mode='OBJECT')
RES = 1024
ao_img = bpy.data.images.new('hand-ao', RES, RES, alpha=False); ao_img.colorspace_settings.name = 'Non-Color'
mat = bpy.data.materials.new('Material_hand_tpl'); mat.use_nodes = True
nt = mat.node_tree; tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = ao_img; nt.nodes.active = tex
hand.data.materials.clear(); hand.data.materials.append(mat)
scn = bpy.context.scene; scn.render.engine = 'CYCLES'; scn.cycles.samples = 96; scn.cycles.device = 'CPU'
scn.render.bake.margin = 8; scn.world = scn.world or bpy.data.worlds.new('W'); scn.world.light_settings.distance = 0.03
for o in bpy.data.objects:
    if o is not hand: o.hide_render = True
bpy.ops.object.select_all(action='DESELECT'); hand.select_set(True); bpy.context.view_layer.objects.active = hand
bpy.ops.object.bake(type='AO')
ao = np.array(ao_img.pixels[:]).reshape(RES, RES, 4)[..., 0]

# colour: skin tone, AO darkening with warmer shadows, nails on the back of each fingertip
skin = np.array([0.945, 0.753, 0.745])                                          # same target as the build's hand_skin
uvl = hand.data.uv_layers.active.data
def raster(polys):
    M = np.zeros((RES, RES), bool)
    for p in polys:
        q = [(uvl[li].uv[0] * RES, uvl[li].uv[1] * RES) for li in p.loop_indices]
        for t in range(1, len(q) - 1):
            (x0, y0), (x1, y1), (x2, y2) = q[0], q[t], q[t + 1]
            xa, xb = int(max(0, min(x0, x1, x2))), int(min(RES - 1, max(x0, x1, x2)) + 1)
            ya, yb = int(max(0, min(y0, y1, y2))), int(min(RES - 1, max(y0, y1, y2)) + 1)
            gx, gy = np.meshgrid(np.arange(xa, xb) + .5, np.arange(ya, yb) + .5)
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-12: continue
            a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den; b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
            M[ya:yb, xa:xb] |= (a >= -.01) & (b >= -.01) & (a + b <= 1.01)
    return M
HW = hand.matrix_world; hco = np.array([(HW @ v.co)[:] for v in hand.data.vertices])
nail_polys = []
for side in ('L', 'R'):
    sgn = 1.0 if side == 'L' else -1.0
    Wo = ours('hand.' + side)[0]; Ko = ours('middle_proximal.' + side)[0]
    Io = ours('index_proximal.' + side)[0]; Lo = ours('little_proximal.' + side)[0]
    dors = sgn * nrm(np.cross(Io - Lo, Ko - Wo))
    for fn in FINGERS:
        bn = f'{fn}_distal.{side}'; g = hand.vertex_groups[bn].index; h, _ = ours(bn)
        L = report[side]['finger_len'][bn]; ax = nrm(ours(bn)[1] - h)
        dd = dors if fn != 'thumb' else nrm(dors + sgn * 0.0 * ax)
        ids = np.array([v.index for v in hand.data.vertices if any(e.group == g and e.weight > 0.6 for e in v.groups)])
        if len(ids) == 0: continue
        rel = hco[ids] - h; t = rel @ ax; perp = rel - np.outer(t, ax)
        if fn == 'thumb':                                                       # the thumb nail faces away from the palm side
            dd = nrm(perp[np.argmax(perp @ dors)] if len(perp) else dors)
        up = perp @ dd; r = np.linalg.norm(perp, axis=1).max()
        sel = set(ids[(t > 0.42 * L) & (up > 0.45 * r)].tolist())
        nail_polys += [p for p in hand.data.polygons if all(vi in sel for vi in p.vertices)]
nail = raster(nail_polys)
def blur(A, r):
    A = A.astype(np.float32)
    for ax in (0, 1):
        c = np.cumsum(np.pad(A, [(r + 1, r) if i == ax else (0, 0) for i in range(A.ndim)], mode="edge"), axis=ax)
        A = (np.take(c, range(2 * r + 1, c.shape[ax]), axis=ax) - np.take(c, range(0, c.shape[ax] - 2 * r - 1), axis=ax)) / (2 * r + 1)
    return A
covered = raster(hand.data.polygons)
aos = np.where(covered, ao, 1.0)
shade = 0.76 + 0.24 * np.clip(aos, 0, 1) ** 1.3                                   # finger gaps, palm creases, wrist (light: 11-17 the hand read tan next to the face)
warm = np.array([1.0, 0.86, 0.88])                                                # shadows lean pink, not grey
col = skin[None, None, :] * (shade[..., None] * (1 - (1 - shade[..., None]) * (1 - warm)))
nm = blur(nail, 2); rim = np.clip(blur(nail, 4) - nm, 0, 1)
nail_col = np.array([1.0, 0.90, 0.90])
col = col * (1 - 0.75 * nm[..., None]) + nail_col * 0.75 * nm[..., None]
col = col * (1 - 0.25 * rim[..., None]) + skin * np.array([0.86, 0.66, 0.68]) * 0.25 * rim[..., None]
# bleed past the islands so mip maps do not pull in black
fill = covered.copy(); out = col.copy()
for _ in range(10):
    grown = blur(fill.astype(np.float32), 1) > 0
    acc = blur(out * fill[..., None], 1); cnt = blur(fill.astype(np.float32), 1)
    new = grown & ~fill; out[new] = (acc[new] / np.maximum(cnt[new, None], 1e-6)); fill = grown
out[~fill] = skin
img = bpy.data.images.new('hand-tpl-basecolor', RES, RES, alpha=True)
px = np.ones((RES, RES, 4), np.float32); px[..., :3] = np.clip(out, 0, 1)
img.pixels.foreach_set(px.ravel()); img.filepath_raw = str(OUT / 'hand-tpl-basecolor.png'); img.file_format = 'PNG'; img.save()
img.source = 'FILE'; img.filepath = str(OUT / 'hand-tpl-basecolor.png'); img.reload(); img.pack()
tex.image = img
bsdf = nt.nodes.get('Principled BSDF'); nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color']); bsdf.inputs['Roughness'].default_value = 0.8
for o in list(bpy.data.objects):
    if o is not hand: bpy.data.objects.remove(o, do_unlink=True)
report['nail_faces'] = len(nail_polys); report['texture'] = str(OUT / 'hand-tpl-basecolor.png')
json.dump(report, open(OUT / 'template_hand.json', 'w'), indent=1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'template_hand.blend'))
print('TEMPLATE_HAND_OK', json.dumps({s: {k: v for k, v in report[s].items() if k != 'finger_len'} for s in ('L', 'R')}), 'nails', len(nail_polys))
