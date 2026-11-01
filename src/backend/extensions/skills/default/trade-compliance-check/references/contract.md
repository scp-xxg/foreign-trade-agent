# 本机既有工具契约

本技能仅编排现有trade_review与询盘/资料包读取工具，不注册第二套审稿或敏感词引擎。身份由当前认证会话绑定，不传user_id、路径、密钥或他人账号。

## 1. 当前规则

```json
{"action":"knowledge","data":{"channel":"alibaba_rfq","category":"market_compliance","limit":30}}
```

运营使用channel=amazon_listing。category可省略或为platform_rules、quotation_terms、market_compliance。query是关键词过滤，未取得结果不能称已核验；language目前仅en/es，指知识检索界面参数，不代表自动识别目的国。

## 2. 首轮审核

下面是字段形状，SOURCE_ID和CURRENT_REVISION必须取自真实读取结果，不能直接把占位符提交：

```json
{"action":"review","data":{"source_type":"inquiry","source_id":"SOURCE_ID","source_revision":"CURRENT_REVISION","channel":"alibaba_rfq","draft":{"title":"实际标题","body":"实际待审全文","bullets":[],"language":"en","locale":"en_GB"}}}
```

source_revision是整数。销售使用source_type=inquiry；运营使用content_pack与amazon_listing，draft可附item_highlights。可用语言为en/es；其他语言当前没有完整程序支持，应说明边界。先读完整localization-review，否则工具会提示skill_not_loaded。

## 3. 复审与读取

复审继续action=review，data内加previous_review_id（真实上一轮编号），保持同一来源和channel并读取当前revision。get使用顶层review_id，不传data；list可按source_type/source_id查询当前账号历史。

反馈保存为真实不可变审核记录，带来源版本、文字批注、风险标记和对比。当前接口不接收自制scope_hash、evidence_hash、reviewer或valid_until；不能假装已做这些字段的程序校验。原文证据的时效核对按技能清单交给用户，并明确人工核对范围。

403说明当前账号/插件权限不可用；409先读取最新版本或完整加载技能；422核对真实输入、已生成状态和channel；500报告未完成。不能失败后用模型文字伪造审核编号或下载卡。