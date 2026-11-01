import type { ToolCall } from '../types';
export interface CheckField { id: string; text: string; placement?: string }
export interface WordHit { rule_id: string; field_id: string; level: string; match: string; span: [number,number]; reason: string; suggestion: string }
export interface CheckRow { check_id: string; title: string; status: string; evidence_request: string; issues: string[] }
export interface MaterialReceipt {
  document_type: 'trade_material_check'; document_version: 1; check_id: string; action: 'sensitive'|'compliance';
  fields: CheckField[]; notices: string[];
  sensitive: { status: string; scan_complete: boolean; hits: WordHit[]; rule_version: string; input_sha256: string } | null;
  compliance: { status: string; checks: CheckRow[]; coverage_gaps: string[]; pack_version: string; as_of: string; input_hash: string } | null;
  release_authorized: false; external_action_executed: false;
}
const object=(v: unknown): v is Record<string,unknown> => !!v && typeof v==='object' && !Array.isArray(v);
const str=(v: unknown): v is string => typeof v==='string' && v.length<=200000;
const strings=(v: unknown): v is string[] => Array.isArray(v) && v.length<=1000 && v.every(str);
export function parseMaterialReceipt(v: unknown): MaterialReceipt|null {
  if(!object(v) || v.document_type!=='trade_material_check' || v.document_version!==1 || !str(v.check_id) || !/^check_[a-f0-9]{32}$/.test(v.check_id) || !['sensitive','compliance'].includes(String(v.action)) || v.release_authorized!==false || v.external_action_executed!==false || !strings(v.notices)) return null;
  if(!Array.isArray(v.fields) || v.fields.length>100) return null;
  const fields=new Map<string,string>();let length=0;
  for(const f of v.fields) {
    if(!object(f) || !str(f.id) || !str(f.text) || !f.id || fields.has(f.id) || (f.placement!==undefined && !str(f.placement)))return null;
    fields.set(f.id,f.text);length+=f.text.length;
  }
  if(length>400000)return null;
  const s=v.sensitive;
  if(s!==null) {
    if(!object(s) || !str(s.rule_version) || !str(s.input_sha256) || !['no_lexical_hits','review_required','incomplete'].includes(String(s.status)) || typeof s.scan_complete!=='boolean' || !Array.isArray(s.hits) || s.hits.length>2000)return null;
    for(const h of s.hits) {
      if(!object(h) || !str(h.rule_id) || !str(h.field_id) || !fields.has(h.field_id) || !['L1','L2','L3','L4'].includes(String(h.level)) || !str(h.match) || !str(h.reason) || !str(h.suggestion) || !Array.isArray(h.span) || h.span.length!==2 || !h.span.every(n=>Number.isSafeInteger(n) && n>=0))return null;
      const chars=Array.from(fields.get(h.field_id)!);const [a,b]=h.span as number[];
      if(a>=b || b>chars.length || chars.slice(a,b).join('')!==h.match)return null;
    }
    if((s.status==='no_lexical_hits' && s.hits.length) || (s.status==='incomplete' && s.scan_complete))return null;
  }
  const c=v.compliance;
  if(c!==null) {
    if(!object(c) || !['needs_review','scoped_checklist_reviewed'].includes(String(c.status)) || !str(c.pack_version) || !str(c.as_of) || !Number.isFinite(Date.parse(c.as_of)) || !str(c.input_hash) || !strings(c.coverage_gaps) || !Array.isArray(c.checks) || c.checks.length>1000 || c.release_authorized!==false || c.legal_compliance!=='not_determined')return null;
    for(const row of c.checks)if(!object(row) || !str(row.check_id) || !str(row.title) || !str(row.status) || !str(row.evidence_request) || !strings(row.issues))return null;
  }
  if((v.action==='compliance')!==(c!==null))return null;
  return v as unknown as MaterialReceipt;
}
function unwrap(v: unknown,depth=0): MaterialReceipt[] {
  if(depth>6)return [];
  if(typeof v==='string'){if(v.length>3000000)return [];try{return unwrap(JSON.parse(v),depth+1);}catch{return [];}}
  if(Array.isArray(v))return v.length>50?[]:v.flatMap(x=>unwrap(x,depth+1));
  if(!object(v) || v.ok===false || v.isError===true || ('errors' in v && (!Array.isArray(v.errors) || v.errors.length>0)))return [];
  const receipt=parseMaterialReceipt(v);if(receipt)return [receipt];
  if(v.ok===true && 'data' in v)return unwrap(v.data,depth+1);
  for(const key of ['structuredContent','content','output','result'])if(key in v){const found=unwrap(v[key],depth+1);if(found.length)return found;}
  return v.type==='text'?unwrap(v.text,depth+1):[];
}
export function extractMaterialChecks(tools: ToolCall[]): MaterialReceipt[] {
  const records=new Map<string,MaterialReceipt>();
  for(const tool of tools)if(tool.name==='trade_material_check' && tool.status==='success' && (!tool.outputTruncated || tool.outputLoaded))for(const r of unwrap(tool.output))records.set(r.check_id,r);
  return [...records.values()];
}
export function markedSegments(field: CheckField,hits: WordHit[]) {
  const chars=Array.from(field.text);const related=hits.filter(h=>h.field_id===field.id);const bounds=[...new Set([0,chars.length,...related.flatMap(h=>h.span)])].sort((a,b)=>a-b);
  return bounds.slice(0,-1).map((start,i)=>({start,text:chars.slice(start,bounds[i+1]).join(''),hits:related.filter(h=>h.span[0]<=start && h.span[1]>=bounds[i+1])}));
}
export const checkRowState=(r: CheckRow): 'done'|'missing'|'review'|'issue' => ['reviewed_with_supplied_evidence','not_applicable_per_supplied_review'].includes(r.status)?'done':r.status==='evidence_required'?'missing':r.status==='issue_reported'?'issue':'review';
