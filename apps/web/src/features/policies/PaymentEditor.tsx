import { formText } from "../../lib/forms";
import { useState,type FormEvent } from "react";
import { useDraftGuard } from "../../app/router";
import { ErrorPanel } from "../../components/layout/LegacyShared";
import { useAction } from "../../hooks/useResource";
import { frequencies,today } from "../../lib/labels";
import { familyApi,type Payment,type PaymentInput } from "../../services/household";

export function PaymentEditor({ policyId, payment, saved, cancel }: { policyId: string; payment?: Payment; saved: () => void; cancel: () => void }) {
  const {busy,error,run} = useAction(); const [dirty,setDirty] = useState(false); useDraftGuard(dirty);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const text = (key: string) => formText(form, key);
    const value: PaymentInput = { due_amount:text("due_amount"), due_date:text("due_date"), paid_amount:text("paid_amount") || null, paid_date:text("paid_date") || null, currency:text("currency"), frequency:text("frequency") as NonNullable<PaymentInput["frequency"]> };
    void run(async () => { await familyApi.payment(policyId,value,payment);setDirty(false);saved(); });
  };
  return <form className="form-grid" onSubmit={submit} onChange={() => setDirty(true)}>
    <h2 className="full-row">{payment ? "更新缴费记录" : "登记一笔缴费"}</h2>
    {error && <div className="full-row"><ErrorPanel message={error} /></div>}
    <label>应缴金额<input name="due_amount" required inputMode="decimal" pattern="\d+(\.\d{1,2})?" defaultValue={payment?.due_amount ?? ""} /></label>
    <label>应缴日期<input name="due_date" type="date" required defaultValue={payment?.due_date ?? ""} /></label>
    <label>币种<select name="currency" defaultValue={payment?.currency ?? "CNY"}><option>CNY</option><option>HKD</option><option>USD</option></select></label>
    <label>本期实缴金额<input name="paid_amount" inputMode="decimal" pattern="\d+(\.\d{1,2})?" defaultValue={payment?.paid_amount ?? ""} placeholder="尚未缴费请留空" /></label>
    <label>实缴日期<input name="paid_date" type="date" max={today()} defaultValue={payment?.paid_date ?? ""} /></label>
    <label>缴费频率<select name="frequency" defaultValue={payment?.frequency ?? "ANNUAL"}>{Object.entries(frequencies).map(([key,text]) => <option key={key} value={key}>{text}</option>)}</select></label>
    <p className="hint full-row">应缴和实缴分别记录。部分缴费请登记本期累计实缴；待缴事项会按差额更新。不会自动创建下一期缴费。</p>
    <div className="form-actions"><button className="button secondary" type="button" disabled={busy} onClick={() => {if(!dirty || window.confirm("丢弃尚未保存的缴费输入？")){setDirty(false);cancel();}}}>取消</button><button className="button primary" disabled={busy}>{busy ? "正在保存…" : "保存缴费记录"}</button></div>
  </form>;
}
