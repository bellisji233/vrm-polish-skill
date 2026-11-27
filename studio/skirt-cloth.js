// 裙摆骨骼布料（2026-11-18）
// 弹簧骨把每条裙摆链当成互不相干的摆锤：膝盖顶上来时两条链各自往两边让，中间的布被撕开；膝盖一帧扫过时链子被推到
// 腿后面卡住。成熟做法是把整圈裙摆链当成一块布来解（MagicaCloth 的骨骼布料）：
//   粒子 = 每条链的每个关节（第 0 节钉在腰上，跟动画走），
//   约束 = 链内每节长度固定；相邻链同一层的距离在 [COMPRESS, STRETCH] 倍静止距离之间；腿的胶囊/球碰撞；
//          「背面限位」——粒子只能待在大腿朝向自己裙根的一侧（站立时腿前面，深蹲时大腿上面），
//   每帧 Verlet 积分（重力、阻尼、按静止形状回拉）后迭代 ITER 轮，再把粒子写回骨骼旋转。
// 静止形状跟腿走：前片按方位角部分跟随同侧大腿转动（MMD 模型裙前骨骼「付与」大腿旋转的做法），膝盖以上的粒子回拉强，
//   以下回拉很弱、主要靠重力垂下——深蹲时裙子搭在大腿上、从膝盖垂下，而不是被拉回站立形状、夹进腿里。
// 碰撞和背面限位的修正不计入速度（同时移动上一帧位置），否则膝盖一顶，布被瞬间推出去会飞起来。
// 边碰撞（11-18）：只查粒子时，两个粒子之间那段布会整段穿过腿（每节 9–18 cm）；竖向每一节和横向相邻链之间的连线
//   都按线段对胶囊求最近点，把线段推出去，相当于整块布参与碰撞（MagicaCloth 的 edge collision）。
// 地面：裙摆不低于模型所站的地面（深蹲时下摆落地）。
// 手臂（11-19）：模型文件里的前臂碰撞体放歪了（中心偏离前臂 13 cm、半径 16 cm，手臂垂下时正好在胯侧），手一放下裙子就被
//   撑起来、贴着手抖（用户：做动作裙子会飞起来、手边的裙子奇怪地抖动）。改为按骨骼位置自建前臂和手的胶囊，
//   并且只往身体一侧推：手在裙子外面按住裙子，裙子不会翻到手上面被托起来；之后再做腿的碰撞，腿优先。
// 胯部（11-19）：腿的胶囊从胯关节往下才有，胯部中间是空的。踢腿加跳跃时，腿一扫把粒子推进两腿之间、胯部里面，
//   链子在身体里缠成一团，腿的碰撞又把它们卡住，站着也下不来（用户截图：做完动作裙子一侧一直掀着；实测缠住时每帧
//   上千次边碰撞）。每个粒子到胯部竖轴（静止时的竖直方向，跟胯骨转）的水平距离不小于静止时的 CORE 倍，最后做，身体优先。
// 翻起上限（11-19）：极乐净土 11.5 s 右腿高抬到 80°、同时起跳，前片被甩过头顶（与竖直向下成 159°）。每个粒子相对裙根的方向
//   与胯部向下方向的夹角不超过 MAX_LIFT：大腿抬平时裙子搭在腿上（约 90°），不会被甩到朝天。
// 只接管骨骼名以 Skirt 开头的弹簧骨；三-vrm 对这些关节的 update 被关掉，其余弹簧骨（头发、丝带）不变。
// createSkirtCloth(THREE, opts) → { setup(vrm), info }
export function createSkirtCloth(THREE, opts = {}) {
  const cfg = {
    iter: opts.iter ?? 8,
    gravity: opts.gravity ?? 9.8,      // m/s²；6.0 时深蹲后裙子堆在一侧、落得慢
    drag: opts.drag ?? 0.12,           // 每步速度损失；0.3 时裙子下落太慢、被膝盖顶起后飘着下不来（「像被风吹」的真因是步长不固定，已改固定步长）
    shape: opts.shape ?? 0.08,         // 每帧回拉到静止形状的比例（膝盖以上）
    shapeLow: opts.shapeLow ?? 0.012,  // 膝盖以下
    follow: opts.follow ?? 0.8,        // 正前方的链跟随大腿转动的比例，向两侧按 cos(方位角) 减到 0，后片不跟
    stretch: opts.stretch ?? 1.45,     // 相邻链最多拉开到静止距离的倍数（膝盖抬起时裙摆周长要能变大）
    compress: opts.compress ?? 0.45,
    margin: 0.03,
    edges: opts.edges ?? true,
    backstopOn: opts.backstop ?? false,   // 背面限位会把前片硬推到大腿上面，抬腿舞里裙子一直掀着；默认关
    arms: opts.arms ?? true,
    core: opts.core ?? 0.6,               // 胯部：到竖轴的距离不小于静止时的倍数（0 关闭）
    maxLift: opts.maxLift ?? 105,         // 度，相对胯部向下方向
    foreR: opts.foreR ?? 0.045,           // 前臂（含贴身的袖子）
    handR: opts.handR ?? 0.03,
  };
  const info = { chains: 0, particles: 0, links: 0, backstops: 0, edgeHits: 0, armHits: 0, coreHits: 0, liftHits: 0, active: false };
  let S = null;
  const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3(), _d = new THREE.Vector3(), _ax = new THREE.Vector3();
  const _m = new THREE.Matrix4(), _q = new THREE.Quaternion();

  function setup(vrm) {
    S = null; info.active = false;
    const mgr = vrm?.springBoneManager; if (!mgr?.joints) return;
    const sk = [...mgr.joints].filter(j => /^Skirt/i.test(j.bone?.name || ''));
    if (sk.length < 6) return;
    vrm.scene.updateMatrixWorld(true);
    const parentOf = new Map(); for (const j of sk) for (const k of sk) if (k.child === j.bone) parentOf.set(j, k);
    const roots = sk.filter(j => !parentOf.has(j));
    const inv = new THREE.Matrix4().copy(vrm.scene.matrixWorld).invert();
    const hips = vrm.humanoid?.getNormalizedBoneNode('hips');
    const hp = hips ? hips.getWorldPosition(new THREE.Vector3()).applyMatrix4(inv) : new THREE.Vector3();
    const leg = side => vrm.humanoid?.getRawBoneNode(side + 'UpperLeg');
    const knee = side => vrm.humanoid?.getRawBoneNode(side + 'LowerLeg');
    const legs = ['left', 'right'].map(sd => leg(sd)).filter(Boolean);
    const legRest = legs.map(b => b.matrixWorld.clone().invert());
    const legX = legs.map(b => b.getWorldPosition(new THREE.Vector3()).applyMatrix4(inv).x);
    const kneeY = Math.min(...['left', 'right'].map(sd => knee(sd)).filter(Boolean).map(b => b.getWorldPosition(new THREE.Vector3()).applyMatrix4(inv).y));
    const chains = roots.map(r => {
      const joints = [r]; let cur = r;
      for (let g = 0; g < 12; g++) { const nx = sk.find(k => parentOf.get(k) === cur); if (!nx) break; joints.push(nx); cur = nx; }
      const tailOf = j => j.child ? j.child.getWorldPosition(new THREE.Vector3()) : j.bone.localToWorld(j._initialLocalChildPosition.clone());
      const P = [r.bone.getWorldPosition(new THREE.Vector3()), ...joints.map(tailOf)];
      const L = P.map((p, i) => i ? p.distanceTo(P[i - 1]) : 0);
      // rest positions in the space of the root bone's parent (the shape the chain springs back to)
      const pinv = new THREE.Matrix4().copy(r.bone.parent.matrixWorld).invert();
      const restLocal = P.map(p => p.clone().applyMatrix4(pinv));
      const p0 = P[0].clone().applyMatrix4(inv);
      // colliders this chain reacts to: those of its joints' groups (legs, knee spheres, the kit's guards); not inside shapes
      // the kit's per-chain guard spheres (radius ~0.45, parented to the thigh) rise with a lifted knee and shove the whole
      // front of the skirt up; leg capsules, knee spheres and arm colliders are enough for the cloth
      const isArm = c => /arm|hand|wrist|elbow|finger/i.test(c.parent?.name || '') && !/leg/i.test(c.parent?.name || '');
      const cols = new Set(); for (const j of joints) for (const g of j.colliderGroups) for (const c of g.colliders) if (!c.shape?.inside && !isArm(c) && !(c.shape?.type === 'sphere' && c.shape.radius > (opts.maxSphere ?? 0.2))) cols.add(c);
      const az = Math.atan2(p0.x - hp.x, p0.z - hp.z);
      // leg weights: front chains follow the thigh on their side, the centre chain both halves
      let wl = 0, wr = 0;
      if (legs.length === 2 && Math.cos(az) > 0) {
        const f = cfg.follow * Math.pow(Math.cos(az), 1.5), mid = (legX[0] + legX[1]) / 2, half = Math.abs(legX[0] - mid) || 0.08;
        const t = Math.max(-1, Math.min(1, (p0.x - mid) / half * Math.sign(legX[0] - mid)));
        const sl = 0.5 + 0.5 * t; wl = f * sl; wr = f * (1 - sl);
      }
      const restWorld = P.map(p => p.clone());
      const kneeLift = opts.kneeLift ?? 0.04;   // the strong shape pull ends this far below the knee (negative = above); -0.1 left the skirt hiked up after a squat
      const above = P.map(p => { const y = p.clone().applyMatrix4(inv).y; return Math.max(0, Math.min(1, (y - kneeY + kneeLift) / 0.12)); });
      const legCols = [...cols].filter(c_ => /leg|knee|thigh|shin/i.test(c_.parent?.name || '') || /leg/i.test(c_.parent?.parent?.name || ''));
      return { root: r, joints, P, Q: P.map(p => p.clone()), L, restLocal, restWorld, above, wl, wr, az, cols: [...cols], legCols, hit: r.settings.hitRadius || 0.02 };
    }).filter(c => c.joints.length >= 2).sort((a, b) => a.az - b.az);
    if (chains.length < 3) return;
    // ring links between neighbours, not across a wide gap (an open skirt)
    const gaps = chains.map((c, i) => { let g = chains[(i + 1) % chains.length].az - c.az; if (g <= 0) g += Math.PI * 2; return g; });
    const med = [...gaps].sort((a, b) => a - b)[gaps.length >> 1];
    const links = [];
    chains.forEach((c, i) => {
      if (gaps[i] > med * 2.5) return;
      const n = chains[(i + 1) % chains.length], depth = Math.min(c.P.length, n.P.length);
      for (let k = 1; k < depth; k++) links.push({ a: c, b: n, k, rest: c.P[k].distanceTo(n.P[k]) });
    });
    // take the joints over from three-vrm
    for (const c of chains) for (const j of c.joints) { j.__clothUpdate = j.update; j.update = () => {}; }
    if (!mgr.__clothWrapped) {
      const origUpdate = mgr.update.bind(mgr), origReset = mgr.reset.bind(mgr);
      mgr.update = delta => { origUpdate(delta); if (mgr.__cloth) mgr.__cloth.step(delta); };
      mgr.reset = () => { origReset(); if (mgr.__cloth) mgr.__cloth.reset(); };
      mgr.__clothWrapped = true;
    }
    const raw = n => vrm.humanoid?.getRawBoneNode(n);
    const arms = ['left', 'right'].map(sd => ({ lo: raw(sd + 'LowerArm'), hand: raw(sd + 'Hand'), tip: raw(sd + 'MiddleDistal') || raw(sd + 'MiddleIntermediate') || raw(sd + 'MiddleProximal') }))
      .filter(a => a.lo && a.hand).map(a => ({ ...a, pLo: new THREE.Vector3(), pHand: new THREE.Vector3(), pTip: new THREE.Vector3() }));
    const hipsRaw = vrm.humanoid?.getRawBoneNode('hips');
    if (hipsRaw) {   // rest distance of every particle from the hips' vertical axis, and its direction (hips local)
      const hinv = new THREE.Matrix4().copy(hipsRaw.matrixWorld).invert();
      const q = hipsRaw.getWorldQuaternion(new THREE.Quaternion()).invert();
      upL.set(0, 1, 0).applyQuaternion(q).normalize();   // world up at rest, in the hips' frame
      const radial = (l, out) => out.copy(l).addScaledVector(upL, -l.dot(upL));
      for (const c of chains) {
        c.rr = c.P.map(p => radial(p.clone().applyMatrix4(hinv), _a).length());
        const r = radial(c.P[c.P.length - 1].clone().applyMatrix4(hinv), new THREE.Vector3()); c.dir = r.lengthSq() > 1e-10 ? r.normalize() : new THREE.Vector3(1, 0, 0);
      }
    }
    S = { vrm, chains, links, legs, legRest, floor: -1e9, arms, hips: hipsRaw, axis: new THREE.Vector3(), hinv: new THREE.Matrix4() };
    mgr.__cloth = { step, reset };
    info.chains = chains.length; info.particles = chains.reduce((s, c) => s + c.P.length - 1, 0); info.links = links.length; info.active = true;
  }

  function reset() {
    if (!S) return;
    for (const c of S.chains) {
      c.root.bone.parent.updateWorldMatrix(true, false);
      for (let k = 0; k < c.P.length; k++) { c.P[k].copy(c.restLocal[k]).applyMatrix4(c.root.bone.parent.matrixWorld); c.Q[k].copy(c.P[k]); }
      writeBones(c);
    }
  }

  function capsulePush(col, p, r) {
    const m = col.colliderMatrix, sh = col.shape;
    _a.setFromMatrixPosition(m);
    if (sh.type === 'sphere') { _c.copy(_a); }   // sphere: the collider matrix already carries the offset (as in three-vrm)
    else {
      _b.subVectors(sh.tail, sh.offset).applyMatrix4(m);
      _ax.subVectors(_b, _a); const L2 = _ax.lengthSq();
      let t = L2 > 0 ? _d.subVectors(p, _a).dot(_ax) / L2 : 0; t = Math.max(0, Math.min(1, t));
      _c.copy(_a).addScaledVector(_ax, t);
    }
    const R = sh.radius + r;
    _d.subVectors(p, _c); const dl = _d.length();
    if (dl < R && dl > 1e-6) p.addScaledVector(_d, (R - dl) / dl);
    return sh.type === 'capsule';
  }
  // backstop: on a thigh, a particle stays on the side that faces its chain's root
  function backstop(col, p, root, r) {
    if (col.shape?.type !== 'capsule' || !/upper_?leg|thigh/i.test(col.parent?.name || '')) return;
    const m = col.colliderMatrix, sh = col.shape;
    _a.setFromMatrixPosition(m); _b.subVectors(sh.tail, sh.offset).applyMatrix4(m);
    _ax.subVectors(_b, _a); const L2 = _ax.lengthSq(); if (L2 < 1e-8) return;
    let t = _d.subVectors(p, _a).dot(_ax) / L2; t = Math.max(0, Math.min(1, t));
    _c.copy(_a).addScaledVector(_ax, t); _ax.normalize();
    const rp = _d.subVectors(p, _c); if (rp.length() > sh.radius + r + cfg.margin) return;
    rp.addScaledVector(_ax, -rp.dot(_ax));
    const rr = _b.subVectors(root, _c); rr.addScaledVector(_ax, -rr.dot(_ax));
    if (rr.lengthSq() < 1e-8 || rp.dot(rr) >= 0) return;
    p.copy(_c).addScaledVector(rr.normalize(), sh.radius + r + 0.005); info.backstops++;
  }

  // arm capsules from the bones: a particle inside one goes to the side facing the body's vertical axis
  const _h = new THREE.Vector3(), _r = new THREE.Vector3();
  function segPush(p, a, b, R) {
    _ax.subVectors(b, a); const L2 = _ax.lengthSq();
    const t = L2 > 1e-10 ? Math.max(0, Math.min(1, _r.subVectors(p, a).dot(_ax) / L2)) : 0;
    _c.copy(a).addScaledVector(_ax, t);
    _r.subVectors(p, _c); if (_r.lengthSq() >= R * R) return;
    _h.set(S.axis.x - _c.x, 0, S.axis.z - _c.z); const hl = _h.length(); if (hl < 1e-6) return; _h.multiplyScalar(1 / hl);
    const o = _r.dot(_h); if (o < 0) _r.addScaledVector(_h, -2 * o);
    const rl = _r.length(); if (rl < 1e-6) _r.copy(_h); else _r.multiplyScalar(1 / rl);
    p.copy(_c).addScaledVector(_r, R); info.armHits++;
  }
  function armPush(p, r) {
    for (const a of S.arms) { segPush(p, a.pLo, a.pHand, cfg.foreR + r); if (a.tip) segPush(p, a.pHand, a.pTip, cfg.handR + r); }
  }
  // the pelvis: no particle closer to the hips' vertical axis than CORE × its rest distance
  const _l = new THREE.Vector3(), _rad = new THREE.Vector3(), upL = new THREE.Vector3(0, 1, 0), _l0 = new THREE.Vector3();
  function corePush(c, k, p) {
    _l.copy(p).applyMatrix4(S.hinv); const h = _l.dot(upL); _rad.copy(_l).addScaledVector(upL, -h);
    const d = _rad.length(), m = cfg.core * c.rr[k];
    if (d >= m) return;
    if (d > 1e-5) _rad.multiplyScalar(m / d); else _rad.copy(c.dir).multiplyScalar(m);
    p.copy(_rad).addScaledVector(upL, h).applyMatrix4(S.hips.matrixWorld); info.coreHits++;
  }
  // a particle's direction from the chain root stays within MAX_LIFT of the hips' down direction
  function liftCap(c, k, p) {
    _l0.copy(c.P[0]).applyMatrix4(S.hinv); _l.copy(p).applyMatrix4(S.hinv).sub(_l0);
    const len = _l.length(); if (len < 1e-6) return;
    const down = -_l.dot(upL) / len, lim = Math.cos(cfg.maxLift * Math.PI / 180);
    if (down >= lim) return;
    _rad.copy(_l).addScaledVector(upL, -_l.dot(upL)); const rl = _rad.length();
    if (rl < 1e-6) _rad.copy(c.dir); else _rad.multiplyScalar(1 / rl);
    const sn = Math.sqrt(1 - lim * lim);
    _l.copy(_rad).multiplyScalar(sn * len).addScaledVector(upL, -lim * len).add(_l0);
    p.copy(_l).applyMatrix4(S.hips.matrixWorld); info.liftHits++;
  }
  const _t1 = new THREE.Vector3(), _mm = new THREE.Matrix4();
  // rest position of particle k carried by the hips, blended with the same point carried rigidly by each thigh
  function target(c, k, parent, out) {
    out.copy(c.restLocal[k]).applyMatrix4(parent.matrixWorld);
    const w = [c.wl, c.wr], wsum = c.wl + c.wr; if (!(wsum > 0)) return out;
    out.multiplyScalar(1 - wsum);
    for (let i = 0; i < 2; i++) {
      if (!w[i]) continue;
      _mm.multiplyMatrices(S.legs[i].matrixWorld, S.legRest[i]);
      out.addScaledVector(_t1.copy(c.restWorld[k]).applyMatrix4(_mm), w[i]);
    }
    return out;
  }
  // closest points between segment p0p1 and segment q0q1 → returns [s, t] (params on each)
  function segSeg(p0, p1, q0, q1) {
    const d1 = _e1.subVectors(p1, p0), d2 = _e2.subVectors(q1, q0), r = _e3.subVectors(p0, q0);
    const a = d1.dot(d1), e = d2.dot(d2), f = d2.dot(r);
    let s_, t_;
    if (a < 1e-10 && e < 1e-10) return [0, 0];
    if (a < 1e-10) { s_ = 0; t_ = Math.min(1, Math.max(0, f / e)); }
    else {
      const c = d1.dot(r);
      if (e < 1e-10) { t_ = 0; s_ = Math.min(1, Math.max(0, -c / a)); }
      else {
        const b = d1.dot(d2), den = a * e - b * b;
        s_ = den > 1e-10 ? Math.min(1, Math.max(0, (b * f - c * e) / den)) : 0;
        t_ = (b * s_ + f) / e;
        if (t_ < 0) { t_ = 0; s_ = Math.min(1, Math.max(0, -c / a)); }
        else if (t_ > 1) { t_ = 1; s_ = Math.min(1, Math.max(0, (b - c) / a)); }
      }
    }
    return [s_, t_];
  }
  const _e1 = new THREE.Vector3(), _e2 = new THREE.Vector3(), _e3 = new THREE.Vector3(), _q0 = new THREE.Vector3(), _q1 = new THREE.Vector3(), _cp = new THREE.Vector3(), _cq = new THREE.Vector3(), _nn = new THREE.Vector3();
  // push segment (pa, pb) out of a collider; pinned endpoints do not move. qa/qb are the previous positions (no speed gained)
  function edgePush(col, pa, pb, qa, qb, r, pinA) {
    const m = col.colliderMatrix, sh = col.shape;
    _q0.setFromMatrixPosition(m);
    if (sh.type === 'sphere') _q1.copy(_q0); else _q1.subVectors(sh.tail, sh.offset).applyMatrix4(m);
    const [s_, t_] = segSeg(pa, pb, _q0, _q1);
    _cp.lerpVectors(pa, pb, s_); _cq.lerpVectors(_q0, _q1, t_);
    _nn.subVectors(_cp, _cq); const d = _nn.length(), R = sh.radius + r;
    if (d >= R || d < 1e-6) return;
    _nn.multiplyScalar(1 / d); const depth = R - d;
    const wa = pinA ? 0 : 1 - s_, wb = s_, den = wa * wa + wb * wb; if (den < 1e-6) return;
    const k = depth / den;
    if (wa) { pa.addScaledVector(_nn, k * wa); qa.addScaledVector(_nn, k * wa); }
    pb.addScaledVector(_nn, k * wb); qb.addScaledVector(_nn, k * wb);
    info.edgeHits++;
  }
  function writeBones(c) {
    for (let k = 0; k < c.joints.length; k++) {
      const j = c.joints[k], bone = j.bone, parent = bone.parent;
      const pmw = parent.matrixWorld;
      _m.multiplyMatrices(pmw, j._initialLocalMatrix).invert();
      _d.copy(c.P[k + 1]).applyMatrix4(_m).normalize();
      bone.quaternion.setFromUnitVectors(j._boneAxis, _d).premultiply(j._initialLocalRotation);
      bone.updateMatrix(); bone.matrixWorld.multiplyMatrices(pmw, bone.matrix);
    }
  }

  // Every frame steps at least once, in equal sub-steps no longer than 1/60 s, so a 120 Hz display gets 120 Hz cloth
  // (11-18: fixed 1/60 s steps updated the skirt every other frame and it moved in jerks while dancing). Verlet's
  // implied velocity is rescaled by the step ratio (time-corrected Verlet), so uneven frame times no longer feed
  // energy in (the earlier "wind"); drag and shape pull are per 1/60 s and converted to the actual step.
  const H = 1 / 60;
  function step(delta) {
    if (!S || !(delta > 0)) return;
    const d = Math.min(delta, 4 * H), n = Math.max(1, Math.ceil(d / H - 1e-6)), dt = d / n;
    for (let i = 0; i < n; i++) sub(dt);
    for (const c of S.chains) writeBones(c);
  }
  function sub(dt) {
    const g = cfg.gravity * dt * dt, ratio = S.lastDt ? Math.min(2, Math.max(0.5, dt / S.lastDt)) : 1; S.lastDt = dt;
    const k = dt * 60, keep = Math.pow(1 - cfg.drag, k);
    S.floor = S.vrm.scene.getWorldPosition(_t1).y + 0.004;
    if (cfg.arms) for (const a of S.arms) {
      (a.tip || a.hand).updateWorldMatrix(true, false);
      a.lo.getWorldPosition(a.pLo); a.hand.getWorldPosition(a.pHand); if (a.tip) a.tip.getWorldPosition(a.pTip);
    }
    if (S.hips) { S.hips.getWorldPosition(S.axis); S.hinv.copy(S.hips.matrixWorld).invert(); }
    for (const c of S.chains) {
      const parent = c.root.bone.parent; parent.updateWorldMatrix(true, false);
      const root = c.root.bone.getWorldPosition(_a);
      // a teleport (stage switch) moves the whole chain with the root instead of swinging it
      const jump = _b.subVectors(root, c.P[0]);
      if (jump.lengthSq() > 0.09) for (let k = 0; k < c.P.length; k++) { c.P[k].add(jump); c.Q[k].add(jump); }
      c.P[0].copy(root); c.Q[0].copy(root);
      const n = c.P.length - 1;
      for (let k = 1; k <= n; k++) {
        const p = c.P[k], q = c.Q[k];
        _c.subVectors(p, q).multiplyScalar(keep * ratio);
        q.copy(p);
        p.add(_c); p.y -= g;
        const s = 1 - Math.pow(1 - (cfg.shapeLow + (cfg.shape - cfg.shapeLow) * c.above[k]), dt * 60);
        target(c, k, parent, _d);
        p.lerp(_d, s);
      }
    }
    for (let it = 0; it < cfg.iter; it++) {
      for (const c of S.chains) for (let k = 1; k < c.P.length; k++) {   // inextensible chain, root first
        _d.subVectors(c.P[k], c.P[k - 1]); const dl = _d.length() || 1;
        c.P[k].copy(c.P[k - 1]).addScaledVector(_d, c.L[k] / dl);
      }
      for (const { a, b, k, rest } of S.links) {
        const pa = a.P[k], pb = b.P[k]; _d.subVectors(pb, pa); const dl = _d.length();
        if (dl < 1e-6) continue;
        const lo = rest * cfg.compress, hi = rest * cfg.stretch;
        const target = dl > hi ? hi : dl < lo ? lo : dl;
        if (target === dl) continue;
        const corr = (dl - target) * 0.5 / dl; pa.addScaledVector(_d, corr); pb.addScaledVector(_d, -corr);
      }
      for (const c of S.chains) for (let k = 1; k < c.P.length; k++) {
        const p = c.P[k]; _t1.copy(p);
        if (cfg.arms) armPush(p, c.hit);
        for (const col of c.cols) { capsulePush(col, p, c.hit); if (cfg.backstopOn) backstop(col, p, c.P[0], c.hit); }
        if (p.y < S.floor + c.hit) p.y = S.floor + c.hit;
        c.Q[k].add(_t1.subVectors(p, _t1));   // pushed out without picking up speed
      }
      // edges: chain segments and the ring links between neighbouring chains, against the leg colliders
      // not the top segment / top ring: they start at the waist and graze the round top of the thigh capsules at the
      // hip joint, which inflated the whole skirt even standing still (11-18)
      if (cfg.edges) for (const c of S.chains) for (let k = 2; k < c.P.length; k++)
        for (const col of c.legCols) edgePush(col, c.P[k - 1], c.P[k], c.Q[k - 1], c.Q[k], 0, false);
      if (cfg.edges) for (const { a, b, k } of S.links) if (k >= 2)
        for (const col of a.legCols) edgePush(col, a.P[k], b.P[k], a.Q[k], b.Q[k], 0, false);
      if (cfg.core > 0 && S.hips) for (const c of S.chains) if (c.rr) for (let k = 1; k < c.P.length; k++) {
        const p = c.P[k]; _t1.copy(p); corePush(c, k, p); if (cfg.maxLift < 180) liftCap(c, k, p); c.Q[k].add(_t1.subVectors(p, _t1));
      }
    }
    for (const c of S.chains)
      for (let k = 1; k < c.P.length; k++) { _d.subVectors(c.P[k], c.P[k - 1]); const dl = _d.length() || 1; c.P[k].copy(c.P[k - 1]).addScaledVector(_d, c.L[k] / dl); }
  }
  return { setup, info, cfg, debug: () => S };
}
