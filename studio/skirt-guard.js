// 裙摆背面限位（2026-11-18）
// 深蹲、抬膝时膝盖一帧就能扫过裙摆链的位置，弹簧骨的碰撞只会把链子往最近的方向推，于是链子被推到腿的另一侧
// （腿和身体之间），站起来以后卡在那里，裙子从前面分开回不去。
// 做法：每条裙摆链应该待在腿「朝向自己裙根」的一侧（站立时是腿前面，深蹲大腿抬平时是大腿上面）。在 three-vrm
// 每节的碰撞计算之后，如果末端落在腿的另一侧、离腿不远，就把它放回正确一侧的腿表面外——布浮在腿上，而不是被穿过。
// 这是布料系统里「背面限位」（backstop）的简化版。只作用于骨骼名以 Skirt 开头的弹簧骨。
// 横向连接（11-18 第二版）：裙摆链之间原本没有任何连接，膝盖顶上来时两条链各自往两边让，中间的布被撕开（深蹲时
// 裙子从前面裂开）。相邻两条链同一节的末端距离超过静止时的 STRETCH 倍，就各自往对方拉回一半，裙子像一整片布一样
// 被膝盖撑起来盖住腿。相当于 MagicaCloth 骨骼布料的「网格连接」。
export function createSkirtGuard(THREE, opts = {}) {
  const _head = new THREE.Vector3(), _tailP = new THREE.Vector3(), _ax = new THREE.Vector3(), _c = new THREE.Vector3();
  const _rt = new THREE.Vector3(), _rr = new THREE.Vector3(), _bone = new THREE.Vector3(), _root = new THREE.Vector3(), _tmp = new THREE.Vector3();
  const info = { joints: 0, fixes: 0, pulls: 0, chains: 0, links: 0 };
  const MARGIN = 0.03;   // 末端离腿表面这么近才算「卡在腿那一侧」，远处的摆动不管
  const STRETCH = opts.stretch ?? 1.6;  // 相邻链末端最多拉开到静止距离的这个倍数（0 = 不连）；1.15 时膝盖抬起裙子撑不开，被挤到一边
  const _n = new THREE.Vector3(), _nw = new THREE.Vector3();
  function neighborTail(j, out) { return out.copy(j._currentTail).applyMatrix4(j._getMatrixCenterToWorld()); }
  function lateral(joint, tail) {
    const L = joint.__skirtLinks; if (!L) return;
    _bone.setFromMatrixPosition(joint.bone.matrixWorld);
    for (const { other, rest } of L) {
      neighborTail(other, _nw);
      _n.subVectors(_nw, tail); const d = _n.length(), max = rest * STRETCH;
      if (d <= max || d < 1e-6) continue;
      tail.addScaledVector(_n, (d - max) * 0.5 / d);
      tail.sub(_bone); const len = tail.length() || 1; tail.multiplyScalar(joint._worldSpaceBoneLength / len).add(_bone);
      info.pulls++;
    }
  }

  // 胶囊轴上离 p 最近的点 → _c；返回胶囊半径
  function closestOnCapsule(collider, p) {
    const m = collider.colliderMatrix, sh = collider.shape;
    _head.setFromMatrixPosition(m);
    _tailP.subVectors(sh.tail, sh.offset).applyMatrix4(m);
    _ax.subVectors(_tailP, _head);
    const L = _ax.lengthSq(); let t = L > 0 ? _tmp.subVectors(p, _head).dot(_ax) / L : 0; t = Math.max(0, Math.min(1, t));
    _c.copy(_head).addScaledVector(_ax, t);
    return sh.radius;
  }
  function guard(joint, root, tail) {
    _bone.setFromMatrixPosition(joint.bone.matrixWorld);
    root.bone.getWorldPosition(_root);
    for (const g of joint.colliderGroups) for (const col of g.colliders) {
      // thighs only: below the knee the skirt hangs in front of the shin, while the root lies behind it
      if (col.shape?.type !== 'capsule' || col.shape.inside || !/upper_?leg|thigh/i.test(col.parent?.name || '')) continue;
      const r = closestOnCapsule(col, tail);
      _rt.subVectors(tail, _c);
      const d = _rt.length();
      if (d > r + joint.settings.hitRadius + MARGIN) continue;
      // 正确一侧：裙根相对这条腿轴的方向（去掉沿轴的分量）
      _ax.normalize();
      _rr.subVectors(_root, _c); _rr.addScaledVector(_ax, -_rr.dot(_ax));
      _rt.addScaledVector(_ax, -_rt.dot(_ax));
      if (_rr.lengthSq() < 1e-8 || _rt.dot(_rr) >= 0) continue;
      // 放到正确一侧的腿表面外，再按骨长拉回
      tail.copy(_c).addScaledVector(_rr.normalize(), r + joint.settings.hitRadius + 0.005);
      tail.sub(_bone); const len = tail.length() || 1; tail.multiplyScalar(joint._worldSpaceBoneLength / len).add(_bone);
      info.fixes++;
    }
  }
  function setup(vrm) {
    info.joints = 0; info.fixes = 0; info.pulls = 0;
    const mgr = vrm?.springBoneManager; if (!mgr?.joints) return;
    const byChainRoot = new Map();
    for (const j of mgr.joints) {
      if (!/^Skirt/i.test(j.bone?.name || '') || typeof j._collision !== 'function') continue;
      // 链的根：沿父级往上找，最上面一个仍是裙摆弹簧骨的那节
      let root = j;
      for (const k of mgr.joints) if (k.child === root.bone) { root = k; }
      byChainRoot.set(j, root);
    }
    // 再走一遍保证找到最顶端（链有 4–5 节）
    for (const [j] of byChainRoot) {
      let root = byChainRoot.get(j), guardN = 8;
      while (guardN-- > 0) { const up = [...byChainRoot.keys()].find(k => k.child === root.bone); if (!up) break; root = up; }
      byChainRoot.set(j, root);
    }
    // chains: root → children; ordered around the body by the root's azimuth (scene-local, around the hips)
    const chains = new Map();
    for (const [j, root] of byChainRoot) (chains.get(root) || chains.set(root, []).get(root)).push(j);
    const depth = j => { let d = 0, k = j; while (k !== byChainRoot.get(j) && d < 10) { const up = [...byChainRoot.keys()].find(x => x.child === k.bone); if (!up) break; k = up; d++; } return d; };
    const inv = new THREE.Matrix4().copy(vrm.scene.matrixWorld).invert();
    const hips = vrm.humanoid?.getNormalizedBoneNode('hips'); const hp = hips ? hips.getWorldPosition(new THREE.Vector3()).applyMatrix4(inv) : new THREE.Vector3();
    const list = [...chains.entries()].map(([root, js]) => {
      const p = root.bone.getWorldPosition(new THREE.Vector3()).applyMatrix4(inv);
      return { root, joints: js.sort((a, b) => depth(a) - depth(b)), az: Math.atan2(p.x - hp.x, p.z - hp.z) };
    }).sort((a, b) => a.az - b.az);
    info.chains = list.length; info.links = 0;
    const restTail = j => j.child ? j.child.getWorldPosition(new THREE.Vector3()) : j.bone.localToWorld(j._initialLocalChildPosition.clone());
    if (list.length >= 3 && STRETCH > 0) {
      const gaps = list.map((c, i) => { const n = list[(i + 1) % list.length]; let g = n.az - c.az; if (g <= 0) g += Math.PI * 2; return g; });
      const med = [...gaps].sort((a, b) => a - b)[gaps.length >> 1];
      list.forEach((c, i) => {
        if (gaps[i] > med * 2.5) return;   // an open skirt (slit) is not closed across the gap
        const n = list[(i + 1) % list.length], depthN = Math.min(c.joints.length, n.joints.length);
        for (let k = 0; k < depthN; k++) {
          const a = c.joints[k], b = n.joints[k], rest = restTail(a).distanceTo(restTail(b));
          if (!(rest > 1e-4)) continue;
          (a.__skirtLinks ||= []).push({ other: b, rest }); (b.__skirtLinks ||= []).push({ other: a, rest });
          info.links++;
        }
      });
    }
    for (const [j, root] of byChainRoot) {
      if (j.__skirtGuard) continue;
      const orig = j._collision.bind(j);
      j._collision = tail => { orig(tail); guard(j, root, tail); lateral(j, tail); };
      j.__skirtGuard = true; info.joints++;
    }
  }
  return { setup, info };
}
