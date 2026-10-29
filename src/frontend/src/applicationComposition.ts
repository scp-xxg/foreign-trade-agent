// Modified by foreign-trade-agent contributors, 2026-10-28; see CHANGES_FOREIGN_TRADE.md.
import './applicationWorkspaceActions';
import { PersonalAgentPanel } from './personalAgentEdition';
import { ConversationPage, ProjectListPage, type WorkspaceContext } from './applicationPages';
import { lazy, type ComponentType } from 'react';
import type { PanelKey } from './types';
import { LAYOUT_ITEMS } from './components/sidebar/items';
import { createWorkbenchRegistry } from './workbench/registry';

const AutomationPanel = lazy(() => import('./components/automation/AutomationPanel').then(m => ({ default: m.AutomationPanel })));
const AbilityCenterPage = lazy(() => import('./components/catalog/AbilityCenterPage').then(m => ({ default: m.AbilityCenterPage })));
const AppCenterPanel = lazy(() => import('./components/docs/AppCenterPanel'));
const DocsPanel = lazy(() => import('./components/docs/DocsPanel'));
const LabPanel = lazy(() => import('./components/lab/LabPanel'));
const MySpacePanel = lazy(() => import('./components/myspace/MySpacePanel').then(m => ({ default: m.MySpacePanel })));
const SettingsPage = lazy(() => import('./components/settings/SettingsModal'));
const SitesPanel = lazy(() => import('./components/sites/SitesPanel').then(m => ({ default: m.SitesPanel })));

const InquiryWorkspace = lazy(() => import('./components/foreign-trade/InquiryWorkspace').then(m => ({ default: m.InquiryWorkspace })));
const ProductContentWorkspace = lazy(() => import('./components/foreign-trade/ProductContentWorkspace').then(m => ({ default: m.ProductContentWorkspace })));
const CollaborationWorkspace = lazy(() => import('./components/foreign-trade/CollaborationWorkspace').then(m => ({ default: m.CollaborationWorkspace })));

const pages = {
  trade_inquiries: InquiryWorkspace,
  trade_content: ProductContentWorkspace,
  trade_collaboration: CollaborationWorkspace,
  chat: ConversationPage,
  personal_agent: PersonalAgentPanel,
  ability_center: AbilityCenterPage,
  app_center: AppCenterPanel,
  automation: AutomationPanel,
  docs: DocsPanel,
  sites: SitesPanel,
  lab: LabPanel,
  settings: SettingsPage,
  my_space: MySpacePanel,
  projects: ProjectListPage,
} satisfies Partial<Record<PanelKey, ComponentType<WorkspaceContext>>>;

// The trusted component map and navigation metadata meet here, outside the workbench.
export const builtinPages = createWorkbenchRegistry<WorkspaceContext>({
  components: pages,
  commands: {},
  applications: [
    { id: 'chat', target: { kind: 'builtin', componentId: 'chat' } },
    { id: 'personal_agent', target: { kind: 'builtin', componentId: 'personal_agent' } },
    { id: 'docs', target: { kind: 'builtin', componentId: 'docs' } },
    ...Object.entries(LAYOUT_ITEMS).map(([id, item]) => ({
      id, target: { kind: 'builtin' as const, componentId: item.targetPanel },
    })),
  ],
});
