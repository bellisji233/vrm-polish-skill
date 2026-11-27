# All expression work for this model, run inside the expression studio on a fresh workspace (helper available).
# Parts were identified by eye from part renders (work/qa); vertex ids refer to the Head mesh of this model only.
import bpy, bmesh, json, math, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import os as _os
D_ = _os.environ['POLISH_HEAD_DATA'].rstrip('/') + '/'   # the head profile's expr-data (component ids, eye/mouth points)
_POLISH = _os.environ['POLISH_DIR']                         # this skill's polish/ folder
comps = json.load(open(D_ + 'components.json')); loops = json.load(open(D_ + 'skin_boundaries.json'))
spots = json.load(open(D_ + 'uvspots.json')); pts0 = np.load(D_ + 'points.npy')
N_ORIG = len(pts0)
h = bpy.data.objects['Head']; me = h.data
MW = np.array(h.matrix_world); M3 = MW[:3, :3]; M3i = np.linalg.inv(M3); T = MW[:3, 3]
wv = lambda v: M3i @ np.array(v, dtype=float)
UPPER_LASH = [3, 4]
LOWER_LASH = [28, 29, 33, 34, 36, 38, 41, 44, 46, 48, 50, 52, 54, 56, 27, 30, 32, 35, 37, 39, 40, 42, 45, 47, 49, 51, 55]
DOUBLE = {'R': 18, 'L': 19}
EYEBALL = {'R': [11, 15, 22, 25, 26], 'L': [12, 16, 20, 23, 24]}
IRIS = {'R': [15, 22, 25, 26], 'L': [16, 20, 23, 24]}
LINER = {'R': [31, 43, 57], 'L': [21]}   # dark eyeliner pieces under the lash strip: they ride with the lash
BROW = {'R': 13, 'L': 14}
SKIN = 1
SCLERA = {'R': 11, 'L': 12}
SKULL = 0
RIM_N = {'R': 34, 'L': 32}
RIM_VS = None
SCLERA_EXTRA = {'R': [], 'L': []}
PIECES = dict(lash=True, iris=True, brow=True)       # heads whose lashes, iris or brows are only painted: False
LM = None                                             # this head's face landmarks (new heads), profile frame
# Part roles found automatically (polish/profile/auto_head.py) replace the purple head's hand-picked ids above.
if _os.path.isfile(D_ + 'roles.json'):
    _rl = json.load(open(D_ + 'roles.json'))
    _st = _rl.get('structure', {})
    PIECES = dict(lash=_st.get('lash_pieces', True), iris=_st.get('iris_pieces', True), brow=_st.get('brow_pieces', True))
    UPPER_LASH = [_rl['upper_lash']['R'], _rl['upper_lash']['L']] if PIECES['lash'] else []
    LOWER_LASH = list(_rl['lower_lash'])
    DOUBLE = {s_: _rl['crease'][s_] for s_ in ('R', 'L') if s_ in _rl.get('crease', {})}
    SCLERA = dict(_rl['sclera'])
    SCLERA_EXTRA = {s_: list(_rl.get('sclera_extra', {}).get(s_, [])) for s_ in ('R', 'L')}
    IRIS = {s_: list(_rl['iris'][s_]) for s_ in ('R', 'L')}
    EYEBALL = {s_: [SCLERA[s_]] + SCLERA_EXTRA[s_] + IRIS[s_] for s_ in ('R', 'L')}
    LINER = {s_: list(_rl['liner'][s_]) for s_ in ('R', 'L')}
    BROW = dict(_rl['brow'])
    LM = _rl.get('landmarks')
    SKIN = _rl['skin']
    SKULL = _rl['skull']
    RIM_N = dict(_rl['rim_loop_n']); RIM_VS = _rl.get('rim_vs')
# Iris painted on the eyeball and cut into its own layer at build time (face/iris_layer.py): that layer is the iris,
# sliding over a white that stays (the white under it was repainted).
_irl = {i for i, m_ in enumerate(me.materials) if m_ and m_.name.startswith('EyeIris')}
IRIS_LAYER = {}; IRIS_MAT = {}
if _irl:
    _ivs = sorted({v for p_ in me.polygons if p_.material_index in _irl for v in p_.vertices})
    _ix = np.array([(MW @ np.r_[me.vertices[v].co, 1.0])[0] for v in _ivs]); _mx = 0.5 * (_ix.min() + _ix.max())
    IRIS_LAYER = {'R': np.array([v for v, x in zip(_ivs, _ix) if x < _mx], dtype=int),
                  'L': np.array([v for v, x in zip(_ivs, _ix) if x >= _mx], dtype=int)}
    PIECES['iris'] = True
    # one material per eye (the gaze shifts its texture); each eye's layer: the grid's vertices and their UVs
    _uvd = me.uv_layers.active.data; IRIS_UV = {}
    for p_ in me.polygons:
        if p_.material_index in _irl:
            for li_, v_ in zip(p_.loop_indices, p_.vertices):
                IRIS_UV[v_] = tuple(_uvd[li_].uv)
    for mi_ in _irl:
        _xs = [(MW @ np.r_[me.vertices[v].co, 1.0])[0] for p_ in me.polygons if p_.material_index == mi_ for v in p_.vertices]
        IRIS_MAT['R' if np.mean(_xs) < _mx else 'L'] = me.materials[mi_].name
    # the lid layer in front of it (the card's painted lids, see-through over the painted eye) stays with the eyeball
    _lml = {i for i, m_ in enumerate(me.materials) if m_ and m_.name == 'EyeLid'}
    _lvs = sorted({v for p_ in me.polygons if p_.material_index in _lml for v in p_.vertices})
    _lx = np.array([(MW @ np.r_[me.vertices[v].co, 1.0])[0] for v in _lvs]) if _lvs else np.zeros(0)
    LID_LAYER = {'R': np.array([v for v, x in zip(_lvs, _lx) if x < _mx], dtype=int),
                 'L': np.array([v for v, x in zip(_lvs, _lx) if x >= _mx], dtype=int)}
# Fixed positions below (mouth box, cavity, tongue, cheeks, nose) were measured on the profile head. On another head
# they move with its own mouth and nose: x' = MC1 + km (x - MC0), km = mouth width ratio (identity for the profile head).
MC0 = MC1 = np.array([0.003, 0.0, 1.470]); KM = 1.0; NZ = 0.0
if LM and _os.environ.get('POLISH_PROFILE_JSON') and _os.path.isfile(_os.environ['POLISH_PROFILE_JSON']):
    _L0 = json.load(open(_os.environ['POLISH_PROFILE_JSON']))['landmarks']
    MC1 = MC0 + (np.array(LM['mouth']) - np.array(_L0['mouth']))
    KM = abs(LM['mouthL'][0] - LM['mouthR'][0]) / abs(_L0['mouthL'][0] - _L0['mouthR'][0])
    NZ = LM['noseTip'][2] - _L0['noseTip'][2]
def mx(x):
    return MC1[0] + KM * (x - MC0[0])
def mz(z):
    return MC1[2] + KM * (z - MC0[2])
def my(y):
    return y + (MC1[1] - MC0[1])
seed = lambda i: comps[i][0]
ids = lambda lst: np.array([v for i in lst for v in comps[i]], dtype=int)
report = {}

# ---------------------------------------------------------------- eyes
pts = json.load(open(D_ + 'eye_points.json'))
if _os.path.isfile(D_ + 'overrides.json'):                   # hand-moved eye points of a profile (purple: inner corner R)
    for _k, _vi in json.load(open(D_ + 'overrides.json')).get('eye_point_vertex', {}).items():
        pts[_k] = [float(x) for x in pts0[_vi]]
helper.prepare_blink('Head', skin_seed=seed(SKIN))
helper.set_blink_points(pts)
helper.set_blink_followers([{'object': 'Head', 'seed': seed(i)} for i in UPPER_LASH + LOWER_LASH + list(DOUBLE.values()) + LINER['R'] + LINER['L']])
helper.fit_blink()
helper.transfer_eyes(reviewed=True)
kb = me.shape_keys.key_blocks
B = np.array([v.co for v in kb['Basis'].data]); BW = B @ M3.T + T
skin = np.array(comps[SKIN]); skinset = set(skin.tolist())
nbr = {}
for e in me.edges:
    a, b = e.vertices
    if a in skinset and b in skinset:
        nbr.setdefault(a, []).append(b); nbr.setdefault(b, []).append(a)
ball = {s: ids(v) for s, v in EYEBALL.items()}; iris = {s: ids(v) for s, v in IRIS.items()}
if IRIS_LAYER:
    iris = dict(IRIS_LAYER); ball = {s: np.unique(np.r_[ball[s], iris[s], LID_LAYER[s]]).astype(int) for s in ball}
set_sclera = {v for s_ in ('R', 'L') for i in [SCLERA[s_]] + SCLERA_EXTRA[s_] for v in comps[i]}
dbl = {s: np.array(comps[i]) for s, i in DOUBLE.items()}
rimloop = RIM_VS or {s_: next(d for d in loops if d['n'] == RIM_N[s_])['vs'] for s_ in ('R', 'L')}
upper, ring1, ring2, lid, lower, lring = {}, {}, {}, {}, {}, {}
for s, rv in rimloop.items():
    R = BW[rv]; zc = np.median(R[:, 2]); up = [v for v in rv if BW[v, 2] >= zc]
    upper[s] = up
    lower[s] = [v for v in rv if BW[v, 2] < zc]
    lring[s] = list({n for v in lower[s] for n in nbr.get(v, []) if BW[n, 2] < BW[v, 2] + 0.0005} - set(rv))
    r1 = {n for v in up for n in nbr.get(v, []) if BW[n, 2] > BW[v, 2] - 0.0005} - set(rv)
    r2 = {n for v in r1 for n in nbr.get(v, [])} - r1 - set(rv)
    ring1[s], ring2[s] = list(r1), list(r2)
    x0, x1 = R[:, 0].min() - 0.006, R[:, 0].max() + 0.006
    lid[s] = [v for v in skin if x0 < BW[v, 0] < x1 and zc - 0.002 < BW[v, 2] < R[:, 2].max() + 0.022 and BW[v, 1] < -0.06 and v not in set(rv)]
upper_seq, lower_seq = {}, {}                           # upper edge = loop arc between the corners, higher one
from collections import Counter as _Cn
_ecount = _Cn()
for p in me.polygons:
    vs = list(p.vertices)
    if all(v in skinset for v in vs):
        for i_ in range(len(vs)): _ecount[frozenset((vs[i_], vs[(i_ + 1) % len(vs)]))] += 1
def _ordered(vset):
    adj = {v: [] for v in vset}
    for e_, c_ in _ecount.items():
        if c_ == 1 and all(v in vset for v in e_):
            a_, b_ = tuple(e_); adj[a_].append(b_); adj[b_].append(a_)
    while True:                                         # drop dangling spurs, keep the cycle
        ends = [v for v, w in adj.items() if len(w) < 2]
        if not ends: break
        for v in ends:
            for w in adj.pop(v):
                if w in adj: adj[w].remove(v)
    start = next(iter(adj)); path = [start]; prev = None
    while True:
        nxt = [w for w in adj[path[-1]] if w != prev]
        if not nxt or nxt[0] == start: break
        prev = path[-1]; path.append(nxt[0])
    return path
for s_, rv0 in rimloop.items():
    rv_ = _ordered(set(rv0)); n_ = len(rv_); P_ = BW[rv_]
    i_in = int(np.argmin(np.linalg.norm(P_ - np.array(pts['eyeInner' + s_]), axis=1)))
    i_out = int(np.argmin(np.linalg.norm(P_ - np.array(pts['eyeOuter' + s_]), axis=1)))
    arc1 = [rv_[(i_in + k) % n_] for k in range((i_out - i_in) % n_ + 1)]
    arc2 = [rv_[(i_in - k) % n_] for k in range((i_in - i_out) % n_ + 1)]
    upper_seq[s_], lower_seq[s_] = (arc1, arc2) if BW[arc1, 2].mean() > BW[arc2, 2].mean() else (arc2, arc1)
report['upperEdge'] = {k: [len(v), len(rimloop[k])] for k, v in upper_seq.items()}
_img = next(n_.image for m_ in me.materials if m_ for n_ in m_.node_tree.nodes
            if n_.type == 'TEX_IMAGE' and n_.image and 'BaseColor' in n_.name)
_W, _H = _img.size; _px = np.empty(_W * _H * 4, np.float32); _img.pixels.foreach_get(_px); _px = _px.reshape(_H, _W, 4)
_uvd = me.uv_layers.active.data
def _flum(p):
    u, v = np.mean([_uvd[li].uv[:] for li in p.loop_indices], axis=0)
    x = int(np.clip(u % 1 * _W, 0, _W - 1)); y = int(np.clip(v % 1 * _H, 0, _H - 1))
    return float(_px[max(0, y - 2):y + 3, max(0, x - 2):x + 3, :3].reshape(-1, 3).mean(0) @ [0.299, 0.587, 0.114])
liner_band = {}
for s_, rv_ in rimloop.items():
    useq = set(upper_seq[s_]); rset = set(rv_)
    g1 = {n for v in useq for n in nbr.get(v, []) if n not in rset}
    band_v = set()
    for p in me.polygons:
        vs = list(p.vertices)
        if max(vs) >= N_ORIG or not all(v in useq or v in g1 for v in vs) or not any(v in useq for v in vs): continue
        if _flum(p) < 0.45: band_v |= {v for v in vs if v in g1}
    liner_band[s_] = []
    for v in band_v:
        rn = [n for n in nbr.get(v, []) if n in useq]
        if rn and min(np.linalg.norm(BW[v] - BW[n]) for n in rn) < 0.002: liner_band[s_].append((v, rn))
report['linerBand'] = {k: len(v) for k, v in liner_band.items()}
lash_end = {}
for ci in UPPER_LASH:
    lv = np.array(comps[ci]); xs = BW[lv, 0]; s_ = 'R' if xs.mean() < 0 else 'L'
    xin = xs.max() if s_ == 'R' else xs.min()
    dx = np.abs(xs - xin); t = np.clip(1 - dx / 0.004, 0, 1); sel_ = t > 0
    lash_end[s_] = (lv[sel_], (t * t * (3 - 2 * t))[sel_])
# ---- eye groups. The skin opening is the master shape (the kit's poses describe only the opening).
# Upper-lid group: edge, three skin rings above it, upper lash strip, double-eyelid line.
# Lower-lid group: lower edge and lower lashes. Eyeball group (white, iris, highlights): still.
from mathutils.bvhtree import BVHTree as _BVH
from mathutils import geometry as _geo
def _arc_bind(verts, arc):
    """For each vertex: (segment index, t) of the nearest point on the edge polyline (Basis)."""
    A = BW[arc]; out = []
    for v in verts:
        p = BW[v]; best = (1e9, 0, 0.0)
        for j in range(len(arc) - 1):
            a_, b_ = A[j], A[j + 1]; ab = b_ - a_; t = float(np.clip(np.dot(p - a_, ab) / max(np.dot(ab, ab), 1e-12), 0, 1))
            d = np.linalg.norm(a_ + t * ab - p)
            if d < best[0]: best = (d, j, t)
        out.append(best[1:])
    return out
def _arc_delta(D, arc, bind):
    return np.array([(1 - t) * D[arc[j]] + t * D[arc[j + 1]] for j, t in bind])
lash_bind, llash_bind = {}, {}
for ci in UPPER_LASH:
    lv = np.array(comps[ci]); s_ = 'R' if BW[lv, 0].mean() < 0 else 'L'
    lv = np.concatenate([lv, ids(LINER[s_])])            # liner pieces under the strip move exactly like it
    lash_bind[s_] = (lv, _arc_bind(lv, upper_seq[s_]))
shadow_bind = {}                                        # the white's painted top shadow belongs to the upper lid
for s_, sci in (('R', SCLERA['R']), ('L', SCLERA['L'])) if PIECES['iris'] and not IRIS_LAYER else ():   # painted iris (cut or not): the eyeball stays whole
    sv = np.array(comps[sci]); ue = upper_seq[s_]; A = BW[ue]
    o = np.argsort(A[:, 0]); zarc = np.interp(BW[sv, 0], A[o, 0], A[o, 2])
    depth = zarc - BW[sv, 2]
    t = np.clip(1 - depth / 0.0025, 0, 1); keep = t > 0
    shadow_bind[s_] = (sv[keep], _arc_bind(sv[keep], ue), (t * t * (3 - 2 * t))[keep])
report['scleraShadowVerts'] = {k: len(v[0]) for k, v in shadow_bind.items()}
liner_bind = {}                                         # liner pieces ride on the lash strip itself (6 nearest)
for s_ in [s_ for s_ in ('L', 'R') if s_ in lash_bind]:
    lv = ids(LINER[s_]); lash_v = lash_bind[s_][0]
    d_ = np.linalg.norm(BW[lv][:, None, :] - BW[lash_v][None, :, :], axis=2)
    liner_bind[s_] = (lv, lash_v[np.argsort(d_, axis=1)[:, :6]])
for s_ in ('L', 'R'):
    lv = np.array([v for ci in LOWER_LASH for v in comps[ci] if (BW[comps[ci], 0].mean() < 0) == (s_ == 'R')], dtype=int)
    llash_bind[s_] = (lv, _arc_bind(lv, lower_seq[s_]))
eye_rings = {}                                          # skin rings around each opening (BFS over skin)
for s_, rv_ in rimloop.items():
    ring_ = {v: 0 for v in rv_}; q_ = list(rv_)
    while q_:
        u = q_.pop(0)
        if ring_[u] >= 3: continue
        for w in nbr.get(u, []):
            if w not in ring_: ring_[w] = ring_[u] + 1; q_.append(w)
    eye_rings[s_] = ring_
_skin_tris = [lt for lt in me.loop_triangles if all(v in skinset for v in lt.vertices)] if me.loop_triangles else []
if not _skin_tris:
    me.calc_loop_triangles(); _skin_tris = [lt for lt in me.loop_triangles if all(v in skinset for v in lt.vertices)]
_tri_v = [tuple(lt.vertices) for lt in _skin_tris]
_skin_bvh = _BVH.FromPolygons([Vector(p) for p in BW], _tri_v)
def _skin_bind(verts):
    out = []
    for v in verts:
        loc, nrm, ti, dist = _skin_bvh.find_nearest(Vector(BW[v]))
        a_, b_, c_ = (Vector(BW[i]) for i in _tri_v[ti])
        w = _geo.barycentric_transform(loc, a_, b_, c_, Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        out.append((_tri_v[ti], (w.x, w.y, w.z)))
    return out
crease_bind = {s_: (dbl[s_], _skin_bind(dbl[s_])) for s_ in ('L', 'R') if s_ in dbl}
OPEN_RING_W = (1.0, 0.6, 0.25)
CLOSE = {'blink': ('L', 'R'), 'blink_smile': ('L', 'R'), 'blink_L': ('L',), 'blink_R': ('R',), 'blink_smile_L': ('L',), 'blink_smile_R': ('R',)}
for e in [e for e in helper.state['keys'] if e.endswith('_eye') or e.startswith('blink')]:
    k = kb[helper.state['keys'][e]['Head']]
    D = np.array([v.co for v in k.data]) - B
    for s in ('L', 'R'):
        D[ball[s]] = 0.0                                   # white, iris and highlights never ride on the lid
        if s in CLOSE.get(e, ()):
            D[ids(LINER[s])] = 0.0                          # liner pieces stay on the eyeball; the closing lid covers them
            if not IRIS_LAYER:
                D[iris[s]] += wv([0.0, 0.0035, 0.0040])     # iris/highlights roll up and back behind the shut lid
            # a cut iris layer lies 0.3 mm in front of a card that stays: rolled back, even the share of a closing key
            # that the smiling, squinting and half-lidded eyes take put it behind the card, and the eyes went white
            # (11-25, "rolled-back eyes"); the closing lid covers it where it is
            for v in upper[s]: D[v] += wv([0.0, -0.0022, -0.0016])   # lid edge comes forward over the eyeball
            for v in ring1[s]: D[v] += wv([0.0, -0.0016, -0.0008])
            for v in ring2[s]: D[v] += wv([0.0, -0.0008, 0.0])
            fixed = set(upper[s]) | set(ring1[s]) | set(ring2[s])
            free = [v for v in lid[s] if v not in fixed]
            for _ in range(10):                             # spread the stretch above the crease
                Dn = D.copy()
                for v in free:
                    ns = nbr.get(v, [])
                    if ns: Dn[v] = 0.5 * D[v] + 0.5 * D[ns].mean(0)
                D = Dn
            for v in lower[s]: D[v] += wv([0.0, -0.0008, 0.0016])   # lower lid rises to meet the lash: no slit
            for v in lring[s]: D[v] += wv([0.0, -0.0004, 0.0008])
            if s in lash_end:
                lv, tw = lash_end[s]                        # blunt inner end of the lash strip tucks into the lid
                D[lv] += tw[:, None] * wv([0.0, 0.0020, 0.0004])[None, :]
            seq = upper_seq[s]                              # shut lid edge smoothed along the edge: the thin
            Pk = B[seq] + D[seq]                            # edge-only triangles (painted liner) collapse
            for _ in range(8):
                Pk[1:-1] = 0.5 * Pk[1:-1] + 0.25 * (Pk[:-2] + Pk[2:])
            D[seq] = Pk - B[seq]
            for v, rn in liner_band[s]:                     # painted liner band just above the edge folds
                D[v] = (B[rn] + D[rn]).mean(0) + wv([0.0, 0.0, 0.0001]) - B[v]   # onto the edge, under the lash
    if e == 'surprised_eye':
        D *= 0.55
        for s in ('L', 'R'):                                # inner corner stays: the lash keeps covering the
            dist = np.linalg.norm(BW - np.array(pts['eyeInner' + s]), axis=1)   # ragged sclera edge there
            t = np.clip(dist / 0.012, 0, 1)
            near = dist < 0.012
            D[near] *= (t[near] * t[near] * (3 - 2 * t[near]))[:, None]
    for s in ('L', 'R'):
        if s not in CLOSE.get(e, ()):                       # open shapes: rings follow the edge, lashes ride on it
            ring_ = eye_rings[s]; F = D.copy()
            for r_ in (1, 2, 3):
                w = OPEN_RING_W[r_ - 1]
                for v in [v for v, r in ring_.items() if r == r_]:
                    inner = [u for u in nbr.get(v, []) if ring_.get(u) == r_ - 1]
                    if inner:
                        F[v] = F[inner].mean(0); D[v] = w * F[v] + (1 - w) * D[v]
            if s in lash_bind:
                lv, bd = lash_bind[s]; D[lv] = _arc_delta(D, upper_seq[s], bd)
            lv, bd = llash_bind[s]
            if len(lv):
                D[lv] = _arc_delta(D, lower_seq[s], bd)
            if s in shadow_bind:
                sv, bd, sw = shadow_bind[s]; D[sv] = sw[:, None] * _arc_delta(D, upper_seq[s], bd)
        if s in crease_bind:
            cv, bd = crease_bind[s]                         # double-eyelid line stays on the lid skin
            D[cv] = np.array([sum(wi * D[vi] for vi, wi in zip(tv, ws)) for tv, ws in bd])
    for i, v in enumerate(k.data): v.co = B[i] + D[i]

# the top of each white curls backwards; it shows above the iris once the lash lifts (surprised) and renders
# pale in the double-sided preview. Back-facing white faces take the lash colour.
_uv3 = me.uv_layers.active.data
nback = 0
if UPPER_LASH:
    _lp = next(p for p in me.polygons if p.vertices[0] in set(comps[UPPER_LASH[0]]))
    _lash_uv = tuple(np.mean([_uv3[li].uv[:] for li in _lp.loop_indices], axis=0))
for p in (me.polygons if UPPER_LASH else ()):
    if not all(v in set_sclera for v in p.vertices): continue
    nw = M3 @ np.array(p.normal); nw /= np.linalg.norm(nw)
    cz = BW[list(p.vertices), 2].mean(); ez = 0.5 * (pts['eyeUpperR'][2] + pts['eyeLowerR'][2])
    if cz > ez and (nw[1] > 0.05 or nw[2] < -0.7):
        for li in p.loop_indices: _uv3[li].uv = _lash_uv
        nback += 1
report['scleraBackFaces'] = nback

# eye-socket skin that folds in front of the white near the corners (Tripo mesh) shows as grey shards: white texel
_sc = [p for p in me.polygons if all(v in set(comps[SCLERA['R']]) for v in p.vertices)]
_white_uv = tuple(np.mean([_uvd[li].uv[:] for li in max(_sc, key=_flum).loop_indices], axis=0))
_bme = bmesh.new(); _bme.from_mesh(me); _bme.transform(h.matrix_world); _bme.faces.ensure_lookup_table()
# rays from the front must not stop on the overlays added in build_character (face effects, brow copy)
_ovl = {i for i, m_ in enumerate(me.materials) if m_ and (m_.name.startswith('FX_') or m_.name == 'BrowOverlay')}
_polys = [p_ for p_ in me.polygons if p_.material_index not in _ovl]
_tre = BVHTree.FromPolygons([v_.co.copy() for v_ in _bme.verts], [tuple(p_.vertices) for p_ in _polys]); _tre_idx = [p_.index for p_ in _polys]
nshard = 0
for s_ in ('L', 'R'):
    poly = BW[_ordered(set(rimloop[s_]))][:, [0, 2]]
    def _inside(x, z):
        c = False; n_ = len(poly)
        for i_ in range(n_):
            (x1, z1), (x2, z2) = poly[i_], poly[(i_ + 1) % n_]
            if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1 + 1e-12) + x1: c = not c
        return c
    for p in me.polygons:
        vs = list(p.vertices)
        if max(vs) >= N_ORIG or not all(v in skinset for v in vs): continue
        cw = BW[vs].mean(0)
        if not _inside(cw[0], cw[2]): continue
        hit = _tre.ray_cast(Vector(cw) + Vector((0, -0.05, 0)), Vector((0, 1, 0)))
        if hit[2] is None or _tre_idx[hit[2]] != p.index: continue
        for li in p.loop_indices: _uvd[li].uv = _white_uv
        nshard += 1
_bme.free()
report['socketShards'] = nshard

# ---------------------------------------------------------------- brows (painted brow removed from the texture)
BROW_SCALE = {'brow_angry': 0.3, 'brow_sad': 0.5, 'brow_happy': 0.5, 'brow_relaxed': 0.5, 'brow_surprised': 0.3}
if PIECES['brow']:
    helper.prepare_brows({'L': {'object': 'Head', 'seed': seed(BROW['L'])}, 'R': {'object': 'Head', 'seed': seed(BROW['R'])}})
    helper.transfer_brows(reviewed=True)
    # the kit scales brow motion by brow width; these brows are 75 mm long, so angry dropped the inner end 25 mm and
    # pushed the strip into the forehead. Scale down and keep each brow vertex at its own height above the skin.
    BROW_SCALE = {'brow_angry': 0.3, 'brow_sad': 0.5, 'brow_happy': 0.5, 'brow_relaxed': 0.5, 'brow_surprised': 0.3}
    kb = me.shape_keys.key_blocks
    brow_v = np.array(comps[BROW['R']] + comps[BROW['L']])
    _off = []
    for v in brow_v:
        loc, nrm, ti, dist = _skin_bvh.find_nearest(Vector(BW[v]))
        _off.append(float(np.dot(BW[v] - np.array(loc), np.array(nrm))))
    for e, f in BROW_SCALE.items():
        k = kb[helper.state['keys'][e]['Head']]
        K = np.array([d.co for d in k.data]); KW = K @ M3.T + T
        for v, o in zip(brow_v, _off):
            pw = BW[v] + f * (KW[v] - BW[v])
            loc, nrm, ti, dist = _skin_bvh.find_nearest(Vector(pw))
            pw = np.array(loc) + np.array(nrm) * o
            k.data[int(v)].co = (M3i @ (pw - T)).tolist()
    report['browScale'] = BROW_SCALE


else:
    # brows painted on the skin (no brow pieces): each brow pose moves the forehead skin around the painted brow along
    # the surface, so the painting moves with it. Lengths in eye widths; the inner end is the one nearer the nose.
    BROW_PAINTED = dict(angry=(-0.13, 0.03, 0.05), sad=(0.12, -0.02, 0.0), surprised=(0.15, 0.15, 0.0),
                        happy=(0.07, 0.07, 0.0), relaxed=(-0.04, -0.04, 0.0), radius=0.7, rim_guard=0.3)
    # (inner rise, outer rise, inward pull at the inner end)
    _px_lum = lambda u, v: float(_px[int(np.clip(v % 1 * _H, 0, _H - 1)), int(np.clip(u % 1 * _W, 0, _W - 1)), :3] @ [0.299, 0.587, 0.114])
    _vuv = {}
    for p in me.polygons:
        for li, vi in zip(p.loop_indices, p.vertices):
            if vi in skinset and vi not in _vuv: _vuv[vi] = _uvd[li].uv[:]
    kb = me.shape_keys.key_blocks
    _brow_rep = {}
    _Dpose = {n_: np.zeros_like(B) for n_ in BROW_SCALE}
    for s_ in ('L', 'R'):
        rv = rimloop[s_]; R_ = BW[rv]; ew = abs(pts['eyeOuter' + s_][0] - pts['eyeInner' + s_][0])
        x_in, x_out = pts['eyeInner' + s_][0], pts['eyeOuter' + s_][0]; o_ = 1 if x_out > x_in else -1
        ztop = R_[:, 2].max()
        cand = [v for v in skin if v in _vuv and ztop + 0.15 * ew < BW[v, 2] < ztop + 1.3 * ew
                and (BW[v, 0] - x_in) * o_ > -0.3 * ew and (BW[v, 0] - x_out) * o_ < 0.35 * ew and BW[v, 1] < BW[rv, 1].mean() + 0.3 * ew]
        lum = np.array([_px_lum(*_vuv[v]) for v in cand]); ref = float(np.median(lum))
        dark = [v for v, l_ in zip(cand, lum) if l_ < 0.62 * ref]
        if len(dark) < 4:
            raise SystemExit(f'painted brow not found above the {"left" if s_ == "L" else "right"} eye')
        Q = BW[dark]; xi = Q[:, 0].min() if o_ > 0 else Q[:, 0].max(); xo = Q[:, 0].max() if o_ > 0 else Q[:, 0].min()
        bw = abs(xo - xi); zb = np.interp(BW[:, 0] * o_, np.sort(Q[:, 0] * o_), Q[np.argsort(Q[:, 0] * o_), 2])
        t = np.clip((BW[:, 0] - xi) * o_ / max(bw, 1e-6), 0, 1)
        dx = np.clip(np.maximum((xi - BW[:, 0]) * o_, (BW[:, 0] - xo) * o_), 0, None); dz = BW[:, 2] - zb
        w = np.clip(1 - np.hypot(dx, dz) / (BROW_PAINTED['radius'] * ew), 0, 1); w = w * w * (3 - 2 * w)
        g = np.clip((BW[:, 2] - ztop) / (BROW_PAINTED['rim_guard'] * ew), 0, 1); w *= g * g * (3 - 2 * g)
        side = ((BW[:, 0] - 0.5 * (pts['eyeInnerL'][0] + pts['eyeInnerR'][0])) * o_ > 0)
        mask = np.zeros(len(B), bool); mask[[v for v in skin if v < len(B)]] = True; w *= mask * side
        for name in BROW_SCALE:
            a_, b_, c_ = BROW_PAINTED[name.split('_')[1]]
            Dw = np.zeros_like(BW); Dw[:, 2] = (a_ * (1 - t) + b_ * t) * ew; Dw[:, 0] = -o_ * c_ * (1 - t) * ew
            _Dpose[name] += Dw * w[:, None]
        _brow_rep[s_] = dict(painted_verts=len(dark), width_mm=round(bw * 1000, 1), eye_width_mm=round(ew * 1000, 1))
    for name, Dw in _Dpose.items():
        helper.ensure_expression(name)
        Pw = BW + Dw; moved = np.nonzero(np.linalg.norm(Dw, axis=1) > 1e-7)[0]
        for v in moved:                                     # stay on the skin surface: the painting slides with it
            loc, nrm, ti, dist = _skin_bvh.find_nearest(Vector(Pw[v])); Pw[v] = np.array(loc)
        K = B.copy(); K[moved] = (Pw[moved] - T) @ M3i.T
        kb[helper.state['keys'][name]['Head']].data.foreach_set('co', K.ravel())
    report['browPainted'] = dict(BROW_PAINTED, sides=_brow_rep)

# ---------------------------------------------------------------- closed-lid fold
# Closing, the lid skin moves fully up to where the kit's lid region ends and the skin above does not move, so a fold
# forms there; lit, it reads as a dark, uneven line above the closed eye (user, 11-13: "like a knife cut"). The
# displacement of every closing key is relaxed over the skin around each eye (harmonic, the opening edge and its first
# ring fixed), so it fades out smoothly instead.
LIDFOLD = dict(iters=80, ring_fixed=1, margin=3)
_closing = ['blink', 'blink_L', 'blink_R', 'blink_smile', 'blink_smile_L', 'blink_smile_R']
_Bf = np.array([v.co for v in kb['Basis'].data]); _fixed = set()
for s_, ring_ in eye_rings.items():
    _fixed |= {v for v, r in ring_.items() if r <= LIDFOLD['ring_fixed']}
_nb = {v: [w for w in nbr.get(v, [])] for v in skinset}
_lf = {}
for e in _closing:
    if e not in helper.state['keys']: continue
    k = kb[helper.state['keys'][e]['Head']]; K = np.array([d.co for d in k.data]); D = K - _Bf
    mv = {v for v in skinset if np.linalg.norm(D[v]) > 2e-5}
    reg = set(mv)
    for _ in range(LIDFOLD['margin']):
        reg |= {w for v in reg for w in _nb.get(v, [])}
    free = np.array(sorted(v for v in reg if v not in _fixed and _nb.get(v)))
    if not len(free): continue
    idx = {v: i for i, v in enumerate(free)}
    for _ in range(LIDFOLD['iters']):
        D[free] = np.array([D[_nb[v]].mean(0) for v in free])
    k.data.foreach_set('co', (_Bf + D).ravel())
    _lf[e] = dict(free=len(free), moved=len(mv))
report['lidFold'] = _lf

# ---------------------------------------------------------------- mouth
bmw = bmesh.new(); bmw.from_mesh(me); bmw.transform(h.matrix_world); bmw.verts.ensure_lookup_table()
tree = BVHTree.FromPolygons([v_.co.copy() for v_ in bmw.verts], [tuple(p_.vertices) for p_ in me.polygons if p_.material_index not in _ovl])
box = [v.index for v in bmw.verts if v.index in skinset and abs(v.co.x - mx(0.003)) < 0.032 * KM and mz(1.452) < v.co.z < mz(1.492) and v.co.y < my(-0.09)]
hidden = set(i for i in box if tree.ray_cast(bmw.verts[i].co + Vector((0, -0.0004, 0)), Vector((0, -1, 0)), 0.05)[0] is not None)
# only the hidden regions spanning most of the mouth width are the lip fold; the box can also hold the nostrils
# (11-25: nostril faces took the inner-lip colour and moved with the lips)
_hcomps, _hseen = [], set()
for _s in hidden:
    if _s in _hseen: continue
    _st, _c = [_s], []; _hseen.add(_s)
    while _st:
        _u = _st.pop(); _c.append(_u)
        for _e in bmw.verts[_u].link_edges:
            _w = _e.other_vert(bmw.verts[_u]).index
            if _w in hidden and _w not in _hseen: _hseen.add(_w); _st.append(_w)
    _hcomps.append(_c)
_hext = [float(np.ptp(BW[_c, 0])) for _c in _hcomps]
_hkeep = [_c for _c, _x in zip(_hcomps, _hext) if _x >= 0.5 * max(_hext)] if _hcomps else []
_hother = len(hidden) - sum(len(_c) for _c in _hkeep)
hidden = set(v for _c in _hkeep for v in _c)
vis = [i for i in box if i not in hidden]
rim = sorted({i for i in vis for e in bmw.verts[i].link_edges if e.other_vert(bmw.verts[i]).index in hidden})
R = BW[rim]; cR, cL = rim[int(np.argmin(R[:, 0]))], rim[int(np.argmax(R[:, 0]))]
adj = {i: set() for i in rim}
for e in me.edges:
    a, b = e.vertices
    if a in adj and b in adj: adj[a].add(b); adj[b].add(a)
import heapq
def sp(a, b, banned):
    dist = {a: 0}; prev = {a: None}; q = [(0, a)]
    while q:
        dd, u = heapq.heappop(q)
        if u == b: break
        if dd > dist[u]: continue
        for w in adj[u]:
            if w in banned: continue
            nd = dd + float(np.linalg.norm(BW[u] - BW[w]))
            if nd < dist.get(w, 1e9): dist[w] = nd; prev[w] = u; heapq.heappush(q, (nd, w))
    path = [b]
    while prev[path[-1]] is not None: path.append(prev[path[-1]])
    return path[::-1]
p1 = sp(cR, cL, set()); p2 = sp(cR, cL, set(p1[1:-1]))
up_arc, lo_arc = (p1, p2) if BW[p1, 2].mean() > BW[p2, 2].mean() else (p2, p1)
NOSE_HOLD = dict(above=0.5, half_width=0.75, depth=1.5)   # above / depth in mouth-to-nose-tip heights, half_width in mouth widths
if LM:
    # the kit spreads mouth motion over 2.85 mouth widths of skin; a wide mouth would drag the eyes and nose along.
    # Keep the profile's reach in face units and hold the skin around the eyes still.
    _arcs = set(up_arc) | set(lo_arc)
    _prot = sorted({v for s_ in eye_rings for v, r in eye_rings[s_].items() if v in skinset and v not in _arcs})
    # the nose holds still: the motion spread over 2.85 mouth widths reached it and the nose tip went 11 mm down with
    # the jaw (user, 11-25: "the nose moves with the open mouth"); the motion fades out over the philtrum instead
    _nh = LM['noseTip'][2] - LM['mouth'][2]; _mw0 = abs(LM['mouthL'][0] - LM['mouthR'][0])
    _nose = {int(v) for v in skin if v not in _arcs and BW[v, 2] >= LM['mouth'][2] + NOSE_HOLD['above'] * _nh
             and abs(BW[v, 0] - LM['noseTip'][0]) <= NOSE_HOLD['half_width'] * _mw0 and BW[v, 1] < LM['noseTip'][1] + NOSE_HOLD['depth'] * _nh}
    _prot = sorted(set(_prot) | _nose)
    report['noseHold'] = dict(verts=len(_nose), **NOSE_HOLD)
    helper.prepare_mouth('Head', seed(SKIN), upper=up_arc, lower=lo_arc, support=max(0.8, min(2.85, 2.85 / KM)), protected=_prot)
    report['mouthReach'] = dict(support=round(max(0.8, min(2.85, 2.85 / KM)), 3), protectedEyeVerts=len(_prot))
else:
    helper.prepare_mouth('Head', seed(SKIN), upper=up_arc, lower=lo_arc)
helper.transfer_mouth(reviewed=True)
if LM:
    # the kit sizes mouth poses by mouth width; a wide mouth over a short chin opens past the chin. Scale the vowel and
    # mood mouths so the jaw drop keeps the profile's share of the mouth-to-chin distance.
    _L0m = json.load(open(_os.environ['POLISH_PROFILE_JSON']))['landmarks']
    _r = (LM['mouth'][2] - LM['chin'][2]) / max(KM * (_L0m['mouth'][2] - _L0m['chin'][2]), 1e-6)
    MOUTH_GAIN = float(np.clip(_r, 0.5, 1.0))
    if MOUTH_GAIN < 0.999:
        _kbx = me.shape_keys.key_blocks; _Bx = np.array([v.co for v in _kbx['Basis'].data])
        for _n in ('aa', 'ih', 'ou', 'ee', 'oh', 'happy_mouth', 'angry_mouth', 'sad_mouth', 'relaxed_mouth', 'surprised_mouth'):
            if _n in helper.state['keys']:
                _k = _kbx[helper.state['keys'][_n]['Head']]; _K = np.array([v.co for v in _k.data])
                _k.data.foreach_set('co', (_Bx + MOUTH_GAIN * (_K - _Bx)).ravel())
    report['mouthGain'] = round(MOUTH_GAIN, 3)
# How far the vowels open is a matter of style: the kit (and the purple head) opens aa to 1.1 mouth widths, an anime
# mouth; on a realistic face that read as far too big (user, 11-25). A head may set mouth_open in its build config: the
# aa opening in widths of the visible mouth; every opening shape (vowels, surprised, the laugh) is scaled with it, so
# they keep their proportions.
_mo = (json.load(open(_os.environ['POLISH_BUILD_CONFIG'])) if _os.environ.get('POLISH_BUILD_CONFIG') and _os.path.isfile(_os.environ['POLISH_BUILD_CONFIG']) else {}).get('mouth_open')
if _mo:
    _kbo = me.shape_keys.key_blocks; _Bo = np.array([v.co for v in _kbo['Basis'].data])
    def _sep(name):
        D_ = (np.array([v.co for v in _kbo[helper.state['keys'][name]['Head']].data]) - _Bo) @ M3.T
        return float(D_[up_arc, 2].max() - D_[lo_arc, 2].min())
    _BWo = _Bo @ M3.T + T
    _wv = abs(LM['mouthL'][0] - LM['mouthR'][0]) if LM else float(np.ptp(_BWo[up_arc + lo_arc, 0]))
    _g = min(1.0, float(_mo) * _wv / max(_sep('aa'), 1e-6))
    if _g < 0.999:
        for _n in ('aa', 'ih', 'ou', 'ee', 'oh', 'happy_mouth', 'surprised_mouth'):
            if _n in helper.state['keys']:
                _k = _kbo[helper.state['keys'][_n]['Head']]; _K = np.array([v.co for v in _k.data])
                _k.data.foreach_set('co', (_Bo + _g * (_K - _Bo)).ravel())
    report['mouthOpen'] = dict(aa_widths=float(_mo), gain=round(_g, 3))
# smile: the kit's happy mouth is a wide open laugh. It is kept as laugh_mouth (used by happy_open) and
# happy_mouth becomes a closed smile: both lip arcs keep the neutral gap, the corners move out and up in an
# anime-sized, even U (the drawn line is small on this face, so a realistic amount reads as no smile; corners curled
# up at the very end read as a smirk), the middle stays flat. Same relaxation over the skin as the kit's mouth transfer, plus the apples of the cheeks rising.
TR = helper.transfer_helper()
mcfg = helper.state['mouth']; mobj, mskin = TR.selected_part(helper, mcfg['object'], mcfg['skin_seed'])
mtgt = helper.mask_helper().basis_world(mobj) @ TR.frame(helper).T; maxes = TR.frame(helper)
helper.ensure_expression('laugh_mouth')
_kbm = me.shape_keys.key_blocks; _co = np.empty(len(me.vertices) * 3, np.float32)
_kbm[helper.state['keys']['happy_mouth']['Head']].data.foreach_get('co', _co)
_kbm[helper.state['keys']['laugh_mouth']['Head']].data.foreach_set('co', _co)
SMILE = dict(wide=0.53, back=0.0, lift=0.37, mid=0.0, p2=0.8)    # fractions of the mouth width; p2: share of s^2 in the lift
# user, 11-13: lift 0.70 with most of it at the corners read as a smirk; pull out first, then up on a diagonal, even U;
# 0.42 still curled up, lowered to 0.26
# user, 11-18: the smile read stiff, corners should reach toward the pupils. wide 0.52 put the corners at 52% of the
# pupil half-distance (the drawn line ends even closer in); 1.18 puts them at ~85%. lift/wide drops from 0.50 to 0.40,
# so the U stays even (no smirk) while the corners rise 1.8x.
# user, 11-18 later: happy references (closed U smile with blush, open laugh, cat mouth) have narrower mouths with a clear U:
# 0.84 / 0.39 puts the corners at ~68% of the pupil half-distance, the U sagitta at 0.29 of the half-width (references ~0.27)
# user, 11-18 afternoon: with the mouth slightly open (tracked jaw) 0.84 became a wide flat trapezoid; 0.53 / 0.37 puts the
# corners at ~52% (references ~50%), so the open smile reads as a D
if LM:
    # another face: the smile is set in the face's own units, as tuned on the profile (corners end at 52 % of the
    # pupils' half distance, lift 0.19 of it, cheeks under the pupils); identical numbers on the profile head
    _ph = 0.25 * abs((pts['eyeInnerL'][0] + pts['eyeOuterL'][0]) - (pts['eyeInnerR'][0] + pts['eyeOuterR'][0]))
    _w = mcfg['width']
    SMILE.update(wide=max(0.1, (0.52 * _ph - _w / 2) / _w), lift=0.19 * _ph / _w)
    report['smileFace'] = dict(pupil_half=round(_ph, 4), mouth_width=round(_w, 4), wide=round(SMILE['wide'], 3), lift=round(SMILE['lift'], 3))
def _smile(arc):
    s = 2 * TR.arc_parameter(mtgt[arc]) - 1; d = np.zeros((len(arc), 3)); w_ = mcfg['width']
    d[:, 0] = SMILE['wide'] * w_ * s * np.abs(s); d[:, 1] = SMILE['back'] * w_ * s ** 2
    d[:, 2] = SMILE['lift'] * w_ * (SMILE['p2'] * s ** 2 + (1 - SMILE['p2']) * s ** 4) + SMILE['mid'] * w_ * (1 - s ** 2)
    return d
_cons = {i: v for arc in (mcfg['upper'], mcfg['lower']) for i, v in zip(arc, _smile(arc))}
_dl = TR.smooth_displacements(mtgt, [e.vertices[:] for e in mobj.data.edges], mskin, _cons, mcfg['width'] * mcfg['support'], mcfg['protected'])
TR.write_delta(helper, mobj, 'happy_mouth', _dl @ maxes)
# cheek raise (in mouth widths from the mouth centre / corner height): up and a little forward and outward,
# fading out below the lower lid; kept as its own delta for cheekSquint
CHEEK = dict(amount=0.005, radius=1.0, dx=1.32, dz=0.5, top=1.16)   # 11-18: 0.0035 -> 0.005 with the wider smile
if LM:
    CHEEK.update(dx=0.66 * _ph / _w, dz=0.25 * _ph / _w, radius=0.5 * _ph / _w, top=0.585 * _ph / _w)
_wm0 = mcfg['width']; _cx = 0.5 * (BW[up_arc[0], 0] + BW[up_arc[-1], 0]); _cz = 0.5 * (BW[up_arc[0], 2] + BW[up_arc[-1], 2])
_skm = np.zeros(len(BW), bool); _skm[skin[skin < len(BW)]] = True
cheek_raise = np.zeros_like(BW)
for o_ in (1, -1):
    _c = np.array([_cx + o_ * CHEEK['dx'] * _wm0, _cz + CHEEK['dz'] * _wm0])
    _d = np.linalg.norm(BW[:, [0, 2]] - _c, axis=1); _w = np.clip(1 - _d / (CHEEK['radius'] * _wm0), 0, 1); _w = _w * _w * (3 - 2 * _w)
    _w *= np.clip((_cz + CHEEK['top'] * _wm0 - BW[:, 2]) / 0.006, 0, 1) * _skm * (np.sign(BW[:, 0] - _cx) == o_)
    _v = np.array([o_ * 0.15, -0.3, 1.0]); _v /= np.linalg.norm(_v)
    cheek_raise += (_w * CHEEK['amount'])[:, None] * _v
cheek_raise = cheek_raise @ M3i.T                      # local
cheek_raise = np.r_[cheek_raise, np.zeros((len(me.vertices) - len(cheek_raise), 3))]
_k = kb_hm = me.shape_keys.key_blocks[helper.state['keys']['happy_mouth']['Head']]
_co = np.empty(len(me.vertices) * 3, np.float32); _k.data.foreach_get('co', _co)
_k.data.foreach_set('co', (_co.reshape(-1, 3) + cheek_raise).ravel())
report['smile'] = dict(closed=SMILE, cheek=CHEEK, laugh='kit happy_mouth')
# ARKit mouth shapes built from lip-arc targets (world deltas in mouth widths; s = -1 at the avatar's right corner,
# +1 at its left corner). One-sided shapes fade over the middle third of the mouth. Same skin relaxation as above.
_wm = mcfg['width']
def _s_of(arc):
    s_ = 2 * TR.arc_parameter(mtgt[arc]) - 1
    return s_ if BW[arc[-1], 0] > BW[arc[0], 0] else -s_
def _sm(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)
_wL = lambda s_: _sm((s_ + 0.3) / 0.6)
_wR = lambda s_: _sm((-s_ + 0.3) / 0.6)
def _v(dx=0.0, dy=0.0, dz=0.0):
    return lambda s_: np.c_[np.broadcast_to(dx(s_) if callable(dx) else dx, s_.shape), np.broadcast_to(dy(s_) if callable(dy) else dy, s_.shape), np.broadcast_to(dz(s_) if callable(dz) else dz, s_.shape)] * _wm
_mid = lambda s_: 1 - s_ ** 2
_mid7 = lambda s_: np.clip(1 - s_ ** 2, 0, 1) ** 0.7
_c2 = lambda s_: s_ ** 2
_Z = _v()
CAT = dict(narrow=0.0, amp=0.09)                     # mouth widths; 11-16: no pursing (read as a pout), deeper omega + drawn line
ARKIT_ARC = {   # name: (upper arc, lower arc)
    'mouthLeft': (_v(dx=0.14), _v(dx=0.14)), 'mouthRight': (_v(dx=-0.14), _v(dx=-0.14)),
    'jawLeft': (_v(dx=0.03), _v(dx=0.12)), 'jawRight': (_v(dx=-0.03), _v(dx=-0.12)),
    'jawForward': (_Z, _v(dy=-0.07)),
    'mouthRollLower': (_Z, _v(dy=lambda s_: 0.06 * _mid(s_), dz=lambda s_: 0.04 * _mid(s_))),
    'mouthRollUpper': (_v(dy=lambda s_: 0.06 * _mid(s_), dz=lambda s_: -0.04 * _mid(s_)), _Z),
    'mouthShrugLower': (_v(dz=lambda s_: 0.02 * _mid(s_)), _v(dy=lambda s_: -0.03 * _mid(s_), dz=lambda s_: 0.06 * _mid(s_))),
    'mouthShrugUpper': (_v(dz=lambda s_: 0.05 * _mid(s_)), _Z),
    'mouthClose': (_v(dz=lambda s_: -0.03 * _mid(s_)), _v(dz=lambda s_: 0.03 * _mid(s_))),   # lips press together; no reverse jaw
    # cat mouth: the closed lip line becomes an omega (corners and middle up, two dips), corners a little in
    'mouth_cat': (_v(dx=lambda s_: -CAT['narrow'] * s_, dz=lambda s_: CAT['amp'] * np.cos(2 * np.pi * s_)),) * 2,
    # corrective, horizontal only: the player adds it when combined shapes (tracked smile + stretch + jaw) would spread
    # the corners past the width limit (post/vrm_finalize.py writes the corner motion of every shape into the VRM)
    'mouthNarrow': (_v(dx=lambda s_: -0.15 * s_),) * 2,
}
for side, wf, o_ in (('Left', _wL, 1), ('Right', _wR, -1)):
    ARKIT_ARC['mouthDimple' + side] = (_v(dx=lambda s_, wf=wf, o_=o_: o_ * 0.06 * _c2(s_) * wf(s_), dy=lambda s_, wf=wf: 0.03 * _c2(s_) * wf(s_)),) * 2   # dimple barely tucks back: tracked smiles carry dimple too
    ARKIT_ARC['mouthStretch' + side] = (_v(dx=lambda s_, wf=wf, o_=o_: o_ * 0.12 * _c2(s_) * wf(s_), dz=lambda s_, wf=wf: -0.04 * _c2(s_) * wf(s_)),
                                        _v(dx=lambda s_, wf=wf, o_=o_: o_ * 0.12 * _c2(s_) * wf(s_), dz=lambda s_, wf=wf: (-0.04 * _c2(s_) - 0.07 * _mid(s_)) * wf(s_)))
    ARKIT_ARC['mouthPress' + side] = (_v(dx=lambda s_, wf=wf, o_=o_: o_ * 0.03 * _c2(s_) * wf(s_), dz=lambda s_, wf=wf: -0.012 * wf(s_)),
                                      _v(dx=lambda s_, wf=wf, o_=o_: o_ * 0.03 * _c2(s_) * wf(s_), dz=lambda s_, wf=wf: 0.012 * wf(s_)))
    ARKIT_ARC['mouthLowerDown' + side] = (_Z, _v(dz=lambda s_, wf=wf: -0.16 * _mid7(s_) * wf(s_)))
    ARKIT_ARC['mouthUpperUp' + side] = (_v(dz=lambda s_, wf=wf: 0.12 * _mid7(s_) * wf(s_)), _Z)
_s_up, _s_lo = _s_of(mcfg['upper']), _s_of(mcfg['lower'])
_cons = {}
for arc, s_arc, k_ in ((mcfg['upper'], _s_up, 0), (mcfg['lower'], _s_lo, 1)):
    vals = np.concatenate([ARKIT_ARC[n][k_](s_arc) @ maxes.T for n in ARKIT_ARC], axis=1)   # world -> mouth frame
    for i, v in zip(arc, vals): _cons[i] = v
_dl = TR.smooth_displacements(mtgt, [e.vertices[:] for e in mobj.data.edges], mskin, _cons, _wm * mcfg['support'], mcfg['protected'])
for n_, name in enumerate(ARKIT_ARC):
    TR.write_delta(helper, mobj, name, _dl[:, n_ * 3:n_ * 3 + 3] @ maxes)
MOUTH_KEYS = ['aa', 'ih', 'ou', 'ee', 'oh', 'happy_mouth', 'laugh_mouth', 'angry_mouth', 'sad_mouth', 'relaxed_mouth', 'surprised_mouth'] + list(ARKIT_ARC)
report['arkitArc'] = len(ARKIT_ARC)
report['mouth'] = dict(hidden=len(hidden), otherHidden=_hother, rim=len(rim), upper=len(up_arc), lower=len(lo_arc))
# inner lip / pocket colours (existing face texture texels; no new material)
uvd = me.uv_layers.active.data
slot = next(i for i, s_ in enumerate(h.material_slots) if s_.material and s_.material.name.startswith('Material_head'))
UP = BW[up_arc]; LO = BW[lo_arc]
def rim_y(x, z):
    arc = UP if z >= np.interp(x, LO[:, 0], LO[:, 2]) else LO
    o = np.argsort(arc[:, 0]); return float(np.interp(x, arc[o, 0], arc[o, 1]))
ncol = {'innerlip': 0, 'midred': 0, 'dark': 0, 'keptSeenAtRest': 0}
# faces seen with the mouth closed (front, sides to 45 degrees, a little from below and above) keep the model's own
# texture: they are the lip line, and the inner-lip colour on them showed as pink blocks between the lips (11-25)
_views = [Vector((math.sin(a_) * math.cos(b_), -math.cos(a_) * math.cos(b_), math.sin(b_))) for a_, b_ in
          ((0, 0), (0.4, 0), (-0.4, 0), (0.78, 0), (-0.78, 0), (0, -0.3), (0, 0.25))]
def _seen_at_rest(p):
    c_ = Vector(BW[list(p.vertices)].mean(0))
    for q_ in [c_] + [c_.lerp(Vector(BW[v_]), 0.7) for v_ in p.vertices]:
        for d_ in _views:
            if tree.ray_cast(q_ + d_ * 0.0003, d_, 0.3)[0] is None: return True
    return False
for p in me.polygons:
    vs = list(p.vertices)
    nh = sum(v in hidden for v in vs)
    if nh == 0 or max(vs) >= N_ORIG: continue
    if _seen_at_rest(p):
        ncol['keptSeenAtRest'] += 1; continue
    c = MW[:3, :3] @ np.array(p.center) + T
    depth = c[1] - rim_y(c[0], c[2])
    # inner-lip colour only on shallow faces at the opening; a large face running from the lip edge deep into the
    # pocket showed as a flat pink panel from the side (11-25)
    dmax = max(BW[v_, 1] - rim_y(BW[v_, 0], BW[v_, 2]) for v_ in vs)
    tone = 'innerlip' if ((nh < len(vs) or depth < 0.004) and dmax < 0.005) else ('midred' if depth < 0.008 and dmax < 0.010 else 'dark')
    p.material_index = slot
    for li in p.loop_indices: uvd[li].uv = spots[tone][:2]
    ncol[tone] += 1
# the rest of the pocket: Tripo's closed heads model the inside of the mouth as a pocket about 4 cm deep, and past the
# mouth box only its front was coloured; the back kept stray texture, seen once the mouth opened (11-25). Every face
# reached from the pocket without crossing a face seen at rest takes the cavity colours by depth.
_hm_ = slot; _done = {p.index for p in me.polygons if any(v in hidden for v in p.vertices)}
_e2f = {}
for p in me.polygons:
    if p.material_index != _hm_ or max(p.vertices) >= N_ORIG: continue
    for ek in p.edge_keys: _e2f.setdefault(ek, []).append(p.index)
_front = list(_done); _deep = 0
while _front:
    nxt_ = []
    for fi_ in _front:
        for ek in me.polygons[fi_].edge_keys:
            for g_ in _e2f.get(ek, []):
                if g_ in _done: continue
                _done.add(g_); q_ = me.polygons[g_]
                if _seen_at_rest(q_): continue
                c = MW[:3, :3] @ np.array(q_.center) + T
                depth = c[1] - rim_y(c[0], c[2])
                tone = 'innerlip' if depth < 0.004 else ('midred' if depth < 0.008 else 'dark')
                for li in q_.loop_indices: uvd[li].uv = spots[tone][:2]
                ncol[tone] += 1; _deep += 1; nxt_.append(g_)
    _front = nxt_
ncol['beyondBox'] = _deep
report['pocketColours'] = ncol
# rings around the opening follow the lip edge (propagated ring by ring), so the drawn mouth line one
# ring outside the edge stays thin and hugs the opening; near the corners the pocket faces and the faces
# between the upper edge and the line take the cavity colour, so the line joins the cavity without a pale gap
from collections import deque
arc = list(dict.fromkeys(list(up_arc) + list(lo_arc))); arcset = set(arc); upset = set(up_arc)
mnbr = {}
for e in me.edges:
    a, b = e.vertices
    if a < N_ORIG and b < N_ORIG and a in skinset and b in skinset:
        mnbr.setdefault(a, []).append(b); mnbr.setdefault(b, []).append(a)
RING_W = (1.0, 0.65, 0.3)
ring = {v: 0 for v in arc}; q = deque(arc)
while q:
    u = q.popleft()
    if ring[u] >= len(RING_W): continue
    for w in mnbr.get(u, []):
        if w not in ring and w not in hidden: ring[w] = ring[u] + 1; q.append(w)
by_ring = [[v for v, r in ring.items() if r == k] for k in range(1, len(RING_W) + 1)]
kb = me.shape_keys.key_blocks
Bm = np.array([v.co for v in kb['Basis'].data])
for e in MOUTH_KEYS:
    k = kb[helper.state['keys'][e]['Head']]
    K = np.array([d.co for d in k.data]); Dk = K - Bm; Fk = Dk.copy()
    for r_, verts in enumerate(by_ring, start=1):
        w = RING_W[r_ - 1]
        for v in verts:
            inner = [u for u in mnbr.get(v, []) if ring.get(u) == r_ - 1]
            Fk[v] = np.mean(Fk[inner], axis=0) if inner else Dk[v]
            K[v] = Bm[v] + w * Fk[v] + (1 - w) * Dk[v]
    k.data.foreach_set('co', K.ravel())
corner_w = [BW[up_arc[0]], BW[up_arc[-1]]]
ncorner = 0
# the dark corners join a drawn mouth line to the cavity plate of an open head; a closed head has no plate (its fold
# closes the mouth), and darkened corners there showed at rest as black wedges (11-25)
for p in (me.polygons if SKULL is not None else ()):
    vs = list(p.vertices)
    if max(vs) >= N_ORIG: continue
    pocket = any(v in hidden for v in vs)
    outer_up = (not pocket) and all(v in upset or ring.get(v) == 1 for v in vs) and any(ring.get(v) == 1 for v in vs) and any(v in upset for v in vs)
    if pocket:                                              # side walls of the pocket near each corner
        cw = BW[vs].mean(0)
        if min(np.linalg.norm(cw - c) for c in corner_w) > 0.0045: continue
    elif outer_up:
        if min(min(np.linalg.norm(BW[v] - c) for c in corner_w) for v in vs if v in arcset) > 0.0035: continue
    else:
        continue
    for li in p.loop_indices: uvd[li].uv = spots['dark'][:2]
    ncorner += 1
report['mouthRings'] = dict(rings=[len(x) for x in by_ring], cornerFaces=ncorner)
# one-sided smile and frown: the processed closed smile / sad mouth, faded across the middle of the mouth
def _sidew(s_, P_):
    t = np.clip(((P_[:, 0] - mx(0.003)) * (1 if s_ == 'L' else -1)) / (0.012 * KM) + 0.5, 0, 1)
    return (t * t * (3 - 2 * t))[:, None]
_Bm = np.array([v.co for v in kb['Basis'].data]); _BWm = _Bm @ M3.T + T
for side, s_ in (('Left', 'L'), ('Right', 'R')):
    for name, src, gain in (('mouthSmile' + side, 'happy_mouth', 0.85), ('mouthFrown' + side, 'sad_mouth', 1.6)):
        helper.ensure_expression(name)
        Dm = np.array([v.co for v in kb[helper.state['keys'][src]['Head']].data]) - _Bm
        kb[helper.state['keys'][name]['Head']].data.foreach_set('co', (_Bm + gain * Dm * _sidew(s_, _BWm)).ravel())

# ---------------------------------------------------------------- inner lips follow their lip; smooth opening edge
# user, 11-20 (人物2): the open mouth's inner edge zigzagged and the fold behind the lips stretched into spikes. The
# opening edge is the lip seam's mesh edges, which zigzag on a sparse seam: in every mouth shape the two lip arcs are
# smoothed along their length (corners fixed) and the rings next to them take a fading share of that correction. The
# fold behind the lips (hidden at rest) moves with its own lip, the upper half with the upper arc and the lower half
# with the lower arc, sinking back as the mouth opens; the faces joining the two halves become the dark back wall.
INNER = dict(sigma=1.3, ring_share=0.55, sink=0.8)
_arcU, _arcL = np.array(up_arc, dtype=int), np.array(lo_arc, dtype=int)
_hid = np.array(sorted(v for v in hidden if v < len(BW) and v not in set(up_arc) | set(lo_arc)), dtype=int)
_lineP = BW[np.array(list(dict.fromkeys(list(up_arc) + list(lo_arc))))]
_lo_ = np.argsort(_lineP[:, 0])
_upper_side = BW[_hid, 2] > np.interp(BW[_hid, 0], _lineP[_lo_, 0], _lineP[_lo_, 2])
# Which lip a pocket vertex belongs to is decided by connection (nearest lip arc along the pocket's own edges), the
# height only where no edge path exists. 人物2's lips curl in past each other (the upper lip's inner end 1.4 mm below
# the lower lip's): by height each lip's inner end went with the other lip and the walls crossed into a spiked
# membrane when the mouth opened (11-25).
_hidset = set(_hid.tolist()); _cor = {up_arc[0], up_arc[-1]}
_adjh = {}
for e in me.edges:
    a, b = e.vertices
    if a in _hidset or b in _hidset:
        _adjh.setdefault(a, []).append(b); _adjh.setdefault(b, []).append(a)
_gd, _glab, _pq = {}, {}, []
for arc, lab in ((up_arc, True), (lo_arc, False)):
    for v in arc:
        if v not in _cor: _gd[v] = 0.0; _glab[v] = lab; heapq.heappush(_pq, (0.0, v))
while _pq:
    d_, u_ = heapq.heappop(_pq)
    if d_ > _gd[u_]: continue
    for w_ in _adjh.get(u_, []):
        if w_ not in _hidset: continue
        nd_ = d_ + float(np.linalg.norm(BW[u_] - BW[w_]))
        if nd_ < _gd.get(w_, 1e9): _gd[w_] = nd_; _glab[w_] = _glab[u_]; heapq.heappush(_pq, (nd_, w_))
_byz = _upper_side.copy()
_upper_side = np.array([_glab.get(int(v), bool(z_)) for v, z_ in zip(_hid, _byz)], dtype=bool)
report['innerSide'] = dict(byConnection=int(sum(int(v) in _glab for v in _hid)), differsFromHeight=int((_upper_side != _byz).sum()))
from mathutils.kdtree import KDTree as _KDT
def _arc_tree(arc):
    t_ = _KDT(len(arc))
    for i_, a_ in enumerate(arc): t_.insert(Vector(BW[a_]), i_)
    t_.balance(); return t_
_tU, _tL = _arc_tree(_arcU), _arc_tree(_arcL)
_near = np.array([_arcU[_tU.find(Vector(BW[v]))[1]] if up_ else _arcL[_tL.find(Vector(BW[v]))[1]]
                  for v, up_ in zip(_hid, _upper_side)], dtype=int)
_dep = np.clip(BW[_hid, 1] - BW[_near, 1], 0, None); _depn = _dep / max(float(_dep.max()) if len(_dep) else 0.0, 1e-4)
def _smooth_arc(P_):
    n_ = len(P_)
    if n_ < 5: return P_
    sl = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
    h_ = INNER['sigma'] * sl[-1] / (n_ - 1); out_ = P_.copy()
    for i_ in range(1, n_ - 1):
        w_ = np.exp(-0.5 * ((sl - sl[i_]) / h_) ** 2); out_[i_] = (w_[:, None] * P_).sum(0) / w_.sum()
    return out_
_Bk = np.array([v.co for v in kb['Basis'].data])
_inner_rep = {}
# The smoothing has two parts: the shape's own motion, and the resting zigzag of the seam, which only shows once the
# lips part. Every shape carried the full resting part, so tracked shapes added together (smile + stretch + dimple +
# jaw) applied it four to seven times and the edges overshot into notches; the closed smile opened two small gaps
# (11-25). The resting part now comes in proportion to how far the shape opens the mouth (aa: all of it).
_rest_fix = {id(a_): _smooth_arc(BW[a_]) - BW[a_] for a_ in (_arcU, _arcL)}
def _opening_of(name):
    D_ = (np.array([v.co for v in kb[helper.state['keys'][name]['Head']].data]) - _Bk) @ M3.T
    return max(0.0, float(D_[_arcU, 2].mean() - D_[_arcL, 2].mean()))
_open_ref = max(_opening_of('aa'), 1e-4)
for name in list(dict.fromkeys(MOUTH_KEYS + ['mouthSmileLeft', 'mouthSmileRight', 'mouthFrownLeft', 'mouthFrownRight'])):
    k = kb[helper.state['keys'][name]['Head']]
    Dw = (np.array([v.co for v in k.data]) - _Bk) @ M3.T
    corr = np.zeros_like(Dw)
    _a = min(1.0, max(0.0, float(Dw[_arcU, 2].mean() - Dw[_arcL, 2].mean())) / _open_ref)
    for arc in (_arcU, _arcL):
        P_ = BW[arc] + Dw[arc]; corr[arc] = _smooth_arc(P_) - P_ - (1.0 - _a) * _rest_fix[id(arc)]
    for r_, verts in enumerate(by_ring, start=1):           # rings beside the opening take a fading share
        for v in verts:
            inner = [u for u in mnbr.get(v, []) if ring.get(u) == r_ - 1]
            if inner: corr[v] = INNER['ring_share'] * corr[inner].mean(0)
    Dw += corr
    opening = max(0.0, float(Dw[_arcU, 2].mean() - Dw[_arcL, 2].mean()))
    if len(_hid):
        Dw[_hid] = Dw[_near]
        Dw[_hid, 1] += INNER['sink'] * opening * _depn
    k.data.foreach_set('co', (_Bk + Dw @ M3i.T).ravel())
    _inner_rep[name] = round(float(np.abs(corr).max()) * 1000, 2)
_side_of = {int(v): bool(u) for v, u in zip(_hid, _upper_side)}      # pocket faces only: faces on the lip line show at rest
_nbridge = 0
for p in me.polygons:
    sd = [_side_of[v] for v in p.vertices if v in _side_of]
    if len(sd) == len(p.vertices) and any(sd) and not all(sd):
        for li in p.loop_indices: uvd[li].uv = spots['dark'][:2]
        _nbridge += 1
report['innerLips'] = dict(pocketVerts=int(len(_hid)), upper=int(_upper_side.sum()), backWallFaces=_nbridge,
                           edgeSmoothMaxMm=max(_inner_rep.values()) if _inner_rep else 0)

# Mouth width limit (user, 11-20): the smile and the sad mouth are the widest the mouth gets. Every other mouth shape
# that spreads the mouth wider is narrowed horizontally (its vertical motion kept) to that width; the opening vowels
# (jaw drop, rounded lips) hardly widen a mouth, so they stay within OPEN_WIDTH of the closed mouth. Measured at the
# corners one sees: on a closed head the lip fold runs ~4 mm past them into the cheek, and its ends stayed within the
# limit while the visible corners spread past it (11-25, 人物2: ih 1.29, angry 1.29, relaxed 1.27 against happy 1.22).
# Applied after the inner-lip pass, which moves the arcs.
OPEN_WIDTH = 1.05
OPEN_KEYS = ('aa', 'oh', 'ou', 'surprised_mouth')
import sys
sys.path.insert(0, _POLISH + '/expr')
from mouth_width import horizontal_gain
_Bm = np.array([v.co for v in kb['Basis'].data]); _BWm = _Bm @ M3.T + T
if LM:
    _vc = [int(skin[np.argmin(np.linalg.norm(_BWm[skin] - np.array(LM[k_]), axis=1))]) for k_ in ('mouthR', 'mouthL')]
else:
    _vc = [cR, cL]
corner_x = _BWm[_vc, 0]
def mouth_displacement(name):
    key = kb[helper.state['keys'][name]['Head']]
    return (np.array([v.co for v in key.data]) - _Bm) @ M3.T
rest_span = float(np.ptp(corner_x))
reference_span = max(np.ptp(corner_x + mouth_displacement(e)[_vc, 0]) for e in ('happy_mouth', 'sad_mouth'))
limit = max(rest_span, reference_span)
report['mouthWidthLimit'] = {'limit_over_rest': round(float(limit / rest_span), 3), 'corners': _vc}
# Mood mouths at a natural size (user, 11-26: angry and sad read as a big mouth: angry spread to the smile's width and
# pushed the upper lip up into a wide arch). Facial-movement data (Coulson et al. 2000; FACS AU15/AU23/AU24): pulling the
# corners down moves them about 5 mm at full effort on a 47 mm mouth (0.1 mouth widths); pressing or tightening the lips
# neither widens nor opens the mouth. Angry and sad keep the closed width, part the lips at most MOOD['open'], arch at
# most MOOD['arc'] (middle of the lip line against the lower corner), raise the middle of the upper lip at most
# MOOD['rise'] (人物2's angry mouth raised it 6.6 mm in a wide arch) and drop the corners at most MOOD['drop'] (mouth
# widths). An angry mouth that is mostly a parted snarl (scaled under half to fit) becomes the pressed frown: the sad
# mouth at MOOD['angry_frown'] of its size. A stylised head may set mouth_mood: false in its build config.
MOOD = dict(width=1.0, open=0.03, arc=0.10, rise=0.04, drop=0.06, angry_frown=0.8)
_mm = (json.load(open(_os.environ['POLISH_BUILD_CONFIG'])) if _os.environ.get('POLISH_BUILD_CONFIG') and _os.path.isfile(_os.environ['POLISH_BUILD_CONFIG']) else {}).get('mouth_mood', {})
MOOD_KEYS = () if _mm is False else ('sad_mouth', 'mouthFrownLeft', 'mouthFrownRight', 'angry_mouth')
MOOD.update(_mm if isinstance(_mm, dict) else {})
for name in MOUTH_KEYS + ['mouthSmileLeft', 'mouthSmileRight', 'mouthFrownLeft', 'mouthFrownRight']:
    if name == 'mouthNarrow': continue
    delta = mouth_displacement(name)
    lim_ = min(limit, OPEN_WIDTH * rest_span) if name in OPEN_KEYS else limit
    if name in MOOD_KEYS: lim_ = min(lim_, MOOD['width'] * rest_span)
    gain = horizontal_gain(corner_x, delta[_vc, 0], lim_)
    if gain < 1:
        delta[:, 0] *= gain
        kb[helper.state['keys'][name]['Head']].data.foreach_set('co', (_Bm + delta @ M3i.T).ravel())
        report['mouthWidthLimit'][name] = round(gain, 4)
def _mood_shape(D_):
    # corner drop, arch and parting of the lip line, in rest mouth widths
    ua_, la_ = np.array(up_arc), np.array(lo_arc); xc_ = float(corner_x.mean())
    cz_ = D_[_vc, 2]; low_ = float(cz_.min())
    allx_ = np.r_[_BWm[ua_, 0], _BWm[la_, 0]]; alldz_ = np.r_[D_[ua_, 2], D_[la_, 2]]
    mid_ = np.abs(allx_ - xc_) < 0.2 * rest_span
    arc_ = (float(alldz_[mid_].mean()) - low_) if mid_.any() else 0.0
    gap_ = 0.0
    for b0 in np.linspace(xc_ - 0.4 * rest_span, xc_ + 0.3 * rest_span, 8):
        su_ = np.abs(_BWm[ua_, 0] - (b0 + 0.05 * rest_span)) < 0.05 * rest_span; sl_ = np.abs(_BWm[la_, 0] - (b0 + 0.05 * rest_span)) < 0.05 * rest_span
        if su_.any() and sl_.any(): gap_ = max(gap_, float(D_[ua_[su_], 2].mean() - D_[la_[sl_], 2].mean()))
    umid_ = np.abs(_BWm[ua_, 0] - xc_) < 0.3 * rest_span
    rise_ = max(0.0, float(D_[ua_[umid_], 2].max())) if umid_.any() else 0.0
    return dict(drop=-low_ / rest_span, arc=arc_ / rest_span, open=gap_ / rest_span, rise=rise_ / rest_span)
report['mouthMood'] = {}
for name in MOOD_KEYS:
    if name not in helper.state['keys']: continue
    delta = mouth_displacement(name); m0 = _mood_shape(delta)
    g_ = min([1.0] + [MOOD[k_] / m0[k_] for k_ in ('drop', 'arc', 'open', 'rise') if m0[k_] > 1e-6])
    how = 'scaled'
    if name == 'angry_mouth' and g_ < 0.5 and 'sad_mouth' in helper.state['keys']:
        delta = MOOD['angry_frown'] * mouth_displacement('sad_mouth'); g_ = 1.0; how = 'frown'
    delta = g_ * delta
    kb[helper.state['keys'][name]['Head']].data.foreach_set('co', (_Bm + delta @ M3i.T).ravel())
    report['mouthMood'][name] = dict(before={k_: round(v_, 3) for k_, v_ in m0.items()}, after={k_: round(v_, 3) for k_, v_ in _mood_shape(delta).items()}, gain=round(g_, 3), how=how)
# corner positions (build world) for the player, which keeps combined shapes (tracked smile + stretch + jaw) within
# the same width with mouthNarrow (post/vrm_finalize.py writes the per-expression corner motion into the VRM)
_frm = json.loads(_os.environ.get('POLISH_FRAME') or '{"s": 1.0, "t": [0, 0, 0]}')    # profile frame -> build world
report['mouthCornersWorld'] = [[round(float(_frm['s'] * _BWm[v_, i_] + _frm['t'][i_]), 6) for i_ in range(3)] for v_ in _vc]

# ---------------------------------------------------------------- mouth cavity and tongue (head-weighted, existing texture)
skull_set = set(comps[SKULL]) if SKULL is not None else set()      # a closed head has no added cranium
t_skull = None
if skull_set:
    bms = bmesh.new(); bms.from_mesh(me); bms.verts.ensure_lookup_table()
    bmesh.ops.delete(bms, geom=[v for v in bms.verts if v.index not in skull_set], context='VERTS')
    bms.transform(h.matrix_world); t_skull = BVHTree.FromBMesh(bms)
bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
layers = [bm.verts.layers.shape[k.name] for k in kb]
dfl = bm.verts.layers.deform.verify(); uvl = bm.loops.layers.uv.active
head_gi = h.vertex_groups['head'].index
MWi = h.matrix_world.inverted()
def add_vert(pw):
    p = MWi @ Vector(pw); v = bm.verts.new(p)
    for L in layers: v[L] = p
    v[dfl][head_gi] = 1.0
    return v
cx, cz = mx(0.003), mz(1.470)
NX, NZc = 40, 30
grid = []
# a closed head (no added cranium): the inner lips and the dark back wall between them close the mouth; the plate
# behind it showed through the jaw and left gaps at its sides (11-20), so it is not added
_closed_head = SKULL is None and len(_hid) > 0
# An open face shell with a lip fold gets a closed mouth bag instead of the plate (user, 11-26: the first character's
# mouth was not closed; at 45 degrees the plate's edge and the pink inside of the face shell showed past its sides).
# Same idea as the pocket of a closed head: the bag's rim sits just behind the skin around the mouth (hidden at rest),
# it reaches about one mouth width back and closes there; its lower half moves with the lower lip, the upper half with
# the upper lip; inside it darkens with depth, the tongue lies on its floor. The faces bridging the two halves of the
# fold (the shallow dark back wall) are removed so the bag is what shows. mouth_bag: false in the build config keeps
# the plate.
MOUTH_BAG = dict(rim_x=1.35, rim_z=0.9, behind=0.003, depth=1.1, rings=8, around=48, low_band=0.6)
_mb = (json.load(open(_os.environ['POLISH_BUILD_CONFIG'])) if _os.environ.get('POLISH_BUILD_CONFIG') and _os.path.isfile(_os.environ['POLISH_BUILD_CONFIG']) else {}).get('mouth_bag', {})
MOUTH_BAG.update(_mb if isinstance(_mb, dict) else {})
_bag = (not _closed_head) and len(_hid) > 0 and _mb is not False
for j in (range(NZc + 1) if not (_closed_head or _bag) else ()):
    z = mz(1.448) + (mz(1.494) - mz(1.448)) * j / NZc; row = []
    for i in range(NX + 1):
        x = cx - 0.030 * KM + 0.060 * KM * i / NX
        ex, ez = (x - cx) / (0.030 * KM), (z - cz) / (0.023 * KM)
        y = my(-0.0865) + 0.004 * KM * min(1.0, ex * ex + ez * ez)
        hs = t_skull.ray_cast(Vector((x, -0.3, z)), Vector((0, 1, 0)), 0.5) if t_skull else (None,)
        if hs[0] is not None: y = min(y, hs[0].y - 0.0015)
        if LM:                                          # another face: only behind the mouth, well behind its skin
            _hw = 0.5 * abs(LM['mouthL'][0] - LM['mouthR'][0])
            if ((x - LM['mouth'][0]) / (1.35 * _hw)) ** 2 + ((z - LM['mouth'][2]) / (0.9 * _hw)) ** 2 > 1:
                row.append(None); continue
            hf_ = _skin_bvh.ray_cast(Vector((x, -0.4, z)), Vector((0, 1, 0)), 1.0)
            if hf_[0] is None:
                row.append(None); continue
            y = max(y, hf_[0].y + 0.004)
        row.append(add_vert((x, y, z)))
    grid.append(row)
cav_faces = []
for j in (range(NZc) if grid else ()):
    for i in range(NX):
        q_ = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]]
        if any(v_ is None for v_ in q_): continue
        f = bm.faces.new(q_); f.material_index = slot; f.smooth = True
        for l in f.loops: l[uvl].uv = spots['dark'][:2]
        cav_faces.append(f)
# the skull's mouth recess (pushed back at build time) shows past the cavity's sides at an angle: dark too
nrecess = 0
for f in bm.faces:
    if f.verts[0].index >= N_ORIG or not all(v.index in skull_set for v in f.verts if v.index < N_ORIG): continue
    c = h.matrix_world @ f.calc_center_median()
    if ((c.x - mx(0.003)) / (0.042 * KM)) ** 2 + ((c.z - mz(1.47)) / (0.037 * KM)) ** 2 > 1 or c.y > my(-0.055): continue
    f.material_index = slot
    for l in f.loops: l[uvl].uv = spots['dark'][:2]
    nrecess += 1
report['skullRecessDark'] = nrecess
bag_vs, _bag_rep = [], {}
if _bag:
    MB = MOUTH_BAG
    _cxb, _hwb = float(corner_x.mean()), 0.5 * rest_span
    _czb = float(np.interp(_cxb, _lineP[_lo_, 0], _lineP[_lo_, 2]))           # lip line at the middle
    _cyb = float(np.r_[BW[up_arc, 1], BW[lo_arc, 1]].mean())
    rimP = []
    for i_ in range(MB['around']):
        th_ = 2 * math.pi * i_ / MB['around']
        x_, z_ = _cxb + MB['rim_x'] * _hwb * math.cos(th_), _czb + MB['rim_z'] * _hwb * math.sin(th_)
        hit_ = _skin_bvh.ray_cast(Vector((x_, -0.4, z_)), Vector((0, 1, 0)), 1.0)
        rimP.append((x_, (hit_[0].y if hit_[0] is not None else _cyb + 0.01) + MB['behind'], z_))
    rimP = np.array(rimP); Cb = np.array([_cxb, float(rimP[:, 1].mean()), _czb]); Db = MB['depth'] * 2 * _hwb
    n_bag0 = len(bm.verts); rings_ = []
    for k_ in range(MB['rings']):
        t_ = k_ / MB['rings']; s_ = math.sqrt(max(0.0, 1 - t_ * t_))
        rings_.append([add_vert(tuple(Cb + s_ * (p_ - Cb) + np.array([0.0, Db * t_, 0.0]))) for p_ in rimP])
    apex_ = add_vert(tuple(Cb + np.array([0.0, Db, 0.0])))
    n_bag1 = len(bm.verts); bag_faces = []
    def _tone(t_):
        return 'innerlip' if t_ < 0.12 else ('midred' if t_ < 0.3 else 'dark')
    for k_ in range(MB['rings']):
        for i_ in range(MB['around']):
            j_ = (i_ + 1) % MB['around']
            q_ = [rings_[k_][i_], rings_[k_][j_]] + ([rings_[k_ + 1][j_], rings_[k_ + 1][i_]] if k_ + 1 < MB['rings'] else [apex_])
            f_ = bm.faces.new(q_); f_.material_index = slot; f_.smooth = True
            for l_ in f_.loops: l_[uvl].uv = spots[_tone((k_ + 0.5) / MB['rings'])][:2]
            bag_faces.append(f_)
    bm.normal_update()
    _R3 = h.matrix_world.to_3x3()
    for f_ in bag_faces:                                   # faces look into the bag (seen through the open lips)
        c_ = h.matrix_world @ f_.calc_center_median()
        if (_R3 @ f_.normal).dot(Vector((Cb[0], c_.y, Cb[2])) - c_) < 0: f_.normal_flip()
    # the bridge between the fold's halves goes: the bag is the back of the mouth now
    _br = [f_ for f_ in bm.faces if f_.verts[0].index < N_ORIG and all(v_.index in _side_of for v_ in f_.verts)
           and len({_side_of[v_.index] for v_ in f_.verts}) == 2]
    bmesh.ops.delete(bm, geom=_br, context='FACES_ONLY')
    bag_vs = list(range(n_bag0, n_bag1))
    _bag_rep = dict(rim=len(rimP), rings=MB['rings'], faces=len(bag_faces), depthMm=round(Db * 1000, 1), bridgeRemoved=len(_br))
# tongue: flattened ellipsoid low in the cavity
tc, trad = np.array([mx(0.003), my(-0.0905), mz(1.4632)]), min(KM, 1.2) * np.array([0.0125, 0.0058, 0.0043])
if _closed_head:
    # just behind the deepest part of the fold, below the lip line: hidden at rest, in front of the back wall once it sinks
    _xc = 0.5 * (BW[up_arc[0], 0] + BW[up_arc[-1], 0])
    _zc = float(np.interp(_xc, _lineP[_lo_, 0], _lineP[_lo_, 2]))
    tc = np.array([_xc, float(BW[_hid, 1].max()) + trad[1] + 0.0008, _zc - trad[2] - 0.0015])
    _hf = _skin_bvh.ray_cast(Vector((tc[0], tc[1] - 0.3, tc[2] - trad[2])), Vector((0, 1, 0)), 1.0)
    if _hf[0] is not None and tc[1] - trad[1] < _hf[0].y + 0.002:
        tc[1] = _hf[0].y + 0.002 + trad[1]
if _bag:
    # on the bag's floor, a little less than half way back
    _tt = 0.42; _sb = math.sqrt(1 - _tt * _tt)
    tc = np.array([Cb[0], Cb[1] + _tt * Db, Cb[2] + _sb * (float(rimP[:, 2].min()) - Cb[2]) + trad[2] + 0.001])
tb = bmesh.new(); bmesh.ops.create_uvsphere(tb, u_segments=24, v_segments=12, radius=1.0); tb.verts.ensure_lookup_table()
tmap = {}
for v in tb.verts:
    tmap[v] = add_vert(tuple(tc + np.array(v.co) * trad))
tongue_faces = []
for f in tb.faces:
    nf = bm.faces.new([tmap[v] for v in f.verts]); nf.material_index = slot; nf.smooth = True
    for l in nf.loops: l[uvl].uv = spots['tongue'][:2]
    tongue_faces.append(nf)
bm.normal_update()
for f in cav_faces:
    if (h.matrix_world.to_3x3() @ f.normal).y > 0: f.normal_flip()
n_before = len(me.vertices)
bm.to_mesh(me); me.update()
tongue_vs = list(range(len(me.vertices) - len(tb.verts), len(me.vertices)))
# tongue follows the lower lip half way down, a little forward
kb = me.shape_keys.key_blocks
B = np.array([v.co for v in kb['Basis'].data])
LOa = np.array(lo_arc); mid = LOa[len(LOa) // 3: 2 * len(LOa) // 3]
for e in MOUTH_KEYS:
    k = kb[helper.state['keys'][e]['Head']]
    Dl = (np.array([k.data[v].co for v in mid]) - B[mid]).mean(0)
    dw = M3 @ Dl; dw = np.array([0.0, dw[1] * 0.4, dw[2] * 0.5])
    off = M3i @ dw
    for v in tongue_vs: k.data[v].co = (B[v] + off).tolist()
if bag_vs:
    # every shape that moves the lips moves the bag: its lower half with the middle of the lower lip, the upper half
    # with the middle of the upper lip, blended across the lip line
    UPa = np.array(up_arc); midU = UPa[len(UPa) // 3: 2 * len(UPa) // 3]
    Bw_ = B[bag_vs] @ M3.T + T
    wl_ = np.clip((_czb + 0.15 * _hwb - Bw_[:, 2]) / (MOUTH_BAG['low_band'] * _hwb), 0, 1); wl_ = (wl_ * wl_ * (3 - 2 * wl_))[:, None]
    nb_ = 0
    for e_, kk_ in helper.state['keys'].items():
        if 'Head' not in kk_ or kk_['Head'] not in kb: continue
        k = kb[kk_['Head']]
        K_ = np.array([d.co for d in k.data])
        dL_ = (K_[mid] - B[mid]).mean(0); dU_ = (K_[midU] - B[midU]).mean(0)
        if np.abs(dL_).max() < 1e-6 and np.abs(dU_).max() < 1e-6: continue
        K_[bag_vs] = B[bag_vs] + wl_ * dL_ + (1 - wl_) * dU_
        k.data.foreach_set('co', K_.ravel()); nb_ += 1
    _bag_rep['shapes'] = nb_
report['cavity'] = dict(cavityFaces=len(cav_faces), tongueVerts=len(tongue_vs), closedHead=bool(_closed_head),
                       tongueCentre=[round(float(x), 4) for x in tc], mouthBag=_bag_rep or None)
# tongueOut opens the lips a little and slides the tongue forward onto the lower lip
_Da = np.array([v.co for v in kb[helper.state['keys']['aa']['Head']].data]) - B
helper.ensure_expression('tongueOut')
_Dt = 0.4 * _Da
_Dt[tongue_vs] = M3i @ np.array([0.0, -0.006, 0.002]) + 0.4 * _Da[tongue_vs]
kb[helper.state['keys']['tongueOut']['Head']].data.foreach_set('co', (B + _Dt).ravel())

# ---------------------------------------------------------------- even toon shading on the eyeball parts
fwd = M3i @ np.array([0.0, -1.0, 0.0]); fwd /= np.linalg.norm(fwd)
bset = set(int(i) for s in ball for i in ball[s])
bset |= set(bag_vs)                      # the mouth bag too: toon shading drew its inner faces as light and dark patches
cn = np.array([list(c.vector) for c in me.corner_normals])
for li, l in enumerate(me.loops):
    if l.vertex_index in bset: cn[li] = fwd
me.normals_split_custom_set([tuple(n) for n in cn]); me.update()
# ---------------------------------------------------------------- gaze (per eye, ARKit names)
# The white is not a sphere (Tripo), so the iris and its highlights slide over it instead of rotating: x/z shift in
# the eye plane, depth from a quadratic fitted to the white inside the opening, so the iris stays on the white and
# goes under the lid skin at the corners. The upper lid follows a little (down: part of that eye's blink; up: part
# of that eye's surprised lid). The four VRM look expressions are built from these after export.
kb = me.shape_keys.key_blocks
Bg = np.array([v.co for v in kb['Basis'].data]); BWg = Bg @ M3.T + T
GAZE = dict(out=0.0085, inn=0.0075, up=0.0045, down=0.0050, lid_down=0.25, lid_up=0.3, white_in=0.05, white_out=0.3, white_pin=0.0015, white_pin_fade=0.003)
GAZE_LIMIT = dict(pupil=0.35, pupil_keep=0.3, pupil_room=2.0)   # pupil radius in iris radii; the rest in pupil radii (cut iris layer)
IRIS_EXT = 1.15                                         # face/iris_layer.py EXT: the iris texture spans +- EXT iris radii
IRIS_MAP = {}
def _keyd(name):
    return np.array([v.co for v in kb[helper.state['keys'][name]['Head']].data]) - Bg
def _side(s_):                                          # 1 on that side of the face, feathered over 1 cm
    t = np.clip(((BWg[:, 0] - 0.003) * (1 if s_ == 'L' else -1)) / 0.01 + 0.5, 0, 1)
    return (t * t * (3 - 2 * t))[:, None]
_sur = _keyd('surprised_eye')
report['gaze'] = {}
for s_, side in (('L', 'Left'), ('R', 'Right')):
    Q = BWg[np.array(comps[SCLERA[s_]])]; zr = BWg[rimloop[s_], 2]
    keep = (Q[:, 2] > zr.min()) & (Q[:, 2] < zr.max())
    Xf = lambda P_: np.c_[np.ones(len(P_)), P_[:, 0], P_[:, 2], P_[:, 0] ** 2, P_[:, 0] * P_[:, 2], P_[:, 2] ** 2]
    for _ in range(4):                                  # robust: the white curls back at the top; refit on the front sheet
        coef, *_ = np.linalg.lstsq(Xf(Q[keep]), Q[keep, 1], rcond=None)
        r_all = np.abs(Xf(Q) @ coef - Q[:, 1])
        keep = keep & (r_all < max(0.0015, 2.5 * float(np.median(r_all[keep]))))
    resid = np.abs(Xf(Q[keep]) @ coef - Q[keep, 1])
    report.setdefault('gazeFitKept', {})[s_] = int(keep.sum())
    ivs = iris[s_]; o_ = 1 if s_ == 'L' else -1
    G_ = GAZE
    if IRIS_LAYER:
        # the cut iris layer's texture slides over the eyeball, travel in eye widths, so the painted lids on the
        # lid layer in front of it cover it at the ends, as the lids would (profile travel was set on the purple eye)
        rim_ = BWg[rimloop[s_]]; ew_ = float(np.ptp(rim_[:, 0])); eh_ = float(np.ptp(rim_[:, 2]))
        G_ = dict(GAZE, out=0.22 * ew_, inn=0.20 * ew_, up=0.30 * eh_, down=0.30 * eh_)
        # at full weight the pupil stays inside the opening: its centre at least pupil_keep pupil radii inside the lid
        # line above / below, and sideways no farther than where the opening is still pupil_room pupil radii tall
        # (11-25, 人物2: the painted iris is twice as tall as the opening and its centre 1.8 mm under the upper lid;
        # 0.30 of the opening height took the pupil under the lid, and with a second gaze channel on top the iris
        # disappeared, "rolled-back eyes")
        # the layer is a fixed grid with the iris texture mapped around the iris centre (face/iris_layer.py): centre
        # and size from that mapping, x = a + b u, z = c + d v (b = d = 2 EXT r)
        _Pi = BWg[ivs]; _UVi = np.array([IRIS_UV[v] for v in ivs])
        (_au, _bu), (_av, _bv) = [np.linalg.lstsq(np.c_[np.ones(len(ivs)), _UVi[:, k_]], _Pi[:, c_], rcond=None)[0] for k_, c_ in ((0, 0), (1, 2))]
        _xc, _zc = float(_au + 0.5 * _bu), float(_av + 0.5 * _bv); _ri = 0.5 * abs(float(_bu)) / IRIS_EXT
        IRIS_MAP[s_] = (float(_bu), float(_bv))
        _rl = BWg[_ordered(set(rimloop[s_]))][:, [0, 2]]
        def _lids(x_):
            zs_ = []
            for a_, b_ in zip(_rl, np.roll(_rl, -1, 0)):
                if (a_[0] - x_) * (b_[0] - x_) <= 0 and a_[0] != b_[0]:
                    zs_.append(a_[1] + (x_ - a_[0]) / (b_[0] - a_[0]) * (b_[1] - a_[1]))
            return (max(zs_), min(zs_)) if len(zs_) >= 2 else None
        _l0 = _lids(_xc)
        report.setdefault('gazeLimit', {})[s_] = dict(iris_r_mm=round(_ri * 1000, 2), lid_top_mm=round((_l0[0] - _zc) * 1000, 2) if _l0 else None,
                                                     lid_bottom_mm=round((_zc - _l0[1]) * 1000, 2) if _l0 else None, rim_pts=len(_rl))
        if _l0 is not None:
            _rp = GAZE_LIMIT['pupil'] * _ri
            G_['up'] = min(G_['up'], max(0.0, _l0[0] - _zc - GAZE_LIMIT['pupil_keep'] * _rp))
            G_['down'] = min(G_['down'], max(0.0, _zc - _l0[1] - GAZE_LIMIT['pupil_keep'] * _rp))
            for key_, sgn_ in (('out', o_), ('inn', -o_)):
                reach_ = 0.0
                for t_ in np.linspace(0, G_[key_], 40):
                    l_ = _lids(_xc + sgn_ * t_)
                    if l_ is None or l_[0] - l_[1] < GAZE_LIMIT['pupil_room'] * _rp: break
                    reach_ = t_
                G_[key_] = reach_
        report.setdefault('gazeLayer', {})[s_] = {k_: round(G_[k_] * 1000, 2) for k_ in ('out', 'inn', 'up', 'down')}
    elif not PIECES['iris']:
        # iris painted on the eyeball: the whole eyeball slides behind the opening, as far as it reaches past the rim
        ivs = ids([SCLERA[s_]] + SCLERA_EXTRA[s_]); rim_ = BWg[rimloop[s_]]; Pb_ = BWg[ivs]
        mxg = 0.9 * min(Pb_[:, 0].max() - rim_[:, 0].max(), rim_[:, 0].min() - Pb_[:, 0].min())
        mzg = 0.9 * min(Pb_[:, 2].max() - rim_[:, 2].max(), rim_[:, 2].min() - Pb_[:, 2].min())
        G_ = dict(GAZE, out=min(GAZE['out'], max(mxg, 0.0)), inn=min(GAZE['inn'], max(mxg, 0.0)),
                  up=0.5 * min(GAZE['up'], max(mzg, 0.0)), down=0.5 * min(GAZE['down'], max(mzg, 0.0)))
        report.setdefault('gazePainted', {})[s_] = {k_: round(G_[k_] * 1000, 2) for k_ in ('out', 'inn', 'up', 'down')}
    P_ = BWg[ivs]
    lid_down = _keyd('blink_' + s_) * _side(s_); lid_down[ivs] = 0
    _zc = 0.5 * (zr.min() + zr.max())                   # upper lid only: the surprised lower lid drops and shows socket skin
    _up = np.clip((BWg[:, 2] - _zc) / 0.004, 0, 1)[:, None]
    lid_up = _sur * _side(s_) * _up; lid_up[ivs] = 0
    # the white slides with the iris (it is the same eyeball): full near the iris, nothing at the opening's edge, so
    # what the iris covered at rest stays covered and the light shading around it moves with it (user, 11-13)
    wvs = np.array(comps[SCLERA[s_]]) if PIECES['iris'] and not IRIS_LAYER else np.zeros(0, int); PW_ = BWg[wvs]
    rim_ = BWg[rimloop[s_]]; xc_, zc_ = P_[:, 0].mean(), P_[:, 2].mean()
    ax_, az_ = 0.5 * np.ptp(rim_[:, 0]), 0.5 * np.ptp(rim_[:, 2])
    r_ = np.hypot((PW_[:, 0] - xc_) / ax_, (PW_[:, 2] - zc_) / az_)
    rin_ = 0.5 * np.ptp(P_[:, 0]) / ax_ + GAZE['white_in']
    rout_ = rin_ + GAZE['white_out']                     # near the lids it stays: moving it there uncovers the socket
    t_ = np.clip((rout_ - r_) / max(rout_ - rin_, 1e-3), 0, 1); ww_ = t_ * t_ * (3 - 2 * t_)
    ww_[np.abs(Xf(PW_) @ coef - PW_[:, 1]) > max(0.0015, 2.5 * float(np.median(resid)))] = 0   # the sheet curling back under the lids stays
    # pinned along the opening's edge: within white_pin of the rim it stays, so no gap opens between lid and white
    ring_ = BWg[_ordered(set(rimloop[s_]))][:, [0, 2]]; A_ = ring_; B_ = np.roll(ring_, -1, 0); AB_ = B_ - A_
    Q2_ = PW_[:, [0, 2]][:, None, :]
    tt_ = np.clip(((Q2_ - A_) * AB_).sum(-1) / np.maximum((AB_ * AB_).sum(-1), 1e-12), 0, 1)
    drim_ = np.linalg.norm(Q2_ - (A_ + tt_[..., None] * AB_), axis=-1).min(1)
    tp_ = np.clip((drim_ - GAZE['white_pin']) / GAZE['white_pin_fade'], 0, 1); ww_ *= tp_ * tp_ * (3 - 2 * tp_)
    report.setdefault('gazeWhite', {})[s_] = dict(verts=int((ww_ > 0.01).sum()), full=int((ww_ > 0.99).sum()))
    for name, (dx, dz, extra) in {f'eyeLookOut{side}': (o_ * G_['out'], 0.0, None), f'eyeLookIn{side}': (-o_ * G_['inn'], 0.0, None),
                                  f'eyeLookUp{side}': (0.0, G_['up'], GAZE['lid_up'] * lid_up), f'eyeLookDown{side}': (0.0, -G_['down'], GAZE['lid_down'] * lid_down)}.items():
        helper.ensure_expression(name)
        qq = P_ + np.array([dx, 0.0, dz]); dy = Xf(qq) @ coef - Xf(P_) @ coef
        if IRIS_LAYER:
            # the texture moves, the grid stays: the iris image moves by (dx, dz) when the texture offset is
            # (-dx / b, dz / d) (glTF v runs down: v = 1 - Blender v)
            _bu, _bv = IRIS_MAP[s_]
            report.setdefault('gazeUV', {})[name] = dict(material=IRIS_MAT[s_], offset=[round(-dx / _bu, 5), round(dz / _bv, 5)])
        if not PIECES['iris']:
            dy = np.maximum(dy, 0.0)                    # the whole eyeball moves: never forward through the lids
        Dl = np.zeros_like(Bg) if extra is None else extra.copy()
        if IRIS_LAYER:
            Dl[ivs] = 0.0
        else:
            Dl[ivs] = np.c_[np.full(len(ivs), dx), dy, np.full(len(ivs), dz)] @ M3i.T
        mw_ = ww_ > 0.001; qw_ = PW_[mw_] + np.c_[dx * ww_[mw_], np.zeros(mw_.sum()), dz * ww_[mw_]]
        dyw_ = Xf(qw_) @ coef - Xf(PW_[mw_]) @ coef
        Dl[wvs[mw_]] = np.c_[dx * ww_[mw_], dyw_, dz * ww_[mw_]] @ M3i.T
        kb[helper.state['keys'][name]['Head']].data.foreach_set('co', (Bg + Dl).ravel())
    report['gaze'][s_] = dict(irisVerts=len(ivs), whiteFitMm=round(float(resid.max()) * 1000, 2))
me.update()
# ARKit eye and brow shapes from the existing symmetric shapes, split by side; cheek puff and nose sneer as small
# surface pushes. eyeBlink, jawOpen, mouthFunnel, mouthPucker and browInnerUp reuse existing shapes after export.
def _setk(name, D_):
    helper.ensure_expression(name); kb[helper.state['keys'][name]['Head']].data.foreach_set('co', (Bg + D_).ravel())
_he, _bs = _keyd('happy_eye'), {s_: _keyd('blink_smile_' + s_) for s_ in 'LR'}
# smiling eyes push the lower lid up (the part of the closed smile eyes that moves up); the upper lid drops a little
_lo = lambda D_: D_ * ((D_ @ M3.T)[:, 2] > 0)[:, None]
_upd = lambda D_: D_ - _lo(D_)
_cr = np.zeros_like(Bg); _cr[:len(cheek_raise)] = cheek_raise
for s_, side in (('L', 'Left'), ('R', 'Right')):
    m_ = _side(s_)
    _setk('eyeSquint' + side, _lo(_bs[s_]))
    _setk('eyeWide' + side, _sur * m_)
    _setk('browDown' + side, _keyd('brow_angry') * m_)
    _setk('browOuterUp' + side, _keyd('brow_surprised') * m_)
    _setk('cheekSquint' + side, _cr * m_ + 0.3 * _lo(_bs[s_]))
_Nw = BWg - np.array([0.003, -0.02, 0.0]); _Nw[:, 2] = 0     # outward = horizontal, away from the head axis (Tripo normals vary)
_Nw /= np.maximum(np.linalg.norm(_Nw, axis=1, keepdims=True), 1e-9)
_skinmask = np.zeros(len(Bg), bool); _skinmask[[v for v in skin if v < len(Bg)]] = True
def _push(centers, radius, amount, direction=None):
    Dw = np.zeros_like(BWg)
    for c_ in centers:
        d_ = np.linalg.norm(BWg - np.array(c_), axis=1); w_ = np.clip(1 - d_ / radius, 0, 1); w_ = w_ * w_ * (3 - 2 * w_)
        w_[~_skinmask] = 0
        Dw += (w_ * amount)[:, None] * (_Nw if direction is None else np.array(direction)[None, :])
    return Dw @ M3i.T
def _surf(x, z):                                        # skin point in front at (x, z)
    hit = _skin_bvh.ray_cast(Vector((x, -0.4, z)), Vector((0, 1, 0)), 1.0)
    return list(hit[0]) if hit[0] is not None else [x, -0.09, z]
_cheeks = [_surf(mx(0.003 + 0.05), mz(1.468)), _surf(mx(0.003 - 0.05), mz(1.468))]
_setk('cheekPuff', _push(_cheeks, 0.032, 0.006))
for s_, side, o_ in (('L', 'Left', 1), ('R', 'Right', -1)):
    _setk('noseSneer' + side, _push([_surf(mx(0.003 + o_ * 0.007), 1.497 + NZ)], 0.009, 0.0012, (0, 0, 1)))
report['arkit'] = dict(cheeks=[[round(c, 3) for c in c_] for c_ in _cheeks])

# >< : eyes closed (blink) and the character's own upper lash strip folded into a chevron pointing at the nose:
# the strip is cut at its middle, the outer half swings up and out, the inner half is mirrored below (its lashes then
# point down, like lower lashes); the lower lashes go behind the closed lid. Drawn strokes stay on the closed lid skin.
# Half-lidded (jito): the upper-lid part of the blink at half weight.
EYEX = dict(hide_back=0.004)                         # lash pieces go 4 mm behind the closed lid
Db = _keyd('blink'); KbW = (Bg + Db) @ M3.T + T
_closed_bvh = _BVH.FromPolygons([Vector(p) for p in KbW], _tri_v)
def _skin_y(x, z):
    hit = _closed_bvh.ray_cast(Vector((x, -0.4, z)), Vector((0, 1, 0)), 1.0)
    return hit[0].y if hit[0] is not None else None
DX = Db.copy(); ex_rep = {}
# 11-16: the folded-lash chevron read as "closed eyes with messy lashes" (user). Now the eye closes and *all* its lash
# pieces go behind the lid; the >< strokes are a decal (face_fx eye_x, drawn by code, projected onto the closed lid).
for s_ in ('L', 'R'):
    on_side = lambda vs: [v for v in vs if (BWg[v, 0] > 0.003) == (s_ == 'L')]
    lash = on_side([v for ci in UPPER_LASH for v in comps[ci]])
    low = on_side([v for ci in LOWER_LASH + LINER[s_] for v in comps[ci]])
    hide = lash + low
    DX[hide] = Db[hide] + (M3i @ np.array([0.0, EYEX['hide_back'], 0.0]))[None, :]
    ex_rep[s_] = dict(lash=len(lash), lower=len(low))
# 11-17 user: >< removed (looked wrong); DX kept for reference only
_up_lid = ((Db @ M3.T)[:, 2] < 0)[:, None]
_setk('eye_jito', 0.5 * Db * _up_lid)
report['eyeX'] = dict(EYEX, sides=ex_rep)
me.update()

# happy = smiling eyes (happy_eye plus a little of the closed smile eyes) with the closed smile mouth;
# happy_open = laugh: closed smile eyes, open mouth, happy brows (one key, so it shows as one expression)
kb = me.shape_keys.key_blocks
B = np.empty(len(me.vertices) * 3, np.float32); kb['Basis'].data.foreach_get('co', B)
def _d(name):
    a = np.empty_like(B); kb[helper.state['keys'][name]['Head']].data.foreach_get('co', a); return a - B
HAPPY_EYE = dict(lower=0.35, upper=0.0)                # parts of the closed smile eyes; a dropped upper lid reads as smug
# 11-18: 0.7 -> 0.35, the user's happy references keep the eyes open (0.7 read sleepy next to them)
_bsw = _d('blink_smile').reshape(-1, 3); _up_ = ((_bsw @ M3.T)[:, 2] > 0)[:, None]
kb[helper.state['keys']['happy_eye']['Head']].data.foreach_set('co', B + (HAPPY_EYE['lower'] * _bsw * _up_ + HAPPY_EYE['upper'] * _bsw * ~_up_).ravel())
helper.ensure_expression('happy_open')
kb[helper.state['keys']['happy_open']['Head']].data.foreach_set('co', B + _d('blink_smile') + _d('laugh_mouth') + _d('brow_happy'))
me.update()
report['happyEye'] = HAPPY_EYE

# ---------------------------------------------------------------- brows over the bangs
# BrowOverlay (a copy of the brow pieces, added in build_character) follows every key of the brow it copies.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('brow_overlay', _POLISH + '/face/brow_overlay.py')
_bo = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_bo)
if PIECES['brow']:
    report['browOverlay'] = _bo.sync_brow_overlay(h, [sel['seed'] for sel in helper.state['brows']['selections'].values()])
# anime face effects (decals added in build_character) follow the surface under them
_spec = _ilu.spec_from_file_location('face_fx', _POLISH + '/face/face_fx.py')
_fxm = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_fxm)
_fxc = json.load(open(_os.environ['POLISH_BUILD_CONFIG'], encoding='utf-8')).get('face_fx')
if _fxc:                                                # decals are optional (a config without face_fx builds none)
    report['faceFx'] = _fxm.sync_fx(h, _fxc)
print('EXPR_BUILD', json.dumps(report, default=float))
helper.note('一括再生成（目・眉・口・口内）', '目：まつ毛と二重線のみ追従、閉眼で虹彩を瞼の裏へ、瞼縁を前へ；眉：描かれた眉はテクスチャから除去済み；口：ポケットを内唇色、口内と舌を追加', '', 'チェックシート')
