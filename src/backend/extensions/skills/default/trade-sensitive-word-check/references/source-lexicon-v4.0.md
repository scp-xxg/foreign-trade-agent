# 外贸业务助手 · 敏感词库（Compliance Lexicon）

> 适用：阿里国际站等 B2B 出口场景的回复、报价单、Listing、FAQ、图片文案、社媒素材
> 用途：Agent 生成后的**自动拦截与改写**，以及人工复核时的检查清单
> 版本：**v4.0（第 4 次迭代）**　｜　规模：26 章 + 附录 ｜ 1223 行 ｜ 9,150 汉字（含代码与英文共 3.4 万字符）｜ 维护：外贸业务助手项目组
>
> 版本规则：**主版本号 = 迭代次数**，每次内容迭代 +1.0；同一轮内的补丁用 v4.1、v4.2。

---

## 迭代记录

| 版本 | 迭代 | 本次新增 | 章节数 | 状态 |
|---|---|---|---|---|
| **v1.0** | 第 1 次 | 骨架：使用方式、分级与处置、中文广告法绝对化用语、英文绝对化与保证性用语、平台规则类表述、认证宣称误用 | 6 | ✅ |
| **v2.0** | 第 2 次 | 医疗功效、环保宣称、价格促销、比较广告、知识产权与品牌词、儿童安全、文化宗教禁忌 | 13 | ✅ |
| **v3.0** | 第 3 次 | 地图与国家表述、数据隐私、8 语种敏感词、机器可读正则规则表、白名单豁免、25 条测试用例、维护机制 | 19 | ✅ |
| **v4.0** | 第 4 次 | 8 个品类专用词库、文案位置级风险矩阵、中译英语义漂移 30 组、外贸黑话对照、AI 幻觉七类风险、三级审核 SOP 与质量指标、词条治理规范 | 26 | ✅ 当前 |

---

## 0. 怎么用

### 0.1 三种接入方式

| 方式 | 做法 | 适合 |
|---|---|---|
| **A. 作为知识库文件** | 整份 md 上传到知识库，让 Agent 在生成后自查 | 最快，适合演示 |
| **B. 作为 Skill 脚本** | 取第 16 章「机器可读规则表」，写成 Python/JS 函数，在输出前跑一遍 | 推荐，可拦截 |
| **C. 作为人工检查清单** | 业务员发稿前按第 18 章测试用例抽查 | 兜底 |

### 0.2 每条规则的四个字段

| 字段 | 含义 |
|---|---|
| **词/模式** | 需要检测的文本或正则 |
| **严重级** | L1 提示 / L2 建议改 / L3 必须改 / L4 直接拦截 |
| **依据** | 哪条法规或平台规则 |
| **建议替换** | 改成什么（可验证、不夸大） |

### 0.3 命中后的输出格式（建议固定）

```
【敏感词命中】共 3 处
🔴 L4 · 「CE certified」· 位置：报价单第 3 段
   依据：CE 是自我声明标志，非机构认证；无 RED 报告即宣称 CE 属虚假宣传
   建议：改为「CE: LVD/EMC compliant; RED pending」
🟡 L2 · 「best price」· 位置：回复第 2 段
   依据：绝对化用语，多数市场属不当商业行为
   建议：改为「competitive price for 500 pcs」
```

---

## 1. 分级与处置

| 级别 | 含义 | 典型情形 | 处置动作 |
|---|---|---|---|
| **L1 提示** | 可能引起歧义，不违规 | 表述含糊、缺少限定条件 | 提示优化，不阻断 |
| **L2 建议改** | 属绝对化/夸大，易被投诉 | best、No.1、100% | 给出替换建议，允许人工放行 |
| **L3 必须改** | 明确违规或高风险 | 虚假认证、站外引导、医疗功效 | 阻断输出，必须改后重跑 |
| **L4 直接拦截** | 法律或平台硬红线 | 禁限售品、地图问题、侵权品牌、伪造产地 | 不生成、不发送，转人工 |

> **一条经验**：L3/L4 宁可误杀。外贸场景里，一条错误认证声明的代价（滞港、退运、平台扣分）远高于一次改写。

---

## 2. 中文广告法绝对化用语

> 依据：中国《广告法》第九条禁止使用"国家级""最高级""最佳"等用语。跨境文案虽以外文为主，但中文素材、中文版报价单、国内宣传同样受约束。

### 2.1 绝对化（L2–L3）

| 敏感词 | 建议替换 | 说明 |
|---|---|---|
| 最好 / 最佳 / 最优 / 最好用 | 表现良好、经测试 | 无法举证的比较级一律避免 |
| 第一 / 排名第一 / 销量第一 | 行业前列（需注明数据来源与期间） | 需可验证 |
| 唯一 / 独家 / 首创 | 较早推出、自主研发 | — |
| 顶级 / 顶尖 / 极致 / 至尊 | 高规格、专业级 | — |
| 国家级 / 世界级 / 国际领先 | 符合 XX 标准 | 需标准号 |
| 王牌 / 王牌产品 / 冠军品质 | 主力型号 | — |
| 万能 / 全能 / 通用一切 | 适用于 XX 场景 | — |
| 永久 / 终身 / 永不 | 长期、质保 X 年 | 承诺性用语 |

### 2.2 保证性（L3）

| 敏感词 | 建议替换 |
|---|---|
| 100% / 百分百 | 高（+ 具体指标，如"良品率 ≥99.5%"） |
| 绝对 / 绝对安全 / 绝对无毒 | 符合 XX 标准 |
| 零缺陷 / 零风险 / 零投诉 | AQL 2.5 抽检、1 年质保 |
| 保证通过 / 包过 / 保证认证 | 可协助准备资料，认证结果由机构判定 |
| 假一赔十 / 无条件退换 | 按合同条款执行（写明条款） |

### 2.3 未证实（L3）

| 敏感词 | 问题 |
|---|---|
| 国际认证 / 权威认证 / 认证齐全 | 未列具体标准号与证书编号 |
| 专家推荐 / 权威推荐 | 需说明是谁、什么资质 |
| 专利技术 | 需专利号 |
| 独家配方 / 保密工艺 | 无法举证，易被认为虚假 |

---

## 3. 英文绝对化与保证性用语

> 英文文案最容易"顺手写大"。以下按风险从高到低。

### 3.1 绝对化（L2–L3）

| 英文 | 建议替换 | 备注 |
|---|---|---|
| best / the best | high-performance、reliable | 最高频命中词 |
| No.1 / #1 / number one | leading（需举证）、one of the leading | — |
| world's best / world-class | professional-grade | — |
| the only / unique | one of the few | — |
| top quality / top-grade | consistent quality | — |
| ultimate / perfect | suitable、well-suited | — |
| unbeatable | competitive | — |
| finest | premium（可举证材质/工艺） | — |
| revolutionary / breakthrough | improved（+ 具体指标） | — |

### 3.2 保证性（L3）

| 英文 | 建议替换 | 备注 |
|---|---|---|
| 100% guaranteed / guaranteed | warranted for X years | guarantee 作名词需限定范围 |
| 100% safe / absolutely safe | tested to [standard] | 安全宣称属高风险 |
| zero defect / zero risk | AQL 2.5 inspection | — |
| risk-free | low-risk（+ 说明） | 金融/贸易场景尤忌 |
| never fails / never breaks | designed for continuous operation | — |
| lifetime warranty | X-year warranty | lifetime 无定义，易纠纷 |
| fully compliant | compliant with [具体法规/标准] | 必须带标准号 |
| certified by CE | CE-marked（自我声明） | **CE 不是认证机构**，见第 5 章 |
| FDA approved | FDA registered / 510(k) cleared（按实际） | 三类含义完全不同 |

### 3.3 空泛修饰（L1，仅提示）

excellent、superior、amazing、perfect quality、high-end、luxury —— 不违规，但**不可验证**，建议换成可量化描述（"130 lm/W""IP66""3-year warranty"）。

> **改写公式**：`形容词 → 数字 + 标准 + 期限`。
> 例：`very durable` → `die-cast aluminum housing, IP66, 3-year warranty`。

---

## 4. 平台规则类敏感表述（阿里国际站）

> 依据：国际站规则中心《商品信息滥发违规处罚规则》《知识产权规则》《交易违规处罚规则》及站外沟通管控公告。

### 4.1 虚假与夸大（L3）

| 表述 | 问题 | 改法 |
|---|---|---|
| 认证齐全 / all certificates available | 未列清单 | 列出实际持有的证书与标准号 |
| 工厂直营 / 源头工厂（无验厂） | 与金品认证冲突时属虚假 | 有验厂报告才写 |
| 月产能 XXX 万（无依据） | 虚标 | 写实际产线数与班次 |
| 已服务 XXX 家客户 | 无依据 | 写具体行业与案例（脱敏） |
| 平台推荐 / 官方合作 | 暗示官方背书 | 删除 |
| 最低价 / 全网最低 | 价格欺诈风险 | 写"competitive for this quantity" |

### 4.2 站外引导（L4）

| 表述 | 说明 |
|---|---|
| 加我 WhatsApp / Skype / WeChat | **主动索要**站外即时通讯账号属违规 |
| 私下付款更便宜 / pay outside the platform | 高交易风险，严禁 |
| 加微信发目录 / 邮箱发报价（主动引导） | 视语境，主动引导有风险 |

> **边界（重要）**：**按买家要求**在下单、物流环节提供 Email / 传真 / 电话是**允许**的；违规的是**卖方主动索要**站外即时沟通账号。区别在"谁先提"。

### 4.3 交易与履约（L3）

| 表述 | 问题 |
|---|---|
| 保证 7 天到货（未核算物流） | 交期承诺不实 |
| 无条件退款 | 与平台规则/合同不符 |
| 可开任何金额发票 | 涉税务违规 |
| 支持任何付款方式 | 与信保/合规冲突 |

### 4.4 图片与素材（L3）

| 元素 | 问题 |
|---|---|
| 主图带文字、水印、二维码、边框 | 违反主图规范，影响搜索排序 |
| 图片含联系方式 | 站外引导 |
| 盗用他人产品图 / 模特图 | 著作权侵权 |
| 认证标识放在主图 | 既违规又降排序 |

---

## 5. 认证宣称误用（高频且高危）

> 这一章是外贸文案里**最容易被忽略、后果最重**的一类。核心原则：**没有证书，不写认证；有证书，写清标准号与范围。**

### 5.1 常见误用对照

| ❌ 错误写法 | 为什么错 | ✅ 正确写法 |
|---|---|---|
| CE certified | CE 是**标志**而非机构发的"证书"；多数品类可自我声明，高风险品类（如部分机械、医疗器械）需公告机构（NB）介入 | CE-marked, compliant with LVD 2014/35/EU |
| certified by CE | CE 不是机构 | 同上 |
| CE certified for all EU countries | 未拆分指令，且可能缺 RED | CE: LVD / EMC compliant; RED pending |
| RoHS certified | RoHS 是限用物质要求，通常出测试报告 | RoHS 2011/65/EU — test report available |
| FDA approved | 多数产品只是**注册**或**备案** | FDA registered（设施注册）/ 510(k) cleared（器械） |
| ISO certified | ISO 9001 是**体系认证**，不是产品认证 | ISO 9001:2015 certified（体系） |
| SGS approved | SGS 出报告，不"批准"产品 | Tested by SGS, report No. XXX |
| UL certified（未取证） | UL 是自愿性安全认证 | UL listed（有文件时）／"designed to UL standards" |
| 通过欧盟认证 | 无具体指令 | Compliant with [指令号] |

### 5.2 认证词的"三要素"检查

任何认证表述，必须同时具备：
1. **标准/指令编号**（如 LVD 2014/35/EU、EN 60598）
2. **标志或文件类型**（CE marking / test report / certificate）
3. **覆盖范围**（哪些型号、哪些市场）

缺任一项 → **L3 必须改**；三项全缺且声称"认证齐全" → **L4 拦截**。

### 5.3 各市场认证词速查

| 市场 | 正确表述 | 常见错误 |
|---|---|---|
| 欧盟 | CE-marked; compliant with LVD/EMC/RED; RoHS test report | CE certified |
| 美国 | FCC Part 15 compliant; UL listed; FDA registered | FDA approved（除非真是） |
| 英国 | UKCA-marked（或 CE，按现行认可安排） | 只写 CE 不说明 |
| 沙特 | SASO compliant; SABER PC/SC issued | 只写"符合沙特标准" |
| 日本 | PSE-marked（菱形/圆形需区分） | 笼统写 PSE |
| 澳洲 | RCM compliant | — |
| 韩国 | KC certified | — |

> ⚠️ 认证要求与认可安排会变（如英国对 CE 的认可、欧盟 GPSR/EPR 的执行口径）。**对外表述一律加"以最新官方要求为准"**，并在报价单注明证书有效期。

---

<!-- 第 2 次迭代追加 -->

---

## 6. 医疗与健康功效宣称（L4 为主）

> 这是**全库最高危**的一类。多数市场对医疗器械、保健、化妆品有专门法规，一句"治疗失眠"就能把普通商品变成"未注册医疗器械"。

### 6.1 绝对禁用（L4）

| 中文 | 英文 | 问题 |
|---|---|---|
| 治疗 / 治愈 / 根治 | cure, treat, heal | 医疗行为，需药品/器械资质 |
| 预防疾病 | prevent disease | 同上 |
| 杀菌 99.9% / 抗病毒 | kills 99.9% germs, anti-viral | 需第三方检测且限定条件 |
| 无副作用 / 绝对安全 | no side effects, 100% safe | 任何医疗产品都不得如此宣称 |
| 替代药物治疗 | replace medication | 严重违规 |
| 临床验证（无报告） | clinically proven | 需可查的临床研究 |

### 6.2 高风险（L3）

| 中文 | 英文 | 处理 |
|---|---|---|
| 改善睡眠 / 缓解疼痛 | improves sleep, relieves pain | 需医疗器械或保健资质，否则删 |
| 抗菌 / 抑菌 | antibacterial, antimicrobial | 需检测报告 + 适用标准 |
| 医用级 / 医疗级 | medical grade | 需资质或标准定义 |
| 促进血液循环 | promotes blood circulation | 涉功效宣称 |
| 增强免疫力 | boosts immunity | 多数市场禁止食品类如此宣称 |

### 6.3 合规改写路径

```
❌ This lamp relieves eye fatigue and improves sleep.
✅ This lamp uses flicker-free drivers (flicker rate <1%) and adjustable CCT (3000–6500K).
   → 描述物理参数，不描述人体功效
```

**判断口诀**：**说产品做了什么（参数），不说它对人做了什么（功效）。**

---

## 7. 环保与可持续宣称（greenwashing）

> `【需核验】` 欧盟《赋能消费者绿色转型指令》(EU) 2024/825 自 **2026 年 9 月起适用**，禁止在无可靠依据时使用泛化环保表述；《绿色声明指令》仍在立法进程中。美国有 FTC Green Guides。**这类词在 2026 年后风险显著上升。**

### 7.1 泛化环保词（L3，无证据即禁）

| 英文 | 中文 | 说明 |
|---|---|---|
| eco-friendly / environmentally friendly | 环保 | 泛化，需具体证据 |
| green / greener | 绿色 | 同上 |
| sustainable / eco | 可持续 / 环保 | 同上 |
| nature-friendly / planet-friendly | 亲自然 | 同上 |
| carbon neutral / net zero | 碳中和 | 需核算方法与抵消凭证 |
| climate positive | 气候正效益 | 极高举证要求 |

### 7.2 具体环保词（L2–L3，需报告）

| 英文 | 需要什么证据 |
|---|---|
| biodegradable | 降解条件与标准（如 EN 13432）+ 测试报告 |
| compostable | 可堆肥认证 |
| recyclable | 当地回收体系可行性说明 |
| recycled content XX% | 第三方声明/追溯 |
| non-toxic | 具体标准（如 RoHS、REACH SVHC） |
| PVC-free / BPA-free | 检测报告 |

### 7.3 改写路径

```
❌ 100% eco-friendly packaging
✅ Packaging: 80% recycled paper (FSC certified), plastic-free inner tray
   → 给比例 + 给认证 + 给具体材料
```

**口诀**：**不给证据的"环保"，等于给自己埋投诉。**

---

## 8. 价格与促销宣称

### 8.1 价格类（L3）

| 中文 | 英文 | 问题 |
|---|---|---|
| 全网最低价 / 最低价保证 | lowest price, price match guarantee | 无法举证即价格欺诈 |
| 原价 XXX，现价 XXX（虚构原价） | was $X, now $Y | 欧盟 Omnibus 要求"原价"为**前 30 天最低价**；中国禁止虚构原价 |
| 限时 5 折（长期如此） | 50% off (permanently) | 虚假紧迫感 |
| 亏本清仓 | below cost | 需真实 |
| 买一送一（实为加价） | buy 1 get 1 free | 价格需真实 |

### 8.2 促销紧迫感（L2）

| 表述 | 建议 |
|---|---|
| Only today / last chance | 若长期使用，改为具体活动期 |
| Limited stock（无库存数据） | 给真实剩余量或删除 |
| 最后 3 件 | 需真实库存 |

### 8.3 报价单里的价格表述（L3）

| 问题 | 改法 |
|---|---|
| 只写 "best price" | 给阶梯价：`USD 17.20/pc @500; USD 15.80/pc @2,000` |
| 价格无有效期 | 加 `Validity: 15 days` |
| 未写贸易术语 | `FOB Ningbo` |
| 未写币种/单位 | `USD 17.20/pc` |
| 隐藏运费 | 明示 `Freight and taxes excluded` |

---

## 9. 比较广告与竞品贬低（L3）

> 多数市场**允许比较**，但要求：真实、可验证、不贬低、不混淆。中国《广告法》明确禁止贬低他人商品。

### 9.1 禁用表述

| 表述 | 问题 |
|---|---|
| 比 XX 品牌好 / 优于同行 | 需可验证的对比测试 |
| 同行都是劣质品 | 贬低竞争对手 |
| 市面上唯一能做到 | 绝对化 + 不可举证 |
| 山寨 / 仿 XX | 侵权 + 贬低 |
| 客户都被 XX 坑过 | 商业诋毁 |

### 9.2 合规比较的四个条件

1. **比的是同类、同规格**（不能拿自己的高配比别人的低配）
2. **数据可验证**（有测试报告或公开参数）
3. **不出现对方商标**（除必要的指示性使用）
4. **不做贬低性描述**（说"我们的驱动是 Meanwell"，不说"他们的驱动是垃圾"）

### 9.3 客户说"对手便宜 15%"时的合规话术

```
✅ 先确认配置差异（驱动品牌、外壳材质、质保年限、是否含测试报告），
   再给"降配版"作为选项，保护主推款价格体系。
❌ 不要说"他们质量差"，也不要说"我们的绝对比他们好"。
```

---

## 10. 知识产权与品牌词（L4 为主）

> 这是国际站**唯一"三次就关店"**的红线（3 振关店制）。配件类最容易踩。

### 10.1 高风险品牌词（示例，非穷举）

| 类别 | 品牌（示例） |
|---|---|
| 消费电子 | Apple, iPhone, iPad, Samsung, Galaxy, Huawei, Xiaomi, Sony, Bose, JBL, Anker, Dyson |
| 电动工具 | Bosch, Makita, DeWalt, Milwaukee, Black+Decker, Hilti |
| 家居电器 | Philips, Panasonic, Tefal, Midea, Haier |
| 运动户外 | Nike, Adidas, Puma, The North Face, Columbia, Decathlon |
| 玩具动漫 | LEGO, Disney, Marvel, Pokémon, Hello Kitty, Barbie, Hasbro |
| 汽车 | Toyota, BMW, Mercedes-Benz, Tesla, Bosch（汽车件） |
| 赛事 IP | FIFA, 世界杯, Olympic, 奥运, NBA, F1 |
| 平台 | Amazon, Alibaba, TikTok（不得暗示官方合作） |

> 完整品牌库建议接入**平台知识产权保护系统**或商标数据库（如 EUIPO、USPTO、中国商标网）做实时比对，本表只做"高频预警"。

### 10.2 三种使用情形

| 情形 | 是否允许 | 写法 |
|---|---|---|
| **指示性使用**（说明适配关系） | ✅ 有条件允许 | `Replacement battery compatible with iPhone 13`（须真实适配，不得暗示授权） |
| **描述性使用**（说明接口标准） | ✅ 允许 | `USB-C connector`、`Type-C` |
| **暗示授权/官方** | ❌ 禁止 | `Apple authorized`、`official supplier of Bosch`、`OEM for Dyson`（无授权时） |

### 10.3 图片与设计侵权（L4）

| 元素 | 风险 |
|---|---|
| 他人产品图、模特图 | 著作权 |
| 品牌 Logo（含模糊、变形、部分遮挡） | 商标 |
| 与爆款高度相似的外观 | 外观设计专利 |
| 动漫/影视角色形象 | 著作权 |
| 赛事标志、吉祥物、口号 | 赛事 IP 专项治理 |
| 名人肖像 | 肖像权 |

### 10.4 标题写法规范

```
❌ Hot Sale Phone Case for iPhone 14 Pro Max Apple Original Quality
   （"Apple"+"Original" 暗示官方）
✅ Phone Case for iPhone 14 Pro Max, Shockproof TPU, Camera Protection
   （仅指示适配机型，不出现品牌方修饰词）
```

---

## 11. 儿童与玩具安全（L4）

> 涉及儿童的商品，几乎所有市场都按"最严标准"审查。文案里的"安全"承诺最容易出事。

### 11.1 禁用/高危表述

| 表述 | 问题 |
|---|---|
| 绝对安全 / 宝宝放心用 | 安全宣称需测试 |
| 无毒无害 / non-toxic（无报告） | 需 EN71-3 / CPSIA 等检测 |
| 适合 0 岁+（未做年龄评估） | 年龄标识需依据 |
| 食品级（无 FDA/LFGB 报告） | 需食品接触材料测试 |
| 通过所有安全测试 | 需列具体标准 |

### 11.2 必须标注的信息

| 市场 | 要求 |
|---|---|
| 欧盟 | CE + EN71 系列、年龄警告、制造商与进口商信息 |
| 美国 | CPC 证书、CPSIA 测试、小零件警告（3 岁以下） |
| 英国 | UKCA + 英国责任人 |
| 澳洲 | AS/NZS ISO 8124 |

### 11.3 图片与文案禁忌

- 不得出现儿童独自使用有窒息风险的小件
- 不得暗示"可入口""可啃咬"（除非是牙胶类且有报告）
- 不得用真实儿童模特暗示产品适用年龄（易误导）

---

## 12. 文化、宗教与政治禁忌（按市场）

> 这一章不涉及"违规"，但涉及**订单能不能成**。中东客户看到猪的元素，生意就结束了。

### 12.1 中东（沙特、阿联酋、卡塔尔等）

| 禁忌 | 说明 |
|---|---|
| 猪、酒精、赌博 | 图片与文案双重规避 |
| 十字架、六芒星等宗教符号 | 不得作为装饰元素 |
| 左手递物 | 人物图避免左手特写 |
| 斋月期间饮食图像 | 改打"家庭、感恩、馈赠"主题 |
| 暴露的女性形象 | 服饰、美妆类尤需注意 |
| 以色列相关标识 | 政治敏感 |

### 12.2 南亚（印度、巴基斯坦、孟加拉）

| 禁忌 | 说明 |
|---|---|
| 牛、牛肉制品 | 印度教禁忌 |
| 猪制品 | 穆斯林禁忌 |
| 部分邦禁酒 | 酒类相关 |
| 宗教符号误用 | 如将神像用于鞋类、地垫 |

### 12.3 东南亚（印尼、马来西亚、文莱）

| 禁忌 | 说明 |
|---|---|
| 猪肉、酒精 | 清真市场 |
| Halal 标识 | **必须有认证**，不得自行标注 |
| 宗教符号 | 同上 |

### 12.4 欧美

| 禁忌 | 说明 |
|---|---|
| 种族、性别、残障刻板印象 | 素材避免单一族裔呈现 |
| 儿童形象商用 | 需授权，且不得暗示不当场景 |
| 纳粹/法西斯符号 | 德国法律禁止 |
| 原住民文化挪用 | 图案、图腾类需谨慎 |
| 体型羞辱（body shaming） | 服饰类文案 |

### 12.5 日本 / 韩国

| 禁忌 | 说明 |
|---|---|
| 数字 4、9（日本） | 礼品类避免 |
| 过度推销式表达 | 文案克制、重细节 |
| 日文"日本製" | 非日本生产不得使用 |
| 韩国"国产" | 同上 |

### 12.6 通用政治红线

| 内容 | 处理 |
|---|---|
| 国家/地区名称与归属表述 | 严格按中国官方口径 |
| 国旗、国徽的装饰性使用 | 避免 |
| 争议地区标注 | 一律使用合规地图 |
| 领导人形象 | 不使用 |
| 涉政、涉宗教冲突话题 | 不涉及 |

<!-- 第 2 次迭代结束 -->

---

## 13. 地图与国家表述（硬红线）

> 这一类没有"改一改"的余地，命中即 **L4 拦截**。

### 13.1 地图素材

| 问题 | 说明 |
|---|---|
| 使用非标准地图 | 必须使用自然资源部标准地图服务或经审核的合规版本 |
| 国界线绘制错误 | 包括九段线、藏南、阿克赛钦、台湾、南海诸岛 |
| 缺漏领土 | 常见于网络下载的"世界地图"素材 |
| 将中国地图用于装饰性拼接 | 易产生错误裁切 |
| 把地区标注为国家 | 严格按官方口径 |

### 13.2 国家/地区名称表述

| 正确 | 错误 |
|---|---|
| 中国台湾 / Taiwan, China | Taiwan（作为国家） |
| 中国香港 / Hong Kong, China | Hong Kong（作为国家） |
| 中国澳门 / Macao, China | Macao（作为国家） |
| 中国大陆 | 用"中国"与"台湾"并列 |

### 13.3 业务场景里的隐性风险

| 场景 | 风险点 |
|---|---|
| 物流报价表按"国家"列 | 需确保地区归属正确 |
| 网站语言/国家选择器 | 不得把台湾列为国家选项 |
| 认证清单按市场分 | 同上 |
| 客户所在地填写 | 系统字段需合规 |

---

## 14. 数据与隐私相关表述

> 涉及"我们怎么处理你的数据"的文案，属于法律承诺，不是营销话术。

### 14.1 高危表述（L3）

| 表述 | 问题 |
|---|---|
| 我们不会存储你的任何数据 | 与事实不符即虚假陈述 |
| 数据绝对安全 / 100% 保密 | 无法保证 |
| GDPR 认证 | GDPR 第 42 条确有认证机制，但须由监管机构认可的认证机构颁发；市面上自称 "GDPR certified" 的多为无效，正确说法是"符合 GDPR 要求"或援引 SCC/BCR |
| 完全符合 GDPR（无依据） | 需 DPA、SCC、数据处理记录 |
| 匿名化（实为假名化） | 术语误用 |

### 14.2 正确表述

| 场景 | 建议写法 |
|---|---|
| 数据处理 | "We process inquiry data solely to prepare quotations, retained for X months." |
| 跨境传输 | "Data may be transferred under Standard Contractual Clauses." |
| 本地部署 | "Deployed on your own infrastructure; model calls are configurable." |
| 知识库 | "Private knowledge base, account-scoped access, source-traceable." |

> 提醒：**本地部署 ≠ 模型数据不出本机**。如果调用了外部模型 API，数据仍会离开本地。这句话写错，是技术评委最容易抓的点。

---

## 15. 多语种敏感词（8 语种）

> 同一句话，英语合规不代表德语合规。以下为各语种的"高频踩坑词"。

### 15.1 德语（DE）

| 词 | 问题 | 替换 |
|---|---|---|
| garantiert / Garantie | "保证"类，需限定范围 | mit X Jahren Gewährleistung |
| beste / bester / Nr. 1 | 绝对化，UWG 禁止无依据比较 | hochwertig、bewährt |
| 100 % sicher | 绝对安全 | geprüft nach [Norm] |
| TÜV geprüft（无证书） | 认证误用 | 仅在持证时使用 |
| umweltfreundlich | 泛化环保，2026 后高风险 | mit XX % Recyclinganteil |
| klima neutral | 碳中和，需核算 | CO₂-Bilanz auf Anfrage |
| Made in Germany（非德国产） | 产地欺诈 | Made in China |

### 15.2 法语（FR）

| 词 | 问题 | 替换 |
|---|---|---|
| le meilleur / n°1 | 绝对化 | performant、reconnu |
| garanti | 需限定 | garanti X ans |
| 100 % naturel | 天然宣称需证据 | à base de [ingrédient] |
| bio（无认证） | 法国对 bio 有专门认证 | issu de l'agriculture biologique（需证书） |
| écologique / vert | 泛化环保 | 给具体指标 |
| fabriqué en France（非法国产） | 产地欺诈 | Fabriqué en Chine |

### 15.3 西班牙语（ES / 拉美）

| 词 | 问题 | 替换 |
|---|---|---|
| el mejor / número 1 | 绝对化 | de alto rendimiento |
| garantizado | 需限定 | con garantía de X años |
| 100 % seguro | 绝对安全 | probado según [norma] |
| ecológico / verde | 泛化环保 | con XX % de material reciclado |
| libre de riesgo | 零风险 | de bajo riesgo（+说明） |
| hecho en España（非西班牙产） | 产地欺诈 | Fabricado en China |

### 15.4 葡萄牙语（巴西 PT-BR）

| 词 | 问题 |
|---|---|
| o melhor / número 1 | 绝对化（巴西 CDC 消费者法典严格） |
| garantido | 需限定 |
| 100 % natural | 需证据 |
| ecológico | 泛化环保 |
| feito no Brasil（非巴西产） | 产地欺诈 |

### 15.5 阿拉伯语（AR）

| 点 | 说明 |
|---|---|
| 宗教用语误用 | "Inshallah""Bismillah" 不宜用于商业承诺 |
| Halal 标识 | 必须认证 |
| 猪/酒相关词 | 完全避免 |
| 左手、脚部意象 | 图片避免 |
| 翻译方向 | 阿语从右至左，排版需适配（数字、标点） |

### 15.6 俄语（RU / EAEU）

| 词 | 问题 |
|---|---|
| самый лучший / №1 | 绝对化（俄广告法严格） |
| гарантировано | 需限定 |
| 100 % безопасно | 绝对安全 |
| экологичный | 泛化环保 |
| EAC 标志（无证书） | 认证误用 |

### 15.7 日语（JP）

| 词 | 问题 |
|---|---|
| 最高級 / 日本一 / No.1 | 景品表示法（不当表示）管得极严，需客观依据 |
| 絶対 / 完璧 | 绝对化 |
| 日本製（非日本产） | 产地欺诈 |
| 安全・安心 | 需具体依据，否则属"优良误认" |
| 効果・効能（日用品） | 涉功效宣称，需资质 |

### 15.8 韩语（KR）

| 词 | 问题 |
|---|---|
| 최고 / 1위 | 绝对化，需依据 |
| 100% 안전 | 绝对安全 |
| 국산（非韩国产） | 产地欺诈 |
| 무독성（无检测） | 毒性宣称 |

---

## 16. 机器可读规则表（可直接实现）

> 以下为正则模式（Python `re` 语法，忽略大小写）。建议按 L4 → L3 → L2 顺序执行，命中即停或累积报告。

### 16.1 L4 拦截（硬红线）

| ID | 模式 | 说明 |
|---|---|---|
| `S401` | `(?i)\b(ce\s*certified\|certified\s*by\s*ce)\b` | CE 表述误用（CE 是标志，非机构认证） |
| `S402` | `(?i)\b(fda\s*approved)\b` | FDA 批准误用（除非确为器械获批） |
| `S403` | `(?i)\b(100\s*%\s*(safe\|secure\|guaranteed\|effective))\b` | 绝对保证 |
| `S404` | `(?i)\b(cure\|treat\|heal\|prevent\s+disease)\b` | 医疗功效 |
| `S405` | `(?i)(whatsapp\|wechat\|skype)\s*[:：]?\s*[\+\d]` | 站外联系方式 |
| `S406` | `(?i)\b(apple\|samsung\|nike\|disney\|fifa\|olympic)\b.{0,20}\b(authorized\|official\|original\|genuine)\b` | 品牌+授权暗示 |
| `S407` | `(?i)\b(made\s+in\s+(germany\|italy\|usa\|japan\|korea))\b` | 产地表述（需核验实际产地） |
| `S408` | `(?i)\b(oem\s+for\|official\s+supplier\s+of)\b` | 官方供应暗示 |

### 16.2 L3 必须改

| ID | 模式 | 建议 |
|---|---|---|
| `S301` | `(?i)\b(best\s+price\|lowest\s+price\|cheapest)\b` | competitive price |
| `S302` | `(?i)\b(no\.?\s*1\|#1\|number\s+one)\b` | leading（需举证） |
| `S303` | `(?i)\b(eco[\s-]?friendly\|environmentally\s+friendly)\b` | 具体材料/比例 |
| `S304` | `(?i)\b(carbon\s+neutral\|net\s+zero\|climate\s+positive)\b` | 需核算说明 |
| `S305` | `(?i)\b(non[\s-]?toxic\|food[\s-]?grade)\b` | 需检测报告 |
| `S306` | `(?i)\b(lifetime\s+warranty\|permanent)\b` | X-year warranty |
| `S307` | `(?i)\b(all\s+certificates?\s+available\|fully\s+certified)\b` | 列具体证书 |
| `S308` | `(?i)\b(guaranteed?\s+delivery\|delivery\s+guaranteed)\b` | 写明交期与条件 |

### 16.3 L2 建议改

| ID | 模式 | 建议 |
|---|---|---|
| `S201` | `(?i)\b(top\s+quality\|world[\s-]?class\|premium\s+quality)\b` | 给参数 |
| `S202` | `(?i)\b(revolutionary\|breakthrough\|ultimate)\b` | 给改进幅度 |
| `S203` | `(?i)\b(only\s+today\|last\s+chance)\b` | 具体活动期 |
| `S204` | `(?i)\b(risk[\s-]?free)\b` | low-risk |
| `S205` | `(?i)\b(amazing\|perfect\|excellent)\b` | 可量化描述 |

### 16.4 中文规则

| ID | 模式 | 级别 |
|---|---|---|
| `C401` | `最好\|最佳\|第一\|唯一\|顶级\|国家级` | L3 |
| `C402` | `100%\|绝对\|永久\|零缺陷` | L3 |
| `C403` | `治疗\|治愈\|根治\|预防疾病` | L4 |
| `C404` | `认证齐全\|国际认证\|权威认证` | L3 |
| `C405` | `最低价\|全网最低\|亏本` | L3 |
| `C406` | `加微信\|加我微信\|私聊` | L4 |

### 16.5 完整规则表（可直接复制，Python）

> 上面表格里的 `\|` 是 Markdown 表格转义，**复制代码请用下面这份**（`|` 即正则的"或"）。

```python
import re

RULES = [
    # ===== L4 拦截 =====
    ("S401", r"(?i)\b(ce\s*certified|certified\s*by\s*ce)\b", "L4",
     "CE 是标志，非机构认证", "CE-marked, compliant with LVD 2014/35/EU"),
    ("S402", r"(?i)\b(fda\s*approved)\b", "L4",
     "FDA approved 仅适用于获批器械", "FDA registered / 510(k) cleared（按实际）"),
    ("S403", r"(?i)\b(100\s*%\s*(safe|secure|guaranteed|effective))\b", "L4",
     "绝对保证", "high reliability / tested to [standard]"),
    ("S404", r"(?i)\b(cure|treat|heal|prevent\s+disease)\b", "L4",
     "医疗功效", "描述物理参数，不描述人体功效"),
    ("S405", r"(?i)(whatsapp|wechat|skype)\s*[:：]?\s*[\+\d]", "L4",
     "站外联系方式", "删除，改用平台内沟通"),
    ("S406", r"(?i)\b(apple|samsung|nike|disney|fifa|olympic)\b.{0,20}\b(authorized|official|original|genuine)\b", "L4",
     "品牌+授权暗示", "compatible with [型号]"),
    ("S407", r"(?i)\b(made\s+in\s+(germany|italy|usa|japan|korea))\b", "L4",
     "产地表述需核验实际产地", "按实际产地填写"),
    ("S408", r"(?i)\b(oem\s+for|official\s+supplier\s+of)\b", "L4",
     "官方供应暗示", "删除或改为 supplier of [自有品牌]"),

    # ===== L3 必须改 =====
    ("S301", r"(?i)\b(best\s+price|lowest\s+price|cheapest)\b", "L3",
     "绝对化价格", "competitive price for [quantity]"),
    ("S302", r"(?i)\b(no\.?\s*1|#1|number\s+one)\b", "L3",
     "绝对化排名", "leading（需举证）"),
    ("S303", r"(?i)\b(eco[\s-]?friendly|environmentally\s+friendly)\b", "L3",
     "泛化环保宣称", "XX% recycled content / FSC certified"),
    ("S304", r"(?i)\b(carbon\s+neutral|net\s+zero|climate\s+positive)\b", "L3",
     "碳中和需核算", "CO2 footprint report on request"),
    ("S305", r"(?i)\b(non[\s-]?toxic|food[\s-]?grade)\b", "L3",
     "需检测报告", "FDA-compliant material, report No. XXX"),
    ("S306", r"(?i)\b(lifetime\s+warranty|permanent)\b", "L3",
     "无定义承诺", "X-year warranty"),
    ("S307", r"(?i)\b(all\s+certificates?\s+available|fully\s+certified)\b", "L3",
     "认证笼统表述", "列具体证书与标准号"),
    ("S308", r"(?i)\b(guaranteed?\s+delivery|delivery\s+guaranteed)\b", "L3",
     "交期承诺", "lead time X days after deposit"),

    # ===== L2 建议改 =====
    ("S201", r"(?i)\b(top\s+quality|world[\s-]?class|premium\s+quality)\b", "L2",
     "空泛修饰", "给参数（130 lm/W, IP66）"),
    ("S202", r"(?i)\b(revolutionary|breakthrough|ultimate)\b", "L2",
     "夸大修饰", "improved by XX%"),
    ("S203", r"(?i)\b(only\s+today|last\s+chance)\b", "L2",
     "虚假紧迫感", "活动起止日期"),
    ("S204", r"(?i)\b(risk[\s-]?free)\b", "L2",
     "零风险", "low-risk（+说明）"),
    ("S205", r"(?i)\b(amazing|perfect|excellent)\b", "L2",
     "空泛评价", "可量化描述"),

    # ===== 中文 =====
    ("C401", r"最好|最佳|第一|唯一|顶级|国家级", "L3", "绝对化用语", "给可验证表述"),
    ("C402", r"100%|绝对|永久|零缺陷", "L3", "保证性用语", "给指标与期限"),
    ("C403", r"治疗|治愈|根治|预防疾病", "L4", "医疗功效", "描述参数"),
    ("C404", r"认证齐全|国际认证|权威认证", "L3", "认证笼统", "列证书编号"),
    ("C405", r"最低价|全网最低|亏本", "L3", "价格夸大", "阶梯价"),
    ("C406", r"加微信|加我微信|私聊", "L4", "站外引导", "平台内沟通"),
]

# 白名单：命中但不应报的模式（上下文豁免）
WHITELIST = [
    (r"(?i)best\s+(regards|wishes)", "S301"),
    (r"(?i)compatible\s+with", "S406"),
    (r"(?i)iso\s*9001", "S307"),
    (r"(?i)fda\s+registered", "S402"),
]

def scan(text: str) -> list[dict]:
    hits = []
    for rid, pat, level, reason, suggestion in RULES:
        for m in re.finditer(pat, text):
            ctx = text[max(0, m.start() - 40): m.end() + 40]
            if any(re.search(w, ctx) and w_rid == rid for w, w_rid in WHITELIST):
                continue
            hits.append({
                "id": rid, "level": level, "match": m.group(0),
                "span": (m.start(), m.end()),
                "reason": reason, "suggestion": suggestion,
            })
    # 同词多命中取最高级
    order = {"L4": 0, "L3": 1, "L2": 2, "L1": 3}
    hits.sort(key=lambda h: (h["span"][0], order[h["level"]]))
    return hits
```

> 落地时把 `RULES` 外置成 YAML/JSON，就能让业务人员自己加词，不用改代码。

## 17. 白名单与豁免（降低误报）

> **不做白名单的敏感词库，上线三天就会被业务员关掉。** 以下为常见误报场景。

| 误报场景 | 处理 |
|---|---|
| `best regards` / `best wishes` | 固定搭配，不判 |
| `guarantee` 出现在 `warranty` 语境 | 若同句有 "X-year warranty" 则降为 L1 |
| `compatible with iPhone` | 指示性使用，允许 |
| `CE-marked, compliant with LVD` | 合规写法，不判 |
| `FDA registered`（设施注册） | 与 `FDA approved` 区分，前者允许 |
| `ISO 9001 certified` | 体系认证，允许 |
| `Tested by SGS, report No. XXX` | 允许 |
| `carbon footprint report available on request` | 允许（有报告） |
| `original design`（自主设计） | 与 `original Apple` 区分 |
| 客户原话引用 | 标注为引用时可豁免，但需人工确认 |

**实现建议**：白名单用"上下文窗口"判断，而非简单字符串排除。例如 `best` 后接 `regards/wishes` 才豁免。

---

## 18. 测试用例集（回归用）

> 每次改规则跑一遍。期望结果：命中的 ID 与级别一致。

| # | 输入 | 期望命中 | 级别 |
|---|---|---|---|
| 1 | `CE certified for all EU countries` | S401 | L4 |
| 2 | `CE-marked, compliant with LVD 2014/35/EU` | — | 通过 |
| 3 | `FDA approved LED lamp` | S402 | L4 |
| 4 | `FDA registered facility` | — | 通过 |
| 5 | `100% guaranteed quality` | S403 / S301 | L4/L3 |
| 6 | `Best regards, Thomas` | — | 通过（白名单） |
| 7 | `This lamp cures eye strain` | S404 | L4 |
| 8 | `Our best price is USD 17.2` | S301 | L3 |
| 9 | `Eco-friendly packaging` | S303 | L3 |
| 10 | `Packaging: 80% recycled paper (FSC)` | — | 通过 |
| 11 | `Add my WhatsApp: +86 138...` | S405 | L4 |
| 12 | `Compatible with iPhone 14` | — | 通过 |
| 13 | `Apple authorized supplier` | S406 | L4 |
| 14 | `Made in Germany`（实际中国产） | S407 | L4 |
| 15 | `Lifetime warranty` | S306 | L3 |
| 16 | `3-year warranty` | — | 通过 |
| 17 | `All certificates available` | S307 | L3 |
| 18 | `CE (LVD/EMC); RED pending` | — | 通过 |
| 19 | `No.1 supplier in China` | S302 | L3 |
| 20 | `Only today, 50% off` | S203 | L2 |
| 21 | `TÜV geprüft`（无证书） | 德语规则 | L3 |
| 22 | `最高級の品質` | 日语规则 | L3 |
| 23 | `加我微信发目录` | C406 | L4 |
| 24 | `认证齐全，可放心采购` | C404 | L3 |
| 25 | `符合 EN 60598，报告编号 XXX` | — | 通过 |

**通过标准**：25 条中至少 23 条判定正确；L4 类**必须 100% 命中**。

---

## 19. 维护机制

### 19.1 更新节奏

| 频率 | 动作 |
|---|---|
| 每周 | 看一次阿里国际站规则中心公告，把新增禁限售/表述要求补进第 4 章 |
| 每月 | 复盘被人工改写的文案，把高频改写词补进对应章节 |
| 每季度 | 复核第 7 章（环保）、第 15 章（多语种），法规变动最频繁 |
| 每次大促前 | 复核第 8 章（价格促销），大促是价格投诉高发期 |

### 19.2 一条新词入库的标准

一条词要进库，必须能回答四个问题：
1. **它错在哪？**（法律/平台规则/文化）
2. **多严重？**（L1–L4）
3. **改成什么？**（必须给可执行替换）
4. **有没有例外？**（白名单）

答不全的，不进库——否则就是制造误报。

### 19.3 参考来源

| 来源 | 用途 |
|---|---|
| 阿里巴巴国际站规则中心 `rulechannel.alibaba.com/icbu` | 平台规则、禁限售、知识产权、处罚 |
| 国际站帮助中心（合规经营栏目） | 违规类型与整改口径 |
| 《新手商家成长宝典》 | 官方对违规风险的分环节说明 |
| 中国《广告法》《价格法》 | 绝对化用语、虚构原价 |
| 欧盟 UCPD、GPSR、(EU) 2024/825 | 不当商业行为、产品安全、绿色宣称 |
| 美国 FTC Act / Green Guides、CPSC | 欺骗性广告、环保宣称、儿童产品 |
| 德国 UWG、法国消费法典、英国 CMA | 比较广告、价格公告 |
| 日本景品表示法、韩国表示广告法 | 绝对化与产地表述 |
| EUIPO / USPTO / 中国商标网 | 品牌词核验 |

> ⚠️ 法规与平台规则具有时效性。本库为**操作指引**，不构成法律意见；对外文案的最终判断以官方最新公告与专业顾问意见为准。

---

## 20. 品类专用词库（8 个高频出口品类）

> 通用规则之外，每个品类有自己的"死亡表述"。以下按品类给出：**高危点 → 合规写法 → 必备信息**。

### 20.1 LED 照明（本项目演示品类）

| 高危表述 | 问题 | 合规写法 |
|---|---|---|
| 护眼灯 / eye-protection lamp | 涉功效宣称 | flicker-free (<1%), CRI>80, adjustable CCT |
| 无频闪（无测试） | 需实测 | flicker rate <1% (tested per IEEE 1789) |
| 寿命 50000 小时 | 需 LM-80/LM-79 数据 | L70 > 50,000h (LM-80 data available) |
| 节能 80% | 需对比基准 | 130 lm/W (vs. 100 lm/W halogen equivalent) |
| 防水（未标 IP） | 无等级 | IP66 |
| 德国芯片 / 美国芯片 | 产地暗示，需真实 | Bridgelux / Epistar chip (origin on request) |
| 通过 CE（带 WiFi 未做 RED） | 认证缺口 | CE: LVD/EMC; RED pending |
| 适用所有国家电压 | 不实 | AC 100–277V, 50/60Hz |

**必备信息**：功率、光效（lm/W）、色温、显指、IP 等级、驱动品牌、质保年限、认证清单（分指令）。

### 20.2 五金与电动工具

| 高危表述 | 问题 | 合规写法 |
|---|---|---|
| 军工级 / military grade | 无标准、严重夸大 | industrial grade, tested to [standard] |
| 德国工艺 / German technology | 产地与技术暗示 | precision die-cast, [具体工艺] |
| 终身保修 | 无定义 | 3-year limited warranty |
| 适用于所有品牌电池 | 适配不实 | compatible with [具体型号列表] |
| 扭矩 XXX N·m（峰值当持续） | 参数误导 | max torque XXX N·m, sustained YY N·m |

**必备信息**：材质、硬度/扭矩、适配型号、电池平台、认证（CE/GS/UL）。

### 20.3 消费电子配件

| 高危表述 | 问题 | 合规写法 |
|---|---|---|
| Apple 原装 / original quality | 商标 + 暗示授权 | compatible with iPhone 15 |
| MFi 认证（无授权） | 需 Apple 授权 | （无授权则不写） |
| 快充 100W（实际峰值瞬时） | 参数误导 | 100W peak, 65W sustained |
| 不伤电池 | 功效宣称 | built-in over-charge protection (IC model) |
| 通过所有安全认证 | 无清单 | CE, RoHS, UN38.3 (含电池时) |

**必备信息**：适配机型、接口协议（PD/QC）、电池容量与 UN38.3、认证清单。

### 20.4 家居日用

| 高危表述 | 问题 | 合规写法 |
|---|---|---|
| 食品级（无报告） | 需 FDA/LFGB | FDA-compliant (21 CFR 177), report No. XXX |
| 抗菌 / 抑菌 | 需检测 | （无报告则删） |
| 永久不掉色 | 绝对化 | colorfastness grade 4–5 (ISO 105) |
| 环保材质（泛化） | 2026 后高风险 | 80% recycled PP |

**必备信息**：材质、尺寸、承重、食品接触合规、清洗方式。

### 20.5 纺织服装

| 高危表述 | 问题 | 合规写法 |
|---|---|---|
| 100% 纯棉（混纺） | 成分不实 | 95% cotton / 5% elastane |
| 免烫 / 抗皱（无整理工艺） | 功能宣称 | wrinkle-resistant finish |
| 色牢度 4 级以上（未测） | 需检测 | colorfastness 4 (ISO 105-C06) |
| 欧洲标准 / OEKO-TEX（无证书） | 认证误用 | OEKO-TEX Standard 100, cert. No. XXX |

**必备信息**：成分比例、克重、缩水率、色牢度、护理标签、OEKO-TEX 证书号。

### 20.6 玩具与婴童

见第 11 章。补充：**年龄标识**必须与测试报告一致；**小零件警告**（3 岁以下）为强制；**CE + EN71-1/2/3** 缺一不可。

### 20.7 化工与材料

| 高危表述 | 问题 | 合规写法 |
|---|---|---|
| 无毒无害 | 需 SDS/检测 | see SDS section 11 for toxicological info |
| 环保溶剂 | 泛化 | VOC content < XX g/L |
| 通过 REACH | 需说明是注册还是 SVHC | REACH compliant; SVHC < 0.1% (screening report) |

**必备信息**：CAS 号、SDS、UN 编号、危险品等级、REACH/RoHS 状态。

### 20.8 机械设备

| 高危表述 | 问题 | 合规写法 |
|---|---|---|
| CE 认证（机械指令需 NB） | 部分机械需公告机构 | CE-marked per Machinery Directive 2006/42/EC |
| 零故障率 | 不可举证 | MTBF XXX hours (test data) |
| 免维护 | 不实 | low-maintenance, service interval XXX h |

**必备信息**：功率、产能、尺寸重量、CE/机械指令、随机文件（说明书/图纸）。

---

## 21. 文案位置级风险矩阵

> 同一句话，放在标题和放在邮件里，风险不一样。**标题受平台规则约束最强，邮件受目的国广告法约束最强。**

| 位置 | 最高危 | 特殊约束 | 检查要点 |
|---|---|---|---|
| **商品标题** | 品牌词、绝对化、关键词堆砌 | 平台规则优先 | 前 3 词核心词；无他人品牌；无 best/No.1；无认证词 |
| **主图** | 文字/水印/二维码/认证标识 | 平台图片规范 | 白底、无文字、无边框、比例 1:1~1:1.3 |
| **详情页** | 功效宣称、认证误用、参数臆造 | 广告法 + 目标国 | 每条参数可溯源；认证带标准号 |
| **FAQ** | 承诺性回答（交期、质保、退款） | 合同法属性 | 用"通常/在…条件下"而非"保证" |
| **报价单 / PI** | 认证表述、价格、交期、贸易术语 | 合同属性最强 | 12 项齐全；认证与证书一致；交期写确定天数 |
| **开发信 / 询盘回复** | 绝对化、站外引导、过度承诺 | 目的国广告法 | 不用 best/cheapest；不索要站外账号 |
| **社媒 / 短视频** | 医疗功效、比较广告、未授权音乐 | 平台 + 广告法 | 不贬低竞品；不用未授权 BGM/形象 |
| **图片 OCR 文字** | 与正文同标准 | 常被漏检 | 图上的字也要过一遍词库 |

> **实践提醒**：90% 的违规发生在**详情页和报价单**，但 90% 的注意力在标题。检查顺序建议反过来。

---

## 22. 中译英语义漂移表（30 组）

> 外贸文案的违规，很大一部分不是"想夸大"，而是**翻译时无意放大了**。中文里中性的词，直译成英文就变成了绝对化。

| 中文原意 | 常见直译 | 漂移后的问题 | 建议写法 |
|---|---|---|---|
| 优质 | superior quality | 绝对化、不可验证 | consistent quality |
| 高品质 | high quality | 空泛 | meets [standard] |
| 领先 | leading | 需举证 | one of the leading（+依据） |
| 顶级 | top-grade | 绝对化 | professional-grade |
| 超值 | super value | 夸大 | cost-effective at this volume |
| 热销 | hot selling | 无依据 | best-selling model in [market]（+数据） |
| 爆款 | explosive model | 无意义且夸张 | top-selling SKU |
| 独家 | exclusive | 需独家授权 | proprietary（有专利号） |
| 首创 | first-ever | 需举证 | early adoption of [technology] |
| 军工品质 | military grade | 严重夸大 | industrial grade |
| 出口级 | export grade | 无标准定义 | meets [目的国标准] |
| 国际品质 | international quality | 空洞 | complies with EN [编号] |
| 厂家直销 | factory direct | 可能违反分销协议 | direct from manufacturer |
| 一手货源 | first-hand source | 无意义 | sourced directly from our factory |
| 源头工厂 | source factory | 与验厂认证冲突时虚假 | verified manufacturer（有验厂报告时） |
| 包清关 | customs clearance guaranteed | 承诺不可控事项 | DDP terms available |
| 双清包税 | double clearance, tax included | 涉低报货值风险 | DDP, declared value per invoice |
| 免检 | inspection-free | 危险表述 | AQL 2.5 inspection before shipment |
| 零投诉 | zero complaints | 不可举证 | （删除） |
| 终身维护 | lifetime maintenance | 无定义 | X-year warranty + paid service |
| 免费样品 | free sample | 需条件 | free sample for orders above X pcs |
| 现货充足 | ample stock | 空泛 | in stock, ships within X days |
| 通过率 100% | 100% pass rate | 不可举证 | first-pass yield XX% (internal data) |
| 食品级 | food grade | 需报告 | FDA-compliant material |
| 药级 | pharma grade | 需资质 | USP Class VI（有报告时） |
| 环保 | eco-friendly | 2026 后高风险 | XX% recycled content |
| 可降解 | biodegradable | 需标准 | biodegradable per EN 13432 |
| 无辐射 | radiation-free | 需检测 | EMC compliant (EN 55015) |
| 静音 | silent | 绝对化 | ≤XX dB(A) |
| 万能 | universal | 夸大 | fits [型号列表] |

> **一句话**：中文里的"形容词经济"，在英文里会被当成**可验证的事实陈述**。所以改写的本质是——**把形容词换成数字**。

---

## 23. 外贸黑话 → 合规表述

> 这些词在业务员之间说没问题，**写进对外文案就是风险**。

| 黑话 | 为什么危险 | 对外写法 |
|---|---|---|
| 一手货源 / 厂家直销 | 暗示无中间商，可能违反分销协议；与验厂认证冲突 | direct manufacturer / verified supplier |
| 包清关 / 双清包税 | 涉及低报货值与税务风险 | DDP terms, declared value per commercial invoice |
| 免检 | 暗示不做质检 | AQL 2.5 inspection before shipment |
| 走量 / 薄利多销 | 无问题，但易滑向"最低价" | volume pricing available |
| 支持一件代发 | 无问题，但需说明是 B2C 还是 B2B | dropshipping supported (MOQ 1 for samples) |
| 可开票（金额随意） | **税务违规** | invoice issued per actual transaction |
| 内部价 / 底价 | 价格歧视风险 | distributor pricing available on request |
| 打点 / 关系 | **商业贿赂**，绝对禁止 | — |
| 通融 / 灵活处理 | 涉合规松绑 | handled per contract terms |
| 先发货后付款（口头） | 无合同保障 | payment terms per agreement |
| 质量绝对没问题 | 绝对化 | AQL 2.5, 3-year warranty |
| 你说多少钱就多少钱 | 价格随意，涉倾销 | price based on quantity and spec |

> **底线**：涉及**税务、贿赂、低报货值**的三类黑话，任何情况下都不进对外文案，也不进 AI 提示词——否则模型会学着用。

---

## 24. AI 生成内容的特有风险

> 传统文案是人写错；AI 文案是**"编得很像真的"**。这一类风险最高，因为看起来最专业。

### 24.1 七类典型幻觉（按发生率排序）

| # | 类型 | 表现 | 拦截方式 |
|---|---|---|---|
| 1 | **虚构认证** | 自动补上 "CE certified"、"FDA approved" | 认证词必须匹配产品档案字段 |
| 2 | **虚构客户/案例** | "we supply to Carrefour, IKEA…" | 客户名必须来自白名单字段 |
| 3 | **臆造参数** | 自动补 lm/W、IP 等级、容量 | 参数必须来自产品档案，缺失写"待确认" |
| 4 | **虚构产能/交期** | "monthly capacity 500,000 pcs" | 必须取自已确认字段 |
| 5 | **语气放大** | 把"建议"译成"guarantee" | 输出后跑词库 |
| 6 | **单位错误** | mm/inch、kg/lb、℃/℉ 混用 | 单位白名单校验 |
| 7 | **引用过期法规** | 引用已废止的指令号 | 法规号做版本校验 |

### 24.2 三条硬规则（写进 Prompt）

```
1. 认证、参数、产能、客户名 —— 只能来自产品档案字段；缺失一律输出「待确认」，
   不得推测、不得补全、不得用行业常见值填充。
2. 任何数字后面必须能指到档案里的字段名；指不到的，删掉。
3. 不确定的地方，用「we will confirm」而不是「we confirm」。
```

### 24.3 "看起来专业"反而是风险信号

AI 最容易在这三处"过度专业"：
- 自动补齐认证清单（因为训练数据里都这么写）
- 自动补上"符合国际标准"（因为听起来对）
- 自动把"约 18 天"写成"18 天"（去掉了不确定性）

**建议**：让 Agent 输出时**保留不确定性标记**，例如 `Lead time: 18 days (subject to production schedule)`。

---

## 25. 三级审核 SOP 与质量指标

### 25.1 审核路径

```
Agent 生成
   ↓
【一级·自动】跑词库（第 16 章规则）
   ├─ 命中 L4 → 阻断，不输出，转人工
   ├─ 命中 L3 → 阻断，给改写建议，重跑
   └─ 命中 L2/L1 → 放行 + 标注
   ↓
【二级·业务复核】业务员看标注项，决定接受/改写
   ↓
【三级·合规复核】仅触发以下情形：
   · 新品首次对外
   · 新市场首次进入
   · 新的认证表述
   · 涉及医疗/儿童/环保/价格促销
```

### 25.2 四个质量指标

| 指标 | 定义 | 目标 |
|---|---|---|
| **拦截率** | L4 命中数 / 总输出数 | 观察值，不设目标（越高说明模型越敢写） |
| **误报率** | 人工判定"不该拦"数 / 总命中数 | **< 15%**（超过就会被人关掉） |
| **改写采纳率** | 接受建议改写的条数 / 给出建议的条数 | **> 70%** |
| **平均处理时长** | 从生成到可发送 | **< 5 分钟** |

> **误报率是生命线**。误报率超过 20%，业务员就会绕过工具直接发——那时词库再全也没用。

### 25.3 每周复盘三问

1. 本周被拦截最多的三个词是什么？（→ 说明模型在哪个环节最容易夸大）
2. 有哪些拦截是误报？（→ 补白名单）
3. 有没有漏检导致客户投诉的？（→ 补规则 + 补测试用例）

---

## 26. 词条治理规范

### 26.1 ID 命名

| 前缀 | 含义 | 示例 |
|---|---|---|
| `S` | 英文规则 | `S401` |
| `C` | 中文规则 | `C406` |
| `DE` / `FR` / `ES` / `PT` / `RU` / `JP` / `KR` / `AR` | 语种规则 | `DE301` |
| `LED` / `TOOL` / `ELEC` / `HOME` / `TEXT` / `TOY` / `CHEM` / `MACH` | 品类规则 | `LED302` |

### 26.2 变更日志格式

```
[2026-11-15] +S309  新增 "guaranteed delivery" L3
             理由：大促期间高频承诺交期
             依据：交易违规处罚规则（承诺未履行）
             替换：lead time X days after deposit
[2026-11-20] ~S301  级别 L3 → L2
             理由：competitive price 语境下误报率 22%
```

### 26.3 冲突处理

| 冲突 | 处理 |
|---|---|
| 同一词命中多条规则 | **取最高级别**，只报一次 |
| 白名单与规则冲突 | **白名单优先**，但记日志供复盘 |
| 多语种规则冲突 | 按目标市场语言优先，其余降级为提示 |
| 新旧规则冲突 | 新规则生效日之后以新为准，旧规则标 `deprecated` |

### 26.4 词条生命周期

```
候选（业务反馈/投诉） → 试用（仅记录不拦截，观察 2 周）
   → 生效（正式拦截） → 复核（季度） → 废弃（标 deprecated，保留 6 个月）
```

> 新增词条**先试用再拦截**，是控制误报率最有效的办法。

---

## 附录 A：一句话速查

| 场景 | 一句话 |
|---|---|
| 写认证 | 没证书不写认证，有证书写标准号 |
| 写价格 | 给阶梯价，不给"最低价" |
| 写功效 | 说参数，不说对人体的作用 |
| 写环保 | 给比例、给认证、给材料 |
| 写比较 | 比配置，不比品牌，不贬低 |
| 写品牌 | 只写 "compatible with"，不写 "authorized" |
| 写安全 | 给标准，不给"绝对安全" |
| 写产地 | 实际在哪产就写哪 |
| 写交期 | 写确定天数，不写 "about 30 days" |
| 写联系 | 不加站外账号，除非买家先要 |
| 写品类 | 参数优先，认证带标准号（第 20 章） |
| 写黑话 | 税务、贿赂、低报货值三类，一律不出口（第 23 章） |
| 用 AI | 认证/参数/客户名只能取档案，缺失写"待确认"（第 24 章） |
| 放位置 | 详情页与报价单风险最高，先查这两处（第 21 章） |

---

*文档结束 · v4.0 · 2026-11-01*
