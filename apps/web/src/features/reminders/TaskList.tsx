import { formText } from "../../lib/forms";
import { useState } from "react";
import { Link } from "../../app/router";
import { ErrorPanel } from "../../components/layout/LegacyShared";
import { useAction } from "../../hooks/useResource";
import { today } from "../../lib/labels";
import { familyApi,type Task } from "../../services/household";

export function TaskList({ tasks, refresh }: { tasks: Task[]; refresh: () => void }) {
  const {busy,error,run} = useAction();
  const [snoozing,setSnoozing] = useState<string | null>(null);
  return <>{error && <ErrorPanel message={error} />}<div className="task-list">{tasks.map(task => <article className="task-item" key={task.id}>
    <div className={`task-mark ${task.kind === "INFORMATION" ? "information" : ""}`} />
    <div className="task-body"><strong>{task.title}</strong><small>{task.due_date ? `${task.due_date} ${task.due_date < today() ? "· 已过登记日期" : ""}` : "资料待补充，无截止日期"}{task.status === "DONE" ? " · 已处理" : task.status === "SNOOZED" ? ` · 延至 ${task.snoozed_until}` : ""}</small><p>{task.reason}</p>
      <div className="inline-actions"><Link className="text-link" href={task.href}>{task.kind === "PAYMENT" ? "登记实缴情况" : task.kind === "INFORMATION" ? "补充资料" : "查看相关记录"}</Link>
        {task.status !== "DONE" ? <>{task.kind !== "PAYMENT" && <button className="link-button" disabled={busy} onClick={() => void run(async () => {await familyApi.task(task,{status:"DONE",snoozed_until:null});refresh();})}>标记已处理</button>}<button className="link-button" disabled={busy} onClick={() => setSnoozing(task.id)}>稍后处理</button></> : <button className="link-button" disabled={busy} onClick={() => void run(async () => {await familyApi.task(task,{status:"OPEN",snoozed_until:null});refresh();})}>重新打开</button>}
      </div>
      {snoozing === task.id && <form className="inline-actions" onSubmit={event => {event.preventDefault();const until = formText(new FormData(event.currentTarget), "until");void run(async () => {await familyApi.task(task,{status:"SNOOZED",snoozed_until:until});setSnoozing(null);refresh();});}}><label>延期至<input type="date" name="until" required min={today()} /></label><button className="button secondary" disabled={busy}>保存延期</button></form>}
    </div>
  </article>)}</div></>;
}
