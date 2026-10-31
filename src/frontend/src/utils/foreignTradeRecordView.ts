/** Guards for owner-scoped workspace records and asynchronous read responses. */
export interface RecordRevision { id: string; revision: number }
export function canReplaceRecord(incoming: RecordRevision, current: RecordRevision | null): boolean {
  return !!incoming.id && Number.isSafeInteger(incoming.revision) && incoming.revision > 0 &&
    (!current || current.id !== incoming.id || incoming.revision >= current.revision);
}
export function canApplyRecordRead(request: number, activeRequest: number, dirty: boolean,
  incoming: RecordRevision, current: RecordRevision | null, requestedId?: string): boolean {
  return request === activeRequest && !dirty && (!requestedId || incoming.id === requestedId) && canReplaceRecord(incoming, current);
}
export function shouldPreserveRecordDraft(currentPath: string, nextPath: string, dirty: boolean, busy: string): boolean {
  return currentPath !== nextPath && (dirty || !!busy && busy !== 'loading');
}
