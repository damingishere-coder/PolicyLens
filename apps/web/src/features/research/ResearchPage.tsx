import { Card,StatusBadge } from "@policylens/ui";
import {
BadgeCheck,
BookOpen,
ChevronRight,
CircleAlert,
Clock3,
FileSearch,
Scale,
Search,
ShieldCheck,
Sparkles
} from "lucide-react";
import { useCallback,useEffect,useState } from "react";
import { policyLens } from "../../api";
import { asError,ErrorPanel,fieldLabels,PageHeader } from '../../components/layout/LegacyShared';
import type { CandidateComparisonView,ProductSummary,ResearchCandidateView,ResearchPreviewView,ResearchReadinessView,ResearchRunView } from '../research/types';
export const researchErrors: Record<string, string> = {
  CODEX_FAILED: "研究执行失败，本次未取得完整结果；请勿将其理解为保险公司没有产品。旧记录未保留具体原因，请在修复生效后重新预览并启动研究。",
  CODEX_UNTRUSTED_DIRECTORY: "研究未能启动：临时工作目录未通过检查，请更新程序后重新研究。",
  CODEX_NOT_FOUND: "未找到 Codex CLI，请检查本机安装后重新研究。",
  CODEX_START_FAILED: "研究进程无法启动或临时文件无法读写，请检查本机运行环境。",
  CODEX_INVALID_SCHEMA: "研究输出格式配置不兼容，请更新程序后重新研究。",
  CODEX_AUTH_REQUIRED: "Codex 登录验证失败，请检查本机登录状态后重新研究。",
  CODEX_RATE_LIMIT: "Codex 可用额度或请求频率受限，请待限制恢复后重新研究。",
  CODEX_NETWORK_FAILED: "无法连接 Codex 服务，请检查网络后重新研究。",
  CODEX_TIMEOUT: "研究超时，本次未取得完整结果；请稍后重新预览并启动研究。",
  DNS_FAILED: "官网域名解析失败，无法取得原文。",
  DNS_REJECTED: "官网解析结果未通过安全检查，无法取得原文。",
  SSRF_REJECTED: "官网解析到了非公网地址，已停止抓取；请检查网络或代理的 DNS 设置。",
  EVIDENCE_MISMATCH: "返回的证据摘录无法在官网原文中逐字核对，该产品未进入候选。",
  REQUIRED_EVIDENCE_MISSING: "必要字段缺少可逐字核对的官方证据，该产品未进入候选。",
  OFFICIAL_LEAD_UNVERIFIED: "已找到官方页面线索，但尚未取得完整的可核验证据。",
  CODEX_INVALID_OUTPUT: "研究返回内容未通过格式校验，本次未创建候选产品。",
  CODEX_OUTPUT_TOO_LARGE: "研究输出超过安全上限，本次结果已拒绝。",
  RESEARCH_PIPELINE_FAILED: "研究处理失败，本次结果不完整。",
  USER_CANCELLED: "本次研究已取消，未完成的搜索不能视为没有产品。",
  PROCESS_INTERRUPTED: "服务退出导致研究中断，请重新预览并启动研究。",
  NO_VERIFIED_OFFICIAL_SOURCE: "本次搜索已结束，但没有取得通过官方来源核验的候选，请查看各公司的具体结果。",
  RESEARCH_FAILED: "本次研究执行失败，尚无完整搜索结果。",
  RESEARCH_CANCELLED: "本次研究已取消。",
  RESEARCH_INTERRUPTED: "本次研究已中断，请重新预览并启动研究。",
  NO_RESULT_RETURNED: "本次搜索已结束，未返回该公司的候选或线索。",
  NO_OFFICIAL_CANDIDATE: "本次仅发现第三方线索，未取得可核验的官方候选。"
};

export function researchError(code: string): string {
  return researchErrors[code] ? `${researchErrors[code]}（${code}）` : code;
}

export function ResearchExecution({ run }: { run: ResearchRunView }) {
  const execution = run.summary.execution;
  if (!execution) return null;
  const phases: Record<string, string> = {
    STARTING: "正在启动", RESEARCHING: "正在研究", WEB_SEARCH: "检索和读取公开网页", RESPONSE_READY: "已返回研究资料"
  };
  const elapsed = `${Math.floor(execution.elapsed_seconds / 60)} 分 ${execution.elapsed_seconds % 60} 秒`;
  return <div className="notice research-execution"><Clock3 /><span>
    {['QUEUED', 'DISCOVERING', 'FETCHING'].includes(run.status) ? "Codex 阶段" : "Codex 最后记录"}：{phases[execution.phase] ?? "正在处理"} · 已用 {elapsed} / 上限 {Math.ceil(execution.timeout_seconds / 60)} 分钟
    {" · "}网页检索活动 {execution.web_searches} 次
    {execution.last_event_elapsed_seconds !== null && ` · 最近活动在第 ${execution.last_event_elapsed_seconds} 秒`}
    {run.status === "FETCHING" && " · 正在核验官方原文"}
  </span></div>;
}

export function ResearchStatus({ status }: { status: string }) {
  const tone = ["WAITING_REVIEW", "COMPLETED"].includes(status) ? "success" : ["FAILED", "CANCELLED", "INTERRUPTED"].includes(status) ? "danger" : "warning";
  const labels: Record<string, string> = { FAILED: "执行失败", CANCELLED: "已取消", INTERRUPTED: "已中断", NO_RESULT: "未发现结果", SEARCHING: "研究中", QUEUED: "等待启动", DISCOVERING: "联网研究中", FETCHING: "核验原文中", PARTIAL: "部分完成", LEAD_ONLY: "待核验线索" };
  return <StatusBadge tone={tone}>{labels[status] ?? status}</StatusBadge>;
}

export function HongKongResearchPage({ openImport, openProduct }: { openImport: (id: string) => void; openProduct: (id: string) => void }) {
  const [preview, setPreview] = useState<ResearchPreviewView | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [run, setRun] = useState<ResearchRunView | null>(null);
  const [runs, setRuns] = useState<ResearchRunView[]>([]);
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [candidates, setCandidates] = useState<ResearchCandidateView[]>([]);
  const [readiness, setReadiness] = useState<ResearchReadinessView | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([]);
  const [candidateComparison, setCandidateComparison] = useState<CandidateComparisonView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = run && ["QUEUED", "DISCOVERING", "FETCHING"].includes(run.status);
  const refresh = useCallback(async () => {
    const [runValue, productValue, candidateValue, readinessValue] = await Promise.all([
      policyLens.listResearchRuns(),
      policyLens.listResearchProducts(true),
      policyLens.listResearchCandidates(),
      policyLens.getResearchReadiness()
    ]);
    const recent = runValue as ResearchRunView[];
    setRuns(recent);
    setProducts(productValue as ProductSummary[]);
    setCandidates(candidateValue as ResearchCandidateView[]);
    setReadiness(readinessValue as ResearchReadinessView);
    setRun((current) => current ? recent.find((item) => item.id === current.id) ?? current : recent[0] ?? null);
  }, []);
  useEffect(() => { refresh().catch((reason) => setError(asError(reason))); }, [refresh]);
  useEffect(() => {
    if (!active || !run) return;
    const timer = window.setInterval(() => {
      policyLens.getResearchRun(run.id).then((value) => {
        const next = value as ResearchRunView;
        setRun(next);
        if (!["QUEUED", "DISCOVERING", "FETCHING"].includes(next.status)) void refresh();
      }).catch((reason) => setError(asError(reason)));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, refresh, run]);
  const prepare = async () => {
    setBusy(true); setError("");
    try { setPreview(await policyLens.previewResearch() as ResearchPreviewView); setConfirmed(false); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const start = async () => {
    if (!preview || !confirmed) return;
    setBusy(true); setError("");
    try { const next = await policyLens.startResearch(preview.preview_hash) as ResearchRunView; setRun(next); setPreview(null); setConfirmed(false); await refresh(); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!run) return;
    try { await policyLens.cancelResearch(run.id); setRun(await policyLens.getResearchRun(run.id) as ResearchRunView); } catch (reason) { setError(asError(reason)); }
  };
  const toggleCandidate = (importId: string) => {
    setCandidateComparison(null);
    setSelectedCandidates((current) => current.includes(importId)
      ? current.filter((item) => item !== importId)
      : current.length < 4 ? [...current, importId] : current);
  };
  const compareCandidates = async () => {
    if (selectedCandidates.length < 2) return;
    setBusy(true); setError("");
    try {
      setCandidateComparison(await policyLens.compareResearchCandidates(selectedCandidates) as CandidateComparisonView);
    } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const officialLeads = run?.leads.filter((item) => item.channel === "OFFICIAL_SEARCH") ?? [];
  const thirdPartyLeads = run?.leads.filter((item) => item.channel === "THIRD_PARTY_LEAD") ?? [];
  return <>
    <PageHeader title="香港储蓄/年金主动研究" subtitle="友邦、保诚、宏利 · 全网发现线索 · 官方来源逐字验证" actions={<button className="button primary" disabled={busy || Boolean(active) || readiness?.ready === false} onClick={() => void prepare()}><Search size={18} />查看联网研究预览</button>} />
    {error && <ErrorPanel message={error} />}
    {readiness && <div className={`notice ${readiness.ready ? "success" : "warning"}`}>{readiness.ready ? <BadgeCheck /> : <CircleAlert />}{readiness.ready ? "研究环境已就绪；点击后仍会先展示本次联网范围与用量预览。" : readiness.checks.filter((item) => !item.ready).map((item) => item.message).join("；")}</div>}
    <div className="research-insurers">{["友邦香港", "保诚香港", "宏利香港"].map((name) => <Card key={name}><ShieldCheck /><div><strong>{name}</strong><span>官方域名白名单已锁定</span></div></Card>)}</div>
    {preview && <Card className="research-preview"><div className="card-title"><h2><Sparkles />本次联网研究预览</h2><StatusBadge tone="warning">需要逐次确认</StatusBadge></div><p className="research-query">{preview.query_summary}</p><div className="two-column compact-columns"><div><h3>会发送</h3><ul>{preview.will_send.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h3>不会发送</h3><ul>{preview.will_not_send.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="notice warning"><CircleAlert />{preview.usage_notice}</div><code>预览校验 {preview.preview_hash.slice(0, 12)}…</code><label className="confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已查看范围和用量提示，同意本次只搜索公开资料</label><div className="form-actions"><button className="button secondary" onClick={() => setPreview(null)}>取消</button><button className="button primary" disabled={!confirmed || busy} onClick={() => void start()}><Search />确认并启动一次研究</button></div></Card>}
    {run && <Card className="research-run"><div className="card-title"><h2><FileSearch />最近运行</h2><ResearchStatus status={run.status} /></div><div className="run-summary"><span>候选产品 <strong>{run.summary.discovered_products ?? 0}</strong></span><span>待核验 <strong>{run.summary.waiting_review ?? 0}</strong></span><span>已拒绝 <strong>{run.summary.rejected_products ?? 0}</strong></span><span>线索 <strong>{run.summary.lead_only ?? 0}</strong></span></div><ResearchExecution run={run} />{active && <div className="notice"><span className="spinner" />Codex 正在发现公开线索并验证官方页面。可以离开本页，运行记录会保留。<button className="button secondary" onClick={() => void cancel()}>取消研究</button></div>}{run.error_code && <div className="notice warning"><CircleAlert />{researchError(run.error_code)}</div>}{officialLeads.length > 0 && <div className="lead-list"><h3>官方来源与候选</h3>{officialLeads.map((lead) => <article key={lead.id}><div><strong>{lead.title}</strong><small>{lead.insurer_id} · {lead.authority}</small><span>{lead.url}</span></div><div><ResearchStatus status={lead.status} />{lead.import_id && <button className="button secondary" onClick={() => openImport(lead.import_id!)}>逐项核验</button>}</div></article>)}</div>}{thirdPartyLeads.length > 0 && <details className="third-party-leads"><summary>第三方线索 {thirdPartyLeads.length} 条（不会作为事实）</summary>{thirdPartyLeads.map((lead) => <p key={lead.id}>{lead.title} · {lead.url}</p>)}</details>}</Card>}
    {run && <Card className="insurer-outcomes"><div className="card-title"><h2>逐保险公司结果</h2><span>零结果也会给出明确原因</span></div><div className="outcome-grid">{run.insurer_outcomes.map((item) => <div key={item.insurer_id}><div><strong>{item.brand_name}</strong><ResearchStatus status={item.status} /></div><small>官方候选 {item.official_candidates} · 官方线索 {item.official_leads ?? 0} · 待核验 {item.waiting_review} · 第三方线索 {item.lead_only}</small>{item.error_codes.length > 0 && <p>{item.error_codes.map(researchError).join("、")}</p>}</div>)}</div></Card>}
    <Card className="candidate-workbench"><div className="card-title"><div><h2><FileSearch />研究候选工作台</h2><span>候选生成后立即可浏览、选中和并排比较</span></div><div className="candidate-actions"><StatusBadge tone="warning">全部先视为未核验</StatusBadge><button className="button primary" disabled={selectedCandidates.length < 2 || busy} onClick={() => void compareCandidates()}><Scale />对比所选 {selectedCandidates.length || ""}</button></div></div>{candidates.length ? <div className="candidate-card-grid">{candidates.map((candidate) => <article className={`candidate-card ${selectedCandidates.includes(candidate.import_id) ? "selected" : ""}`} key={candidate.import_id}><label className="candidate-select"><input type="checkbox" checked={selectedCandidates.includes(candidate.import_id)} disabled={!selectedCandidates.includes(candidate.import_id) && selectedCandidates.length >= 4} onChange={() => toggleCandidate(candidate.import_id)} />加入待核验对比</label><div className="card-title"><div><h3>{candidate.display_name}</h3><small>{candidate.version_label} · {candidate.insurer_id}</small></div><StatusBadge tone={candidate.review_status === "WAITING_REVIEW" ? "warning" : "success"}>{candidate.review_status === "WAITING_REVIEW" ? "未核验候选" : "已完成核验"}</StatusBadge></div><dl><div><dt>类别</dt><dd>{candidate.line_of_business ?? "未知"}</dd></div><div><dt>币种</dt><dd>{candidate.currency ?? "未知"}</dd></div><div><dt>销售状态</dt><dd>{candidate.sale_status ?? "未知"}</dd></div><div><dt>候选字段</dt><dd>{candidate.field_count}</dd></div></dl><details><summary>查看字段证据</summary>{candidate.fields.map((field) => <div className="candidate-evidence" key={field.id}><strong>{fieldLabels[field.field_path] ?? field.field_path}：{field.value} {field.unit ?? ""}</strong><small>{field.source_authority} · {field.page_number ? `第 ${field.page_number} 页` : "网页正文"}</small><blockquote>{field.excerpt}</blockquote></div>)}</details><div className="candidate-source"><BookOpen /><a href={candidate.source.canonical_url ?? undefined} target="_blank" rel="noreferrer">{candidate.source.title}</a></div><button className="button secondary full" onClick={() => candidate.published_product_version_id ? openProduct(candidate.published_product_version_id) : openImport(candidate.import_id)}>{candidate.published_product_version_id ? "查看正式产品" : "逐项人工核验"}</button></article>)}</div> : <div className="small-empty"><FileSearch /><h2>尚无研究候选</h2><p>完成一次联网研究后，通过官方来源逐字验证的候选会立即显示在这里；无需先发布成正式产品。</p></div>}</Card>
    {candidateComparison && <Card className="evidence-matrix candidate-matrix"><div className="card-title"><h2>待核验候选对比</h2><StatusBadge tone="warning">不是正式结论</StatusBadge></div><div className="matrix-scroll"><table><thead><tr><th>字段</th>{candidateComparison.candidates.map((candidate) => <th key={candidate.import_id}>{candidate.display_name}<small>{candidate.version_label}</small></th>)}</tr></thead><tbody>{candidateComparison.rows.map((row) => <tr key={row.field_path}><td><strong>{fieldLabels[row.field_path] ?? row.field_path}</strong></td>{row.cells.map((cell) => <td key={cell.import_id}><strong>{cell.value ?? "缺失"} {cell.unit ?? ""}</strong><small>{cell.verification_status} · {cell.guarantee_type}</small>{cell.excerpt && <details><summary>证据摘录</summary><blockquote>{cell.excerpt}</blockquote></details>}</td>)}</tr>)}</tbody></table></div><div className="notice warning"><CircleAlert />{candidateComparison.notice}</div></Card>}
    <Card className="table-card research-products"><div className="card-title table-heading"><h2>本地香港产品档案</h2><span>{products.length} 个版本</span></div>{products.length ? <table><thead><tr><th>产品</th><th>保险公司</th><th>类别</th><th>销售状态</th><th>核验</th><th /></tr></thead><tbody>{products.map((product) => <tr key={product.version_id}><td><strong>{product.display_name}</strong><small>{product.version_label}</small></td><td>{product.insurer_id ?? "未知"}</td><td>{product.product_category ?? product.line_of_business}</td><td>{product.sale_status ?? "未知"}</td><td><ResearchStatus status={product.record_status} /></td><td><button className="icon-button" aria-label={`查看产品 ${product.display_name}`} onClick={() => openProduct(product.version_id)}><ChevronRight /></button></td></tr>)}</tbody></table> : <div className="small-empty"><Search /><h2>尚无已抓取产品</h2><p>先运行一次公开研究。只有通过官方来源验证的候选才会进入人工核验。</p></div>}</Card>
    {runs.length > 1 && <div className="notice"><Clock3 />已保留 {runs.length} 次最近研究记录；服务重启不会自动重跑未完成任务。</div>}
  </>;
}
