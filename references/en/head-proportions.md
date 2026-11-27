[中文](../头身比.md) | English

# Head Proportions

## Measurement

Heads tall = stature ÷ head height. Head height runs from the top of the head (top of the skull, excluding hair) to the lowest point of the chin; stature runs from that same top point to the soles. Use a neutral upright pose, excluding hair, hats, animal ears, and shoe heels.

```sh
zsh polish/pipeline/head_ratio.sh built.vrm
```

Outputs `heads` (heads tall), plus `stature`, `head_height`, `top`, `chin`, `foot`, and `head_joint` (in m). The tool finds the head top and chin using the `Material_head` and `Material_scalp` material prefixes, excluding hair, eyes, decals, and the neck transition; it takes the lowest mesh point as the sole. For VRMs from other sources, heels, or accessories below the feet, verify measurement endpoints first; do not treat the bounding box directly as barefoot stature.

## Recommended Ranges

Choose by visual style first, then apparent age; gender warrants only small adjustments. Preserve established proportions when reference images specify them clearly. Defaults are production starting points, not anthropometric means, market shares, or official VRoid defaults.

| Style | Recommended range | Default | Source |
|---|---|---|---|
| Realistic adult | 7–8 heads tall | 7.5 heads tall | [Maestri, Digital Character Animation 3, p.11](https://api.pageplace.de/preview/DT0400.9780321455123_A26059437/preview-9780321455123_A26059437.pdf), [Navy drafting textbook's 7.5-head art reference](https://draftingmanuals.tpub.com/14262/css/Common-Errors-145.htm) |
| Idealized adult, elongated stage style | 7.5–8 heads tall | 8 heads tall | [Loomis, Figure Drawing for All It's Worth](https://en.wikisource.org/wiki/Page:Andrew_Loomis,_Figure_Drawing_for_All_It's_Worth.pdf/19) |
| Japanese anime-style VRM for both streaming and dancing | 6–7 heads tall | 6.5 heads tall | [Meshy VTuber creation tutorial](https://www.meshy.ai/ja/tutorials/how-to-make-a-vtuber-3d-model); 6.5 heads tall is the midpoint |
| Super-deformed, chibi, mascot | 2–4 heads tall | 3 heads tall | [CLIP STUDIO](https://www.clipstudio.net/how-to-draw/archives/155423), [Toon Boom](https://learn.toonboom.com/modules/character-design/topic/character-proportions) |

### Separate Standards for Men and Women?

Use the same scale for men and women, not two separate standards.

| Basis | Male | Female | Source |
|---|---|---|---|
| Anthropometry: young Japanese adults (AIST 1997–98, 110 men and 107 women; mean stature ÷ mean total head height) | 7.14 heads tall (170.6 ÷ 23.9 cm) | 6.87 heads tall (158.6 ÷ 23.1 cm) | [Survey description](https://www.airc.aist.go.jp/dhrt/97-98/index.html), [Statistics](https://www.airc.aist.go.jp/dhrt/97-98_Statistics.pdf) |
| Loomis ideal proportions | 8 heads tall | Also 8 heads tall in educators' interpretations | [Original book, p.26–27](https://en.wikisource.org/wiki/Page:Andrew_Loomis,_Figure_Drawing_for_All_It's_Worth.pdf/20), [Illustrated explanation](https://brendrawscomics.com/news/proportions-figure-resources) |
| Fashion illustration | 9 or 11 heads tall | Same as male; women have longer legs, men longer torsos | [Fashion Drawing For Dummies](https://www.dummies.com/article/academics-the-arts/art-architecture/drawing/fashion-drawing/proportions-in-fashion-drawing-171535) |
| Japanese character-drawing instruction | Some use “male 8, female 7”; others separate only by age: adults 7–8, middle/high school students 6–7 | | [Textbook, p.89](https://www.art-design.ac.jp/wp-content/themes/artdesign/file/houkokusyo_h29_1.pdf), [ATAM](https://atam-academy.com/blog/47577/), [MediBang](https://medibangpaint.com/use/2020/12/how-to-draw-a-character-at-different-ages-2/) |

- Do not change the default by gender. Measured male/female differences are only about 0.25 heads; visual style and apparent age have much greater effects.
- When male and female characters in the same style share a stage, the male character may be 0.25–0.5 heads taller in proportion, or follow the specified height difference.
- When characters in different styles share a stage (for example, 6.5 and 8 heads tall), the difference in head size is conspicuous; confirm with the user first.

### Characters in This Repository

| Character | Heads tall | Stature | Head height | Style |
|---|---|---|---|---|
| the purple version (紫色版) (female) | 6.51 | 168.7 cm | 25.9 cm | Japanese anime |
| Lavender Denim (薰衣草牛仔) (same head, different outfit) | 6.17 | 165.5 cm | 26.8 cm | Japanese anime |
| Character 2 (人物2) (male) | 8.0 (originally 8.89) | 163.1 cm | 20.4 cm | Idealized |

## Changing Head Proportion

When the head is too small after rigging and weighting, enlarge it around the head joint: scale each vertex proportionally to its head weight, enlarging the head and hair together with a smooth neck transition, and transform the head bone's children together. Uniformly scaling the entire character does not change heads tall. There is no need to return to Charakuru to adjust proportions, redo rigging and weights, or spend Tripo credits.

```sh
zsh polish/pipeline/head_ratio.sh <project> <built.vrm> <target>
zsh polish/pipeline/prepare.sh <project> <head-profile> --force
zsh polish/pipeline/polish.sh <project> <head-profile> <new-built.vrm>
zsh polish/pipeline/head_ratio.sh <new-built.vrm>
```

`<target>` is the target heads tall; `work/weights/head_scale.json` records the total multiplier `scale` relative to the original and the `target`. The first run saves `work/weights/weighted-orig.blend`; subsequent runs always generate `weighted.blend` from the original using the total multiplier, without repeatedly scaling an already modified mesh. The input finished model must match the current scale record; do not mix VRMs from other versions. Remeasurement fits hair positions, automatically enlarging the hair accordingly. Put manual build values in `work/build_overrides.json`; see [Configuration](configuration.md).

Character 2: 8.89 → 8.0 heads tall, enlarged 1.1232 times around the head joint; head height 18.2 → 20.4 cm, stature 161.4 → 163.1 cm. The neck seam and expressions have passed acceptance checks in the Director Console.

## Proportions and Hand Placement in Dance

At the same bone angles, Character 2's chin is 11.2 cm above the shoulders, 0.228 times the arm length; the denim outfit measures 6.5 cm and 0.12 times. During the chin-rest gesture in Reze, Character 2's hand lands below the chin, while the denim outfit's hand lands beside the mouth. Arm span ÷ stature is 0.89 and 0.91 respectively, compared with about 1.0 for a real person, solely as a proportion reference.

When confirming proportions, inspect half-body streaming, full-body dancing, and chin-rest poses together. Record heads tall, arm-span ratio, and hand placement relative to the face; report differences of more than 0.3 heads from the user's target. Collision avoidance only reduces penetration and cannot replace proportion choices. See [Acceptance Checklist](acceptance-checklist.md).
