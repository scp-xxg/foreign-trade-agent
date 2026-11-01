# LYRECO 真实公开资料背调测试

测试日期：2026-11-01（Asia/Shanghai）。真实来源获取与四阶段服务调用完成于约12:38—12:39。测试对象是真实企业，但不是已确认客户；未联系该企业，未提交其联系表单。

## 测试范围与结论

实际使用现有开发容器调用生产代码 `core.foreign_trade.diligence.run_stage`，未替换网络或模拟服务返回。先自动读取公开资料，再由测试执行者从原文整理证据与findings，交给四阶段服务检查。因此，本次证明真实公开数据读取及后端业务逻辑可运行，不证明模型能自主完成整条编排。

四阶段均返回结果，8项断言通过。当前本地网页 `http://localhost:3002` 返回连接拒绝，本次没有完成登录HTTP接口、前端聊天或真实模型端到端验收。没有修改应用配置、重启服务或使用旧验收结果替代本次结果。

## 收集到的真实资料

| 信息 | 本次读取结果 | 来源及限定 |
|---|---|---|
| 法定名称候选 | LYRECO | GLEIF同名、同登记国家记录；尚未独立绑定集团官网与该法人 |
| 登记国家、城市 | FR / MARLY | GLEIF法律地址 |
| 登记编号 | 400423968 | GLEIF `registeredAs`，非另行查询法国工商数据库 |
| LEI | 9695008VOHGGNWBV6W58 | GLEIF记录 |
| 实体状态、LEI状态 | ACTIVE / ISSUED | 两种不同登记字段，均非信用或付款能力证明 |
| 其他登记字段 | conformityFlag=NON_CONFORMING | 原始来源已留存；本次未调查其具体含义，不能据此推断违法或信用风险；现有自动事实卡未展示此字段 |
| 公开业务 | office supplies, furniture, IT equipment, printing solutions, personal protective equipment, hygiene, coffee, catering | 集团官网自述，不自动归为每个法人或子公司的业务 |
| 公开联系入口 | https://www.lyreco.com/group/contacts | 官网联系表单，没有提交 |
| 具名采购负责人 | 未取得可核验资料 | 联系入口不等于采购联系人或决策权限证明 |
| 真实交易条件 | 未提供 | 无金额、付款条件或合同／收款主体，不补造 |

来源：

- [LYRECO集团官网](https://www.lyreco.com/group/)
- [集团官网介绍页](https://www.lyreco.com/group/about/lyreco-international-footprint)
- [官网联系页](https://www.lyreco.com/group/contacts)
- [GLEIF记录](https://api.gleif.org/api/v1/lei-records/9695008VOHGGNWBV6W58)

## 四技能实际输出

共同输入版本：`1853f09c52ea296d`。卖方“办公用品与办公收纳”仅为项目演示匹配方向，不是用户真实产品及供货能力声明。没有提交主体已获人工确认的标志。

| 技能 | 返回状态 | 本次业务解读 |
|---|---|---|
| 企业身份核验 | evidence_pending_review | 找到登记证据，官网与法人关系仍待人工核验，不把同名登记自动视为主体确认 |
| 业务与采购匹配 | needs_review | 官网经营品类与演示方向相关；真实MOQ、价格、认证、交期及采购意向未知，不能判断完整匹配 |
| 联系人与决策链核验 | evidence_pending_review | 有官网联系入口证据，但没有具名采购人员、任职或审批权限证据 |
| 交易风险与合作建议 | incomplete_checks | 信用、司法、制裁均为not_queried；交易条件缺失，不作信用或授信结论 |

建议仅作为继续核实的企业候选：先确认应接洽的地区法人及供应商入口，再取得采购岗位、需求和交易条件。当前结果不是合作批准。

## 8项检查

1. 四阶段均返回实际结果。
2. 所有阶段保留人工复核。
3. 未冒充已确认主体。
4. 信用、司法、制裁保持未查询。
5. 缺交易条件返回不完整状态，而非全面通过（不是发送或付款拦截测试）。
6. 同输入四阶段版本一致。
7. 不存在于原文的引用被输入校验拒绝。
8. 单独的合成对象触发合同／收款主体差异与账户变更提示。该探针与LYRECO完全分离，不是该公司的风险事实。

详细断言见 [summary.json](summary.json)。单个企业和合成边界案例不足以计算业务准确率、风险漏检率或获客效果。

## 本次发现的改进点

- **联系渠道用途识别：**自动提取到了 `privacy.office@lyreco.com`。联系页上下文明示其用于个人数据权利请求，因此本次明确排除其作为采购或开发信渠道。现有输出只有公开列出和权限未知标志，缺少用途分类及非商务邮箱排除，需要改进。
- **来源主体层级：**集团网站与同名法人需要进一步绑定，不能把集团业务、覆盖市场和人员信息自动归给单一法人。
- **自动抓取到结论的衔接：**初次无findings输入时，服务虽在public_research中获取了真实资料，顶层状态仍为insufficient_data；整理原文证据并重新输入后才进入待审状态。这意味着完整工作流依赖模型正确提取和组织findings，本次没有验证这一步自动完成。
- **联系人阶段状态精度：**只提供联系表单证据也可得到evidence_pending_review，前端应同时明确显示“具名采购负责人未核实”，避免误读为决策链完整。

## 证据与复跑

- `website-source.json`、`contact-source.json`、`registry-source.json`：实际读取文本、URL与获取时间。
- `input.json`：带真实原文摘录的四阶段输入。
- `identity-check.json`、`business-fit.json`、`decision-chain.json`、`transaction-risk.json`：四份实际回执。
- `*-initial.json`：首次未整理findings时的真实读取结果。
- `synthetic-risk-probe.json`：独立合成风险探针，不归属真实公司。
- `research.py`、`collect.py`、`run_acceptance.py`：可复跑脚本，按此顺序执行；重新读取会覆盖本目录证据，保留本轮资料后再复跑。

在项目根目录、开发容器内运行：

```bash
.venv/bin/python outputs/diligence-live/research.py
.venv/bin/python outputs/diligence-live/collect.py
.venv/bin/python outputs/diligence-live/run_acceptance.py
```

这些脚本读取公开网络并写本地测试结果，不发送邮件、不保存CRM、不签约或授信。
