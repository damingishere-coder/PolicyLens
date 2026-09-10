import { formText } from "../../lib/forms";
import { useState, type FormEvent } from "react";
import { useDraftGuard } from "../../app/router";
import { useAction, useResource } from "../../hooks/useResource";
import { familyBase, type Member } from "../../services/household";
import { request, jsonBody } from "../../services/http";
import { ErrorPanel } from "../../components/layout/LegacyShared";
import { incomeKinds, type Income, type Plan, type PlanInput } from "./types";

export function RetirementEditor({ plan, saved, cancel }: { plan?: Plan; saved: (value: Plan) => void; cancel: () => void }) {
  const members = useResource<Member[]>(`${familyBase}/members`);
  const [personId,setPersonId] = useState(plan?.person_id ?? "");
  const [incomes,setIncomes] = useState<Array<Income & { key: string }>>(() => (plan?.incomes ?? []).map(income => ({...income,key:crypto.randomUUID()})));
  const [dirty,setDirty] = useState(false); const {busy,error,run} = useAction(); useDraftGuard(dirty);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const text = (name: string) => formText(form, name).trim();
    const input: PlanInput = {name:text("name"),person_id:text("person_id") || null,retirement_date:text("retirement_date") || null,currency:text("currency"),monthly_expense:text("monthly_expense") || null,income_inventory_complete:form.get("income_complete") === "on",notes:text("notes"),incomes:incomes.map(({label,monthly_amount,kind,source_note}) => ({label,monthly_amount:monthly_amount || null,kind,source_note}))};
    void run(async () => {const result = await request<Plan>(`${familyBase}/retirement${plan ? `/${plan.id}` : ""}`,jsonBody(plan ? {...input,expected_revision:plan.revision} : input,plan ? "PUT" : "POST"));setDirty(false);saved(result);});
  };
  const changeIncome = (key: string, values: Partial<Income>) => {setDirty(true);setIncomes(current => current.map(income => income.key === key ? {...income,...values} : income));};
  return <form className="plan-editor" onSubmit={submit} onChange={() => setDirty(true)}>
    <h2>{plan ? "调整养老目标" : "建立养老目标"}</h2>{error && <ErrorPanel message={error} />}
    <div className="form-grid"><label>目标名称<input name="name" required maxLength={160} defaultValue={plan?.name ?? ""} placeholder="例如：我的长期养老目标" /></label><label>为谁规划<select name="person_id" value={personId} onChange={event => setPersonId(event.target.value)}><option value="">稍后确定</option>{members.data?.map(member => <option key={member.id} value={member.id}>{member.nickname}</option>)}{plan?.person_id && !members.data && <option value={plan.person_id}>保留当前成员</option>}</select></label><label>退休收支参考日期<input name="retirement_date" type="date" defaultValue={plan?.retirement_date ?? ""} /></label><label>统一计算币种<select name="currency" defaultValue={plan?.currency ?? "CNY"}><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>参考时点每月支出预算<input name="monthly_expense" inputMode="decimal" pattern="\d+(\.\d{1,2})?" defaultValue={plan?.monthly_expense ?? ""} placeholder="尚不清楚可留空" /></label></div>
    <p className="hint">每项收入金额均按上方的统一币种填写，切换币种不会自动换算。请填写参考日期时的月度净收支；这里不自动把今天的支出换算为未来购买力。未知金额留空，明确没有收入时才填写零或确认空收入清单。</p>
    <div className="section-heading"><h3>每月预计收入</h3><button type="button" className="button secondary" disabled={incomes.length >= 30} onClick={() => {setDirty(true);setIncomes(current => [...current,{key:crypto.randomUUID(),label:"",monthly_amount:null,kind:"ESTIMATE",source_note:""}]);}}>添加收入来源</button></div>
    {incomes.map((income,index) => <div key={income.key} className="income-row"><span className="income-number">{index+1}</span><label>收入名称<input required maxLength={160} value={income.label} onChange={event => changeIncome(income.key,{label:event.target.value})} /></label><label>月度金额<input inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={income.monthly_amount ?? ""} onChange={event => changeIncome(income.key,{monthly_amount:event.target.value || null})} /></label><label>收入性质<select value={income.kind} onChange={event => changeIncome(income.key,{kind:event.target.value as Income["kind"]})}>{Object.entries(incomeKinds).map(([key,text]) => <option key={key} value={key}>{text}</option>)}</select></label><label>依据或假设<input maxLength={1000} value={income.source_note} placeholder="如来源日期、演示假设" onChange={event => changeIncome(income.key,{source_note:event.target.value})} /></label><button className="link-button" type="button" onClick={() => {setDirty(true);setIncomes(current => current.filter(item => item.key !== income.key));}}>移除</button></div>)}
    <label className="check-label"><input name="income_complete" type="checkbox" defaultChecked={plan?.income_inventory_complete ?? false} />我已登记目前已知的收入来源；清单为空时，表示明确按零收入建立情景。</label>
    <label className="spaced-card">目标说明与假设<textarea name="notes" maxLength={2000} defaultValue={plan?.notes ?? ""} /></label>
    <div className="form-actions"><button className="button secondary" type="button" disabled={busy} onClick={() => {if(!dirty || window.confirm("丢弃尚未保存的养老参数？")){setDirty(false);cancel();}}}>取消</button><button className="button primary" disabled={busy}>{busy ? "正在保存…" : "保存目标并计算"}</button></div>
  </form>;
}
