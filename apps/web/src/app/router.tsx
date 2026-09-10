import { useEffect,useSyncExternalStore,type AnchorHTMLAttributes,type MouseEvent } from "react";

const dirtyForms = new Set<symbol>();
let activeIndex = Number((window.history.state as { plIndex?: number } | null)?.plIndex ?? 0);
window.history.replaceState({ plIndex: activeIndex }, "");
let recovering = false;
const listeners = new Set<() => void>();
function notify() { listeners.forEach(listener => listener()); }
window.addEventListener("popstate", () => {
  const nextIndex = Number((window.history.state as { plIndex?: number } | null)?.plIndex ?? 0);
  if (recovering) { recovering = false; return; }
  if (dirtyForms.size && !window.confirm("当前输入尚未保存。离开会丢弃这些输入，确定离开吗？")) {
    recovering = true; window.history.go(activeIndex - nextIndex); return;
  }
  activeIndex = nextIndex; dirtyForms.clear(); notify();
});
window.addEventListener("beforeunload", event => {
  if (dirtyForms.size) { event.preventDefault(); event.returnValue = ""; }
});

export function navigate(url: string, force = false) {
  if (!url.startsWith("/") || url.startsWith("//")) return;
  if (!force && dirtyForms.size && !window.confirm("当前输入尚未保存。离开会丢弃这些输入，确定离开吗？")) return;
  dirtyForms.clear(); activeIndex += 1;
  window.history.pushState({ plIndex: activeIndex }, "", url);
  notify(); window.scrollTo(0, 0);
}
export function useRoute() {
  return useSyncExternalStore(callback => { listeners.add(callback); return () => { listeners.delete(callback); }; }, () => window.location.pathname + window.location.search);
}
export function useDraftGuard(dirty: boolean) {
  useEffect(() => {
    const key = Symbol();
    if (dirty) dirtyForms.add(key);
    return () => { dirtyForms.delete(key); };
  }, [dirty]);
}
export function Link({ href = "/", children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const click = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || props.target) return;
    event.preventDefault(); navigate(href);
  };
  return <a {...props} href={href} onClick={click}>{children}</a>;
}
