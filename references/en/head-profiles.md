[中文](../头部档案.md) | English

# Head Profiles

Expressions and head polishing depend on the head mesh itself: where facial features are, which vertices belong to the sclera and iris, and where decals attach. These data are saved per head as a head profile.

## Starter Head Profile

New users can use `assets/head-profile/` directly: it contains only landmarks, head settings, and anime decals, without the first character's mesh, face texture, or hair texture, and without `head_rest.npy`. Any new head can enter the automatic identification workflow through it; supported structures are listed under "New Heads" below.

```sh
zsh polish/pipeline/prepare.sh <project> assets/head-profile
zsh polish/pipeline/polish.sh <project> assets/head-profile <out.vrm>
```

Character 2 (人物2) has passed acceptance checks from scratch. The configuration generated with the starter head profile matches the full profile's configuration item by item, and the expression stage completes successfully. Use a full profile only when changing outfits on the same head and requiring vertex-by-vertex reuse.

## Contents of a Full Profile

A head profile is a folder:

| Content | Purpose |
|---|---|
| `profile.json` | Head-specific parts of the build configuration (skull, hair chains, jaw, brow overlay, decals, sclera repainting, earrings, etc.), with paths relative to the profile folder; also head colliders, facial skin tone, and expression camera |
| `head_rest.npy` | Head vertex positions in profile coordinates, used to determine whether a new project uses the same head and calculate `frame` |
| `expr-data/` | Component IDs (sclera, iris, eyelashes, eyebrows, mouth), eye and mouth opening boundaries, and landmarks such as eye and mouth corners |
| `face/` | Corrected face texture (eyebrows removed, mouth line softened), chin crease vertex pairs, and assembly-space transform |
| `hair/` | Hair texture and cleaned hair texture |
| `fx/` | Blush, star-eye, heart-eye, cat-mouth, and other decals, plus `fx.json` |

Package from a completed purple-head-type project. `make_profile.py` currently requires separate eye, eyebrow, and crease components; Character 2-type heads produce an error listing missing configuration and cannot be packaged. `roles.json` and `overrides.json` are copied if present:

```
blender -b <project>/work/weights/weighted.blend --python polish/profile/make_profile.py -- <project>/work/build_character.json <profile-folder>
```

## Changing Outfits with the Same Head

Reuse the original candidate or original head GLB to retain the same mesh. Regenerating from the same images does not guarantee vertex correspondence.

1. `prepare.sh` fits the new project's head vertices point by point to `head_rest.npy`, producing scale `s` and translation `t` (a different vertex count or root-mean-square fitting error that fails `rms < 0.002 × s` m means it is not the same head).
2. Write `frame: {"s": s, "t": [tx, ty, tz]}` into the new project's configuration.
3. Build and expression operations run in profile coordinates, then transform back on completion; profile data and values remain usable unchanged.

The automatic fit for the denim outfit matched the manual calculation (s = 1.03604, with t differing by less than 0.01 mm).

This method let the denim outfit reuse all head polishing and about 100 VRM expressions (standard expressions, ARKit 52, gaze, anime decals, and 6 joint corrections) from the purple version (紫色版), without changing a single script line.

## New Heads

New heads do not require a manually created profile first. When `prepare.sh` finds that the vertex count or shape does not match the profile's head, it automatically takes the new-head route:

1. **Identify components** (`polish/face/locate.py`): split the head mesh into connected components and determine their roles from relationships between them:
   - Facial skin: the large component with the most openings;
   - Eye openings: two symmetric holes in the skin;
   - Sclera: the largest light-colored component inside each opening;
   - Upper eyelashes: large dark components above the openings;
   - Irises: components in front of the sclera;
   - Eyebrows: symmetric wide components above the upper eyelashes; eyelid creases: thin components between eyelashes and eyebrows;
   - Small components: those along opening edges are lower eyelashes; flat, dark components along the upper edge are eyeliner; flat components within the iris area are iris highlights;
   - Nose, earrings;
   - Mouth line: texture darker than skin in the center of the lower face;
   - Chin, nose tip.

   All 59 components of the purple version's head matched manual labeling, with 0 mm error at the four eye corners.
2. **Align to the profile's face**: fit uniform scale and translation using 9 points—eye corners, mouth corners, mouth center, nose tip, and chin—and write them to `frame`. Adapt head settings in this coordinate system. Rebuild or skip sclera, iris layers, skull, jaw, and brow overlay according to the new head's structure; convert mouth settings using this head's landmarks rather than copying all parameters unchanged.
3. **Write this head's own data** to `work/measure/`:
   - Component lists and IDs (for sclera repainting, eyelid creases, and brow overlay);
   - Chin creases (convex crease edges near the profile's crease lines);
   - Its own assembly transform (for placing hair, `hair_affine`);
   - Corrected face texture (`polish/face/head_texture.py`: remove eyebrows painted on skin, cheek creases, and jaw contour lines, and change the mouth line to a soft lip color); before/after comparison at `work/measure/texture/贴图修整前后.jpg`.
4. **Expressions**: identify components again in the expression workspace (the skull and neck transition now exist), then run expression scripts using the identified IDs.

The denim outfit was run through the complete new-head workflow once (without vertex-by-vertex correspondence, using only the identification and alignment above):

- **Alignment**: scale 1.03605, compared with 1.03604 for exact vertex-by-vertex fitting;
- **Result**: all approximately 100 VRM expressions (standard expressions, ARKit 52, gaze, anime decals, and 6 joint corrections) were present; differences from the vertex-by-vertex version for neutral, eyes closed, smiling, mouth open, angry, and blinking occupied about 1% of the image.

The second character (Character 2, male) has a genuinely different head, with a structure different from the purple version:

- Eyelashes are part of the facial skin, without separate eyelash components;
- Irises are painted on the eyeballs, without separate iris components; each eyeball has two overlapping copies;
- Eyebrows are painted only on the skin;
- The head is a closed whole head rather than a face mask, so no skull needs to be added.

Handling for this head type:

- `structure` in the identification result indicates which component types are missing;
- Eyebrow motion moves the forehead skin, carrying the painted eyebrows with it;
- Irises painted on the eyeballs are split into a separate material layer, with gaze translating the texture; heads with separate iris components still use geometric motion;
- Sclera repainting, brow overlay, skull, and jaw rounding are automatically skipped;
- Mouth position, mouth cavity size, smile amplitude, and the affected area of mouth motion are all converted using this face's own landmarks (mouth corners, nose tip, chin, and interpupillary distance);
- Anime decals are moved onto this face using the landmarks.

Result: about 100 VRM expressions (standard expressions, ARKit 52, gaze, anime decals, and 6 joint corrections), with complete ARKit 52 bindings. Neutral, eyes closed, smiling, angry, sad, surprised, relaxed, five mouth shapes, gaze in four directions, and the Reze dance were inspected in the Director Console at 120 Hz.

**Limitations**:

- Identification rules support two structures: separate sclera, iris, and eyelash components, or features painted together; so far they have been tested only on Tripo-generated heads. Heads matching neither structure fail at identification with a message naming the missing component.
- When the face shape differs greatly from the profile, head settings are only approximate: aligned landmark errors are recorded in `measure.json`; errors exceeding a few millimeters require close inspection of the chin, mouth interior, and cheeks.
- Hair on new heads is re-rooted with `hair.root: head_width`, with positions fitted from measurements. Decals prefer the project's `work/fx/fx.json`; otherwise they are transformed using landmarks. Their positions still need checking.
- Profiles do not save `mouth_open` or `mouth_mood`, and `iris_layer` lacks full same-head profile round-trip support. Put persistent manual values in `work/build_overrides.json`; see [Configuration](configuration.md).

## Choosing a Route by Symptom

| Symptom | Cause | Action | Configuration key |
|---|---|---|---|
| No existing character profile | New project has no vertex-by-vertex baseline | Use `assets/head-profile/` to identify this head automatically | Profile `starter`, `landmarks`; generates `frame` |
| Head position changes after an outfit change | Same mesh with different scale and translation | Fit point by point using a full profile; retain the original candidate | `head_rest.npy`, `frame.s/t` |
| New head differs structurally from the profile | Eyes and eyebrows may be painted on textures | Select geometry or texture route according to `structure` | `iris_layer`, `eye_white_fill`, `brow_overlay`, `skull` |
| Opening the mouth exposes a light inner wall | Input has only a face shell or an unprocessed existing mouth pocket | Use a closed mouth bag consistently; see [Troubleshooting](troubleshooting.md) | `mouth_bag`, `mouth_open` |

The expression stage builds 77 shape keys. The final number registered in the VRM varies with character decals, retained items, and corrections; no fixed total is specified.
