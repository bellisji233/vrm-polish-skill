# Locate the parts of a Charakuru head automatically: run inside the kit's expression studio (polish/expr/run_studio.py)
# on a fresh expression workspace of the built character. Writes the head profile's expr-data/:
#   components.json, skin_boundaries.json, points.npy (the studio's own mesh inspection, unchanged)
#   roles.json        component roles and face landmarks (polish/face/locate.py)
#   eye_points.json   eye corners and lid midpoints from the eye openings of the skin
#   uvspots.json      texture spots used to colour generated mouth and eye geometry
# env: POLISH_PROFILE_OUT (the profile folder), POLISH_DIR
import os, sys, json, importlib.util, bpy, numpy as np

_spec = importlib.util.spec_from_file_location('polish_locate', os.environ['POLISH_DIR'] + '/face/locate.py')
loc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(loc)
OUT = os.environ['POLISH_PROFILE_OUT'].rstrip('/') + '/expr-data/'
os.makedirs(OUT, exist_ok=True)
info = helper.inspect_mesh('Head')
P = np.array(info['points']); comps = info['components']; bounds = info['boundaries']
vcol, vuv, A = loc.vertex_colours(bpy.data.objects['Head'], len(P))
H_, W_ = A.shape[:2]
_known = json.loads(os.environ['POLISH_KNOWN_LANDMARKS']) if os.environ.get('POLISH_KNOWN_LANDMARKS') else None
# parts the build added on the head (face decals, brows over the bangs, the cut iris layer) are not head parts
_hm = bpy.data.objects['Head'].data
_added = {i for i, m in enumerate(_hm.materials) if m and (m.name.startswith(('FX_', 'EyeIris')) or m.name in ('BrowOverlay', 'EyeLid'))}
_added_v = {v for p in _hm.polygons if p.material_index in _added for v in p.vertices}
_skip = {i for i, c in enumerate(comps) if c and all(v in _added_v for v in c)}
found = loc.locate(P, comps, bounds, vcol, known=_known, skip=_skip)
found['roles']['added_parts'] = sorted(_skip)
roles, pts = found['roles'], found['eye_points']
# ---- texture spots: flat patches of the face texture closest to a dark mouth red, a clean white and three mouth reds
def patch_spot(target, step, max_std):
    hh, ww = (H_ // step) * step, (W_ // step) * step
    T = A[:hh, :ww].reshape(hh // step, step, ww // step, step, 3)
    m = T.mean((1, 3)); v = T.std((1, 3)).mean(-1)
    d = np.linalg.norm(m - np.array(target), axis=-1) + v
    d[v > max_std] = 1e9
    y, x = np.unravel_index(int(np.argmin(d)), d.shape)
    return [float((x * step + step / 2) / W_), float((y * step + step / 2) / H_), [round(float(c), 3) for c in m[y, x]]]
# targets: the mouth colour patches head_texture.py paints into free texture space (MOUTH_PATCHES); on a texture without
# them the closest flat patch is used, as before
_hts = importlib.util.spec_from_file_location('polish_head_texture', os.environ['POLISH_DIR'] + '/face/head_texture.py')
_ht = importlib.util.module_from_spec(_hts); _hts.loader.exec_module(_ht); _MP = _ht.MOUTH_PATCHES
uvspots = {'dark': patch_spot(_MP['dark'], 24, 0.02), 'white': patch_spot(_MP['white'], 24, 0.02),
           'innerlip': patch_spot(_MP['innerlip'], 16, 0.015), 'tongue': patch_spot(_MP['tongue'], 16, 0.015),
           'midred': patch_spot(_MP['midred'], 16, 0.015)}

json.dump(comps, open(OUT + 'components.json', 'w'))
sb = sorted([dict(n=len(lv), ctr=[round(float(x), 4) for x in P[lv].mean(0)], lo=[round(float(x), 4) for x in P[lv].min(0)],
                  hi=[round(float(x), 4) for x in P[lv].max(0)], vs=lv) for lv in bounds[roles['skin']]], key=lambda d: -d['n'])
json.dump(sb, open(OUT + 'skin_boundaries.json', 'w'))
np.save(OUT + 'points.npy', P)
json.dump(pts, open(OUT + 'eye_points.json', 'w'), indent=1)
json.dump(uvspots, open(OUT + 'uvspots.json', 'w'), indent=1)
json.dump(dict(roles, landmarks=found['landmarks']), open(OUT + 'roles.json', 'w'), indent=1)
print('AUTO_HEAD ' + json.dumps({k: v for k, v in roles.items() if k not in ('lower_lash', 'rim_vs')}) + f" lower_lash={len(roles['lower_lash'])}")
print('LANDMARKS ' + json.dumps({k: [round(x, 4) for x in v] for k, v in found['landmarks'].items()}))
NO_SAVE = True
