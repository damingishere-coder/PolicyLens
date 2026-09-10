import { Card } from "@policylens/ui";
import {
BookOpen,
ChevronRight,
CircleAlert,
FileCheck2,
FileSearch,
Search
} from "lucide-react";
import { useEffect,useState } from "react";
import { policyLens } from "../../api";
import { asError,ErrorPanel,Loading,PageHeader } from '../../components/layout/LegacyShared';
import type { SearchResultView } from '../research/types';
export function SearchPage({ query, openProduct, openImport }: { query: string; openProduct: (id: string) => void; openImport: (id: string) => void }) {
  const [result, setResult] = useState<SearchResultView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (query.trim().length < 2) { setResult(null); return; }
    policyLens.search(query).then((value) => setResult(value as SearchResultView)).catch((reason) => setError(asError(reason)));
  }, [query]);
  return <><PageHeader title="本地证据搜索" subtitle={query ? `搜索“${query}”的正式产品、待核验候选和来源` : "输入至少两个字符，搜索已经保存的产品、候选与来源"} />{error && <ErrorPanel message={error} />}{query.trim().length < 2 ? <Card className="small-empty"><Search /><p>在顶部搜索框输入产品名称、版本、保险公司或来源标题，然后按 Enter。</p></Card> : !result ? <Loading /> : <div className="search-grid"><Card><div className="card-title"><h2>正式产品</h2><span>{result.products.length}</span></div>{result.products.length ? <div className="list">{result.products.map((product) => <button className="search-result" key={product.version_id} onClick={() => openProduct(product.version_id)}><FileCheck2 /><span><strong>{product.display_name}</strong><small>{product.version_label} · {product.record_status}</small></span><ChevronRight /></button>)}</div> : <div className="small-empty"><Search /><p>没有匹配正式产品。</p></div>}</Card><Card><div className="card-title"><h2>待核验候选</h2><span>{result.candidates.length}</span></div>{result.candidates.length ? <div className="list">{result.candidates.map((candidate) => <button className="search-result" key={candidate.import_id} onClick={() => openImport(candidate.import_id)}><CircleAlert /><span><strong>{candidate.display_name}</strong><small>{candidate.version_label} · {candidate.review_status}</small></span><ChevronRight /></button>)}</div> : <div className="small-empty"><FileSearch /><p>没有匹配研究候选。</p></div>}</Card><Card><div className="card-title"><h2>来源</h2><span>{result.sources.length}</span></div>{result.sources.length ? <div className="list">{result.sources.map((source) => <div className="list-row" key={source.id}><BookOpen /><div><strong>{source.title}</strong><span>{source.authority} · {source.status}</span></div></div>)}</div> : <div className="small-empty"><BookOpen /><p>没有匹配来源。</p></div>}</Card></div>}</>;
}
