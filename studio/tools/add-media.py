#!/usr/bin/env python3
"""Add your own dances and motions to the director console library (catalog.json).

  python3 tools/add-media.py dance NAME --motion M.vmd|M.vrma [--expression E.vmd] [--overlay FIX.vmd]
                             --music SONG.wav|.mp3 [--start SEC] [--length SEC] [--category TEXT] [--credit TEXT]
  python3 tools/add-media.py motion NAME --motion M.vrma [--credit TEXT]
  python3 tools/add-media.py list
  python3 tools/add-media.py remove NAME

MMD motions (.vmd) are converted with tools/vmd2vrma.mjs (Node.js 18+); --expression adds the facial track that
some dances ship as a second VMD, --overlay applies a correction VMD the author ships separately (same bone, same
frame: the correction wins). Music is cut with ffmpeg when --start or --length is given. Files go to animations/
and music/, and catalog.json is updated in place. MEDIA.md lists where each dance of the original library comes from.
"""
import argparse
import base64
import json
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'catalog.json'
PLAIN_AUDIO = ('.wav', '.mp3', '.m4a', '.ogg', '.flac', '.aac')


def fail(msg):
    sys.exit('add-media: ' + msg)


def load_catalog():
    cat = json.loads(CATALOG.read_text('utf-8')) if CATALOG.exists() else {}
    for k in ('actions', 'dances', 'previews'):
        cat.setdefault(k, [])
    return cat


def save_catalog(cat):
    CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=1) + '\n', 'utf-8')


def safe(name):
    name = name.strip()
    if not name or any(c in name for c in '/\\:*?"<>|') or name.startswith('.'):
        fail(f'name "{name}" cannot be used as a file name')
    return name


def motion_seconds(path):
    """length of a .vrma: the largest keyframe time over all animation samplers"""
    b = path.read_bytes()
    if b[:4] == b'glTF':
        n = struct.unpack_from('<I', b, 12)[0]
        g = json.loads(b[20:20 + n])
        o = 20 + n
        binchunk = b[o + 8:o + 8 + struct.unpack_from('<I', b, o)[0]] if len(b) > o + 8 else b''
    else:
        g, binchunk = json.loads(b), b''
    if 'VRMC_vrm_animation' not in g.get('extensions', {}):
        fail(f'{path.name} is not a VRM Animation (.vrma) file')
    out = 0.0
    for anim in g.get('animations', []):
        for s in anim['samplers']:
            a = g['accessors'][s['input']]
            if 'max' in a:
                out = max(out, a['max'][0])
                continue
            v = g['bufferViews'][a['bufferView']]
            uri = g['buffers'][v['buffer']].get('uri')
            data = base64.b64decode(uri.split(',', 1)[1]) if uri else binchunk
            off = v.get('byteOffset', 0) + a.get('byteOffset', 0)
            out = max(out, max(struct.unpack_from('<' + 'f' * a['count'], data, off)))
    if out <= 0:
        fail(f'{path.name} has no animation')
    return out


def audio_seconds(path):
    if path.suffix.lower() == '.wav':
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    if not shutil.which('ffprobe'):
        return None
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def add_motion_file(src, dst, expression=None, overlay=None):
    src = Path(src)
    if not src.is_file():
        fail(f'{src} not found')
    dst.parent.mkdir(exist_ok=True)
    if src.suffix.lower() == '.vrma':
        if expression or overlay:
            fail('--expression and --overlay only apply to .vmd motions')
        shutil.copyfile(src, dst)
    elif src.suffix.lower() == '.vmd':
        if not shutil.which('node'):
            fail('Node.js 18+ is needed to convert .vmd motions')
        cmd = ['node', str(ROOT / 'tools' / 'vmd2vrma.mjs'), str(src), str(dst)]
        if expression:
            cmd.append('--morph=' + str(Path(expression).resolve()))
        if overlay:
            cmd.append('--overlay=' + str(Path(overlay).resolve()))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode or not dst.exists():
            fail('conversion failed: ' + (r.stderr or r.stdout).strip()[-400:])
        print(r.stdout.strip().splitlines()[-1])
    else:
        fail(f'{src.name}: use a .vmd or .vrma motion')
    return motion_seconds(dst)


def add_music_file(src, name, start, length):
    src = Path(src)
    if not src.is_file():
        fail(f'{src} not found')
    (ROOT / 'music').mkdir(exist_ok=True)
    for old in (ROOT / 'music').glob(name + '.*'):
        old.unlink()
    if start or length or src.suffix.lower() not in PLAIN_AUDIO:
        if not shutil.which('ffmpeg'):
            fail('ffmpeg is needed to cut or convert music')
        dst = ROOT / 'music' / (name + '.wav')
        cmd = ['ffmpeg', '-v', 'error', '-y', '-ss', str(start or 0), '-i', str(src)]
        if length:
            cmd += ['-t', str(length)]
        subprocess.run(cmd + ['-ac', '2', '-ar', '44100', str(dst)], check=True)
    else:
        dst = ROOT / 'music' / (name + src.suffix.lower())
        shutil.copyfile(src, dst)
    return dst


def cmd_dance(a):
    name = safe(a.name)
    motion = ROOT / 'animations' / f'dance-{name}.vrma'
    msec = add_motion_file(a.motion, motion, a.expression, a.overlay)
    music = add_music_file(a.music, name, a.start, a.length)
    asec = audio_seconds(music)
    item = {'url': motion.relative_to(ROOT).as_posix(), 'label': name, 'audio': music.relative_to(ROOT).as_posix(),
            'playDuration': round(min(msec, asec) if asec else msec, 3), 'shortAudio': bool(a.start or a.length)}
    if a.category:
        item['category'] = a.category
    if a.credit:
        item['credit'] = a.credit
    cat = load_catalog()
    cat['dances'] = [d for d in cat['dances'] if d.get('label') != name] + [item]
    save_catalog(cat)
    print(f'dance "{name}": motion {msec:.1f} s, music {asec:.1f} s, plays {item["playDuration"]:.1f} s'
          if asec else f'dance "{name}": motion {msec:.1f} s')


def cmd_motion(a):
    name = safe(a.name)
    dst = ROOT / 'animations' / f'{name}.vrma'
    sec = add_motion_file(a.motion, dst)
    item = {'url': dst.relative_to(ROOT).as_posix(), 'label': name}
    if a.credit:
        item['credit'] = a.credit
    cat = load_catalog()
    cat['actions'] = [m for m in cat['actions'] if m.get('label') != name] + [item]
    save_catalog(cat)
    print(f'motion "{name}": {sec:.1f} s')


def cmd_list(_):
    cat = load_catalog()
    for kind, items in (('dance', cat['dances']), ('motion', cat['actions'])):
        for it in items:
            missing = [p for p in (it.get('url'), it.get('audio')) if p and not (ROOT / p).exists()]
            print(f'{kind:6} {it["label"]}' + (f'  missing: {", ".join(missing)}' if missing else ''))
    if not cat['dances'] and not cat['actions']:
        print('library is empty')


def cmd_remove(a):
    cat = load_catalog()
    gone = [it for k in ('dances', 'actions') for it in cat[k] if it.get('label') == a.name]
    if not gone:
        fail(f'"{a.name}" is not in the library')
    for k in ('dances', 'actions'):
        cat[k] = [it for it in cat[k] if it.get('label') != a.name]
    save_catalog(cat)
    used = {it.get(f) for k in ('dances', 'actions') for it in cat[k] for f in ('url', 'audio')}
    for it in gone:
        for p in (it.get('url'), it.get('audio')):
            if p and p not in used and (ROOT / p).exists():
                (ROOT / p).unlink()
    print(f'removed "{a.name}"')


def main():
    ap = argparse.ArgumentParser(description='Add dances and motions to the director console library.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('dance', help='a dance with its music')
    d.add_argument('name')
    d.add_argument('--motion', required=True, help='.vmd or .vrma')
    d.add_argument('--expression', help='facial VMD shipped with the dance')
    d.add_argument('--overlay', help='correction VMD shipped by the motion author')
    d.add_argument('--music', required=True)
    d.add_argument('--start', type=float, help='seconds into the song where the dance starts')
    d.add_argument('--length', type=float, help='seconds of music to keep')
    d.add_argument('--category', help='heading in the dance list')
    d.add_argument('--credit')
    d.set_defaults(fn=cmd_dance)
    m = sub.add_parser('motion', help='a short motion (.vrma)')
    m.add_argument('name')
    m.add_argument('--motion', required=True)
    m.add_argument('--credit')
    m.set_defaults(fn=cmd_motion)
    sub.add_parser('list').set_defaults(fn=cmd_list)
    r = sub.add_parser('remove')
    r.add_argument('name')
    r.set_defaults(fn=cmd_remove)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
