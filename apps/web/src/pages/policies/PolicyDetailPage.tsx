import { ExplanationPanel } from "../../features/ai/ExplanationPanel";
import { Card,StatusBadge } from "@policylens/ui";
import { useState } from "react";
import { Link } from "../../app/router";
import { ResourceState } from "../../components/feedback/ResourceState";
import { PageHeader } from "../../components/layout/LegacyShared";
import { PaymentEditor } from "../../features/policies/PaymentEditor";
import { PolicyEditor } from "../../features/policies/PolicyEditor";
import { useResource } from "../../hooks/useResource";
import { amount,coverageStates,frequencies,lines } from "../../lib/labels";
import { familyBase,type HistoryEntry,type Member,type Payment,type Policy } from "../../services/household";

export function PolicyDetailPage({ id, created }: { id: string; created: boolean }) {
  const resource = useResource<Policy>(`${familyBase}/policies/${encodeURIComponent(id)}`);
  const members = useResource<Member[]>(`${familyBase}/members`);
  const history = useResource<HistoryEntry[]>(`${familyBase}/policies/${encodeURIComponent(id)}/history`);
  const [editing,setEditing] = useState(false);
  const [payment,setPayment] = useState<Payment | "new" | null>(null);
  const p = resource.data;
  const refresh = () => {resource.refresh();history.refresh();};
  return <><Link href="/policies" className="back">← 我的保单</Link>
    <ResourceState error={resource.error} loading={!p} retry={resource.refresh}>{p && <>
      <PageHeader title={p.name} subtitle={`${p.member_nickname ?? "归属待确认"} · ${lines[p.line]} · ${p.insurer || "保险公司待补充"}`} actions={<button className="button secondary" onClick={() => setEditing(true)}>编辑保单</button>} />
      {created && <div className="notice success">已记下这份保单。补充保障期间后，可以帮助你查看到期事项。</div>}
      {editing ? <Card><ResourceState error={members.error} loading={!members.data} retry={members.refresh}>{members.data && <PolicyEditor policy={p} members={members.data} saved={() => {setEditing(false);refresh();}} cancel={() => setEditing(false)} />}</ResourceState></Card> : <>
        <Card className="policy-summary"><div className="card-title"><h2>这份保险的记录</h2><StatusBadge tone="info">{coverageStates[p.coverage_state]}</StatusBadge></div><div className="summary-strip"><div><span>保障期间</span><strong>{p.start_date ?? "待补充"} — {p.lifetime ? "终身" : p.end_date ?? "待补充"}</strong></div><div><span>投保人</span><strong>{members.data?.find(m => m.id === p.owner_id)?.nickname ?? "待确认"}</strong></div><div><span>缴费人</span><strong>{members.data?.find(m => m.id === p.payer_id)?.nickname ?? "待确认"}</strong></div></div><p className="muted">期间状态按你登记的资料判断，不代表保障充分或一定获赔。</p></Card>
        {!!p.missing_fields.length && <div className="notice warning">待补充：{p.missing_fields.join("、")}。缺少资料不代表没有保障。</div>}
        <div className="two-column"><Card><h2>主要保什么</h2><StatusBadge tone="neutral">手工记录 · 待核实</StatusBadge><p className="preserve-text">{p.coverage_summary || "尚未记录保障责任，可以查看条款后逐步补充。"}</p></Card><Card><h2>重要限制与除外</h2><StatusBadge tone="neutral">手工记录 · 待核实</StatusBadge><p className="preserve-text">{p.exclusions || "尚未核实免赔、赔付比例、等待期、医院范围和除外条件。"}</p></Card></div>
        <Card><h2>个人特别约定与备注</h2><p className="preserve-text">{p.personal_terms || "尚未登记个人约定或批单。"}</p>{p.notes && <p className="preserve-text">{p.notes}</p>}<p className="muted">个人记录独立保存，不会被产品库更新覆盖。</p></Card>
        <Card><div className="card-title"><h2>缴费与续保</h2><button className="button primary" disabled={payment !== null} onClick={() => setPayment("new")}>登记缴费</button></div>
          {payment && <PaymentEditor policyId={p.id} {...(payment === "new" ? {} : {payment})} saved={() => {setPayment(null);refresh();}} cancel={() => setPayment(null)} />}
          {!p.premium_records.length ? <p className="muted">尚未登记缴费，不显示默认金额，也不假定已经缴费。</p> : <div className="table-scroll"><table><thead><tr><th>应缴日期</th><th>应缴</th><th>实缴日期</th><th>实缴</th><th>频率</th><th /></tr></thead><tbody>{p.premium_records.map(record => <tr key={record.id}><td>{record.due_date}</td><td>{amount(record.due_amount,record.currency)}</td><td>{record.paid_date ?? "尚未登记"}</td><td>{amount(record.paid_amount,record.currency)}</td><td>{frequencies[record.frequency]}</td><td><button className="link-button" disabled={payment !== null} onClick={() => setPayment(record)}>更新缴费</button></td></tr>)}</tbody></table></div>}
          <p className="hint">续保权利、标准费率、调费规则与实际缴费分别记录；保证续保不表示保费固定。</p>
        </Card>
        <Card><h2>条款与资料依据</h2>{p.product_version_id ? <Link className="button secondary" href={`/products/${p.product_version_id}?returnTo=${encodeURIComponent(`/policies/${p.id}`)}`}>查看关联产品的条款与字段证据</Link> : <p>尚未关联已核验产品。可以先保存自己的资料，以后再核对关联。</p>}<div className="inline-actions"><Link className="button secondary" href={`/library?policy=${p.id}`}>这份保单的资料</Link><Link className="text-link" href="/imports">整理产品条款</Link></div></Card>
        <ExplanationPanel scope="POLICY" targetId={p.id} productId={p.product_version_id} /><Card><h2>变更记录</h2><ResourceState error={history.error} loading={!history.data} retry={history.refresh}><div className="list">{history.data?.map(item => <div key={item.id} className="list-row"><span>{({CREATED:"建立档案",UPDATED:"更新档案",PAYMENT_CREATED:"登记缴费",PAYMENT_UPDATED:"更新缴费"} as Record<string,string>)[item.action] ?? "档案变更"}</span><small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></div>)}</div></ResourceState></Card>
      </>}
    </>}</ResourceState>
  </>;
}
