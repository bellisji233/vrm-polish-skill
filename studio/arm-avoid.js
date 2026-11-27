// 手臂避让身体（2026-11-18）
// 实测三套模型的穿模大多是「手臂插进躯干 / 大腿」：舞蹈、摄像头里手臂垂下或贴身时，袖子和手整段进到身体里。
// 做法：模型载入时在静止姿势下量躯干每一层的横截面（椭圆）、大腿和袖子的粗细；每帧在姿势定好、
// vrm.update 之前，检查上臂、手肘、小臂、手腕、手掌几个采样点，插进身体就把上臂绕肩往外转到刚好贴住。
// 只改上臂（整条胳膊一起移开），不改手肘弯曲和手的朝向。
// 11-18 加头和脖子（用户：手和手臂会穿过头）：头按头部网格量一个椭球，脖子按颈到头的胶囊，同样绕肩把手臂让开。
// 11-19 平滑（用户：极乐净土动作卡卡的）：每帧现算的修正量在「刚插进 / 刚离开」时一帧跳几度，实测手肘、手腕的瞬时加速度
//   99 分位比不避让时高 50%、最大值翻倍。修正量记成肩部坐标里的一个旋转，按时间常数追目标（推开快、松开慢）。
// 11-26 头改成按高度分层的椭圆（用户：手穿到嘴里）：包围盒内切的椭球装不下写实脸的下巴和嘴（人物2 嘴前 1.07、下巴 1.56，
//   都在椭球外），手上也只查了手掌中间一点。现在头按 1 cm 一层量横截面（和躯干一样），手加手指根和指尖两点；
//   脸上的允许贴合深度单独设小（HEAD_ALLOW），手指不能伸进嘴里。
// 11-26 晚 头改成按网格算的距离场（用户：Reze 托腮时人物2 的拳头顶进下颌，牛仔装没事）：横截面椭圆只会水平推，
//   下巴底下往上顶的手指推不出来；手上也只查了中指。现在静止姿势下把头部网格体素化（5 mm 一格，沿三个轴各扫一遍
//   按交点奇偶判内外、多数决，网格有开口也不怕），每格存到表面的距离（1 cm 内按三角形精确算，更远用倒角扫描传开）；手掌和五根手指的关节、指尖都按
//   距离场判断，沿表面法线推。手碰头时上臂和手肘一起动：只转上臂时，推的方向和「肩到手」接近平行就推不动（手从下往上
//   托下巴正是这样）。
// 网页和穿模检测共用：createArmAvoid(THREE) → { setup(vrm), apply(vrm, dt), info }；不给 dt 时立即生效（穿模检测）
const SDF_CELL = 0.005, SDF_MARGIN = 0.03, SDF_FAR = 0.08;
// T: triangles (9 floats each) in the head frame → { o, n, C, d } signed distance (inside < 0), capped at SDF_FAR
export function buildHeadSDF(T) {
  const ntri = T.length / 9, mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < T.length; i += 3) for (let k = 0; k < 3; k++) { if (T[i + k] < mn[k]) mn[k] = T[i + k]; if (T[i + k] > mx[k]) mx[k] = T[i + k]; }
  const C = SDF_CELL, o = mn.map(v => v - SDF_MARGIN), n = mn.map((v, k) => Math.ceil((mx[k] - v + 2 * SDF_MARGIN) / C) + 1);
  const N = n[0] * n[1] * n[2], votes = new Uint8Array(N), at = (x, y, z) => (z * n[1] + y) * n[0] + x;
  const J = [0.0137, 0.0291, 0.0419];   // ray offsets inside a cell: rays never run exactly along a shared edge
  for (let k = 0; k < 3; k++) {
    const u = (k + 1) % 3, w = (k + 2) % 3, cols = new Array(n[u] * n[w]);
    for (let t = 0; t < ntri; t++) {
      const i = t * 9, au = T[i + u], aw = T[i + w], bu = T[i + 3 + u], bw = T[i + 3 + w], cu = T[i + 6 + u], cw = T[i + 6 + w];
      const det = (bu - au) * (cw - aw) - (cu - au) * (bw - aw); if (Math.abs(det) < 1e-14) continue;
      const iu0 = Math.max(0, Math.ceil((Math.min(au, bu, cu) - o[u]) / C - J[u])), iu1 = Math.min(n[u] - 1, Math.floor((Math.max(au, bu, cu) - o[u]) / C - J[u]));
      const iw0 = Math.max(0, Math.ceil((Math.min(aw, bw, cw) - o[w]) / C - J[w])), iw1 = Math.min(n[w] - 1, Math.floor((Math.max(aw, bw, cw) - o[w]) / C - J[w]));
      for (let iu = iu0; iu <= iu1; iu++) for (let iw = iw0; iw <= iw1; iw++) {
        const qu = o[u] + (iu + J[u]) * C, qw = o[w] + (iw + J[w]) * C;
        const l1 = ((qu - au) * (cw - aw) - (cu - au) * (qw - aw)) / det, l2 = ((bu - au) * (qw - aw) - (qu - au) * (bw - aw)) / det;
        if (l1 < 0 || l2 < 0 || l1 + l2 > 1) continue;
        (cols[iu * n[w] + iw] ||= []).push(T[i + k] + l1 * (T[i + 3 + k] - T[i + k]) + l2 * (T[i + 6 + k] - T[i + k]));
      }
    }
    for (let iu = 0; iu < n[u]; iu++) for (let iw = 0; iw < n[w]; iw++) {
      const h = cols[iu * n[w] + iw]; if (!h || h.length < 2) continue;
      h.sort((a, b) => a - b);
      let c = 0;
      for (let ik = 0; ik < n[k]; ik++) {
        const q = o[k] + ik * C; while (c < h.length && h[c] < q) c++;
        if (c % 2 === 1) { const idx = [0, 0, 0]; idx[k] = ik; idx[u] = iu; idx[w] = iw; votes[at(idx[0], idx[1], idx[2])]++; }
      }
    }
  }
  // distance to the surface: exact distance to the triangles within 1 cm of a cell (vertex distance alone overshot the
  // surface by ~3 mm at the jaw), carried further by a chamfer sweep, so a hand deep inside still knows the nearest
  // way out (Gokuraku 2 s: a palm 5 cm inside the top of the head had no direction past a 2 cm band)
  const key = (a, b, c) => (a * 73856093) ^ (b * 19349663) ^ (c * 83492791);
  const HT = 0.01, tb = new Map();      // triangles by 1 cm bucket of their bounding box
  for (let t = 0; t < ntri; t++) {
    const i = t * 9;
    const lo = [0, 1, 2].map(k => Math.floor(Math.min(T[i + k], T[i + 3 + k], T[i + 6 + k]) / HT)), hi = [0, 1, 2].map(k => Math.floor(Math.max(T[i + k], T[i + 3 + k], T[i + 6 + k]) / HT));
    for (let a = lo[0]; a <= hi[0]; a++) for (let b = lo[1]; b <= hi[1]; b++) for (let c = lo[2]; c <= hi[2]; c++) { const k_ = key(a, b, c); let l = tb.get(k_); if (!l) tb.set(k_, l = []); l.push(t); }
  }
  const triDist2 = (t, px, py, pz) => {   // squared distance from p to triangle t (closest point, Ericson 5.1.5)
    const i = t * 9, ax = T[i], ay = T[i + 1], az = T[i + 2];
    const abx = T[i + 3] - ax, aby = T[i + 4] - ay, abz = T[i + 5] - az, acx = T[i + 6] - ax, acy = T[i + 7] - ay, acz = T[i + 8] - az;
    const apx = px - ax, apy = py - ay, apz = pz - az;
    const d1 = abx * apx + aby * apy + abz * apz, d2 = acx * apx + acy * apy + acz * apz;
    let qx, qy, qz;
    if (d1 <= 0 && d2 <= 0) { qx = ax; qy = ay; qz = az; }
    else {
      const bpx = px - T[i + 3], bpy = py - T[i + 4], bpz = pz - T[i + 5], d3 = abx * bpx + aby * bpy + abz * bpz, d4 = acx * bpx + acy * bpy + acz * bpz;
      const cpx = px - T[i + 6], cpy = py - T[i + 7], cpz = pz - T[i + 8], d5 = abx * cpx + aby * cpy + abz * cpz, d6 = acx * cpx + acy * cpy + acz * cpz;
      const vc = d1 * d4 - d3 * d2, vb = d5 * d2 - d1 * d6, va = d3 * d6 - d5 * d4;
      if (d3 >= 0 && d4 <= d3) { qx = T[i + 3]; qy = T[i + 4]; qz = T[i + 5]; }
      else if (d6 >= 0 && d5 <= d6) { qx = T[i + 6]; qy = T[i + 7]; qz = T[i + 8]; }
      else if (vc <= 0 && d1 >= 0 && d3 <= 0) { const v = d1 / (d1 - d3); qx = ax + v * abx; qy = ay + v * aby; qz = az + v * abz; }
      else if (vb <= 0 && d2 >= 0 && d6 <= 0) { const w = d2 / (d2 - d6); qx = ax + w * acx; qy = ay + w * acy; qz = az + w * acz; }
      else if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0) { const w = (d4 - d3) / ((d4 - d3) + (d5 - d6)); qx = T[i + 3] + w * (T[i + 6] - T[i + 3]); qy = T[i + 4] + w * (T[i + 7] - T[i + 4]); qz = T[i + 5] + w * (T[i + 8] - T[i + 5]); }
      else { const dn = 1 / (va + vb + vc), v = vb * dn, w = vc * dn; qx = ax + abx * v + acx * w; qy = ay + aby * v + acy * w; qz = az + abz * v + acz * w; }
    }
    return (px - qx) ** 2 + (py - qy) ** 2 + (pz - qz) ** 2;
  };
  const d = new Float32Array(N).fill(Infinity), stamp = new Int32Array(ntri);
  let stampId = 0;
  for (let z = 0; z < n[2]; z++) for (let y = 0; y < n[1]; y++) for (let x = 0; x < n[0]; x++) {
    const px = o[0] + x * C, py = o[1] + y * C, pz = o[2] + z * C, tx = Math.floor(px / HT), ty = Math.floor(py / HT), tz = Math.floor(pz / HT);
    let best = HT * HT; stampId++;
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (let c = -1; c <= 1; c++) {
      const l = tb.get(key(tx + a, ty + b, tz + c)); if (!l) continue;
      for (let j = 0; j < l.length; j++) { const t = l[j]; if (stamp[t] === stampId) continue; stamp[t] = stampId; const q = triDist2(t, px, py, pz); if (q < best) best = q; }
    }
    if (best < HT * HT) d[at(x, y, z)] = Math.sqrt(best);
  }
  // chamfer sweeps (forward and back over the 26 neighbours) for the cells further than 1 cm
  const nb = [];
  for (let c = -1; c <= 1; c++) for (let b = -1; b <= 1; b++) for (let a = -1; a <= 1; a++) if (a || b || c) nb.push([a, b, c, C * Math.hypot(a, b, c), (c * n[1] + b) * n[0] + a]);
  const fwd = nb.filter(([a, b, c]) => c < 0 || (c === 0 && (b < 0 || (b === 0 && a < 0)))), bwd = nb.filter(q => !fwd.includes(q));
  for (const [list, z0, z1, st] of [[fwd, 0, n[2], 1], [bwd, n[2] - 1, -1, -1]]) {
    for (let z = z0; z !== z1; z += st) for (let y = st > 0 ? 0 : n[1] - 1; y !== (st > 0 ? n[1] : -1); y += st) for (let x = st > 0 ? 0 : n[0] - 1; x !== (st > 0 ? n[0] : -1); x += st) {
      const i = at(x, y, z); let v = d[i];
      for (const [a, b, c, w, off] of list) {
        const X = x + a, Y = y + b, Z = z + c; if (X < 0 || Y < 0 || Z < 0 || X >= n[0] || Y >= n[1] || Z >= n[2]) continue;
        const u = d[i + off] + w; if (u < v) v = u;
      }
      d[i] = v;
    }
  }
  for (let i = 0; i < N; i++) { const v = Math.min(d[i], SDF_FAR); d[i] = votes[i] >= 2 ? -v : v; }
  return { o, n, C, d };
}
// trilinear distance at (x, y, z) in the head frame, gradient into g (not normalised); outside the grid: SDF_FAR
export function sdfAt(S, x, y, z, g) {
  const fx = (x - S.o[0]) / S.C, fy = (y - S.o[1]) / S.C, fz = (z - S.o[2]) / S.C, n = S.n;
  if (fx < 0 || fy < 0 || fz < 0 || fx > n[0] - 1 || fy > n[1] - 1 || fz > n[2] - 1) { g.set(0, 0, 0); return SDF_FAR; }
  const ix = Math.min(n[0] - 2, Math.floor(fx)), iy = Math.min(n[1] - 2, Math.floor(fy)), iz = Math.min(n[2] - 2, Math.floor(fz));
  const tx = fx - ix, ty = fy - iy, tz = fz - iz, D = S.d, sy = n[0], sz = n[0] * n[1], b = (iz * n[1] + iy) * n[0] + ix;
  const c000 = D[b], c100 = D[b + 1], c010 = D[b + sy], c110 = D[b + 1 + sy], c001 = D[b + sz], c101 = D[b + 1 + sz], c011 = D[b + sy + sz], c111 = D[b + 1 + sy + sz];
  const c00 = c000 + (c100 - c000) * tx, c10 = c010 + (c110 - c010) * tx, c01 = c001 + (c101 - c001) * tx, c11 = c011 + (c111 - c011) * tx;
  const c0 = c00 + (c10 - c00) * ty, c1 = c01 + (c11 - c01) * ty;
  const gx = ((c100 - c000) * (1 - ty) + (c110 - c010) * ty) * (1 - tz) + ((c101 - c001) * (1 - ty) + (c111 - c011) * ty) * tz;
  g.set(gx / S.C, ((c10 - c00) * (1 - tz) + (c11 - c01) * tz) / S.C, (c1 - c0) / S.C);
  return c0 + (c1 - c0) * tz;
}
export function createArmAvoid(THREE, opts = {}) {
  const TORSO = ['hips', 'spine', 'chest', 'upperChest'];
  const SLAB = 0.02;           // 躯干分层厚度（米）
  const ALLOW = opts.allow ?? 0.02;   // 允许的贴合深度：袖子和衣服是软的，2 cm 以内的贴合看着是「贴着身体」；只处理插得深的
  const HEAD_ALLOW = opts.headAllow ?? 0.004;   // 脸是硬的：手指贴到脸上就停
  const MAX_HEAD = opts.maxHead ?? 0.45;          // 手碰到脸时最多外移 26°（15° 时 Reze 托腮的手指还在下颌里）
  const HEAD_SLAB = 0.01;
  const MAX_STEP = 0.35;       // 单次迭代最多转 20°
  const ITER = 4;
  const MAX_TOTAL = opts.maxTotal ?? 0.26;   // 单侧最多外移 15°：宽裙摆、蓬袖时宁可留一点贴合，也不把手臂撑成企鹅
  let P = null;                // 当前模型的代理形状
  const info = { active: false, lastAngle: { left: 0, right: 0 }, lastHit: { left: null, right: null } };
  let hitWhat = '';
  const _m = new THREE.Matrix4(), _mi = new THREE.Matrix4(), _v = new THREE.Vector3(), _q = new THREE.Quaternion();

  const pct = (arr, p) => { if (!arr.length) return 0; const a = Float64Array.from(arr).sort(); return a[Math.min(a.length - 1, Math.floor(p * a.length))]; };
  const segDist = (p, a, b, out) => { // closest point on segment ab → out; returns t
    const ab = _v.subVectors(b, a); const L = ab.lengthSq();
    let t = L > 0 ? (p.clone().sub(a).dot(ab)) / L : 0; t = Math.max(0, Math.min(1, t));
    out.copy(a).addScaledVector(ab, t); return t;
  };

  // 场景内（vrm.scene 局部）坐标
  function sceneLocal(vrm) { return _mi.copy(vrm.scene.matrixWorld).invert(); }
  function bonePos(vrm, name, inv, out = new THREE.Vector3()) {
    const n = vrm.humanoid.getNormalizedBoneNode(name); if (!n) return null;
    return out.setFromMatrixPosition(n.matrixWorld).applyMatrix4(inv);
  }

  function setup(vrm) {
    P = null; info.active = false; corr.left.identity(); corr.right.identity(); hasOut.left = hasOut.right = false; corrL.left.identity(); corrL.right.identity(); hasOutL.left = hasOutL.right = false;
    const h = vrm?.humanoid; if (!h) return;
    // 在静止姿势下量：先存当前姿势，量完恢复
    const saved = new Map();
    for (const name of Object.keys(h.humanBones)) { const n = h.getNormalizedBoneNode(name); if (n) saved.set(n, n.quaternion.clone()); }
    try {
      h.resetNormalizedPose(); h.update(); vrm.scene.updateMatrixWorld(true);
      const inv = sceneLocal(vrm).clone();
      const raw2human = new Map();
      for (const [name, b] of Object.entries(h.humanBones)) if (b?.node) raw2human.set(b.node, name);
      const J = {};
      for (const name of [...TORSO, 'neck', 'head', 'leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand',
        'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg', 'leftMiddleProximal', 'rightMiddleProximal']) {
        const n = h.getRawBoneNode(name); if (n) J[name] = new THREE.Vector3().setFromMatrixPosition(n.matrixWorld).applyMatrix4(inv);
      }
      if (!J.hips || !J.leftUpperArm || !J.rightUpperArm || !J.leftUpperLeg || !J.rightUpperLeg) return;
      const groups = {};
      const meshes = [];
      vrm.scene.traverse(o => { if (o.isSkinnedMesh) meshes.push(o); });
      for (const mesh of meshes) {
        const mat = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
        if (/^(Hair|head|Head|Spring_)/.test(mesh.name) || /accessor|hair|head|face|eye/i.test(mat?.name || '')) continue;
        const g = mesh.geometry, pos = g.attributes.position, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
        if (!pos || !si || !sw) continue;
        _m.multiplyMatrices(inv, mesh.matrixWorld);
        const bones = mesh.skeleton.bones;
        for (let i = 0; i < pos.count; i += 1) {
          let best = -1, bi = 0;
          for (let c = 0; c < 4; c++) { const w = sw.getComponent(i, c); if (w > best) { best = w; bi = si.getComponent(i, c); } }
          let hn = raw2human.get(bones[bi]);
          if (!hn) { // 辅助骨按所属肢体算
            const m = /^(Shoulder|Elbow|Wrist)Helper\.?(L|R)$/.exec(bones[bi]?.name || '');
            if (m) hn = (m[2] === 'L' ? 'left' : 'right') + (m[1] === 'Shoulder' ? 'UpperArm' : 'LowerArm');
          }
          if (!hn) continue;
          (groups[hn] ||= []).push(new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(_m));
        }
      }
      // 头：头部网格里由 head 骨骼带动的顶点（不含头发，头发是软的，穿一点看不出），分位数范围定椭球
      let head = null;
      if (J.head) {
        const hv = [];
        for (const mesh of meshes) {
          if (!/^head/i.test(mesh.name) || /hair/i.test(mesh.name) || /^(Eye|FX_|Brow|Crease)/.test(mesh.material?.name || '')) continue;
          const g = mesh.geometry, pos = g.attributes.position, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
          if (!pos || !si || !sw) continue;
          _m.multiplyMatrices(inv, mesh.matrixWorld);
          const bones = mesh.skeleton.bones;
          for (let i = 0; i < pos.count; i += 2) {
            let best = -1, bi = 0;
            for (let c = 0; c < 4; c++) { const w = sw.getComponent(i, c); if (w > best) { best = w; bi = si.getComponent(i, c); } }
            if (raw2human.get(bones[bi]) === 'head') hv.push(new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(_m));
          }
        }
        if (hv.length > 200) {
          const e = 0.02, ax = k => hv.map(v => v[k]);
          const [x0, x1, y0, y1, z0, z1] = [pct(ax('x'), e), pct(ax('x'), 1 - e), pct(ax('y'), e), pct(ax('y'), 1 - e), pct(ax('z'), e), pct(ax('z'), 1 - e)];
          head = { c: new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2).sub(J.head), r: new THREE.Vector3((x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2) };
          // cross-sections every HEAD_SLAB of height: chin, mouth and nose are inside, unlike the box ellipsoid
          const ys = ax('y'), slabs = [];
          for (let y = Math.min(...ys); y < Math.max(...ys); y += HEAD_SLAB) {
            const pts = hv.filter(p => p.y >= y && p.y < y + HEAD_SLAB);
            if (pts.length < 4) continue;
            const xs = pts.map(p => p.x), zs = pts.map(p => p.z);
            // near the extremes by count, not share: the face is far denser than the back of the head (人物2 at eye
            // level: 10 % of the points lie behind z = 0.047 of a -0.064..0.076 head), so share percentiles lost the back
            const ex = Math.min(0.02, 2 / pts.length), sx0 = pct(xs, ex), sx1 = pct(xs, 1 - ex), sz0 = pct(zs, ex), sz1 = pct(zs, 1 - ex);
            slabs.push({ y: y + HEAD_SLAB / 2 - J.head.y, cx: (sx0 + sx1) / 2 - J.head.x, cz: (sz0 + sz1) / 2 - J.head.z, a: (sx1 - sx0) / 2, b: (sz1 - sz0) / 2 });
          }
          if (slabs.length >= 6) head.slabs = slabs;
          // 11-26 晚: the head surface itself as a distance field (buildHeadSDF); slabs stay as the fallback direction
          // the neck blend is an open tube overlapping the jaw: its walls flipped the inside test there (Reze 7.5 s, a
          // fingertip 2 cm inside the jaw read as outside); the neck capsule covers the neck
          const tris = [];
          for (const mesh of meshes) {
            if (!/^head/i.test(mesh.name) || /hair/i.test(mesh.name) || /^(Eye|FX_|Brow|Crease)|neck/i.test(mesh.material?.name || '')) continue;
            const g = mesh.geometry, pos = g.attributes.position, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
            if (!pos || !si || !sw) continue;
            _m.multiplyMatrices(inv, mesh.matrixWorld);
            const bones = mesh.skeleton.bones, P3 = new Float32Array(pos.count * 3), isH = new Uint8Array(pos.count);
            for (let i = 0; i < pos.count; i++) {
              let best = -1, bi = 0;
              for (let c = 0; c < 4; c++) { const w = sw.getComponent(i, c); if (w > best) { best = w; bi = si.getComponent(i, c); } }
              if (raw2human.get(bones[bi]) !== 'head') continue;
              isH[i] = 1; _v.fromBufferAttribute(pos, i).applyMatrix4(_m).sub(J.head);
              P3[i * 3] = _v.x; P3[i * 3 + 1] = _v.y; P3[i * 3 + 2] = _v.z;
            }
            const ix = g.index, nI = ix ? ix.count : pos.count;
            for (let t = 0; t + 2 < nI; t += 3) {
              const a = ix ? ix.getX(t) : t, b = ix ? ix.getX(t + 1) : t + 1, c = ix ? ix.getX(t + 2) : t + 2;
              if (isH[a] && isH[b] && isH[c]) for (const q of [a, b, c]) tris.push(P3[q * 3], P3[q * 3 + 1], P3[q * 3 + 2]);
            }
          }
          if (tris.length >= 9 * 500) {
            const t0 = performance.now();
            head.sdf = buildHeadSDF(Float32Array.from(tris));
            head.sdfInfo = { tris: tris.length / 9, ms: Math.round(performance.now() - t0), cells: head.sdf.n };
          }
        }
      }
      // 躯干：每 2 cm 一层，按所在骨骼记录椭圆（中心、左右半宽、前后半深）
      const torsoVerts = TORSO.flatMap(n => groups[n] || []);
      if (torsoVerts.length < 200) return;
      const ranges = [];
      for (let k = 0; k < TORSO.length; k++) {
        const b = TORSO[k], y0 = k === 0 ? J.hips.y - 0.16 : J[b]?.y, y1 = J[TORSO[k + 1]]?.y ?? J.neck?.y ?? (J[b].y + 0.12);
        if (J[b] && y0 != null) ranges.push({ bone: b, y0, y1, slabs: [] });
      }
      for (const r of ranges) {
        for (let y = r.y0; y < r.y1; y += SLAB) {
          const pts = torsoVerts.filter(p => p.y >= y && p.y < y + SLAB);
          if (pts.length < 12) continue;
          // 中心和半宽取两端分位数的中点和一半：顶点分布不均（臀部、胸部密），用中位数当中心会把椭圆拉偏、撑大
          const e = opts.pTorso ?? 0.03, xs = pts.map(p => p.x), zs = pts.map(p => p.z);
          const x0 = pct(xs, e), x1 = pct(xs, 1 - e), z0 = pct(zs, e), z1 = pct(zs, 1 - e);
          r.slabs.push({ y: y + SLAB / 2 - J[r.bone].y, cx: (x0 + x1) / 2 - J[r.bone].x, cz: (z0 + z1) / 2 - J[r.bone].z, a: (x1 - x0) / 2, b: (z1 - z0) / 2 });
        }
      }
      // 大腿、袖子：到骨轴距离的分位数
      const radius = (verts, a, b, p) => {
        const c = new THREE.Vector3(), d = [];
        for (const v of verts || []) { const t = segDist(v, a, b, c); if (t > 0.1 && t < 0.9) d.push(v.distanceTo(c)); }
        return pct(d, p);
      };
      const side = s => ({
        // 65 / 60 分位：蓬袖、袖口荷叶边、挎包会把高分位数撑大（夏日装 80 分位袖子 8–9 cm、左大腿 12 cm），把手臂推得太开；
        // 夏日装严格动作穿模 43.6 → 6.5（80 分位时 1.8 但手臂明显张开）
        upper: radius(groups[s + 'UpperArm'], J[s + 'UpperArm'], J[s + 'LowerArm'], opts.pArm ?? 0.45) || 0.045,
        lower: radius(groups[s + 'LowerArm'], J[s + 'LowerArm'], J[s + 'Hand'], opts.pArm ?? 0.45) || 0.035,
        thigh: radius(groups[s + 'UpperLeg'], J[s + 'UpperLeg'], J[s + 'LowerLeg'], opts.pThigh ?? 0.5) || 0.07,
        hand: 0.028,
      });
      P = { ranges: ranges.filter(r => r.slabs.length), left: side('left'), right: side('right'), head, neckR: 0.05 };
      info.P = P;
      info.active = true;
      info.proxies = {
        torsoSlabs: P.ranges.reduce((s, r) => s + r.slabs.length, 0),
        left: Object.fromEntries(Object.entries(P.left).map(([k, v]) => [k, +v.toFixed(3)])),
        right: Object.fromEntries(Object.entries(P.right).map(([k, v]) => [k, +v.toFixed(3)])),
        head: head ? head.r.toArray().map(v => +v.toFixed(3)) : null,
      };
    } finally {
      for (const [n, q] of saved) n.quaternion.copy(q);
      h.update(); vrm.scene.updateMatrixWorld(true);
    }
  }

  // 采样点 p（场景局部）半径 r 插进身体的最大深度和推开方向
  const _g = new THREE.Vector3(), _local = new THREE.Vector3(), _bm = new THREE.Matrix4(), _bmi = new THREE.Matrix4(), _c = new THREE.Vector3(), _a = new THREE.Vector3(), _b = new THREE.Vector3();
  function penetration(vrm, inv, p, r, out, hand = false) {
    let best = 0;
    for (const R of P.ranges) {
      const node = vrm.humanoid.getNormalizedBoneNode(R.bone); if (!node) continue;
      _bm.multiplyMatrices(inv, node.matrixWorld); _bmi.copy(_bm).invert();
      _local.copy(p).applyMatrix4(_bmi);
      const S = R.slabs; if (_local.y < S[0].y - SLAB || _local.y > S[S.length - 1].y + SLAB) continue;
      let k = 0; while (k < S.length - 1 && S[k + 1].y < _local.y) k++;
      const s0 = S[k], s1 = S[Math.min(k + 1, S.length - 1)], t = s1 === s0 ? 0 : Math.max(0, Math.min(1, (_local.y - s0.y) / (s1.y - s0.y)));
      const cx = s0.cx + (s1.cx - s0.cx) * t, cz = s0.cz + (s1.cz - s0.cz) * t;
      const A = s0.a + (s1.a - s0.a) * t + r, B = s0.b + (s1.b - s0.b) * t + r;
      const dx = _local.x - cx, dz = _local.z - cz, dl = Math.hypot(dx, dz);
      if (dl < 1e-6) continue;
      const ux = dx / dl, uz = dz / dl, Rdir = 1 / Math.hypot(ux / A, uz / B), d = Rdir - dl;
      if (d > best) { best = d; hitWhat = R.bone; out.set(ux, 0, uz).transformDirection(_bm); }
    }
    if (P.head) {   // head ellipsoid in the head bone's frame
      const node = vrm.humanoid.getNormalizedBoneNode('head');
      if (node) {
        _bm.multiplyMatrices(inv, node.matrixWorld); _bmi.copy(_bm).invert();
        _local.copy(p).applyMatrix4(_bmi);
        const S = P.head.slabs, extra = hand ? ALLOW - HEAD_ALLOW : 0;   // the strict face contact is for the hand and fingers
        let sdfDone = false;
        // the distance field is for the hand and fingers; the forearm and upper arm keep the cross-sections, which push
        // them sideways (a forearm across a large head at Gokuraku 2 s was pushed up through it by the field's normal)
        if (P.head.sdf && hand) {
          const ds = sdfAt(P.head.sdf, _local.x, _local.y, _local.z, _g), gl = _g.length();
          if (gl > 0.3) {   // where the gradient is flat (a ridge of the distance field) the slabs give the direction
            sdfDone = true;
            const d = r - ds + extra;
            if (d > best) { best = d; hitWhat = 'head'; out.copy(_g).multiplyScalar(1 / gl).transformDirection(_bm); }
          }
        }
        if (sdfDone) { /* done */ } else if (S) {
          if (_local.y >= S[0].y - HEAD_SLAB && _local.y <= S[S.length - 1].y + HEAD_SLAB) {
            let k = 0; while (k < S.length - 1 && S[k + 1].y < _local.y) k++;
            const s0 = S[k], s1 = S[Math.min(k + 1, S.length - 1)], t = s1 === s0 ? 0 : Math.max(0, Math.min(1, (_local.y - s0.y) / (s1.y - s0.y)));
            const cx = s0.cx + (s1.cx - s0.cx) * t, cz = s0.cz + (s1.cz - s0.cz) * t;
            const A = s0.a + (s1.a - s0.a) * t + r, B = s0.b + (s1.b - s0.b) * t + r;
            const dx = _local.x - cx, dz = _local.z - cz, dl = Math.hypot(dx, dz);
            if (dl > 1e-6) {
              const ux = dx / dl, uz = dz / dl, d = 1 / Math.hypot(ux / A, uz / B) - dl + extra;
              if (d > best) { best = d; hitWhat = 'head'; out.set(ux, 0, uz).transformDirection(_bm); }
            }
          }
        } else {
          _local.sub(P.head.c);
          const A = P.head.r.x + r, B = P.head.r.y + r, C = P.head.r.z + r, dl = _local.length();
          if (dl > 1e-6) {
            const ux = _local.x / dl, uy = _local.y / dl, uz = _local.z / dl, Rdir = 1 / Math.hypot(ux / A, uy / B, uz / C), d = Rdir - dl + extra;
            if (d > best) { best = d; hitWhat = 'head'; out.set(ux, uy, uz).transformDirection(_bm); }
          }
        }
      }
      if (bonePos(vrm, 'neck', inv, _a) && bonePos(vrm, 'head', inv, _b)) {   // neck capsule
        segDist(p, _a, _b, _c);
        const dl = p.distanceTo(_c), d = P.neckR + r - dl;
        if (d > best && dl > 1e-6) { best = d; hitWhat = 'neck'; out.subVectors(p, _c).normalize(); }
      }
    }
    for (const s of ['left', 'right']) {
      if (!bonePos(vrm, s + 'UpperLeg', inv, _a) || !bonePos(vrm, s + 'LowerLeg', inv, _b)) continue;
      segDist(p, _a, _b, _c);
      const dl = p.distanceTo(_c), d = P[s].thigh + r - dl;
      if (d > best && dl > 1e-6) { best = d; hitWhat = s + 'Thigh'; out.subVectors(p, _c).normalize(); }
    }
    return best;
  }

  const _S = new THREE.Vector3(), _E = new THREE.Vector3(), _W = new THREE.Vector3(), _H = new THREE.Vector3(), _F = new THREE.Vector3(), _p = new THREE.Vector3(), _n = new THREE.Vector3(), _bn = new THREE.Vector3(), _ax = new THREE.Vector3();
  const _pq = new THREE.Quaternion(), _wq = new THREE.Quaternion(), _rq = new THREE.Quaternion(), _sq = new THREE.Quaternion();
  const TAU_IN = opts.tauIn ?? 0.06, TAU_OUT = opts.tauOut ?? 0.18;
  // the hand closing on the face moves steadily, so the push follows at once (0.004 s: 87 % per frame at 120 Hz); at 0.06 s the fingertips stayed
  // inside the jaw for half a second of Reze (the target grew faster than the push caught up)
  const TAU_IN_FACE = opts.tauInFace ?? 0.004;
  const corr = { left: new THREE.Quaternion(), right: new THREE.Quaternion() }, _q0 = new THREE.Quaternion(), _ct = new THREE.Quaternion();
  // what this module wrote last frame: three's AnimationMixer only writes a bone when its value changes, so on a held or
  // paused pose the upper arm still carries last frame's correction and must not be corrected again on top of it
  const lastOut = { left: new THREE.Quaternion(), right: new THREE.Quaternion() }, hasOut = { left: false, right: false }, _ci = new THREE.Quaternion();
  const qAngle = q => 2 * Math.acos(Math.min(1, Math.abs(q.w)));
  const FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Little'];
  const MAX_ELBOW = opts.maxElbow ?? 0.4;   // 手碰头时手肘最多改 23°
  const corrL = { left: new THREE.Quaternion(), right: new THREE.Quaternion() }, lastOutL = { left: new THREE.Quaternion(), right: new THREE.Quaternion() }, hasOutL = { left: false, right: false };
  const lastIn = { left: new THREE.Quaternion(), right: new THREE.Quaternion() }, lastInL = { left: new THREE.Quaternion(), right: new THREE.Quaternion() };
  const _q0L = new THREE.Quaternion(), _hx = new THREE.Vector3(), _t1 = new THREE.Vector3(), _t2 = new THREE.Vector3(), _fp = new THREE.Vector3();
  // hand sample points: [position, radius] for the palm, each finger's last joint and tip, the thumb's middle joint
  function handPoints(vrm, inv, s, R) {
    const out = [], h = vrm.humanoid;
    for (const f of FINGERS) {
      const dn = h.getNormalizedBoneNode(s + f + 'Distal'), pn = h.getNormalizedBoneNode(s + f + (f === 'Thumb' ? 'Proximal' : 'Intermediate'));
      if (!dn || !pn) continue;
      const d = new THREE.Vector3().setFromMatrixPosition(dn.matrixWorld).applyMatrix4(inv), q = _fp.setFromMatrixPosition(pn.matrixWorld).applyMatrix4(inv);
      out.push([d, 0.008], [d.clone().sub(q).multiplyScalar(0.8).add(d), 0.006]);
      if (f === 'Thumb') out.push([q.clone(), 0.009]);
    }
    for (const f of ['Index', 'Little']) {
      const n = h.getNormalizedBoneNode(s + f + 'Proximal'); if (!n) continue;
      out.push([_fp.setFromMatrixPosition(n.matrixWorld).applyMatrix4(inv).lerp(_W, 0.45).clone(), R.hand * 0.5]);
    }
    return out;
  }
  function apply(vrm, dt) {
    if (!P || !vrm?.humanoid) return;
    vrm.humanoid.normalizedHumanBonesRoot?.updateMatrixWorld?.(true);
    vrm.scene.updateMatrixWorld(true);
    const inv = sceneLocal(vrm).clone();
    vrm.scene.matrixWorld.decompose(_v, _sq, new THREE.Vector3());
    for (const s of ['left', 'right']) {
      const ua = vrm.humanoid.getNormalizedBoneNode(s + 'UpperArm'); if (!ua) continue;
      const la = vrm.humanoid.getNormalizedBoneNode(s + 'LowerArm');
      let total = 0, elbow = 0, faced = false; info.lastHit[s] = null; const tr = info.traceOn ? (info.trace ||= {}, info.trace[s] = []) : null;
      // a bone the animation did not write this frame still carries last frame's output (held or paused pose): take the
      // correction off again. Decided by which of last frame's input and output the bone is closer to; an exact-equality
      // test failed on a paused dance (the arm drifted ~0.9° a frame) and the correction never built up (Reze 7.5 s)
      if (dt > 0 && hasOut[s] && Math.abs(ua.quaternion.dot(lastOut[s])) > Math.abs(ua.quaternion.dot(lastIn[s]))) { ua.quaternion.premultiply(_ci.copy(corr[s]).invert()).normalize(); ua.updateMatrixWorld(true); }
      if (la && dt > 0 && hasOutL[s] && Math.abs(la.quaternion.dot(lastOutL[s])) > Math.abs(la.quaternion.dot(lastInL[s]))) { la.quaternion.premultiply(_ci.copy(corrL[s]).invert()).normalize(); la.updateMatrixWorld(true); }
      _q0.copy(ua.quaternion); if (la) _q0L.copy(la.quaternion);
      lastIn[s].copy(_q0); if (la) lastInL[s].copy(_q0L);
      for (let it = 0, nIt = ITER; it < nIt + 2; it++) {   // the last two steps only move the hand off the face
        if (!bonePos(vrm, s + 'UpperArm', inv, _S) || !bonePos(vrm, s + 'LowerArm', inv, _E) || !bonePos(vrm, s + 'Hand', inv, _W)) break;
        if (!bonePos(vrm, s + 'MiddleProximal', inv, _H)) _H.subVectors(_W, _E).normalize().multiplyScalar(0.07).add(_W);
        if (!bonePos(vrm, s + 'MiddleDistal', inv, _F)) _F.subVectors(_H, _W).multiplyScalar(0.8).add(_H);
        const R = P[s], pts = [[0.45, 0, R.upper], [0.75, 0, R.upper], [1, 0, (R.upper + R.lower) / 2], [0.35, 1, R.lower], [0.7, 1, R.lower], [1, 1, R.lower * 0.9], [0.6, 2, R.hand],
          [1, 2, R.hand * 0.6], [1, 3, R.hand * 0.4]];   // finger roots and fingertips
        let best = ALLOW, bp = null, handHead = false, bseg = 0, bwhat = '', armHead = null;
        const viol = [];   // hand points past their allowance on the face or neck: [point, normal, needed move, segment]
        const test = (p, r, seg, t) => {
          const d = penetration(vrm, inv, p, r, _n, seg >= 2);
          if (d > ALLOW) {
            const hh = seg >= 2 && (hitWhat === 'head' || hitWhat === 'neck');
            if (hh) { viol.push([p.clone(), _n.clone(), hitWhat === 'head' ? d - ALLOW + HEAD_ALLOW * 0.5 : d - ALLOW * 0.5, seg]); handHead = true; }
          }
          if (seg < 2 && (hitWhat === 'head' || hitWhat === 'neck') && d > ALLOW && (!armHead || d > armHead[2])) armHead = [p.clone(), _n.clone(), d];
          if (d > best) { best = d; bp = [p.clone(), _n.clone()]; bseg = seg; bwhat = hitWhat; if (it === 0) info.lastHit[s] = { seg, t, d: +d.toFixed(3), what: hitWhat }; }
        };
        for (const [t, seg, r] of pts) {
          if (seg === 0) _p.lerpVectors(_S, _E, t); else if (seg === 1) _p.lerpVectors(_E, _W, t); else if (seg === 2) _p.lerpVectors(_W, _H, t); else _p.lerpVectors(_H, _F, t);
          test(_p, r, seg, t);
        }
        if (P.head?.sdf) for (const [p, r] of handPoints(vrm, inv, s, R)) test(p, r, 4, 1);   // every finger, against the head surface
        if (!bp) break;
        // order: the arm through the head first (a forearm across the head at Gokuraku 2 s), then the hand on the face,
        // then soft contacts (sleeve against the chest)
        let armFirst = false;
        if (armHead && (!handHead || armHead[2] - ALLOW * 0.5 > Math.max(...viol.map(v_ => v_[2])))) {
          bp = [armHead[0], armHead[1]]; best = armHead[2]; armFirst = true;
        }
        if (handHead && la && !armFirst) {
          faced = true;
          // the hand against the face or neck comes first, even when the upper arm is deeper in the chest (pushing off the
          // chest first pushed the hand back into the face, Reze 7.4 s). The deepest touching hand point moves along its
          // normal by the upper arm (turning about the axis that moves it most) and the elbow together, least squares:
          // the upper arm alone cannot move a hand that comes up from below the chin (the move is along the arm).
          if (it < ITER) nIt = ITER + 3;
          let k = 0; for (let i = 1; i < viol.length; i++) if (viol[i][2] > viol[k][2]) k = i;
          const [hp, hn, need, hseg] = viol[k];
          _ax.subVectors(hp, _S).cross(hn);
          const eu = _ax.length();
          _hx.subVectors(_E, _S).cross(_t1.subVectors(_W, _E));
          const bend = _t1.angleTo(_t2.subVectors(_E, _S));
          let ee = 0;
          if (_hx.lengthSq() > 1e-8 && hseg >= 1) { _hx.normalize(); ee = _t2.crossVectors(_hx, _t1.subVectors(hp, _E)).dot(hn); }
          const den = eu * eu + ee * ee; if (den < 1e-10 || need <= 0) break;
          const tu = Math.min(MAX_STEP, MAX_HEAD - total, eu * need / den);
          let te = Math.max(-MAX_STEP, Math.min(MAX_STEP, ee * need / den));
          te = te > 0 ? Math.min(te, Math.max(0, 2.5 - bend)) : Math.max(te, Math.min(0, 0.15 - bend));   // elbow stays within 9°..143°
          te = Math.sign(te) * Math.min(Math.abs(te), Math.max(0, MAX_ELBOW - elbow));
          if (tr) tr.push({ it, n: viol.length, need: +need.toFixed(4), eu: +eu.toFixed(3), ee: +ee.toFixed(3), bend: +(bend * 57.3).toFixed(1), tu: +(tu * 57.3).toFixed(1), te: +(te * 57.3).toFixed(1), total: +(total * 57.3).toFixed(1) });
          if (tu <= 1e-4 && Math.abs(te) <= 1e-4) break;
          if (Math.abs(te) > 1e-4) {
            elbow += Math.abs(te);
            _rq.setFromAxisAngle(_bn.copy(_hx).applyQuaternion(_sq), te);
            la.getWorldQuaternion(_wq); la.parent.getWorldQuaternion(_pq);
            la.quaternion.copy(_pq.invert().multiply(_rq.multiply(_wq))); la.updateMatrixWorld(true);
          }
          if (tu > 1e-4) {
            total += tu; _ax.normalize();
            _rq.setFromAxisAngle(_bn.copy(_ax).applyQuaternion(_sq), tu);
            ua.getWorldQuaternion(_wq); ua.parent.getWorldQuaternion(_pq);
            ua.quaternion.copy(_pq.invert().multiply(_rq.multiply(_wq))); ua.updateMatrixWorld(true);
          }
          continue;
        }
        if (it >= nIt) break;
        if (tr) tr.push({ it, torso: bwhat, best: +best.toFixed(4) });
        const v = bp[0].sub(_S), L = v.length();
        _ax.crossVectors(v, bp[1]); if (_ax.lengthSq() < 1e-10 || L < 1e-4) break;
        _ax.normalize();
        const ang = Math.min(MAX_STEP, (handHead || armFirst ? MAX_HEAD : MAX_TOTAL) - total, Math.atan2(best - ALLOW * 0.5, L));
        if (ang <= 1e-4) break;
        total += ang;
        // 绕肩、在场景坐标里转 ang：q_world' = R · q_world → 本地 = parent⁻¹ · q_world'
        _rq.setFromAxisAngle(_bn.copy(_ax).applyQuaternion(_sq), ang);
        ua.getWorldQuaternion(_wq); ua.parent.getWorldQuaternion(_pq);
        ua.quaternion.copy(_pq.invert().multiply(_rq.multiply(_wq)));
        ua.updateMatrixWorld(true);
      }
      info.lastAngle[s] = +(total * 180 / Math.PI).toFixed(1);
      info.lastElbow ||= {}; info.lastElbow[s] = +(elbow * 180 / Math.PI).toFixed(1);
      if (dt > 0) {
        // target correction in the shoulder's frame: q' = C · q0
        _ct.copy(ua.quaternion).multiply(_pq.copy(_q0).invert());
        const c = corr[s], tau = qAngle(_ct) > qAngle(c) ? (faced ? TAU_IN_FACE : TAU_IN) : TAU_OUT;
        c.slerp(_ct, 1 - Math.exp(-dt / tau)).normalize();
        ua.quaternion.copy(c).multiply(_q0).normalize(); ua.updateMatrixWorld(true);
        lastOut[s].copy(ua.quaternion); hasOut[s] = true;
        info.applied ||= {}; info.applied[s] = +(qAngle(c) * 180 / Math.PI).toFixed(1);
        if (la) {   // the elbow's share, in the upper arm's frame, smoothed the same way
          _ct.copy(la.quaternion).multiply(_pq.copy(_q0L).invert());
          const cl = corrL[s], tl = qAngle(_ct) > qAngle(cl) ? (faced ? TAU_IN_FACE : TAU_IN) : TAU_OUT;
          cl.slerp(_ct, 1 - Math.exp(-dt / tl)).normalize();
          la.quaternion.copy(cl).multiply(_q0L).normalize(); la.updateMatrixWorld(true);
          lastOutL[s].copy(la.quaternion); hasOutL[s] = true;
          info.appliedElbow ||= {}; info.appliedElbow[s] = +(qAngle(cl) * 180 / Math.PI).toFixed(1);
        }
      }
    }
    shoulderShapes(vrm, inv);
  }

  // 关节修正形态（work/shoulder_fix.py 生成的 corrShoulderUpL/R、corrShoulderDownL/R、corrKneeL/R）：肩按上臂相对上胸的仰角、膝按弯曲角混入。
  // 修正量是双四元数蒙皮和线性蒙皮在关键角度（上 70°、下 75°）的差，小角度时差值约按角度平方增长，所以权重取平方。
  const UP_KEY = 70 * Math.PI / 180, DOWN_KEY = 75 * Math.PI / 180;
  const _cq = new THREE.Quaternion(), _dir = new THREE.Vector3();
  function shoulderShapes(vrm, inv) {
    const em = vrm.expressionManager; if (!em) return;
    const chest = vrm.humanoid.getNormalizedBoneNode('upperChest') || vrm.humanoid.getNormalizedBoneNode('chest');
    if (!chest) return;
    chest.getWorldQuaternion(_cq).invert();
    for (const [s, k] of [['left', 'L'], ['right', 'R']]) {
      const up = em.getExpression('corrShoulderUp' + k), down = em.getExpression('corrShoulderDown' + k);
      if (!up && !down) continue;
      const a = vrm.humanoid.getNormalizedBoneNode(s + 'UpperArm'), b = vrm.humanoid.getNormalizedBoneNode(s + 'LowerArm');
      if (!a || !b) continue;
      _dir.setFromMatrixPosition(b.matrixWorld).sub(_v.setFromMatrixPosition(a.matrixWorld)).normalize().applyQuaternion(_cq);
      const elev = Math.asin(Math.max(-1, Math.min(1, _dir.y)));
      const wUp = Math.min(1, Math.max(0, elev / UP_KEY)) ** 2, wDown = Math.min(1, Math.max(0, -elev / DOWN_KEY)) ** 2;
      if (up) em.setValue('corrShoulderUp' + k, wUp);
      if (down) em.setValue('corrShoulderDown' + k, wDown);
      info.shoulder ||= {}; info.shoulder[s] = { elev: +(elev * 180 / Math.PI).toFixed(1), up: +wUp.toFixed(2), down: +wDown.toFixed(2) };
    }
    // 11-18: knees (corrKneeL/R, key pose 110 deg of flexion): weight by the angle between thigh and shin, squared
    for (const [s, k] of [['left', 'L'], ['right', 'R']]) {
      if (!em.getExpression('corrKnee' + k)) continue;
      const u = vrm.humanoid.getNormalizedBoneNode(s + 'UpperLeg'), l = vrm.humanoid.getNormalizedBoneNode(s + 'LowerLeg'), f = vrm.humanoid.getNormalizedBoneNode(s + 'Foot');
      if (!u || !l || !f) continue;
      _dir.setFromMatrixPosition(l.matrixWorld).sub(_v.setFromMatrixPosition(u.matrixWorld)).normalize();
      _kn.setFromMatrixPosition(f.matrixWorld).sub(_v.setFromMatrixPosition(l.matrixWorld)).normalize();
      const bend = Math.acos(Math.max(-1, Math.min(1, _dir.dot(_kn))));
      const w = Math.min(1, bend / KNEE_KEY) ** 2;
      em.setValue('corrKnee' + k, w);
      info.knee ||= {}; info.knee[s] = { bend: +(bend * 180 / Math.PI).toFixed(1), w: +w.toFixed(2) };
    }
    // 11-26: elbows (corrElbowL/R, key pose 110 deg of flexion), weighted the same way
    for (const [s, k] of [['left', 'L'], ['right', 'R']]) {
      if (!em.getExpression('corrElbow' + k)) continue;
      const u = vrm.humanoid.getNormalizedBoneNode(s + 'UpperArm'), l = vrm.humanoid.getNormalizedBoneNode(s + 'LowerArm'), h = vrm.humanoid.getNormalizedBoneNode(s + 'Hand');
      if (!u || !l || !h) continue;
      _dir.setFromMatrixPosition(l.matrixWorld).sub(_v.setFromMatrixPosition(u.matrixWorld)).normalize();
      _kn.setFromMatrixPosition(h.matrixWorld).sub(_v.setFromMatrixPosition(l.matrixWorld)).normalize();
      const bend = Math.acos(Math.max(-1, Math.min(1, _dir.dot(_kn))));
      const w = Math.min(1, bend / ELBOW_KEY) ** 2;
      em.setValue('corrElbow' + k, w);
      info.elbow ||= {}; info.elbow[s] = { bend: +(bend * 180 / Math.PI).toFixed(1), w: +w.toFixed(2) };
    }
  }
  const KNEE_KEY = 110 * Math.PI / 180, ELBOW_KEY = 110 * Math.PI / 180, _kn = new THREE.Vector3();
  return { setup, apply, info };
}
