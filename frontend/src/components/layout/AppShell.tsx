import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Target,
  Building2,
  Users,
  Sparkles,
  Mail,
  Send,
  Inbox,
  MessageSquare,
  FlaskConical,
  Download,
  ThumbsUp,
  Sliders,
  ShieldCheck,
  PlayCircle,
  Workflow,
  CalendarClock,
  LineChart,
  BookOpen,
  Ban,
  Settings,
  Brain,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/state/authStore";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { RunPipelineButton } from "./RunPipelineButton";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/icps", label: "ICPs", icon: Target },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/contacts", label: "Contacts", icon: Users },
  { to: "/leads", label: "Leads", icon: Sparkles },
  { to: "/outreach", label: "Outreach", icon: Send },
  { to: "/quality", label: "Quality", icon: ShieldCheck },
  { to: "/sends", label: "Sends", icon: Inbox },
  { to: "/replies", label: "Replies", icon: MessageSquare },
  { to: "/experiments", label: "Experiments", icon: FlaskConical },
  { to: "/exports", label: "Exports", icon: Download },
  { to: "/feedback", label: "Feedback", icon: ThumbsUp },
  { to: "/tuning", label: "Tuning", icon: Sliders },
  { to: "/email-drafts", label: "Email Drafts", icon: Mail },
  { to: "/templates", label: "Templates", icon: Workflow },
  { to: "/schedules", label: "Schedules", icon: CalendarClock },
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/reasoning", label: "Reasoning", icon: Brain },
  { to: "/pipeline-dashboard", label: "Pipeline Dashboard", icon: LineChart },
  { to: "/pipeline-runs", label: "Pipeline Runs", icon: PlayCircle },
  { to: "/knowledge", label: "Knowledge Base", icon: BookOpen },
  { to: "/suppression", label: "Suppression", icon: Ban },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const initials = (user?.full_name || user?.email || "U")
    .split(/\s+|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]!.toUpperCase())
    .join("");
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="w-60 shrink-0 border-r border-border bg-card/40 p-4 flex flex-col gap-2">
        <div className="text-lg font-semibold mb-4">GTM Automation</div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex-1 flex flex-col">
        <header className="h-14 border-b border-border flex items-center justify-between px-6 gap-4">
          <ProjectSwitcher />
          <div className="flex items-center gap-3">
            <RunPipelineButton />
            <div className="flex items-center gap-2 text-sm">
              <div
                className="h-8 w-8 rounded-full bg-primary/30 flex items-center justify-center text-xs font-semibold"
                title={user?.email}
              >
                {initials}
              </div>
              <div className="hidden md:flex flex-col leading-tight">
                <span className="font-medium text-xs">
                  {user?.full_name || user?.email}
                </span>
                <span className="text-[10px] text-muted-foreground capitalize">
                  {user?.role}
                </span>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={logout}
                title="Sign out"
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </header>
        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
