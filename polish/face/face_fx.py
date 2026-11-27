# Anime face effects (blush, >< eyes, star eyes, cat mouth, sweat drop) as decals. Each effect was drawn by Codex on
# a front render of the face and cut out against that render (fx/<name>.png, fx/fx.json: crop box and the render
# camera). build_character adds, per effect, a grid of quads projected from that camera onto the head (or hair)
# just in front of the surface, UV-mapped to the cut-out, with its own blended material (FX_<name>) and the head's
# skinning; materials can only be added at that stage. expr_build makes bound decals follow every shape key of the
# surface under them (sync_fx). vrm_finalize hides them (base colour alpha 0) and adds one expression per effect
# that fades the alpha in.
import json, math
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

PREFIX = 'FX_'


def _camera(info):
    c = info['image']['camera']; W, H = info['image']['size']
    pos = np.array(c['pos'], float); tgt = np.array(c['target'], float)       # three.js coordinates (y up, +z front)
    t = math.tan(math.radians(c['fov']) / 2); a = c['aspect']; x0, y0, x1, y1 = c['crop']

    def ray(px, py):                                                        # crop pixel -> Blender ray
        u = x0 + (px / W) * (x1 - x0); v = y0 + (py / H) * (y1 - y0)
        d = np.array([(2 * u - 1) * t * a, (1 - 2 * v) * t, -1.0])          # camera looks down -z (target straight ahead)
        d /= np.linalg.norm(d)
        o_b = Vector((pos[0], -pos[2], pos[1])); d_b = Vector((d[0], -d[2], d[1]))
        return o_b, d_b
    return ray


def add_fx(head, hair, cfg):
    """cfg: dir, effects {name: {grid, offset, bind, hair}}; returns per-effect counts."""
    info = json.load(open(cfg['dir'] + '/fx.json'))
    ray = _camera(info)
    me = head.data; M = head.matrix_world; Mi = M.inverted()
    bmh = bmesh.new(); bmh.from_mesh(me); bmh.transform(M)
    skipm = {i for i, m in enumerate(me.materials) if m and (m.name.startswith(PREFIX) or m.name == 'BrowOverlay')}
    bmesh.ops.delete(bmh, geom=[f for f in bmh.faces if f.material_index in skipm], context='FACES')
    tree_h = BVHTree.FromBMesh(bmh); bmh.free()
    tree_hair = None
    if hair is not None:
        bmr = bmesh.new(); bmr.from_mesh(hair.data); bmr.transform(hair.matrix_world); tree_hair = BVHTree.FromBMesh(bmr); bmr.free()
    Pw = np.array([M @ v.co for v in me.vertices])
    from mathutils.kdtree import KDTree
    kd = KDTree(len(Pw))
    for i, p in enumerate(Pw): kd.insert(Vector(p), i)
    kd.balance()
    dvert_src = [[(g.group, g.weight) for g in v.groups] for v in me.vertices]
    # faces of the plain head (no decals/overlay) as vertex-index polygons, for projecting onto a deformed state
    polys = [tuple(p.vertices) for p in me.polygons if p.material_index not in skipm]
    out = {}
    for name, ec in cfg['effects'].items():
        x0, y0, x1, y1 = info[name]['bbox']; W, H = info['image']['size']
        n = ec.get('grid', 24); nx = max(4, int(n * (x1 - x0) / max(x1 - x0, y1 - y0))); ny = max(4, int(n * (y1 - y0) / max(x1 - x0, y1 - y0)))
        # bind_delta: a per-vertex displacement (.npy, e.g. the blink) of the head as it is at this point of the build.
        # The decal is projected onto the *displaced* surface and each vertex is then placed where that surface point
        # sits at rest, so a decal that must ride on the closed eyelid (><) is drawn on the lid, not on the eyeball.
        Dd = None
        if ec.get('bind_delta'):
            Dd = np.load(ec['bind_delta']).astype(np.float64)
            if len(Dd) != len(Pw):
                raise RuntimeError(f'{name}: bind_delta has {len(Dd)} vertices, head has {len(Pw)} at this point of the build')
            Dd = Dd @ np.array(M.to_3x3()).T                                   # local displacement -> world
            tree_d = BVHTree.FromPolygons([Vector(p) for p in (Pw + Dd)], polys)
        grid = {}
        wp = (cfg.get('warp') or {}).get(name)        # another face: carry the decal by this face's landmarks
        for j in range(ny + 1):
            for i in range(nx + 1):
                px = x0 + (x1 - x0) * i / nx; py = y0 + (y1 - y0) * j / ny
                o, d = ray(px, py)
                if wp:
                    # the drawn spot on a front plane, moved in the front view (x' = sx x + tx, z' = sz z + tz),
                    # then cast straight back onto this face
                    tpl = (wp['plane_y'] - o.y) / d.y; x_, z_ = o.x + d.x * tpl, o.z + d.z * tpl
                    o = Vector((wp['sx'] * x_ + wp['tx'], wp['plane_y'] - 0.5, wp['sz'] * z_ + wp['tz'])); d = Vector((0.0, 1.0, 0.0))
                if Dd is not None:
                    hit = tree_d.ray_cast(o, d, 2.0)
                    if hit[0] is None:
                        continue
                    a, b, c = polys[hit[2]][:3]
                    if len(polys[hit[2]]) > 3:                                  # quad: pick the triangle under the hit
                        q = polys[hit[2]]; best = None
                        for (a_, b_, c_) in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
                            w_ = _bary(np.array(hit[0]), Pw[a_] + Dd[a_], Pw[b_] + Dd[b_], Pw[c_] + Dd[c_])
                            s_ = float(np.clip(w_, 0, 1).sum() - 1) if (w_ >= -1e-3).all() else 9
                            if best is None or abs(s_) < best[0]: best = (abs(s_), (a_, b_, c_))
                        a, b, c = best[1]
                    w = _bary(np.array(hit[0]), Pw[a] + Dd[a], Pw[b] + Dd[b], Pw[c] + Dd[c])
                    w = np.clip(w, 0, None); w = w / max(w.sum(), 1e-9)
                    disp = Dd[a] * w[0] + Dd[b] * w[1] + Dd[c] * w[2]
                    p = (hit[0] - d * ec.get('offset', 0.0004)) - Vector(disp)
                    grid[(i, j)] = (p, ((px - x0) / (x1 - x0), 1 - (py - y0) / (y1 - y0)), o, d, hit[3])
                    continue
                hit = tree_h.ray_cast(o, d, 2.0)
                if ec.get('hair') and tree_hair is not None:
                    hh = tree_hair.ray_cast(o, d, 2.0)
                    if hh[0] is not None and (hit[0] is None or hh[3] < hit[3]): hit = hh
                if hit[0] is None:
                    continue
                p = hit[0] - d * ec.get('offset', 0.0004)
                grid[(i, j)] = (p, ((px - x0) / (x1 - x0), 1 - (py - y0) / (y1 - y0)), o, d, hit[3])
        if ec.get('flat') and grid:                          # a flat card at the median depth (hair strands are uneven)
            dm = float(np.median([g[4] for g in grid.values()])) - ec.get('offset', 0.0004)
            grid = {k: (g[2] + g[3] * dm, g[1], g[2], g[3], g[4]) for k, g in grid.items()}
        img = None
        import bpy
        img = bpy.data.images.load(cfg['dir'] + f'/{name}.png'); img.pack()
        mat = bpy.data.materials.new(PREFIX + name); mat.use_nodes = True
        if hasattr(mat, 'blend_method'): mat.blend_method = 'BLEND'
        nt = mat.node_tree; bsdf = next(nd for nd in nt.nodes if nd.type == 'BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value = (1, 1, 1, 1); bsdf.inputs['Emission Color'].default_value = (0, 0, 0, 1)
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color']); nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        me.materials.append(mat); slot = len(me.materials) - 1
        bm = bmesh.new(); bm.from_mesh(me)
        uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new(); dfl = bm.verts.layers.deform.verify()
        vmap = {}
        for key, (p, uv, *_r) in grid.items():
            v = bm.verts.new(Mi @ p); vmap[key] = (v, uv)
            _, src, _ = kd.find(p)
            for g, w in dvert_src[src]: v[dfl][g] = w
        nf = 0
        for j in range(ny):
            for i in range(nx):
                ks = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                if not all(k in vmap for k in ks): continue
                f = bm.faces.new([vmap[k][0] for k in ks]); f.material_index = slot; f.smooth = True; nf += 1
                for loop, k in zip(f.loops, ks): loop[uvl].uv = vmap[k][1]
        bm.normal_update()
        for f in bm.faces:                                                 # face the render camera
            if f.material_index == slot and (M.to_3x3() @ f.normal).y > 0: f.normal_flip()
        bm.to_mesh(me); bm.free(); me.update()
        out[name] = dict(verts=len(vmap), faces=nf)
    return out


def sync_fx(head, cfg):
    """Bound decals: every shape key, each decal vertex moves with the surface point under it (barycentric)."""
    me = head.data; kb = me.shape_keys.key_blocks
    B = np.empty(len(me.vertices) * 3, np.float32); kb['Basis'].data.foreach_get('co', B); B = B.reshape(-1, 3)
    mats = [m.name if m else '' for m in me.materials]
    fxv = {}; surf_tris = []
    me.calc_loop_triangles()
    skip = {i for i, n in enumerate(mats) if n.startswith(PREFIX) or n == 'BrowOverlay'}
    for p in me.polygons:
        n = mats[p.material_index]
        if n.startswith(PREFIX):
            fxv.setdefault(n[len(PREFIX):], set()).update(p.vertices)
    tris = [tuple(lt.vertices) for lt in me.loop_triangles if lt.material_index not in skip]
    tree = BVHTree.FromPolygons([Vector(p) for p in B], tris)
    K = np.empty_like(B); keys = [k for k in kb if k.name != 'Basis']; res = {}
    binds = {}
    for name, vs in fxv.items():
        if not cfg['effects'].get(name, {}).get('bind'):
            continue
        for v in vs:
            loc, nrm, ti, dist = tree.find_nearest(Vector(B[v]))
            if ti is None: continue
            a, b, c = tris[ti]
            w = _bary(np.array(loc), B[a], B[b], B[c])
            binds[v] = ((a, b, c), w)
        res[name] = len(vs)
    if not binds:
        return res
    vv = np.array(list(binds)); tri = np.array([binds[v][0] for v in vv]); wt = np.array([binds[v][1] for v in vv])
    for k in keys:
        k.data.foreach_get('co', K.ravel()); D = K - B
        K[vv] = B[vv] + (D[tri[:, 0]] * wt[:, :1] + D[tri[:, 1]] * wt[:, 1:2] + D[tri[:, 2]] * wt[:, 2:3])
        k.data.foreach_set('co', K.ravel())
    me.update()
    res['keys'] = len(keys)
    return res


def _bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-18: return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / den; w = (d00 * d21 - d01 * d20) / den
    return np.array([1 - v - w, v, w])
