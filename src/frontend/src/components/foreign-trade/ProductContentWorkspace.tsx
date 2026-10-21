// Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Empty, Input, InputNumber, Select, Tag } from 'antd';
import { CopyOutlined, DownloadOutlined, FileImageOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons';
import { t } from '../../i18n';
import { ApiResponseError } from '../../utils/apiError';
import { createInquiry, searchInquiryProducts, type InquiryProduct } from '../../utils/foreignTradeInquiryApi';
import { createContentPack, downloadContentAsset, downloadContentDemo, generateContentPack, getContentPack, listContentPacks,
  previewContentAsset, previewContentFile, updateContentPack, uploadContentPackFile,
  type ContentAssetKind, type ContentDownloadKind, type ContentPackInput, type ContentPackRecord, type DemoFileKind,
} from '../../utils/foreignTradeContentApi';
import './ProductContentWorkspace.css';

const emptyPack = (): ContentPackInput => ({ title: '', product_name: '', brand: '', model: '', source_url: '', raw_text: '', facts: [], image_credit: '' });
const demoPack = (): ContentPackInput => ({ ...emptyPack(), title: t('Raspberry Pi 5 · 真实产品资料示例'), product_name: 'Raspberry Pi 5', brand: 'Raspberry Pi', model: '5', source_url: 'https://www.raspberrypi.com/products/raspberry-pi-5/', image_credit: 'Photo: SimonWaldherr, Raspberry Pi 5.jpg (CC BY 4.0). Layout and text added; original photo retained. Source: https://commons.wikimedia.org/wiki/File:Raspberry_Pi_5.jpg License: https://creativecommons.org/licenses/by/4.0/' });
function packInput(record: ContentPackRecord): ContentPackInput {
  return { title: record.title, product_name: record.product_name, brand: record.brand, model: record.model, source_url: record.source_url,
    raw_text: record.raw_text, facts: record.facts.map((fact) => ({ ...fact })), image_credit: record.image_credit };
}
function dateText(value: string) { const date = new Date(value); return Number.isFinite(date.getTime()) ? date.toLocaleString(undefined, { hour12: false }) : value; }
function safeLink(value?: string): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined; } catch { return undefined; }
}
function contentError(error: unknown): string {
  if (error instanceof ApiResponseError) {
    if (error.status === 409) return t('资料包已在其他页面更新，请刷新记录后重试。');
    if (error.status === 403 || error.status === 404) return t('资料包或文件不存在，或当前账号无权访问。');
  }
  return error instanceof Error ? error.message : t('操作失败，请重试。');
}
function assetLabel(kind: ContentAssetKind): string {
  return { square: t('方形商品图'), landscape: t('横版展示图'), spec: t('规格信息图') }[kind];
}

export function ProductContentWorkspace({ onOpenInquiries }: { onOpenInquiries?: () => void }) {
  const [records, setRecords] = useState<ContentPackRecord[]>([]);
  const [record, setRecord] = useState<ContentPackRecord | null>(null);
  const [form, setForm] = useState<ContentPackInput>(emptyPack);
  const [busy, setBusy] = useState('loading');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [sourcePreview, setSourcePreview] = useState('');
  const [assetPreviews, setAssetPreviews] = useState<Partial<Record<ContentAssetKind, string>>>({});
  const [assetErrors, setAssetErrors] = useState<string[]>([]);
  const [productQuery, setProductQuery] = useState('');
  const [products, setProducts] = useState<InquiryProduct[] | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<InquiryProduct | null>(null);
  const [quantity, setQuantity] = useState<number | null>(null);
  const [packaging, setPackaging] = useState<'standard' | 'custom' | undefined>();
  const [destination, setDestination] = useState('');
  const [inquiryCreated, setInquiryCreated] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const dirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(record ? packInput(record) : emptyPack()), [form, record]);
  const outputs = dirty ? null : record?.outputs;
  const locked = !!busy;
  const lastImage = record?.documents.filter((doc) => doc.kind === 'image').at(-1);
  const change = (patch: Partial<ContentPackInput>) => { setForm((current) => ({ ...current, ...patch })); setConfirmed(false); };
  const accept = (next: ContentPackRecord) => {
    setRecord(next); setForm(packInput(next)); setConfirmed(false);
    setRecords((current) => [next, ...current.filter((item) => item.pack_id !== next.pack_id)].sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
    return next;
  };
  useEffect(() => {
    let active = true;
    listContentPacks().then((items) => { if (active) { setRecords(items); if (items[0]) { setRecord(items[0]); setForm(packInput(items[0])); } } })
      .catch((err) => { if (active) setError(contentError(err)); }).finally(() => { if (active) setBusy(''); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true; let objectUrl = ''; setSourcePreview('');
    if (record && lastImage) void previewContentFile(record.pack_id, lastImage.file_id).then((blob) => {
      if (active) { objectUrl = URL.createObjectURL(blob); setSourcePreview(objectUrl); }
    }).catch(() => { /* Upload metadata remains visible if preview is unavailable. */ });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [record?.pack_id, lastImage?.file_id]);
  useEffect(() => {
    let active = true; const urls: string[] = []; setAssetPreviews({}); setAssetErrors([]);
    if (record && outputs) for (const asset of outputs.assets) {
      void previewContentAsset(record.pack_id, asset.kind, record.revision).then((blob) => {
        if (!active) return; const url = URL.createObjectURL(blob); urls.push(url);
        setAssetPreviews((current) => ({ ...current, [asset.kind]: url }));
      }).catch(() => { if (active) setAssetErrors((current) => [...current, asset.kind]); });
    }
    return () => { active = false; urls.forEach((url) => URL.revokeObjectURL(url)); };
  }, [record?.pack_id, outputs]);
  async function run(name: string, work: () => Promise<void>) {
    if (locked) return; setBusy(name); setError(''); setNotice('');
    try { await work(); } catch (err) { setError(contentError(err)); } finally { setBusy(''); }
  }
  async function save(): Promise<ContentPackRecord> {
    const input = { ...form, title: form.title.trim() || form.product_name.trim() || t('新的商品资料包') };
    if (record) return dirty ? accept(await updateContentPack(record.pack_id, record.revision, input)) : record;
    const created = await createContentPack(input.title);
    setRecord(created); setRecords((current) => [created, ...current]);
    return accept(await updateContentPack(created.pack_id, created.revision, input));
  }
  function startNew(demo = false) {
    setRecord(null); setForm(demo ? demoPack() : emptyPack()); setConfirmed(false); setError(''); setNotice(''); setInquiryCreated(false);
  }
  function download(kind: ContentDownloadKind) { if (record) void run(`download-${kind}`, () => downloadContentAsset(record.pack_id, kind, record.revision)); }
  function downloadDemo(kind: DemoFileKind) { void run(`demo-${kind}`, () => downloadContentDemo(kind)); }
  function uploadFiles(files: File[]) {
    if (!files.length) return;
    void run('upload', async () => {
      if (files.some((file) => file.size > 8 * 1024 * 1024)) throw new Error(t('单个文件不能超过 8 MiB。'));
      if (files.length + (record?.documents.length || 0) > 10) throw new Error(t('每个资料包最多上传 10 个文件。'));
      if (files.reduce((total, file) => total + file.size, 0) + (record?.documents.reduce((total, doc) => total + doc.size, 0) || 0) > 32 * 1024 * 1024) throw new Error(t('每个资料包的文件总大小不能超过 32 MiB。'));
      let current = await save();
      for (const file of files) current = accept(await uploadContentPackFile(current.pack_id, current.revision, file));
      setNotice(t('文件已上传。请对照原文核对事实，确认后再生成。'));
    });
  }
  const listingText = outputs ? [outputs.listing.title, '', ...outputs.listing.bullets.map((bullet) => `• ${bullet}`), '', outputs.listing.description].join('\n') : '';
  const faqText = outputs ? outputs.faq.map((faq) => `${faq.question}\n${faq.answer}`).join('\n\n') : '';
  const canGenerate = confirmed && (!lastImage || !!form.image_credit.trim()) && !!form.product_name.trim() && form.facts.length > 0 && form.facts.every((fact) => fact.label.trim() && fact.value.trim());

  return <main className="jx-productContent" aria-label={t('商品资料工作台')}>
    <header className="jx-contentHeader"><div><span className="jx-contentEyebrow">FOREIGN TRADE · PRODUCT CONTENT</span><h1>{t('商品资料工作台')}</h1><p>{t('把产品事实与授权原图，整理成可审阅、可复用的上品资料。')}</p></div>
      <Button icon={<FileImageOutlined />} disabled={locked || dirty} onClick={() => startNew(true)}>{t('新建 Raspberry Pi 5 示例')}</Button></header>
    <div className="jx-contentLayout">
      <aside className="jx-contentSidebar" aria-label={t('商品资料包列表')}><div className="jx-contentSidebarTitle"><strong>{t('我的资料包')}</strong><Tag>{records.length}</Tag></div>
        <Button block type="primary" icon={<PlusOutlined />} disabled={locked || dirty} onClick={() => startNew()}>{t('新建资料包')}</Button>
        <Button block type="text" icon={<ReloadOutlined />} disabled={locked || dirty} onClick={() => void run('refresh', async () => { setRecords(await listContentPacks()); if (record) accept(await getContentPack(record.pack_id)); })}>{t('刷新记录')}</Button>
        {!records.length && <p className="jx-contentMuted">{t('还没有资料包，先新建或载入示例。')}</p>}
        <nav>{records.map((item) => <button key={item.pack_id} className={`jx-contentListItem ${record?.pack_id === item.pack_id ? 'is-active' : ''}`} disabled={locked || dirty} onClick={() => void run('open', async () => { accept(await getContentPack(item.pack_id)); })}><strong>{item.title}</strong><span>{item.product_name || t('产品名称待补充')}</span><small>{item.outputs ? t('已有待审阅资料') : t('待整理')} · {dateText(item.updated_at)}</small></button>)}</nav>
      </aside>
      <div className="jx-contentMain" aria-busy={locked}>
        {error && <Alert type="error" showIcon title={error} />}{notice && <Alert type="success" showIcon title={notice} />}
        <div className="jx-contentRecordTitle"><div><h2>{record?.title || t('新的商品资料包')}</h2><span className="jx-contentMuted">{record ? t('记录版本 {revision} · 更新于 {time}', { revision: record.revision, time: dateText(record.updated_at) }) : t('资料、原图和生成结果保存在当前账号。')}</span></div>
          <div className="jx-contentActions"><Button disabled={locked || !dirty} onClick={() => { setForm(record ? packInput(record) : emptyPack()); setConfirmed(false); }}>{t('放弃修改')}</Button><Button type="primary" disabled={locked || !dirty} loading={busy === 'save'} onClick={() => void run('save', async () => { await save(); setNotice(t('商品资料已保存。')); })}>{t('保存资料')}</Button></div></div>
        {dirty && record && <Alert type="warning" showIcon title={t('资料已修改，旧生成结果暂不可下载。保存并重新确认事实后，请重新生成。')} />}
        <section className="jx-contentSection">
          <div className="jx-contentSectionTitle"><span>01</span><div><h3>{t('收集产品资料与原图')}</h3><p>{t('支持文本、表格与可提取文字的 PDF；扫描件请先提供文字。')}</p></div></div>
          <details className="jx-contentDemo"><summary>{t('使用真实公开资料：Raspberry Pi 5')}</summary>
            <p>{t('示例规格来自产品官网，照片按其授权条件使用。请下载样例，再从下方实际上传；示例不含供货价格、库存或采购关系。')}</p>
            <div className="jx-contentActions"><Button icon={<DownloadOutlined />} disabled={locked} onClick={() => downloadDemo('txt')}>{t('下载示例资料 TXT')}</Button><Button icon={<DownloadOutlined />} disabled={locked} onClick={() => downloadDemo('csv')}>{t('下载示例事实 CSV')}</Button><Button icon={<DownloadOutlined />} disabled={locked} onClick={() => downloadDemo('photo')}>{t('下载授权原图')}</Button></div>
          </details>
          <div className="jx-contentGrid"><label>{t('资料包标题')}<Input value={form.title} maxLength={200} disabled={locked} onChange={(e) => change({ title: e.target.value })} /></label>
            <label>{t('产品名称')}<Input value={form.product_name} maxLength={200} disabled={locked} onChange={(e) => change({ product_name: e.target.value })} /></label>
            <label>{t('品牌')}<Input value={form.brand} maxLength={100} disabled={locked} onChange={(e) => change({ brand: e.target.value })} /></label>
            <label>{t('产品型号')}<Input value={form.model} maxLength={100} disabled={locked} onChange={(e) => change({ model: e.target.value })} /></label></div>
          <label className="jx-contentField">{t('主要资料来源')}<Input value={form.source_url} maxLength={2000} disabled={locked} placeholder="https://" onChange={(e) => change({ source_url: e.target.value })} />{safeLink(form.source_url) && <a href={safeLink(form.source_url)} target="_blank" rel="noopener noreferrer">{t('查看原始来源')} ↗</a>}</label>
          <input className="jx-contentFileInput" ref={fileInput} type="file" multiple accept=".txt,.csv,.json,.xlsx,.pdf,.png,.jpg,.jpeg,.webp" aria-label={t('选择产品资料与原图')} disabled={locked} onChange={(e) => { const files = Array.from(e.target.files || []); e.target.value = ''; uploadFiles(files); }} />
          <div className="jx-contentUpload"><UploadOutlined /><div><strong>{t('上传产品表、说明资料和授权照片')}</strong><p>{t('TXT / CSV / JSON / XLSX / PDF / PNG / JPEG / WebP · 单文件 8 MiB，最多 10 个文件')}</p></div><Button icon={<UploadOutlined />} loading={busy === 'upload'} disabled={locked} onClick={() => fileInput.current?.click()}>{t('选择文件上传')}</Button></div>
          {!!record?.documents.length && <div className="jx-contentDocuments">{record.documents.map((doc) => <article key={doc.file_id}><div><strong>{doc.name}</strong><Tag>{doc.kind === 'image' ? t('原图') : t('资料')}</Tag><small>{Math.ceil(doc.size / 1024)} KB</small></div>
            {doc.text && <details><summary>{t('查看提取文字')}</summary><pre>{doc.text}</pre></details>}</article>)}</div>}
          {!!record?.warnings.length && <ul className="jx-contentWarnings">{record.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
          {lastImage && <div className="jx-contentOriginal">{sourcePreview ? <img src={sourcePreview} alt={t('当前使用的商品原图')} /> : <FileImageOutlined />}<div><strong>{t('本次排版使用最后上传的图片')}</strong><p>{lastImage.name}</p><small>{t('只做等比缩放、留白排版和信息标注，不改变产品外观。')}</small></div></div>}
          <label className="jx-contentField">{t('图片来源与授权署名')}<Input.TextArea value={form.image_credit} maxLength={600} rows={2} disabled={locked} placeholder={t('600 字符以内，保留作者、图片来源及许可证链接。')} onChange={(e) => change({ image_credit: e.target.value })} /><small className="jx-contentMuted">{t('使用简短署名，保留作者、许可与来源；内容会随图片一起导出。')}</small></label>
          <label className="jx-contentField">{t('产品原始文字')}<Input.TextArea value={form.raw_text} rows={5} disabled={locked} maxLength={100000} onChange={(e) => change({ raw_text: e.target.value })} placeholder={t('保留原始规格和说明，便于核对。')} /></label>
        </section>

        <section className="jx-contentSection">
          <div className="jx-contentSectionTitle"><span>02</span><div><h3>{t('核对唯一的产品事实表')}</h3><p>{t('标题、图片与客服答案共用这份事实。未提供的认证、价格或性能不作承诺。')}</p></div></div>
          {!!record?.suggested_facts.length && <div className="jx-contentSuggestions"><strong>{t('从资料中提取的待核对字段')}</strong><ul>{record.suggested_facts.map((fact, index) => <li key={index}><span>{fact.label}：{fact.value}</span>{safeLink(fact.source_url) && <a href={safeLink(fact.source_url)} target="_blank" rel="noopener noreferrer">{t('来源')} ↗</a>}</li>)}</ul>
            <Button disabled={locked} onClick={() => { const added = record.suggested_facts.filter((suggestion) => !form.facts.some((fact) => fact.label === suggestion.label && fact.value === suggestion.value && fact.source_url === suggestion.source_url)); change({ facts: [...form.facts, ...added].slice(0, 20) }); }}>{t('加入事实表，逐项核对')}</Button></div>}
          <div className="jx-contentFacts">{form.facts.map((fact, index) => <div className="jx-contentFact" key={index}><span className="jx-contentFactIndex">{index + 1}</span>
            <label>{t('事实名称')}<Input value={fact.label} maxLength={160} disabled={locked} onChange={(e) => change({ facts: form.facts.map((item, i) => i === index ? { ...item, label: e.target.value } : item) })} /></label>
            <label>{t('已核对的值')}<Input value={fact.value} maxLength={1500} disabled={locked} onChange={(e) => change({ facts: form.facts.map((item, i) => i === index ? { ...item, value: e.target.value } : item) })} /></label>
            <label>{t('事实来源链接')}<Input value={fact.source_url} maxLength={2000} disabled={locked} onChange={(e) => change({ facts: form.facts.map((item, i) => i === index ? { ...item, source_url: e.target.value } : item) })} /></label>
            <Button type="text" danger disabled={locked} onClick={() => change({ facts: form.facts.filter((_, i) => i !== index) })}>{t('移除')}</Button>
          </div>)}</div>
          {!form.facts.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚无已核对事实。可从上传资料加入，或手工填写。')} />}
          <Button type="dashed" icon={<PlusOutlined />} disabled={locked || form.facts.length >= 20} onClick={() => change({ facts: [...form.facts, { label: '', value: '', source_url: form.source_url }] })}>{t('添加产品事实')}</Button>
          <div className="jx-contentConfirm"><Checkbox checked={confirmed} disabled={locked} onChange={(e) => setConfirmed(e.target.checked)}>{t('我已对照来源逐项核对产品事实，并确认图片可用于本次制作。')}</Checkbox><p>{t('每次修改资料或上传文件后，都需要重新核对。生成结果仍需人工审阅。')}</p></div>
          <div className="jx-contentActions"><Button type="primary" icon={<FileImageOutlined />} loading={busy === 'generate'} disabled={locked || !canGenerate} onClick={() => void run('generate', async () => { const saved = await save(); accept(await generateContentPack(saved.pack_id, saved.revision)); setNotice(t('资料包已生成，请核对文案、图片和事实引用后使用。')); })}>{t('生成上品文案、FAQ 与图片')}</Button>
            {!lastImage && <span className="jx-contentMuted">{t('尚未上传原图，本次只生成文字资料。')}</span>}{lastImage && !form.image_credit.trim() && <span className="jx-contentMuted">{t('请先填写图片来源与授权署名。')}</span>}</div>
        </section>
        <section className="jx-contentSection">
          <div className="jx-contentSectionTitle"><span>03</span><div><h3>{t('审阅并下载商品资料包')}</h3><p>{t('所有结果均为待审阅草稿，不会自动上架或发送给客户。')}</p></div></div>
          {!outputs ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('核对产品事实后，生成结果会显示在这里。')} /> : <>
            <div className="jx-contentResultHeader"><div><Tag>{outputs.method === 'ai_grounded' ? t('AI 根据事实生成') : t('模板整理')}</Tag><Tag>{t('尚未发布')}</Tag><span>{dateText(outputs.generated_at)}</span></div><Button type="primary" icon={<DownloadOutlined />} loading={busy === 'download-zip'} disabled={locked} onClick={() => download('zip')}>{t('下载全部资料 ZIP')}</Button></div>
            {outputs.method === 'template' && <Alert type="warning" showIcon title={t('本次使用模板整理；未翻译的原文会保留，请补充审阅。')} />}
            {!!outputs.warnings.length && <ul className="jx-contentWarnings">{outputs.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
            <div className="jx-contentOutputCard"><div className="jx-contentCardTitle"><h4>{t('上品文案草稿')}</h4><div className="jx-contentActions"><Button size="small" icon={<CopyOutlined />} disabled={locked} onClick={() => void run('copy-listing', async () => { await navigator.clipboard.writeText(listingText); setNotice(t('文案已复制。')); })}>{t('复制文案')}</Button><Button size="small" icon={<DownloadOutlined />} disabled={locked} onClick={() => download('listing')}>{t('下载文案')}</Button></div></div>
              <h5>{outputs.listing.title}</h5><ul>{outputs.listing.bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}</ul><p className="jx-contentDescription">{outputs.listing.description}</p>
            </div>
            {!!outputs.translated_facts.length && <details className="jx-contentTranslated"><summary>{t('查看生成内容使用的事实与引用')}</summary><ul>{outputs.translated_facts.map((fact, index) => <li key={index}><strong>{fact.label}</strong>：{fact.value} <span>{t('事实项 {refs}', { refs: fact.source_refs.join(', ') })}</span></li>)}</ul></details>}
            <div className="jx-contentOutputCard"><div className="jx-contentCardTitle"><h4>{t('客服 FAQ')}</h4><div className="jx-contentActions"><Button size="small" icon={<CopyOutlined />} disabled={locked} onClick={() => void run('copy-faq', async () => { await navigator.clipboard.writeText(faqText); setNotice(t('FAQ 已复制。')); })}>{t('复制 FAQ')}</Button><Button size="small" icon={<DownloadOutlined />} disabled={locked} onClick={() => download('faq')}>{t('下载 FAQ')}</Button></div></div>
              <div className="jx-contentFaq">{outputs.faq.map((faq, index) => <article key={index}><strong>{faq.question}</strong><p>{faq.answer}</p><small>{faq.source_refs.length ? t('依据事实项 {refs}', { refs: faq.source_refs.join(', ') }) : t('需人工补充确认')}</small></article>)}</div>
            </div>
            {lastImage && !outputs.assets.length && <Alert type="warning" showIcon title={t('本次未生成可用图片，请查看上方原因。文案与 FAQ 可单独审阅下载。')} />}
            {!!outputs.assets.length && <div className="jx-contentImageGrid">{outputs.assets.map((asset) => <article key={asset.kind}>
              <div className="jx-contentImagePreview">{assetPreviews[asset.kind] ? <img src={assetPreviews[asset.kind]} alt={assetLabel(asset.kind)} /> : <span>{assetErrors.includes(asset.kind) ? t('预览暂不可用，可尝试下载文件。') : t('正在加载图片预览…')}</span>}</div>
              <div><strong>{assetLabel(asset.kind)}</strong><small>{asset.width} × {asset.height} · PNG</small><Button icon={<DownloadOutlined />} disabled={locked} loading={busy === `download-${asset.kind}`} onClick={() => download(asset.kind)}>{t('下载 PNG')}</Button></div>
            </article>)}</div>}
          </>}
        </section>
        <section className="jx-contentSection jx-contentCatalog">
          <div className="jx-contentSectionTitle"><span>↗</span><div><h3>{t('从演示目录衔接询盘报价')}</h3><p>{t('真实产品资料与模拟报价目录独立。不会把 Raspberry Pi 等外部品牌规格套用到 DESK-001 的价格上。')}</p></div></div>
          <Alert type="info" showIcon title={t('本区域仅使用演示目录的 SKU、MOQ 和价格；与上方真实产品无供货关系。')} />
          <div className="jx-contentSearch"><Input value={productQuery} disabled={locked} aria-label={t('查询演示目录')} placeholder={t('查询产品名称或 SKU，例如 DESK-001')} onChange={(e) => setProductQuery(e.target.value)} onPressEnter={() => void run('products', async () => { const result = await searchInquiryProducts(productQuery); setProducts(result.data.products); })} /><Button icon={<SearchOutlined />} disabled={locked} loading={busy === 'products'} onClick={() => void run('products', async () => { const result = await searchInquiryProducts(productQuery); setProducts(result.data.products); })}>{t('查询演示目录')}</Button></div>
          {products && <div className="jx-contentCatalogProducts">{!products.length && <p>{t('没有找到匹配产品，请换一个关键词。')}</p>}{products.map((product) => <button className={selectedProduct?.sku === product.sku ? 'is-active' : ''} key={product.sku} disabled={locked} onClick={() => { setSelectedProduct(product); setQuantity(null); setPackaging(undefined); setInquiryCreated(false); }}><strong>{product.sku} · {product.name_zh}</strong><small>{t('起订量 {moq} 件 · 参考生产周期 {days} 天', { moq: product.moq, days: product.production_lead_days })}</small><Tag>DEMO</Tag></button>)}</div>}
          {selectedProduct && <div className="jx-contentCatalogForm"><strong>{t('已选择演示产品：{sku}', { sku: selectedProduct.sku })}</strong><div className="jx-contentGrid"><label>{t('采购数量')}<InputNumber min={1} precision={0} value={quantity} disabled={locked} placeholder={t('请明确填写数量')} onChange={setQuantity} /></label>
            <label>{t('包装方式')}<Select value={packaging} disabled={locked} placeholder={t('请选择包装方式')} options={[{ value: 'standard', label: t('标准包装') }, { value: 'custom', label: t('定制包装') }]} onChange={setPackaging} /></label>
            <label>{t('交付目的国')}<Input value={destination} disabled={locked} onChange={(e) => setDestination(e.target.value)} /></label></div>
            <Button disabled={locked || dirty || !quantity || !packaging || !destination.trim()} loading={busy === 'create-inquiry'} onClick={() => void run('create-inquiry', async () => {
              await createInquiry({ title: t('演示目录询盘：{sku}', { sku: selectedProduct.sku }), buyer: { company_name: '', website: '', email: '', country: '' },
                raw_inquiry: `TEAM-CREATED DEMONSTRATION INQUIRY. Please quote ${quantity} units of ${selectedProduct.sku} with ${packaging} packaging for delivery to ${destination.trim()}. This inquiry uses the fictional demo catalog and is unrelated to external brand product materials.`,
                items: [{ sku: selectedProduct.sku, quantity: quantity!, custom_packaging: packaging === 'custom' }], destination_country: destination.trim(), requested_lead_days: null, is_demo_inquiry: true });
              setInquiryCreated(true); setNotice(t('演示询盘已创建，可前往询盘工作台查询、报价和导出。'));
            })}>{t('用此目录产品创建询盘')}</Button>{dirty && <p className="jx-contentMuted">{t('请先保存或放弃上方资料修改，再创建询盘。')}</p>}
          </div>}
          {inquiryCreated && onOpenInquiries && <Button type="link" onClick={onOpenInquiries}>{t('前往询盘工作台')} →</Button>}
        </section>
        <footer className="jx-contentFooter">Powered by HugAgentOS · {t('保留产品事实、来源和图片授权；人工审阅后使用。')}</footer>
      </div>
    </div>
  </main>;
}
