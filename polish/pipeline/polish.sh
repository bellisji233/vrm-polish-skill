#!/bin/zsh
# One command: (measure + config if missing) -> build -> springs -> expressions -> shoulder/knee correctives.
# usage: polish.sh PROJECT_DIR PROFILE_DIR OUT.vrm [REQUEST_ID]
set -e; setopt pipefail
P=$1; HD=$2; OUT=$3; R=$4; H=${0:A:h}
[ -n "$OUT" ] || { echo "usage: polish.sh PROJECT_DIR PROFILE_DIR OUT.vrm [REQUEST_ID]"; exit 2; }
mkdir -p "${OUT:A:h}"
[ -f "$P/work/build_character.json" ] || zsh "$H/prepare.sh" "$P" "$HD"
zsh "$H/build.sh" "$P" $R
zsh "$H/expressions.sh" "$P" "$HD" "${OUT%.vrm}-expr.vrm"
# safety shorts painted under a skirt: "safety_shorts": {"hem": 0.5, "material": "Material_lower_body", "palette": "lavender"}
SS=($(python3 -c "import json,sys; s=json.load(open(sys.argv[1])).get('safety_shorts'); print(*([s.get('hem',0.26), s.get('material','Material_lower_body'), s.get('palette','lavender')] if s else []))" "$P/work/build_character.json"))
if [ ${#SS} -gt 0 ]; then
  python3 "${H:h}/post/safety_shorts.py" "${OUT%.vrm}-expr.vrm" "${OUT%.vrm}-shorts.vrm" $SS 2>&1 | tail -1 | cut -c1-120
  mv "${OUT%.vrm}-shorts.vrm" "${OUT%.vrm}-expr.vrm"
fi
python3 "${H:h}/post/shoulder_fix.py" "${OUT%.vrm}-expr.vrm" "$OUT" 2>&1 | grep -oE "SHOULDER_OK.*" | cut -c1-80
[ -f "$OUT" ] || { echo "stopped: correctives failed"; exit 1; }
rm -f "${OUT%.vrm}-expr.vrm"
echo "POLISH_OK $OUT"
