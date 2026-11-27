# Brows over the bangs. The bangs cover this character's brows, so angry / sad / surprised brows were not
# readable. Each brow piece is copied with its own material (BrowOverlay, blended). The driving page draws that
# material after the hair without depth test, like see-through brows in 2D rigs; other viewers see the copy a
# fraction of a millimetre in front of the brow. build_character adds the copy (materials can only be added
# there); expr_build makes the copy follow every shape key of the brow vertex it duplicates (sync_brow_overlay);
# vrm_finalize sets the opacity and render queue on the exported material.
import bmesh
import numpy as np
from mathutils import Vector

NAME = 'BrowOverlay'


def _islands(bm, seeds):
    bm.verts.ensure_lookup_table()
    out = set()
    for s in seeds:
        seen = {s}; stack = [bm.verts[s]]
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                w = e.other_vert(v)
                if w.index not in seen:
                    seen.add(w.index); stack.append(w)
        out |= seen
    return out


def add_brow_overlay(head, cfg):
    """cfg: seeds (one vertex per brow piece), offset (m, toward the viewer), max_verts (sanity check per piece)."""
    me = head.data
    if any(m and m.name == NAME for m in me.materials):
        raise RuntimeError('BrowOverlay already present')
    bm = bmesh.new(); bm.from_mesh(me)
    isl = _islands(bm, cfg['seeds'])
    if len(isl) > cfg.get('max_verts', 200) * len(cfg['seeds']):
        raise RuntimeError(f'brow seeds reach {len(isl)} verts; check seeds')
    bm.faces.ensure_lookup_table()
    faces = [f for f in bm.faces if all(v.index in isl for v in f.verts)]
    edges = list({e for f in faces for e in f.edges}); verts = list({v for f in faces for v in f.verts})
    src = next(m for m in me.materials if m and m.name.startswith('Material_head'))
    mat = src.copy(); mat.name = NAME
    if hasattr(mat, 'blend_method'):
        mat.blend_method = 'BLEND'                       # the kit's MToon conversion reads this for alphaMode
    x = getattr(mat, 'vrm_addon_extension', None)
    if x is not None and x.mtoon1.enabled:
        x.mtoon1.alpha_mode = 'BLEND'                    # already converted (a source blend): set it directly
    me.materials.append(mat); slot = len(me.materials) - 1
    dup = bmesh.ops.duplicate(bm, geom=faces + edges + verts)
    off = head.matrix_world.inverted().to_3x3() @ Vector((0.0, -cfg['offset'], 0.0))
    layers = list(bm.verts.layers.shape.values())
    for g in dup['geom']:
        if isinstance(g, bmesh.types.BMFace):
            g.material_index = slot
        elif isinstance(g, bmesh.types.BMVert):
            g.co += off
            for L in layers:
                g[L] = g[L] + off
    bm.to_mesh(me); bm.free(); me.update()
    P = np.array([head.matrix_world @ me.vertices[i].co for i in sorted(isl)])
    return dict(verts=len(isl), faces=len(faces), zRange=[round(float(P[:, 2].min()), 3), round(float(P[:, 2].max()), 3)])


def sync_brow_overlay(head, seeds):
    """Every shape key: each BrowOverlay vertex moves exactly like the brow vertex it was copied from."""
    me = head.data
    mi = next((i for i, m in enumerate(me.materials) if m and m.name == NAME), None)
    if mi is None:
        return dict(skipped='no BrowOverlay material')
    ov = sorted({v for p in me.polygons if p.material_index == mi for v in p.vertices})
    bm = bmesh.new(); bm.from_mesh(me); isl = sorted(_islands(bm, seeds)); bm.free()
    kb = me.shape_keys.key_blocks
    B = np.empty(len(me.vertices) * 3, np.float32); kb['Basis'].data.foreach_get('co', B); B = B.reshape(-1, 3)
    S = B[isl]; src = []
    for v in ov:
        d = np.linalg.norm(S - B[v], axis=1); src.append(isl[int(np.argmin(d))])
    gap = max(float(np.linalg.norm(B[v] - B[s])) for v, s in zip(ov, src))
    src = np.array(src); ov = np.array(ov)
    K = np.empty_like(B)
    n = 0
    for k in kb:
        if k.name == 'Basis':
            continue
        k.data.foreach_get('co', K.ravel())
        K[ov] = B[ov] + (K[src] - B[src])
        k.data.foreach_set('co', K.ravel()); n += 1
    me.update()
    return dict(verts=len(ov), keys=n, maxGapMm=round(gap * 1000, 3))
