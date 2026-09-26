"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { ClipboardCheck, Hammer, KeyRound, Lightbulb, MessageSquare, Moon, Radio, Rocket, ShieldCheck, SlidersHorizontal, Sun } from "lucide-react";

import { Switch } from "@/components/ui/switch";
import { setUseMocks, isMockMode } from "@/lib/api";
import { useConnectionState } from "@/lib/useEvents";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/onboarding", label: "Get started", icon: Rocket },
  { href: "/", label: "Tool shop", icon: Hammer },
  { href: "/suggestions", label: "Suggestions", icon: Lightbulb },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/connectors", label: "Connected apps", icon: KeyRound },
  { href: "/capture", label: "Capture & privacy", icon: Radio },
  { href: "/policy", label: "Policy & metrics", icon: ShieldCheck },
  { href: "/demo", label: "Demo controls", icon: SlidersHorizontal },
];

const noopSubscribe = () => () => {};

export function AppSidebar() {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const connection = useConnectionState();
  // Client-only values (localStorage, theme) render after hydration to avoid mismatches.
  const mounted = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const mocks = mounted && isMockMode();

  const toggleMocks = (value: boolean) => {
    setUseMocks(value);
    window.location.reload();
  };

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Hammer className="size-4" />
        </div>
        <span className="font-semibold tracking-tight">ToolSmith</span>
      </div>
      <nav className="flex flex-col gap-0.5 px-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" || pathname.startsWith("/tools") : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent",
                active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto flex flex-col gap-3 border-t px-4 py-4 text-xs text-muted-foreground">
        <div className="flex items-center justify-between">
          <span>Live events</span>
          <span className="flex items-center gap-1.5">
            <span
              className={cn(
                "size-2 rounded-full",
                connection === "open" && "bg-emerald-500",
                connection === "mock" && "bg-amber-500",
                connection === "connecting" && "bg-muted-foreground",
                connection === "error" && "bg-red-500",
              )}
            />
            {connection}
          </span>
        </div>
        {mounted && (
          <>
            <label className="flex items-center justify-between">
              <span>Use mock data</span>
              <Switch checked={mocks} onCheckedChange={toggleMocks} aria-label="Use mock data" />
            </label>
            <button
              type="button"
              className="flex items-center gap-2 hover:text-foreground"
              onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            >
              {resolvedTheme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
              {resolvedTheme === "dark" ? "Light mode" : "Dark mode"}
            </button>
          </>
        )}
      </div>
    </aside>
  );
}
