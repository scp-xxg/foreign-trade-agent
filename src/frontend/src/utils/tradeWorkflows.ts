import type { ComposerDraft } from '../stores/composerStore';

/** Add future chat workflows here so they share one menu and selection policy. */
export const TRADE_WORKFLOWS = [
  { id: 'acquisition', label: '获客', field: 'acquisitionMode' },
  { id: 'diligence', label: '客户背调', field: 'diligenceMode' },
  { id: 'communication', label: '客户沟通', field: 'communicationMode' },
  { id: 'negotiation', label: '谈单', field: 'negotiationMode' },
  { id: 'procurement', label: '采购', field: 'procurementMode' },
  { id: 'listing', label: '发品准备', field: 'listingMode' },
  { id: 'closing', label: '成交', field: 'closingMode' },
  { id: 'retrospective', label: '复盘', field: 'retrospectiveMode' },
] as const;

export function workflowSelection(draft: ComposerDraft, id: string): Partial<ComposerDraft> {
  const chosen = TRADE_WORKFLOWS.find(workflow => workflow.id === id);
  if (!chosen) return {};
  return { materialCheckMode: false, ...Object.fromEntries(TRADE_WORKFLOWS.map(workflow => [workflow.field,
    workflow.id === id && !draft[chosen.field]])) };
}
