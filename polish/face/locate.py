"""Find the parts and landmarks of a Charakuru (Tripo) head from its geometry and texture colours.

locate(P, comps, bounds, vcol) -> dict(roles, landmarks, eye_points)
  P       vertex positions (N x 3), in a frame where -Y is the face front and +Z is up
  comps   connected components (lists of vertex ids), as the kit's expression helper lists them (largest first)
  bounds  boundary loops of each component (lists of vertex ids)
  vcol    texture colour per vertex (N x 3, 0..1)
Roles are component indices into `comps`. Rules use relations inside the head only (mirrored pairs, openings of the
skin, distance to the eye rim, flatness, colour against the skin), with lengths in units of the head height.
On the purple head every one of the 59 components gets the role it was given by hand.
"""
import numpy as np


def vertex_colours(obj, n=None):
    """Texture colour per vertex (first image texture of the object's materials) and one UV per vertex."""
    me = obj.data
    img = next(nd.image for m in me.materials if m and m.use_nodes for nd in m.node_tree.nodes
               if nd.type == 'TEX_IMAGE' and nd.image and nd.image.has_data)
    W_, H_ = img.size
    A = np.empty(W_ * H_ * 4, np.float32); img.pixels.foreach_get(A); A = A.reshape(H_, W_, 4)[..., :3]
    n = n or len(me.vertices)
    uvd = me.uv_layers.active.data
    vcol = np.zeros((n, 3)); vn = np.zeros(n); vuv = np.zeros((n, 2))
    for p in me.polygons:
        for li, vi in zip(p.loop_indices, p.vertices):
            if vi >= n: continue
            u, v = uvd[li].uv
            vcol[vi] += A[int((v % 1) * (H_ - 1)), int((u % 1) * (W_ - 1))]; vn[vi] += 1; vuv[vi] = (u, v)
    return vcol / np.maximum(vn, 1)[:, None], vuv, A


def locate(P, comps, bounds, vcol, known=None, skip=()):
    """skip: component ids added by the build (decals, the cut iris layer), left out of every role."""
    Pf = np.asarray(P, float)
    C = []
    for i, c in enumerate(comps):
        if i in skip:
            continue
        q = Pf[c]
        C.append(dict(i=i, n=len(c), ctr=q.mean(0), lo=q.min(0), hi=q.max(0), col=vcol[c].mean(0)))
    for c in C:
        c['holes'] = sum(1 for lv in bounds[c['i']] if len(lv) >= 12)
    skin = max(C, key=lambda c: (c['holes'] >= 3, c['n']))           # the face skin: eye and mouth openings
    size = float(skin['hi'][2] - skin['lo'][2])                      # head height, the unit for every threshold
    mid_x = float((skin['lo'][0] + skin['hi'][0]) / 2)
    rest_big = [c for c in C if c is not skin and c['n'] > 0.3 * skin['n']]
    # skull (added by the build): a large piece reaching the top of the head, behind the face
    skull = max([c for c in rest_big if c['hi'][2] > skin['hi'][2] - 0.1 * (skin['hi'][2] - skin['lo'][2]) and c['ctr'][1] > skin['ctr'][1]],
                key=lambda c: c['n'], default=None)
    # neck sleeve (added by the build): a large piece below the face, behind it
    neck = [c['i'] for c in rest_big if c is not skull and abs(c['ctr'][0] - (skin['lo'][0] + skin['hi'][0]) / 2) < 0.1 * (skin['hi'][2] - skin['lo'][2])
            and c['lo'][2] < skin['lo'][2] and c['ctr'][1] > skin['ctr'][1]]
    roles = {'skin': skin['i'], 'skull': skull['i'] if skull else None, 'neck': neck}
    skin_tone = skin['col']

    # ---- eye openings: the two mirrored holes of the skin in its upper front half
    loops = []
    for lv in bounds[skin['i']]:
        q = Pf[lv]
        loops.append(dict(n=len(lv), ctr=q.mean(0), lo=q.min(0), hi=q.max(0), vs=lv))
    cand = [l for l in loops if l['n'] >= 12 and l['ctr'][2] > skin['ctr'][2] - 0.05 * size and l['ctr'][1] < skin['ctr'][1] + 0.05 * size]
    best, pair = 1e9, None
    for a in cand:
        for b in cand:
            if a is b or a['ctr'][0] >= b['ctr'][0]: continue
            d = abs((a['ctr'][0] - mid_x) + (b['ctr'][0] - mid_x)) + abs(a['ctr'][2] - b['ctr'][2]) + abs(a['ctr'][1] - b['ctr'][1])
            if d < best: best, pair = d, (a, b)
    if pair is None:
        raise SystemExit('eye openings not found in the skin')
    rim = {'R': pair[0], 'L': pair[1]}            # R = -X side (character right)
    roles['rim_loop_n'] = {s: r['n'] for s, r in rim.items()}
    roles['rim_vs'] = {s: [int(v) for v in r['vs']] for s, r in rim.items()}

    def side_of(c):
        return 'R' if c['ctr'][0] < mid_x else 'L'
    def in_rim_box(c, s, pad):
        r = rim[s]
        return (r['lo'][0] - pad < c['ctr'][0] < r['hi'][0] + pad) and (r['lo'][2] - pad < c['ctr'][2] < r['hi'][2] + pad)
    def rim_dist(c, s):
        # distance (front view) from the piece centre to the rim polyline
        q = Pf[rim[s]['vs']][:, [0, 2]]; a, b = q, np.roll(q, -1, axis=0); p = c['ctr'][[0, 2]]
        t = np.clip(((p - a) * (b - a)).sum(1) / np.maximum(((b - a) ** 2).sum(1), 1e-12), 0, 1)
        return float(np.min(np.linalg.norm(a + (b - a) * t[:, None] - p, axis=1)))
    def dark(c):
        return c['col'].mean() < 0.47
    def mirror_pair(pool, key):
        """best L/R pairs from pool, matched by mirrored centroid"""
        out = {}
        R_ = [c for c in pool if side_of(c) == 'R']; L_ = [c for c in pool if side_of(c) == 'L']
        if not R_ or not L_: return None
        best_ = min(((r, l) for r in R_ for l in L_), key=lambda rl: np.linalg.norm(
            np.array([rl[0]['ctr'][0] - mid_x + rl[1]['ctr'][0] - mid_x, rl[0]['ctr'][1] - rl[1]['ctr'][1], rl[0]['ctr'][2] - rl[1]['ctr'][2]])) - 1e-4 * key(rl[0]))
        return {'R': best_[0], 'L': best_[1]}

    others = [c for c in C if c['i'] not in (skin['i'], roles['skull']) and c['i'] not in neck]
    taken = set()
    # sclera: the largest light piece inside each opening, not in front of the rim (the lash strip sits in front)
    def need(pool, what, s):
        if not pool:
            raise SystemExit(f'{what} not found for the {"right" if s == "R" else "left"} eye')
        return pool
    sclera = {s: max(need([c for c in others if side_of(c) == s and in_rim_box(c, s, 0.005 * size) and not dark(c)
                           and c['ctr'][1] > rim[s]['ctr'][1] - 0.005 * size], 'eyeball piece inside the opening', s),
                     key=lambda c: c['n']) for s in rim}
    taken |= {c['i'] for c in sclera.values()}
    # a second copy of the eyeball at the same place (some heads carry both faces of the eye as two pieces)
    sclera_extra = {s: [c['i'] for c in others if c['i'] not in taken and c['n'] == sclera[s]['n']
                        and np.linalg.norm(c['ctr'] - sclera[s]['ctr']) < 0.002 * size] for s in rim}
    taken |= {i for v in sclera_extra.values() for i in v}
    # upper lash: the large dark piece over each opening (absent when the lashes are part of the face skin)
    up = [c for c in others if c['i'] not in taken and dark(c) and c['n'] > 0.3 * sclera['R']['n']]
    lash = {s: max(cs, key=lambda c: c['n']) for s in rim
            for cs in [[c for c in up if side_of(c) == s and in_rim_box(c, s, 0.06 * size) and c['ctr'][2] > sclera[s]['ctr'][2]]] if cs}
    if len(lash) == 1:
        raise SystemExit('upper lash found for one eye only')
    taken |= {c['i'] for c in lash.values()}
    # iris: the largest remaining piece inside the opening, in front of the sclera (absent when the iris is painted
    # on the eyeball)
    iris_main = {s: max(cs, key=lambda c: c['n']) for s in rim
                 for cs in [[c for c in others if c['i'] not in taken and side_of(c) == s and in_rim_box(c, s, 0.0)
                             and c['ctr'][1] < sclera[s]['ctr'][1] + 0.01 * size]] if cs}
    taken |= {c['i'] for c in iris_main.values()}
    # brows: the mirrored pair of wide pieces above the lashes; crease: the thinner pair between lash and brow.
    # No such pieces: the brows are painted on the face skin.
    lid_top = max((lash[s]['ctr'][2] for s in lash), default=max(rim[s]['hi'][2] for s in rim))
    above = [c for c in others if c['i'] not in taken and c['n'] > 20 and c['hi'][0] - c['lo'][0] > 0.08 * size
             and c['ctr'][2] > lid_top]
    brow = {s: max(cs, key=lambda c: c['ctr'][2]) for s in rim for cs in [[c for c in above if side_of(c) == s]] if cs}
    if len(brow) == 1:
        raise SystemExit('brow found for one side only')
    taken |= {c['i'] for c in brow.values()}
    crease_c = [c for c in above if c['i'] not in taken and brow and c['ctr'][2] < brow[side_of(c)]['lo'][2]
                and in_rim_box(c, side_of(c), 0.06 * size)]
    crease = {s: max([c for c in crease_c if side_of(c) == s], key=lambda c: c['n']) for s in rim if any(side_of(c) == s for c in crease_c)}
    taken |= {c['i'] for c in crease.values()}
    # small pieces of each eye. Iris parts and liner strokes are flat (thin in depth); lash pieces stick out of the surface.
    # flat + dark + on the upper rim -> liner; flat + inside the iris disk -> iris part; otherwise on the rim -> lower lash
    iris = {s: [iris_main[s]['i']] if s in iris_main else [] for s in rim}; liner = {'R': [], 'L': []}; lower = []
    disk = {}
    for s_ in rim:
        m_ = iris_main.get(s_)
        if m_ is None:                                 # painted iris: a disk of a third of the eyeball width
            c_ = sclera[s_]; disk[s_] = ((c_['lo'] + c_['hi']) / 2, np.maximum((c_['hi'] - c_['lo']) / 6, 1e-6))
        else:
            disk[s_] = ((m_['lo'] + m_['hi']) / 2, np.maximum((m_['hi'] - m_['lo']) / 2, 1e-6))
    for c in others:
        if c['i'] in taken or c['n'] > 0.8 * sclera['R']['n']: continue
        s = side_of(c)
        if not in_rim_box(c, s, 0.01 * size): continue
        span = c['hi'] - c['lo']; flat = span[1] < 0.4 * max(span[0], span[2])
        cc, rr = disk[s]; r2 = ((c['ctr'][0] - cc[0]) / rr[0]) ** 2 + ((c['ctr'][2] - cc[2]) / rr[2]) ** 2
        d = rim_dist(c, s)
        if flat and dark(c) and c['ctr'][2] > cc[2] and d < 0.007 * size:
            liner[s].append(c['i'])
        elif flat and r2 < 1.0:
            iris[s].append(c['i'])
        elif d < 0.016 * size:
            lower.append(c['i'])
        else:
            iris[s].append(c['i'])
        taken.add(c['i'])
    # nose: small skin-coloured pieces at the centre line in front of the face, below the eyes
    nose = [c['i'] for c in others if c['i'] not in taken and abs(c['ctr'][0] - mid_x) < 0.02 * size
            and c['ctr'][2] < sclera['R']['ctr'][2] and c['ctr'][1] < skin['ctr'][1]]
    taken |= set(nose)
    # earrings and other side pieces below the eyes, outside the face front
    side = [c['i'] for c in others if c['i'] not in taken and abs(c['ctr'][0] - mid_x) > 0.25 * size and c['ctr'][2] < sclera['R']['ctr'][2]]
    taken |= set(side)
    # a mask-like face (Tripo): the skin has openings at the back or top of the head; a closed head has openings only
    # around the eyes
    open_back = any(len(lv) >= 12 and ((Pf[lv][:, 1].mean() - skin['ctr'][1]) / size > 0.2 or (Pf[lv][:, 2].mean() - skin['lo'][2]) / size > 0.7)
                    for lv in bounds[skin['i']])
    roles['structure'] = dict(lash_pieces=bool(lash), iris_pieces=bool(iris_main), brow_pieces=bool(brow), open_back=bool(open_back))
    roles.update({'sclera': {s: c['i'] for s, c in sclera.items()}, 'sclera_extra': sclera_extra,
                  'iris': iris, 'iris_main': {s: c['i'] for s, c in iris_main.items()},
                  'upper_lash': {s: c['i'] for s, c in lash.items()}, 'lower_lash': sorted(lower), 'liner': liner,
                  'brow': {s: c['i'] for s, c in brow.items()}, 'crease': {s: c['i'] for s, c in crease.items()},
                  'nose': nose, 'ear_side': side, 'unassigned': [c['i'] for c in others if c['i'] not in taken]})

    # ---- eye points: corners and lid midpoints of each opening (world coordinates)
    pts = {}
    for s, r in rim.items():
        vs = r['vs']; q = Pf[vs]; ax = np.abs(q[:, 0] - mid_x)
        inner, outer = vs[int(np.argmin(ax))], vs[int(np.argmax(ax))]
        xm = (ax.min() + ax.max()) / 2; w = ax.max() - ax.min(); idx = np.nonzero(np.abs(ax - xm) < w * 0.2)[0]
        upper_v, lower_v = vs[idx[int(np.argmax(q[idx, 2]))]], vs[idx[int(np.argmin(q[idx, 2]))]]
        for k, v in (('Inner', inner), ('Outer', outer), ('Upper', upper_v), ('Lower', lower_v)):
            pts[f'eye{k}{s}'] = [round(float(x), 5) for x in P[v]]

    # ---- landmarks: mouth line (dark texels on the lower face centre, below the nose), nose tip, chin
    front = [v for v in comps[skin['i']] if Pf[v, 1] < skin['ctr'][1]]
    fP = Pf[front]
    centre = np.abs(fP[:, 0] - mid_x) < 0.08 * size
    nose_v = [v for i in nose for v in comps[i]] + [front[k] for k in np.nonzero(centre)[0]]
    tip = Pf[min(nose_v, key=lambda v: Pf[v, 1])]
    chin = fP[centre][np.argmin(fP[centre][:, 2])]
    eye_z = float(np.mean([sclera[s]['ctr'][2] for s in rim]))
    lum = vcol[front].mean(1); skin_lum = float(np.median(lum))
    m_sel = centre & (fP[:, 2] < tip[2] - 0.02 * size) & (fP[:, 2] > chin[2] + 0.05 * size) & (lum < 0.6 * skin_lum)
    mouth = fP[m_sel]
    if known and all(k in known for k in ('mouthR', 'mouthL', 'mouth', 'noseTip', 'chin')):
        # landmarks found earlier on the untouched texture (the build softens the drawn mouth line)
        mouth = np.array([known['mouthR'], known['mouth'], known['mouthL']], float)
        tip, chin = np.array(known['noseTip'], float), np.array(known['chin'], float)
    if len(mouth) < 3:
        raise SystemExit('mouth line not found on the face texture')
    # keep the largest cluster in height (the painted line), drop stray dark texels
    zc = np.median(mouth[:, 2]); mouth = mouth[np.abs(mouth[:, 2] - zc) < 0.03 * size]
    landmarks = {f'eye{k}{s}': pts[f'eye{k}{s}'] for s in rim for k in ('Inner', 'Outer')}
    landmarks.update({'mouthR': [float(x) for x in mouth[np.argmin(mouth[:, 0])]], 'mouthL': [float(x) for x in mouth[np.argmax(mouth[:, 0])]],
                      'mouth': [float(x) for x in mouth.mean(0)], 'noseTip': [float(x) for x in tip], 'chin': [float(x) for x in chin]})
    return dict(roles=roles, landmarks=landmarks, eye_points=pts, size=size, mid_x=mid_x)


def fit_frame(lm, ref):
    """Uniform scale and offset carrying the reference landmarks onto these (x = s * x_ref + t, least squares),
    and the largest landmark error after the fit."""
    keys = [k for k in ref if k in lm]
    A = np.array([ref[k] for k in keys], float); B = np.array([lm[k] for k in keys], float)
    Am, Bm = A.mean(0), B.mean(0)
    s = float(((A - Am) * (B - Bm)).sum() / ((A - Am) ** 2).sum()); t = Bm - s * Am
    err = np.linalg.norm(s * A + t - B, axis=1)
    return {'s': round(s, 5), 't': [round(float(x), 5) for x in t]}, {k: round(float(e), 4) for k, e in zip(keys, err)}


def kit_parts(kit, mesh):
    """Components and boundary loops exactly as the kit's expression helper lists them."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('kit_expression_mask', str(kit) + '/scripts/expression-mask.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    comps = m.components(mesh)
    return comps, [m.boundaries(mesh, c) for c in comps]
