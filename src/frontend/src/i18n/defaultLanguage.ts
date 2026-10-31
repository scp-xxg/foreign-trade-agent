/** Respect explicit build language while keeping the upstream edition fallback. */
export type Lang = 'zh-CN' | 'en';
export function resolveLanguage(saved: unknown, configured: unknown, community: boolean): Lang {
  if (saved === 'en' || saved === 'zh-CN') return saved;
  if (configured === 'en' || configured === 'zh-CN') return configured;
  return community ? 'en' : 'zh-CN';
}
