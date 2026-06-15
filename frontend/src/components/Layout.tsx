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
    <div className="min-h-screen md:flex">
      {/* Left rail on desktop, sticky top bar on mobile */}
      <aside className="sticky top-0 z-10 flex flex-col border-b border-zinc-800 bg-zinc-950 text-zinc-400 md:static md:w-60 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-4 py-3 md:px-5 md:py-5">
          <Briefcase className="h-5 w-5 text-indigo-400" />
          <span className="text-lg font-semibold tracking-tight text-white">JobScout</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:pb-0">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium",
                  isActive ? "bg-zinc-800 text-white" : "hover:bg-zinc-900 hover:text-zinc-100",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden px-5 py-4 text-xs text-zinc-600 md:block">
          Phase 7 · scheduler
        </div>
      </aside>
      <main className="flex-1 px-4 py-6 sm:px-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-4xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
