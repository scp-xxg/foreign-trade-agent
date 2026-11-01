import { PartitionOutlined } from '@ant-design/icons';
import { TRADE_WORKFLOWS, workflowSelection } from '../../utils/tradeWorkflows';
import { useComposerDraft } from '../../stores/composerStore';
import { t } from '../../i18n';

export function AcquisitionShortcut({ draftKey }: { draftKey?: string }) {
  const draft = useComposerDraft(draftKey);
  const active = TRADE_WORKFLOWS.find(workflow => draft[workflow.field]);
  if (draft.materialCheckMode) return <button type="button" role="switch" aria-checked={true} className="jx-composerChip active" aria-label={t('检查资料')} onClick={() => draft.patch({materialCheckMode:false})}>{t('检查资料')} · {t('已开启')} ×</button>;
  if (!active) return null;
  return <button type="button" role="switch" aria-checked={true}
    className="jx-composerChip active" aria-label={t(active.label)}
    onClick={() => draft.patch(workflowSelection(draft, active.id))}>
    <PartitionOutlined aria-hidden="true" /><span>{t(active.label)} · {t('已开启')} ×</span>
  </button>;
}

export function AcquisitionGuide({ draftKey }: { draftKey: string }) {
  const draft = useComposerDraft(draftKey);
  if (draft.materialCheckMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('资料检查：敏感词标注与合规清单')}</summary>
    <p>{t('粘贴文字或上传文件。可补充目标市场、产品用途和平台；缺少信息时先检查文字，再提示补充。')}</p>
    <p>{t('结果显示原文标注和合规卡片。图片需先提取文字，未识别内容会明确提示。')}</p>
  </details>;
  if (draft.procurementMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('采购已开启：需求拆解 → 供应商寻源 → 能力评估 → 成本比选 → 质量策划 → 交期跟踪 → 验收结算')}</summary>
    <p>{t('请提供：产品规格与版本、数量与单位、需求日期与交付地；已有供应商、报价、库存、质量标准、采购订单和验收付款记录可分阶段补充。')}</p>
    <p>{t('将交付：采购需求与询价草稿、候选及能力证据、成本对比、质量清单、交期风险和结算差异。缺资料暂停对应阶段，审批后推进；下单、发送及付款需另行确认。')}</p>
  </details>;
  if (draft.listingMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('发品准备已开启：资料标准化 → 类目属性 → 关键词 → 商品内容 → 图片适配 → 发布前检查')}</summary>
    <p>{t('请提供：产品资料和图片、目标平台、站点、语言，以及有版本和有效期的平台规则。')}</p>
    <p>{t('将交付：产品档案、类目属性、关键词方案、标题描述、适配图片和检查报告。缺资料会暂停对应步骤；审核后继续，当前不会发布商品。')}</p>
  </details>;
  if (draft.closingMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('成交已开启：准备检查 → 条款核对 → 制单 → 签署下单 → 收款核验 → 订单交接')}</summary>
    <p>{t('请提供：订单与截至时间、企业成交规则、PO与报价版本、规格及往来、批准模板、签署记录和付款证据。')}</p>
    <p>{t('将交付：阻塞清单、条款差异、PI或合同草稿、手续进度、收款对照与交接包。水单不等于到账，执行与文件均需审核。')}</p>
  </details>;
  if (draft.retrospectiveMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('复盘已开启：过程还原 → 漏斗分析 → 原因分析 → 改进行动 → 经验沉淀')}</summary>
    <p>{t('请提供：复盘对象与周期、目标、客户往来、报价及订单记录。周期分析还需阶段口径、观察期和统计截至时间。')}</p>
    <p>{t('将交付：证据时间线、转化与瓶颈、赢丢原因及假设、改进任务草案和待审案例。单商机可跳过漏斗，未知数据不补造，知识入库需审核。')}</p>
  </details>;
  if (draft.negotiationMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('谈单已开启：诊断 → 报价 → 异议与条件交换 → 样品试单 → 条款与纪要')}</summary>
    <p>{t('请提供：客户往来、采购需求、报价版本、成本及币种、利润底线、让步权限和样品政策。')}</p>
    <p>{t('将交付：商机卡点、谈判策略、内部让步测算、样品计划和待审回复。缺少成本或授权先确认，商业承诺由你审核。')}</p>
  </details>;
  if (draft.communicationMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('客户沟通已开启：触达 → 分流 → 澄清 → 答复 → 跟进 → 纪要')}</summary>
    <p>{t('请提供：客户与渠道、沟通目标、往来原文、已确认产品及供货资料、实际发送记录与买家时区。')}</p>
    <p>{t('将交付：意图判断、需求问题、有据答复草稿、跟进建议及沟通纪要。按情境调用技能，退订停止触达，消息经你审核后发送。')}</p>
  </details>;
  if (draft.diligenceMode) return <details className="jx-acquisitionGuide" open>
    <summary>{t('客户背调已开启：企业身份 → 业务匹配 → 联系人核验 → 交易风险')}</summary>
    <p>{t('请提供：企业名称、官网或登记号、注册国家、我方产品与供货能力、已有联系人及证据；交易评估可补充金额、币种、付款条件、合同与收款主体。')}</p>
    <p>{t('将交付：企业身份、业务匹配、联系人与决策链、风险与合作建议，以及证据来源和待核实项。未查询不代表无风险；主体冲突须人工确认，不自动联系客户。')}</p>
  </details>;
  if (!draft.acquisitionMode) return null;
  return <details className="jx-acquisitionGuide" open>
    <summary>{t('获客已开启：画像 → 搜索 → 背调 → 联系人 → 排序 → 开发信')}</summary>
    <p>{t('请提供：产品及用途、目标市场、买家类型、MOQ、价格区间、交期、认证与定制能力。可补充期望数量、排除名单、预算及产品目录。')}</p>
    <p>{t('将交付：客户画像、去重买家清单、背调证据与风险、审核后买家的公开联系渠道、优先级与开发信草稿、执行统计与待核实事项。背调后需你审核；资料不足会先追问。')}</p>
  </details>;
}
