import type { Plan } from "../../features/retirement/types";
import { Card,StatusBadge } from "@policylens/ui";
import { ArrowUpRight,Plus,Users } from "lucide-react";
import { Link } from "../../app/router";
import { ResourceState } from "../../components/feedback/ResourceState";
import { TaskList } from "../../features/reminders/TaskList";
import { useResource } from "../../hooks/useResource";
import { amount,lines } from "../../lib/labels";
import { familyBase,type Summary } from "../../services/household";

export function HomePage() {
  const resource = useResource<Summary>(`${familyBase}/summary`);
  const planning = useResource<Plan[]>(`${familyBase}/retirement`);
  const data = resource.data;
  const policies = data?.policies.filter(p => p.status !== "ARCHIVED") ?? [];
  const members = data?.members.filter(member => !member.archived) ?? [];
  const openTasks = data?.tasks.filter(task => task.status === "OPEN") ?? [];
  const urgent = openTasks.filter(task => task.kind !== "INFORMATION");
  return <>
    <div className="home-heading"><div><span className="eyebrow">POLICYLENS · 家庭保险档案</span><h1>把家人的保障，放在心上。</h1><p>从记下已有保险开始，让每一次整理都有下一步。</p></div><Link className="button primary" href="/policies/new"><Plus size={18} />添加保单</Link></div>
    <ResourceState error={resource.error} loading={!data} retry={resource.refresh}>{data && <>
      <Card className="household-hero"><div><span className="eyebrow">我的家庭 · {data.as_of}</span><h2>{policies.length ? `已记录 ${members.length} 位家人、${policies.length} 份保单` : "先记一份保险，不必一次弄懂所有条款"}</h2><p>{policies.length ? "以下内容基于已登记资料，未知信息会单独提示。" : "只有保险名称也可以保存。资料留在本地，之后再逐步补充。"}</p>{!policies.length && <div className="inline-actions"><Link href="/policies/new" className="button primary">记下第一份保单 <ArrowUpRight size={18} /></Link><Link href="/family" className="text-link">先添加家人</Link></div>}</div><div className="hero-mark"><Users size={52} /></div></Card>
      <div className="home-metrics"><Link href="/family"><small>家人的保险</small><strong>{policies.length} <span>份已记录</span></strong></Link><Link href="/policies?filter=incomplete"><small>资料完整度</small><strong>{policies.filter(p => p.missing_fields.length > 0).length} <span>份待完善</span></strong></Link><Link href="/tasks"><small>需要处理</small><strong>{urgent.length} <span>项登记事项</span></strong></Link><Link href="/retirement"><small>养老规划</small><strong className="text-metric">{planning.data ? `${planning.data.length} 份目标` : planning.error ? "暂不可读" : "读取目标…"}</strong></Link></div>
      <div className="home-columns"><div>
        <div className="section-heading"><h2>我的家庭</h2><Link href="/family" className="text-link">管理成员 →</Link></div>
        <div className="member-grid">{members.length ? members.map(member => {
          const mine = policies.filter(p => p.person_id === member.id);
          return <Card key={member.id} className="member-card"><div className="card-title"><h3><Link href={`/family/${member.id}`}>{member.nickname}</Link></h3><span className="member-avatar">{member.nickname.slice(0,1)}</span></div><p>{mine.length ? `${mine.length} 份保单已关联` : "尚未关联保单，暂时无法判断保障"}</p><div className="badge-row">{[...new Set(mine.map(p => p.line))].map(line => <StatusBadge tone="info" key={line}>{lines[line]}</StatusBadge>)}</div><Link href={`/family/${member.id}`} className="text-link">查看已有保障 →</Link></Card>;
        }) : <Card className="small-empty"><h3>把保险归到家人名下</h3><p>昵称即可，不需要完整身份资料。</p><Link href="/family" className="button secondary">添加家人</Link></Card>}</div>
        <div className="section-heading"><h2>保单概览</h2><Link href="/policies" className="text-link">全部保单 →</Link></div>
        <Card>{policies.length ? <div className="list">{policies.slice(0,5).map(p => <Link className="policy-link" href={`/policies/${p.id}`} key={p.id}><div><strong>{p.name}</strong><small>{p.member_nickname ?? "归属待确认"} · {lines[p.line]}</small></div><span>{p.missing_fields.length ? "继续完善 →" : "查看详情 →"}</span></Link>)}</div> : <p className="muted">保存第一份保单后，这里会显示你的家庭保险。</p>}</Card>
        <Card className="spaced-card"><h2>{data.year} 年缴费记录</h2>{data.totals.length ? data.totals.map(total => <div className="payment-total" key={total.currency}><span>{total.currency}</span><div><small>本年已缴</small><strong>{amount(total.paid_this_year,total.currency)}</strong></div><div><small>本年登记待缴</small><strong>{amount(total.outstanding_registered,total.currency)}</strong></div></div>) : <p>尚未登记缴费金额。</p>}<p className="muted">{data.policies_without_payments} 份保单尚无缴费记录。各币种独立统计，不默认换算。</p></Card>
      </div><aside>
        <div className="section-heading"><h2>最近需要处理</h2><Link href="/tasks" className="text-link">全部 →</Link></div><Card>{openTasks.length ? <TaskList tasks={[...urgent,...openTasks.filter(t => t.kind === "INFORMATION")].slice(0,3)} refresh={resource.refresh} /> : <p>当前已登记资料没有待处理事项。可以继续核对保单信息。</p>}</Card>
        <Card className="spaced-card retirement-teaser"><span className="eyebrow">为以后做准备</span><h2>你和家人的养老目标</h2><ResourceState error={planning.error} loading={!planning.data} retry={planning.refresh}>{planning.data?.length ? planning.data.slice(0,3).map(plan => <div key={plan.id}><h3><Link href={`/retirement/${plan.id}`}>{plan.name}</Link></h3>{plan.result.status === "READY" ? <p>{plan.retirement_date} · 仅按已登记的确定收入，月度缺口 {amount(plan.result.scenarios[0]?.monthly_gap,plan.currency)}。用户标记的收入尚需核实。</p> : <p>待补充：{plan.result.missing_inputs.join("、")}</p>}</div>) : <p>尚未建立目标。可以先记下自己的长期目标或父母的退休收支。</p>}</ResourceState><Link className="button secondary" href="/retirement">查看养老规划 →</Link></Card>
        <Card className="spaced-card"><h2>读懂保险</h2><p>解释与判断都应有依据。可以从某份保单的条款开始，或查找已保存的比较笔记。</p><Link href="/library" className="text-link">查看资料与笔记 →</Link></Card>
      </aside></div>
      <p className="home-footnote">{data.disclaimer}</p>
    </>}</ResourceState>
  </>;
}
