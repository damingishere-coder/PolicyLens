import { Link } from "../../app/router";
import { Card,StatusBadge } from "@policylens/ui";
import {
BadgeCheck,
BookOpen,
FileSearch,
Info
} from "lucide-react";
import { useEffect,useState } from "react";
import { policyLens } from "../../api";
import { asError,ErrorPanel,Loading,PageHeader } from '../../components/layout/LegacyShared';
import type { SourceView } from '../research/types';
export function SourcesPage() {
  const [sources, setSources] = useState<SourceView[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { policyLens.listSources().then((value) => setSources(value as SourceView[])).catch((reason) => setError(asError(reason))); }, []);
  if (error) return <ErrorPanel message={error} />;
  return <><PageHeader title="来源与证据中心" subtitle="官方网页、PDF、内容修订、哈希和字段证据都保留可追溯关系" />{sources === null ? <Loading /> : <><div className="metric-grid metric-grid--three"><Card className="metric"><BookOpen /><div><span>本地来源</span><strong>{sources.length}</strong></div></Card><Card className="metric"><BadgeCheck /><div><span>已核验来源</span><strong>{sources.filter((item) => item.status === "VERIFIED").length}</strong></div></Card><Card className="metric"><FileSearch /><div><span>证据锚点</span><strong>{sources.reduce((sum, item) => sum + item.evidence_count, 0)}</strong></div></Card></div>{sources.length ? <Card className="table-card"><table><thead><tr><th>来源</th><th>权威性</th><th>官方地址</th><th>SHA-256</th><th>证据</th><th>状态</th></tr></thead><tbody>{sources.map((source) => <tr key={source.id}><td><strong><Link href={`/library/${source.id}?kind=source`}>{source.title}</Link></strong><small>{source.document_type}{source.fetched_at ? ` · ${source.fetched_at.slice(0, 10)}` : ""}</small></td><td>{source.authority}</td><td><small className="source-url">{source.canonical_url ?? "本地导入"}</small></td><td><code>{source.sha256.slice(0, 10)}…{source.sha256.slice(-6)}</code></td><td>{source.evidence_count}</td><td><StatusBadge tone={source.status === "VERIFIED" ? "success" : "warning"}>{source.status}</StatusBadge></td></tr>)}</tbody></table></Card> : <Card className="small-empty"><BookOpen /><p>尚无来源。完成一次公开研究或导入本地资料后，这里会显示内容哈希和证据状态。</p></Card>}</>}<div className="notice"><Info size={18} />第三方内容只作为发现线索；产品事实必须落到保险公司官方来源并经过人工核验。</div></>;
}
