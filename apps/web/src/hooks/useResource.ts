import { useCallback,useEffect,useRef,useState } from "react";
import { request } from "../services/http";

export function useResource<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError("");
    request<T>(url, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setData(value);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "本地资料读取失败");
    });
    return () => controller.abort();
  }, [url, version]);
  return { data, error, refresh };
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败，输入已保留，请检查后再试"); }
    finally { lock.current = false; setBusy(false); }
  };
  return { busy, error, run };
}
