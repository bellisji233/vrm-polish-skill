"""Cut anime face effects out of edited renders of this character's own face (face_fx.py reads the result).

Each effect is drawn (Codex) on a front render of the character's own face, taken with the decal camera in the head
frame (fx_render.py). The cut-out keeps only what the drawing changed, and only where that effect belongs (both eyes,
both cheeks, the mouth), so nothing of the face around it comes along (the purple head's star eyes carried its green
iris onto 人物2, 11-20).

Difference alone is not enough: the drawing redraws nearby hair strands and lash lines slightly differently. So each
effect keeps only its own kind of change: eye effects the iris discs (the cut iris layer's circles, from the build
report) and new white sparkles near the eyes; the blush only texels that turned pinker.

usage: python3 fx_cutout.py FX_DIR MEASURE_JSON PROFILE_FX_DIR [BUILD_REPORT]
  FX_DIR/0-原图.png               the render
  FX_DIR/<effect>-codex.png       the drawings (eye_star, eye_heart, blush)
  writes FX_DIR/<effect>.png (RGBA, cropped), FX_DIR/mouth_cat.png, FX_DIR/fx.json, FX_DIR/贴纸检查.jpg
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REGION = {'eye_star': 'eyes', 'eye_heart': 'eyes', 'blush': 'cheeks'}


def project(cam, size, p):
    """Point in the head frame (Blender axes) -> pixel of the cropped render."""
    W, H = size; x0, y0, x1, y1 = cam['crop']
    pos = np.array(cam['pos'], float)
    p3 = np.array([p[0], p[2], -p[1]], float)            # Blender -> three.js
    d = p3 - pos; t = math.tan(math.radians(cam['fov']) / 2)
    xn = (d[0] / -d[2]) / (t * cam['aspect']); yn = (d[1] / -d[2]) / t
    u, v = (xn + 1) / 2, (1 - yn) / 2
    return np.array([(u - x0) / (x1 - x0) * W, (v - y0) / (y1 - y0) * H])


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def _blur(a, r):
    for _ in range(2):
        a = (a + np.roll(a, r, 0) + np.roll(a, -r, 0) + np.roll(a, r, 1) + np.roll(a, -r, 1)) / 5
    return a


def _align(base, img, reach=16):
    """Integer shift of img that best matches base (Codex sometimes moves the picture by a few pixels)."""
    b = base[::4, ::4].mean(-1); best = (1e9, 0, 0)
    for dy in range(-reach, reach + 1, 2):
        for dx in range(-reach, reach + 1, 2):
            s = np.roll(np.roll(img, dy, 0), dx, 1)[::4, ::4].mean(-1)
            e = float(np.abs(s - b)[8:-8, 8:-8].mean())
            if e < best[0]:
                best = (e, dy, dx)
    return np.roll(np.roll(img, best[1], 0), best[2], 1), best[1:]


def _components(mask):
    lab = np.zeros(mask.shape, np.int32); n = 0; sizes = {}
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        if lab[y, x]:
            continue
        n += 1; st = [(y, x)]; lab[y, x] = n; c = 0
        while st:
            cy, cx = st.pop(); c += 1
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n; st.append((ny, nx))
        sizes[n] = c
    return lab, sizes


def main(fx_dir, measure_json, profile_fx, build_report=None):
    fx_dir = Path(fx_dir)
    prof_info = json.load(open(Path(profile_fx) / 'fx.json'))
    cam = prof_info['image']['camera']
    base_im = Image.open(fx_dir / '0-原图.png').convert('RGB'); size = base_im.size
    base = np.asarray(base_im).astype(np.float32) / 255
    m = json.load(open(measure_json)); fr = m['frame']; L = m['new_head']['landmarks']
    lm = {k: project(cam, size, (np.array(v) - np.array(fr['t'])) / fr['s']) for k, v in L.items()}
    eyes = {s: (lm[f'eyeInner{s}'] + lm[f'eyeOuter{s}']) / 2 for s in ('R', 'L')}
    ew = {s: float(np.linalg.norm(lm[f'eyeInner{s}'] - lm[f'eyeOuter{s}'])) for s in ('R', 'L')}
    H, W = base.shape[:2]; yy, xx = np.mgrid[0:H, 0:W]

    def ellipse(c, rx, ry):
        return ((xx - c[0]) / rx) ** 2 + ((yy - c[1]) / ry) ** 2 <= 1

    regions = {'eyes': ellipse(eyes['R'], 0.75 * ew['R'], 0.45 * ew['R']) | ellipse(eyes['L'], 0.75 * ew['L'], 0.45 * ew['L']),
               'cheeks': ellipse(eyes['R'] + [0, 0.75 * ew['R']], 0.75 * ew['R'], 0.5 * ew['R'])
               | ellipse(eyes['L'] + [0, 0.75 * ew['L']], 0.75 * ew['L'], 0.5 * ew['L'])}
    # iris discs in the picture: the cut iris layer (build report, head frame) or else the eye middle
    iris_px = {}
    il = json.load(open(build_report)).get('irisLayer') if build_report else None
    for s_ in ('R', 'L'):
        ey = float(np.mean([(np.array(L[f'eye{k}{s_}']) - np.array(fr['t']))[1] / fr['s'] for k in ('Inner', 'Outer')]))
        if il and s_ in il:
            cx_, cz_ = il[s_]['centre']; r_ = il[s_]['radius_mm'] / 1000
            c_px = project(cam, size, (cx_, ey, cz_)); e_px = project(cam, size, (cx_ + r_, ey, cz_))
            iris_px[s_] = (c_px, float(np.linalg.norm(e_px - c_px)))
        else:
            iris_px[s_] = (eyes[s_], 0.3 * ew[s_])
    discs = np.zeros((H, W), bool)
    for s_, (c_px, r_px) in iris_px.items():
        disc = ((xx - c_px[0]) ** 2 + (yy - c_px[1]) ** 2) <= (1.2 * r_px) ** 2
        if il and il.get(s_, {}).get('opening'):
            # only inside the skin's eye opening: above it are the lid and lash line, which the drawing redraws too
            ey = float(np.mean([(np.array(L[f'eye{k}{s_}']) - np.array(fr['t']))[1] / fr['s'] for k in ('Inner', 'Outer')]))
            poly = Image.new('L', (W, H), 0)
            ImageDraw.Draw(poly).polygon([tuple(project(cam, size, (x_, ey, z_))) for x_, z_ in il[s_]['opening']], fill=255)
            disc &= np.asarray(poly) > 0
        discs |= disc
    info = {'image': {'size': list(size), 'camera': cam}}
    sheet = []
    for name, reg in REGION.items():
        src = fx_dir / f'{name}-codex.png'
        if not src.exists():
            print(f'  {name}: no drawing ({src.name}), skipped'); continue
        im = Image.open(src).convert('RGB')
        if im.size != size:
            im = im.resize(size, Image.LANCZOS)
        ed = np.asarray(im).astype(np.float32) / 255
        ed, shift = _align(base, ed)
        d = _blur(np.abs(ed - base).max(-1), 1)
        a = _smooth((d - 0.05) / 0.12) * regions[reg]
        if reg == 'eyes':
            Le = ed @ np.array([0.299, 0.587, 0.114]); sat = (ed.max(-1) - ed.min(-1)) / np.maximum(ed.max(-1), 1e-4)
            sparkle = regions['eyes'] & (Le > 0.85) & (sat < 0.2) & (d > 0.25)
            a = a * (discs | sparkle)
        else:
            pink = (ed[..., 0] - ed[..., 1]) - (base[..., 0] - base[..., 1])
            a = a * _smooth((pink - 0.03) / 0.06)
        lab, sizes = _components(a > 0.2)
        keep = {k for k, c in sizes.items() if c >= 40}
        a = a * np.isin(lab, list(keep) + [0]) * (a > 0.02)
        a[(lab > 0) & ~np.isin(lab, list(keep))] = 0
        ys, xs = np.nonzero(a > 0.02)
        if not len(ys):
            print(f'  {name}: nothing changed inside its region'); continue
        x0, y0 = max(0, xs.min() - 4), max(0, ys.min() - 4); x1, y1 = min(W, xs.max() + 5), min(H, ys.max() + 5)
        rgba = np.dstack([ed[y0:y1, x0:x1], a[y0:y1, x0:x1]])
        Image.fromarray((rgba * 255).astype(np.uint8)).save(fx_dir / f'{name}.png')
        info[name] = {'bbox': [int(x0), int(y0), int(x1), int(y1)], 'blobs': len(keep), 'shift': list(shift)}
        sheet.append((name, rgba))
    # cat mouth: the profile's code-drawn line, fitted between this face's mouth corners
    cat = Image.open(Path(profile_fx) / 'mouth_cat.png').convert('RGBA')
    mw = float(np.linalg.norm(lm['mouthL'] - lm['mouthR'])); pc = prof_info['mouth_cat']['bbox']
    pw = pc[2] - pc[0]
    sc = 1.15 * mw / pw
    cw, ch = max(4, int(round(cat.width * sc))), max(4, int(round(cat.height * sc)))
    cat = cat.resize((cw, ch), Image.LANCZOS); cat.save(fx_dir / 'mouth_cat.png')
    mc = lm['mouth']
    info['mouth_cat'] = {'bbox': [int(mc[0] - cw / 2), int(mc[1] - ch / 2), int(mc[0] - cw / 2) + cw, int(mc[1] - ch / 2) + ch],
                         'blobs': 1, 'drawn': 'code, profile line fitted to this mouth'}
    json.dump(info, open(fx_dir / 'fx.json', 'w'), indent=1)
    # check sheet: each cut-out on grey and over the render
    rows = []
    for name, rgba in sheet:
        x0, y0, x1, y1 = info[name]['bbox']
        over = base.copy(); a_ = rgba[..., 3:]
        over[y0:y1, x0:x1] = over[y0:y1, x0:x1] * (1 - a_) + rgba[..., :3] * a_
        grey = np.full_like(rgba[..., :3], 0.5); grey = grey * (1 - a_) + rgba[..., :3] * a_
        crop = over[max(0, y0 - 60):y1 + 60, max(0, x0 - 60):x1 + 60]
        rows.append(np.concatenate([np.pad(grey, ((60, 60), (60, 60), (0, 0)), constant_values=0.5)[:crop.shape[0], :crop.shape[1]], crop], 1))
    if rows:
        wmax = max(r.shape[1] for r in rows)
        rows = [np.pad(r, ((0, 10), (0, wmax - r.shape[1]), (0, 0)), constant_values=1) for r in rows]
        Image.fromarray((np.concatenate(rows, 0) * 255).astype(np.uint8)).save(fx_dir / '贴纸检查.jpg', quality=90)
    print('FX_CUTOUT ' + json.dumps({k: v for k, v in info.items() if k != 'image'}))


if __name__ == '__main__':
    main(*sys.argv[1:5])
