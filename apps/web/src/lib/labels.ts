export const lines: Record<string, string> = { MEDICAL: "医疗险", ACCIDENT: "意外险", HUIMIN: "惠民保", CRITICAL_ILLNESS: "重疾险", ANNUITY: "年金险", LIFE_SAVINGS: "储蓄险", LIFE: "寿险", PET: "宠物险", OTHER: "其他", UNKNOWN: "类别待确认" };
export const relations: Record<string, string> = { SELF: "我自己", PARENT: "父母", PARTNER: "伴侣", CHILD: "子女", OTHER: "其他家人" };
export const coverageStates: Record<string, string> = { UNKNOWN: "状态待确认", SCHEDULED: "尚未生效", IN_PERIOD: "登记期间内", ENDED: "登记期间已结束", ARCHIVED: "已归档" };
export const policyStatuses: Record<string, string> = { DRAFT: "先记下，状态待确认", ACTIVE: "已核对保障期间", EXPIRED: "已确认终止", ARCHIVED: "历史归档" };
export const frequencies: Record<string, string> = { MONTHLY: "月缴", QUARTERLY: "季缴", SEMI_ANNUAL: "半年缴", ANNUAL: "年缴", SINGLE: "一次缴清" };
export function today() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
export function amount(value: string | null | undefined, currency = "CNY") { return value == null ? "尚未登记" : `${currency} ${Number(value).toLocaleString("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`; }
