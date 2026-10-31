import { useApplicationDirectory } from '../workbench/catalog';
export function useLocalPrivateKnowledge() {
  const directory = useApplicationDirectory();
  return directory.items.some(item => item.applicationKey === 'builtin:my_space'
    && item.availability.available && item.localPrivateKnowledgeOnly === true);
}
