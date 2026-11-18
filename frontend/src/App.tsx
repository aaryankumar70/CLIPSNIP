import React, { useEffect, useState } from "react";
import { LayoutDashboard, Settings as SettingsIcon, Scissors, AlertTriangle, X, CheckCircle2, RefreshCw } from "lucide-react";
import Home from "./pages/Home";
import Project from "./pages/Project";
import Settings from "./pages/Settings";
import { ToastProvider, useToast } from "./context/ToastContext";
import { api } from "./services/api";
import type { HealthStatus, YouTubeStatus } from "./types";

const useHash = () => {
  const [h, setH] = useState(location.hash || "#/");
  useEffect(() => {
    const f = () => setH(location.hash || "#/");
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return h;
};

function MainLayout() {
  const hash = useHash();
  const m = hash.match(/^#\/project\/([a-zA-Z0-9_-]+)/);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [ytStatus, setYtStatus] = useState<YouTubeStatus | null>(null);
  const [dismissHealth, setDismissHealth] = useState(false);
  const [checkingHealth, setCheckingHealth] = useState(false);

  const checkHealth = async () => {
    setCheckingHealth(true);
    try {
      const [h, yt] = await Promise.all([
        api.health().catch(() => ({ ok: false, warnings: ["Backend server is unreachable"] })),
        api.youtubeStatus().catch(() => null),
      ]);
      setHealth(h);
      if (yt) setYtStatus(yt);
    } catch {
      setHealth({ ok: false, warnings: ["Backend server is unreachable"] });
    } finally {
      setCheckingHealth(false);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const nav = [
    { icon: LayoutDashboard, label: "Dashboard", href: "#/" },
    { icon: SettingsIcon, label: "Settings", href: "#/settings" },
  ];

  const currentTab = m ? "project" : hash === "#/settings" ? "settings" : "dashboard";

  return (
    <div className="flex min-h-screen bg-bg text-zinc-100 flex-col md:flex-row">
      {/* Sidebar */}
      <aside className="w-full md:w-60 shrink-0 border-b md:border-b-0 md:border-r border-line p-4 bg-surface/50 backdrop-blur flex md:flex-col justify-between md:justify-start">
        <div className="flex items-center justify-between w-full md:w-auto md:mb-8">
          <a href="#/" className="flex items-center gap-2.5 font-bold tracking-wider text-base text-white hover:opacity-90">
            <div className="p-1.5 rounded-lg bg-accent/20 text-accent border border-accent/30">
              <Scissors size={20} />
            </div>
            <span>CLIPSNIP</span>
          </a>
          {/* Mobile nav triggers */}
          <div className="flex items-center gap-2 md:hidden">
            {nav.map(({ icon: Icon, label, href }) => {
              const active = (href === "#/" && currentTab === "dashboard") || (href === "#/settings" && currentTab === "settings");
              return (
                <a
                  key={label}
                  href={href}
                  className={`p-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${
                    active ? "bg-accent text-white" : "text-zinc-400 hover:text-white hover:bg-white/5"
                  }`}
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </a>
              );
            })}
          </div>
        </div>

        {/* Desktop Nav */}
        <nav className="hidden md:flex flex-col gap-1.5">
          {nav.map(({ icon: Icon, label, href }) => {
            const active = (href === "#/" && currentTab === "dashboard") || (href === "#/settings" && currentTab === "settings");
            return (
              <a
                key={label}
                href={href}
                className={`flex items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-all ${
                  active ? "bg-accent/15 text-accent border border-accent/30 shadow-sm" : "text-zinc-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon size={18} />
                <span>{label}</span>
              </a>
            );
          })}
        </nav>

        <div className="hidden md:block mt-auto pt-6 border-t border-line/60 text-xs text-zinc-500">
          {/* YouTube Channel status */}
          <div className="mb-3 pb-3 border-b border-line/40">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium text-zinc-400">YouTube Studio</span>
              {ytStatus?.authenticated ? (
                <span className="text-[10px] text-emerald-400 font-semibold uppercase">Linked</span>
              ) : ytStatus?.has_client_secret ? (
                <span className="text-[10px] text-blue-400 font-semibold uppercase">Ready</span>
              ) : (
                <span className="text-[10px] text-zinc-500 font-semibold uppercase">No Key</span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <span
                className={`w-2 h-2 rounded-full ${
                  ytStatus?.authenticated
                    ? "bg-emerald-500"
                    : ytStatus?.has_client_secret
                    ? "bg-blue-500"
                    : "bg-zinc-600"
                }`}
              />
              <span className="text-zinc-400">
                {ytStatus?.authenticated
                  ? "Connected"
                  : ytStatus?.has_client_secret
                  ? "Authorize on Dashboard"
                  : "Needs client_secret.json"}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between mb-1">
            <span>System Status</span>
            <button
              onClick={checkHealth}
              disabled={checkingHealth}
              className="text-zinc-400 hover:text-white transition"
              title="Refresh health"
            >
              <RefreshCw size={12} className={checkingHealth ? "animate-spin" : ""} />
            </button>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                health?.ok && (!health.warnings || health.warnings.length === 0)
                  ? "bg-emerald-500"
                  : health?.ok
                  ? "bg-amber-500"
                  : "bg-rose-500"
              }`}
            />
            <span className="text-zinc-400">
              {health?.ok && (!health.warnings || health.warnings.length === 0)
                ? "All systems ready"
                : health?.ok
                ? "Warnings present"
                : "Offline / Service error"}
            </span>
          </div>
          {health?.disk_free_gb !== undefined && (
            <p className="mt-1 text-[11px] text-zinc-500">Free disk: {health.disk_free_gb.toFixed(1)} GB</p>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Health warning banner */}
        {health?.warnings && health.warnings.length > 0 && !dismissHealth && (
          <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2.5 flex items-center justify-between text-xs text-amber-300">
            <div className="flex items-center gap-2">
              <AlertTriangle size={15} className="shrink-0 text-amber-400" />
              <span>{health.warnings.join(" • ")}</span>
            </div>
            <button
              onClick={() => setDismissHealth(true)}
              className="text-amber-400/70 hover:text-amber-200 p-1"
              title="Dismiss warning"
            >
              <X size={14} />
            </button>
          </div>
        )}

        <div className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto">
          {m ? <Project id={m[1]} /> : hash === "#/settings" ? <Settings /> : <Home />}
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <MainLayout />
    </ToastProvider>
  );
}
