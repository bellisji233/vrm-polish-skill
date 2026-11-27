# Safety shorts painted under a skirt (11-18, user: the skirt flies up in dances and shows bare skin up to the crotch).
# Texture only: the upper-thigh skin faces of the lower-body material are repainted as pale shorts with a scalloped
# lace hem, keeping the original shading. No new geometry, so nothing new can clip.
# usage: python3 safety_shorts.py IN.vrm OUT.vrm [hem=0.26] [material=Material_lower_body] [palette=lavender|cream]
import io, json, math, struct, sys
import numpy as np
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
HEM = float(sys.argv[3]) if len(sys.argv) > 3 else 0.26        # hem position along the thigh (0 hip joint, 1 knee)
MAT = sys.argv[4] if len(sys.argv) > 4 else 'Material_lower_body'
BODY = np.array([0.95, 0.93, 0.97])        # shorts: near white with a lavender cast (the skirt's palette)
LACE = np.array([0.86, 0.80, 0.93])        # hem lace band
LINE = np.array([0.62, 0.52, 0.74])        # stitch line above the lace
PALETTE = sys.argv[5] if len(sys.argv) > 5 else 'lavender'
MIN_LUM = 0.0
if PALETTE == 'cream':                     # 11-18 forest outfit: cream dress, brown leather
    BODY = np.array([0.95, 0.92, 0.85]); LACE = np.array([0.99, 0.97, 0.92]); LINE = np.array([0.58, 0.44, 0.32])
    MIN_LUM = 0.5                          # the brown flap on the thigh is reddish too; skin is lighter

b = open(src, 'rb').read()
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
hb = J['extensions']['VRMC_vrm']['humanoid']['humanBones']
human_of = {v['node']: k for k, v in hb.items()}
# the skinned body node whose mesh has the material (not the spring skirt: its primitives are skirt only)
# 11-18: pick the primitive with the most leg-weighted vertices; the forest skirt shares the material and has more verts
prim = node = None; best = 0; legn = {hb[s + b_]['node'] for s in ('left', 'right') for b_ in ('UpperLeg', 'LowerLeg')}
for ni, nd in enumerate(J['nodes']):
    if 'mesh' not in nd or 'skin' not in nd: continue
    jo = J['skins'][nd['skin']]['joints']
    for p in J['meshes'][nd['mesh']]['primitives']:
        if p.get('material') != mat_idx: continue
        jn = acc(p['attributes']['JOINTS_0']).astype(int); wt = acc(p['attributes']['WEIGHTS_0'])
        k = sum(jo[jn[i, np.argmax(wt[i])]] in legn for i in range(len(jn)))
        if k > best: best, prim, node = k, p, nd
if prim is None: sys.exit('no body primitive with ' + MAT)
skin = J['skins'][node['skin']]; joints = skin['joints']
IBM = acc(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)   # column-major -> row-major
def joint_pos(name):
    ji = joints.index(hb[name]['node']); return np.linalg.inv(IBM[ji])[:3, 3]
P = acc(prim['attributes']['POSITION']).astype(float); UV = acc(prim['attributes']['TEXCOORD_0']).astype(float)
JN = acc(prim['attributes']['JOINTS_0']).astype(int); WT = acc(prim['attributes']['WEIGHTS_0']).astype(float)
IDX = acc(prim['indices']).reshape(-1, 3).astype(int)
dom = np.array([human_of.get(joints[JN[i, np.argmax(WT[i])]], '') for i in range(len(P))])

tex_i = J['materials'][mat_idx]['pbrMetallicRoughness']['baseColorTexture']['index']
img_i = J['textures'][tex_i]['source']; bv = J['bufferViews'][J['images'][img_i]['bufferView']]
im = np.asarray(Image.open(io.BytesIO(bytes(BIN[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]))).convert('RGB')).astype(float) / 255
H_, W_ = im.shape[:2]
def sample(uv): x = np.clip((uv[:, 0] * W_).astype(int), 0, W_ - 1); y = np.clip((uv[:, 1] * H_).astype(int), 0, H_ - 1); return im[y, x]

# thigh frame per side: t along hip -> knee, unit direction around the axis for the scalloped hem
t = np.full(len(P), 9.0); ang = np.zeros((len(P), 2)); side_of = np.full(len(P), '')
for s in ('left', 'right'):
    h0, k0 = joint_pos(s + 'UpperLeg'), joint_pos(s + 'LowerLeg'); ax = k0 - h0; L = np.linalg.norm(ax); ax /= L
    # 11-18: hips-dominated skin counts too (back of the thigh / under the buttock showed skin)
    # and up to the waistline (12 cm above the hip joint): a band of skin under the waist showed when the skirt flew up
    sel = (dom == s + 'UpperLeg') | ((dom == 'hips') & (np.sign(P[:, 0]) == np.sign(h0[0])) & (P[:, 1] < h0[1] + 0.12))
    d = P[sel] - h0; tt = d @ ax / L; r = d - np.outer(d @ ax, ax)
    fwd = np.array([0, 0, 1.0]); e1 = fwd - ax * (fwd @ ax); e1 /= np.linalg.norm(e1); e2 = np.cross(ax, e1)
    rl = np.linalg.norm(r, axis=1) + 1e-9
    t[sel] = tt; ang[sel] = np.c_[r @ e1 / rl, r @ e2 / rl]; side_of[sel] = s
# skin test: colour close to the mid-thigh skin of this texture
mid = (t > 0.45) & (t < 0.8)
ref = np.median(sample(UV[mid]), axis=0)
col = sample(UV)
# skin is clearly redder than blue; the skirt lining is lavender (r ~ b). Colour distance to the mid-thigh failed:
# the skin next to the skirt edge is baked dark (median 0.73/0.46/0.46 against 0.86/0.63/0.59)
skin_like = ((col[:, 0] - col[:, 2]) > 0.12) & (col.mean(1) > MIN_LUM)
leg = t < 9
# the thigh is coarse (about 150 vertices per upper leg): faces that cross the hem line count too, the hem is drawn per pixel
# one skin corner is enough: two left holes of skin inside the shorts where a corner sat in a dark or bluish shadow
tri = IDX[leg[IDX].all(1) & (skin_like[IDX].sum(1) >= 1) & (t[IDX].min(1) < HEM)]
cand = np.zeros(len(P), bool); cand[tri.ravel()] = True
print('ref skin', ref.round(3), 'candidate verts', int(cand.sum()), 'faces', len(tri))

out = im.copy(); lum_ref = ref.mean()
painted = 0
for f in tri:
    uv = UV[f] * [W_, H_]; c = uv.mean(0); uv = c + (uv - c) * 1.0 + np.sign(uv - c) * 1.5   # grow 1.5 px over seams
    x0, y0 = np.floor(uv.min(0)).astype(int); x1, y1 = np.ceil(uv.max(0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W_ - 1), min(y1, H_ - 1)
    if x1 < x0 or y1 < y0: continue
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    (ax_, ay_), (bx, by), (cx, cy) = uv
    den = (by - cy) * (ax_ - cx) + (cx - bx) * (ay_ - cy)
    if abs(den) < 1e-9: continue
    l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den; l2 = ((cy - ay_) * (xs - cx) + (ax_ - cx) * (ys - cy)) / den; l3 = 1 - l1 - l2
    inside = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
    if not inside.any(): continue
    tp = l1 * t[f[0]] + l2 * t[f[1]] + l3 * t[f[2]]
    ca = l1 * ang[f[0], 0] + l2 * ang[f[1], 0] + l3 * ang[f[2], 0]; sa = l1 * ang[f[0], 1] + l2 * ang[f[1], 1] + l3 * ang[f[2], 1]
    th = np.arctan2(sa, ca)
    edge = HEM - 0.012 * (1 - np.abs(np.sin(7 * th)))              # scallops: 14 around the thigh
    region = inside & (tp < edge)
    if not region.any(): continue
    yy, xx = (ys[region] - 0.5).astype(int), (xs[region] - 0.5).astype(int)
    # shading from the original texture: reading the image being painted re-lit the 1.5 px overlaps of neighbouring
    # triangles from already white pixels and drew the triangle edges as bright lines
    shade = np.clip(im[yy, xx].mean(1) / lum_ref, 0.55, 1.15)[:, None]
    tr = tp[region]; e = edge[region]
    color = np.where((e - tr < 0.03)[:, None], LACE, BODY)
    color = np.where(((e - tr > 0.03) & (e - tr < 0.037))[:, None], LINE, color)   # stitch line
    out[yy, xx] = np.clip(color * (0.72 + 0.28 * shade), 0, 1); painted += region.sum()
print('painted px', int(painted))

buf = io.BytesIO(); Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(buf, 'JPEG', quality=93); data = buf.getvalue()
off = len(BIN); off += (4 - off % 4) % 4; BIN += b'\0' * (off - len(BIN)); BIN += data
J['bufferViews'].append(dict(buffer=0, byteOffset=off, byteLength=len(data))); J['images'][img_i]['bufferView'] = len(J['bufferViews']) - 1
J['images'][img_i]['mimeType'] = 'image/jpeg'
BIN += b'\0' * ((4 - len(BIN) % 4) % 4); J['buffers'][0]['byteLength'] = len(BIN)
js = json.dumps(J, ensure_ascii=False, separators=(',', ':')).encode(); js += b' ' * ((4 - len(js) % 4) % 4)
open(dst, 'wb').write(b'glTF' + struct.pack('<II', 2, 12 + 8 + len(js) + 8 + len(BIN)) + struct.pack('<I', len(js)) + b'JSON' + js + struct.pack('<I', len(BIN)) + b'BIN\0' + BIN)
print('SHORTS_OK', dst)
