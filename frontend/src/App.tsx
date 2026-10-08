import { useEffect, useState } from "react"; import { LayoutDashboard, FolderOpen, Settings, Scissors } from "lucide-react";
import Home from "./pages/Home"; import Project from "./pages/Project";
const useHash = () => { const [h, setH] = useState(location.hash); useEffect(() => { const f = () => setH(location.hash); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []); return h; };
export default function App() {
  const hash = useHash(); const m = hash.match(/^#\/project\/(\w+)/);
  const nav = [[LayoutDashboard, "Dashboard", "#/"], [FolderOpen, "Projects", "#/"], [Settings, "Settings", "#/settings"]] as const;
  return (<div className="flex min-h-screen">
    <aside className="hidden w-56 shrink-0 border-r border-line p-4 md:block">
      <div className="mb-8 flex items-center gap-2 font-semibold tracking-widest"><Scissors size={18} className="text-accent" />CLIPPER</div>
      {nav.map(([I, l, h]) => <a key={l} href={h} className="mb-1 flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-zinc-400 hover:bg-white/5 hover:text-white"><I size={16} />{l}</a>)}
    </aside>
    <main className="flex-1 p-4 md:p-8">
      {m ? <Project id={m[1]} /> : hash === "#/settings" ? <p className="text-zinc-400">Settings are configured in <code>.env</code> (provider, Whisper model, storage). A settings UI is not implemented yet.</p> : <Home />}
    </main></div>);
}
