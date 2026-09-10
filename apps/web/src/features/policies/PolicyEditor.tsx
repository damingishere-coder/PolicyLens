import { formText } from "../../lib/forms";
import { useState,type FormEvent } from "react";
import { Link,useDraftGuard } from "../../app/router";
import { ErrorPanel } from "../../components/layout/LegacyShared";
import { useAction,useResource } from "../../hooks/useResource";
import { lines,policyStatuses } from "../../lib/labels";
import { familyApi,type Member,type Policy,type PolicyInput } from "../../services/household";
import type { ProductSummary } from "../research/types";

export function PolicyEditor({ policy, memberId, members, saved, cancel }: { policy?: Policy; memberId?: string; members: Member[]; saved: (value: Policy) => void; cancel: () => void }) {
  const products = useResource<ProductSummary[]>("/api/v1/products?include_drafts=false");
  const [dirty,setDirty] = useState(false);
  const [lifetime,setLifetime] = useState(policy?.lifetime ?? false);
  const [productId,setProductId] = useState(policy?.product_version_id ?? "");
  const {busy,error,run} = useAction(); useDraftGuard(dirty);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const text = (key: string) => formText(form, key).trim();
    const value: PolicyInput = {
      name:text("name"), person_id:text("person_id") || null, product_version_id:text("product_version_id") || null,
      owner_id:text("owner_id") || null, payer_id:text("payer_id") || null,
      insurer:text("insurer"), line:text("line") as NonNullable<PolicyInput["line"]>,
      category:text("category") as NonNullable<PolicyInput["category"]>, status:text("status") as NonNullable<PolicyInput["status"]>,
      start_date:text("start_date") || null, end_date:lifetime ? null : text("end_date") || null, lifetime,
      coverage_summary:text("coverage_summary"), exclusions:text("exclusions"), personal_terms:text("personal_terms"), notes:text("notes"),
    };
    void run(async () => { const result = await familyApi.policy(value,policy); setDirty(false); saved(result); });
  };
  const memberOptions = members.map(member => <option key={member.id} value={member.id}>{member.nickname}{member.archived ? "（已归档）" : ""}</option>);
  return <form className="policy-editor" onSubmit={submit} onChange={() => setDirty(true)}>
    {error && <ErrorPanel message={error} />}
    <div className="form-grid">
      <label>保险名称<input autoFocus name="name" required maxLength={160} defaultValue={policy?.name ?? ""} placeholder="填写你已有保险的名称" /></label>
      <label>被保险成员<select name="person_id" defaultValue={policy?.person_id ?? memberId ?? ""}><option value="">归属待确认</option>{memberOptions}</select></label>
      <label>保险类别<select name="line" defaultValue={policy?.line ?? "UNKNOWN"}>{Object.entries(lines).map(([key,text]) => <option key={key} value={key}>{text}</option>)}</select></label>
    </div>
    <p className="hint">只知道名称也能先保存。其他信息可以稍后补充；保存不会自动确认保障有效或条款已核验。<Link href="/family">管理家人</Link></p>
    <details open={!!policy} className="editor-details"><summary>补充保障期间、缴费角色和重要约定</summary>
      <div className="form-grid">
        <label>保险公司<input name="insurer" maxLength={160} defaultValue={policy?.insurer ?? ""} /></label>
        <label>档案分类<select name="category" defaultValue={policy?.category ?? "UNCONFIRMED"}><option value="UNCONFIRMED">分类待核实</option><option value="CORE">长期核心</option><option value="GROUP">团体福利</option><option value="GIFT">赠送保障</option></select></label>
        <label>保障记录状态<select name="status" defaultValue={policy?.status ?? "DRAFT"}>{Object.entries(policyStatuses).map(([key,text]) => <option key={key} value={key}>{text}</option>)}</select></label>
        <label>生效日期<input name="start_date" type="date" defaultValue={policy?.start_date ?? ""} /></label>
        <label>终止日期<input name="end_date" type="date" disabled={lifetime} defaultValue={policy?.end_date ?? ""} /></label>
        <label className="check-label"><input type="checkbox" checked={lifetime} onChange={event => setLifetime(event.target.checked)} />资料明确为终身保障</label>
        <label>投保人<select name="owner_id" defaultValue={policy?.owner_id ?? ""}><option value="">暂未确认</option>{memberOptions}</select></label>
        <label>缴费人<select name="payer_id" defaultValue={policy?.payer_id ?? ""}><option value="">暂未确认</option>{memberOptions}</select></label>
        <label>关联已核验产品（可留空）<select name="product_version_id" value={productId} onChange={event => setProductId(event.target.value)}><option value="">以后关联条款依据</option>{policy?.product_version_id && !products.data?.some(p => p.version_id === policy.product_version_id) && <option value={policy.product_version_id}>保留原有关联（资料读取中或不可用）</option>}{products.data?.map(product => <option value={product.version_id} key={product.version_id}>{product.display_name} · {product.version_label}</option>)}</select></label>
        {products.error && <p className="hint full-row">产品资料暂时读取失败，不影响先保存家庭档案。请稍后重试关联。</p>}
        <label className="full-row">我记录的保障责任<textarea name="coverage_summary" maxLength={2000} defaultValue={policy?.coverage_summary ?? ""} placeholder="例如保障责任、限额；不了解的内容可以留空" /></label>
        <label className="full-row">重要限制与除外<textarea name="exclusions" maxLength={2000} defaultValue={policy?.exclusions ?? ""} /></label>
        <label className="full-row">个人特别约定／批单<textarea name="personal_terms" maxLength={2000} defaultValue={policy?.personal_terms ?? ""} /></label>
        <label className="full-row">本地备注<textarea name="notes" maxLength={2000} defaultValue={policy?.notes ?? ""} /></label>
      </div>
    </details>
    <div className="form-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => { if(!dirty || window.confirm("丢弃尚未保存的保单输入？")) {setDirty(false);cancel();} }}>取消</button><button className="button primary" disabled={busy}>{busy ? "正在保存…" : policy ? "保存保单修改" : "保存这份保单"}</button></div>
  </form>;
}
