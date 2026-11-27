"""Join pieces-front/back.png with a legend: python3 make_sheet.py OUT_DIR -> OUT_DIR/零件.jpg"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D = Path(sys.argv[1])
pieces = json.loads((D / 'pieces.json').read_text(encoding='utf-8'))
a, b = Image.open(D / 'pieces-front.png').convert('RGB'), Image.open(D / 'pieces-back.png').convert('RGB')
W = a.width + b.width + 520
img = Image.new('RGB', (W, a.height), (255, 255, 255)); img.paste(a, (0, 0)); img.paste(b, (a.width, 0))
dr = ImageDraw.Draw(img)
font = ImageFont.load_default()
for f in ('/System/Library/Fonts/Hiragino Sans GB.ttc', '/System/Library/Fonts/STHeiti Medium.ttc',
          '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'C:/Windows/Fonts/msyh.ttc'):
    if Path(f).is_file():
        font = ImageFont.truetype(f, 22); break
SITE = {'neck': '脖子', 'chest': '胸前', 'belly': '腹部', 'back': '后背', 'hip': '胯部', 'thigh': '大腿', 'shin': '小腿',
        'upper_arm': '上臂', 'forearm': '前臂'}
x0, y = a.width + b.width + 24, 30
dr.text((x0, y), '正面 / 背面，同色为同一零件', fill=(30, 30, 30), font=font); y += 50
for i, p in enumerate(pieces):
    c = tuple(int(v * 255) for v in p['colour'])
    dr.rectangle([x0, y, x0 + 34, y + 34], fill=c)
    sites = '、'.join(SITE.get(s, s) for s in p['sites'])
    auto = {'skin': '　自动：皮肤', 'cloth': '　自动：衣服'}.get(p.get('auto'), '')
    dr.text((x0 + 48, y), f'#{i + 1} {sites}{auto}', fill=(30, 30, 30), font=font)
    dr.text((x0 + 48, y + 30), f'{p["faces"]} 面，肤色占 {round(p["skin_fraction"] * 100)}%', fill=(110, 110, 110), font=font)
    y += 78
img.save(D / '零件.jpg', quality=90)
print('SHEET_OK ' + str(D / '零件.jpg'))
