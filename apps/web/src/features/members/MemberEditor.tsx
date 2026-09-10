import { formText } from "../../lib/forms";
import { useState,type FormEvent } from "react";
import { useDraftGuard } from "../../app/router";
import { ErrorPanel } from "../../components/layout/LegacyShared";
import { useAction } from "../../hooks/useResource";
import { relations,today } from "../../lib/labels";
import { familyApi,type Member,type MemberInput } from "../../services/household";

export function MemberEditor({ member, saved, cancel }: { member?: Member; saved: (value: Member) => void; cancel: () => void }) {
  const [dirty, setDirty] = useState(false);
  const {busy,error,run} = useAction();
  useDraftGuard(dirty);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const age = formText(form, "age");
    const input: MemberInput = { nickname: formText(form, "nickname"), relationship: form.get("relationship") as MemberInput["relationship"], age: age ? Number(age) : null, age_as_of: age ? formText(form, "age_as_of") : null, archived: form.get("archived") === "on" };
    void run(async () => { const value = await familyApi.member(input,member); setDirty(false); saved(value); });
  };
  return <form className="form-grid" onSubmit={submit} onChange={() => setDirty(true)}>
    <h2 className="full-row">{member ? "编辑成员" : "添加家人"}</h2>
    {error && <div className="full-row"><ErrorPanel message={error} /></div>}
    <label>成员昵称<input name="nickname" required maxLength={40} autoFocus defaultValue={member?.nickname ?? ""} placeholder="例如：我、妈妈" /></label>
    <label>与我的关系<select name="relationship" defaultValue={member?.relationship ?? "OTHER"}>{Object.entries(relations).map(([key,text]) => <option key={key} value={key}>{text}</option>)}</select></label>
    <label>年龄（可稍后填写）<input name="age" type="number" min={0} max={130} defaultValue={member?.age ?? ""} /></label>
    <label>年龄参考日期<input name="age_as_of" type="date" defaultValue={member?.age_as_of ?? today()} /></label>
    {member && <label className="check-label"><input type="checkbox" name="archived" defaultChecked={member.archived} />归档成员（保留关联保单）</label>}
    <p className="hint full-row">使用昵称即可。年龄只用于你主动建立的本地规划，同名成员不会自动合并。</p>
    <div className="form-actions"><button className="button secondary" type="button" disabled={busy} onClick={() => { if (!dirty || window.confirm("丢弃尚未保存的成员信息？")) { setDirty(false); cancel(); } }}>取消</button><button className="button primary" disabled={busy}>{busy ? "正在保存…" : "保存成员"}</button></div>
  </form>;
}
