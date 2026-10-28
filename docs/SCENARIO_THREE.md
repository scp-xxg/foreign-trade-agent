# 场景三：跨岗位协同与内部交接

版本 0.3.0 的主入口是聊天中的“外贸业务助手（演示）”。协同工作台用于查看同一账号下的记录、负责人标签、依赖、待确认事项和审核结果。它复用场景一的询盘与报价、场景二的产品资料包，不另建报价计算规则。

## 业务范围

这是**当前账号下的岗位协同记录**。业务、采购、美工、运营、合规是岗位标签；负责人是用户填写的姓名或称呼。填写负责人不会赋予其他账号访问权限，也不会通知、邀请或向其发送消息。审核操作记录当前认证用户与时间，不伪称另一位负责人已经操作。

所有外部内容仍为草稿。可内部交接不代表已经向客户发信、已上架、可直接发货，或已取得认证、销售授权与合规结论。实际供货、库存、运费、税费、运输时效、保修等未知条件应保留在待确认事项中。

## 六项任务

| 任务 ID | 岗位 | 必需前置任务 | 审核内容 |
|---|---|---|---|
| `sales_requirements` | 业务 | 无 | 询盘原文、产品条件、目的国、买家公开资料及未知项 |
| `procurement_quote` | 采购 | `sales_requirements` | 当前报价、费用范围、供货与交期风险 |
| `design_assets` | 美工 | `sales_requirements` | 已生成图片、来源与署名；模拟示意图不称为实物照片 |
| `operations_content` | 运营 | `design_assets` | 当前商品文案、FAQ、确认事实和缺失商务条件 |
| `compliance_review` | 合规 | `procurement_quote`、`operations_content` | 来源、图片许可、模拟标记及不实承诺检查 |
| `sales_handoff` | 业务 | `compliance_review` | 所有岗位有效审核、风险与未确认事项、内部交接范围 |

可填写状态为 `todo`、`in_progress`、`in_review`、`cancelled`。`done` 只能由服务端在人工审核成功后写入，不能通过普通状态更新直接设置。取消任务会阻止整单导出，不等于完成。

可以增加前置依赖；不能移除模板必需依赖，也不能形成自依赖、重复依赖或环。`stale`、`blocked` 和 `workflow_status.ready_for_handoff` 由服务端计算，模型不能自行宣称为完成。

## 同一订单资料与独立参考

未指定 `content_pack_id` 且 `prepare_catalog_content=true` 时，当前自动准备能力仅支持**询盘中只有一个 DESK-001 产品行**。它导入：

- [模拟规格 CSV](../extensions/foreign_trade/demo_product/desk-001-demo-specs.csv)：来自仓库模拟目录。
- [程序绘制的几何示意图](../extensions/foreign_trade/demo_product/desk-001-demo-schematic.png)：明确标注虚构演示，不是真实产品照片或实际结构证据。
- [来源、声明和 SHA256 清单](../extensions/foreign_trade/demo_product/desk-001-demo-sources.json)。

创建只保存候选事实、原始资料和图片署名，**不确认事实、不生成资料、不完成任务**。首次回执的 `content_preparation` 会说明新建的 `pack_id`，且 `facts_confirmed=false`、`generated=false`。后续查询显示当前资料状态。

`content_relationship` 有两种值：

| 值 | 含义 |
|---|---|
| `transaction` | 同一模拟 SKU 的目录绑定资料；服务端检查绑定、型号、名称及所用事实 |
| `independent_reference` | 独立产品参考；不构成本询盘规格或报价依据 |

Raspberry Pi 5 的公开规格与许可照片只能作为独立参考，不能绑定为 DESK-001，也不能套用 DESK 的价格、MOQ 或生产周期。其他 SKU、多 SKU 或尚无资料的询盘可以设置 `prepare_catalog_content=false`，保留资料待办，之后用 `link_content` 关联当前账号已有的资料包。任意上传资料不会因名称相似自动获得目录产品绑定。

## 完整示例：LYRECO 公开资料＋DESK 模拟交易

以下是一条**团队构造的演示询盘**，不是 LYRECO 发来的邮件、采购单或合作证明。LYRECO 官网 `https://www.lyreco.com/group/` 和登记查询仅供核对公开公司信息；不编造联系人、邮箱或采购意愿。示例中的负责人也是操作演示标签。

### 1. 保存询盘并报价

在聊天中明确提出：

> 请使用 LYRECO、注册国 FR、官网 https://www.lyreco.com/group/ 的公开资料演示买家核验。团队构造的询盘为 DESK-001，500 件，标准包装，交付目的国 Spain，未指定生产天数。请保存询盘、查询产品、计算模拟报价并准备内部协同；不是实际订单，不联系客户。岗位标签设为业务经办、采购经办、美工经办、运营经办、合规经办。

助手读取对应技能，使用 `trade_save_inquiry` 保存明确条件，使用 `trade_inquiry(action="verify_buyer")` 核验公开资料，再用 `trade_calculate_quote` 保存报价。每个后续操作都取最新成功回执的 `inquiry_id` 和 `revision`，不能心算修订号。

按当前模拟目录，500 件标准包装的货值为 USD 2400.00，包装费 USD 0.00；运费及未核定费用不计入小计。金额以实际工具回执为准。公开来源不可访问时保留“未核实”，不能自动认定买家不可靠。

### 2. 建立协同单

工具参数示意如下；`INQUIRY_ID` 代表刚取得的真实记录 ID，不是可直接照抄的值：

```text
trade_collaboration(
  action="create",
  data={
    "title": "LYRECO 公开资料＋DESK 模拟订单协同",
    "inquiry_id": INQUIRY_ID,
    "prepare_catalog_content": true,
    "assignees": {
      "sales": "业务经办",
      "procurement": "采购经办",
      "design": "美工经办",
      "operations": "运营经办",
      "compliance": "合规经办"
    }
  }
)
```

读取回执中的 `collaboration_id`、`revision` 和 `content_pack_id`，展示六项任务及阻塞原因。此时资料包只有候选事实，任务仍待办理。

### 3. 人工确认产品事实并生成

使用 `trade_product_content(action="get", pack_id=PACK_ID)` 展示候选事实、来源、几何示意图声明、图片署名与缺失商务条件。用户看过之后明确说：

> 我已核对这里展示的 DESK-001 模拟事实和示意图声明，确认采用这些候选事实，请生成资料包。图片只能标作模拟示意，不是真实照片。

然后才调用 `trade_confirm_product_facts(pack_id=PACK_ID, revision=PACK_REVISION, confirmed=true)`。采用全部候选时省略 `fact_indices`；选择部分候选时传回执中的从 1 开始的索引。使用确认回执的新修订号，再调用 `trade_product_content(action="generate", pack_id=PACK_ID, revision=NEW_PACK_REVISION, confirmed=true)`。

确认事实不等于生成成功。应查看实际返回的文案、FAQ、图片和下载项；翻译回退时如实说明其状态。几何图按现有图片模板排版，不生成真实产品照片。

资料包变化后，读取协同单，用当前协同单修订号调用 `trade_collaboration(action="refresh_sources", collaboration_id=COLLABORATION_ID, revision=COLLABORATION_REVISION)`。刷新来源不代表重新审核。

### 4. 按依赖逐项办理、逐项审核

每项任务都先展示实际依据和验收条件，再提交待审核。例如采购任务：

```text
trade_collaboration(
  action="update_task",
  collaboration_id=COLLABORATION_ID,
  revision=CURRENT_COLLABORATION_REVISION,
  task_id="procurement_quote",
  data={
    "status": "in_review",
    "result_note": "已核对当前 DESK-001 模拟报价、标准包装及不含运费的费用范围。",
    "unresolved_items": ["实际供货、库存、运费、税费及运输时效待确认"],
    "risks": ["模拟价格与生产周期不能作为真实供货承诺"]
  }
)
```

只有用户看过该任务当前产物、检查项和待确认事项，并明确确认后，才能执行：

```text
trade_collaboration(
  action="review",
  collaboration_id=COLLABORATION_ID,
  revision=LATEST_COLLABORATION_REVISION,
  task_id="procurement_quote",
  data={"confirmed": true, "review_note": "用户已核对当前模拟报价和费用范围，接受保留上述待确认事项用于内部交接。"}
)
```

负责人、结果依据、`in_review` 状态、有效来源和前置任务均须通过检查。不能把一句“帮我处理订单”理解为用户已经看过并批准所有结果，也不能循环自动批准六项任务。按任务表顺序分别办理业务、采购、美工、运营、合规和最终业务交接。

待确认事项可以在用户明确知悉后保留于内部交接稿，不要求删除未知项来获得完成状态。审核记录代表当前用户的内部检查，不伪称岗位标签对应的人亲自登录审批。

### 5. 下载与改单

全部六项任务有效完成后，`get` 回执的 `workflow_status.ready_for_handoff=true`。协同状态卡和工作台提供 Markdown、JSON 下载，导出内容包含版本依据、负责人、结果、审核意见、未确认事项与风险；没有发信或发布动作。

若把询盘改为 1000 件、定制包装，应重新计算：当前模拟目录的货值 USD 4800.00、包装费 USD 300.00、小计 USD 5100.00。旧协同依据和下游验收随之失效，不能继续下载旧交接稿。刷新来源后，受影响的已完成任务退回待审核，旧审核留在历史中；按新版报价重新办理。新增普通跟进待办不改变业务指纹，不会使整单误失效。

## 工具与 HTTP 契约

`trade_collaboration(action, collaboration_id="", revision=null, task_id="", data=null)` 支持：

| action | data | 其他参数 |
|---|---|---|
| `list` | 可选 `limit`，1–50，默认 20 | 无 |
| `get` | 不传 | `collaboration_id` |
| `create` | `title`、`inquiry_id`、可选 `content_pack_id`、`content_relationship`、`prepare_catalog_content`、`assignees` | 无 |
| `update_task` | 可选 `assignee_label`、`status`、`result_note`、`unresolved_items`、`risks`、`depends_on` | `collaboration_id`、最新 `revision`、`task_id` |
| `review` | `confirmed=true`、`review_note` | `collaboration_id`、最新 `revision`、`task_id` |
| `refresh_sources` | 不传 | `collaboration_id`、最新 `revision` |
| `link_content` | `content_pack_id`、`content_relationship` | `collaboration_id`、最新 `revision` |

工具的 `revision` 和 `task_id` 放在顶层，不能再放进 `data`。不接受模型提供的 `user_id`、`owner_user_id`、登录凭据或服务器路径。`link_content` 会重新验证来源权限与产品关系，并使受影响的验收失效。

认证 HTTP API 的应用前缀为 `/api/v1/foreign-trade/collaborations`：

| 方法与路径 | 用途 |
|---|---|
| `GET /`、`POST /` | 列表、创建 |
| `GET /{id}` | 当前详情与派生状态 |
| `PATCH /{id}` | 关联资料：`revision`、`content_pack_id`、`content_relationship` |
| `PATCH /{id}/tasks/{task_id}` | 更新任务，body 带 `revision` |
| `POST /{id}/review` | body 带 `revision`、`task_id`、`confirmed`、`review_note` |
| `POST /{id}/refresh-sources` | body 带 `revision` |
| `GET /{id}/handoff?revision=N&kind=md` | 下载 Markdown；`kind=json` 下载结构化交接稿 |

不存在或越权返回 404；修订冲突、来源过期、依赖阻塞或不可交接返回 409；无效字段、产品关联或缺少人工确认返回 422。下载固定使用请求版本的快照，并在返回前复查版本和审核状态；并发更新时旧链接返回 409，不替用户导出更新版本的审核结果。

## 实现位置与检查范围

- 业务服务：`src/backend/core/foreign_trade/collaboration.py`、`catalog_content.py`。
- 用户隔离与 CAS 存储：`foreign_trade_collaborations` 表，与询盘、资料包独立存储并保留引用。
- native 适配：`src/backend/core/llm/tools/foreign_trade_collaboration_tool.py`。
- 认证 API：`src/backend/api/routes/v1/foreign_trade_collaboration.py`。
- 离线服务与接口用例：`tests/test_foreign_trade_collaboration.py`，包括隔离、并发版本、依赖、人工审核、资料变化、Pi 关联限制与交接下载。

部署、依赖和更新步骤见 [TEAM_SETUP.md](TEAM_SETUP.md)；聊天入口见 [CHAT_PLUGIN.md](CHAT_PLUGIN.md)。实际 CI 和网页验收以相应验收记录为准，本说明描述使用契约，不作为现场验收证明。
