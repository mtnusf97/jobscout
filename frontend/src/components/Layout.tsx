import { Briefcase, LayoutDashboard, Settings as SettingsIcon, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "./ui";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/profiles", label: "Profiles", icon: Users, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
];

export default function Layout() {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 text-zinc-400">
        <div className="flex items-center gap-2 px-5 py-5">
          <Briefcase className="h-5 w-5 text-indigo-400" />
          <span className="text-lg font-semibold tracking-tight text-white">JobScout</span>
        </div>
        <nav className="space-y-1 px-3">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium",
                  isActive ? "bg-zinc-800 text-white" : "hover:bg-zinc-900 hover:text-zinc-100",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-5 py-4 text-xs text-zinc-600">
          Phase 7 · scheduler
        </div>
      </aside>
      <main className="flex-1 px-8 py-8">
        <div className="mx-auto max-w-4xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
