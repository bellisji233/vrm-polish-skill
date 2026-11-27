[中文](../../SKILL.md) | English

# VRM avatar polish (skill guide)

## Division of work with Charakuru

| Who | Work |
|---|---|
| Charakuru | Image generation, Tripo candidates, parts and textures, head/body adjustment, rigging, weight transfer |
| This skill, during the Charakuru steps | `rig.sh upload`, `rig.sh check` (rigging); `finish_weights.py` (when weights cannot be calculated) |
| Handoff point | Copy `weighted.blend` from the weight task to the project's `work/weights/` |
| This skill | Polish build, expressions and mouth interior, joint corrections, safety shorts, head proportion, Director Console acceptance checks |
| Kit scripts called by this skill | Springs (hair and skirt physics) setup and checks, skirt colliders, expression workspace and integration, registration back in the workbench |

For stage-by-stage instructions, see “Division of work” in [charakuru-integration.md](charakuru-integration.md).

**This skill contains no Charakuru code.** Users obtain the kit themselves from the official Charakuru source (tested with version 1.1.1); the skill only calls scripts in the kit.

## Prerequisites

| Requirement | Notes |
|---|---|
| Charakuru 1.1.1 | Obtain it yourself and use it under its license; this skill's scripts stay outside the kit |
| Blender 5.2 + VRM Add-on | Also required by Charakuru itself |
| Tripo account | About 300 credits for a new character (100 for candidates, 40 for segmentation, 80 for textures, rigging starts at 20) |
| Image generation | Part images and texture reference images, required by the Charakuru workflow itself |
| Python 3 + numpy + Pillow, Node.js 22 | Pillow is used for the piece sheet and head textures |
| macOS + zsh | Platform requirement for the polish pipeline; the `BLENDER` environment variable can override the Blender executable path. The Director Console supports macOS / Windows |

## Workflow

1. **Complete weights in Charakuru**: Follow [charakuru-integration.md](charakuru-integration.md). Use this skill's two tools for the rigging step:
   ```
   zsh polish/pipeline/rig.sh upload <project>          # head + body without textures, under the 10 MB upload limit
   zsh polish/pipeline/rig.sh check <FBX returned by Tripo>  # left-right symmetry check; mirrors the fingers when one side is off
   ```
2. **Head profile**: See [head-profiles.md](head-profiles.md). New users start with the repository's `assets/head-profile/`; it contains only calibration points, head settings, and anime-style decals, without the first character's meshes or textures. Facial features on a new head are detected automatically and aligned using 9 calibration points; relevant settings are rebuilt or skipped based on its structure. A complete profile containing `head_rest.npy` is needed only when reusing the same head with different outfits. `make_profile.py` currently supports only purple-head types with separate eye, eyebrow, and crease parts; Character 2 (人物2) types cannot be packaged.
3. **Measurement and configuration**:
   ```
   zsh polish/pipeline/prepare.sh <project> <head-profile>
   ```
   Automatically measures head coordinates, the neck transition, hair collision spheres, fingers, waist, cuffs, springs starting points, and belt; fits the template hand; and writes `work/build_character.json`. Then **look at `work/measure/零件.jpg`**: the neck and clothing with distinct colors have already been selected automatically. Add skin parts such as exposed waist and legs using the numbers in the image; after confirming small items such as necklaces, add `--metal`:
   ```
   zsh polish/pipeline/prepare.sh <project> <head-profile> --skin 3 --metal --force
   ```
   Write manual adjustments to `work/build_overrides.json`; they are merged and preserved when using `--force`. `neck_widen.factor` corresponds to `--neck-widen`. For detailed fields and merge exceptions, see [Configuration](configuration.md).
4. **One command**:
   ```
   zsh polish/pipeline/polish.sh <project> <head-profile> <out.vrm> [request ID]
   ```
   Runs in order: build (head refinement, template hand, color correction by part, weights and physics bones) → kit springs registration and checks → expressions (builds 77 shape keys) → safety shorts texture (when enabled in the configuration) → shoulder, knee, and elbow correction shapes. The skirt collider setup is applied according to `work/skirt-colliders.json` and `work/skirt-extra-colliders.json`. If no configuration exists, step 3 runs automatically first. If a request ID is provided, the model for confirmation is also registered back in Charakuru and the request is completed.
5. **Proportion check**: Use `zsh polish/pipeline/head_ratio.sh <built.vrm>` to measure height in heads, and compare it with the recommended value for the art style (realistic 7.5, idealized 8, Japanese anime 6.5, chibi 3; the same standard applies to male and female characters, though male characters may be 0.25–0.5 heads taller when appearing alongside female characters in the same style). Tell the user if the difference is more than 0.3 heads. If a change is needed, scale the weighted result directly, then run `prepare.sh --force` and `polish.sh`; see [Head proportion](head-proportions.md).
6. **Acceptance checks**: In the Director Console (`studio/`, double-click `start-mac.command` or `start-windows.bat`), check each item in [acceptance-checklist.md](acceptance-checklist.md). Compare static screenshots with the baseline version, and keep recordings or consecutive frames of motions and transitions. Good numbers do not count; judge by the visuals.

## Check here first when problems occur

[troubleshooting.md](troubleshooting.md) lists causes, fixes, and configuration keys by symptom. The mouth interior consistently uses a closed mouth bag, with visible depth and tongue when the mouth opens; hand/face avoidance uses a 5 mm distance field. Past test results do not replace acceptance checks for the current character.

## Files

```
polish/
  build_character.py      main build, driven by the config
  face/                   facial part detection, face texture clean-up, chin, brow overlay, decals
  expr/                   expression building (runs in head profile coordinates)
  hand/                   MakeHuman template hand fitting
  post/                   VRM post-processing: expression finalize, shoulder/knee/elbow correctives, safety shorts, leg skin tone, cuff follow, etc.
  rig/                    rig upload export, left-right symmetry check
  measure/                body measurement, piece sheet, config generation
  profile/                head profile packing
  pipeline/               rig.sh、prepare.sh、build.sh、expressions.sh、polish.sh、head_ratio.sh
assets/head-profile/     starter head profile for new heads (no character mesh or texture)
assets/makehuman-hand/    MakeHuman hand assets (CC0)
studio/                   out-of-box Director Console (open in a browser; see studio/README.md)
studio/tools/             add-media.py (adds dances and motions to the library), vmd2vrma.mjs (MMD motion to VRMA)
studio/MEDIA.md           sources and download pages of the development library
scripts/publish-studio.sh builds studio/ from the working console
references/               Charakuru integration, configuration, head profiles, head proportions, acceptance checklist, troubleshooting (Chinese; English in references/en/)
```

## Known limitations

- Detection rules for new heads were written for Tripo-generated heads; Character 2 has passed acceptance checks from scratch. Head settings are only approximate when the face shape differs greatly from the profile.
- Measurement rules were fitted to two outfits, the purple version (紫色版) and Lavender Denim (薰衣草牛仔); after the first run on a new body type, inspect close-ups of the neck, belt, and cuffs.
- Enable clothing shape corrections (sleeve fitting, cuffs following hands, skirts following legs) according to the configuration instructions only after inspecting the model.
- `work/weights/weighted.blend` must be copied out of the temporary directory for the Charakuru weight task (see step 7 in Charakuru integration).
- Complete head profile packaging supports only purple-head types; new heads can use the starter head profile, but this does not mean arbitrary heads can be packaged.
- The Director Console does not include characters, dances, short motions, or music. Users drag in their own characters; download dances and other media from the original creators' pages as described in [../../studio/MEDIA.md](../../studio/MEDIA.md), and add them to the library with `studio/tools/add-media.py`.
- When hands move quickly toward the face, brief contact of 1–3 mm may still occur for a few frames.
- Long, wide skirts still clip during high leg raises and deep squats. Bone-driven skirts cannot completely avoid clipping; avoiding these poses is recommended in the design.
