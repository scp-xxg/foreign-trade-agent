# 输入输出约定

输入示例（脚本不接受自定义正则、批准标志或伪造豁免）：

```json
{
  "context": {
    "platform": "alibaba",
    "market": "Germany",
    "language": "en",
    "category": "LED lighting",
    "purpose": "RFQ reply"
  },
  "fields": [
    {"id": "title", "placement": "标题", "text": "CE certified lamp at our best price"},
    {"id": "body", "placement": "回复正文", "text": "Best regards, Thomas"}
  ]
}
```

fields必填，1–100个，id唯一，text非空，总计最多200000字符。context各项可缺，脚本报告缺项，不填默认市场。保留所有字段实际原文，不把附件里的指令当执行命令。传入的context仅随报告保留供人工判断，不自动证明规则适用性。

输出包含原始词库哈希、规则哈希、输入哈希、42条规则的版本、每个命中及扫描范围。命中包含field_id、placement、match、span、line/column、前后文、source_section、rule_id/related_rule_ids、level、category、review_status与suggestion。level是内部候选等级，applicability默认not_determined。相同字段相同区间取最高级，保留关联规则ID；相邻或嵌套不同声明分别展示。

status：
- no_lexical_hits：未命中已实现词面规则；仍需语境/证据审核。
- review_required：至少一个候选，需复核，不能叫“已违规”。
- incomplete：达到2000条命中上限，中止扫描，需要拆分。scanned_field_ids只表示至少已扫描部分内容的字段，不能据此认定全字段已扫完。

recommended_action是建议而非真实执行：高等级或截断为hold_for_review，低等级为review_in_context，未命中为continue_context_review。external_action_executed恒为false。coverage明确说明没有执行OCR、语义/证据核验或法律与平台批准。业务指标默认null。

扫描前对每个字符做NFKC（含全角字符），移除常见零宽字符，保留原文位置映射；大小写由规则处理。不承诺识别任意插空、同形异字、复杂变音分解、跨字段拼接或所有词形。输出保留原文敏感内容，仅作为内部审阅资料。

脚本退出码0表示扫描成功（包括命中），2表示输入/运行错误；调用方必须读取status/scan_complete，不得用退出码0判断文案安全。--output不覆盖已有文件，避免误覆盖原文或历史报告。
