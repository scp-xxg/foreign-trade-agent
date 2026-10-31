type Status = {generating?: boolean};
type Stats = {total_pages?: number};
export function watchWikiProgress(options: {
  status: () => Promise<Status>; stats: () => Promise<Stats>;
  onGenerating: (value:boolean)=>void; onPages:(value:number)=>void;
  schedule?: (tick:()=>void)=>()=>void;
}) {
  let active=true;
  const tick=()=>{
    void options.status().then(value=>{if(active && typeof value.generating==='boolean')options.onGenerating(value.generating);}).catch(()=>{});
    void options.stats().then(value=>{if(active && typeof value.total_pages==='number' && Number.isFinite(value.total_pages))options.onPages(value.total_pages);}).catch(()=>{});
  };
  const cancel=options.schedule ? options.schedule(tick) : (()=>{const timer=window.setInterval(tick,10000);return()=>window.clearInterval(timer);})();
  return ()=>{active=false;cancel();};
}
