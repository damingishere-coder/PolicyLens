import { ExplanationPanel } from "../../features/ai/ExplanationPanel";
import { useState } from "react";
import { Card, StatusBadge } from "@policylens/ui";
import { Link, navigate } from "../../app/router";
import { PageHeader, ErrorPanel } from "../../components/layout/LegacyShared";
import { ResourceState } from "../../components/feedback/ResourceState";
import { RetirementEditor } from "../../features/retirement/RetirementEditor";
import { RetirementResult } from "../../features/retirement/RetirementResult";
import { type Plan, type Snapshot, type Calculation } from "../../features/retirement/types";
import { useResource, useAction } from "../../hooks/useResource";
import { familyBase, type Member } from "../../services/household";
import { request, downloadBlob } from "../../services/http";

function PlanDetail({id,snapshotId}: {id:string;snapshotId:string | null}) {
  const resource = useResource<Plan>(`${familyBase}/retirement/${id}`);
  const snapshots = useResource<Snapshot[]>(`${familyBase}/retirement/${id}/snapshots`);
  const [editing,setEditing] = useState(false); const [message,setMessage] = useState("");
  const {busy,error,run} = useAction();
  const plan=resource.data; const selected=snapshots.data?.find(s => s.id === snapshotId); const currentSnapshot=snapshots.data?.find(s => s.result.input_hash === plan?.result.input_hash);
  return <><Link href="/retirement" className="back">← 所有养老目标</Link><ResourceState error={resource.error} loading={!plan} retry={resource.refresh}>{plan && <>
    <PageHeader title={plan.name} subtitle="分别保存每次参数与结果，可以回来继续调整。" actions={<button className="button primary" onClick={() => setEditing(true)}>调整参数</button>} />
    {editing ? <Card><RetirementEditor plan={plan} saved={() => {setEditing(false);resource.refresh();snapshots.refresh();}} cancel={() => setEditing(false)} /></Card> : <>
      {snapshotId && !selected ? <ResourceState error={snapshots.error} loading={!snapshots.data} retry={snapshots.refresh}><p>没有找到这个历史版本。<Link href={`/retirement/${id}`}>查看当前目标</Link></p></ResourceState> : <>
        {selected && <div className="notice">正在查看 {new Date(selected.created_at).toLocaleString("zh-CN")} 的历史参数。<Link href={`/retirement/${id}`}>返回当前版本</Link></div>}
        <RetirementResult result={selected?.result ?? plan.result} />{(selected?.result ?? plan.result).status === "READY" && <ExplanationPanel key={selected?.id ?? currentSnapshot?.id} scope="RETIREMENT" targetId={id} {...((selected?.id ?? currentSnapshot?.id) ? {snapshotId:selected?.id ?? currentSnapshot?.id ?? ""} : {})} />}
        <Card><h2>这次输入的收入与假设</h2><div className="list">{(selected?.inputs.incomes ?? plan.incomes).map((income,index) => <div className="list-row" key={index}><div><strong>{income.label}</strong><span>{income.source_note || "依据尚未填写"}</span></div><span>{income.monthly_amount ?? "金额待补充"} {selected?.inputs.currency ?? plan.currency}</span></div>)}</div><p className="preserve-text">{selected?.inputs.notes ?? plan.notes}</p><button className="button secondary" onClick={() => downloadBlob(new Blob([JSON.stringify(selected ?? currentSnapshot ?? {inputs:{name:plan.name,person_id:plan.person_id,retirement_date:plan.retirement_date,currency:plan.currency,monthly_expense:plan.monthly_expense,incomes:plan.incomes,income_inventory_complete:plan.income_inventory_complete,notes:plan.notes},result:plan.result},null,2)],{type:"application/json"}),"PolicyLens-retirement-local.json")}>下载本地参数与结果</button></Card>
      </>}
      {error && <ErrorPanel message={error} />}{message && <div className="notice success">{message}</div>}
      <Card><h2>历史计算版本</h2><ResourceState error={snapshots.error} loading={!snapshots.data} retry={snapshots.refresh}><div className="list">{snapshots.data?.map(snapshot => <div className="list-row" key={snapshot.id}><Link href={`/retirement/${id}?snapshot=${snapshot.id}`}><strong>{new Date(snapshot.created_at).toLocaleString("zh-CN")}</strong><span>{snapshot.result.status === "READY" ? "已计算" : "待补充输入"} · {snapshot.inputs.name}</span></Link><button className="button secondary" disabled={busy} onClick={() => void run(async () => {await request<Calculation>(`${familyBase}/retirement/${id}/snapshots/${snapshot.id}/reproduce`,{method:"POST"});setMessage("已按该版本保存的参数复算，结果与历史快照一致。");})}>复算此版本</button></div>)}</div></ResourceState></Card>
    </>}
  </>}</ResourceState></>;
}

export function RetirementPage({id,query}: {id?:string;query:URLSearchParams}) {
  const resource = useResource<Plan[]>(`${familyBase}/retirement`);
  const members = useResource<Member[]>(`${familyBase}/members`);
  if(id && id !== "new") return <PlanDetail id={id} snapshotId={query.get("snapshot")} />;
  return <><PageHeader title="养老规划" subtitle="先整理你和家人的目标与收支，再决定哪些资料值得进一步研究。" actions={id !== "new" && <Link href="/retirement/new" className="button primary">建立养老目标</Link>} />
    {id === "new" ? <Card><RetirementEditor saved={plan => navigate(`/retirement/${plan.id}`,true)} cancel={() => navigate("/retirement",true)} /></Card> : <ResourceState error={resource.error} loading={!resource.data} retry={resource.refresh}>
      {!resource.data?.length ? <Card className="small-empty"><h2>为自己，也为父母留一份计划</h2><p>目标与不确定的参数都可以先保存。这里不会默认推荐保险产品。</p><Link className="button primary" href="/retirement/new">建立第一份目标</Link></Card> : <div className="policy-grid">{resource.data.map(plan => <Card key={plan.id}><div className="card-title"><span className="eyebrow">{members.data?.find(member => member.id === plan.person_id)?.nickname ?? "规划对象待确认"}</span><StatusBadge tone={plan.result.status === "READY" ? "info" : "warning"}>{plan.result.status === "READY" ? "已有情景结果" : "输入待补充"}</StatusBadge></div><h2><Link href={`/retirement/${plan.id}`}>{plan.name}</Link></h2><p>{plan.retirement_date ?? "参考时点待填写"} · {plan.currency}</p>{plan.result.status === "INCOMPLETE" && <p className="muted">待补充：{plan.result.missing_inputs.join("、")}</p>}<Link href={`/retirement/${plan.id}`} className="text-link">继续这份规划 →</Link></Card>)}</div>}
    </ResourceState>}
  </>;
}
