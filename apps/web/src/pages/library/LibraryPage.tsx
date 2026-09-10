import { ComparisonNotes } from "../../features/ai/ComparisonNotes";
import type { components } from "@policylens/contracts/generated";
import { Card } from "@policylens/ui";
import { useEffect, useState, type FormEvent } from "react";
import { Link, navigate, useDraftGuard } from "../../app/router";
import { ResourceState } from "../../components/feedback/ResourceState";
import { PageHeader, ErrorPanel } from "../../components/layout/LegacyShared";
import { ExplanationRecord, explanationStatuses, type Explanation } from "../../features/ai/ExplanationPanel";
import { SourcesPage } from "../../features/evidence/SourcesPage";
import { useAction, useResource } from "../../hooks/useResource";
import { formText } from "../../lib/forms";
import { familyBase, type Policy } from "../../services/household";
import { jsonBody, request, rawRequest } from "../../services/http";

type Document = components["schemas"]["DocumentView"];
type Content = components["schemas"]["DocumentContent"];
type Import = {id:string;status:string;source:{title:string}};

function OriginalViewer({content,source,initialPage}: {content:Content;source:boolean;initialPage:number}) {
  const [page,setPage] = useState(Math.max(1,Math.min(initialPage,content.pages.length)));
  const [pdf,setPdf] = useState(""); const [error,setError] = useState("");
  useEffect(() => {
    if(content.kind !== "PDF") return;
    let objectUrl = ""; let active = true;
    rawRequest(`${familyBase}/${source ? "sources" : "documents"}/${content.id}/original`).then(r => r.blob()).then(blob => {if(active) {objectUrl=URL.createObjectURL(blob);setPdf(objectUrl);}}).catch((e:unknown) => {if(active)setError(e instanceof Error ? e.message : "原件读取失败");});
    return () => {active=false;if(objectUrl) URL.revokeObjectURL(objectUrl);};
  },[content.id,content.kind,source]);
  return <Card><h2>本地原文</h2><p>{content.notice}</p>{error && <ErrorPanel message={error} />}<label>页码<select aria-label="原文页码" value={page} onChange={e => setPage(Number(e.target.value))}>{content.pages.map((_,i) => <option key={i} value={i+1}>第 {i+1} 页</option>)}</select></label>{pdf && <><a className="button secondary" href={`${pdf}#page=${page}`} target="_blank" rel="noreferrer">打开 PDF 原件</a><iframe title="本地 PDF 原件" className="document-frame" src={`${pdf}#page=${page}`} sandbox="allow-same-origin" /></>}<h3>第 {page} 页提取文本</h3><pre className="document-text">{content.pages[page-1] || "此页没有可提取文字，请查看原件。扫描件尚未执行 OCR，可以手工记录重点。"}</pre></Card>;
}

function DocumentDetail({id,source,page}: {id:string;source:boolean;page:number}) {
  const content = useResource<Content>(`${familyBase}/${source ? "sources" : "documents"}/${id}/content`);
  return <><Link href={source ? "/library?tab=sources" : "/library"} className="back">← 资料与笔记</Link><ResourceState error={content.error} loading={!content.data} retry={content.refresh}>{content.data && <><PageHeader title={content.data.title} subtitle="原文与提取文字分别呈现，资料始终保存在本地。" /><OriginalViewer content={content.data} source={source} initialPage={page} />{!source && <DocumentAssociation id={id} />}</>}</ResourceState></>;
}

function DocumentAssociation({id}: {id:string}) {
  const document = useResource<Document>(`${familyBase}/documents/${id}`);
  const policies = useResource<Policy[]>(`${familyBase}/policies`);
  const [dirty,setDirty] = useState(false); useDraftGuard(dirty);
  const {busy,error,run} = useAction(); const [message,setMessage]=useState("");
  const save = (event:FormEvent<HTMLFormElement>) => {event.preventDefault();const form = new FormData(event.currentTarget);const current=document.data;if(!current)return;void run(async () => {await request(`${familyBase}/documents/${id}`,jsonBody({title:formText(form,"title"),policy_id:formText(form,"policy") || null,expected_revision:current.revision},"PUT"));setDirty(false);setMessage("已保存资料名称与关联。");document.refresh();});};
  return <Card><h2>资料归属</h2><ResourceState error={document.error || policies.error} loading={!document.data || !policies.data} retry={() => {document.refresh();policies.refresh();}}>{document.data && policies.data && <form onSubmit={save} onChange={() => setDirty(true)}><div className="form-grid"><label>资料名称<input name="title" required maxLength={160} defaultValue={document.data.title} /></label><label>关联保单<select name="policy" defaultValue={document.data.policy_id ?? ""}><option value="">暂不关联</option>{policies.data.map(p => <option key={p.id} value={p.id}>{p.member_nickname ?? "归属待确认"} · {p.name}</option>)}</select></label></div>{error && <ErrorPanel message={error} />}{message && <p role="status">{message}</p>}<button className="button primary" disabled={busy}>保存资料关联</button></form>}</ResourceState></Card>;
}

export function LibraryPage({id,query}: {id?:string;query:URLSearchParams}) {
  const tab=query.get("tab") ?? "documents"; const policyId=query.get("policy") ?? "";
  const [uploadPolicy,setUploadPolicy]=useState(policyId);
  const documents=useResource<Document[]>(`${familyBase}/documents${policyId ? `?policy_id=${encodeURIComponent(policyId)}` : ""}`);
  const policies=useResource<Policy[]>(`${familyBase}/policies`);
  const notes=useResource<Explanation[]>(`${familyBase}/explanations`);
  const imports=useResource<Import[]>("/api/v1/imports");
  const {busy,error,run}=useAction();
  const upload=(event:FormEvent<HTMLFormElement>) => {event.preventDefault();const data=new FormData(event.currentTarget);if(!data.get("policy_id"))data.delete("policy_id");void run(async () => {const result=await request<Document>(`${familyBase}/documents`,{method:"POST",body:data});navigate(`/library/${result.id}`);});};
  if(id) return query.get("kind") === "note" ? <><Link href="/library?tab=notes" className="back">← 解读与笔记</Link><ExplanationRecord id={id} /></> : <DocumentDetail id={id} source={query.get("kind") === "source"} page={Number(query.get("page")) || 1} />;
  return <><PageHeader title="资料与笔记" subtitle="找到原件、继续整理，或回看已经确认的解释。" /><div className="filter-tabs">{[["documents","家庭资料"],["notes","解读与笔记"],["imports","待整理产品资料"],["sources","来源与证据"]].map(([key,label]) => <Link key={key} href={`/library?tab=${key}`} className={key === tab ? "active" : ""}>{label}</Link>)}</div>
    {tab === "sources" ? <SourcesPage /> : tab === "notes" ? <><ComparisonNotes /><ResourceState error={notes.error} loading={!notes.data} retry={notes.refresh}><Card><h2>保存的 AI 解读</h2><p>草稿与接受为笔记分别标记，原始事实不受影响。</p>{notes.data?.length ? notes.data.map(n => <Link className="policy-link" key={n.id} href={`/library/${n.id}?kind=note`}><div><strong>{n.scope === "POLICY" ? "保单条款解读" : "养老计算解读"} · {explanationStatuses[n.status]}</strong><small>{new Date(n.created_at).toLocaleString("zh-CN")}{n.stale ? " · 关联资料已变化" : ""}</small></div><span>查看 →</span></Link>) : <p>尚未保存解读。从保单详情或养老计算进入，先检查预览再决定是否调用。</p>}</Card></ResourceState></> : tab === "imports" ? <Card><div className="card-title"><h2>产品资料整理记录</h2><Link href="/imports" className="button primary">整理新资料</Link></div><ResourceState error={imports.error} loading={!imports.data} retry={imports.refresh}>{imports.data?.length ? imports.data.map(i => <Link className="policy-link" href={`/imports/${i.id}`} key={i.id}><span>{i.source.title}</span><span>{i.status === "PUBLISHED" ? "已核验入库" : "查看整理进度"} →</span></Link>) : <p>暂无整理记录。家庭保单原件请先保存在“家庭资料”。</p>}</ResourceState></Card> : <>
      <Card><h2>添加家庭资料</h2><p>PDF 原件会加密保存在本地，不自动外发。文字 PDF 可查看提取文本，扫描件可以存档和看原件；OCR 留待后续。</p><form onSubmit={upload}><div className="form-grid"><label>PDF 文件（最多 10 MiB、100 页）<input name="file" type="file" accept=".pdf,application/pdf" required /></label><label>属于哪份保单<select name="policy_id" value={uploadPolicy} onChange={event => setUploadPolicy(event.target.value)}><option value="">暂不关联</option>{policies.data?.map(p => <option key={p.id} value={p.id}>{p.member_nickname ?? "归属待确认"} · {p.name}</option>)}</select></label></div>{error && <ErrorPanel message={error} />}<button className="button primary" disabled={busy}>{busy ? "正在加密保存…" : "保存本地资料"}</button></form></Card>
      <div className="section-heading"><h2>{policyId ? "这份保单的资料" : "已有家庭资料"}</h2>{policyId && <Link href="/library">查看全部</Link>}</div><ResourceState error={documents.error} loading={!documents.data} retry={documents.refresh}><Card>{documents.data?.length ? documents.data.map(d => <Link className="policy-link" key={d.id} href={`/library/${d.id}`}><div><strong>{d.title}</strong><small>{policies.data?.find(p => p.id === d.policy_id)?.name ?? "暂未关联保单"} · {d.page_count} 页 · {d.text_available ? "可查看文字" : "扫描件／无文字层"}</small></div><span>查看原文 →</span></Link>) : <p>还没有相关资料，可以先添加一份原件。</p>}</Card></ResourceState>
    </>}
  </>;
}
