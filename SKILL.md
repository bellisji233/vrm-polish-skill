---
name: vrm-polish
description: 3D 皮套精修。把 Charakuru 做出的基础 VRM 精修成能直播、能跳舞的模型：闭合头壳、脖子过渡、模板手、肩、膝、肘修正、衣服边缘去肤色、小件物理，约 100 个 VRM 表情（标准表情、ARKit 52、视线、二次元贴片、6 个关节修正），同一个头复用到多套衣服；附验收检查表和通用问题手册。用于用户已经用 Charakuru 走到骨骼和权重、想把模型做到可以直播或在导演台演示时。Polishes a Charakuru VRM into a stream-ready avatar.
---

中文 | [English](references/en/skill.md)

# 3D 皮套精修

## 和 Charakuru 的分工

| 谁做 | 内容 |
|---|---|
| Charakuru | 出图、Tripo 候选、部件和贴图、调头身、绑骨骼、权重转移 |
| 本 skill，在 Charakuru 步骤中间 | `rig.sh upload`、`rig.sh check`（绑骨骼）；`finish_weights.py`（权重算不出时） |
| 交接点 | 权重任务的 `weighted.blend` 复制到项目 `work/weights/` |
| 本 skill | 精修构建、表情和口腔、关节修正、安全裤、头身比、导演台验收 |
| 本 skill 调用套件脚本 | 揺れ物设置和检查、裙子碰撞体、表情工作区和集成、登记回工作台 |

逐阶段的说明见 [references/配合Charakuru.md](references/配合Charakuru.md) 的「分工」。

**本 skill 不包含 Charakuru 的任何代码。** 用户自己从 Charakuru 官方获取套件（版本 1.1.1 实测），skill 只调用套件里的脚本。

## 前置条件

| 需要 | 说明 |
|---|---|
| Charakuru 1.1.1 | 自行获取，按它的许可使用；本 skill 的脚本放在套件之外 |
| Blender 5.2 + VRM Add-on | Charakuru 本身也需要 |
| Tripo 账号 | 一个新角色约 300 积分（候选 100、分割 40、贴图 80、绑骨 20 起） |
| 图像生成 | 部位图和贴图参考图，Charakuru 流程本身需要 |
| Python 3 + numpy + Pillow、Node.js 22 | Pillow 用于零件图和头部贴图 |
| macOS + zsh | 精修流水线的平台要求；`BLENDER` 环境变量可覆盖 Blender 可执行文件路径。导演台支持 macOS / Windows |

## 流程

1. **Charakuru 走到权重完成**：按 [references/配合Charakuru.md](references/配合Charakuru.md) 操作。骨骼这一步用本 skill 的两个工具：
   ```
   zsh polish/pipeline/rig.sh upload <项目>          # 不带贴图的头+身体，低于 10 MB 上传限制
   zsh polish/pipeline/rig.sh check <Tripo 返回的 FBX>  # 左右对称检查，一侧手指偏了自动镜像修正
   ```
2. **头部档案**：见 [references/头部档案.md](references/头部档案.md)。新用户用仓库的 `assets/head-profile/` 起步；它只有标定点、头部设置和二次元贴片，不含首个角色的网格和贴图。新头自动识别五官，用 9 个标定点对齐，按结构重建或跳过相关设置。同一个头换衣服才需要带 `head_rest.npy` 的完整档案。`make_profile.py` 目前只支持独立眼睛、眉毛、折痕部件的紫色头类，人物2 类不能打包。
3. **测量和配置**：
   ```
   zsh polish/pipeline/prepare.sh <项目> <头部档案>
   ```
   自动量出头部坐标、脖子过渡、头发碰撞球、手指、腰部、袖口、揺れ物起点、腰带，拟合模板手，写出 `work/build_character.json`。然后**看 `work/measure/零件.jpg`**：脖子和颜色明显的衣服已自动选好，露腰、露腿这类皮肤零件按图上编号补上，项链这类小件确认后加 `--metal`：
   ```
   zsh polish/pipeline/prepare.sh <项目> <头部档案> --skin 3 --metal --force
   ```
   手调值写进 `work/build_overrides.json`，`--force` 时合并保留；`neck_widen.factor` 对应 `--neck-widen`。详细字段、合并例外见[配置说明](references/配置说明.md)。
4. **一条命令**：
   ```
   zsh polish/pipeline/polish.sh <项目> <头部档案> <输出.vrm> [请求 ID]
   ```
   依次做：构建（头部修整、模板手、按零件补色、权重和物理骨）→ 套件的揺れ物登记和检查 → 表情（构建 77 个形态键）→ 安全裤贴图（配置启用时）→ 肩、膝、肘修正形态。裙子碰撞方案按 `work/skirt-colliders.json` 和 `work/skirt-extra-colliders.json` 应用。没有配置时先自动跑第 3 步。给了请求 ID 时，同时把确认用模型登记回 Charakuru 并完成请求。
5. **比例确认**：用 `zsh polish/pipeline/head_ratio.sh <成品.vrm>` 量头身数，按画风对照推荐值（写实 7.5、理想化 8、日系二次元 6.5、Q 版 3；男女同一标准，同画风男女同台时男性可多 0.25–0.5 头），差 0.3 头以上告诉用户。需要改时直接缩放权重结果，再 `prepare.sh --force` 和 `polish.sh`，见[头身比](references/头身比.md)。
6. **验收**：在导演台（`studio/`，双击 `start-mac.command` 或 `start-windows.bat`）里按 [references/验收检查表.md](references/验收检查表.md) 逐项看，静态截图对比基准版，动作和过渡留录像或连续帧。数字好看不算数，画面为准。

## 遇到问题先查

[references/通用问题手册.md](references/通用问题手册.md) 按现象列原因、处理和配置键。口腔统一为封闭口腔袋，张嘴能看到深度和舌头；手脸避让使用 5 mm 距离场。历史实测不替代当前角色验收。

## 文件

```
polish/
  build_character.py      主构建，配置驱动
  face/                   五官部件识别、脸部贴图修整、下巴、透眉、贴片
  expr/                   表情制作（在头部档案的坐标里运行）
  hand/                   MakeHuman 模板手拟合
  post/                   VRM 后处理：表情收尾、肩、膝、肘修正、安全短裤、腿部肤色、袖口跟随等
  rig/                    骨骼上传文件导出、左右对称检查
  measure/                身体测量、零件图、生成配置
  profile/                打包头部档案
  pipeline/               rig.sh、prepare.sh、build.sh、expressions.sh、polish.sh、head_ratio.sh
assets/head-profile/     新头起步档案（不含角色网格和贴图）
assets/makehuman-hand/    MakeHuman 手部资源（CC0）
studio/                   皮套导演台开箱版（浏览器打开即用，见 studio/README.zh-CN.md）
studio/tools/             add-media.py（把舞蹈、小动作加进曲库）、vmd2vrma.mjs（MMD 动作转 VRMA）
studio/MEDIA.zh-CN.md     开发时曲库的来源和下载地址
scripts/publish-studio.sh 从工作中的导演台生成 studio/
references/               配合 Charakuru、配置说明、头部档案、头身比、验收检查表、通用问题手册
references/en/            以上文档的英文版和本文件的英文版 skill.md；改中文版时同步改英文版
```

## 已知限制

- 新的头的识别规则目前只在 Tripo 生成的头上验证过，人物2 已从头验收；脸型和档案差别大时头部设置只是近似。
- 测量规则是在两套衣服（紫色版、薰衣草牛仔）上拟合的；新体型第一次跑完要看脖子、腰带、袖口的特写。
- 衣服形状类修正（袖子贴合、袖口跟手、裙子跟腿）要看过模型再按配置说明开。
- `work/weights/weighted.blend` 要从 Charakuru 权重任务的临时目录复制出来（见配合 Charakuru 第 7 步）。
- 完整头部档案打包只支持紫色头类；新头可用起步档案，不能据此承诺任意头都能打包。
- 导演台不附带角色、舞蹈、小动作和音乐。用户拖入自己的角色；舞蹈等按 [studio/MEDIA.zh-CN.md](studio/MEDIA.zh-CN.md) 从原作者页面下载，用 `studio/tools/add-media.py` 加进曲库。
- 手快速贴脸时仍可能有几帧 1–3 mm 的瞬间接触。
- 长而宽的裙子在高抬腿和深蹲时仍会穿模，骨骼驱动的裙子做不到完全不穿；设计上建议避开。
