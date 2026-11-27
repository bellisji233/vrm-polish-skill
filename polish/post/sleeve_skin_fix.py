# Skin-coloured patches inside long sleeves (11-18, user: the forest outfit's armpit is bare skin; parts not shown
# from the front have no clothing texture).
# Tripo textures a model by projecting a few views; the underside of a T-pose sleeve near the armpit is in none of
# them, so its colour is guessed and comes out as a skin gradient. On an outfit whose sleeves reach the wrist, any skin
# colour on faces carried by the upper arm or shoulder is wrong. Those texels are repainted with the sleeve colour
# (median of the non-skin texels on the same bones), keeping their own light and shade; the edge blends by how
# skin-like a texel is. Hands are a separate material and the wrist stub is on the lower arm, so neither is touched.
# usage: python3 sleeve_skin_fix.py IN.vrm OUT.vrm [material=Material_upper_body] [bones=UpperArm,Shoulder]
import io, json, struct, sys
import numpy as np
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
MAT = sys.argv[3] if len(sys.argv) > 3 else 'Material_upper_body'
BONES = (sys.argv[4] if len(sys.argv) > 4 else 'UpperArm,Shoulder').split(',')
np.seterr(all='ignore')

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
hb = J['extensions']['VRMC_vrm']['humanoid']['humanBones']; human_of = {v['node']: k for k, v in hb.items()}
want = {hb[s + bn]['node'] for s in ('left', 'right') for bn in BONES if (s + bn) in hb}
# the skinned primitive with this material that has the most vertices carried by these bones
prim = node = None; best = 0
for nd in J['nodes']:
    if 'mesh' not in nd or 'skin' not in nd: continue
    jo = J['skins'][nd['skin']]['joints']
    for pr in J['meshes'][nd['mesh']]['primitives']:
        if pr.get('material') != mat_idx: continue
        jn = acc(pr['attributes']['JOINTS_0']).astype(int); wt = acc(pr['attributes']['WEIGHTS_0'])
        k = int(np.isin(np.array(jo)[jn[np.arange(len(jn)), np.argmax(wt, 1)]], list(want)).sum())
        if k > best: best, prim, node = k, pr, nd
if prim is None: sys.exit('no primitive with %s carried by %s' % (MAT, BONES))
jo = np.array(J['skins'][node['skin']]['joints'])
UV = acc(prim['attributes']['TEXCOORD_0']).astype(float); IDX = acc(prim['indices']).reshape(-1, 3).astype(int)
JN = acc(prim['attributes']['JOINTS_0']).astype(int); WT = acc(prim['attributes']['WEIGHTS_0']).astype(float)
carried = (WT * np.isin(jo[JN], list(want))).sum(1)          # weight on these bones per vertex
tex_i = J['materials'][mat_idx]['pbrMetallicRoughness']['baseColorTexture']['index']
img_i = J['textures'][tex_i]['source']; bv = J['bufferViews'][J['images'][img_i]['bufferView']]
im = np.asarray(Image.open(io.BytesIO(bytes(BIN[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]))).convert('RGB')).astype(float) / 255
H_, W_ = im.shape[:2]

def skinness(c):            # 0 = cloth, 1 = clearly skin (reddish, not dark)
    return np.clip(((c[:, 0] - c[:, 2]) - 0.10) / 0.08, 0, 1) * (c.mean(1) > 0.42)

# armpit faces are half carried by the chest, so 15% on the arm or shoulder is enough; the sides of the torso under the
# arm (outside the chest centre, between waist and shoulder) are clothed too
POS = acc(prim['attributes']['POSITION']).astype(float)
neck_y = POS[:, 1].max()
lower = (WT * np.isin(jo[JN], [hb[s + 'LowerArm']['node'] for s in ('left', 'right')])).sum(1)
side = (np.abs(POS[:, 0]) > 0.10) & (POS[:, 1] > neck_y - 0.40) & (POS[:, 1] < neck_y - 0.08) & (lower < 0.5)
faces = IDX[((carried[IDX] > 0.15) & (lower[IDX] < 0.5)).all(1) | side[IDX].all(1)]
texels = []                 # (ys, xs) per face
def raster(f):
    uv = UV[f] * [W_, H_]; c = uv.mean(0); uv = c + (uv - c) + np.sign(uv - c) * 1.5
    x0, y0 = np.floor(uv.min(0)).astype(int); x1, y1 = np.ceil(uv.max(0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W_ - 1), min(y1, H_ - 1)
    if x1 < x0 or y1 < y0: return None
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    (ax_, ay_), (bx, by), (cx, cy) = uv
    den = (by - cy) * (ax_ - cx) + (cx - bx) * (ay_ - cy)
    if abs(den) < 1e-9: return None
    l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den; l2 = ((cy - ay_) * (xs - cx) + (ax_ - cx) * (ys - cy)) / den
    ins = (l1 >= -0.03) & (l2 >= -0.03) & (1 - l1 - l2 >= -0.03)
    return ((ys[ins] - 0.5).astype(int), (xs[ins] - 0.5).astype(int)) if ins.any() else None
# whole faces: a face is repainted only when most of it is skin (pink flowers embroidered on the capelet stay)
mask = np.zeros((H_, W_), bool); allm = np.zeros((H_, W_), bool)
for f in faces:
    r = raster(f)
    if not r: continue
    allm[r] = True
    if skinness(im[r]).mean() > 0.5: mask[r] = True
ys, xs = np.nonzero(allm); col = im[ys, xs]; w = skinness(col)
# the sleeve is the light cloth here; the forest capelet (dark green) and lace are carried by the same bones
cloth = col[(w == 0) & (col.mean(1) > 0.62) & (col.max(1) - col.min(1) < 0.18)]
if len(cloth) < 100: sys.exit('too little sleeve colour to sample')
ref = np.median(cloth, 0); lum_cloth = np.median(cloth.mean(1)); lum_skin = np.median(col[w > 0.5].mean(1)) if (w > 0.5).any() else 1
print('sleeve colour', ref.round(3), 'texels', len(col), 'skin texels', int((w > 0.5).sum()), '(%.1f%%)' % (100 * (w > 0.5).mean()))
shade = np.clip(col.mean(1) / lum_skin, 0.75, 1.1)[:, None]
fix = np.clip(ref * shade, 0, 1)
sel = mask[ys, xs]; w = w * sel
out = im.copy(); out[ys, xs] = col * (1 - w[:, None]) + fix * w[:, None]
print('repainted faces cover', int(sel.sum()), 'texels')

buf = io.BytesIO(); Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, 'JPEG', quality=93); data = buf.getvalue()
off = len(BIN); off += (4 - off % 4) % 4; BIN += b'\0' * (off - len(BIN)); BIN += data
J['bufferViews'].append(dict(buffer=0, byteOffset=off, byteLength=len(data))); J['images'][img_i]['bufferView'] = len(J['bufferViews']) - 1
J['images'][img_i]['mimeType'] = 'image/jpeg'
BIN += b'\0' * ((4 - len(BIN) % 4) % 4); J['buffers'][0]['byteLength'] = len(BIN)
js = json.dumps(J, ensure_ascii=False, separators=(',', ':')).encode(); js += b' ' * ((4 - len(js) % 4) % 4)
open(dst, 'wb').write(b'glTF' + struct.pack('<II', 2, 12 + 8 + len(js) + 8 + len(BIN)) + struct.pack('<I', len(js)) + b'JSON' + js + struct.pack('<I', len(BIN)) + b'BIN\0' + BIN)
print('SLEEVE_OK', dst)
