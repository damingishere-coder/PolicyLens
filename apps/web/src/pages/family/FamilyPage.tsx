import { Card,StatusBadge } from "@policylens/ui";
import { Plus,Users } from "lucide-react";
import { useState } from "react";
import { Link } from "../../app/router";
import { ResourceState } from "../../components/feedback/ResourceState";
import { PageHeader } from "../../components/layout/LegacyShared";
import { MemberEditor } from "../../features/members/MemberEditor";
import { useResource } from "../../hooks/useResource";
import { lines,relations } from "../../lib/labels";
import { familyBase,type Member,type Summary } from "../../services/household";

export function FamilyPage({ id }: { id?: string }) {
  const resource = useResource<Summary>(`${familyBase}/summary`);
  const [editor,setEditor] = useState<Member | "new" | null>(null);
  const members = resource.data?.members.filter(member => !id || member.id === id) ?? [];
  return <>
    <PageHeader title={id ? "成员保障档案" : "我的家庭"} subtitle="把保险归到具体家人名下，再逐步看清已有保障。" actions={<button className="button primary" disabled={!!editor} onClick={() => setEditor("new")}><Plus size={18} />添加家人</button>} />
    {id && <Link className="back" href="/family">← 所有家人</Link>}
    {editor && <Card><MemberEditor {...(editor === "new" ? {} : {member: editor})} saved={() => {setEditor(null);resource.refresh();}} cancel={() => setEditor(null)} /></Card>}
    <ResourceState error={resource.error} loading={!resource.data} retry={resource.refresh}>
      {!members.length && <Card className="small-empty"><Users /><h2>{id ? "未找到这位成员" : "先从你和家人开始"}</h2><p>添加昵称即可，也可以先记保单，再关联成员。</p><Link href="/policies/new" className="button secondary">先记一份保单</Link></Card>}
      <div className="member-grid">{members.map(member => {
        const policies = resource.data?.policies.filter(p => p.person_id === member.id && p.status !== "ARCHIVED") ?? [];
        return <Card key={member.id} className="member-card"><div className="card-title"><div><span className="eyebrow">{relations[member.relationship]} {member.archived ? " · 已归档" : ""}</span><h2><Link href={`/family/${member.id}`}>{member.nickname}</Link></h2></div><span className="member-avatar">{member.nickname.slice(0,1)}</span></div>
          <p>{member.age == null ? "年龄尚未填写" : `${member.age} 岁 · 参考日期 ${member.age_as_of}`}</p>
          <div className="badge-row">{[...new Set(policies.map(p => p.line))].map(line => <StatusBadge tone="info" key={line}>{lines[line]}</StatusBadge>)}</div>
          {!policies.length ? <p className="muted">尚未关联保单，暂时无法判断保障。</p> : <div className="list">{policies.map(p => <Link className="policy-link" href={`/policies/${p.id}`} key={p.id}><strong>{p.name}</strong><small>{p.missing_fields.length ? `${p.missing_fields.length} 项信息待完善` : "查看保障与依据"}</small></Link>)}</div>}
          {!!member.possible_duplicate_ids.length && <div className="notice warning">存在同昵称成员。请核对保单归属；系统保留各自记录，不会自动合并。</div>}
          <div className="inline-actions"><Link className="button primary" href={`/policies/new?member=${member.id}`}>为这位家人记保单</Link><button className="button secondary" disabled={!!editor} onClick={() => setEditor(member)}>编辑成员</button></div>
        </Card>;
      })}</div>
      {!!resource.data?.policies.some(p => !p.person_id) && <div className="notice warning">有保单尚未关联成员。<Link href="/policies?filter=unassigned">核对归属</Link></div>}
    </ResourceState>
  </>;
}
