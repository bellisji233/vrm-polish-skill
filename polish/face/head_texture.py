"""Prepare the face texture of a new head: remove the brows painted on the skin (the 3D brow strips replace them),
the contour line painted along the cheek crease and jaw, and soften the drawn mouth line to a muted rose.

1. blender -b PROJECT/work/weights/weighted.blend --python head_texture.py -- export MEASURE_DIR
   reads work/measure/{measure.json, head-components.json, head-skin-boundaries.json, crease-pairs.json};
   writes MEASURE_DIR/texture/{raw.png, uv.json}
2. python3 head_texture.py fix MEASURE_DIR/texture  ->  head-basecolor.png, 贴图修整前后.jpg
Same procedures as the purple head's hand-run repairs (normalized Gaussian fill from surrounding skin of the same
UV island; mouth texels darker than the lip blended toward the lip colour).
"""
import json
import sys
from pathlib import Path

import numpy as np


def export_np(md):
    """Blender side without PIL: raw pixels as .npy, UV geometry as JSON."""
    import bpy
    md = Path(md); out = md / 'texture'; out.mkdir(exist_ok=True)
    m = json.loads((md / 'measure.json').read_text(encoding='utf-8'))
    roles = m['new_head']['roles']; lm = m['new_head']['landmarks']; s = m['frame']['s']
    comps = json.load(open(md / 'head-components.json'))
    pairs = json.load(open(md / 'crease-pairs.json'))['pairs']
    loops = json.load(open(md / 'head-skin-boundaries.json'))
    h = bpy.data.objects['Head']; me = h.data; MW = h.matrix_world
    P = np.array([(MW @ v.co)[:] for v in me.vertices])
    img = next(nd.image for mt in me.materials if mt and mt.use_nodes for nd in mt.node_tree.nodes
               if nd.type == 'TEX_IMAGE' and nd.image and nd.image.has_data)
    W_, H_ = img.size
    A = np.empty(W_ * H_ * 4, np.float32); img.pixels.foreach_get(A)
    np.save(out / 'raw.npy', (np.clip(A.reshape(H_, W_, 4)[::-1, :, :3], 0, 1) * 255).astype(np.uint8))   # top row first
    skin = set(comps[roles['skin']])
    uvd = me.uv_layers.active.data
    vuv = {}
    tris = []
    for p in me.polygons:
        if not all(v in skin for v in p.vertices):
            continue
        q = [tuple(uvd[li].uv) for li in p.loop_indices]
        for li, vi in zip(p.loop_indices, p.vertices):
            vuv.setdefault(vi, tuple(uvd[li].uv))
        tris.append(dict(uv=q, c=P[list(p.vertices)].mean(0).tolist()))
    crease = [[vuv[a], vuv[b]] for a, b in pairs if a in vuv and b in vuv]
    # jaw: open edges of the skin under the chin, chosen as the build chooses them (the profile's assembly-space box,
    # carried into this head through the profile's head_affine and the head frame)
    zm = lm['mouth'][2]
    prof = json.loads((Path(m['profile']) / 'profile.json').read_text(encoding='utf-8'))
    Taff = np.load(Path(m['profile']) / prof['head_affine']); S_ = float(np.cbrt(np.linalg.det(Taff[:3]))); TV = Taff[3]
    fr = m['frame']; Pa = ((P - np.array(fr['t'])) / fr['s'] - TV) / S_
    jaw_v = set(np.nonzero((Pa[:, 1] > -0.22) & (Pa[:, 2] < 0.44) & (np.abs(Pa[:, 0]) < 0.21))[0].tolist())
    ecount = {}
    for p in me.polygons:
        if all(v in skin for v in p.vertices):
            for k in p.edge_keys:
                ecount[k] = ecount.get(k, 0) + 1
    jaw = [[vuv[a], vuv[b]] for (a, b), c in ecount.items() if c == 1 and a in jaw_v and b in jaw_v]
    # brows modelled as pieces: the copy painted on the skin under them is removed. Brows only painted on the skin
    # (no brow pieces) are the brows, and stay.
    brow_area = []
    if roles.get('brow'):
        brow_v = np.array([v for side in ('R', 'L') for v in comps[roles['brow'][side]]])
        BP = P[brow_v][:, [0, 2]]
        for t in tris:
            d = np.min(np.linalg.norm(BP - np.array(t['c'])[[0, 2]], axis=1))
            if d < 0.007 * s:
                brow_area.append(t['uv'])
    # mouth line: skin vertices around the mouth landmarks that are darker than the skin
    vcol = {}
    A3 = A.reshape(H_, W_, 4)[..., :3]
    for vi, (u, v) in vuv.items():
        vcol[vi] = A3[int((v % 1) * (H_ - 1)), int((u % 1) * (W_ - 1))]
    mw = abs(lm['mouthL'][0] - lm['mouthR'][0])
    cand = [vi for vi in vuv if abs(P[vi, 0] - lm['mouth'][0]) < 0.75 * mw + 0.004 * s and abs(P[vi, 2] - zm) < 0.006 * s
            and P[vi, 1] < lm['mouth'][1] + 0.01 * s]
    lum = np.array([vcol[v].mean() for v in cand]); skin_lum = float(np.median([c.mean() for c in vcol.values()]))
    mouth_uv = [vuv[v] for v, l_ in zip(cand, lum) if l_ < 0.75 * skin_lum]
    used = [[tuple(uvd[li].uv) for li in p.loop_indices] for p in me.polygons]      # every face, for free texture space
    json.dump(dict(size=[W_, H_], tris=[t['uv'] for t in tris], crease=crease, jaw=jaw, brow_area=brow_area, mouth=mouth_uv,
                   used=used), open(out / 'uv.json', 'w'))
    print('TEXTURE_EXPORT ' + json.dumps(dict(tris=len(tris), crease=len(crease), jaw=len(jaw), brow_area=len(brow_area), mouth=len(mouth_uv))))


# mouth interior colours (0-1, as stored in the texture): back wall, pocket wall, inner lip, tongue, white.
# auto_head.py looks for these.
MOUTH_PATCHES = {'dark': (0.13, 0.045, 0.05), 'midred': (0.40, 0.14, 0.15), 'innerlip': (0.70, 0.38, 0.38),
                 'tongue': (0.80, 0.44, 0.44), 'white': (0.97, 0.96, 0.96)}


def _box(x, k, axis):
    c = np.cumsum(np.pad(x, [(k + 1, k) if i == axis else (0, 0) for i in range(2)], mode='edge'), axis=axis)
    return (np.take(c, np.arange(2 * k + 1, c.shape[axis]), axis=axis) - np.take(c, np.arange(0, c.shape[axis] - 2 * k - 1), axis=axis)) / (2 * k + 1)


def gblur(x, r):
    k = max(int(round(np.sqrt(12 * r * r / 3 + 1) / 2 - 0.5)), 1); x = x.astype(np.float32)
    for _ in range(3):
        x = _box(_box(x, k, 0), k, 1)
    return x


def fill_from(A, known, region, radii, crop=None):
    """normalized Gaussian fill of `region` from `known` pixels, coarse to fine"""
    fill = A.copy(); done = np.zeros(region.shape, bool); K = known.astype(np.float32)
    for r in radii:
        kb = gblur(K, r); ok = region & (kb > 2e-3)
        for c in range(3):
            f = gblur(A[..., c] * K, r) / np.maximum(kb, 1e-6); sub = fill[..., c]
            first = ok & ~done; sub[first] = f[first]
            refine = ok & done; sub[refine] = 0.5 * sub[refine] + 0.5 * f[refine]
        done |= ok
    return fill


def fix(td):
    from PIL import Image, ImageDraw, ImageFilter
    td = Path(td)
    d = json.load(open(td / 'uv.json')); W, H = d['size']
    A0 = np.load(td / 'raw.npy').astype(np.float32); A = A0.copy()
    P = lambda p: (p[0] % 1 * W, (1 - p[1] % 1) * H)
    isl = Image.new('L', (W, H), 0); di = ImageDraw.Draw(isl)
    for t in d['tris']:
        di.polygon([P(p) for p in t], fill=255)
    I = np.asarray(isl.filter(ImageFilter.MinFilter(5))) > 0
    report = {}
    # 1. contour along the cheek crease and the jaw edge
    band = max(8, W // 200)
    line = Image.new('L', (W, H), 0); dl = ImageDraw.Draw(line)
    for a, b in d['crease']: dl.line([P(a), P(b)], fill=255, width=band)
    for a, b in d['jaw']: dl.line([P(a), P(b)], fill=255, width=band // 2)
    L = (np.asarray(line) > 0) & I
    if L.any():
        fill = fill_from(A, I & ~L, L, (band * 0.9, band * 0.45))
        soft = gblur(L.astype(np.float32), band * 0.15) * I
        A = A * (1 - soft[..., None]) + fill * soft[..., None]
    report['contour_px'] = int(L.sum())
    # 2. painted brows: strokes darker than the local skin inside the area next to the 3D brow strips
    area = Image.new('L', (W, H), 0); da = ImageDraw.Draw(area)
    for poly in d['brow_area']: da.polygon([P(u) for u in poly], fill=255)
    area = np.asarray(area.filter(ImageFilter.MaxFilter(9))) > 0
    if area.any():
        lum = A.mean(-1); bg = gblur(lum, 25)
        stroke = area & (np.abs(bg - lum) > 3.5)
        M = (np.asarray(Image.fromarray((stroke * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(17))) > 0) & area
        fill = fill_from(A, ~M, M, (120, 60, 30, 12))
        soft = np.clip(gblur(M.astype(np.float32), 3) * 1.5, 0, 1)
        A = A * (1 - soft[..., None]) + fill * soft[..., None]
        report['brow_px'] = int(M.sum())
    # 3. mouth line: texels darker than the lip, blended toward a muted lip colour (per UV cluster of the line)
    pts = np.array([P(u) for u in d['mouth']]) if d['mouth'] else np.zeros((0, 2))
    R = max(20, W // 80)
    groups = []
    for p in pts:
        for g in groups:
            if np.min(np.linalg.norm(np.array(g) - p, axis=1)) < 3 * R: g.append(p); break
        else:
            groups.append([p])
    for g in groups:
        g = np.array(g)
        if len(g) < 2: continue
        x0, y0 = np.maximum((g.min(0) - R - 10).astype(int), 0); x1, y1 = np.minimum((g.max(0) + R + 10).astype(int), [W, H])
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dist = np.min(np.hypot(xx[..., None] - g[:, 0], yy[..., None] - g[:, 1]), axis=-1)
        bnd = dist <= R; sub = A[y0:y1, x0:x1]; lum = sub.mean(-1)
        bl = lum[bnd]; lipLum = np.percentile(bl, 65); lip = np.median(sub[bnd][bl >= lipLum], axis=0)
        w = np.clip((0.8 * lipLum - lum) / (0.25 * lipLum), 0, 1) * 0.65 * bnd
        w = np.asarray(Image.fromarray((w * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32) / 255
        A[y0:y1, x0:x1] = sub * (1 - w[..., None]) + (lip * 0.7)[None, None, :] * w[..., None]
    report['mouth_groups'] = len(groups)
    # 4. mouth interior colours: the generated mouth parts (pocket, back wall, tongue) take their colour from texture
    # spots. A face texture rarely has a dark mouth red or a tongue pink, so flat patches of these colours are painted
    # into texture space no face uses (auto_head picks the closest flat patch, which is then exactly these).
    if d.get('used'):
        occ = Image.new('L', (W, H), 0); do = ImageDraw.Draw(occ)
        for poly in d['used']:
            if len(poly) >= 3: do.polygon([P(u) for u in poly], fill=255)
        occ = np.asarray(occ.filter(ImageFilter.MaxFilter(9))) > 0
        cell = max(48, W // 64); free = []
        for y in range(0, H - cell + 1, cell):
            for x in range(0, W - cell + 1, cell):
                if not occ[y:y + cell, x:x + cell].any():
                    free.append((x, y))
        placed = {}
        for (name, rgb), (x, y) in zip(MOUTH_PATCHES.items(), free):
            A[y:y + cell, x:x + cell] = np.array(rgb, np.float32) * 255
            placed[name] = [x, y, cell]
        report['mouth_patches'] = placed
    out = np.clip(A, 0, 255).astype(np.uint8)
    Image.fromarray(out).save(td / 'head-basecolor.png')
    # before/after of the face area
    ys, xs = np.nonzero(I)
    if len(ys):
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        a, b = Image.fromarray(A0.astype(np.uint8)).crop((x0, y0, x1, y1)), Image.fromarray(out).crop((x0, y0, x1, y1))
        sc = 700 / max(a.size); a, b = a.resize((int(a.width * sc), int(a.height * sc))), b.resize((int(b.width * sc), int(b.height * sc)))
        sheet = Image.new('RGB', (a.width * 2 + 10, a.height), 'white'); sheet.paste(a, (0, 0)); sheet.paste(b, (a.width + 10, 0))
        sheet.save(td / '贴图修整前后.jpg', quality=90)
    print('TEXTURE_FIX ' + json.dumps(report))


if __name__ == '__main__':
    if '--' in sys.argv:
        args = sys.argv[sys.argv.index('--') + 1:]
        if args[0] == 'export':
            export_np(args[1])
    elif len(sys.argv) > 2 and sys.argv[1] == 'fix':
        fix(sys.argv[2])
