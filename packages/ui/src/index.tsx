import type { HTMLAttributes, PropsWithChildren } from "react";

export const tokens = {
  color: {
    primary: "#1677ff",
    primaryDeep: "#0b5de8",
    text: "#162033",
    secondaryText: "#667085",
    background: "#f5f8fc",
    surface: "#ffffff",
    border: "#e6ecf3",
    success: "#18a566",
    warning: "#f59e0b",
    danger: "#e5484d",
    stale: "#73839a"
  },
  radius: { small: 10, medium: 14, large: 20 }
} as const;

export function Card({ children, className = "", ...props }: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) {
  return <section className={`pl-card ${className}`.trim()} {...props}>{children}</section>;
}

export function StatusBadge({ tone, children }: PropsWithChildren<{ tone: "success" | "warning" | "danger" | "neutral" | "info" }>) {
  return <span className={`pl-badge pl-badge--${tone}`}><span aria-hidden="true" className="pl-badge__dot" />{children}</span>;
}
