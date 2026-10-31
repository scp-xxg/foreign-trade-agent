# 智能体上架审核

团队成员先在能力中心创建并测试个人智能体，再点击“申请上架”。申请状态为 `pending` 时，其他成员不会在智能体市场看到它。

管理员接口使用现有 `ADMIN_TOKEN`：

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://127.0.0.1:3001/v1/admin/agent-marketplace/submissions?status=pending
```

查看申请详情：

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://127.0.0.1:3001/v1/admin/agent-marketplace/submissions/SUBMISSION_ID
```

通过申请并上架：

```bash
curl -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"approve":true,"review_note":"已验证报价工具和输出边界","category":"外贸业务"}' \
  http://127.0.0.1:3001/v1/admin/agent-marketplace/submissions/SUBMISSION_ID/review
```

驳回申请：

```bash
curl -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"approve":false,"review_note":"请补充价格来源和人工确认规则"}' \
  http://127.0.0.1:3001/v1/admin/agent-marketplace/submissions/SUBMISSION_ID/review
```

审核通过后，智能体会出现在所有已登录成员的智能体市场中。成员安装后获得自己的私有副本；审核通过的版本不会跟随提交者后续修改自动变化。
