"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  MessageSquare,
  FlaskConical,
  FolderOpen,
  Sparkles,
  Brain,
  ListChecks,
} from "lucide-react";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/evals", label: "Evals", icon: FlaskConical },
  { href: "/cases", label: "Cases", icon: FolderOpen },
  { href: "/adapt", label: "Adapt", icon: Sparkles },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-16 shrink-0 flex-col bg-[var(--sidebar)] text-[var(--sidebar-foreground)] md:w-60">
      <div className="flex items-center justify-center gap-2.5 px-3 py-5 md:justify-start md:px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--sidebar-primary)]">
          <Brain className="h-4 w-4 text-[var(--sidebar-primary-foreground)]" />
        </div>
        <h1 className="hidden text-base font-bold tracking-tight md:block">
          Adaptive Agent
        </h1>
      </div>
      <nav className="flex-1 space-y-0.5 px-3">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center justify-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all md:justify-start",
                isActive
                  ? "bg-[var(--sidebar-primary)] text-[var(--sidebar-primary-foreground)]"
                  : "text-[var(--sidebar-foreground)]/60 hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-foreground)]"
              )}
              aria-label={item.label}
            >
              <item.icon className="h-4 w-4" />
              <span className="hidden md:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="hidden border-t border-[var(--sidebar-border)] px-5 py-4 md:block">
        <p className="text-[11px] text-[var(--sidebar-foreground)]/40 tracking-wide uppercase">
          Self-Improving Loop v0.1
        </p>
      </div>
    </aside>
  );
}
