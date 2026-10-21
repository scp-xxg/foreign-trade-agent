# 场景一：买家公开资料、询盘处理与跟进

入口：登录后点击侧栏 **询盘工作台**。现有聊天中的产品查询、报价和下载继续可用。

## 具体案例与数据边界

内置“体验 Lyreco 公开资料示例”使用真实企业公开资料：

- 网站：https://www.lyreco.com/group/
- 公司介绍：https://www.lyreco.com/group/about/lyreco-international-footprint
- 示例法人检索名称：LYRECO，注册国 FR。
- 可核对的 GLEIF 记录：https://api.gleif.org/api/v1/lei-records/9695008VOHGGNWBV6W58

页面会实时读取来源、记录获取时间并显示官网自述和登记名称匹配的区别。登记匹配不证明网站或来信人与该法人的关系，LEI 登记状态不是资信评级。采购意愿与交易关系保持未核实；抓取失败不等于公司有风险。

**示例询盘由团队构造，不是 LYRECO 发来的邮件或订单，也不表示本项目与该企业有业务关系。** 示例产品 DESK-001、价格与交期仍来自模拟目录。没有捏造采购联系人或邮箱。

## 使用流程

1. 载入示例或新建询盘，填写买家和询盘原文后保存。
2. 点击“核验公开信息”，查看事实卡、来源、获取时间与未核实项。
3. 点击“提取询盘需求建议”。优先调用已配置的 main_agent；不可用时按基础关键词给出建议，并明确显示回退。建议附原文摘录，必须由用户确认并采用到表单，再保存。不会自动覆盖已确认条件。
4. 查询产品，确认 SKU、数量、标准/定制包装、交付目的国和可选的生产天数，再计算报价。
5. 点击报价卡下载中英文 PDF 或 Excel，点击生成中英文回复草稿。回复使用确定性模板保持金额与费用范围一致，供人工审阅和复制，不自动发送。
6. 填写跟进事项和带时区的到期时间，添加待办。可以完成、取消，或标记“客户已回复”来取消所有未完成待办；需要继续跟进时可恢复，但不会重新打开已经结束的旧待办。

工作台保存记录，刷新后仍可继续。当前跟进是站内待办管理，不含后台邮件、短信或系统推送通知。

## 验收路径

- 首次：500 件 DESK-001、标准包装、Spain，得到 USD 2400.00。
- 改单：1000 件、定制包装，得到货值 USD 4800.00 + 包装费 USD 300.00 = USD 5100.00。
- 修改条件后，旧报价不再作为当前下载结果，旧草稿标记过期；历史保留之前报价版本。
- 同一个买家资料、询盘原文、报价条件和跟进状态都属于当前账号，其他账号不能读取或更改。
- 每次写入校验 revision，其他页面已修改时返回冲突，避免覆盖。

## 实现与部署

新增 API：`/api/v1/foreign-trade`。询盘以 JSON 业务记录存入独立的 `foreign_trade_inquiries` 表，使用现有认证和用户隔离。公开团队的 SQLite 部署在启动时建立新表；本次未提供 PostgreSQL/Alembic 升级路径。

公开证据采集只允许标准 HTTP/HTTPS 公网地址，限制响应大小、重定向和超时，固定核验过的 IP 并保留 TLS 主机名校验。邮箱只作本地域名比较，不发送给 GLEIF 或其他第三方。网络页面视作资料，不执行其中指令。

团队更新后执行 setup，再重启自己的后端并刷新网页。导航会补入询盘工作台，已有账号和询盘数据保留。报价引擎通过正式 Python 包 foreign_trade 复用，setup 的 editable 安装会配置包路径。

## 检查

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_foreign_trade*.py' -v
.venv/bin/python -m pip install pytest pytest-asyncio
.venv/bin/python -m pytest tests/test_inquiry_workflow.py tests/test_inquiry_ai.py tests/test_buyer_public_data.py -q
npm --prefix src/frontend run test:foreign-trade-quote
```

自动测试使用隔离 SQLite 和模拟网络响应，不使用生产账号、真实模型密钥或付费接口。真实公开来源与网页流程由验收单独检查。
