"""Package a finished character's head data as a head profile, reusable by every outfit with the same head.

usage: blender -b PROJECT/work/weights/weighted.blend --python make_profile.py -- PROJECT/work/build_character.json OUT_DIR

The profile holds everything the build and the expressions need that belongs to the head mesh rather than the body:
component ids and eye/mouth points (expr-data/), the repaired face texture, crease pairs, the cleaned hair texture,
decals (fx/), and the head-space settings of build_character.json (profile.json, paths relative to the profile).
head_rest.npy keeps the head vertices in the profile frame; a new project with the same head is fitted to it
(polish/measure/measure.py) to get its `frame`.
"""
import json
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

HEAD_KEYS = ['hair', 'skull', 'hair_cavity_box', 'eye_white_fill', 'brow_overlay', 'jaw_round', 'face_fx',
             'crease', 'earring', 'head_texture_note']


def head_landmarks(cfg, head, M):
    """Face landmarks (for fitting other heads to this one) and the cheek-crease edge midpoints, in the profile frame."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('polish_locate', Path(__file__).resolve().parents[1] / 'face' / 'locate.py')
    loc = importlib.util.module_from_spec(spec); spec.loader.exec_module(loc)
    P = np.array([(M @ head.matrix_world @ v.co)[:] for v in head.data.vertices], np.float64)
    comps, bounds = loc.kit_parts(cfg['kit'], head.data)
    vcol, _, _ = loc.vertex_colours(head)
    found = loc.locate(P, comps, bounds, vcol)
    pairs = json.loads(Path(cfg['crease_pairs']).read_text())['pairs']
    prior = [[round(float(x), 5) for x in (P[a] + P[b]) / 2] for a, b in pairs]
    return {'landmarks': {k: [round(float(x), 5) for x in v] for k, v in found['landmarks'].items()}, 'crease_prior': prior,
            'roles_raw': found['roles']}


def main(cfg_path, out):
    cfg = json.loads(Path(cfg_path).read_text(encoding='utf-8'))
    out = Path(out)
    if out.exists():
        raise SystemExit(f'profile folder exists: {out}')
    for sub in ('expr-data', 'face', 'hair', 'fx'):
        (out / sub).mkdir(parents=True)

    def take(src, rel):
        shutil.copy2(src, out / rel)
        return rel

    missing = [k for k in ('eye_white_fill', 'crease', 'brow_overlay', 'jaw_round', 'face_fx', 'crease_pairs', 'head_texture', 'hair_texture') if k not in cfg]
    if missing:
        # a head with painted eyes, brows or a closed skull (人物2) has none of these: it is not a profile head; such a
        # head is used directly (measure finds its parts, see references/头部档案.md) and is not packed yet
        raise SystemExit('this build config lacks ' + ', '.join(missing) + ': only heads with separate eye, brow and crease '
                         'pieces (like the profile head) can be packed as a profile')
    prof = {k: json.loads(json.dumps(cfg[k])) for k in HEAD_KEYS if k in cfg}
    prof['head_affine'] = take(cfg['head_affine'], 'face/head_affine.npy')
    prof['crease_pairs'] = take(cfg['crease_pairs'], 'face/crease-pairs.json')
    prof['head_texture'] = take(cfg['head_texture'], 'face/head-basecolor' + Path(cfg['head_texture']).suffix)
    prof['hair_texture'] = take(cfg['hair_texture'], 'hair/hair-basecolor' + Path(cfg['hair_texture']).suffix)
    if cfg.get('hair_texture_clean'):
        prof['hair_texture_clean'] = take(cfg['hair_texture_clean'], 'hair/hair-basecolor-clean' + Path(cfg['hair_texture_clean']).suffix)
    comps = Path(cfg['eye_white_fill']['components']).parent
    for f in ('components.json', 'skin_boundaries.json', 'eye_points.json', 'points.npy', 'uvspots.json'):
        take(comps / f, f'expr-data/{f}')
    for f in ('overrides.json', 'roles.json'):          # hand-moved points and part roles, when the head has them
        if (comps / f).is_file():
            take(comps / f, f'expr-data/{f}')
    ew = prof['eye_white_fill']
    ew['components'] = 'expr-data/components.json'
    ew['boundaries'] = 'expr-data/skin_boundaries.json'
    ew.pop('out', None)
    prof['crease']['components'] = 'expr-data/components.json'
    fx = Path(cfg['face_fx']['dir'])
    for f in fx.iterdir():
        if f.is_file() and (f.suffix == '.png' or f.name == 'fx.json'):
            take(f, f'fx/{f.name}')
    prof['face_fx']['dir'] = 'fx'
    for k in ('brow_overlay', 'jaw_round', 'face_fx'):
        prof[k].pop('module', None)        # the skill's polish/face/ modules are used
    prof['head_collider'] = next(c for c in cfg['hair_colliders'] if c['bone'] == 'head')
    rep = Path(cfg['report_out'])
    if rep.is_file():
        prof['face_tone'] = json.loads(rep.read_text(encoding='utf-8')).get('faceTone')
    prof['lab_camera'] = {'center': [0.003, -0.08, 1.515], 'ortho_scale': 0.24}

    # head vertices in the profile frame, before any build step touches them
    fr = cfg.get('frame')
    M = Matrix.Identity(4)
    if fr:
        M = Matrix.Diagonal((1 / fr['s'],) * 3 + (1.0,)) @ Matrix.Translation(-Vector(fr['t']))
    head = bpy.data.objects['Head']
    hv = np.array([(M @ head.matrix_world @ v.co)[:] for v in head.data.vertices], np.float64)
    np.save(out / 'head_rest.npy', hv)
    prof.update(head_landmarks(cfg, head, M))
    prof['head_vertices'] = len(hv)
    prof['source'] = {'project': str(Path(cfg_path).resolve().parents[1].name), 'frame': fr}
    (out / 'profile.json').write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding='utf-8')
    print('PROFILE_OK ' + json.dumps({'out': str(out), 'head_vertices': len(hv),
                                      'files': sum(1 for _ in out.rglob('*') if _.is_file())}))


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:][:2])
