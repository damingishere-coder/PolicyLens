import { formText } from "../lib/forms";
import { Archive,Bell,BookOpen,Home,Scale,Search,Settings,ShieldCheck,Sprout,Users } from "lucide-react";
import { useEffect,type FormEvent,type ReactNode } from "react";
import { SettingsPage } from "../features/backup/SettingsPage";
import { ComparisonPage } from "../pages/comparison/ComparisonPage";
import { ProductDetailPage } from "../features/evidence/ProductDetailPage";
import { LibraryPage } from "../pages/library/LibraryPage";
import { ImportPage } from "../features/imports/ImportPage";
import { HongKongResearchPage } from "../features/research/ResearchPage";
import { SearchPage } from "../features/research/SearchPage";
import { FamilyPage } from "../pages/family/FamilyPage";
import { HomePage } from "../pages/home/HomePage";
import { RetirementPage } from "../pages/retirement/RetirementPage";
import { PoliciesPage } from "../pages/policies/PoliciesPage";
import { PolicyDetailPage } from "../pages/policies/PolicyDetailPage";
import { TasksPage } from "../pages/tasks/TasksPage";
import { Link,navigate,useRoute } from "./router";

const navigation = [
  {path:"/",label:"家庭首页",icon:Home}, {path:"/family",label:"我的家庭",icon:Users},
  {path:"/policies",label:"我的保单",icon:Archive}, {path:"/compare",label:"挑选与比较",icon:Scale},
  {path:"/retirement",label:"养老规划",icon:Sprout}, {path:"/library",label:"资料与笔记",icon:BookOpen},
];

export default function App() {
  const route = useRoute(); const url = new URL(route,window.location.origin);
  const segments = url.pathname.split("/").filter(Boolean); const id = segments[1];
  useEffect(() => {document.querySelector("main")?.focus();},[route]);
  const openProduct = (productId: string) => navigate(`/products/${productId}?returnTo=${encodeURIComponent(route)}`);
  const openImport = (importId: string) => navigate(`/imports/${importId}`);
  let content: ReactNode;
  switch(segments[0]) {
    case undefined: content = <HomePage />; break;
    case "family": content = <FamilyPage {...(id ? {id} : {})} />; break;
    case "policies": content = id && id !== "new" ? <PolicyDetailPage id={id} created={url.searchParams.has("created")} /> : <PoliciesPage creating={id === "new"} query={url.searchParams} />; break;
    case "tasks": content = <TasksPage />; break;
    case "evidence-search": content = <><form className="filter-bar" onSubmit={event => {event.preventDefault();navigate(`/evidence-search?q=${encodeURIComponent(formText(new FormData(event.currentTarget),"query"))}`);}}><label>查找产品、候选或来源<input name="query" minLength={2} maxLength={120} required defaultValue={url.searchParams.get("q") ?? ""} /></label><button className="button primary">搜索本地证据</button></form><SearchPage query={url.searchParams.get("q") ?? ""} openProduct={openProduct} openImport={openImport} /></>; break;
    case "research": content = <><Link className="back" href="/compare">← 挑选与比较</Link><HongKongResearchPage openImport={openImport} openProduct={openProduct} /></>; break;
    case "compare": content = <ComparisonPage {...(id ? {id} : {})} query={url.searchParams} openProduct={openProduct} />; break;
    case "products": content = <ProductDetailPage id={id ?? null} back={() => navigate(url.searchParams.get("returnTo") || "/compare")} />; break;
    case "imports": content = <><Link className="back" href="/library">← 资料与笔记</Link><ImportPage openProduct={openProduct} initialImportId={id ?? null} /></>; break;
    case "library": content = <LibraryPage {...(id ? {id} : {})} query={url.searchParams} />; break;
    case "retirement": content = <RetirementPage {...(id ? {id} : {})} query={url.searchParams} />; break;
    case "settings": content = <SettingsPage />; break;
    default: content = <div><h1>没有找到这个页面</h1><Link href="/">返回家庭首页</Link></div>;
  }
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {event.preventDefault();const q = formText(new FormData(event.currentTarget), "search").trim();if(q) navigate(`/policies?q=${encodeURIComponent(q)}`);};
  return <div className="app-shell family-shell" data-testid="app-shell"><a className="skip-link" href="#main-content">跳到主要内容</a><aside className="sidebar"><Link className="brand" href="/"><span className="brand-mark"><ShieldCheck /></span><strong>PolicyLens</strong></Link><span className="sidebar-caption">家庭保险与规划</span><nav aria-label="主要导航">{navigation.map(item => {const Icon=item.icon;const active=item.path === "/" ? !segments.length : url.pathname.startsWith(item.path);return <Link key={item.path} href={item.path} className={active ? "active" : ""} aria-current={active ? "page" : undefined}><Icon /><span>{item.label}</span></Link>;})}</nav><div className="sidebar-bottom"><Link href="/settings"><Settings size={18} />设置与备份</Link><div className="sidebar-foot"><ShieldCheck /><span>资料保存在本地<br /><small>AI 外发由你逐次确认</small></span></div></div></aside><section className="workspace"><header className="topbar"><form className="searchbox" onSubmit={submitSearch}><Search /><input name="search" aria-label="全局搜索" placeholder="查找成员或已有保险" /><kbd>Enter</kbd></form><Link href="/tasks" className="topbar-task"><Bell size={19} />家庭待办</Link><span className="local-label"><i />本地模式</span></header><main id="main-content" tabIndex={-1} key={route}>{content}</main></section></div>;
}
