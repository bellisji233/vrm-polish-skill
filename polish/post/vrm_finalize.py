# Finish an exported VRM 1.0 for live driving (the kit's export is the input; nothing else is changed):
#  1. override modes: the kit writes 'block' for every emotion, so any emotion weight above 0 switches blinking,
#     mouth shapes and gaze off; face tracking sends small emotion values all the time. Modes checked by eye.
#  2. ARKit 52 (perfect sync): 47 are authored shape keys; eyeBlink, jawOpen, mouthFunnel, mouthPucker and
#     browInnerUp reuse existing morphs. All of them override nothing, since trackers drive them together.
#  3. gaze: the four VRM look expressions are built from the per-eye eyeLook shapes; lookAt uses expressions with
#     ranges in degrees, its origin between the eyes.
#  6. Crease_L / Crease_R (double-eyelid lines): fade to CREASE_ALPHA as the eye closes.
#  5. anime face effects (face_fx.py): FX_<name> materials start fully transparent; expression <name> fades them in
#     (eye_x also closes the eyes).
#  4. BrowOverlay (brows over the bangs, see brow_overlay.py): the brows are nearly hair-coloured, so the copy is
#     tinted darker (BROW_COLOR, checked by eye: 0.75 still blends into the bangs, 0.45 too heavy), blended, late in the queue.
#  8. cut iris layer (face/iris_layer.py): the gaze shifts each eye's iris texture (textureTransformBinds from
#     expr_build's gazeUV), the texture clamped at its transparent edge; the offsets' range per material goes into
#     extras.vrmPolish.gazeUV so the player can keep stacked gaze channels within one full look.
#  7. mouth width (user, 11-20: the smile and the sad mouth are the widest the mouth gets): every morph target's motion
#     of the two visible mouth corners goes into extras.vrmPolish.mouthWidth, so the player can add mouthNarrow when
#     tracked shapes combine past that width (each shape alone is limited at build time; sums are not).
# usage: python3 vrm_finalize.py IN.vrm OUT.vrm [EXPR_REPORT.json]
import json, struct, sys
import numpy as np

MODES = {  # name: (overrideBlink, overrideMouth, overrideLookAt)
    'happy': ('none', 'none', 'none'), 'angry': ('none', 'none', 'none'), 'sad': ('none', 'none', 'none'),
    'relaxed': ('none', 'none', 'none'),
    'surprised': ('blend', 'blend', 'none'),          # raised lids do not close fully under blink; O mouth + aa too tall
    'happy_eye': ('none', 'none', 'none'), 'angry_eye': ('none', 'none', 'none'), 'sad_eye': ('none', 'none', 'none'),
    'relaxed_eye': ('none', 'none', 'none'), 'surprised_eye': ('blend', 'none', 'none'),
    'happy_mouth': ('none', 'none', 'none'), 'angry_mouth': ('none', 'none', 'none'), 'sad_mouth': ('none', 'none', 'none'),
    'relaxed_mouth': ('none', 'none', 'none'), 'surprised_mouth': ('none', 'blend', 'none'), 'laugh_mouth': ('none', 'blend', 'none'),
    'blink_smile': ('block', 'none', 'none'), 'blink_smile_L': ('block', 'none', 'none'), 'blink_smile_R': ('block', 'none', 'none'),
    'happy_open': ('block', 'blend', 'none'),          # eyes already closed; blink on top breaks the lash line
    'eye_x': ('block', 'none', 'block'), 'eye_jito': ('blend', 'none', 'none'), 'mouth_cat': ('none', 'block', 'none'),
    'mouthNarrow': ('none', 'none', 'none'),
}
ARKIT = [f'eye{a}{s}' for s in ('Left', 'Right') for a in ('Blink', 'LookDown', 'LookIn', 'LookOut', 'LookUp', 'Squint', 'Wide')] + \
    ['jawForward', 'jawLeft', 'jawRight', 'jawOpen', 'mouthClose', 'mouthFunnel', 'mouthPucker', 'mouthLeft', 'mouthRight'] + \
    [f'mouth{a}{s}' for a in ('Smile', 'Frown', 'Dimple', 'Stretch', 'Press', 'LowerDown', 'UpperUp') for s in ('Left', 'Right')] + \
    ['mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper', 'browDownLeft', 'browDownRight', 'browInnerUp',
     'browOuterUpLeft', 'browOuterUpRight', 'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight', 'noseSneerLeft', 'noseSneerRight', 'tongueOut']
assert len(ARKIT) == 52
REUSE = {'eyeBlinkLeft': ('preset', 'blinkLeft'), 'eyeBlinkRight': ('preset', 'blinkRight'), 'jawOpen': ('preset', 'aa'),
         'mouthFunnel': ('preset', 'oh'), 'mouthPucker': ('preset', 'ou'), 'browInnerUp': ('custom', 'brow_sad')}
LOOK = {'lookLeft': ('eyeLookOutLeft', 'eyeLookInRight'), 'lookRight': ('eyeLookInLeft', 'eyeLookOutRight'),
        'lookUp': ('eyeLookUpLeft', 'eyeLookUpRight'), 'lookDown': ('eyeLookDownLeft', 'eyeLookDownRight')}
RANGE = dict(horizontal=30.0, vertical=25.0)          # degrees of gaze for full weight
BROW_COLOR, BROW_ALPHA, BROW_QUEUE = (0.68, 0.55, 0.55), 0.55, 9    # user, 11-13: 0.6 / 0.9 too heavy

src, dst = sys.argv[1], sys.argv[2]
b = open(src, 'rb').read()
magic, ver, total = struct.unpack('<III', b[:12]); assert magic == 0x46546C67 and ver == 2
jlen, jtype = struct.unpack('<II', b[12:20]); assert jtype == 0x4E4F534A
j = json.loads(b[20:20 + jlen]); rest = b[20 + jlen:]
vrm = j['extensions']['VRMC_vrm']; ex = vrm['expressions']; pre, cus = ex.setdefault('preset', {}), ex.setdefault('custom', {})
modes = dict(MODES, **{n: ('none', 'none', 'none') for n in ARKIT})
for name, (g, srcname) in REUSE.items():              # reuse existing morphs
    cus[name] = dict(morphTargetBinds=[dict(x) for x in (pre if g == 'preset' else cus)[srcname]['morphTargetBinds']], isBinary=False)
missing = [n for n in ARKIT if n not in cus]
rep = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {}
_mi = {m.get('name'): i for i, m in enumerate(j.get('materials', []))}
gaze_uv = {}
for name, g in (rep.get('gazeUV') or {}).items():
    if name in cus and g['material'] in _mi:
        cus[name]['textureTransformBinds'] = [dict(material=_mi[g['material']], scale=[1.0, 1.0], offset=list(g['offset']))]
        r_ = gaze_uv.setdefault(g['material'], dict(min=[0.0, 0.0], max=[0.0, 0.0]))
        for k in (0, 1):
            r_['min'][k] = min(r_['min'][k], g['offset'][k]); r_['max'][k] = max(r_['max'][k], g['offset'][k])
if gaze_uv:
    j.setdefault('extras', {}).setdefault('vrmPolish', {})['gazeUV'] = gaze_uv
    for m in j['materials']:
        if m.get('name') in gaze_uv:                # clamped: the shifted texture shows its transparent edge, not a repeat
            texs = [m.get('pbrMetallicRoughness', {}).get('baseColorTexture')] + [v for k, v in m.get('extensions', {}).get('VRMC_materials_mtoon', {}).items() if k.endswith('Texture') and isinstance(v, dict)]
            for t in texs:
                if t and 'index' in t:
                    j.setdefault('samplers', []).append(dict(magFilter=9729, minFilter=9729, wrapS=33071, wrapT=33071))
                    j['textures'][t['index']]['sampler'] = len(j['samplers']) - 1
for name, parts in LOOK.items():
    pre[name] = dict(morphTargetBinds=[dict(x) for p in parts for x in cus[p]['morphTargetBinds']], isBinary=False,
                     overrideBlink='none', overrideMouth='none', overrideLookAt='none')
    tt = [dict(x) for p in parts for x in cus[p].get('textureTransformBinds', [])]
    if tt: pre[name]['textureTransformBinds'] = tt
changed = 0
for group in (pre, cus):
    for name, e in group.items():
        if name in modes:
            e.update(zip(('overrideBlink', 'overrideMouth', 'overrideLookAt'), modes[name])); changed += 1
# lookAt origin between the eyes, in the head bone's local space
def trs(n):
    if 'matrix' in n: return np.array(n['matrix'], float).reshape(4, 4).T
    t = np.array(n.get('translation', [0, 0, 0]), float); x, y, z, w = n.get('rotation', [0, 0, 0, 1]); s = np.array(n.get('scale', [1, 1, 1]), float)
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4); M[:3, :3] = R * s; M[:3, 3] = t; return M
parent = {c: i for i, n in enumerate(j['nodes']) for c in n.get('children', [])}
def world(i):
    M = trs(j['nodes'][i])
    while i in parent: i = parent[i]; M = trs(j['nodes'][i]) @ M
    return M
hb = vrm['humanoid']['humanBones']
Hw = world(hb['head']['node'])
if 'leftEye' in hb and 'rightEye' in hb:
    mid = 0.5 * (world(hb['leftEye']['node'])[:3, 3] + world(hb['rightEye']['node'])[:3, 3])
    off = (np.linalg.inv(Hw) @ np.r_[mid, 1])[:3]
else:
    off = np.array(vrm.get('lookAt', {}).get('offsetFromHeadBone', [0, 0.06, 0]))
vrm['lookAt'] = dict(type='expression', offsetFromHeadBone=[round(float(v), 4) for v in off],
                     rangeMapHorizontalInner=dict(inputMaxValue=RANGE['horizontal'], outputScale=1.0),
                     rangeMapHorizontalOuter=dict(inputMaxValue=RANGE['horizontal'], outputScale=1.0),
                     rangeMapVerticalDown=dict(inputMaxValue=RANGE['vertical'], outputScale=1.0),
                     rangeMapVerticalUp=dict(inputMaxValue=RANGE['vertical'], outputScale=1.0))
# 11-17: the template hands get the face material's colour factors and toon settings (the exporter wrote base 0.8,
# shade 0.512 and emission 1 x strength 0 from Blender's default node values, so the hand read darker than the neck)
_mats = {m.get('name'): m for m in j.get('materials', [])}
if 'Material_hand_tpl' in _mats and 'Material_head' in _mats:
    _h, _f = _mats['Material_hand_tpl'], _mats['Material_head']
    _h.setdefault('pbrMetallicRoughness', {})['baseColorFactor'] = list(_f.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1]))
    _h['emissiveFactor'] = [0.0, 0.0, 0.0]
    _hm = _h.setdefault('extensions', {}).setdefault('VRMC_materials_mtoon', {}); _fm = _f.get('extensions', {}).get('VRMC_materials_mtoon', {})
    for k_, v_ in _fm.items():
        if not k_.endswith('Texture'): _hm[k_] = v_
brow = 0
for m in j.get('materials', []):
    if m.get('name') == 'BrowOverlay':
        m['alphaMode'] = 'BLEND'; pbr = m.setdefault('pbrMetallicRoughness', {}); pbr['baseColorFactor'] = [*BROW_COLOR, BROW_ALPHA]
        mt = m.setdefault('extensions', {}).setdefault('VRMC_materials_mtoon', {}); mt['renderQueueOffsetNumber'] = BROW_QUEUE; mt['shadeColorFactor'] = [round(c * 0.8, 3) for c in BROW_COLOR]; mt['transparentWithZWrite'] = False
        brow += 1
# painted eye cut into layers (face/iris_layer.py): the lid layer is an opaque cut-out (drawn with the head, depth
# written), the iris disc behind it a blended layer drawn after it, so the painted lids cover the iris when it moves
for m in j.get('materials', []):
    if m.get('name') == 'EyeLid':
        m['alphaMode'] = 'MASK'; m['alphaCutoff'] = 0.5
        mt = m.setdefault('extensions', {}).setdefault('VRMC_materials_mtoon', {}); mt['renderQueueOffsetNumber'] = 0; mt['transparentWithZWrite'] = False
    elif m.get('name', '').startswith('EyeIris'):
        m['alphaMode'] = 'BLEND'
        mt = m.setdefault('extensions', {}).setdefault('VRMC_materials_mtoon', {}); mt['renderQueueOffsetNumber'] = 1; mt['transparentWithZWrite'] = False
fx = {}
for mi, m in enumerate(j.get('materials', [])):
    nm = m.get('name', '')
    if nm.startswith('FX_'):
        m['alphaMode'] = 'BLEND'; pbr = m.setdefault('pbrMetallicRoughness', {}); f = pbr.get('baseColorFactor', [1, 1, 1, 1]); f[3] = 0.0; pbr['baseColorFactor'] = f
        mt = m.setdefault('extensions', {}).setdefault('VRMC_materials_mtoon', {}); mt['transparentWithZWrite'] = False; mt['renderQueueOffsetNumber'] = 5
        name = nm[3:]
        bind = dict(material=mi, type='color', targetValue=[f[0], f[1], f[2], 1.0])
        if name in cus:                        # a modelled expression of the same name (eye_x closes the eyes and hides
            cus[name].setdefault('materialColorBinds', []).append(bind)   # the lashes, mouth_cat shapes the lips): add the decal
        else:
            cus[name] = dict(morphTargetBinds=[], materialColorBinds=[bind], isBinary=False,
                             overrideBlink='none', overrideMouth='none', overrideLookAt='none')
        fx[name] = mi
# 11-18: the user's happy references all blush; happy and happy_open bring part of the blush decal with them
FX_WITH = {'happy': ('blush', 0.5), 'happy_open': ('blush', 0.6)}
for ename, (fname, amt) in FX_WITH.items():
    e = pre.get(ename) or cus.get(ename); mi = fx.get(fname)
    if e is None or mi is None: continue
    f = j['materials'][mi]['pbrMetallicRoughness']['baseColorFactor']
    e.setdefault('materialColorBinds', []).append(dict(material=mi, type='color', targetValue=[f[0], f[1], f[2], amt]))
CREASE_ALPHA = 0.15                    # user, 11-13: 0.35 still too dark
cm = {m.get('name'): i for i, m in enumerate(j.get('materials', [])) if m.get('name', '').startswith('Crease_')}
for nm, mi in cm.items():
    m = j['materials'][mi]; m['alphaMode'] = 'BLEND'
    m.setdefault('extensions', {}).setdefault('VRMC_materials_mtoon', {})['transparentWithZWrite'] = False
closing = {'blink': 'LR', 'blinkLeft': 'L', 'blinkRight': 'R', 'eyeBlinkLeft': 'L', 'eyeBlinkRight': 'R', 'blink_smile': 'LR',
           'blink_smile_L': 'L', 'blink_smile_R': 'R', 'happy_open': 'LR', 'eye_x': 'LR'}
ncrease = 0
for ename, sides in closing.items():
    e = pre.get(ename) or cus.get(ename)
    if not e: continue
    for sd in sides:
        mi = cm.get('Crease_' + sd)
        if mi is None: continue
        f = j['materials'][mi].get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])
        e.setdefault('materialColorBinds', []).append(dict(material=mi, type='color', targetValue=[f[0], f[1], f[2], CREASE_ALPHA])); ncrease += 1
mouth_meta = None
if rep:
    corners = rep.get('mouthCornersWorld'); lim = (rep.get('mouthWidthLimit') or {}).get('limit_over_rest')
    if corners and lim:
        CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}; NC = {'SCALAR': 1, 'VEC3': 3}
        binb = rest[8:8 + struct.unpack('<I', rest[:4])[0]]
        def acc(i):
            a = j['accessors'][i]; nc = NC[a['type']]; dt = CT[a['componentType']]
            if 'bufferView' in a:
                v = j['bufferViews'][a['bufferView']]
                r = np.frombuffer(binb, dt, a['count'] * nc, v.get('byteOffset', 0) + a.get('byteOffset', 0)).reshape(a['count'], nc).copy()
            else:
                r = np.zeros((a['count'], nc), dt)
            if 'sparse' in a:
                sp = a['sparse']; iv = j['bufferViews'][sp['indices']['bufferView']]; vv = j['bufferViews'][sp['values']['bufferView']]
                ia = np.frombuffer(binb, CT[sp['indices']['componentType']], sp['count'], iv.get('byteOffset', 0) + sp['indices'].get('byteOffset', 0))
                r[ia] = np.frombuffer(binb, dt, sp['count'] * nc, vv.get('byteOffset', 0) + sp['values'].get('byteOffset', 0)).reshape(-1, nc)
            return r
        cg = [np.array([c[0], c[2], -c[1]]) for c in corners]       # Blender (z up) -> glTF (y up)
        best = None
        for m in j['meshes']:
            names = (m.get('extras') or {}).get('targetNames')
            if not names or 'EA_mouthNarrow' not in names: continue
            for pr in m['primitives']:
                P = acc(pr['attributes']['POSITION']).astype(float)
                ii = [int(np.argmin(np.linalg.norm(P - c, axis=1))) for c in cg]
                err = max(float(np.linalg.norm(P[i] - c)) for i, c in zip(ii, cg))
                if best is None or err < best[0]: best = (err, m, pr, ii, P)
        if best and best[0] < 5e-4:
            err, m, pr, ii, P = best
            names = m['extras']['targetNames']; iR, iL = sorted(ii, key=lambda i: P[i, 0])
            dx = {}
            for ti, t in enumerate(pr.get('targets', [])):
                if 'POSITION' not in t: continue
                D = acc(t['POSITION'])
                w = float(D[iL, 0] - D[iR, 0])
                if abs(w) > 1e-6: dx[names[ti]] = round(w, 7)
            rest_w = float(P[iL, 0] - P[iR, 0])
            mouth_meta = dict(rest=round(rest_w, 7), limit=round(rest_w * lim, 7), narrow='EA_mouthNarrow', dx=dx)
            j.setdefault('extras', {}).setdefault('vrmPolish', {})['mouthWidth'] = mouth_meta
js = json.dumps(j, ensure_ascii=False, separators=(',', ':')).encode('utf-8'); js += b' ' * ((4 - len(js) % 4) % 4)
out = struct.pack('<III', magic, ver, 12 + 8 + len(js) + len(rest)) + struct.pack('<II', len(js), 0x4E4F534A) + js + rest
open(dst, 'wb').write(out)
print('FINALIZE_OK crease', ncrease, 'fx', sorted(fx), 'browOverlay', brow, 'modes', changed, 'arkit', sum(n in cus for n in ARKIT), 'missing', missing, 'lookAt offset', vrm['lookAt']['offsetFromHeadBone'],
      'mouthWidth', None if not mouth_meta else dict(rest=mouth_meta['rest'], limit=mouth_meta['limit'], shapes=len(mouth_meta['dx'])), 'gazeUV', gaze_uv or None)
