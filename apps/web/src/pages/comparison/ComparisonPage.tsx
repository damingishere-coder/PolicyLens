import type { components } from "@policylens/contracts/generated";
import { Card } from "@policylens/ui";
import { useState, type FormEvent } from "react";
import { Link, navigate, useDraftGuard } from "../../app/router";
import { ResourceState } from "../../components/feedback/ResourceState";
import { ErrorPanel, PageHeader } from "../../components/layout/LegacyShared";
import { ComparisonPage as EvidenceComparisonPage } from "../../features/comparison/EvidenceComparisonPage";
import type { ProductSummary } from "../../features/research/types";
import { useAction, useResource } from "../../hooks/useResource";
import { formText } from "../../lib/forms";
import { familyBase, type Member } from "../../services/household";
import { jsonBody, request } from "../../services/http";

type Comparison = Required<components["schemas"]["FamilyComparisonView"]>;
type Input = components["schemas"]["FamilyComparisonInput"];

function ComparisonDetail({id,openProduct}: {id:string;openProduct:(id:string)=>void}) {
  const resource=useResource<Comparison>(`${familyBase}/comparisons/${id}`);
  const data=resource.data;
  return <><Link href="/compare" className="back">← 所有比较</Link><ResourceState error={resource.error} loading={!data} retry={resource.refresh}>{data && <>
    <PageHeader title={data.inputs.purpose} subtitle={`保存于 ${new Date(data.created_at).toLocaleString("zh-CN")} · 条件与结果按当次版本保留`} actions={<Link className="button secondary" href={`/compare?from=${id}`}>复制条件开始新比较</Link>} />
    {data.stale && <div className="notice warning">关联产品资料已经变化。下面是历史快照；重新比较前请核对最新条款。</div>}
    <Card><h2>这次比较的条件</h2><div className="summary-strip"><p>年龄：{data.inputs.age ?? "待确认"}</p><p>地区：{data.inputs.jurisdiction === "HK" ? "香港" : data.inputs.jurisdiction === "CN_MAINLAND" ? "中国内地" : "待确认"}</p><p>年度预算：{data.inputs.annual_budget ?? "待确认"} {data.inputs.currency ?? "币种待确认"}</p><p>缴费期：{data.inputs.payment_term || "待确认"}</p><p>保障／领取期：{data.inputs.benefit_term || "待确认"}</p></div></Card>
    {!!data.blockers.length && <Card><h2>暂不能直接比较的项目</h2><ul>{data.blockers.map(text => <li key={text}>{text}</li>)}</ul></Card>}
    <Card><h2>主要条款与差异</h2><p>没有给出适合度排名。相同字段值也可能带有不同适用条件，请查看证据。</p><div className="table-scroll"><table><thead><tr><th>比较项目</th>{data.product_names.map((name,index) => <th key={index}>{name}</th>)}</tr></thead><tbody>{data.differences.map(row => <tr key={row.field}><th>{row.label}</th>{row.cells.map(cell => <td key={cell.product_version_id}><strong>{cell.value ?? "资料未知"}</strong><small>{cell.verification_status === "VERIFIED" ? "已核验" : "待核实"} · {cell.guarantee_type === "GUARANTEED" ? "保证" : cell.guarantee_type === "NON_GUARANTEED" ? "非保证" : "保证属性待确认"}</small><small>{cell.evidence_ids.length} 条证据</small><button className="link-button" onClick={() => openProduct(cell.product_version_id)}>核对原文依据</button></td>)}</tr>)}</tbody></table></div>{!data.differences.length && <p>当前缺少可对照的关键字段，请先补充产品资料。</p>}</Card>
    <Card><h2>还需要确认</h2><ul>{data.questions.map(text => <li key={text}>{text}</li>)}</ul><details><summary>快照与计算版本</summary><p>{data.algorithm_version}</p><code>{data.input_hash}</code></details></Card>
    <details className="card"><summary>展开完整证据矩阵与两产品 AI 差异解读</summary><p>此处读取关联产品的当前资料。若上方历史快照已过期，请先重新比较。</p>{data.stale ? <p>历史资料已变化，请创建新的比较快照。</p> : <EvidenceComparisonPage key={id} initialIds={data.inputs.product_version_ids} fixedSelection openProduct={openProduct} />}</details>
  </>}</ResourceState></>;
}

function ComparisonEditor({initial,openProduct}: {initial?:Input;openProduct:(id:string)=>void}) {
  const products=useResource<ProductSummary[]>("/api/v1/products?include_drafts=false");
  const members=useResource<Member[]>(`${familyBase}/members`);
  const [personId,setPersonId]=useState(initial?.person_id ?? "");
  const [selected,setSelected]=useState<string[]>(initial?.product_version_ids ?? []);
  const [dirty,setDirty]=useState(false); useDraftGuard(dirty);
  const {busy,error,run}=useAction();
  const save=(event:FormEvent<HTMLFormElement>) => {event.preventDefault();const form=new FormData(event.currentTarget);const text=(key:string)=>formText(form,key);const input:Input={purpose:text("purpose"),person_id:text("person") || null,age:text("age") ? Number(text("age")) : null,jurisdiction:(text("jurisdiction") || null) as Exclude<Input["jurisdiction"],undefined>,currency:(text("currency") || null),annual_budget:text("budget") || null,payment_term:text("payment"),benefit_term:text("benefit"),product_version_ids:selected};void run(async () => {const result=await request<Comparison>(`${familyBase}/comparisons`,jsonBody(input));setDirty(false);navigate(`/compare/${result.id}`,true);});};
  return <Card><h2>先明确你想解决的问题</h2><form onSubmit={save} onChange={() => setDirty(true)}><div className="form-grid">
    <label className="full-row">这次比较的目的<input required name="purpose" maxLength={160} defaultValue={initial?.purpose ?? ""} placeholder="例如：了解妈妈两份医疗保障的续保差异" /></label>
    <label>为谁比较<select name="person" value={personId} onChange={event => setPersonId(event.target.value)}><option value="">暂未明确</option>{personId && !members.data && <option value={personId}>保留原有关联</option>}{members.data?.map(m => <option key={m.id} value={m.id}>{m.nickname}</option>)}</select></label>
    <label>按多少岁比较<input name="age" type="number" min={0} max={130} defaultValue={initial?.age ?? ""} /></label>
    <label>适用地区<select name="jurisdiction" defaultValue={initial?.jurisdiction ?? ""}><option value="">待确认</option><option value="CN_MAINLAND">中国内地</option><option value="HK">香港</option></select></label>
    <label>预算币种<select name="currency" defaultValue={initial?.currency ?? ""}><option value="">待确认</option>{["CNY","HKD","USD"].map(c => <option key={c}>{c}</option>)}</select></label>
    <label>年度预算<input name="budget" type="number" min={0} step="0.01" defaultValue={initial?.annual_budget ?? ""} /></label>
    <label>目标缴费期<input name="payment" maxLength={100} defaultValue={initial?.payment_term ?? ""} /></label><label>目标保障／领取期<input name="benefit" maxLength={100} defaultValue={initial?.benefit_term ?? ""} /></label>
  </div><h3>选择 2–4 个已核验备选</h3><ResourceState error={products.error} loading={!products.data} retry={products.refresh}><div className="product-picker">{products.data?.map(p => <label className="comparison-choice" key={p.version_id}><input type="checkbox" checked={selected.includes(p.version_id)} disabled={busy || (!selected.includes(p.version_id) && selected.length >= 4)} onChange={e => setSelected(current => e.target.checked ? [...current,p.version_id] : current.filter(id => id !== p.version_id))} /><span>{p.display_name} · {p.currency}</span><button type="button" className="link-button" onClick={() => openProduct(p.version_id)}>查看资料</button></label>)}</div>{!products.data?.length && <p>还没有已核验备选。可先整理已有产品资料，或按需使用高级研究。家庭建档无需等待产品库。</p>}</ResourceState>{error && <ErrorPanel message={error} />}<p className="hint">未知条件可以暂时保留，结果会标出待核实问题。不会把预算或年龄直接推断为适合投保。</p><button className="button primary" disabled={busy || selected.length < 2}>保存条件并查看差异</button></form></Card>;
}

function CopyEditor({id,openProduct}: {id:string;openProduct:(id:string)=>void}) {
  const resource=useResource<Comparison>(`${familyBase}/comparisons/${id}`);
  return <ResourceState error={resource.error} loading={!resource.data} retry={resource.refresh}>{resource.data && <ComparisonEditor initial={resource.data.inputs} openProduct={openProduct} />}</ResourceState>;
}

export function ComparisonPage({id,query,openProduct}: {id?:string;query:URLSearchParams;openProduct:(id:string)=>void}) {
  const records=useResource<Comparison[]>(`${familyBase}/comparisons`);
  if(id) return <ComparisonDetail id={id} openProduct={openProduct} />;
  return <><PageHeader title="挑选与比较" subtitle="从家庭需要出发，保存比较条件，逐项理解差异与限制。" /><div className="section-heading"><Link className="button secondary" href="/imports">整理备选产品资料</Link><Link href="/evidence-search">查找本地产品与证据</Link><Link href="/research">高级：香港储蓄／年金研究 →</Link></div>{query.get("from") ? <CopyEditor id={query.get("from")!} openProduct={openProduct} /> : <ComparisonEditor openProduct={openProduct} />}<Card><h2>继续已有比较</h2><ResourceState error={records.error} loading={!records.data} retry={records.refresh}>{records.data?.length ? records.data.map(r => <Link className="policy-link" href={`/compare/${r.id}`} key={r.id}><div><strong>{r.inputs.purpose}</strong><small>{r.product_names.join(" / ")}</small></div><span>{r.stale ? "资料已更新，待复查" : "查看快照 →"}</span></Link>) : <p>暂无比较记录，保存后可以随时回来继续。</p>}</ResourceState></Card><details className="card"><summary>直接使用完整证据比较工具</summary><EvidenceComparisonPage openProduct={openProduct} /></details></>;
}
