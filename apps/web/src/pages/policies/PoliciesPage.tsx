import { formText } from "../../lib/forms";
import { Card,StatusBadge } from "@policylens/ui";
import { Archive,Plus } from "lucide-react";
import { Link,navigate } from "../../app/router";
import { ResourceState } from "../../components/feedback/ResourceState";
import { PageHeader } from "../../components/layout/LegacyShared";
import { PolicyEditor } from "../../features/policies/PolicyEditor";
import { useResource } from "../../hooks/useResource";
import { coverageStates,lines } from "../../lib/labels";
import { familyBase,type Summary } from "../../services/household";

export function PoliciesPage({ creating = false, query }: { creating?: boolean; query: URLSearchParams }) {
  const resource = useResource<Summary>(`${familyBase}/summary`);
  const filter = query.get("filter") ?? "all";
  const search = query.get("q") ?? "";
  const list = resource.data?.policies.filter(policy => {
    if(search && !`${policy.name} ${policy.member_nickname ?? ""} ${policy.insurer}`.toLowerCase().includes(search.toLowerCase())) return false;
    if(filter === "unassigned") return !policy.person_id;
    if(filter === "incomplete") return policy.missing_fields.length > 0 && policy.status !== "ARCHIVED";
    if(filter === "active") return policy.coverage_state === "IN_PERIOD";
    if(filter === "archived") return policy.status === "ARCHIVED";
    return true;
  }) ?? [];
  return <>
    <PageHeader title={creating ? "记下已有保险" : "我的保单"} subtitle={creating ? "先记下你知道的信息，条款与资料可以以后补充。" : "按家人查找已有保险，管理保障期间和每一笔缴费。"} actions={!creating && <Link className="button primary" href="/policies/new"><Plus size={18} />添加保单</Link>} />
    <ResourceState error={resource.error} loading={!resource.data} retry={resource.refresh}>
      {creating ? resource.data && <Card><PolicyEditor {...(query.get("member") ? {memberId:query.get("member")!} : {})} members={resource.data.members} saved={policy => navigate(`/policies/${policy.id}?created=1`,true)} cancel={() => navigate("/policies",true)} /></Card> : <>
        <div className="filter-bar"><nav className="filter-tabs">{[["all","全部"],["incomplete","待完善"],["active","登记期间内"],["unassigned","归属待确认"],["archived","已归档"]].map(([key,text]) => <Link className={key === filter ? "selected" : ""} href={`/policies?filter=${key ?? "all"}`} key={key}>{text}</Link>)}</nav>
          <form onSubmit={event => {event.preventDefault();const value = formText(new FormData(event.currentTarget), "q");navigate(`/policies?filter=${filter}&q=${encodeURIComponent(value)}`);}}><input name="q" aria-label="查找保单" placeholder="保险名称、成员或公司" defaultValue={search} /><button className="button secondary">查找</button></form></div>
        {!!search && <div className="member-grid">{resource.data?.members.filter(member => member.nickname.toLowerCase().includes(search.toLowerCase())).map(member => <Card key={member.id}><h2><Link href={`/family/${member.id}`}>{member.nickname}</Link></h2><p>{member.policy_count} 份关联保单 · {member.policy_count ? "查看成员档案" : "尚未关联，不代表没有保障"}</p></Card>)}</div>}{!list.length ? <Card className="small-empty"><Archive /><h2>还没有符合条件的保单</h2><p>可以先记一笔，暂时没有合同或产品资料也没关系。</p><Link href="/policies/new" className="button primary">记下第一份保单</Link></Card> : <div className="policy-grid">{list.map(policy => <Card key={policy.id} className="policy-card"><div className="card-title"><span className="eyebrow">{policy.member_nickname ?? "归属待确认"} · {lines[policy.line]}</span><StatusBadge tone={policy.coverage_state === "IN_PERIOD" ? "info" : "neutral"}>{coverageStates[policy.coverage_state]}</StatusBadge></div><h2><Link href={`/policies/${policy.id}`}>{policy.name}</Link></h2><p>{policy.insurer || "保险公司待补充"}</p><p>{policy.start_date ?? "生效日待补充"} — {policy.lifetime ? "终身（用户登记）" : policy.end_date ?? "终止日待补充"}</p><div className="card-footer"><span>{policy.missing_fields.length ? `${policy.missing_fields.length} 项待完善` : "查看条款与依据"}</span><Link href={`/policies/${policy.id}`} className="text-link">查看保单 →</Link></div></Card>)}</div>}
      </>}
    </ResourceState>
  </>;
}
