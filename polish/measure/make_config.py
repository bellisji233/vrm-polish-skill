"""Write work/build_character.json from a head profile and the body measurements.

usage: python3 make_config.py PROJECT_DIR PROFILE_DIR [--skin 3,5] [--cloth 2,4] [--metal] [--force]
  reads PROJECT_DIR/work/measure/measure.json (polish/measure/measure.py)
  --skin / --cloth  piece numbers from work/measure/零件.jpg to repaint as skin / to clear of skin colour
                    (the neck piece and cool-coloured garments with rare warm faces are chosen without them)
  --metal           paint the small pieces found around the neck base silver (a bead necklace)
  --force           overwrite an existing build_character.json (the old one is kept as build_character-<time>.json)
work/build_overrides.json (optional) holds hand-set values; it is merged over the generated config every time
(nested objects key by key; a key ending in "+" appends to the generated list, e.g. "region_paint": {"cloth+": [...]}).

Body values come from the measurements; head values from the profile; the rest are the defaults the two finished
outfits use. Outfit-specific repairs that need a look at the model first (belt bands, metal accessories, sleeve
shape fitting) are not switched on here; see references/配置说明.md.
"""
import argparse
import numpy as np
import json
import os
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('project'); ap.add_argument('profile')
ap.add_argument('--skin', default=''); ap.add_argument('--cloth', default=''); ap.add_argument('--metal', action='store_true'); ap.add_argument('--force', action='store_true')
ap.add_argument('--neck-widen', type=float, default=1.0, help='neck width factor from the proportion check against the three views')
a = ap.parse_args()
P, PR = Path(a.project).resolve(), Path(a.profile).resolve()
W = P / 'work'
# hand-set values that survive regeneration: work/build_overrides.json is merged over the generated config (nested
# objects key by key); a neck_widen factor there stands for --neck-widen. A regenerated config otherwise lost them
# (11-26: 人物2's mouth_open and neck width after the head was scaled)
OV = json.loads((W / 'build_overrides.json').read_text(encoding='utf-8')) if (W / 'build_overrides.json').is_file() else {}
if isinstance(OV.get('neck_widen'), dict) and 'factor' in OV['neck_widen'] and abs(a.neck_widen - 1.0) < 1e-3:
    a.neck_widen = float(OV['neck_widen']['factor'])
m = json.loads((W / 'measure' / 'measure.json').read_text(encoding='utf-8'))
prof = json.loads((PR / 'profile.json').read_text(encoding='utf-8'))
out = W / 'build_character.json'
if out.exists() and not a.force:
    raise SystemExit(f'{out} exists; pass --force to replace it')
new_head = m.get('new_head')
if prof.get('starter') and not new_head:
    raise SystemExit('the starter profile only serves new heads; the head was not identified (see work/measure/measure.json)')
if not m.get('same_head') and not new_head:
    raise SystemExit('the head is not the profile head: ' + m.get('head_note', f"fit error {m.get('head_fit_rms_mm')} mm"))
ab = lambda rel: str(PR / rel)

cfg = {'kit': os.environ.get('KIT') or str(P.parents[1]), 'rig': m['rig'], 'collection': m['collection']}
# head (profile)
for k in ('hair', 'skull', 'hair_cavity_box', 'eye_white_fill', 'brow_overlay', 'jaw_round', 'face_fx', 'crease', 'earring'):
    if k in prof:
        cfg[k] = json.loads(json.dumps(prof[k]))
for k in ('head_affine', 'crease_pairs', 'head_texture', 'hair_texture', 'hair_texture_clean'):
    if k in prof:
        cfg[k] = ab(prof[k])
ew = cfg['eye_white_fill']
ew['components'], ew['boundaries'] = ab(ew['components']), ab(ew['boundaries'])
ew['out'] = str(W / 'face' / 'head-basecolor-eyewhite.png')
cfg['crease']['components'] = ab(cfg['crease']['components'])
cfg['face_fx']['dir'] = ab(cfg['face_fx']['dir'])
if m.get('frame'):
    cfg['frame'] = m['frame']
if new_head:
    # another head: the profile's head settings apply in the face frame fitted on landmarks; everything that names
    # parts or vertices of the head, its texture and its hair placement come from this head (work/measure/)
    MD = W / 'measure'; rl = new_head['roles']
    comps_h = json.loads((MD / 'head-components.json').read_text())
    st = rl.get('structure', {})
    if st.get('iris_pieces', True):
        ew.update({'components': str(MD / 'head-components.json'), 'boundaries': str(MD / 'head-skin-boundaries.json'),
                   'sclera': [rl['sclera']['R'], rl['sclera']['L']], 'iris': rl['iris']['R'] + rl['iris']['L'],
                   'iris_main': [rl['iris_main']['R'], rl['iris_main']['L']], 'skin': rl['skin'],
                   'openings': {str(rl['sclera']['R']): rl['rim_loop_n']['R'], str(rl['sclera']['L']): rl['rim_loop_n']['L']}})
        if 'lid_fill' in ew:
            if st.get('lash_pieces', True):
                ew['lid_fill']['lash'] = [rl['upper_lash']['R'], rl['upper_lash']['L']]
            else:
                ew.pop('lid_fill')
    else:
        # iris painted on the eyeball: nothing hidden under a separate iris to paint in; the iris is cut into its own
        # layer so the gaze moves it over a white that stays (eyeball and its copies, see face/iris_layer.py)
        cfg.pop('eye_white_fill', None)
        cfg['iris_layer'] = {'eyes': {s_: [comps_h[rl['sclera'][s_]]] + [comps_h[c_] for c_ in rl.get('sclera_extra', {}).get(s_, [])]
                                      for s_ in ('R', 'L')},
                             'rims': {s_: rl['rim_vs'][s_] for s_ in ('R', 'L')}}
    if rl.get('crease', {}).get('R') is not None and rl['crease'].get('L') is not None:
        cfg['crease'] = {'components': str(MD / 'head-components.json'), 'pieces': {'R': rl['crease']['R'], 'L': rl['crease']['L']}}
    else:
        cfg.pop('crease', None)
    if not st.get('open_back', True):
        # a closed head: no cranium to add behind a face mask, no open jaw edge to round
        cfg.pop('skull', None); cfg.pop('jaw_round', None)
    if rl.get('brow'):
        cfg['brow_overlay']['seeds'] = [comps_h[rl['brow']['R']][0], comps_h[rl['brow']['L']][0]]
    else:
        cfg.pop('brow_overlay', None)                    # painted brows: no brow pieces to copy over the bangs
    cfg['crease_pairs'] = str(MD / 'crease-pairs.json')
    cfg['head_texture'] = str(MD / 'texture' / 'head-basecolor.png')
    cfg['hair_affine'] = str(MD / 'head_affine_own.npy')
    if new_head.get('hair_texture'):
        cfg['hair_texture'] = new_head['hair_texture']
    elif new_head.get('hair_packed'):
        cfg.pop('hair_texture', None)
    elif cfg.get('hair_texture') and Path(cfg['hair_texture']).is_file():
        print('  warning: no 4K hair image found in the assembly; hair_texture still points at the profile head')
    else:
        cfg.pop('hair_texture', None)
    cfg.pop('hair_texture_clean', None)
    # the profile's hair chains were set for its own (long) hair: on another head the chains start where the head is
    # widest, hair on the scalp stays with the head, and the springs stiffen for shorter strands (purple: 0.30 long)
    cfg['hair'] = dict(cfg['hair'], root='head_width', scalp_pin=[0.006, 0.014], length_physics={'ref': 0.30})
    if not rl.get('ear_side'):
        cfg.pop('earring', None)
    # face effects: drawn on this character's own face (work/fx, see face/fx_render.py and face/fx_cutout.py) when
    # they exist; otherwise the profile's, moved by this face's landmarks (they carry the profile's face with them)
    own_fx = W / 'fx' / 'fx.json'
    if cfg.get('face_fx') and own_fx.exists():
        cfg['face_fx'] = dict(cfg['face_fx'], dir=str(own_fx.parent))
        cfg['face_fx'].pop('warp', None)
    elif cfg.get('face_fx') and prof.get('landmarks') and m.get('frame'):
        fr_ = m['frame']; L1 = {k: (np.array(v) - np.array(fr_['t'])) / fr_['s'] for k, v in new_head['landmarks'].items()}
        L0 = {k: np.array(v) for k, v in prof['landmarks'].items()}
        def _lsq(a_, b_):                                 # b = s a + t, one axis
            a_, b_ = np.array(a_), np.array(b_); s_ = float(((a_ - a_.mean()) * (b_ - b_.mean())).sum() / ((a_ - a_.mean()) ** 2).sum())
            return s_, float(b_.mean() - s_ * a_.mean())
        eyes = [f'eye{k}{sd}' for k in ('Inner', 'Outer') for sd in ('R', 'L')]
        sx, tx = _lsq([L0[k][0] for k in eyes], [L1[k][0] for k in eyes])
        ez0, ez1 = np.mean([L0[k][2] for k in eyes]), np.mean([L1[k][2] for k in eyes])
        py = float(np.mean([L0[k][1] for k in eyes]))
        warp = {'eye': dict(sx=sx, tx=tx, sz=sx, tz=float(ez1 - sx * ez0), plane_y=py)}
        szc, tzc = _lsq([ez0, L0['noseTip'][2]], [ez1, L1['noseTip'][2]])
        warp['cheek'] = dict(sx=sx, tx=tx, sz=szc, tz=tzc, plane_y=py)
        smx, tmx = _lsq([L0['mouthR'][0], L0['mouthL'][0]], [L1['mouthR'][0], L1['mouthL'][0]])
        warp['mouth'] = dict(sx=smx, tx=tmx, sz=smx, tz=float(L1['mouth'][2] - smx * L0['mouth'][2]), plane_y=float(L0['mouth'][1]))
        kind = {'blush': 'cheek', 'mouth_cat': 'mouth', 'sweat': 'eye'}
        cfg['face_fx']['warp'] = {n_: {k_: round(v_, 5) for k_, v_ in warp[kind.get(n_, 'eye')].items()} for n_ in cfg['face_fx']['effects']}
cfg['assembly_blend'] = str(W / 'assembly.blend')

# body (measured)
springs = m.get('springs', [])
skirt = next((s for s in springs if s['kind'] == 'skirt'), None)
others = [s for s in springs if s is not skirt]
cfg['keep_meshes'] = [s['mesh'] for s in springs]
cfg['neck_loft'] = dict({'flare_front': 0.012, 'flare_side': 0.035, 'flare_back': 0.055, 'max_rise': 0.12, 'flare_power': 2.0,
                         'lift': 0.0006, 'around': 72, 'along': 14, 'ring_smooth': 3.0, 'color_smooth': 6.0, 'sink': 0.003,
                         'tone': 'jaw', 'ext': [0.004, 0.008, 0.012, 0.016, 0.02],
                         'ext_offset': [0.0004, 0.0004, 0.0003, 0.0001, -0.0005]}, **m['neck_loft'])
cfg['hair_colliders'] = [prof['head_collider']] + m['hair_colliders']
if abs(a.neck_widen - 1.0) > 1e-3:
    cfg['neck_widen'] = {'factor': a.neck_widen, 'z_from': m['neck']['front_collar_top'], 'ramp': round(0.02 * m.get('body_scale', 1.0), 4)}
cfg['finger_clean'] = m['finger_clean']
if skirt:
    cfg['skirt'] = {'mesh': skirt['mesh'], 'z_root': skirt['z_root'], 'bones': 3, 'angles': [0, 45, 90, 135, 180, -135, -90, -45],
                    'physics': {'stiffness': 2.2, 'gravityPower': 0.03, 'dragForce': 0.6, 'hitRadius': 0.016}}
if others:
    r = others[0]
    stem = r['mesh'].split('_', 2)[-1]
    cfg['ribbon'] = {'mesh': r['mesh'], 'bone_prefix': stem.capitalize(), 'chain_prefix': stem.lower(), 'parent': r['parent'],
                     'z_root': r['z_root'], 'bones': 2,
                     'physics': {'stiffness': 1.2, 'gravityPower': 0.1, 'dragForce': 0.5, 'hitRadius': 0.01}}
cfg['helper_bones'] = [{'name': 'WristHelper', 'source': 'hand', 'inner': ['lower_arm'], 'mode': 'band', 'half': 0.03, 'influence': 0.5}]
bare_forearms = not (m.get('sleeves') or {}).get('long', True)
if bare_forearms:
    # bare forearms turn along their length (roll bones), not only at the wrist band (人物2, 11-26)
    cfg['helper_bones'] = [{'name': 'ForearmTwist', 'source': 'hand', 'parent': 'lower_arm', 'mode': 'twist', 'count': 4, 'start': 0.1, 'band': 0.03}]
cfg['hand_skin'] = {'reach': 0.2, 'sigma': 12, 'broad': 0.12, 'detail': 0.6, 'neck': False}
if (m.get('hands') or {}).get('fused', True):
    # fingers webbed past 60 % of their first segment (or not measured): the fitted template hand replaces them
    cfg['template_hand'] = {'blend': str(W / 'hand' / 'template_hand.blend'), 'cut': 0.06}
    if bare_forearms:
        cfg['template_hand']['tone_from'] = 'forearm'      # bare forearms: the hand matches the forearm skin next to it
        cfg['template_hand']['cut'] = 0.025                # and joins it at the wrist, where bands and watches sit
elif bare_forearms:
    # the generated hand stays; its texture (palm often much darker than the back) is evened out to the forearm skin
    cfg['hand_skin']['tone_from'] = 'forearm'
sl = m['sleeves']
# cuff lining: skin-coloured faces of the top's material past the cuff are lining once the template hand has replaced
# the hand; a generated hand that stays is the same material and colour, and was deleted with the lining (11-26, purple)
if sl['long'] and sl['material'] and cfg.get('template_hand'):
    cfg['cuff_lining'] = {'material': sl['material'], 'min_abs_x': sl['min_abs_x'], 'grow': 1, 'neighbours': 12, 'shade': 0.85,
                          'delete': True, 'delete_min_abs_x': sl['delete_min_abs_x'], 'name': 'cuff'}
cfg['waist_blend'] = {'z': m['waist_blend']['z'], 'feather': 0.025, 'bin': 0.01, 'sectors': 16, 'smooth': 3, 'skirt': bool(skirt)}
if m.get('crotch'):
    cfg['crotch_blend'] = dict(m['crotch'], pelvis_min=0.3)

# mesh pieces
pieces = m['pieces']
num = lambda s: [int(x) for x in s.split(',') if x.strip()]
skin_n, cloth_n = set(num(a.skin)), set(num(a.cloth))
SKIN = {'sigma': 16, 'broad': 0.08, 'detail': 0.6, 'detail_clip': [0.88, 1.1]}
rp = {'skin': [], 'cloth': []}
names = []
for i, p in enumerate(pieces, 1):
    name = '_'.join(p['sites'][:2])
    if i in cloth_n or (p.get('auto') == 'cloth' and i not in skin_n):
        e = {'name': name, 'point': p['point'], 'warm': 0.03, 'keep_dark_below': 0.42, 'shade': 1.0, 'neighbours': 10}
        if sl['long'] and sl.get('min_abs_x'):
            e['abs_x'] = sl['min_abs_x']                    # stop at the cuffs: the hands past them are skin
        rp['cloth'].append(e); names.append(f'#{i} cloth')
        if p.get('band'):
            rp.setdefault('band', []).append({'name': name + '_belt', 'point': p['point'], 'axis': m['neck_loft']['axis'],
                                              'z_min': p['band']['z_min'], 'max_mean': 0.42, 'sectors': 36, 'pad': 0.003, 'to_top': True})
            names.append(f'#{i} belt band')
    elif i in skin_n or (p.get('auto') == 'skin' and i not in cloth_n):
        rp['skin'].append(dict({'name': name, 'point': p['point']}, **SKIN)); names.append(f'#{i} skin')
if a.metal and m.get('neck_accessory'):
    rp['metal'] = [{'name': 'necklace', 'box': m['neck_accessory']['box'], 'max_faces': 150}]; names.append('necklace metal')
cfg['region_paint'] = {k: v for k, v in rp.items() if v}
if not cfg['region_paint']:
    del cfg['region_paint']
    cfg['hand_skin']['neck'] = True

def _merge(dst, src):
    for k_, v_ in src.items():
        if k_.endswith('+') and isinstance(v_, list):     # "cloth+": [...] adds to the generated list
            dst.setdefault(k_[:-1], []).extend(v_)
        elif isinstance(v_, dict) and isinstance(dst.get(k_), dict):
            _merge(dst[k_], v_)
        else:
            dst[k_] = v_
_merge(cfg, {k_: v_ for k_, v_ in OV.items() if k_ != 'neck_widen'})
cfg['spring_config_out'] = str(W / 'spring-config.json')
cfg['report_out'] = str(W / 'build-report.json')
cfg['output_blend'] = str(W / 'character-built.blend')
cfg['generated'] = {'by': 'polish/measure/make_config.py', 'profile': str(PR), 'at': time.strftime('%Y-%m-%d %H:%M'),
                    'pieces': names, 'overrides': sorted(OV)}
if out.exists():
    out.rename(W / f'build_character-{time.strftime("%m%d%H%M")}.json')
(W / 'face').mkdir(exist_ok=True)
out.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf-8')
print('CONFIG_OK ' + str(out))
print('  frame', m.get('frame'), '| neck', m['neck_loft'], '| fingers', m['finger_clean']['x_min'], '| waist', m['waist_blend']['z'])
print('  springs', [(s['mesh'], s['kind'], s['z_root']) for s in springs], '| long sleeves', sl['long'])
print('  pieces', names or 'none', '| see work/measure/零件.jpg for the others')
if m.get('neck_accessory'):
    print(f"  {m['neck_accessory']['pieces']} small pieces around the neck base (necklace?): region_paint.metal box {m['neck_accessory']['box']}")
