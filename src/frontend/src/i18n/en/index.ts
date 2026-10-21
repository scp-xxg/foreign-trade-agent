// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
/** Community-edition English dictionaries only. */
import { CORE_DICT } from './core';
import { CHAT_DICT } from './chat';
import { HOOKS_DICT } from './hooks';
import { PANELS_DICT } from './panels';
import { TOOL_DICT } from './tool';
import { CATALOG_DICT } from './catalog';
import { SETTINGS_DICT } from './settings';
import { MYSPACE_DICT } from './myspace';
import { LAB_DICT } from './lab';
import { ADMIN_SKILLS_DICT } from './adminSkills';
import { STORES_DICT } from './stores';
import { APIDOC_DICT } from './apidoc';
import { AGENT_MARKET_DICT } from './agentMarket';
import { ONBOARDING_DICT } from './onboarding';
import { CE_SHARED_DICT } from './ceShared';
import { FOREIGN_TRADE_DICT } from './foreignTrade';
import { FOREIGN_TRADE_INQUIRY_DICT } from './foreignTradeInquiry';
import { FOREIGN_TRADE_CONTENT_DICT } from './foreignTradeContent';

export const EN_DICT: Record<string, string> = {
  ...CORE_DICT,
  ...CHAT_DICT,
  ...HOOKS_DICT,
  ...PANELS_DICT,
  ...TOOL_DICT,
  ...CATALOG_DICT,
  ...SETTINGS_DICT,
  ...MYSPACE_DICT,
  ...LAB_DICT,
  ...ADMIN_SKILLS_DICT,
  ...STORES_DICT,
  ...APIDOC_DICT,
  ...AGENT_MARKET_DICT,
  ...ONBOARDING_DICT,
  ...CE_SHARED_DICT,
  ...FOREIGN_TRADE_DICT,
  ...FOREIGN_TRADE_INQUIRY_DICT,
  ...FOREIGN_TRADE_CONTENT_DICT,
};
