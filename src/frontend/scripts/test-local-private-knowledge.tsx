import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import IndexModePicker from '../src/components/kb/IndexModePicker';
const base={onChange:()=>{},granularity:'focused' as const,onGranularityChange:()=>{},extractionInstructions:'',onExtractionInstructionsChange:()=>{},contentInstructions:'',onContentInstructionsChange:()=>{}};
const render=(value:('rag'|'wiki')[],unavailableModes:('rag'|'wiki')[])=>renderToStaticMarkup(<IndexModePicker {...base} value={value} unavailableModes={unavailableModes}/>);
const buttons=(html:string)=>html.match(/<button[^>]*role="checkbox"[^>]*>/g)||[];
const wiki=buttons(render(['wiki'],['rag']));
assert.equal(wiki.length,2);assert.match(wiki[0],/disabled/);assert.match(wiki[0],/aria-checked="false"/);
assert.doesNotMatch(wiki[1],/disabled/);assert.match(wiki[1],/aria-checked="true"/);
// A previously selected mode whose service disappeared remains removable.
const existing=buttons(render(['rag','wiki'],['rag']));assert.doesNotMatch(existing[0],/disabled/);
const rag=buttons(render(['rag'],[]));assert.match(rag[0],/aria-checked="true"/);assert.doesNotMatch(rag[0],/disabled/);
assert.match(render(['wiki'],['rag']),/Wiki/);
console.log('Local knowledge mode availability and existing-mode controls passed');

const unavailable=buttons(render([],['rag','wiki']));assert.ok(unavailable.every(tag=>tag.includes('disabled')&&tag.includes('aria-checked="false"')));

// The first upload starts after an initially idle capability response.
const {watchWikiProgress}=await import('../src/utils/wikiProgressPoll');
let tick:()=>void=()=>{};let cancelled=false;let phase=false;let pageCount=0;const phases:boolean[]=[];const counts:number[]=[];
let resolveLate:(v:{total_pages:number})=>void=()=>{};let late=false;
const dispose=watchWikiProgress({status:async()=>({generating:phase}),stats:()=>late?new Promise(resolve=>{resolveLate=resolve;}):Promise.resolve({total_pages:pageCount}),
 onGenerating:value=>phases.push(value),onPages:value=>counts.push(value),schedule:fn=>{tick=fn;return()=>{cancelled=true;};}});
tick();await Promise.resolve();phase=true;tick();await Promise.resolve();phase=false;pageCount=6;tick();await Promise.resolve();
assert.deepEqual(phases,[false,true,false]);assert.deepEqual(counts,[0,0,6]);
late=true;tick();await Promise.resolve();dispose();const previous=counts.length;resolveLate({total_pages:99});await Promise.resolve();
assert.equal(counts.length,previous);assert.equal(cancelled,true);
console.log('Wiki progress follows idle → generating → complete and ignores stale reads');
