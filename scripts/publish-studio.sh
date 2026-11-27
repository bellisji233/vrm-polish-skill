#!/bin/zsh
# Build studio/ (the out-of-box director console) from the working viewer: page and modules always; media (motions,
# music, room props, the default character) only where scripts/studio-media.json marks them approved. The dance and
# motion lists are written for what is included, and media folders are emptied first, so nothing stale is left.
# tools/: the VMD converter is copied from the viewer; tools/add-media.py (adding your own media) is kept in studio/.
# usage: publish-studio.sh VIEWER_DIR [DEFAULT.vrm 显示名] [演示舞曲]
#   DEFAULT.vrm is copied only when models/default.vrm is approved in studio-media.json; otherwise the console opens
#   empty and a character is dragged in
set -e; setopt pipefail
SRC=${1:A}; VRM=${2:+${2:A}}; NAME=${3:-默认角色}; DEMO=${4:-}
[ -f "$SRC/index.html" ] || { echo "usage: publish-studio.sh VIEWER_DIR [DEFAULT.vrm 显示名] [演示舞曲]"; exit 2; }
H=${0:A:h}; DST=${H:h}/studio; MAN="$H/studio-media.json"
for f in index.html arm-avoid.js model-store.js skirt-cloth.js skirt-guard.js; do cp "$SRC/$f" "$DST/$f"; done
mkdir -p "$DST/tools"; for f in vmd2vrma.mjs skeleton.json; do cp "$SRC/tools/$f" "$DST/tools/$f"; done   # tools/add-media.py lives here
rm -rf "$DST/animations" "$DST/music" "$DST/models" "$DST/assets" "$DST/scenes"
mkdir -p "$DST/animations" "$DST/music" "$DST/models" "$DST/assets/manpu" "$DST/scenes/bedroom"
cp "$SRC/scenes/catalog.json" "$DST/scenes/catalog.json"; cp "$SRC/scenes/bedroom/catalog.json" "$DST/scenes/bedroom/catalog.json"
cp "$SRC/assets/manpu/manpu.json" "$DST/assets/manpu/manpu.json"
python3 - "$SRC" "$DST" "$MAN" "${VRM:-}" "$NAME" "$DEMO" <<'PY'
import json, shutil, sys
from pathlib import Path
src, dst, man, vrm, name, demo = Path(sys.argv[1]), Path(sys.argv[2]), json.load(open(sys.argv[3])), sys.argv[4], sys.argv[5], sys.argv[6]
ok = {i['path'] for i in man['items'] if i.get('approved')}
copied = []
for p in sorted(ok):
    if p == 'models/default.vrm' or not (src / p).is_file():
        continue
    (dst / p).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src / p, dst / p); copied.append(p)
cat = json.load(open(src / 'catalog.json'))
have = set(copied)                                  # only what was copied: an approved but missing file is not listed
cat['actions'] = [a for a in cat['actions'] if a['url'] in have]
cat['dances'] = [d for d in cat['dances'] if d['url'] in have and d['audio'] in have]
cat['previews'] = [d for d in cat.get('previews', []) if d.get('url') in have]
json.dump(cat, open(dst / 'catalog.json', 'w'), ensure_ascii=False, indent=1)
model = None
if vrm and 'models/default.vrm' in ok:
    shutil.copy2(vrm, dst / 'models/default.vrm'); model = {'url': 'models/default.vrm', 'name': name}
json.dump({'defaultModel': model, 'demo': {'dance': demo or (cat['dances'][0]['label'] if cat['dances'] else '')}},
          open(dst / 'studio.json', 'w'), ensure_ascii=False, indent=1)
print(f"media {len(copied)} | motions {len(cat['actions'])} | dances {len(cat['dances'])} | default character {'yes' if model else 'none'}")
PY
du -sh "$DST" | cut -f1 | xargs echo "studio:"
