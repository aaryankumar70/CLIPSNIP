import { useEffect, useState } from "react"; import { X } from "lucide-react";
import { api } from "../services/api"; import { fmt, type Clip } from "../types";
export default function Editor({ clip, duration, onClose }: { clip: Clip; duration: number; onClose: () => void }) {
  const [c, setC] = useState<Clip>(clip); const [start, setStart] = useState(clip.start); const [end, setEnd] = useState(clip.end); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (c.render_status !== "rendering") return; const t = setInterval(() => api.clip(c.id).then(n => { setC(n); if (n.render_status !== "rendering") setBusy(false); }), 1500); return () => clearInterval(t); }, [c]);
  const submit = async () => { setErr(""); setBusy(true); try { await api.patch(c.id, { start, end, title: c.title, caption_style: c.caption_style, aspect: c.aspect }); await api.render(c.id); setC({ ...c, render_status: "rendering" }); } catch (e) { setErr((e as Error).message); setBusy(false); } };
  const num = (v: number, f: (n: number) => void) => <input type="number" step="0.1" className="input w-28" value={v} onChange={e => f(parseFloat(e.target.value) || 0)} />;
  return (<div className="fixed inset-0 z-10 grid place-items-center bg-black/70 p-4"><div className="panel grid max-h-full w-full max-w-4xl gap-5 overflow-y-auto p-5 md:grid-cols-2">
    <div>{c.video_url && c.render_status === "ready" ? <video key={c.video_url + start + end} src={c.video_url} controls className="max-h-[60vh] w-full rounded-lg bg-black" /> : <div className="grid aspect-video place-items-center rounded-lg bg-black text-sm text-zinc-500">{c.render_status === "rendering" ? "Rendering…" : "Preview updates after rendering"}</div>}
      <div className="mt-4"><input type="range" min={0} max={duration} step={0.1} value={start} onChange={e => setStart(Math.min(parseFloat(e.target.value), end - 1))} className="w-full" /><input type="range" min={0} max={duration} step={0.1} value={end} onChange={e => setEnd(Math.max(parseFloat(e.target.value), start + 1))} className="w-full" />
        <p className="text-xs text-zinc-500">{fmt(start)} — {fmt(end)} · {(end - start).toFixed(1)}s</p></div></div>
    <div className="space-y-3 text-sm"><div className="flex justify-between"><h2 className="text-lg">Edit clip</h2><button onClick={onClose}><X size={18} /></button></div>
      <label className="block">Title<input className="input mt-1 w-full" value={c.title} onChange={e => setC({ ...c, title: e.target.value })} /></label>
      <p className="text-xs text-zinc-500">{c.category} · AI Score {Math.round(c.score)}</p>
      <div className="flex gap-3"><label>Start (s){num(start, setStart)}</label><label>End (s){num(end, setEnd)}</label></div>
      <label className="block">Caption style<select className="input mt-1 w-full" value={c.caption_style} onChange={e => setC({ ...c, caption_style: e.target.value })}>{["classic", "bold", "highlight", "creator", "minimal", "off"].map(s => <option key={s}>{s}</option>)}</select></label>
      <label className="block">Aspect ratio<select className="input mt-1 w-full" value={c.aspect} onChange={e => setC({ ...c, aspect: e.target.value })}>{["9:16", "1:1", "16:9"].map(s => <option key={s}>{s}</option>)}</select></label>
      <p className="text-xs text-zinc-500">Vertical and square use a center crop (no subject tracking yet).</p>
      {(err || c.render_error) && <p className="text-red-400">{err || c.render_error}</p>}
      <button className="btn btn-primary" disabled={busy} onClick={submit}>{busy ? "Rendering…" : "Render Clip"}</button></div></div></div>);
}
