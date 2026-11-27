中文 | [English](en/charakuru-integration.md)

# 配合 Charakuru 使用

Charakuru 版本 1.1.1。

## 分工

Charakuru 做到权重为止；之后的精修、揺れ物（头发、裙子等物理）、表情、关节修正和验收由本 skill 接手。本 skill 不修改套件文件，用到套件功能时调用用户自己安装的套件脚本。

| 阶段 | Charakuru（工作台 + 套件 skill） | 本 skill |
|---|---|---|
| 出图（images） | 部位图 8 张、全身三视图 3 张；用户确认 | — |
| 候选（candidates） | Tripo 生成头、身体各 4 个候选；用户选定 | — |
| 部件和贴图（materials） | 分割、分类、Smart UV、4K 贴图、组装；用户调头身 | — |
| 绑骨骼（rig） | Tripo 绑定，读回骨骼位置 | `rig.sh upload` 导出 10 MB 以内的上传文件；`rig.sh check` 查左右对称，一侧手指偏了镜像修正 |
| 权重（rig） | 素体权重转移，得到 `weighted.blend` | 手腕有独立小配饰导致算不出时，`finish_weights.py` 接着完成 |
| **交接** | `weighted.blend` 复制到项目的 `work/weights/` | 从这里开始 |
| 精修 | — | `prepare.sh` 测量和配置；`polish.sh` 构建头壳、脖子过渡、模板手、按零件配色、物理骨 |
| 揺れ物 | 套件 `spring-setup.py`（设置和检查）、`apply-skirt-colliders.py` | `build.sh` 调用它们，再补手臂和手的裙子碰撞体 |
| 表情 | 标准流程是通常脸、固定视线；表情制作流程不新做口内、牙、舌 | 约 100 个 VRM 表情、封闭口腔袋和舌头；经套件的表情工作区和集成脚本（`expression-lab.mjs`、`integrate-expressions.py`）写入，并通过套件的保留检查 |
| 关节和比例 | 头身在 materials 阶段调，绑骨后锁定 | 肩、膝、肘修正形态，安全裤；`head_ratio.sh` 在权重结果上改头身比 |
| 登记 | 工作台保存完成的 VRM | 给请求 ID 时，把带揺れ物的确认模型登记回工作台并完成请求；最终交付物是 `polish.sh` 输出的 VRM |
| 验收和直播 | 工作台预览 | 导演台（`studio/`） |

下面按 Charakuru 的阶段记和本 skill 衔接的地方，以及实际做下来遇到的坑。

## 0. 每一步的关卡

- **输入不合格就停。** 某一步要的输入做不出来（Codex 额度用完、Tripo 失败、参考图不合格），暂停这一步并报告，不用别的东西代替。例如贴图参考图必须是为这组部件新画的图，部位图裁切对齐后当参考图不行：Tripo 会把正背面都看不到的地方（下巴底、脸侧）按错误内容填满。
- **配饰清单。** 出完立绘就列出每件配饰：在哪、左边还是右边、什么材质（例如：左腕黑色手表、右腕深色手串、两条银项链、左胯钱包链、两耳银圈和黑耳钉）。之后每一步都对照这张清单检查。
- **硬质小配饰不混进衣服组。** Charakuru 规定小饰品跟所属衣服同组；印在衣服上的图案、纽扣可以，单独成块又离开衣服表面的链条、手表、手串不行：贴图从正背面投影，衣服和皮肤的颜色会染到它们的侧面；全身参考图里手腕只有十几个像素，手串和手表分不清。分组时把它们单独成配饰组，或者在本 skill 里按材质统一上色（`region_paint.metal`）。
- **贴图参考图加左右侧面。** Tripo 多视图贴图有正、左、右、背 4 个位置，只给正背面时，肩顶、身体侧面、下巴底由 Tripo 猜。
- **贴图返回后按检查表看。** 6 个方向加下巴底、头顶、腋下和配饰清单里每一件的特写，对照立绘，全部合格才登记。只查 4096、网格对得上、能组装，不算验收。

## 1. 部位图和三视图

- 头部图包含全部头发；身体图必须是 T 字姿势。
- 同一个角色换衣服：头部 4 张图直接沿用，只重做身体 4 张。同一组图片重新生成不保证同一个网格；要逐顶点复用完整头部档案，必须复用原候选或原 GLB。

## 2. 候选

- Tripo 多视图：Smart Mesh P2.0、四边面、面数 25000、生成 4 个。面数设置不沿用，每次生成前检查。
- 同头换装时，头部候选直接复制原项目的 4 个，不用再花积分。
- 身体候选优先选两腿之间空隙大的，权重转移和穿模都更好处理。

## 3. 分割

- Tripo 分割面板选 Auto → Simple（3–6 部件）。
- 同头换装时，复用原头部 GLB，并检查文件与原件逐字节相同，再复用原项目的头部分割结果。

## 4. 贴图

- 上传部位 FBX 时，在「最适合的角度」里填 X=0、Y=90、Z=0，确认正面朝前再继续。
- 头部组的参考图不画头发（Charakuru 规定）：脸、耳朵、下巴底和后颈画成皮肤。
- 套件渲染的线框引导图偶尔出现大块黑色斜带：某个零件的线框修改器炸出巨大三角形，模型本身没坏。用同样的相机参数重渲，删掉线框里超出模型范围的顶点即可。
- Smart UV 展开后要点「保存」，切换到下一个模型前不保存，结果不会留下（不一定弹出提示）。
- 组装报「Returned topology changed」时，多半是 Tripo 存坐标的精度误差让个别面配到了相邻顶点：把返回模型的顶点吸附回原网格对应顶点后另存，再登记。
- 工作台要求头和身体候选各正好 4 个；某个候选没能启动时要补生成，登记是追加的，最多 4 个。
- 参考图提示词里不要写「不要画出衣服下的身体」这类句子，图像生成的安全过滤会拦下。
- 带贴图导出的结果是 ZIP（FBX 加 4K 底色图），解压到各组自己的文件夹后再登记。
- 同头换装时，头发和头部的部位网格与原项目相同，可以复用原项目的 4K 贴图。

## 5. 调比例

- **头部旋转保持 0。** 一旦带着旋转进入下一步，静止姿势里头就是歪的，表情的坐标也对不上。
- 头和脖子要接得上，正面、侧面、背面都看一遍。

## 6. 绑骨骼

- Tripo 的 Rig → 骨架预设选 **VRM 1.0 Humanoid**，确认后再运行。
- 套件导出的头加身体 FBX 带贴图时会超过浏览器上传的 10 MB 限制。用 `zsh polish/pipeline/rig.sh upload <项目>` 导出不带贴图的版本（约 2 MB，几何和材质槽与套件导出逐顶点相同），上传这个文件。
- 骨骼导出的文件名会被 Tripo 忽略，下载下来是 `tripo_convert_*.zip`。
- 导入骨骼前运行 `zsh polish/pipeline/rig.sh check <返回的 FBX>`：左右对应关节的镜像位置差超过身高的 1% 时报出；手指偏了，保留离手指网格中心更近的一侧，另一侧镜像后另存为 `…-symmetric.fbx`，导入这个文件（`node scripts/import-bones.mjs`）。Tripo 正常结果的左右差在 0.7% 以内。
- 导入骨骼后，工作台会锁住头和身体的比例编辑，「重新读取」按钮也不会读磁盘上改过的文件。如果只改头身比，用本 skill 的 `head_ratio.sh` 在权重结果上调整，不用重绑。其他比例或头部旋转要改时，用导入前的项目副本改好，按套件的写入检查覆盖项目文件，再刷新工作台页面。

## 7. 权重

- 套件的权重任务结束后，`weighted.blend` 留在系统临时目录里的 `charakit-job-*` 文件夹，复制到 `work/weights/`，本 skill 从这里开始。
- 手腕上有手串、手表这类独立小零件时，权重任务最后一步会报「Automatic hand weights missing」：套件给手部单独算自动权重，浮在手腕上的小块会让整个手部区域都算不出来。用任务文件夹里的中间结果继续：
  `blender -b <charakit-job-*>/backups/transfer-*/weighted.blend --python polish/rig/finish_weights.py -- <套件> <项目>/work/weights`
  它照套件原样完成这一步，只在算不出时去掉配饰组的零件和其他小块重算一次，配饰沿用最近皮肤的权重。

## 8. 本 skill

- 短袖、露出前臂时，模板手按前臂肤色调色，在手腕处接上（切口 2.5 cm），接缝落在手表和手串下面；模板材质的自发光关掉。紫色版、牛仔装是长袖，还是旧做法。

- 新头使用 `assets/head-profile/` 起步；完整档案用于同头换衣服，打包目前只支持紫色头类，见[头部档案](头部档案.md)。
- `prepare.sh <项目> <头部档案>` 测量并写出 `work/build_character.json`，看过 `work/measure/零件.jpg` 再补皮肤零件（见配置说明）。
- 运行 `polish.sh <项目> <头部档案> <输出.vrm>`。
- 给请求 ID 时会把确认用模型登记回 Charakuru 并完成请求；最终交付的是 `polish.sh` 输出的 VRM（带表情）。

## 9. 精修衔接规则

| 现象 | 原因 | 处理 | 配置键 |
|---|---|---|---|
| 绑定后头偏小 | 头高与身高不匹配 | `zsh polish/pipeline/head_ratio.sh <项目> <成品.vrm> <目标>`，再测量和精修；不消耗 Tripo 积分 | `work/weights/head_scale.json`，见[头身比](头身比.md) |
| `--force` 后手调值丢失 | 生成器不读取旧构建配置 | 手调值放 `work/build_overrides.json`，嵌套对象逐键合并；普通数组键整体替换，带 `+` 后缀的键追加数组 | `mouth_open`、`neck_widen.factor` 等，见[配置说明](配置说明.md) |
| 裙子缺少碰撞体 | 默认物理不足以覆盖裙摆与手臂 | 先用套件 `scripts/plan-skirt-colliders.py` 制作方案；`build.sh` 调套件 `apply-skirt-colliders.py`，再调本仓库 `polish/post/add_skirt_colliders.py` 添加手臂和手的碰撞 | `work/skirt-colliders.json`、`work/skirt-extra-colliders.json`，文件存在才应用 |
| 裙下需要安全裤 | 原贴图没有安全裤 | `polish.sh` 只改贴图，不增加网格 | `safety_shorts: {"hem": 0.5, "material": "Material_lower_body", "palette": "lavender"}`；`hem` 为髋到膝的 0.5 倍位置 |
| 保留原手后手消失 | 手和袖子同材质同颜色，被当成内衬 | 仅在模板手替换原手时启用袖口内衬；衣服去肤色止于测得的袖口 | `cuff_lining`、`template_hand`、`region_paint.cloth[].abs_x` |

## 10. 口腔与代码调用边界

Charakuru 1.1.1 的 `skills/avatar-expression-authoring/SKILL.md` 写明：「口内・歯・舌・テクスチャを新造して欠点を隠しません」。张嘴移动已有唇边，不新做口内、牙、舌。本 skill 整理已有口袋或生成封闭口腔袋，并加入舌头。见[通用问题手册](通用问题手册.md)。版本来源：[Charakuru v1.1.1](https://github.com/nanocle/Charakuru/releases/tag/v1.1.1)。

本 skill 不包含 Charakuru 的任何代码，只调用套件脚本。`expr_build_frame.py` 使用套件自己的 `signature`，只传入报告原位置的物体视图；`finish_weights.py` 原样调用套件 `transfer.finish`，只给它加载的 `body_finish` 换上 `bpy` 包装。套件的 `import-bones.mjs`、`spring-setup.py`、`expression-lab.mjs` 等必须来自用户自己的 Charakuru 安装，不复制到本仓库。

## 11. 依赖和失败处理

精修流水线需要 macOS、zsh、Blender 5.2 + VRM Add-on、Python 3 + numpy + Pillow、Node.js 22。`BLENDER` 指向 Blender 可执行文件，默认 `/Applications/Blender.app/Contents/MacOS/Blender`；`KIT` 可指定 Charakuru 根目录。导演台可以在 macOS / Windows 打开，这不等于精修流水线支持 Windows。

流水线入口启用 `set -e` 和 `pipefail`，构建、表情集成和后处理失败应停止，不继续交付旧产物。当前仍有例外：`prepare.sh` 的零件图渲染和模板手拟合命令以 `|| true` 包装；`build.sh` 的裙子应用也以 `|| true` 包装，之后仅检查输出文件存在。因此不能承诺任意子步骤失败都自动停下。出现错误时检查日志和本轮输出时间，补齐失败步骤后重跑，不把旧文件当新成品。
