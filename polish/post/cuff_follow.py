# Shorts cuffs follow the thighs, leg skin cleaned (11-18, user: the summer shorts clip at the sides and a pale triangle
# shows at the crotch; the side of the thigh looks blurry).
#  - cuff: the denim ring just above the hem keeps part of its weight on the hips (Tripo's shorts and legs are one
#    surface), so when a thigh swings the inner cuff wall stays behind and the thigh goes through it. The ring's weights
#    are blended toward the thigh skin right below the hem.
#  - skin: the leg skin texels of this material are repainted with the outfit's own skin tone, keeping a soft version of
#    the original shading (Tripo baked blotchy light into the outer thighs).
# usage: python3 cuff_follow.py IN.vrm OUT.vrm SKIN_R,G,B [band=0.12]
import io, json, struct, sys
import numpy as np
from PIL import Image, ImageFilter

src, dst = sys.argv[1], sys.argv[2]
TONE = np.array([float(x) for x in sys.argv[3].split(',')])
BAND = float(sys.argv[4]) if len(sys.argv) > 4 else 0.12
MAT = 'Material_lower_body'
b = open(src, 'rb').read()
n = struct.unpack_from('<I', b, 12)[0]; J = json.loads(b[20:20 + n]); o = 20 + n
binlen = struct.unpack_from('<I', b, o)[0]; BIN = bytearray(b[o + 8:o + 8 + binlen])

def view(i):
    a = J['accessors'][i]; v = J['bufferViews'][a['bufferView']]
    k = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a['componentType']]
    assert not v.get('byteStride') or v['byteStride'] == k * np.dtype(dt).itemsize
    off = v.get('byteOffset', 0) + a.get('byteOffset', 0); return off, dt, k, a['count']
def acc(i):
    off, dt, k, c = view(i); return np.frombuffer(bytes(BIN[off:off + c * k * np.dtype(dt).itemsize]), dt).reshape(c, k).copy()
def put(i, arr):
    off, dt, k, c = view(i); data = arr.astype(dt).tobytes(); BIN[off:off + len(data)] = data

mat_idx = next(i for i, m in enumerate(J['materials']) if m.get('name') == MAT)
hb = J['extensions']['VRMC_vrm']['humanoid']['humanBones']; human_of = {v['node']: k for k, v in hb.items()}
prim = node = None
for nd in J['nodes']:
    if 'mesh' not in nd or 'skin' not in nd: continue
    for p in J['meshes'][nd['mesh']]['primitives']:
        if p.get('material') == mat_idx and acc(p['attributes']['POSITION']).shape[0] > 5000: prim, node = p, nd
skin = J['skins'][node['skin']]; joints = skin['joints']
IBM = acc(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
jpos = lambda name: np.linalg.inv(IBM[joints.index(hb[name]['node'])])[:3, 3]
P = acc(prim['attributes']['POSITION']).astype(float); UV = acc(prim['attributes']['TEXCOORD_0']).astype(float)
JN = acc(prim['attributes']['JOINTS_0']).astype(int); WT = acc(prim['attributes']['WEIGHTS_0']).astype(float)
WT /= WT.sum(1, keepdims=True)
dom = np.array([human_of.get(joints[JN[i, np.argmax(WT[i])]], '') for i in range(len(P))])
tex_i = J['materials'][mat_idx]['pbrMetallicRoughness']['baseColorTexture']['index']
img_i = J['textures'][tex_i]['source']; bv = J['bufferViews'][J['images'][img_i]['bufferView']]
im = np.asarray(Image.open(io.BytesIO(bytes(BIN[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]))).convert('RGB')).astype(float) / 255
H_, W_ = im.shape[:2]
px = lambda uv: (np.clip((uv[:, 1] * H_).astype(int), 0, H_ - 1), np.clip((uv[:, 0] * W_).astype(int), 0, W_ - 1))
col = im[px(UV)]
is_skin = (col[:, 0] - col[:, 2]) > 0.12
is_denim = (col[:, 2] - col[:, 0]) > 0.03

report = {}
for s in ('left', 'right'):
    h0, k0 = jpos(s + 'UpperLeg'), jpos(s + 'LowerLeg'); ax = k0 - h0; L = np.linalg.norm(ax); ax /= L
    side = np.sign(P[:, 0]) == np.sign(h0[0])
    t = (P - h0) @ ax / L
    thigh_skin = side & is_skin & (dom == s + 'UpperLeg') & (t > 0) & (t < 0.8)
    if thigh_skin.sum() < 20: continue
    # hem = first height (from the hip down) where the leg ring is mostly skin and stays so; a low percentile of skin
    # heights caught yellow embroidery on the cuff (left 0.175 against right 0.243)
    ring = side & np.isin(dom, [s + 'UpperLeg', s + 'LowerLeg', 'hips'])
    edges = np.arange(0.0, 0.7, 0.01); frac = []
    for e0 in edges:
        sel = ring & (t >= e0) & (t < e0 + 0.02); frac.append(is_skin[sel].mean() if sel.sum() >= 6 else 0)
    frac = np.array(frac); ok = (frac > 0.6)
    t_hem = next((edges[i] for i in range(len(edges) - 3) if ok[i:i + 4].all()), np.percentile(t[thigh_skin], 10))
    donors = np.where(thigh_skin & (t < t_hem + 0.08))[0]
    cuff = np.where(side & is_denim & (t > t_hem - BAND) & (t < t_hem + 0.03) & np.isin(dom, [s + 'UpperLeg', 'hips']))[0]
    for i in cuff:
        k = donors[np.argmin(np.linalg.norm(P[donors] - P[i], axis=1))]
        a = np.clip((t[i] - (t_hem - BAND)) / (BAND * 0.7), 0, 1); a = a * a * (3 - 2 * a)
        w = {}
        for j, x in zip(JN[i], WT[i] * (1 - a)): w[j] = w.get(j, 0) + x
        for j, x in zip(JN[k], WT[k] * a): w[j] = w.get(j, 0) + x
        top = sorted(w.items(), key=lambda z: -z[1])[:4]; tot = sum(x for _, x in top)
        JN[i] = [j for j, _ in top] + [0] * (4 - len(top)); WT[i] = [x / tot for _, x in top] + [0] * (4 - len(top))
    report[s] = dict(hem=round(float(t_hem), 3), cuff=len(cuff), donors=len(donors))
put(prim['attributes']['JOINTS_0'], JN); put(prim['attributes']['WEIGHTS_0'], WT)

# leg skin texels: faces whose corners are skin and dominated by leg bones
# every face of the legs and hips counts; the texel test below keeps only skin (faces near the hem dominated by the
# hips were left out at first and showed as pale squares under the cuffs)
legs = np.isin(dom, ['leftUpperLeg', 'rightUpperLeg', 'leftLowerLeg', 'rightLowerLeg', 'hips'])
IDX = acc(prim['indices']).reshape(-1, 3).astype(int)
tri = IDX[legs[IDX].all(1) & (is_skin[IDX].sum(1) >= 2)]   # skin faces only: the cuff's yellow embroidery passes the texel test
mask = Image.new('L', (W_, H_), 0)
from PIL import ImageDraw
d = ImageDraw.Draw(mask)
for f in tri: d.polygon([tuple((UV[v] * [W_, H_]).tolist()) for v in f], fill=255)
mask = mask.filter(ImageFilter.MaxFilter(5))
m = np.asarray(mask).astype(float) / 255
pixel_skin = ((im[..., 0] - im[..., 2]) > 0.1)        # inside those faces, only texels that are skin (not a denim cuff edge)
m = m * pixel_skin
lum = im.mean(2)
blur = lambda a, r: np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r))).astype(float) / 255
mb = blur(m, 12) + 1e-4; lum_s = blur(lum * m, 12) / mb             # shading smoothed within the skin mask
ref = np.median(lum[m > 0.5]) if (m > 0.5).any() else lum.mean()
# the legs keep their own average colour (the face tone made them read darker and browner next to the denim)
own = np.median(im[m > 0.5], axis=0) if (m > 0.5).any() else TONE
tone = 0.5 * own + 0.5 * TONE * (own.mean() / TONE.mean())
shade = np.clip(1 + 0.6 * (lum_s / ref - 1), 0.7, 1.12)
clean = tone[None, None, :] * shade[..., None]
out = im * (1 - m[..., None]) + clean * m[..., None]
report['skinTexels'] = int((m > 0.5).sum())
# crotch front: a few faces map to a 6-10 texel speck of light grey; spread legs stretch them into a pale triangle on the
# denim (user, 11-18). Their texels (dilated) take the median colour of the other crotch faces.
hy = jpos('leftUpperLeg')[1]
cen = (np.abs(P[:, 0]) < 0.05) & (P[:, 1] > hy - 0.17) & (P[:, 1] < hy - 0.02) & (P[:, 2] > -0.02)
ctri = IDX[cen[IDX].all(1)]
fcol = np.array([out[px(UV[f])].mean(0) for f in ctri]) if len(ctri) else np.zeros((0, 3))
sat = fcol.max(1) - fcol.min(1) if len(fcol) else np.zeros(0)
bad = (sat < 0.05) & (fcol.mean(1) > 0.6)
if bad.any() and (~bad).any():
    denim = np.median(fcol[~bad], axis=0)
    bm = Image.new('L', (W_, H_), 0); bd = ImageDraw.Draw(bm)
    for f in ctri[bad]: bd.polygon([tuple((UV[v] * [W_, H_]).tolist()) for v in f], fill=255)
    bmask = np.asarray(bm.filter(ImageFilter.MaxFilter(7))) > 0
    out[bmask] = denim
    report['crotchSpecks'] = int(bad.sum())
buf = io.BytesIO(); Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, 'JPEG', quality=93); data = buf.getvalue()
off = len(BIN); off += (4 - off % 4) % 4; BIN += b'\0' * (off - len(BIN)); BIN += data
J['bufferViews'].append(dict(buffer=0, byteOffset=off, byteLength=len(data))); J['images'][img_i]['bufferView'] = len(J['bufferViews']) - 1
J['images'][img_i]['mimeType'] = 'image/jpeg'
BIN += b'\0' * ((4 - len(BIN) % 4) % 4); J['buffers'][0]['byteLength'] = len(BIN)
js = json.dumps(J, ensure_ascii=False, separators=(',', ':')).encode(); js += b' ' * ((4 - len(js) % 4) % 4)
open(dst, 'wb').write(b'glTF' + struct.pack('<II', 2, 12 + 8 + len(js) + 8 + len(BIN)) + struct.pack('<I', len(js)) + b'JSON' + js + struct.pack('<I', len(BIN)) + b'BIN\0' + BIN)
print('CUFF_OK', dst, json.dumps(report))
