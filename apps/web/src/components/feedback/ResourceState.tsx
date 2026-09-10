import type { ReactNode } from "react";
import { ErrorPanel,Loading } from "../layout/LegacyShared";

export function ResourceState({ error, loading, retry, children }: { error: string; loading: boolean; retry: () => void; children: ReactNode }) {
  if (error) return <><ErrorPanel message={error} /><button className="button secondary" onClick={retry}>重新读取</button></>;
  if (loading) return <Loading />;
  return <>{children}</>;
}
