import type { TradeQuote } from './foreignTradeQuote';
import * as XLSX from 'xlsx';

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
const USD = (s: string) => `USD ${Number(s).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const zhWarnings: Record<string, string> = {
  SIMULATED_DATA: '产品、规格、价格和生产周期均为虚构演示数据。',
  DESTINATION_REQUIRED: '目的国未提供，运费与交付条件待确认。',
  FREIGHT_UNCONFIRMED: '运费待确认，不等于零；本小计不含运费。',
  TAXES_DUTIES_UNCONFIRMED: '进口税费与关税未核定，不计入小计。',
  REQUESTED_LEAD_TOO_SHORT: '要求交期短于参考生产周期，无法承诺满足该交期。',
  DELIVERY_DATE_UNCONFIRMED: '参考生产周期可落在要求天数内；运输与实际交付仍待确认。',
};
export const quoteFilename = (quote: TradeQuote, extension: 'pdf' | 'xlsx') => `${quote.quoteId}-ZH-EN.${extension}`;

// The workbook is a fixed, tool-calculated quotation snapshot, not a second pricing engine.
export function buildTradeQuoteWorkbook(quote: TradeQuote): XLSX.WorkBook {
  const wb = XLSX.utils.book_new();
  const d = quote.data;
  for (const zh of [true, false]) {
    const rows: (string | number | null)[][] = [
      [zh ? '报价单 | HugAgentOS 外贸助手' : 'QUOTATION | HugAgentOS Trade Assistant'],
      [zh ? 'DEMO / 模拟数据，非真实商业报价' : 'DEMO / Simulated data. Not a binding commercial offer.'],
      [(zh ? '报价编号：' : 'Quote reference: ') + quote.quoteId],
      [(zh ? '目的国：' : 'Destination: ') + (d.destination_country || (zh ? '待确认' : 'Pending confirmation'))],
      [zh ? '币种：USD。合计仅含货值及已计包装费，不含运费、税费、关税和其他未核定费用。' : 'Currency: USD. Subtotal covers goods and packaging only; freight, taxes, duties and unconfirmed costs are excluded.'],
      [],
      zh ? ['SKU', '产品', '数量（件）', '包装', '货品单价 USD', '每件包装费 USD', '货值 USD', '包装费 USD', '小计 USD', '参考生产天数']
         : ['SKU', 'Product', 'Qty (pcs)', 'Packaging', 'Goods unit USD', 'Pack / unit USD', 'Goods USD', 'Packaging USD', 'Subtotal USD', 'Production days'],
      ...d.items.map(line => [line.sku, zh ? line.name_zh : line.name, line.quantity,
        line.custom_packaging ? (zh ? '定制包装' : 'Custom') : (zh ? '标准包装' : 'Standard'),
        Number(line.unit_price), Number(line.packaging_unit_surcharge), Number(line.merchandise_subtotal),
        Number(line.packaging_subtotal), Number(line.line_subtotal), line.production_lead_days]),
      [zh ? '不含运费及税费合计' : 'Subtotal excl. freight/taxes', null, null, null, null, null,
        Number(d.merchandise_subtotal), Number(d.packaging_subtotal), Number(d.subtotal)],
      [],
      [(zh ? '参考生产周期：' : 'Indicative production lead time: ') + d.production_lead_days + (zh ? ' 天，需确认；不含运输时间。' : ' days, subject to confirmation; shipping time excluded.')],
      [(zh ? '客户要求生产天数：' : 'Requested production days: ') + (d.requested_lead_days ?? (zh ? '未指定' : 'Not specified'))],
      [zh ? '待确认：运费、运输方式、贸易术语、税费、保险、付款条件和报价有效期。' : 'Pending: freight, shipping method, Incoterms, taxes, insurance, payment terms and quotation validity.'],
      [zh ? '说明：标准包装已含在货品价格中；定制包装按单列费用收取，不重复计价。' : 'Standard packaging is included in goods prices. Custom packaging is itemized separately and is not counted twice.'],
      ...quote.snapshot.warnings.map(w => [(zh ? (zhWarnings[w.code] || w.message) : w.message)]),
      [(zh ? '目录版本：' : 'Catalog version: ') + quote.snapshot.catalog_version],
      ...quote.snapshot.source.record_refs.map(ref => [(zh ? '来源记录：' : 'Source record: ') + ref]),
      [zh ? '此文件是计算结果快照。修改数量或包装后，请在助手中重新计算并下载新报价单。' : 'This file is a calculated snapshot. Recalculate in the assistant and download a new quotation after changing quantity or packaging.'],
      ['Powered by HugAgentOS | Open-source framework'],
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    const totalRow = 7 + d.items.length;
    ws['!cols'] = [16, 39, 14, 18, 21, 22, 21, 22, 22, 23].map(wch => ({ wch }));
    ws['!rows'] = rows.map((_, i) => ({ hpt: i === 0 ? 30 : i === 6 ? 30 : 24 }));
    const merged = rows.flatMap((row, r) => row.length === 1 ? [{ s: { r, c: 0 }, e: { r, c: 9 } }] : []);
    merged.push({ s: { r: totalRow, c: 0 }, e: { r: totalRow, c: 5 } });
    ws['!merges'] = merged;
    ws['!autofilter'] = { ref: `A7:J${7 + d.items.length}` };
    for (let r = 7; r <= totalRow; r++) {
      for (let c = 4; c <= 8; c++) {
        const cell = ws[XLSX.utils.encode_cell({ r, c })];
        if (cell?.t === 'n') cell.z = '"USD "#,##0.00';
      }
    }
    // aoa_to_sheet writes user-controlled strings as t:s, never as formulas.
    XLSX.utils.book_append_sheet(wb, ws, zh ? '中文报价单' : 'English Quotation');
  }
  wb.Props = { Title: `${quote.quoteId} - Bilingual Demo Quotation`, Author: 'HugAgentOS Trade Assistant', Subject: 'Tool-calculated simulated quotation' };
  return wb;
}

export function buildTradeQuoteHtml(quote: TradeQuote): string {
  const d = quote.data;
  const pages = [];
  for (let offset = 0; offset < d.items.length; offset += 4) {
    const last = offset + 4 >= d.items.length;
    const items = d.items.slice(offset, offset + 4);
    pages.push(`<section class="trade-pdf-page" style="${offset ? 'break-before:page;page-break-before:always;' : ''}">
      <header><b>HugAgentOS · 外贸助手 / Trade Assistant</b><span>DEMO · 模拟报价</span></header>
      <h1>报价单 <small>/ QUOTATION</small></h1>
      <div class="trade-meta"><div><b>报价编号 / Reference</b><br>${esc(quote.quoteId)}</div><div><b>目的国 / Destination</b><br>${esc(d.destination_country || '待确认 / Pending confirmation')}</div><div><b>币种 / Currency</b><br>USD</div></div>
      <table><colgroup><col style="width:25%"><col style="width:7%"><col style="width:12%"><col style="width:12%"><col style="width:14%"><col style="width:14%"><col style="width:16%"></colgroup>
      <thead><tr><th>产品 / Product</th><th>数量<br>Qty</th><th>货品单价<br>Goods / unit</th><th>每件包装费<br>Pack / unit</th><th>货值<br>Goods amount</th><th>包装费<br>Packaging</th><th>行小计<br>Line subtotal</th></tr></thead>
      <tbody>${items.map(line => `<tr><td><b>${esc(line.sku)} · ${esc(line.name_zh)}</b><br>${esc(line.name)}<br><small>${line.custom_packaging ? '定制包装 / Custom packaging' : '标准包装 / Standard packaging'} · ${line.production_lead_days} 天 / days</small></td><td>${line.quantity}</td>${[line.unit_price,line.packaging_unit_surcharge,line.merchandise_subtotal,line.packaging_subtotal,line.line_subtotal].map(v => `<td>${esc(USD(v))}</td>`).join('')}</tr>`).join('')}</tbody></table>
      ${last ? `<div class="trade-total"><div>货值 / Goods: ${esc(USD(d.merchandise_subtotal))}<br>包装费 / Packaging: ${esc(USD(d.packaging_subtotal))}</div><div><small>不含运费及税费小计 / Subtotal excl. freight &amp; taxes</small><strong>${esc(USD(d.subtotal))}</strong></div></div>
      <div class="trade-terms"><b>报价条件 / Terms &amp; scope</b><p>参考生产周期 ${d.production_lead_days} 天，需确认；不含运输时间。客户要求生产天数：${d.requested_lead_days ?? '未指定'}。<br>Indicative production lead time: ${d.production_lead_days} days, subject to confirmation; shipping excluded. Requested production days: ${d.requested_lead_days ?? 'not specified'}.</p><p>标准包装已含在货品价格中；定制包装单独列示。运费、税费、关税、保险、贸易术语、付款条件与报价有效期待确认。<br>Standard packaging is included; custom packaging is itemized. Freight, taxes, duties, insurance, Incoterms, payment terms and validity remain unconfirmed.</p></div>
      <div class="trade-notices">${quote.snapshot.warnings.map(w => `<p><b>${esc(zhWarnings[w.code] || w.code)}</b> / ${esc(w.message)}</p>`).join('')}</div>
      <footer><b>目录 / Catalog:</b> ${esc(quote.snapshot.catalog_version)}<br><b>来源 / Sources:</b> ${quote.snapshot.source.record_refs.map(esc).join(' · ')}<br>模拟数据，非真实商业报价。 / Simulated data, not a binding commercial offer.<br>Powered by HugAgentOS · 报价修改后请重新计算 / Recalculate after changes.</footer>` : '<p class="trade-continued">报价明细续下页；合计及条件见末页。 / Continued; subtotal and terms on the final page.</p>'}
    </section>`);
  }
  /* dark-ok-begin: standalone export document uses white paper and fixed print colors. */
  return `<div class="trade-pdf-document"><style>
    .trade-pdf-document { width:1040px; color:#182b46; background:#fff; font:13px/1.45 "Microsoft YaHei","Noto Sans CJK SC","PingFang SC",Arial,sans-serif; }
    .trade-pdf-document * { box-sizing:border-box; }
    .trade-pdf-page { padding:8px 10px; }
    .trade-pdf-page header { display:flex;justify-content:space-between;border-bottom:3px solid #1e4b77;padding-bottom:10px;font-size:14px; }
    .trade-pdf-page header span { color:#8e4b00; }
    .trade-pdf-page h1 {font-size:28px;margin:14px 0 12px;} .trade-pdf-page h1 small {font-size:22px;font-weight:400;}
    .trade-meta {display:grid;grid-template-columns:1fr 1fr 100px;gap:24px;margin-bottom:16px;word-break:break-word;}
    .trade-pdf-page table {width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed;}
    .trade-pdf-page th {background:#eaf0f6;font-size:12px;}
    .trade-pdf-page th,.trade-pdf-page td {padding:9px 7px;border-bottom:1px solid #d9e2ec;text-align:right;overflow-wrap:anywhere;}
    .trade-pdf-page th:first-child,.trade-pdf-page td:first-child {text-align:left;}
    .trade-pdf-page tr,.trade-terms,.trade-total,.trade-notices p,.trade-pdf-page footer {break-inside:avoid;page-break-inside:avoid;}
    .trade-pdf-page small {font-size:11px;} .trade-total {display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:#eaf0f6;margin:14px 0;}
    .trade-total strong {display:block;text-align:right;font-size:25px;} .trade-terms p {margin:5px 0 9px;}
    .trade-notices {border-left:3px solid #d99b43;padding-left:10px;margin:12px 0;font-size:11px;} .trade-notices p {margin:5px 0;}
    .trade-pdf-page footer {border-top:1px solid #d9e2ec;padding-top:8px;font-size:10px;color:#52647b;overflow-wrap:anywhere;}
  </style>${pages.join('')}</div>`;
  /* dark-ok-end */
}

export async function exportTradeQuoteExcel(quote: TradeQuote): Promise<void> {
  XLSX.writeFile(buildTradeQuoteWorkbook(quote), quoteFilename(quote, 'xlsx'), { compression: true });
}

export async function exportTradeQuotePdf(quote: TradeQuote): Promise<void> {
  const { default: html2pdf } = await import('html2pdf.js');
  const container = document.createElement('div');
  container.innerHTML = buildTradeQuoteHtml(quote);
  // html2pdf clones this detached node into its own overlay at the proper paper width.
  await document.fonts.ready;
  const options = {
    filename: quoteFilename(quote, 'pdf'), margin: [10, 10, 14, 10] as [number, number, number, number],
    image: { type: 'jpeg' as const, quality: 0.98 },
    html2canvas: { scale: 2, useCORS: false, backgroundColor: '#ffffff', windowWidth: 1200 }, // dark-ok: PDF export always uses white paper.
    pagebreak: { mode: ['css', 'legacy'], avoid: ['tr', '.trade-total', '.trade-notices p', 'footer'] },
    jsPDF: { unit: 'mm', format: 'a4', orientation: 'landscape' as const },
  };
  const worker = html2pdf().set(options).from(container);
  await worker.toPdf().get('pdf').then((pdf: any) => {
    const count = pdf.internal.getNumberOfPages();
    for (let i = 1; i <= count; i++) {
      pdf.setPage(i); pdf.setFontSize(8); pdf.setTextColor(85, 100, 120);
      pdf.text(`${quote.quoteId} | DEMO | ${i} / ${count}`, 10, pdf.internal.pageSize.getHeight() - 5);
    }
  });
  await worker.save();
}
