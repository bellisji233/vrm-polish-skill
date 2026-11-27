# Skirt physics tuning on a finished VRM (11-18, user: in the IRIS OUT dance the forest legs go through the long skirt and
# at the end the whole front of the skirt flips up as one board).
#  - lower-leg capsules join the skirt's leg collider group (only the thighs had colliders: knee lifts and kicks went
#    straight through the long skirt)
#  - SkirtRoot rotation constraints scaled down (the front roots copied up to 60% of the thigh rotation, so a kick lifted
#    the whole front panel rigidly)
#  - optional chain stiffness / gravity / drag / joint radius for the skirt chains
# usage: python3 spring_tune.py IN.vrm OUT.vrm '{"rootScale":0.5,"shin":0.055,"stiffness":1.2,"gravity":0.1,"drag":0.5,"hit":0.02}'
import json, struct, sys
import numpy as np

src, dst = sys.argv[1], sys.argv[2]
opt = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
b = open(src, 'rb').read()
n = struct.unpack_from('<I', b, 12)[0]; J = json.loads(b[20:20 + n]); rest = b[20 + n:]
nodes = J['nodes']; sb = J['extensions']['VRMC_springBone']
name_idx = {nd.get('name'): i for i, nd in enumerate(nodes)}
report = {}

if opt.get('shin'):
    grp = next(g for g in sb['colliderGroups'] if g['name'] == 'Skirt/legs')
    for s in ('L', 'R'):
        ln = name_idx.get(f'lower_leg.{s}'); fn = name_idx.get(f'foot.{s}')
        if ln is None or fn is None: continue
        L = float(np.linalg.norm(nodes[fn].get('translation', [0, 0, 0])))
        # raw leg bones point down their local +Y (the thigh capsule is offset 0.04 -> 0.36 along +Y)
        sb['colliders'].append(dict(node=ln, shape=dict(capsule=dict(offset=[0, 0.0, 0], radius=opt['shin'], tail=[0, L * 0.85, 0]))))
        grp['colliders'].append(len(sb['colliders']) - 1)
        if opt.get('knee'):
            sb['colliders'].append(dict(node=ln, shape=dict(sphere=dict(offset=[0, 0, 0], radius=opt['knee']))))
            grp['colliders'].append(len(sb['colliders']) - 1)
    report['legColliders'] = len(grp['colliders'])
if opt.get('thigh'):
    for c in sb['colliders']:
        if nodes[c['node']].get('name', '').startswith('upper_leg.') and 'capsule' in c['shape']:
            c['shape']['capsule']['radius'] = opt['thigh']
if 'rootScale' in opt:
    k = 0
    for nd in nodes:
        con = nd.get('extensions', {}).get('VRMC_node_constraint', {}).get('constraint', {}).get('rotation')
        if con and nd.get('name', '').startswith('SkirtRoot'):
            con['weight'] = round(con['weight'] * opt['rootScale'], 4); k += 1
    report['skirtRoots'] = k
for spring in sb['springs']:
    if not spring.get('name', '').startswith('skirt_'): continue
    nj = len(spring['joints'])
    for ji, j in enumerate(spring['joints']):
        # stiffTip: the last joint's stiffness as a share of the root's (cloth is stiffer at the waistband)
        if 'stiffness' in opt: j['stiffness'] = round(opt['stiffness'] * (1 - (1 - opt.get('stiffTip', 1)) * ji / max(1, nj - 1)), 4)
        if 'gravity' in opt: j['gravityPower'] = opt['gravity']
        if 'drag' in opt: j['dragForce'] = opt['drag']
        if 'hit' in opt: j['hitRadius'] = opt['hit']
js = json.dumps(J, ensure_ascii=False, separators=(',', ':')).encode('utf-8'); js += b' ' * ((4 - len(js) % 4) % 4)
out = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + len(rest)) + struct.pack('<II', len(js), 0x4E4F534A) + js + rest
open(dst, 'wb').write(out)
print('SPRING_OK', dst, json.dumps(report))
