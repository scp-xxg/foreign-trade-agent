# 参与贡献

感谢关注 SailAgent。参与本项目即表示同意遵守中英双语的[社区行为准则](CODE_OF_CONDUCT.md)，请以尊重、友善和建设性的方式交流。

本仓库是 HugAgentOS 社区版的衍生项目，目录分工如下：

- `src/backend`、`src/frontend`：上游框架代码。改动前请先确认是否属于上游通用能力；属于上游问题的，建议附复现步骤向上游反馈。
- `extensions/foreign_trade`：SailAgent 的业务层，新增外贸流程、技能、原生工具与审核规则请放在这里。
- `docs/`、`README.md`：文档，欢迎直接提 PR。

## 提交前自查

```bash
python -m pytest tests -q                      # 业务回归（离线）
npm --prefix src/frontend run build            # 前端构建
.venv/bin/python extensions/foreign_trade/team.py check
```

改动涉及报价、版本、权限或导出时，请补充或更新 `tests/` 下的用例，并在 PR 描述中写清影响范围。

## 提 Issue

- Bug：请附复现步骤、期望行为、实际行为、环境信息（OS / Docker / Python 版本）与相关日志片段。日志中不要包含账号、密钥或客户资料。
- 功能建议：请说明使用场景、当前替代做法与预期收益。

## 安全问题

请勿公开披露安全漏洞，参见 [SECURITY.md](SECURITY.md)。
