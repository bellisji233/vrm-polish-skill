"""Iris painted on the eyeball -> its own layer (new heads without iris pieces).

Some Tripo heads come with the iris, pupil and highlights modelled as pieces in front of the white (the purple head);
others only paint them on the eyeball (人物2). Sliding the whole eyeball for the gaze moves the white with it (user,
11-20). This turns a painted iris into the piece layout, so the gaze path of piece heads applies:

1. every texel of the front eyeball is placed on the eyeball surface (the eyeball's UVs are scattered over many small
   islands, so the iris is found in 3D, seen from the front, not in texture space);
2. the iris is the dark disc in the middle of the white: centre from the dark texels near the middle, radius from their
   width on the row through the centre (above it the painted lid shadow would widen it);
3. a disc of quads just in front of the eyeball, with its own texture (the painted iris, alpha falling off at its rim),
   material EyeIris, skinned like the eyeball;
4. under the disc the white is repainted on the head texture, each texel blended between the white left and right of
   the disc on the same height, so the painted shading of the white (darker under the lid) carries across.

expr_build finds the layer by its material and slides it over the white, which stays.
add_iris_layer(head, cfg) with cfg: eyes {R: [vertex ids of the eyeball and its copies], L: [...]}, out_dir
"""
import json
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

MATERIAL = 'EyeIris'                       # one per eye: EyeIris_R, EyeIris_L (the gaze shifts each eye's texture)
LID_MATERIAL = 'EyeLid'
TEX = 256                                  # iris texture per eye
EXT = 1.15                                 # the iris texture spans the iris centre +- EXT iris radii
LTEX = 384                                 # lid layer texture width per eye
# shaded white joined to the lid-free part: not darker than dark x the white's median, saturation at most sat above the
# white's; grown in cells of this size (m)
SHADED_WHITE = dict(dark=0.62, sat=0.12, cell=0.00025)


def _image(head):
    for m in head.data.materials:
        if m and m.name.startswith('Material_head') and m.use_nodes:
            for nd in m.node_tree.nodes:
                if nd.type == 'TEX_IMAGE' and nd.image and nd.image.has_data:
                    return m, nd.image
    raise RuntimeError('iris layer: no head texture')


def _texels(me, M, faces, W, H):
    """(x, y) pixel and world point of every texel inside the faces' UV triangles."""
    uv = me.uv_layers.active.data
    px, py, pts = [], [], []
    for p in faces:
        lis = list(p.loop_indices); vs = list(p.vertices)
        for k in range(1, len(lis) - 1):
            tri = (0, k, k + 1)
            U = np.array([tuple(uv[lis[i]].uv) for i in tri]) * [W, H]
            V = np.array([tuple(M @ me.vertices[vs[i]].co) for i in tri])
            x0, y0 = np.floor(U.min(0)).astype(int); x1, y1 = np.ceil(U.max(0)).astype(int)
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = U
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-9:
                continue
            a = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
            b = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
            c = 1 - a - b
            ins = (a >= -0.01) & (b >= -0.01) & (c >= -0.01)
            if not ins.any():
                continue
            w = np.c_[a[ins], b[ins], c[ins]]
            px.append(np.clip(np.floor(gx[ins]).astype(int), 0, W - 1)); py.append(np.clip(np.floor(gy[ins]).astype(int), 0, H - 1))
            pts.append(w @ V)
    if not px:
        return np.zeros(0, int), np.zeros(0, int), np.zeros((0, 3))
    return np.concatenate(px), np.concatenate(py), np.concatenate(pts)


def _in_poly(pts, poly):
    """Points (n, 2) inside the closed polygon (m, 2), even-odd rule."""
    x, y = pts[:, 0][:, None], pts[:, 1][:, None]
    x1, y1 = poly[:, 0][None, :], poly[:, 1][None, :]
    x2, y2 = np.roll(poly[:, 0], -1)[None, :], np.roll(poly[:, 1], -1)[None, :]
    cross = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / np.where(y2 - y1 == 0, 1e-12, y2 - y1) + x1)
    return (cross.sum(1) % 2) == 1


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def add_iris_layer(head, cfg):
    me = head.data; M = head.matrix_world; Mi = M.inverted()
    mat_head, img = _image(head)
    W, H = img.size
    A = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(A); A = A.reshape(H, W, 4)
    atl = {s_: np.zeros((TEX, TEX, 4), np.float32) for s_ in ('R', 'L')}
    report = {}
    discs = {}; lids = {}; rims = {}
    for side_i, side in enumerate(('R', 'L')):
        groups = [list(g) for g in cfg['eyes'][side]]    # the eyeball and its copies; the front-most one is painted
        groups.sort(key=lambda g: min((M @ me.vertices[v].co).y for v in g))
        front = set(groups[0])
        f_front = [p for p in me.polygons if all(v in front for v in p.vertices)]
        if not f_front:
            raise RuntimeError(f'iris layer: eyeball {side} not found on the built head')
        tx, ty, Pw = _texels(me, M, f_front, W, H)
        col = A[ty, tx, :3]; L = col @ np.array([0.299, 0.587, 0.114])
        sat = (col.max(1) - col.min(1)) / np.maximum(col.max(1), 1e-4)
        q = Pw[:, [0, 2]]
        # the skin's eye opening, seen from the front: the eyeball is a painted card (lids and lashes are painted on it
        # too); only the part inside the opening shows
        rim = np.array([tuple((M @ me.vertices[v].co))[0::2] for v in cfg['rims'][side]])
        rc = rim.mean(0); rim = rim[np.argsort(np.arctan2(rim[:, 1] - rc[1], rim[:, 0] - rc[0]))]
        span = float(np.ptp(rim[:, 0]))
        inside = _in_poly(q, rc + (rim - rc) * 0.94)
        if inside.sum() < 200:
            raise RuntimeError(f'iris layer: eye opening {side} does not cover the eyeball')
        Lin = L[inside]
        # the white is the brightest thing in the opening (the iris may be as grey as it, so not by saturation)
        white = inside & (L > 0.87 * np.percentile(Lin, 90))
        # iris columns: most of the opening's height is not white there
        cell = span / 60; xb = np.floor((q[:, 0] - rim[:, 0].min()) / cell).astype(int)
        frac = np.zeros(61)
        for k_ in range(61):
            m_ = inside & (xb == k_)
            if m_.sum() > 5:
                frac[k_] = 1 - white[m_].mean()
        # runs of such columns; the corners (shadowed, touching the ends of the opening) are not the iris: the longest
        # run with white on both sides is
        occ = [k_ for k_ in range(61) if (inside & (xb == k_)).sum() > 5]
        runs, k_ = [], occ[0]
        while k_ <= occ[-1]:
            if frac[k_] > 0.5:
                k0 = k_
                while k_ + 1 <= occ[-1] and frac[k_ + 1] > 0.5: k_ += 1
                runs.append((k0, k_))
            k_ += 1
        inner = [rn for rn in runs if rn[0] > occ[0] and rn[1] < occ[-1]] or runs
        k0, k1 = max(inner, key=lambda rn: rn[1] - rn[0])
        x1 = rim[:, 0].min() + k0 * cell; x2 = rim[:, 0].min() + (k1 + 1) * cell
        r = 0.5 * (x2 - x1); cx = 0.5 * (x1 + x2)
        # centre height: the iris rows' widths follow a circle of that radius (rows touching the lids are left out)
        zs_, ws_ = [], []
        zb = np.floor((q[:, 1] - q[inside, 1].min()) / cell).astype(int)
        for k_ in range(int(zb[inside].max()) + 1):
            m_ = inside & (zb == k_) & (np.abs(q[:, 0] - cx) < 1.3 * r)
            if m_.sum() < 8:
                continue
            nw = m_ & ~white
            if nw.sum() < 4:
                continue
            xs = q[nw, 0]; w_ = float(np.percentile(xs, 95) - np.percentile(xs, 5))
            if w_ < 1.9 * r:                                   # a full-width row is the opening edge or the centre
                zs_.append(float(q[m_, 1].mean())); ws_.append(w_)
        zs_, ws_ = np.array(zs_), np.array(ws_)
        cands = np.linspace(q[inside, 1].min() - r, q[inside, 1].max() + r, 200)
        if len(zs_) >= 3:
            err = [np.sum(((ws_ / 2) ** 2 + (zs_ - cz_) ** 2 - r * r) ** 2) for cz_ in cands]
            cz = float(cands[int(np.argmin(err))])
        else:
            cz = float(q[inside & ~white, 1].mean())
        # the pupil is concentric with the iris and small enough to show whole: its centre, when it is clearly darker
        # than the rest of the iris, places the iris better than the row fit
        band = inside & (np.abs(q[:, 0] - cx) < 0.8 * r)
        if band.sum() > 50:
            Lb = L[band]; pup = band & (L < max(0.45 * float(np.percentile(Lb, 50)), float(np.percentile(Lb, 8))))
            if pup.sum() > 20:
                pc = q[pup].mean(0)
                if np.hypot(pc[0] - cx, 0.0) < 0.5 * r:
                    cx, cz = float(pc[0]), float(pc[1])
        c = np.array([cx, cz])
        report_pupil = bool(band.sum() > 50)
        # the painted eye itself (white and iris; the pupil and the highlight inside the iris too): everything else on
        # the card (painted lids, lash line, lid shadow) belongs to the lids and covers the iris when it moves
        dc = np.linalg.norm(q - c, axis=1)
        # inside the iris circle by place, not colour (the iris rim is as dark as the lash line): only a narrow band
        # along the opening's edge is lash line
        A_, B_ = rim, np.roll(rim, -1, 0); AB_ = B_ - A_
        tt_ = np.clip((((q[:, None, :] - A_) * AB_).sum(-1)) / np.maximum((AB_ * AB_).sum(-1), 1e-12), 0, 1)
        d_edge = np.linalg.norm(q[:, None, :] - (A_ + tt_[..., None] * AB_), axis=-1).min(1)
        eye = _in_poly(q, rim) & (white | ((dc < 1.12 * r) & (d_edge > 0.06 * r)))
        # the white darkens towards the corners and under the upper lid (人物2: 0.55-0.65 against 0.75 in the open part)
        # and is still the white: the iris shows over it when it moves there. As lid it covered the iris with a white
        # film at the corners (user, 11-25). Grown from the white through texels of its hue that are not much darker;
        # the lash line (dark), the waterline and the corner flesh (saturated) stay lid.
        Lw = float(np.percentile(L[white], 50)); sw = float(np.percentile(sat[white], 50))
        cand = inside & (L > SHADED_WHITE['dark'] * Lw) & (sat < sw + SHADED_WHITE['sat'])
        cell = SHADED_WHITE['cell']; g0 = q.min(0)
        gi = np.floor((q - g0) / cell).astype(int); GW, GH = gi.max(0) + 1
        gw = np.zeros((GW, GH), bool); gc = np.zeros((GW, GH), bool)
        gw[gi[white & inside, 0], gi[white & inside, 1]] = True; gc[gi[cand, 0], gi[cand, 1]] = True
        reach = gw.copy(); front_ = list(zip(*np.nonzero(gw)))
        while front_:
            nxt = []
            for a_, b_ in front_:
                for da in (-1, 0, 1):
                    for db in (-1, 0, 1):
                        x_, y_ = a_ + da, b_ + db
                        if 0 <= x_ < GW and 0 <= y_ < GH and gc[x_, y_] and not reach[x_, y_]:
                            reach[x_, y_] = True; nxt.append((x_, y_))
            front_ = nxt
        shaded = cand & reach[gi[:, 0], gi[:, 1]] & ~eye
        eye |= shaded
        # decal texture: the painted iris seen from the front; parts hidden under the lids are mirrored from the
        # visible part (the card has lid skin painted there), alpha falling off at the iris rim
        kd = KDTree(int(inside.sum())); ii = np.nonzero(inside)[0]
        for k_, i in enumerate(ii):
            kd.insert(Vector((q[i, 0], q[i, 1], 0.0)), k_)
        kd.balance()
        Lref = float(np.percentile(L[white], 50)) if white.any() else float(np.percentile(L, 85))
        ext = EXT * r; rimr = 1.03 * r
        poly_in = rim.copy()                                     # inside the opening the disc shows the painting as is
        hidden_px = np.zeros((TEX, TEX), bool)
        kd_all = KDTree(len(q))
        for i_, p_ in enumerate(q):
            kd_all.insert(Vector((p_[0], p_[1], 0.0)), i_)
        kd_all.balance()
        # under the lids (and along the lid line, where the painting is shaded) the iris takes its radial profile: the
        # median colour of the clearly visible iris at that radius (the iris is ring-shaped). Copies turned in from the
        # visible sides left a hard seam and light wedges that showed once the gaze moved the texture (11-25)
        vis_ir = eye & (dc < r) & (d_edge > 0.15 * r) & ~white
        NB = 40; rb = np.clip((dc / r * NB).astype(int), 0, NB - 1)
        prof = np.zeros((NB, 3)); have = np.zeros(NB, bool)
        for b_ in range(NB):
            m_ = vis_ir & (rb == b_)
            if m_.sum() >= 5:
                prof[b_] = np.median(col[m_], 0); have[b_] = True
        if not have.any():
            raise RuntimeError(f'iris layer: no visible iris {side}')
        hv = np.nonzero(have)[0]
        for b_ in range(NB):
            if not have[b_]: prof[b_] = prof[hv[np.argmin(np.abs(hv - b_))]]
        def _prof(rr_):
            t_ = min(max(rr_ / r * NB - 0.5, 0.0), NB - 1.0); b0 = int(t_); b1 = min(NB - 1, b0 + 1); f_ = t_ - b0
            return prof[b0] * (1 - f_) + prof[b1] * f_
        for j in range(TEX):
            zz = c[1] + (2 * (j + 0.5) / TEX - 1) * ext
            for i in range(TEX):
                xx = c[0] + (2 * (i + 0.5) / TEX - 1) * ext
                rr = np.hypot(xx - c[0], zz - c[1])
                if rr > ext:
                    continue
                n0 = kd_all.find(Vector((xx, zz, 0.0)))[1]; n = n0; pr_ = _prof(rr)
                if eye[n0]:
                    # the painting as is, fading into the profile towards the lid line (painted lid shadow there)
                    w_ = float(_smooth((d_edge[n0] - 0.03 * r) / (0.12 * r)))
                    rgb = w_ * col[n0] + (1 - w_) * pr_
                    hidden_px[j, i] = w_ < 0.5
                else:
                    hidden_px[j, i] = True; rgb = pr_
                a = float(_smooth((rimr - rr) / (0.1 * r)))
                if rr > 0.82 * r:
                    a *= float(_smooth((Lref - L[n]) / (0.25 * Lref)) if white[n] else 1.0)
                atl[side][j, i] = (*rgb, a)
        # soften the made-up part: blur it, and blend across its border
        sub = atl[side][..., :3].copy(); bl = sub.copy()
        for _ in range(4):
            bl = (bl + np.roll(bl, 1, 0) + np.roll(bl, -1, 0) + np.roll(bl, 1, 1) + np.roll(bl, -1, 1)) / 5
        band = hidden_px.copy()
        for _ in range(3):
            band = band | np.roll(band, 1, 0) | np.roll(band, -1, 0) | np.roll(band, 1, 1) | np.roll(band, -1, 1)
        wgt = np.where(hidden_px, 1.0, np.where(band, 0.5, 0.0))[..., None]
        atl[side][..., :3] = sub * (1 - wgt) + bl * wgt
        # repaint the white under the disc, inside the opening only (front eyeball and its copies)
        wi = np.nonzero(white & (np.linalg.norm(q - c, axis=1) > 1.08 * r))[0]
        kw = KDTree(len(wi))
        for k_, i in enumerate(wi):
            kw.insert(Vector((q[i, 0], q[i, 1], 0.0)), k_)
        kw.balance()
        R2 = 1.2 * r; nfill = 0
        for g in groups:
            gs = set(g)
            fg = [p for p in me.polygons if all(v in gs for v in p.vertices)]
            gx, gy, gP = _texels(me, M, fg, W, H)
            gq = gP[:, [0, 2]]; rr = np.linalg.norm(gq - c, axis=1)
            sel = (rr < 1.15 * r) & _in_poly(gq, rc + (rim - rc) * 1.06)
            for x_, y_, (qx, qz), r_ in zip(gx[sel], gy[sel], gq[sel], rr[sel]):
                dz = np.clip(qz - c[1], -0.98 * R2, 0.98 * R2); dx = np.sqrt(R2 * R2 - dz * dz)
                cl = col[wi[kw.find(Vector((c[0] - dx, qz, 0.0)))[1]]]
                cr = col[wi[kw.find(Vector((c[0] + dx, qz, 0.0)))[1]]]
                t = np.clip((qx - (c[0] - dx)) / (2 * dx), 0, 1)
                fill = (1 - t) * cl + t * cr
                b = float(_smooth((1.15 * r - r_) / (0.12 * r)))
                A[y_, x_, :3] = (1 - b) * A[y_, x_, :3] + b * fill
                nfill += 1
        # lid layer texture: the card's painting seen from the front, see-through where the painted eye is
        lo_, hi_ = q.min(0), q.max(0); LW = LTEX; LH = max(8, int(LTEX * (hi_[1] - lo_[1]) / (hi_[0] - lo_[0])))
        lid = np.zeros((LH, LW, 4), np.float32)
        for j in range(LH):
            zz = lo_[1] + (j + 0.5) / LH * (hi_[1] - lo_[1])
            for i in range(LW):
                xx = lo_[0] + (i + 0.5) / LW * (hi_[0] - lo_[0])
                n = kd_all.find(Vector((xx, zz, 0.0)))[1]
                lid[j, i] = (*col[n], 0.0 if eye[n] else 1.0)
        for _ in range(2):                                      # soften the cut edge a little
            a_ = lid[..., 3]; lid[..., 3] = (a_ + np.roll(a_, 1, 0) + np.roll(a_, -1, 0) + np.roll(a_, 1, 1) + np.roll(a_, -1, 1)) / 5
        lids[side] = (lid, lo_, hi_); rims[side] = (rim, rc)
        discs[side] = (c, r, f_front)
        report[side] = dict(centre=[round(float(x), 4) for x in c], radius_mm=round(r * 1000, 2), texels=int(len(q)),
                            whiteFilled=nfill, opening=[[round(float(a_), 4), round(float(b_), 4)] for a_, b_ in rim])
    # head texture with the white repainted: saved to a file and the packed copy replaced by that file (a packed image
    # whose pixels were only changed in memory is exported with its old packed bytes)
    img.pixels.foreach_set(A.ravel())
    if cfg.get('out_dir'):
        path = cfg['out_dir'] + '/head-iris-filled.png'
        img.filepath_raw = path; img.file_format = 'PNG'; img.save()
        if img.packed_file:
            img.unpack(method='REMOVE')
        img.filepath = path; img.reload()
    img.pack()
    # each eye's iris texture and material (a plain blended material like the face decals; build_character converts
    # it to MToon afterwards). The texture is clamped at its edge, which is transparent: shifted for the gaze, nothing
    # repeats into the opening.
    import bpy
    slots = {}
    for side in ('R', 'L'):
        tex = bpy.data.images.new('eye-iris-' + side, TEX, TEX, alpha=True); tex.pixels.foreach_set(atl[side].ravel())
        if cfg.get('out_dir'):
            tex.filepath_raw = cfg['out_dir'] + f'/eye-iris-{side}.png'; tex.file_format = 'PNG'; tex.save()
            tex.filepath = tex.filepath_raw; tex.reload()
        tex.pack()
        mat = bpy.data.materials.new(f'{MATERIAL}_{side}'); mat.use_nodes = True
        if hasattr(mat, 'blend_method'): mat.blend_method = 'BLEND'
        nt = mat.node_tree; bsdf = next(nd for nd in nt.nodes if nd.type == 'BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value = (1, 1, 1, 1); bsdf.inputs['Emission Color'].default_value = (0, 0, 0, 1)
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = tex; tn.extension = 'EXTEND'
        nt.links.new(tn.outputs['Color'], bsdf.inputs['Base Color']); nt.links.new(tn.outputs['Alpha'], bsdf.inputs['Alpha'])
        me.materials.append(mat); slots[side] = len(me.materials) - 1
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active; dfl = bm.verts.layers.deform.verify()
    shape_layers = list(bm.verts.layers.shape.values())
    off = cfg.get('offset', 0.0003); trees = {}

    def _grid(side, depth, uv_of, slot):
        """Quads over the skin's eye opening (outside it the skin covers everything), cast onto the front eyeball and
        `depth` in front of it, skinned like the eyeball."""
        c, r, f_front = discs[side]; rim, rc = rims[side]; tree = trees[side]
        fv = sorted({v for p in f_front for v in p.vertices}); groups_ = [(g.group, g.weight) for g in me.vertices[fv[0]].groups]
        poly = rc + (rim - rc) * 1.05
        NX_, NZ_ = 48, 16; x0_, x1_ = poly[:, 0].min(), poly[:, 0].max(); z0_, z1_ = poly[:, 1].min(), poly[:, 1].max()
        grid_ = {}
        for j in range(NZ_ + 1):
            for i in range(NX_ + 1):
                x = x0_ + (x1_ - x0_) * i / NX_; z = z0_ + (z1_ - z0_) * j / NZ_
                hit = tree.ray_cast(Vector((x, -10.0, z)), Vector((0, 1, 0)), 20.0)
                if hit[0] is None:
                    hit = (tree.find_nearest(Vector((x, -0.05, z)))[0],)
                nv = bm.verts.new(Mi @ Vector((x, hit[0].y - depth, z)))
                for L_ in shape_layers: nv[L_] = nv.co
                for g_, w_ in groups_: nv[dfl][g_] = w_
                grid_[(i, j)] = (nv, uv_of(x, z), bool(_in_poly(np.array([[x, z]]), poly)[0]))
        nf = 0
        for j in range(NZ_):
            for i in range(NX_):
                ks = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                if not any(grid_[k][2] for k in ks):
                    continue
                f = bm.faces.new([grid_[k][0] for k in ks]); f.material_index = slot; f.smooth = True; nf += 1
                for loop, k in zip(f.loops, ks):
                    loop[uvl].uv = grid_[k][1]
        for k, (nv, _, _) in grid_.items():                      # unused grid corners
            if not nv.link_faces:
                bm.verts.remove(nv)
        return nf

    # the iris layer: a fixed grid over the whole opening just in front of the eyeball, its texture the iris around
    # the iris centre (u, v = 0.5 + (x, z - centre) / (2 EXT r)). The gaze shifts the texture (expression texture
    # transforms, expr_build / vrm_finalize), so the iris stays on the eyeball at any weight and any mix of looks.
    # Moving the disc itself by shape keys took it along the chord of the curved eyeball: half way out it sank up to
    # 1 mm behind the white (user, 11-25: the iris hidden under a white film at some angles).
    for side_i, side in enumerate(('R', 'L')):
        c, r, f_front = discs[side]
        tris = []
        for p in f_front:
            vs = list(p.vertices)
            for k in range(1, len(vs) - 1):
                tris.append((vs[0], vs[k], vs[k + 1]))
        trees[side] = BVHTree.FromPolygons([M @ v.co for v in me.vertices], tris)
        ext = EXT * r
        report[side]['irisFaces'] = _grid(side, off, lambda x, z, c=c, ext=ext: (0.5 + (x - c[0]) / (2 * ext), 0.5 + (z - c[1]) / (2 * ext)), slots[side])
    # lid layer: a copy of each front eyeball card a little in front of the disc, opaque with a cut-out (drawn before
    # the blended disc, so the disc never shows over it); it keeps the card's painted lids and lash line over the iris
    H_ = max(l_[0].shape[0] for l_ in lids.values())
    lid_atlas = np.zeros((H_, 2 * LTEX, 4), np.float32)
    for side_i, side in enumerate(('R', 'L')):
        l_ = lids[side][0]; lid_atlas[:l_.shape[0], side_i * LTEX:(side_i + 1) * LTEX] = l_
    ltex = bpy.data.images.new('eye-lid', 2 * LTEX, H_, alpha=True); ltex.pixels.foreach_set(lid_atlas.ravel())
    if cfg.get('out_dir'):
        ltex.filepath_raw = cfg['out_dir'] + '/eye-lid.png'; ltex.file_format = 'PNG'; ltex.save()
        ltex.filepath = ltex.filepath_raw; ltex.reload()
    ltex.pack()
    lmat = bpy.data.materials.new(LID_MATERIAL); lmat.use_nodes = True
    try:
        lmat.blend_method = 'CLIP'; lmat.alpha_threshold = 0.5
    except (AttributeError, TypeError):
        pass
    lnt = lmat.node_tree; lb = next(nd for nd in lnt.nodes if nd.type == 'BSDF_PRINCIPLED')
    lb.inputs['Base Color'].default_value = (1, 1, 1, 1); lb.inputs['Emission Color'].default_value = (0, 0, 0, 1)
    ltn = lnt.nodes.new('ShaderNodeTexImage'); ltn.image = ltex
    lnt.links.new(ltn.outputs['Color'], lb.inputs['Base Color']); lnt.links.new(ltn.outputs['Alpha'], lb.inputs['Alpha'])
    me.materials.append(lmat); lslot = len(me.materials) - 1
    loff = cfg.get('lid_offset', 0.0005)
    # lid layer geometry: the same grid, just in front of the iris layer
    for side_i, side in enumerate(('R', 'L')):
        lid, lo_, hi_ = lids[side]; vh = lid.shape[0] / H_
        uv_lid = lambda x, z, lo_=lo_, hi_=hi_, vh=vh, side_i=side_i: ((side_i + (x - lo_[0]) / (hi_[0] - lo_[0])) / 2, vh * (z - lo_[1]) / (hi_[1] - lo_[1]))
        report[side]['lidFaces'] = _grid(side, off + loff, uv_lid, lslot)
    bm.normal_update()
    for f in bm.faces:
        if f.material_index in (*slots.values(), lslot) and (M.to_3x3() @ f.normal).y > 0:
            f.normal_flip()
    bm.to_mesh(me); bm.free(); me.update()
    head['polish_iris_layer'] = json.dumps({k: dict(centre=v['centre'], radius_mm=v['radius_mm'], ext=EXT) for k, v in report.items()})
    return report
