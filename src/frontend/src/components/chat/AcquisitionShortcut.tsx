import { PartitionOutlined } from '@ant-design/icons';
import { useComposerDraft } from '../../stores/composerStore';
import { t } from '../../i18n';

export function AcquisitionShortcut({ draftKey }: { draftKey?: string }) {
  const draft = useComposerDraft(draftKey);
  return <><button type="button" role="switch" aria-checked={draft.acquisitionMode}
    className={`jx-composerChip${draft.acquisitionMode ? ' active' : ''}`}
    aria-label={t('获客')} title={t('开启后按顺序使用六个获客技能')}
    onClick={() => draft.patch({ acquisitionMode: !draft.acquisitionMode, followupMode: false })}>
    <PartitionOutlined aria-hidden="true" /><span>{t('获客')} · {draft.acquisitionMode ? t('已开启') : t('已关闭')}</span>
  </button><button type="button" role="switch" aria-checked={draft.followupMode}
    className={`jx-composerChip${draft.followupMode ? ' active' : ''}`}
    aria-label={t('客户跟进')} title={t('开启联系人、评分、跟进规划与回复分流工作流')}
    onClick={() => draft.patch({ followupMode: !draft.followupMode, acquisitionMode: false })}>
    <PartitionOutlined aria-hidden="true" /><span>{t('客户跟进')} · {draft.followupMode ? t('已开启') : t('已关闭')}</span>
  </button></>;
}

export function AcquisitionGuide({ draftKey }: { draftKey: string }) {
  const draft = useComposerDraft(draftKey);
  if (draft.followupMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('客户跟进已开启：联系人 → 评分 → 跟进计划 → 回复分流')}</summary>
    <p>{t('请提供：已审核买家与官网、四维匹配证据、联系用途、买家时区、实际发送记录、退信状态；有回复时提供原文、来源和接收时间。')}</p>
    <p>{t('将交付：公开渠道、优先级、跟进时间与目的、回复意图证据和下一步。任何回复暂停旧计划，退订或明确拒绝停止；仅生成建议，不自动发送或定时执行。')}</p>
  </details>;
  if (!draft.acquisitionMode) return null;
  return <details className="jx-acquisitionGuide" open>
    <summary>{t('获客已开启：画像 → 搜索 → 背调 → 联系人 → 排序 → 开发信')}</summary>
    <p>{t('请提供：产品及用途、目标市场、买家类型、MOQ、价格区间、交期、认证与定制能力。可补充期望数量、排除名单、预算及产品目录。')}</p>
    <p>{t('将交付：客户画像、去重买家清单、背调证据与风险、审核后买家的公开联系渠道、优先级与开发信草稿、执行统计与待核实事项。背调后需你审核；资料不足会先追问。')}</p>
  </details>;
}
