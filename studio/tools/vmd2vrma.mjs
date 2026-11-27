// VMD (MMD) → VRMA (VRMC_vrm_animation) 转换器 v2（2026-11-18）
// v1 见 vmd2vrma-v1-20261118.mjs。v2 改动：
//   1. 解足 IK：MMD 舞蹈的膝盖弯曲大多只存在「足ＩＫ」目标位置里（ひざ 没有关键帧），
//      v1 不解 IK，腿一直是直的。v2 在标准骨架上解两节腿 IK + つま先ＩＫ，烘焙成旋转。
//      VMD 末尾的 IK 开关按帧生效；没有开关段时，足ＩＫ有动画才算开启。
//   2. 根骨骼链：全ての親 → センター → グルーブ → 腰 → 上半身/下半身，位移和旋转都算；
//      下半身 带位移的骨架（米塔类）也能取到胯部位移。hips = 下半身 的世界旋转，
//      spine = 下半身⁻¹·上半身，骨盆跟下半身转。
//   3. 肩P/肩C（耸肩但手臂朝向不变）、手捩（v1 写成了不存在的「ひじ捩」）、足先EX（脚趾）。
//   4. VMD 贝塞尔插值（v1 是线性，稀疏关键帧的舞蹈会显得机械）。
//   5. 位移 z 轴按左手系→右手系翻转（v1 前后反了）。
// 用法: node vmd2vrma.mjs <in.vmd> <out.vrma> [--morph=表情.vmd] [--overlay=修正.vmd] [--ik=auto|on|off] [--k=0.078]
// --overlay：作者另附的修正动作（如 Reze 的 左腕修正用モーション.vmd），同一骨骼同一帧的关键帧以修正为准，和在 MMD 里
//   先读主动作再读修正动作相同。
import { readFileSync, writeFileSync } from 'node:fs';

const args = process.argv.slice(2);
const opt = {};
for (const a of args) { const m = a.match(/^--([a-z]+)=(.+)$/); if (m) opt[m[1]] = m[2]; }
const pos = args.filter(a => !a.startsWith('--'));
const inFile = pos[0], outFile = pos[1] || inFile.replace(/\.vmd$/i, '') + '.vrma';

const ARMDEG = +(opt.armdeg ?? 30);  // MMD 手臂 rest 与水平的夹角
const K = +(opt.k ?? 0.078);         // MMD 单位 → 米（标准骨架腿根高 0.843 m ≈ MMD 10.8）
const IKMODE = opt.ik || 'auto';
const DESPIKE = opt.despike !== '0';
const MAXDEG = +(opt.maxdeg ?? 40);  // 单帧最大旋转（度）。先去「出去又回来」的单帧尖刺，再按此限速；
                                     // v1 的 15°/帧 会把极乐净土这类利落的手部动作压软（每只手臂 50–80 帧被限）
const MAXPOS = +(opt.maxpos ?? 1.5); // 单帧最大位移（MMD 单位）；v1 的 0.5 会压掉快速踢腿
const PASSES = +(opt.passes ?? 2);
// 骨盆：full = hips 取下半身完整旋转；yaw = 只取绕竖轴的转向，前后左右倾斜留在大腿上。
// auto：下半身带位移的动捕类骨架（米塔等）用 yaw —— 这类数据下半身常年倾斜 12–20°，
// 骨盆跟着倾斜会让短裙后摆翘起；标准 MMD 骨架用 full（转身时骨盆要跟着转）。
const PELVIS = opt.pelvis || 'auto';

// ---------- 四元数 / 向量 ----------
const norm = q => { const l = Math.hypot(q[0], q[1], q[2], q[3]) || 1; return q.map(v => v / l); };
const qmul = (a, b) => [
  a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
  a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
  a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
  a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
];
const qconj = q => [-q[0], -q[1], -q[2], q[3]];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const scl = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const len = a => Math.hypot(a[0], a[1], a[2]);
const unit = a => scl(a, 1 / (len(a) || 1));
function qrot(q, v) {
  const u = [q[0], q[1], q[2]], uv = cross(u, v), uuv = cross(u, uv);
  return [v[0] + 2 * (q[3] * uv[0] + uuv[0]), v[1] + 2 * (q[3] * uv[1] + uuv[1]), v[2] + 2 * (q[3] * uv[2] + uuv[2])];
}
function qFromTo(a, b) {
  a = unit(a); b = unit(b);
  const d = dot(a, b);
  if (d > 0.999999) return [0, 0, 0, 1];
  if (d < -0.999999) {
    const c = unit(cross(a, Math.abs(a[0]) > 0.9 ? [0, 1, 0] : [1, 0, 0]));
    return [c[0], c[1], c[2], 0];
  }
  const c = cross(a, b);
  return norm([c[0], c[1], c[2], 1 + d]);
}
const qAxis = (ax, ang) => { const s = Math.sin(ang / 2); return [ax[0] * s, ax[1] * s, ax[2] * s, Math.cos(ang / 2)]; };
function qslerp(a, b, t) {
  let d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  let bb = b;
  if (d < 0) { d = -d; bb = b.map(v => -v); }
  if (d > 0.9995) return norm(a.map((v, i) => v + (bb[i] - v) * t));
  const th = Math.acos(Math.min(1, d)), s = Math.sin(th);
  const wa = Math.sin((1 - t) * th) / s, wb = Math.sin(t * th) / s;
  return norm(a.map((v, i) => v * wa + bb[i] * wb));
}
const qangle = (a, b) => 2 * Math.acos(Math.min(1, Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]))) * 180 / Math.PI;
// 刚体变换 {q, t}：x ↦ q·x + t
const compose = (A, B) => ({ q: qmul(A.q, B.q), t: add(qrot(A.q, B.t), A.t) });
const apply = (M, x) => add(qrot(M.q, x), M.t);
const IDT = { q: [0, 0, 0, 1], t: [0, 0, 0] };

// MMD 左手系（面 -Z，左 +X）→ VRM1 右手系（面 +Z，左 +X）：z 镜像（同 three.js MMDLoader）
const quatConv = ([x, y, z, w]) => norm([-x, -y, z, w]);
const posConv = ([x, y, z]) => [x, y, -z];

// ---------- 静止姿势对齐（与 v1 相同） ----------
// q_local = C_parent⁻¹ · q_mmd · C_bone，C = VRM 静止朝向 → MMD 静止朝向 的最小旋转
function restDirs(armDeg) {
  const A = armDeg * Math.PI / 180, c = Math.cos(A), s = Math.sin(A);
  const up = [0, 1, 0], down = [0, -1, 0], fwd = [0, 0, 1];
  return {
    hips: up, spine: up, chest: up, upperChest: up, neck: up, head: up,
    leftShoulder: [1, 0, 0], rightShoulder: [-1, 0, 0],
    leftUpperArm: [c, -s, 0], leftLowerArm: [c, -s, 0], leftHand: [c, -s, 0],
    rightUpperArm: [-c, -s, 0], rightLowerArm: [-c, -s, 0], rightHand: [-c, -s, 0],
    leftUpperLeg: down, leftLowerLeg: down, leftFoot: fwd, leftToes: fwd,
    rightUpperLeg: down, rightLowerLeg: down, rightFoot: fwd, rightToes: fwd,
  };
}

// ---------- VRM 骨骼层级 ----------
const PARENT = {
  hips: null, spine: 'hips', chest: 'spine', upperChest: 'chest', neck: 'upperChest', head: 'neck',
  leftShoulder: 'upperChest', leftUpperArm: 'leftShoulder', leftLowerArm: 'leftUpperArm', leftHand: 'leftLowerArm',
  rightShoulder: 'upperChest', rightUpperArm: 'rightShoulder', rightLowerArm: 'rightUpperArm', rightHand: 'rightLowerArm',
  leftUpperLeg: 'hips', leftLowerLeg: 'leftUpperLeg', leftFoot: 'leftLowerLeg', leftToes: 'leftFoot',
  rightUpperLeg: 'hips', rightLowerLeg: 'rightUpperLeg', rightFoot: 'rightLowerLeg', rightToes: 'rightFoot',
};
const ORDER = Object.keys(PARENT);
// 上半身/手臂/手指：VRM 骨 ← MMD 骨链（从父到子复合）。'!' 前缀 = 取逆（肩C 抵消 肩P）。
const MMD_CHAIN = {
  chest: ['上半身2'], neck: ['首'], head: ['頭'],
  leftShoulder: ['左肩P', '左肩'], leftUpperArm: ['!左肩P', '左腕'],
  // 手捩 一半给小臂、一半给手腕：VRM 没有前臂扭转骨，全放在手腕会拧成麻花
  leftLowerArm: ['左腕捩', '左ひじ', '½左手捩'], leftHand: ['½左手捩', '左ひじ捩', '左手首'],
  rightShoulder: ['右肩P', '右肩'], rightUpperArm: ['!右肩P', '右腕'],
  rightLowerArm: ['右腕捩', '右ひじ', '½右手捩'], rightHand: ['½右手捩', '右ひじ捩', '右手首'],
};
for (const [side, jp] of [['left', '左'], ['right', '右']]) {
  for (const [finger, source] of [['Thumb', '親指'], ['Index', '人指'], ['Middle', '中指'], ['Ring', '薬指'], ['Little', '小指']]) {
    const joints = finger === 'Thumb' ? ['Metacarpal', 'Proximal', 'Distal'] : ['Proximal', 'Intermediate', 'Distal'];
    joints.forEach((joint, i) => {
      const bone = side + finger + joint;
      PARENT[bone] = i === 0 ? side + 'Hand' : side + finger + joints[i - 1];
      ORDER.push(bone);
      MMD_CHAIN[bone] = [jp + source + (finger === 'Thumb' ? i : i + 1)];
    });
  }
}

// ---------- 标准骨架（skeleton.json → VRM1 轴，米） ----------
// skeleton.json 的 parent 字段是节点名，这里按 VRM 层级解析（v1 没解析父子，世界坐标是错的，
// 只是 v1 只用到 hips 的绝对位置所以没暴露）。
function buildSkeleton() {
  const raw = JSON.parse(readFileSync(new URL('./skeleton.json', import.meta.url)));
  const parentOf = b => PARENT[b] ?? (/Eye$/.test(b) ? 'head' : null);
  const world = {}, qworld = {};
  const resolve = b => {
    if (world[b]) return;
    const p = parentOf(b);
    if (!p || !raw[p]) { world[b] = raw[b].t; qworld[b] = raw[b].q; return; }
    resolve(p);
    world[b] = add(world[p], qrot(qworld[p], raw[b].t));
    qworld[b] = qmul(qworld[p], raw[b].q);
  };
  Object.keys(raw).forEach(resolve);
  const v1 = {};
  for (const b of Object.keys(raw)) v1[b] = [-world[b][0], world[b][1], -world[b][2]]; // 模型空间 → VRM1
  const skel = {};
  for (const b of Object.keys(raw)) {
    const p = parentOf(b);
    skel[b] = (p && v1[p] ? sub(v1[b], v1[p]) : v1[b]).map(v => +v.toFixed(6));
  }
  return { skel, world: v1 };
}

// ---------- VMD 解析（含贝塞尔插值和 IK 开关） ----------
const sjis = new TextDecoder('shift_jis');
function readCString(buf, off, n) {
  let end = off;
  while (end < off + n && buf[end] !== 0) end++;
  return sjis.decode(buf.subarray(off, end)).trim();
}
const normName = s => s.replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0)).replace('人差指', '人指');
function parseVmd(buf) {
  const magic = buf.subarray(0, 30).toString('ascii');
  if (!magic.startsWith('Vocaloid Motion Data')) throw new Error('不是 VMD: ' + magic.slice(0, 26));
  let o = 30;
  const modelName = readCString(buf, o, 20); o += 20;
  const boneCount = buf.readUInt32LE(o); o += 4;
  const motions = [];
  for (let i = 0; i < boneCount; i++) {
    const boneName = normName(readCString(buf, o, 15)); o += 15;
    const frame = buf.readUInt32LE(o); o += 4;
    const p = [buf.readFloatLE(o), buf.readFloatLE(o + 4), buf.readFloatLE(o + 8)]; o += 12;
    const r = [buf.readFloatLE(o), buf.readFloatLE(o + 4), buf.readFloatLE(o + 8), buf.readFloatLE(o + 12)]; o += 16;
    const ip = Array.from(buf.subarray(o, o + 64)); o += 64;
    motions.push({ boneName, frame, pos: p, rot: r, ip });
  }
  const morphCount = buf.readUInt32LE(o); o += 4;
  const morphs = [];
  for (let i = 0; i < morphCount; i++) {
    const morphName = readCString(buf, o, 15); o += 15;
    const frame = buf.readUInt32LE(o); o += 4;
    const weight = buf.readFloatLE(o); o += 4;
    morphs.push({ morphName, frame, weight });
  }
  let ikProps = null;
  try {
    const cc = buf.readUInt32LE(o); o += 4 + cc * 61;
    const lc = buf.readUInt32LE(o); o += 4 + lc * 28;
    const sc = buf.readUInt32LE(o); o += 4 + sc * 9;
    const pc = buf.readUInt32LE(o); o += 4;
    ikProps = [];
    for (let i = 0; i < pc; i++) {
      const frame = buf.readUInt32LE(o); o += 5;
      const n = buf.readUInt32LE(o); o += 4;
      const ik = {};
      for (let j = 0; j < n; j++) { ik[normName(readCString(buf, o, 20))] = buf[o + 20] !== 0; o += 21; }
      ikProps.push({ frame, ik });
    }
    ikProps.sort((a, b) => a.frame - b.frame);
  } catch { ikProps = null; /* 旧格式没有 IK 开关段 */ }
  return { modelName, motions, morphs, ikProps };
}

// VMD 贝塞尔：控制点 (x1,y1)(x2,y2) ∈ [0,127]
function bezier(x1, y1, x2, y2, x) {
  if (x1 === y1 && x2 === y2) return x;
  x1 /= 127; y1 /= 127; x2 /= 127; y2 /= 127;
  let lo = 0, hi = 1, t = x;
  for (let i = 0; i < 24; i++) {
    const bx = 3 * (1 - t) * (1 - t) * t * x1 + 3 * (1 - t) * t * t * x2 + t * t * t;
    if (Math.abs(bx - x) < 1e-6) break;
    if (bx < x) lo = t; else hi = t;
    t = (lo + hi) / 2;
  }
  return 3 * (1 - t) * (1 - t) * t * y1 + 3 * (1 - t) * t * t * y2 + t * t * t;
}
function sampleKeys(arr, f) {
  if (f <= arr[0].f) return arr[0];
  const last = arr[arr.length - 1];
  if (f >= last.f) return last;
  let lo = 0, hi = arr.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (arr[mid].f <= f) lo = mid; else hi = mid; }
  const a = arr[lo], b = arr[hi], x = (f - a.f) / (b.f - a.f), ip = b.ip;
  const tx = bezier(ip[0], ip[4], ip[8], ip[12], x);
  const ty = bezier(ip[1], ip[5], ip[9], ip[13], x);
  const tz = bezier(ip[2], ip[6], ip[10], ip[14], x);
  const tr = bezier(ip[3], ip[7], ip[11], ip[15], x);
  return {
    q: qslerp(a.q, b.q, tr),
    p: [a.p[0] + (b.p[0] - a.p[0]) * tx, a.p[1] + (b.p[1] - a.p[1]) * ty, a.p[2] + (b.p[2] - a.p[2]) * tz],
  };
}

// MMD 表情 → VRM preset
const MORPH_MAP = {
  'まばたき': 'blink', 'ウィンク': 'blinkRight', '左ウィンク': 'blinkLeft', '右ウィンク': 'blinkRight',
  '笑い': 'happy', 'にこり': 'happy', 'にっこり': 'happy', '怒り': 'angry', '悲しい': 'sad',
  'なごみ': 'relaxed', '真面目': 'relaxed', 'あ': 'aa', 'い': 'ih', 'う': 'ou', 'え': 'ee', 'お': 'oh',
};

// ---------- 主流程 ----------
function main() {
  if (!inFile) { console.error('用法: node vmd2vrma.mjs <in.vmd> <out.vrma>'); process.exit(1); }
  const vmd = parseVmd(readFileSync(inFile));
  if (opt.overlay) {
    const fix = parseVmd(readFileSync(opt.overlay)).motions, at = new Map(fix.map(m => [m.boneName + '|' + m.frame, m]));
    vmd.motions = vmd.motions.map(m => { const f = at.get(m.boneName + '|' + m.frame); if (f) at.delete(m.boneName + '|' + m.frame); return f || m; });
    vmd.motions.push(...at.values());
  }
  if (opt.morph) {
    try { vmd.morphs = [...vmd.morphs, ...parseVmd(readFileSync(opt.morph)).morphs]; }
    catch (e) { console.warn('表情 VMD 解析失败:', e.message); }
  }
  const { skel, world: SW } = buildSkeleton();
  const md = restDirs(ARMDEG), vd = restDirs(0);
  const CORR = {};
  for (const b of ORDER) {
    if (/Thumb|Index|Middle|Ring|Little/.test(b)) continue;
    CORR[b] = (md[b] && vd[b]) ? qFromTo(vd[b], md[b]) : [0, 0, 0, 1];
  }
  for (const b of ORDER) if (!CORR[b]) CORR[b] = CORR[b.startsWith('left') ? 'leftHand' : 'rightHand'];

  // 1. 关键帧归类（转换到 VRM1 轴）
  const keys = {};
  let maxFrame = 0;
  for (const m of vmd.motions) {
    (keys[m.boneName] ||= []).push({ f: m.frame, q: quatConv(m.rot), p: posConv(m.pos), ip: m.ip });
    maxFrame = Math.max(maxFrame, m.frame);
  }
  for (const b of Object.keys(keys)) {
    keys[b].sort((a, c) => a.f - c.f);
    keys[b] = keys[b].filter((k, i, arr) => i === arr.length - 1 || arr[i + 1].f !== k.f); // 同帧重复取最后一个
  }
  const nFrames = maxFrame + 1;

  // 2. 逐帧采样（贝塞尔）+ 去瞬切
  const samp = {};
  for (const b of Object.keys(keys)) samp[b] = Array.from({ length: nFrames }, (_, i) => sampleKeys(keys[b], i));
  if (DESPIKE) {
    let fixedQ = 0, fixedP = 0, spikes = 0;
    for (const b of Object.keys(samp)) {
      const arr = samp[b];
      for (let i = 1; i < arr.length - 1; i++) {
        const a = qangle(arr[i - 1].q, arr[i].q), c = qangle(arr[i].q, arr[i + 1].q), ac = qangle(arr[i - 1].q, arr[i + 1].q);
        if (a > 20 && c > 20 && ac < 0.5 * Math.min(a, c)) {
          arr[i] = { q: qslerp(arr[i - 1].q, arr[i + 1].q, 0.5), p: arr[i].p.map((v, j) => (arr[i - 1].p[j] + arr[i + 1].p[j]) / 2) };
          spikes++;
        }
      }
    }
    if (spikes) console.log(`去尖刺：${spikes} 帧`);
    for (let pass = 0; pass < PASSES; pass++) {
      for (const b of Object.keys(samp)) {
        const arr = samp[b];
        let prevQ = arr[0].q, prevP = arr[0].p;
        for (let i = 1; i < arr.length; i++) {
          let { q, p } = arr[i];
          const ang = qangle(prevQ, q);
          if (ang > MAXDEG) { q = qslerp(prevQ, q, MAXDEG / ang); if (!pass) fixedQ++; }
          const d = len(sub(p, prevP));
          if (d > MAXPOS) { p = add(prevP, scl(sub(p, prevP), MAXPOS / d)); if (!pass) fixedP++; }
          arr[i] = { q, p }; prevQ = q; prevP = p;
        }
      }
    }
    if (fixedQ || fixedP) console.log(`去瞬切：${fixedQ} 个旋转帧 / ${fixedP} 个位移帧（限 ${MAXDEG}°/帧、${MAXPOS} 单位/帧）`);
  }
  const ZERO = { q: [0, 0, 0, 1], p: [0, 0, 0] };
  const S = (name, fi) => samp[name]?.[fi] || ZERO;
  const has = name => !!samp[name];

  // 3. IK 开关
  const animated = name => (keys[name] || []).some(k => len(k.p) > 0.01 || Math.abs(k.q[3]) < 0.99995);
  function ikOn(name, fi) {
    if (IKMODE === 'on') return true;
    if (IKMODE === 'off') return false;
    if (vmd.ikProps?.length) {
      let on = null;
      for (const pr of vmd.ikProps) { if (pr.frame > fi) break; if (name in pr.ik) on = pr.ik[name]; }
      if (on === false) return false;
      if (on === true) return name.includes('つま先') ? animated(name.replace('つま先', '足')) : animated(name);
    }
    return animated(name.replace('つま先', '足'));
  }

  // 4. MMD 参照骨架 = 标准骨架 / K（MMD 单位，VRM1 轴）
  const R = b => scl(SW[b], 1 / K);
  const hipsRest = R('hips');
  const REST = {
    '全ての親': [0, 0, 0], 'センター': [0, hipsRest[1] * 0.7, 0], 'グルーブ': [0, hipsRest[1] * 0.72, 0],
    '腰': [0, hipsRest[1] * 0.97, 0], '下半身': hipsRest, '上半身': hipsRest,
  };
  const boneM = (name, rest, fi) => {
    const s = S(name, fi);
    return { q: s.q, t: sub(add(rest, s.p), qrot(s.q, rest)) };
  };
  const legInfo = {};
  for (const [side, jp] of [['left', '左'], ['right', '右']]) {
    const up = SW[side + 'UpperLeg'], lo = SW[side + 'LowerLeg'], ft = SW[side + 'Foot'], toe = SW[side + 'Toes'];
    legInfo[side] = {
      jp, u: sub(lo, up), v: sub(ft, lo), fv: sub(toe, ft),
      hipRest: R(side + 'UpperLeg'), ankleRest: R(side + 'Foot'), toeRest: R(side + 'Toes'),
      ikParentRest: [R(side + 'Foot')[0], 0, R(side + 'Foot')[2]],
    };
  }
  const pelvisMode = PELVIS !== 'auto' ? PELVIS
    : (keys['下半身'] || []).some(k => len(k.p) > 0.05) ? 'yaw' : 'full';
  const twistY = q => { const l = Math.hypot(q[1], q[3]) || 1; return [0, q[1] / l, 0, q[3] / l]; };
  const ikUsed = { left: 0, right: 0 }, toeUsed = { left: 0, right: 0 }, straight = { left: 0, right: 0 };

  // 两节腿 IK：膝盖只绕大腿局部 X 轴弯（MMD ひざ 限制）；大腿从 FK 姿势做最小旋转（同 MMD CCD 以 FK 为初值）
  function solveLeg(L, H, T, Qt_fk) {
    const { u, v } = L;
    const d = len(sub(T, H));
    // |u + Rx(φ)v|² = d²  →  B cosφ + C sinφ = D
    const A = u[0] * v[0], B = u[1] * v[1] + u[2] * v[2], C = u[2] * v[1] - u[1] * v[2];
    const D = (d * d - dot(u, u) - dot(v, v)) / 2 - A;
    const Rr = Math.hypot(B, C), al = Math.atan2(C, B), c = D / Rr;
    const wrap = x => Math.atan2(Math.sin(x), Math.cos(x));
    let phi;
    if (c >= 1) phi = Math.max(0, wrap(al));
    else if (c <= -1) phi = Math.PI;
    else {
      const cands = [wrap(al + Math.acos(c)), wrap(al - Math.acos(c))].filter(x => x >= -0.02);
      phi = cands.length ? Math.min(...cands) : 0;
    }
    phi = Math.max(0, Math.min(phi, 160 * Math.PI / 180));
    const knee = qAxis([1, 0, 0], phi);
    const Lv = add(u, qrot(knee, v));
    const Qt = qmul(qFromTo(qrot(Qt_fk, Lv), sub(T, H)), Qt_fk);
    return { Qt, knee, straight: c >= 1, ankle: add(H, qrot(Qt, Lv)) };
  }

  const tracks = {};
  const push = (bone, t, q) => { (tracks[bone] ||= { times: [], values: [] }); tracks[bone].times.push(t); tracks[bone].values.push(q[0], q[1], q[2], q[3]); };
  const hipsPos = { times: [], values: [] };
  let origin = null;

  for (let fi = 0; fi < nFrames; fi++) {
    const t = fi / 30;
    const root = ['全ての親', 'センター', 'グルーブ', '腰'].reduce((M, nm) => compose(M, boneM(nm, REST[nm], fi)), IDT);
    const lower = compose(root, boneM('下半身', REST['下半身'], fi));
    const upper = compose(root, boneM('上半身', REST['上半身'], fi));
    const Qlw = lower.q, Qh = pelvisMode === 'yaw' ? twistY(Qlw) : Qlw;
    push('hips', t, Qh);
    const hp = scl(apply(lower, hipsRest), K);
    if (!origin) origin = [hp[0] - SW.hips[0], 0, hp[2] - SW.hips[2]];
    hipsPos.times.push(t);
    hipsPos.values.push(hp[0] - origin[0], hp[1], hp[2] - origin[2]);
    push('spine', t, qmul(qconj(Qh), upper.q));
    for (const bone of ORDER) {
      const chain = MMD_CHAIN[bone];
      if (!chain) continue;
      let X = null;
      for (const raw of chain) {
        const inv = raw.startsWith('!'), half = raw.startsWith('½'), nm = inv || half ? raw.slice(1) : raw;
        if (!has(nm)) continue;
        const q = inv ? qconj(S(nm, fi).q) : half ? qslerp([0, 0, 0, 1], S(nm, fi).q, 0.5) : S(nm, fi).q;
        X = X ? qmul(X, q) : q;
      }
      if (!X) continue;
      const pw = PARENT[bone];
      const Cp = (pw && CORR[pw]) ? CORR[pw] : [0, 0, 0, 1];
      push(bone, t, qmul(qmul(qconj(Cp), X), CORR[bone]));
    }
    const Qwaist = S('腰', fi).q;
    for (const side of ['left', 'right']) {
      const L = legInfo[side], jp = L.jp;
      const ikName = jp + '足ＩＫ', toeName = jp + 'つま先ＩＫ';
      if (ikOn(ikName, fi)) {
        ikUsed[side]++;
        const Qt_fk = qmul(qmul(Qlw, qconj(Qwaist)), S(jp + '足', fi).q);
        const H = scl(apply(lower, L.hipRest), K);
        const ikM = [['全ての親', REST['全ての親']], [jp + '足IK親', L.ikParentRest], [ikName, L.ankleRest]]
          .reduce((M, [nm, rest]) => compose(M, boneM(nm, rest, fi)), IDT);
        const T = scl(apply(ikM, L.ankleRest), K);
        const r = solveLeg(L, H, T, Qt_fk);
        if (r.straight) straight[side]++;
        const shinW = qmul(r.Qt, r.knee);
        let footW = qmul(shinW, S(jp + '足首', fi).q);
        if (ikOn(toeName, fi)) {
          toeUsed[side]++;
          const TT = scl(apply(compose(ikM, boneM(toeName, L.toeRest, fi)), L.toeRest), K);
          footW = qmul(qFromTo(qrot(footW, L.fv), sub(TT, r.ankle)), footW);
        }
        push(side + 'UpperLeg', t, qmul(qconj(Qh), r.Qt));
        push(side + 'LowerLeg', t, r.knee);
        push(side + 'Foot', t, qmul(qconj(shinW), footW));
      } else {
        push(side + 'UpperLeg', t, qmul(qmul(qmul(qconj(Qh), Qlw), qconj(Qwaist)), S(jp + '足', fi).q));
        push(side + 'LowerLeg', t, S(jp + 'ひざ', fi).q);
        push(side + 'Foot', t, S(jp + '足首', fi).q);
      }
      const toeFk = has(jp + '足先EX') ? jp + '足先EX' : null;
      if (toeFk) push(side + 'Toes', t, S(toeFk, fi).q);
    }
  }

  // 5. 腿部输出再去一次 1 帧翻转（IK 在伸直附近可能换解）
  if (DESPIKE) {
    for (const b of ['leftUpperLeg', 'rightUpperLeg', 'leftLowerLeg', 'rightLowerLeg', 'leftFoot', 'rightFoot']) {
      const tr = tracks[b]; if (!tr) continue;
      const vals = tr.values;
      for (let i = 1; i < tr.times.length; i++) {
        const prev = vals.slice((i - 1) * 4, i * 4), cur = vals.slice(i * 4, i * 4 + 4);
        const ang = qangle(prev, cur);
        if (ang > 25) vals.splice(i * 4, 4, ...qslerp(prev, cur, 25 / ang));
      }
    }
  }

  // 6. 表情轨道（VRMA 表情通道：translation x = weight）
  const exprKeys = {};
  for (const m of vmd.morphs) {
    const pre = MORPH_MAP[m.morphName];
    if (pre) (exprKeys[pre] ||= []).push({ f: m.frame, w: m.weight });
  }
  const exprTracks = {};
  for (const [pre, arr] of Object.entries(exprKeys)) {
    arr.sort((a, b) => a.f - b.f);
    const seen = new Map(arr.map(k => [k.f, k.w]));
    const tr = { times: [], values: [] };
    const fs = [...seen.keys()];
    if (fs[0] > 0) { tr.times.push(0); tr.values.push(0, 0, 0); }
    for (const f of fs) { tr.times.push(f / 30); tr.values.push(seen.get(f), 0, 0); }
    if (fs[fs.length - 1] < maxFrame) { tr.times.push(maxFrame / 30); tr.values.push(0, 0, 0); }
    exprTracks[pre] = tr;
  }

  // 7. 组装 VRMA glTF
  const usedBones = ORDER.filter(b => tracks[b]);
  const chainBones = new Set();
  for (const b of usedBones) { let p = PARENT[b]; while (p) { chainBones.add(p); p = PARENT[p]; } }
  const allBones = ORDER.filter(b => usedBones.includes(b) || chainBones.has(b));
  const index = {}; allBones.forEach((b, i) => { index[b] = i; });
  const nodes = allBones.map(b => {
    const node = { name: b, translation: b === 'hips' ? SW.hips.map(v => +v.toFixed(6)) : (skel[b] || [0, 0, 0]) };
    const kids = allBones.filter(x => PARENT[x] === b);
    if (kids.length) node.children = kids.map(k => index[k]);
    return node;
  });
  const chunks = []; let offset = 0;
  const bufferViews = [], accessors = [], samplers = [], channels = [];
  const pushFloats = (arr, type, count) => {
    const b = Buffer.alloc(arr.length * 4);
    arr.forEach((v, i) => b.writeFloatLE(v, i * 4));
    bufferViews.push({ buffer: 0, byteOffset: offset, byteLength: b.length });
    offset += b.length;
    const acc = { bufferView: bufferViews.length - 1, componentType: 5126, count, type };
    if (type === 'SCALAR') { acc.min = [arr[0]]; acc.max = [arr[arr.length - 1]]; }
    accessors.push(acc);
    chunks.push(b);
    return accessors.length - 1;
  };
  const addChannel = (tr, nodeIdx, path) => {
    const tAcc = pushFloats(tr.times, 'SCALAR', tr.times.length);
    const vAcc = pushFloats(tr.values, path === 'rotation' ? 'VEC4' : 'VEC3', tr.times.length);
    samplers.push({ input: tAcc, output: vAcc, interpolation: 'LINEAR' });
    channels.push({ sampler: samplers.length - 1, target: { node: nodeIdx, path } });
  };
  for (const b of usedBones) addChannel(tracks[b], index[b], 'rotation');
  addChannel(hipsPos, index.hips, 'translation');
  const exprPresets = {};
  for (const pre of Object.keys(exprTracks)) {
    exprPresets[pre] = { node: nodes.length };
    nodes.push({ name: 'expr_' + pre });
    addChannel(exprTracks[pre], nodes.length - 1, 'translation');
  }
  const bin = Buffer.concat(chunks);
  const humanBones = {};
  for (const b of allBones) humanBones[b] = { node: index[b] };
  const gltf = {
    asset: { version: '2.0', generator: 'vmd2vrma-v2' },
    extensionsUsed: ['VRMC_vrm_animation'],
    extensions: { VRMC_vrm_animation: { specVersion: '1.0', humanoid: { humanBones }, ...(Object.keys(exprPresets).length ? { expressions: { preset: exprPresets } } : {}) } },
    scene: 0, scenes: [{ nodes: [index.hips] }], nodes,
    buffers: [{ byteLength: bin.length, uri: 'data:application/octet-stream;base64,' + bin.toString('base64') }],
    bufferViews, accessors, animations: [{ name: 'motion', channels, samplers }],
  };
  writeFileSync(outFile, JSON.stringify(gltf));
  const ikText = side => ikUsed[side] ? `${side === 'left' ? '左' : '右'}腿 IK ${ikUsed[side]} 帧（伸直 ${straight[side]}，脚尖 ${toeUsed[side]}）` : '';
  console.log('OK', outFile.split('/').pop(), '| 骨骼', usedBones.length, '| 表情', Object.keys(exprTracks).join(',') || '无',
    '| 时长', (maxFrame / 30).toFixed(1) + 's |', (readFileSync(outFile).length / 1024).toFixed(0) + 'KB',
    '|', [ikText('left'), ikText('right')].filter(Boolean).join('；') || '腿部 FK', '| 骨盆', pelvisMode);
}
main();
