import { formText } from "../../lib/forms";
import { Card } from "@policylens/ui";
import { useState } from "react";
import { ResourceState } from "../../components/feedback/ResourceState";
import { ErrorPanel,PageHeader } from "../../components/layout/LegacyShared";
import { TaskList } from "../../features/reminders/TaskList";
import { useAction,useResource } from "../../hooks/useResource";
import { familyApi,familyBase,type Task } from "../../services/household";

export function TasksPage() {
  const resource = useResource<Task[]>(`${familyBase}/tasks`);
  const [filter,setFilter] = useState("OPEN"); const [creating,setCreating] = useState(false);
  const {busy,error,run} = useAction();
  const visible = resource.data?.filter(task => filter === "ALL" || task.status === filter) ?? [];
  return <><PageHeader title="家庭待办" subtitle="缴费、期间复查和资料补充。当前提供站内待办，关闭应用后不承诺系统通知。" actions={<button className="button primary" onClick={() => setCreating(!creating)}>添加待办</button>} />
    {creating && <Card><form className="form-grid" onSubmit={event => {event.preventDefault();const form = new FormData(event.currentTarget);void run(async () => {await familyApi.createTask({title:formText(form, "title"),due_date:formText(form, "date") || null});setCreating(false);resource.refresh();});}}><label>需要处理的事<input name="title" required maxLength={160} /></label><label>日期（可不填）<input name="date" type="date" /></label><div className="form-actions"><button className="button primary" disabled={busy}>保存待办</button></div>{error && <ErrorPanel message={error} />}</form></Card>}
    <div className="filter-tabs">{[["OPEN","待处理"],["SNOOZED","已延期"],["DONE","已处理"],["ALL","全部"]].map(([key,label]) => <button className={filter === key ? "selected" : ""} key={key} onClick={() => setFilter(key ?? "OPEN")}>{label}</button>)}</div>
    <ResourceState error={resource.error} loading={!resource.data} retry={resource.refresh}><Card>{visible.length ? <TaskList tasks={visible} refresh={resource.refresh} /> : <div className="small-empty"><h2>当前没有这类事项</h2><p>仅根据已登记资料生成提醒，不代表全部保险都没有需要处理的问题。</p></div>}</Card></ResourceState>
  </>;
}
