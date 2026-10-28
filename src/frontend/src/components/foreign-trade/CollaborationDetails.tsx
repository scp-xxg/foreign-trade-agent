// Modified by foreign-trade-agent contributors, 2026-10-28; see CHANGES_FOREIGN_TRADE.md.
import { Button, Tag } from 'antd';
import { t } from '../../i18n';
import { navigateTo, pathForPanel } from '../../routing/navigation';
import type { CollaborationRecord, CollaborationRole, CollaborationTaskStatus } from '../../utils/foreignTradeCollaborationApi';
export const collaborationRoleLabel = (role: CollaborationRole) => ({ sales: t('销售'), procurement: t('采购'), design: t('设计'), operations: t('运营'), compliance: t('合规') })[role];
export const collaborationStatusLabel = (status: CollaborationTaskStatus) => ({ todo: t('待处理'), in_progress: t('处理中'), in_review: t('待人工验收'), done: t('已验收'), cancelled: t('已取消') })[status];
export function CollaborationDetails({ record, onEdit }: { record: CollaborationRecord; onEdit?: (id: string) => void }) {
  return <div className="jx-collaborationDetails">
    <p className="jx-collaborationScope">{t('当前账号下的角色协同；负责人为姓名标签，不代表独立账号权限。未发送通知或发布内容。')}</p>
    <p>{record.source_note}</p>
    {record.is_demo_transaction && <Tag color="orange">{t('模拟交易，非真实客户订单')}</Tag>}
    <div className="jx-collaborationSources">{record.source_refs.map(source => <article key={source.key}>
      <strong>{source.key === 'inquiry' ? t('询盘') : source.key === 'quote' ? t('报价') : t('产品资料包')}</strong>
      <span>{source.id} · {t('版本 {revision}', { revision: source.revision })}</span>
      <span>{source.relationship === 'independent_reference' ? t('独立参考，不属于交易产品') : t('本次交易来源')}</span>
      {source.key !== 'quote' && <Button size="small" onClick={() => navigateTo(pathForPanel(source.key === 'inquiry' ? 'trade_inquiries' : 'trade_content', source.id))}>{t('查看来源')}</Button>}
      {source.stale && <Tag color="warning">{t('来源已变化，需重新核对')}</Tag>}
    </article>)}</div>
    <div className="jx-collaborationTasks">{record.tasks.map(task => <article key={task.id} className={task.stale || task.blocked ? 'is-blocked' : ''}>
      <div className="jx-collaborationTaskHeading"><h4>{task.title}</h4><Tag color={task.status === 'done' ? 'success' : task.blocked || task.stale ? 'warning' : 'default'}>{collaborationStatusLabel(task.status)}</Tag></div>
      <p>{collaborationRoleLabel(task.role)} · {task.assignee_label || t('待指定负责人')}</p>
      <small>{t('依赖任务')}：{task.depends_on.map(id => record.tasks.find(item => item.id === id)?.title || id).join(' → ') || t('无')}</small>
      <h5>{t('验收标准')}</h5><ul>{task.acceptance_criteria.map((item, i) => <li key={i}>{item}</li>)}</ul>
      {task.result_note && <p className="jx-collaborationResult">{task.result_note}</p>}
      {(task.stale || task.blocked) && <p className="jx-collaborationWarning">{task.stale ? t('来源版本已变化，请重新核对并验收。') : t('依赖或来源条件尚未满足。')}{task.blockers.length > 0 && ' ' + task.blockers.join('；')}</p>}
      {task.unresolved_items.length > 0 && <div><strong>{t('未解决事项')}</strong><ul>{task.unresolved_items.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
      {task.risks.length > 0 && <div><strong>{t('风险提示')}</strong><ul>{task.risks.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
      {task.review && <p className="jx-collaborationReview">{t('验收记录')}：{task.review.note}<br /><small>{new Date(task.review.at).toLocaleString()} · {t('当前账号人工确认')}</small></p>}
      {onEdit && <Button size="small" onClick={() => onEdit(task.id)}>{t('编辑与验收')}</Button>}
    </article>)}</div>
  </div>;
}
