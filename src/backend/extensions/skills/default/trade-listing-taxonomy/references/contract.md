# 发品准备原生工具契约

调用 `trade_listing_prepare(action="taxonomy", data={...}, file_ids=null)`。身份由当前会话绑定，不传user_id、路径、URL或账号密钥。

先读[完整JSON Schema](schema.json)。必填data：batch_id、as_of（带时区ISO）、platform、site、language。products每项sku/product_id/version/facts；facts每项field/value/confirmed/evidence，证据{source_id,excerpt}为sources[{id,reference,text}]原文子串且value必须出现在excerpt。常用字段name/model/material/capacity/weight/moq/delivery/currency/price/price_unit/packaging/certification；来源标注不证明真实性。SKU唯一，多来源事实保留多条。

rules包含平台类目属性枚举、图片及文字限制、required_fields、版本与有效期，字段均见Schema。没有rules允许做资料草稿，不能通过检查。提供规则只表示调用方输入，工具不访问平台验证。

selections选择类目并confirmed；keywords包含term/intent/fact_fields/origin/confirmed及可选真实报告搜索量；drafts包含sku/title/description/fact_fields/reviewed。media使用当前聊天附件file_id、sku、role=main|detail|dimensions|packaging|scene及人工确认信息。normalize顶层file_ids最多10个，其他步骤不允许file_ids。

media返回真实输出附件链接，后续检查须使用output_file_id。preflight初次返回media.sha256和review_scope_hash；审核后写media.reviewed_sha256等确认，再取新的review_scope_hash，最后填写reviews[{sku,check,state,evidence,scope_hash}]。reviews不参与scope_hash，as_of也不参与；其余参数变化使旧审核失效。预检会单独判断规则和资料过期以及实际图片变化。

## 最小调用

```json
{"action":"taxonomy","data":{"batch_id":"B1","as_of":"2026-10-31T12:00:00+08:00","platform":"用户指定平台","site":"US","language":"en","sources":[{"id":"spec","reference":"规格表A2","text":"Bottle"}],"products":[{"sku":"A1","product_id":"P1","version":"v1","facts":[{"field":"name","value":"Bottle","confirmed":false,"evidence":[{"source_id":"spec","excerpt":"Bottle"}]}]}]}}
```

返回逐SKU状态、问题、来源/版本、输入哈希及平台规则版本。published恒false，指标未采样为null。原生工具处理确定性转换；语义类目、词义、文案真实性、图片外观及法规需依照技能人工复核。当前未集成OCR、独立规则抓取、视觉型号识别、AI图片生成、自动发布与效果统计。错误权限会终止调用；坏图按SKU报告失败。
