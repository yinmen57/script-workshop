## 标准景别术语

shot_type 字段必须使用标准影视术语，可选：近景、特写、中景、全景、大远景、俯拍、仰拍。
对应的英文提示词写法：特写 close-up、大特写 extreme close-up、近景 medium close-up、中景 medium shot（腰部以上 from waist up）、中远景 medium wide shot（全身 full body）、全景/大远景 wide establishing shot（远距离交代环境）。
禁止在 shot_type 里写自由描述文字，这个字段是枚举性质，用于后续按景别批量处理。

---

## 距离类机位的九种取法

按主体在画面中的占比从远到近排列，可用于一个场景内的多机位覆盖：
wide establishing shot from far away 远距离大全景交代环境；medium wide shot showing full body 中远景全身；medium shot from waist up 中景腰部以上；close-up of the character's face 面部特写；extreme close-up on the eyes 眼部大特写；close-up of hands or key detail 手部或关键细节特写；two-shot showing character with environment 人物与环境同框；panoramic ultra-wide view 超宽全景；final dramatic hero shot 收尾的英雄镜头。

---

## 角度类机位的六种取法

low angle looking up at the character 低角度仰拍，让主体显得强势高大；high angle looking down at the character 高角度俯拍，让主体显得弱小被压制；side profile view 侧面剪影视角；bird's eye view from directly above 正上方鸟瞰；worm's eye view from ground level 贴地虫视；dutch angle tilted composition 荷兰角倾斜构图，用于制造不安与失衡感。
选择角度不是为了变化而变化，仰拍与俯拍直接改变观众对角色力量关系的判断。

---

## 特殊视角与主观镜头

over-the-shoulder perspective 过肩视角，用于对话戏建立双方关系；point-of-view shot from character's eyes 主观视角，让观众代入角色视线；tracking shot as if camera is moving alongside 跟移镜头，摄影机与主体并行移动；reflection shot in a mirror or window 借镜面或窗户的反射构图；silhouette against bright background 逆光剪影。

---

## 构图规则

symmetrical centered composition 对称居中构图，画面稳定、仪式感强，适合强调秩序与压迫感。
rule-of-thirds off-center framing 三分法偏心构图，是最通用的自然构图，主体落在三分线交点上。
两者是互斥选择：一个镜头要么对称居中，要么三分法偏心，不要在同一提示词里同时要求。

---

## 焦点与景深控制

rack focus with blurred foreground 变焦点镜头，前景虚化并把观众注意力从一处引导到另一处。
medium close-up with shallow depth of field 浅景深近景，背景虚化突出主体。
shallow depth of field 浅景深与 anamorphic lens flare 变形宽银幕镜头光晕搭配使用，是营造电影感的常用组合。

---

## 一个场景的多机位覆盖策略

对同一场景做 25 格分镜覆盖时，用固定的视角清单逐格渲染，每格只改机位描述、其余提示词保持一致：距离类九种、角度类六种、特殊视角五种、构图与焦点五种。
每格提示词的构造方式是 Based on {场景描述}, render a {机位描述}. 再追加一致性锁定句 Maintain identical character designs, clothing, environment and art style as the reference image. Cinematic film quality.
这样保证 25 张图之间只有机位差异，不出现角色或环境漂移。

---

## 镜头运动术语

推镜 push in / dolly in，向主体靠近，收紧画面制造压迫或强调；拉镜 pull out / dolly out，远离主体，交代环境或制造疏离；平移 pan，水平摇摄扫过场景；环绕 orbit，绕主体旋转，展示立体感与空间关系；固定 static / locked-off，机位不动，让表演成为唯一变化；跟拍 tracking / follow，跟随主体移动。
摇移类补充：上摇 tilt up、下摇 tilt down、横移 lateral track，用于在同一机位内改变画面重心。切换类补充：叠化 dissolve 用于现实与回忆的衔接，快切 quick cut 用于蒙太奇压缩时间，这两类不属于机位运动，必须单独成镜。
运镜不是每一镜都要有。台词镜、反应镜默认用固定，把变化留给表演；只在需要强调、需要交代空间、需要制造不安时才动机位。
写 video_motion_prompt 时运动方式必须配速度描述，例如 slow push in、rapid tracking shot。

---

## 单镜时长与整片节奏

单镜 duration 取 1.5 到 4 秒，2 秒是基准值，允许 0.5 秒粒度（1.5、1.8、2.5 这类值都成立）。
时长由这一镜承载的信息量决定：一句短台词、一个反应、一个纯情绪特写给 1.5 到 2 秒；带明确动作或需要交代环境的镜头给 3 秒；长旁白、蒙太奇快切、叙事转折给 4 秒；5 秒以上只留给收尾长镜。
一集拆 32 到 43 个镜头，按 Part 分块推进，每块 32 镜左右。整片时长等于各单镜时长之和，不额外预留转场时间。
运镜密度上，固定机位占全片四成左右，其余六成里推镜类占大半，摇移与跟拍是少数。旁白承载叙事时画面要稳，镜头一直动会和旁白抢注意力。

---

## 多镜头合并为一次视频生成任务

视频模型支持在一次生成里完成多个镜头的切换，所以「一个分镜等于一次生成任务」不成立：分镜是叙事最小单元，镜头组才是生成单元。
把连续分镜按可合并条件打包成镜头组，一组提交一次视频任务。组内总时长不超过 15 秒，这是模型单次生成的硬上限；组内镜头数由该上限倒推，不单独设限。
可合并的硬条件有两条：组内所有分镜的场景与时间标签完全相同；组内出现的角色集合不变，即传给模型的参考图集合不变。
必须断开的情况有三种：场景或时间发生变化；有角色进出画面导致参考图集合变化；出现叠化、回忆闪回、蒙太奇快切这类需要单独控制的镜头，它们各自独立成组。

---

## 镜头组视频提示词的写法

镜头组提示词按分镜顺序分段写，每段对应一个镜头，写法是「第 N 镜（时长）：景别 + 主体动作 + 环境与光线 + 运镜」。
段与段之间必须写出明确的切换指令（cut to / 切至下一镜），否则模型会把多段描述糅成一个连续长镜，丢掉预设的切点。
一致性锁定句在提示词末尾只写一次，覆盖整组：Maintain identical character designs, clothing, environment and art style as the reference image. Cinematic film quality.
duration 传组内各镜时长之和的整数值，不传智能时长，避免模型自行决定片长后打乱切点节奏。
