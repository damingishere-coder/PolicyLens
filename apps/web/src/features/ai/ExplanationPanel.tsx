import type { components } from "@policylens/contracts/generated";
import { Card } from "@policylens/ui";
import { useEffect, useState } from "react";
import { Link } from "../../app/router";
import { ErrorPanel } from "../../components/layout/LegacyShared";
import { useAction, useResource } from "../../hooks/useResource";
import { familyBase } from "../../services/household";
import { jsonBody, request } from "../../services/http";
import type { ProductDetail } from "../research/types";

export type Explanation = Required<components["schemas"]["ExplanationView"]>;
const base = `${familyBase}/explanations`;
export const explanationStatuses = {PREVIEW:"等待外发确认",RUNNING:"正在解读",DRAFT:"待审阅草稿",ACCEPTED_AS_NOTE:"已保存为笔记",REJECTED:"已拒绝",FAILED:"调用未完成",CANCELLED:"已取消"};

export function ExplanationRecord({id}: {id:string}) {
  const resource = useResource<Explanation>(`${base}/${id}`);
  const [confirmed,setConfirmed] = useState(false);
  const {busy,error,run} = useAction();
  const record = resource.data;
  useEffect(() => {
    if(record?.status !== "RUNNING" && !busy) return;
    const timer = window.setInterval(resource.refresh,3000);
    return () => window.clearInterval(timer);
  },[record?.status,busy,resource.refresh]);
  const mutate = (suffix:string,body?:unknown,method="POST") => void run(async () => {
    try {await request(`${base}/${id}/${suffix}`,body ? jsonBody(body,method) : {method});}
    finally {setConfirmed(false);resource.refresh();}
  });
  if(!record) return <Card>{resource.error ? <ErrorPanel message={resource.error} /> : <p>正在读取解读记录…</p>}<button className="button secondary" onClick={resource.refresh}>刷新记录</button></Card>;
  return <Card className="explanation"><div className="card-title"><h2>AI 解读与笔记</h2><span>{explanationStatuses[record.status]}</span></div>
    {record.stale && <div className="notice warning">关联资料已变化。这份记录仅代表当时的输入，请回到原页面重新核对。</div>}
    {(error || record.error) && <ErrorPanel message={error || record.error || ""} />}
    <details open={record.status === "PREVIEW"}><summary>检查本次实际外发内容</summary><p>将发送：{record.will_send.join("；")}。</p><p>白名单不包含：{record.will_not_send.join("；")}。请同时检查摘录本身是否含有私人信息。</p><pre>{JSON.stringify(record.payload,null,2)}</pre><small>预览校验值：{record.preview_hash}</small></details>
    {record.status === "PREVIEW" && <><label className="confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />我已检查本次完整内容，同意仅外发以上资料</label><button className="button primary" disabled={!confirmed || busy || record.stale} onClick={() => mutate("run",{confirmed:true,preview_hash:record.preview_hash})}>确认并开始解读</button><p className="hint">每份预览只运行一次，15 分钟后失效。刷新不会自动重试。</p></>}
    {(record.status === "RUNNING" || busy) && <div className="notice"><p>运行记录保存在本地，离开页面后可从“资料与笔记”回来查看。</p><button className="button secondary" onClick={() => {void request(`${base}/${id}/cancel`,{method:"POST"}).then(resource.refresh).catch(resource.refresh);}}>取消本次解读</button></div>}
    {(record.status === "FAILED" || record.status === "CANCELLED") && <p className="notice warning">不会自动重试。调用可能已消耗用量，请核对后再从原页面创建新预览。</p>}
    {record.result && <><p className="analysis-summary">{record.result.summary}</p>{record.result.differences.map((item,index) => <article key={index}><h3>{item.title}</h3><p>{item.explanation}</p><small>依据：{item.evidence_ids.join("、") || "未引用产品证据"}</small></article>)}{([['unknowns','未知项'],['risks','需要注意'],['questions_for_human_review','待人工核对']] as const).map(([key,label]) => <div key={key}><h3>{label}</h3><ul>{record.result?.[key].map((text,index) => <li key={index}>{text}</li>)}</ul></div>)}<p className="hint">计算引用：{record.result.calculation_refs.join("、") || "无"}。AI 草稿不会修改保单、计算或任何事实核验状态。</p></>}
    {record.status === "DRAFT" && <div className="form-actions"><button className="button secondary" disabled={busy} onClick={() => mutate("status",{status:"REJECTED"},"PATCH")}>拒绝草稿</button><button className="button primary" disabled={busy} onClick={() => mutate("status",{status:"ACCEPTED_AS_NOTE"},"PATCH")}>仅接受为笔记</button></div>}
    <Link className="text-link" href={record.scope === "POLICY" ? `/policies/${record.target_id}` : `/retirement/${record.target_id}?snapshot=${record.snapshot_id ?? ""}`}>查看这份解读的原始上下文 →</Link>
  </Card>;
}

export function ExplanationPanel({scope,targetId,snapshotId,productId}: {scope:"POLICY"|"RETIREMENT";targetId:string;snapshotId?:string;productId?:string|null}) {
  const [id,setId] = useState<string|null>(null); const [selected,setSelected] = useState<string[]>([]);
  const [product,setProduct] = useState<ProductDetail|null>(null);
  const {busy,error,run} = useAction();
  useEffect(() => {
    if(!productId) return;
    const controller = new AbortController();
    request<ProductDetail>(`/api/v1/products/${productId}`,{signal:controller.signal}).then(setProduct).catch(() => setProduct(null));
    return () => controller.abort();
  },[productId]);
  const evidence = [...new Map((product?.facts.flatMap(f => f.evidence) ?? []).map(e => [e.id,e])).values()];
  return <><Card><h2>{scope === "POLICY" ? "帮助我理解关联条款" : "帮助我理解这次养老计算"}</h2><p>先在本地生成外发预览。预览本身不会调用 AI，结果需要你审阅后才能保存为笔记。</p>
    {scope === "POLICY" && !productId && <p>先编辑保单并关联已核验产品。私人附件和备注不直接进入 AI 外发流程。</p>}
    {evidence.length > 12 && <details><summary>选择要解释的条款（已选 {selected.length}/12）</summary>{evidence.map(e => <label className="evidence-option" key={e.id}><input type="checkbox" checked={selected.includes(e.id)} disabled={!selected.includes(e.id) && selected.length >= 12} onChange={event => setSelected(current => event.target.checked ? [...current,e.id] : current.filter(value => value !== e.id))} /><span>{e.excerpt}</span></label>)}</details>}
    {error && <ErrorPanel message={error} />}
    <button className="button secondary" disabled={busy || (scope === "POLICY" ? !productId || (evidence.length > 12 && !selected.length) : !snapshotId)} onClick={() => void run(async () => {const preview = await request<Explanation>(`${base}/preview`,jsonBody({scope,target_id:targetId,snapshot_id:snapshotId ?? null,...(evidence.length > 12 ? {evidence_ids:selected} : {})}));setId(preview.id);})}>生成解读外发预览</button>
  </Card>{id && <ExplanationRecord key={id} id={id} />}</>;
}
