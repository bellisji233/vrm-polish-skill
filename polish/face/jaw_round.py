# Round the jaw corners below the ears. Tripo's jaw line ends in a sharp corner where it turns back into the neck;
# looking up, the two corners show as bony lumps below the ears (user, 11-13). Skin vertices in a box around each
# corner are relaxed with a Laplacian (a convex corner moves inward), feathered at the box edges and frozen near
# the neck blend ring so the seam stays closed. Vertices only move; none are added or removed (expression scripts
# find the eyes, mouth and brows by vertex index).
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree


def _ramp(v, lo, hi, f):
    return np.clip((v - lo) / f, 0, 1) * np.clip((hi - v) / f, 0, 1)


def round_jaw(head, cfg):
    me = head.data; M = head.matrix_world; Mi = M.inverted()
    P = np.array([M @ v.co for v in me.vertices])
    mats = [m.name if m else '' for m in me.materials]
    skin = np.zeros(len(P), bool); neck = np.zeros(len(P), bool)
    for p in me.polygons:
        n = mats[p.material_index]
        if n.startswith('Material_head'):
            skin[list(p.vertices)] = True
        elif n.startswith('Material_neck'):
            neck[list(p.vertices)] = True
    f = cfg['feather']
    w = _ramp(P[:, 2], *cfg['z'], f) * _ramp(np.abs(P[:, 0] - cfg.get('cx', 0.003)), *cfg['absx'], f) * _ramp(P[:, 1], *cfg['y'], f)
    w[~skin] = 0
    kd = KDTree(int(neck.sum()))
    for i in np.where(neck)[0]:
        kd.insert(Vector(P[i]), int(i))
    kd.balance()
    for i in np.where(w > 0)[0]:
        _, _, d = kd.find(Vector(P[i]))
        w[i] *= np.clip((d - cfg['neck_margin']) / cfg['neck_margin'], 0, 1)
    nb = [[] for _ in range(len(P))]
    for e in me.edges:
        a, b = e.vertices
        if skin[a] and skin[b]:
            nb[a].append(b); nb[b].append(a)
    if cfg.get('ear'):                                   # keep the ear: in front of the jaw back and far out
        e_ = cfg['ear']; ear = (np.abs(P[:, 0] - cfg.get('cx', 0.003)) > e_['absx']) & (P[:, 1] < e_['y'])
        w[ear] = 0
    act = np.where(w > 0)[0]
    P0 = P.copy()
    if cfg.get('pull'):                                  # pull the corner toward the neck axis (horizontal)
        ax_ = np.array(cfg['axis']); d_ = P[act][:, :2] - ax_
        P[act, :2] -= (cfg['pull'] * w[act])[:, None] * d_
    for _ in range(cfg['iters']):
        avg = np.array([P[nb[i]].mean(0) if nb[i] else P[i] for i in act])
        P[act] += (cfg['lam'] * w[act])[:, None] * (avg - P[act])
    for i in act:
        me.vertices[i].co = Mi @ Vector(P[i])
    me.update()
    d = np.linalg.norm(P - P0, axis=1)
    return dict(verts=int((d > 1e-5).sum()), maxMm=round(float(d.max()) * 1000, 2))
