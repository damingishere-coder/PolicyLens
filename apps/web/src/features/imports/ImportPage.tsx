import { Link } from "../../app/router";
import { Card,StatusBadge } from "@policylens/ui";
import {
BadgeCheck,
Check,
FileCheck2,
FileSearch,
Info,
Plus,
ShieldCheck,
Upload
} from "lucide-react";
import { useCallback,useEffect,useState,type FormEvent } from "react";
import { policyLens } from "../../api";
import { asError,ErrorPanel,fieldLabels,PageHeader } from '../../components/layout/LegacyShared';
import type { ImportView } from '../research/types';
export function ImportPage({ openProduct, initialImportId }: { openProduct: (id: string) => void; initialImportId?: string | null }) {
  const [activeImport, setActiveImport] = useState<ImportView | null>(null);
  const [authority, setAuthority] = useState("CONTRACT_DOCUMENT");
  const [decisions, setDecisions] = useState<Record<string, { decision: string; edited_value?: string }>>({});
  const [manualOpen, setManualOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [published, setPublished] = useState<string | null>(null);
  const setImport = useCallback((value: unknown) => {
    const imported = value as ImportView;
    if ((imported as unknown as { cancelled?: boolean }).cancelled) return;
    setActiveImport(imported);
    setDecisions(Object.fromEntries(imported.candidates.map((item) => [item.id, { decision: "KEEP_UNVERIFIED" }])));
    setPublished(null);
  }, []);
  useEffect(() => {
    if (!initialImportId) return;
    policyLens.getImport(initialImportId).then(setImport).catch((reason) => setError(asError(reason)));
  }, [initialImportId, setImport]);
  const choosePdf = async () => {
    setBusy(true); setError("");
    try { setImport(await policyLens.chooseAndImportPdf(authority)); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const manual = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      setImport(await policyLens.importManual({
        display_name: form.get("display_name"), version_label: form.get("version_label"),
        jurisdiction: form.get("jurisdiction"), line_of_business: form.get("line_of_business"), currency: form.get("currency"),
        annual_premium: form.get("annual_premium"), renewal_mode: form.get("renewal_mode"),
        guarantee_period_years: form.get("guarantee_period_years") ? Number(form.get("guarantee_period_years")) : null, maximum_renewal_age: form.get("maximum_renewal_age") ? Number(form.get("maximum_renewal_age")) : null,
        rate_adjustment_scope: form.get("rate_adjustment_scope"), benefit_limit: form.get("benefit_limit") || null,
        source_authority: form.get("source_authority"), evidence_note: form.get("evidence_note")
      }));
      setManualOpen(false);
    } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const submitReview = async () => {
    if (!activeImport) return;
    setBusy(true); setError("");
    try {
      const result = await policyLens.reviewImport(activeImport.id, { decisions: activeImport.candidates.map((candidate) => ({ candidate_id: candidate.id, ...decisions[candidate.id] })) }) as { product_version_id: string; import: ImportView };
      setActiveImport(result.import); setPublished(result.product_version_id);
    } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const acceptAll = () => { if (activeImport) setDecisions(Object.fromEntries(activeImport.candidates.map((item) => [item.id, { decision: "ACCEPT" }]))); };
  return <>
    <PageHeader title="导入与核验" subtitle="只在本地解析文本型 PDF；所有候选字段都由你逐项确认" actions={<><select className="compact-select" value={authority} onChange={(event) => setAuthority(event.target.value)} aria-label="来源权威性"><option value="CONTRACT_DOCUMENT">正式合同/条款</option><option value="REGULATOR_PUBLICATION">监管披露</option><option value="INSURER_OFFICIAL_DISCLOSURE">保险公司正式披露</option><option value="INSURER_OFFICIAL_WEB">保险公司官网</option><option value="THIRD_PARTY_REFERENCE">第三方线索</option><option value="UNATTRIBUTED">来源不明</option></select><button className="button secondary" onClick={() => setManualOpen(!manualOpen)}><Plus size={18} />手工资料</button><button className="button primary" disabled={busy} onClick={() => void choosePdf()}><Upload size={18} />选择文本 PDF</button></>} />
    {error && <ErrorPanel message={error} />}
    <div className="stepper"><span className="done">1 选择资料</span><i /><span className={activeImport ? "done" : ""}>2 本地解析</span><i /><span className={activeImport ? "active" : ""}>3 字段核验</span><i /><span className={published ? "done" : ""}>4 保存入库</span></div>
    {manualOpen && <Card><div className="card-title"><h2>手工资料</h2><StatusBadge tone="warning">不要填写姓名、保单号或健康信息</StatusBadge></div><form className="form-grid" onSubmit={(event) => void manual(event)}><label>产品名称<input name="display_name" required defaultValue="" /></label><label>版本<input name="version_label" required defaultValue="" /></label><label>司法辖区<select name="jurisdiction"><option value="CN_MAINLAND">中国内地</option><option value="HK">香港</option></select></label><label>险种<select name="line_of_business"><option value="MEDICAL">医疗险</option><option value="ACCIDENT">意外险</option><option value="CRITICAL_ILLNESS">重疾险</option><option value="ANNUITY">年金险</option><option value="LIFE_SAVINGS">寿险与储蓄</option><option value="OTHER">其他</option></select></label><label>币种<select name="currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>标准年费率<input name="annual_premium" required defaultValue="" pattern="\d+(\.\d{1,4})?" /></label><label>续保模式<select name="renewal_mode" defaultValue="UNKNOWN"><option value="GUARANTEED_RENEWAL">保证续保</option><option value="CONDITIONAL_RENEWAL">有条件续保</option><option value="NON_GUARANTEED_RENEWAL">不保证续保</option><option value="NON_RENEWABLE">不可续保</option><option value="UNKNOWN">待确认</option></select></label><label>保证续保年数<input name="guarantee_period_years" type="number" min="0" max="100" defaultValue="" /></label><label>最高续保年龄<input name="maximum_renewal_age" type="number" min="0" max="130" defaultValue="" /></label><label>调费范围<select name="rate_adjustment_scope" defaultValue="UNKNOWN"><option value="COHORT">同一投保群体</option><option value="PORTFOLIO">产品组合</option><option value="INDIVIDUAL">个别调整</option><option value="REGULATORY">监管规定</option><option value="UNKNOWN">待确认</option></select></label><label>责任限额<input name="benefit_limit" defaultValue="" /></label><label>来源权威性<select name="source_authority" defaultValue={authority}><option value="CONTRACT_DOCUMENT">正式合同／条款</option><option value="REGULATOR_PUBLICATION">监管披露</option><option value="INSURER_OFFICIAL_DISCLOSURE">保险公司正式披露</option><option value="INSURER_OFFICIAL_WEB">保险公司官网</option><option value="THIRD_PARTY_REFERENCE">第三方线索</option><option value="UNATTRIBUTED">来源不明</option></select></label><label className="span-two">证据摘录（最多 600 字）<textarea name="evidence_note" maxLength={600} required defaultValue="" /></label><div className="form-actions span-two"><button className="button primary">生成待核验字段</button></div></form></Card>}
    {activeImport ? <div className="import-layout"><Card className="document-preview"><div className="card-title"><h2>文档预览</h2>{activeImport.duplicate && <StatusBadge tone="warning">内容哈希重复</StatusBadge>}</div><FileSearch size={48} /><Link href={`/library/${activeImport.source.id}?kind=source`}>查看本地原文 →</Link><strong>{activeImport.source.title}</strong><span>{activeImport.source.document_type} · {activeImport.source.page_count ? `${activeImport.source.page_count} 页` : "网页来源"}</span><code>SHA-256 {activeImport.source.sha256.slice(0, 12)}…{activeImport.source.sha256.slice(-8)}</code><div className="notice"><ShieldCheck size={18} />原文件已使用随机 DEK 加密到私有 vault；界面与日志不显示原始路径。</div></Card><Card className="candidate-panel"><div className="card-title"><h2>候选字段</h2>{activeImport.status === "WAITING_REVIEW" && <button className="link-button" onClick={acceptAll}><Check size={16} />全部接受</button>}</div><div className="candidate-list">{activeImport.candidates.map((candidate) => { const decision = decisions[candidate.id] ?? { decision: "KEEP_UNVERIFIED" }; return <div className="candidate" key={candidate.id}><div className="candidate__number">{candidate.page_number ?? "网"}</div><div className="candidate__main"><label>{fieldLabels[candidate.field_path] ?? candidate.field_path}<input value={decision.edited_value ?? candidate.value} disabled={activeImport.status !== "WAITING_REVIEW" || decision.decision !== "EDIT"} onChange={(event) => setDecisions({ ...decisions, [candidate.id]: { decision: "EDIT", edited_value: event.target.value } })} /></label><small>{candidate.page_number ? `第 ${candidate.page_number} 页` : "网页正文"} · {candidate.value_origin} · {candidate.source_authority}</small><blockquote>{candidate.excerpt}</blockquote></div><select value={activeImport.status === "WAITING_REVIEW" ? decision.decision : candidate.decision ?? "KEEP_UNVERIFIED"} disabled={activeImport.status !== "WAITING_REVIEW"} onChange={(event) => { const next = event.target.value === "EDIT" ? { decision: "EDIT", edited_value: candidate.value } : { decision: event.target.value }; setDecisions({ ...decisions, [candidate.id]: next }); }}><option value="KEEP_UNVERIFIED">保持待核验</option><option value="ACCEPT">接受</option><option value="EDIT">编辑后接受</option><option value="REJECT">拒绝</option></select></div>; })}</div>{activeImport.status === "WAITING_REVIEW" ? <div className="form-actions"><button className="button primary" disabled={busy} onClick={() => void submitReview()}><FileCheck2 size={18} />确认并发布版本</button></div> : published && <div className="success-panel"><BadgeCheck /><div><strong>产品版本已保存</strong><p>核验状态、值来源和证据权威性分别保留。</p></div><button className="button secondary" onClick={() => openProduct(published)}>查看字段证据</button></div>}</Card></div> : !manualOpen && <Card className="small-empty"><Upload /><h2>选择资料开始</h2><p>支持可提取文本的 PDF 或手工资料。扫描 PDF 请先存入家庭资料，可查看原件并手工记录重点。</p></Card>}
    <div className="notice"><Info size={18} />图片 OCR 与 Excel 导入尚未实现。公开研究可通过高级研究入口进行，家庭原件不会自动外发。</div>
  </>;
}
