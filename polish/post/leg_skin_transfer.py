# Leg skin from the base character onto an outfit (11-18, user: on a raised or kneeling leg only the purple model's knee
# looks right; the outfits' knees read as smooth tubes or flat stumps).
# The outfits' legs have about the same shape and weights as the base, but their skin texture is a flat tone (Tripo
# output, and the summer legs were repainted with their average tone), so the painted kneecap, shin and thigh shading of
# the base is missing and a bent knee has no form. This copies the base's leg skin texels onto the outfit's bare leg skin.
# Correspondence is by leg coordinates, not nearest vertex (the meshes differ by 1.5-2 cm): t along hip->knee (0..1) and
# knee->ankle (1..2), and the angle around that bone. Skeletons of all outfits are identical, so the frames agree.
# Only texels that are skin in the outfit's own texture are replaced (socks, shorts, lace stay); the top of the thigh
# fades from the outfit's tone so the edge under a skirt or shorts does not show.
# usage: python3 leg_skin_transfer.py BASE.vrm IN.vrm OUT.vrm [material=Material_lower_body]
import io, json, struct, sys
import numpy as np
from PIL import Image

base_p, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
MAT = sys.argv[4] if len(sys.argv) > 4 else 'Material_lower_body'
NT, NA = 480, 288          # grid over t in [0, 2] and the angle around the bone
import os
ANKLE = float(os.environ.get('LEG_ANKLE', 1.80))            # fades back to the outfit's own skin above this (the base wears ankle socks)
ANKLE_FADE = float(os.environ.get('LEG_ANKLE_FADE', 0.08))
T_FADE = (0.0, 0.06)       # thigh top: outfit tone -> base skin (0.06-0.22 showed a pale band inside raised shorts cuffs)

def load(p):
    b = open(p, 'rb').read()
    n = struct.unpack_from('<I', b, 12)[0]; J = json.loads(b[20:20 + n]); o = 20 + n
    binlen = struct.unpack_from('<I', b, o)[0]; BIN = bytearray(b[o + 8:o + 8 + binlen])
    def acc(i):
        a = J['accessors'][i]; v = J['bufferViews'][a['bufferView']]
        k = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a['componentType']]
        off = v.get('byteOffset', 0) + a.get('byteOffset', 0); st = v.get('byteStride', 0); isz = np.dtype(dt).itemsize
        if st and st != k * isz:
            raw = np.frombuffer(bytes(BIN[off:off + a['count'] * st]), np.uint8).reshape(a['count'], st)[:, :k * isz]
            return raw.copy().view(dt).reshape(a['count'], k)
        return np.frombuffer(bytes(BIN[off:off + a['count'] * k * isz]), dt).reshape(a['count'], k)
    mat_idx = next(i for i, m in enumerate(J['materials']) if m.get('name') == MAT)
    hb = J['extensions']['VRMC_vrm']['humanoid']['humanBones']; human_of = {v['node']: k for k, v in hb.items()}
    # the body primitive with this material: the one with the most leg-weighted vertices (the forest skirt shares it)
    prim = node = None; best = 0; legn = {hb[s + b_]['node'] for s in ('left', 'right') for b_ in ('UpperLeg', 'LowerLeg')}
    for nd in J['nodes']:
        if 'mesh' not in nd or 'skin' not in nd: continue
        jo = J['skins'][nd['skin']]['joints']
        for pr in J['meshes'][nd['mesh']]['primitives']:
            if pr.get('material') != mat_idx: continue
            jn = acc(pr['attributes']['JOINTS_0']).astype(int); wt = acc(pr['attributes']['WEIGHTS_0'])
            k = sum(jo[jn[i, np.argmax(wt[i])]] in legn for i in range(len(jn)))
            if k > best: best, prim, node = k, pr, nd
    skin = J['skins'][node['skin']]; joints = skin['joints']
    IBM = acc(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
    jp = lambda name: np.linalg.inv(IBM[joints.index(hb[name]['node'])])[:3, 3]
    M = dict(J=J, BIN=BIN, P=acc(prim['attributes']['POSITION']).astype(float), UV=acc(prim['attributes']['TEXCOORD_0']).astype(float),
             IDX=acc(prim['indices']).reshape(-1, 3).astype(int))
    JN = acc(prim['attributes']['JOINTS_0']).astype(int); WT = acc(prim['attributes']['WEIGHTS_0']).astype(float)
    M['dom'] = np.array([human_of.get(joints[JN[i, np.argmax(WT[i])]], '') for i in range(len(M['P']))])
    M['legs'] = {s: (jp(s + 'UpperLeg'), jp(s + 'LowerLeg'), jp(s + 'Foot')) for s in ('left', 'right')}
    tex_i = J['materials'][mat_idx]['pbrMetallicRoughness']['baseColorTexture']['index']
    M['img_i'] = J['textures'][tex_i]['source']; bv = J['bufferViews'][J['images'][M['img_i']]['bufferView']]
    M['im'] = np.asarray(Image.open(io.BytesIO(bytes(BIN[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]))).convert('RGB')).astype(float) / 255
    return M

def frame(a, b):
    ax = b - a; L = np.linalg.norm(ax); ax = ax / L
    e1 = np.array([0, 0, 1.0]) - ax * ax[2]; e1 /= np.linalg.norm(e1); e2 = np.cross(ax, e1)
    return a, ax, L, e1, e2

def legcoord(M, side, X):
    """t (0..2) and angle for 3D points X on one leg; also the perpendicular distance to the chosen segment"""
    hip, knee, foot = M['legs'][side]
    out_t = np.full(len(X), np.nan); out_a = np.zeros(len(X)); best = np.full(len(X), np.inf)
    for k, (a, b) in enumerate(((hip, knee), (knee, foot))):
        o, ax, L, e1, e2 = frame(a, b)
        d = X - o; s = d @ ax; tt = np.clip(s / L, 0, 1); r = d - np.outer(tt * L, ax); dist = np.linalg.norm(r, axis=1)
        pen = dist + np.where((s < 0) | (s > L), 0.05, 0)        # prefer the segment the point lies along
        m = pen < best; best[m] = pen[m]; out_t[m] = (k + tt)[m]; out_a[m] = np.arctan2(r @ e2, r @ e1)[m]
    return out_t, out_a

def raster(M, faces, cb):
    """call cb(face, ys, xs, bary) for the texels of each face (grown 1.5 px over seams)"""
    W_, H_ = M['im'].shape[1], M['im'].shape[0]
    for f in faces:
        uv = M['UV'][f] * [W_, H_]; c = uv.mean(0); uv = c + (uv - c) + np.sign(uv - c) * 1.5
        x0, y0 = np.floor(uv.min(0)).astype(int); x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W_ - 1), min(y1, H_ - 1)
        if x1 < x0 or y1 < y0: continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax_, ay_), (bx, by), (cx, cy) = uv
        den = (by - cy) * (ax_ - cx) + (cx - bx) * (ay_ - cy)
        if abs(den) < 1e-9: continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den; l2 = ((cy - ay_) * (xs - cx) + (ax_ - cx) * (ys - cy)) / den
        l3 = 1 - l1 - l2; ins = (l1 >= -0.03) & (l2 >= -0.03) & (l3 >= -0.03)
        if not ins.any(): continue
        cb(f, (ys[ins] - 0.5).astype(int), (xs[ins] - 0.5).astype(int), np.c_[l1[ins], l2[ins], l3[ins]])

def skin_test(c): return ((c[:, 0] - c[:, 2]) > 0.12) & (c.mean(1) > 0.5)

def leg_faces(M, side):
    ok = np.isin(M['dom'], [side + 'UpperLeg', side + 'LowerLeg'])
    return M['IDX'][ok[M['IDX']].all(1)]

np.seterr(all='ignore')   # numpy on macOS Accelerate reports spurious matmul warnings
B = load(base_p); T = load(src)
painted = 0; out = T['im'].copy()
for side in ('left', 'right'):
    # 1. base leg skin into a (t, angle) grid
    acc_c = np.zeros((NT, NA, 3)); acc_n = np.zeros((NT, NA))
    def put(f, ys, xs, bary):
        col = B['im'][ys, xs]; m = skin_test(col)
        if not m.any(): return
        X = bary[m] @ B['P'][f]; t, a = legcoord(B, side, X)
        ti = np.clip((t / 2 * NT).astype(int), 0, NT - 1); ai = ((a + np.pi) / (2 * np.pi) * NA).astype(int) % NA
        np.add.at(acc_c, (ti, ai), col[m]); np.add.at(acc_n, (ti, ai), 1)
    raster(B, leg_faces(B, side), put)
    G = np.where(acc_n[..., None] > 0, acc_c / np.maximum(acc_n, 1)[..., None], np.nan)
    filled0 = np.isfinite(G[..., 0]).mean()
    for _ in range(40):                                   # fill holes from neighbours (angle wraps)
        hole = ~np.isfinite(G[..., 0])
        if not hole.any(): break
        nb = [np.roll(G, 1, 1), np.roll(G, -1, 1), np.roll(G, 1, 0), np.roll(G, -1, 0)]
        st = np.stack(nb); cnt = np.isfinite(st[..., 0]).sum(0)
        mean = np.nansum(np.nan_to_num(st, nan=0.0), 0) / np.maximum(cnt, 1)[..., None]
        G = np.where((hole & (cnt > 0))[..., None], mean, G)
    G = np.nan_to_num(G, nan=0.8)
    print(side, 'base grid filled %.0f%% before hole fill' % (filled0 * 100))
    # 2. outfit bare leg skin from the grid
    def get(f, ys, xs, bary):
        global painted
        col = T['im'][ys, xs]; m = skin_test(col)
        if not m.any(): return
        X = bary[m] @ T['P'][f]; t, a = legcoord(T, side, X)
        tf = t / 2 * NT - 0.5; af = (a + np.pi) / (2 * np.pi) * NA - 0.5
        t0 = np.clip(np.floor(tf).astype(int), 0, NT - 2); a0 = np.floor(af).astype(int)
        wt = np.clip(tf - t0, 0, 1)[:, None]; wa = (af - a0)[:, None]; a0 %= NA; a1 = (a0 + 1) % NA
        c = (G[t0, a0] * (1 - wt) * (1 - wa) + G[t0 + 1, a0] * wt * (1 - wa) + G[t0, a1] * (1 - wt) * wa + G[t0 + 1, a1] * wt * wa)
        w = (np.clip((t - T_FADE[0]) / (T_FADE[1] - T_FADE[0]), 0, 1) * np.clip((ANKLE - t) / ANKLE_FADE, 0, 1))[:, None]   # 11-18: the base's ankle socks are not skin
        yy, xx = ys[m], xs[m]
        out[yy, xx] = T['im'][yy, xx] * (1 - w) + c * w; painted += m.sum()
    raster(T, leg_faces(T, side), get)
print('painted px', int(painted))

J, BIN = T['J'], T['BIN']; img_i = T['img_i']
buf = io.BytesIO(); Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, 'JPEG', quality=93); data = buf.getvalue()
off = len(BIN); off += (4 - off % 4) % 4; BIN += b'\0' * (off - len(BIN)); BIN += data
J['bufferViews'].append(dict(buffer=0, byteOffset=off, byteLength=len(data))); J['images'][img_i]['bufferView'] = len(J['bufferViews']) - 1
J['images'][img_i]['mimeType'] = 'image/jpeg'
BIN += b'\0' * ((4 - len(BIN) % 4) % 4); J['buffers'][0]['byteLength'] = len(BIN)
js = json.dumps(J, ensure_ascii=False, separators=(',', ':')).encode(); js += b' ' * ((4 - len(js) % 4) % 4)
open(dst, 'wb').write(b'glTF' + struct.pack('<II', 2, 12 + 8 + len(js) + 8 + len(BIN)) + struct.pack('<I', len(js)) + b'JSON' + js + struct.pack('<I', len(BIN)) + b'BIN\0' + BIN)
print('LEGSKIN_OK', dst)
