# Shoulder corrective shapes (11-18, user: the shoulder folds when the arm is raised).
# Linear blend skinning moves a vertex shared by chest and arm along the chord between the two bone transforms, so the
# shoulder collapses: the top of the shoulder pinches when the arm goes up, the armpit caves in when it goes down.
# Dual-quaternion skinning moves it along the arc instead (no volume loss). For two key poses per arm (raised 70 deg,
# lowered 75 deg from the T-pose) this writes the difference DQS - LBS back into rest space as morph targets; the page
# blends them in by the arm's elevation (arm-avoid.js), so the shoulder keeps its volume at those angles.
# Only the shoulder region changes (vertices whose weight is split between the arm and the body).
# usage: python3 shoulder_fix.py IN.vrm OUT.vrm [up=70] [down=75] [down]   (the lowered-arm shape only with the 5th argument)
import json, math, struct, sys
import numpy as np

src, dst = sys.argv[1], sys.argv[2]
UP = math.radians(float(sys.argv[3]) if len(sys.argv) > 3 else 70)
DOWN = math.radians(float(sys.argv[4]) if len(sys.argv) > 4 else 75)
b = open(src, 'rb').read()
n = struct.unpack_from('<I', b, 12)[0]; J = json.loads(b[20:20 + n]); o = 20 + n
binlen = struct.unpack_from('<I', b, o)[0]; BIN = bytearray(b[o + 8:o + 8 + binlen])

def acc(i):
    a = J['accessors'][i]; v = J['bufferViews'][a['bufferView']]
    k = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a['componentType']]
    off = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    data = np.frombuffer(bytes(BIN[off:off + a['count'] * k * np.dtype(dt).itemsize]), dt).reshape(a['count'], k)
    if a.get('normalized') and dt != np.float32: data = data / np.iinfo(dt).max
    return data.copy()
def add_vec3(arr):
    arr = np.ascontiguousarray(arr, np.float32); data = arr.tobytes()
    off = len(BIN); off += (4 - off % 4) % 4; BIN.extend(b'\0' * (off - len(BIN))); BIN.extend(data)
    J['bufferViews'].append(dict(buffer=0, byteOffset=off, byteLength=len(data)))
    J['accessors'].append(dict(bufferView=len(J['bufferViews']) - 1, componentType=5126, count=len(arr), type='VEC3',
                               min=arr.min(0).tolist(), max=arr.max(0).tolist()))
    return len(J['accessors']) - 1
def add_zero(count):
    J['accessors'].append(dict(componentType=5126, count=count, type='VEC3', min=[0, 0, 0], max=[0, 0, 0]))   # no bufferView = zeros
    return len(J['accessors']) - 1

def rotmat(axis, ang):
    x, y, z = axis / np.linalg.norm(axis); c, s = math.cos(ang), math.sin(ang); C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s], [y * x * C + z * s, c + y * y * C, y * z * C - x * s], [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])

hb = J['extensions']['VRMC_vrm']['humanoid']['humanBones']
def subtree(ni):
    out = {ni}; stack = [ni]
    while stack:
        for c in J['nodes'][stack.pop()].get('children', []): out.add(c); stack.append(c)
    return out
WITH_DOWN = len(sys.argv) > 5 and sys.argv[5] == 'down'
KEYS = []   # (expression name, side, angle, bone, axis, materials)
KNEE = math.radians(110)
ELBOW = math.radians(110)
LEG_MATS = {'Material_lower_body'}
for s, sg in (('left', 1), ('right', -1)):
    KEYS.append((f'corrShoulderUp{s[0].upper()}', s, sg * UP, 'UpperArm', (0, 0, 1.0), None))
    # 11-18: knees in a deep squat (user: the knee shape looked wrong when crouching); flexion about +X moves the foot back
    KEYS.append((f'corrKnee{s[0].upper()}', s, KNEE, 'LowerLeg', (1.0, 0, 0), LEG_MATS))
    # 11-26: elbows (user: the elbow disappears when the arm bends; linear skinning rounds the bent elbow off and
    # pinches its inside); flexion brings the forearm forward, about +Y with the left arm along +X
    KEYS.append((f'corrElbow{s[0].upper()}', s, -sg * ELBOW, 'LowerArm', (0, 1.0, 0), None))
    if WITH_DOWN: KEYS.append((f'corrShoulderDown{s[0].upper()}', s, -sg * DOWN, 'UpperArm', (0, 0, 1.0), None))
# 11-18: the lowered-arm shape is off by default: on the forest outfit it held the capelet up like a shoulder pad in the
# most common pose (arms hanging); add "down" as a 5th argument to write it
AX = np.array([0, 0, 1.0])
BODY_MATS = {'Material_upper_body', 'Material_hand_tpl'}
RADIUS = {'UpperArm': (0.10, 0.20), 'LowerLeg': (0.08, 0.16), 'LowerArm': (0.05, 0.10)}   # full effect within R0 of the joint, none beyond R1
LIMB = {'UpperArm': ['UpperArm', 'LowerArm', 'Shoulder', 'upperChest', 'chest'], 'LowerLeg': ['UpperLeg', 'LowerLeg'], 'LowerArm': ['UpperArm', 'LowerArm']}

report = {}
mesh_nodes = {}
for ni, nd in enumerate(J['nodes']):
    if 'mesh' in nd and 'skin' in nd: mesh_nodes.setdefault(nd['mesh'], []).append(ni)
new_binds = {k[0]: [] for k in KEYS}
for mi, nodes_ in mesh_nodes.items():
    mesh = J['meshes'][mi]; skin = J['skins'][J['nodes'][nodes_[0]]['skin']]; joints = skin['joints']
    mats = [J['materials'][p['material']]['name'] for p in mesh['primitives'] if 'material' in p]
    if any(('hair' in m.lower() or m in ('Material_head', 'Material_scalp')) for m in mats): continue
    if any(J['nodes'][n].get('name', '').startswith('Spring_') for n in nodes_): continue
    IBM = acc(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
    per_prim = []
    touched = False
    for p in mesh['primitives']:
        P = acc(p['attributes']['POSITION']).astype(float)
        # draped pieces (the forest capelet is on the accessories material) should follow the arm like cloth; the arc
        # kept them up like a shoulder pad when the arm hangs, so only the body and sleeves are corrected
        mname = J['materials'][p['material']]['name']
        if mname not in BODY_MATS and mname not in LEG_MATS:
            per_prim.append([np.zeros_like(P) for _ in KEYS]); continue
        JN = acc(p['attributes']['JOINTS_0']).astype(int); WT = acc(p['attributes']['WEIGHTS_0']).astype(float)
        WT = WT / np.maximum(WT.sum(1, keepdims=True), 1e-9)
        deltas = []
        for name, side, ang, bone, axis, mats in KEYS:
            if (mats or BODY_MATS) and mname not in (mats or BODY_MATS):
                deltas.append(np.zeros_like(P)); continue
            AXK = np.array(axis)
            arm = subtree(hb[side + bone]['node'])
            in_arm = np.isin(np.array(joints)[JN], list(arm))
            W = (WT * in_arm).sum(1)
            sp = np.linalg.inv(IBM[joints.index(hb[side + bone]['node'])])[:3, 3]
            R = rotmat(AXK, ang); v = P - sp
            Q = v + W[:, None] * (v @ (R - np.eye(3)).T)                      # LBS: chord
            D = np.empty_like(v)
            for i in np.where((W > 0.02) & (W < 0.98))[0]: D[i] = rotmat(AXK, W[i] * ang) @ v[i]   # DQS: arc
            d = np.zeros_like(v)
            # 11-18: only near the joint and only on the limb itself. On the outfits the long skirt hem and the shorts
            # cuffs carry part of their weight on the lower leg far from the knee; the arc moved them up to 5.7 cm and
            # the knees looked wrong in a squat.
            near = np.linalg.norm(v, axis=1); R0, R1 = RADIUS[bone]
            fall = np.clip((R1 - near) / (R1 - R0), 0, 1); fall = fall * fall * (3 - 2 * fall)
            dom_node = np.array(joints)[JN[np.arange(len(JN)), np.argmax(WT, 1)]]
            limb = np.isin(dom_node, [hb[side + b_]['node'] for b_ in LIMB[bone] if (side + b_) in hb] + [hb[b_]['node'] for b_ in LIMB[bone] if b_ in hb])
            if bone == 'LowerArm':                          # forearm twist bones (children of the lower arm) are forearm too
                limb |= np.isin(dom_node, list(arm - subtree(hb[side + 'Hand']['node'])))
            for i in np.where((W > 0.02) & (W < 0.98) & (fall > 0) & limb)[0]:
                A = (1 - W[i]) * np.eye(3) + W[i] * R
                d[i] = np.linalg.solve(A, D[i] - Q[i]) * fall[i]
            deltas.append(d)
            if np.abs(d).max() > 1e-5: touched = True
        per_prim.append(deltas)
    if not touched: continue
    base = len(mesh['primitives'][0].get('targets', []))
    for p, deltas in zip(mesh['primitives'], per_prim):
        tg = p.setdefault('targets', [])
        assert len(tg) == base
        for d in deltas: tg.append({'POSITION': add_vec3(d) if np.abs(d).max() > 1e-6 else add_zero(len(d))})
    ex = mesh.setdefault('extras', {}); names = ex.setdefault('targetNames', [f't{i}' for i in range(base)])
    names += [k[0] for k in KEYS]
    if 'weights' in mesh: mesh['weights'] += [0.0] * len(KEYS)
    for k, (name, *_rest) in enumerate(KEYS):
        for ni in nodes_: new_binds[name].append(dict(node=ni, index=base + k, weight=1.0))
    report[mesh.get('name', mi)] = round(float(max(np.abs(d).max() for dd in per_prim for d in dd)) * 1000, 1)
cus = J['extensions']['VRMC_vrm']['expressions'].setdefault('custom', {})
for name, binds in new_binds.items():
    if binds: cus[name] = dict(morphTargetBinds=binds, isBinary=False, overrideBlink='none', overrideMouth='none', overrideLookAt='none')
BIN.extend(b'\0' * ((4 - len(BIN) % 4) % 4)); J['buffers'][0]['byteLength'] = len(BIN)
js = json.dumps(J, ensure_ascii=False, separators=(',', ':')).encode(); js += b' ' * ((4 - len(js) % 4) % 4)
open(dst, 'wb').write(b'glTF' + struct.pack('<II', 2, 12 + 8 + len(js) + 8 + len(BIN)) + struct.pack('<I', len(js)) + b'JSON' + js + struct.pack('<I', len(BIN)) + b'BIN\0' + BIN)
print('SHOULDER_OK', dst, 'max delta mm per mesh', json.dumps(report, ensure_ascii=False))
