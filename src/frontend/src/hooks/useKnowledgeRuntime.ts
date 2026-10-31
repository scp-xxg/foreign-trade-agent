import { useEffect, useState } from 'react';
import { apiRequest } from '../api';
import { useAuthStore } from '../stores/authStore';
import type { KBIndexMode } from '../types';
export interface KnowledgeRuntime {
  local_private_only: boolean;
  embedding_configured: boolean;
  wiki_configured: boolean;
  default_index_modes: KBIndexMode[];
}
export function useKnowledgeRuntime() {
  const owner = useAuthStore(state => state.authUser?.user_id);
  const [state, setState] = useState<{owner?:string; value:KnowledgeRuntime|null}>({value:null});
  useEffect(() => {
    const controller = new AbortController();
    const reload = () => { if (owner) void apiRequest<{data:KnowledgeRuntime}>('/v1/catalog/kb/runtime', {signal:controller.signal})
      .then(result => {if(!controller.signal.aborted)setState({owner,value:result.data});})
      .catch(() => {if(!controller.signal.aborted)setState({owner,value:null});}); };
    reload(); window.addEventListener('focus',reload);
    return () => {controller.abort();window.removeEventListener('focus',reload);};
  }, [owner]);
  return state.owner === owner ? state.value : null;
}
