import { Card,StatusBadge } from "@policylens/ui";
import {
BadgeCheck,
Bot,
Check,
CircleAlert,
Database,
FolderOpen,
KeyRound,
Laptop,
LockKeyhole,
RotateCcw
} from "lucide-react";
import { useCallback,useEffect,useState } from "react";
import { policyLens } from "../../api";
import { asError,ErrorPanel,KeyValue,Loading,PageHeader } from '../../components/layout/LegacyShared';
import type { RestorePreview } from '../research/types';
export function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [runtime, setRuntime] = useState<Record<string, unknown> | null>(null);
  const [backupPassword, setBackupPassword] = useState("");
  const [backupConfirm, setBackupConfirm] = useState("");
  const [restorePassword, setRestorePassword] = useState("");
  const [restore, setRestore] = useState<RestorePreview | null>(null);
  const [restoreConfirmed, setRestoreConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const refresh = useCallback(() => { Promise.all([policyLens.getSettings(), policyLens.getRuntimeInfo()]).then(([s, r]) => { setSettings(s as Record<string, unknown>); setRuntime(r as Record<string, unknown>); }).catch((reason) => setError(asError(reason))); }, []);
  useEffect(refresh, [refresh]);
  const backup = async () => { setError(""); setMessage(""); if (backupPassword !== backupConfirm) { setError("两次输入的恢复密码不一致。"); return; } if (backupPassword.length < 12) { setError("恢复密码至少需要 12 个字符。"); return; } try { const result = await policyLens.createBackup(backupPassword) as { cancelled?: boolean; file_name?: string; payload_sha256?: string }; if (!result.cancelled) { setMessage(`备份已验证并保存：${result.file_name}（校验 ${result.payload_sha256?.slice(0, 12)}…）`); setBackupPassword(""); setBackupConfirm(""); } } catch (reason) { setError(asError(reason)); } };
  const copyDataPath = async () => { setError(""); try { await policyLens.copyDataDirectory(); setMessage("数据目录路径已复制，请粘贴到资源管理器地址栏。"); } catch (reason) { setError(asError(reason)); } };
  const previewRestore = async () => { setError(""); setMessage(""); if (restorePassword.length < 12) { setError("请输入至少 12 个字符的恢复密码。"); return; } try { const result = await policyLens.previewRestore(restorePassword) as RestorePreview & { cancelled?: boolean }; if (!result.cancelled) { setRestore(result); setRestoreConfirmed(false); } } catch (reason) { setError(asError(reason)); } };
  const commitRestore = async () => { if (!restore || !restoreConfirmed) return; try { const result = await policyLens.commitRestore(restore.restore_token) as { safety_snapshot: string }; setMessage(`恢复成功，当前机器已重新包装 DEK；安全快照：${result.safety_snapshot}`); setRestore(null); setRestorePassword(""); setRestoreConfirmed(false); refresh(); } catch (reason) { setError(asError(reason)); } };
  return <><PageHeader title="设置" subtitle="本地优先、隐私可控、AI 可审计" />{error && <ErrorPanel message={error} />}{message && <div className="notice success"><BadgeCheck size={18} />{message}</div>}{!settings || !runtime ? <Loading /> : <div className="settings-grid"><Card><div className="card-title"><h2><Database />本地数据</h2><StatusBadge tone="success">AES-256-GCM</StatusBadge></div><KeyValue data={{ 数据目录: settings.data_directory, 数据库目录: settings.database_directory, 加密: settings.encryption, 本机密钥包装: settings.local_key_wrapper, 遥测: "关闭" }} /><button className="button secondary full" onClick={() => void copyDataPath()}><FolderOpen size={18} />复制数据目录路径</button></Card><Card><div className="card-title"><h2><Laptop />运行状态</h2><StatusBadge tone="success">浏览器本地模式</StatusBadge></div><KeyValue data={{ "Web 服务 PID": runtime.servicePid, 托管方式: runtime.manager, 监听地址: `${String(runtime.serviceHost)}:${String(runtime.servicePort)}`, 端口管理: "RunDock", 会话保护: runtime.sessionProtection }} /></Card><Card><div className="card-title"><h2><KeyRound />便携加密备份</h2><StatusBadge tone="info">Argon2id</StatusBadge></div><p>恢复密码用于另一台电脑。密码不会保存；丢失后无法跨机器恢复。</p><label>恢复密码（至少 12 字符）<input type="password" autoComplete="new-password" value={backupPassword} onChange={(event) => setBackupPassword(event.target.value)} /></label><label>再次输入恢复密码<input type="password" autoComplete="new-password" value={backupConfirm} onChange={(event) => setBackupConfirm(event.target.value)} /></label><button className="button primary full" onClick={() => void backup()}><LockKeyhole size={18} />验证密码并下载备份</button><small>{String(settings.portable_backup_kdf)}</small></Card><Card><div className="card-title"><h2><RotateCcw />跨机器恢复</h2><StatusBadge tone="warning">先验证，后切换</StatusBadge></div><p>错误密码、篡改或版本不兼容会在修改当前数据之前失败。</p><label>备份恢复密码<input type="password" autoComplete="current-password" value={restorePassword} onChange={(event) => setRestorePassword(event.target.value)} /></label><button className="button secondary full" onClick={() => void previewRestore()}><FolderOpen size={18} />上传备份并验证</button>{restore && <div className="restore-preview"><h3>恢复摘要</h3><KeyValue data={{ 来源: restore.source_count, 产品: restore.product_count, 保单: restore.policy_count, 备份时间: restore.backup_created_at, 当前数据: restore.current_data_unchanged ? "尚未修改" : "异常" }} /><label className="confirm"><input type="checkbox" checked={restoreConfirmed} onChange={(event) => setRestoreConfirmed(event.target.checked)} />我确认用已验证备份切换当前数据</label><button className="button primary full" disabled={!restoreConfirmed} onClick={() => void commitRestore()}>确认恢复并重新绑定 DPAPI</button></div>}</Card><Card className="span-two"><div className="card-title"><h2><Bot />Codex CLI 隐私边界</h2><StatusBadge tone="neutral">逐次确认</StatusBadge></div><div className="privacy-grid"><PrivacyItem ok text="只发送直接构造的白名单 DTO" /><PrivacyItem ok text="不发送原始 PDF、完整正文或私人路径" /><PrivacyItem ok text="不发送姓名、电话、证件号或完整保单号" /><PrivacyItem ok text="单段 ≤600 字，最多 12 段，总计 ≤7200 字" /><PrivacyItem ok text="不覆盖模型、Provider、登录或认证配置" /><PrivacyItem ok text="AI 结果只保存为 DRAFT 或用户接受的笔记" /></div><div className="notice warning"><CircleAlert size={18} />Codex 进程拥有当前 Windows 用户权限；工作目录、临时目录和只读 sandbox 只能作为纵深防御，不是保密边界。</div></Card></div>}</>;
}

export function PrivacyItem({ ok, text }: { ok: boolean; text: string }) { return <div className="privacy-item">{ok ? <Check /> : <CircleAlert />}<span>{text}</span></div>; }
