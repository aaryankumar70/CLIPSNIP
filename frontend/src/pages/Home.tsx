import { useEffect, useRef, useState } from "react"; import { Upload, Sparkles, Trash2 } from "lucide-react";
import { api } from "../services/api"; import type { Job } from "../types";
export default function Home() {
  const [url, setUrl] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const [jobs, setJobs] = useState<Job[]>([]); const file = useRef<HTMLInputElement>(null);
  const load = () => api.jobs().then(setJobs).catch(() => {}); useEffect(() => { load(); }, []);
  const start = async (f?: File) => { setErr(""); setBusy(true); try { const { id } = await api.create(f ? { file: f } : { url: url.trim() }); location.hash = `#/project/${id}`; } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  return (<div className="mx-auto max-w-3xl pt-10">
    <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">Turn Long Videos Into Short-Form Content</h1>
    <p className="mt-3 text-zinc-400">Find the best moments, generate captions, and create ready-to-post clips automatically.</p>
    <div className="panel mt-8 p-4"><div className="flex flex-col gap-2 sm:flex-row">
      <input className="input flex-1" placeholder="Paste a direct link to an authorized video file (.mp4, .mov...)" value={url} onChange={e => setUrl(e.target.value)} />
      <button className="btn btn-primary" disabled={busy || !url.trim()} onClick={() => start()}><Sparkles size={16} />Analyze Video</button></div>
      <div className="my-3 text-center text-xs text-zinc-500">OR</div>
      <input ref={file} type="file" accept="video/*" hidden onChange={e => e.target.files?.[0] && start(e.target.files[0])} />
      <button className="btn btn-ghost w-full justify-center" disabled={busy} onClick={() => file.current?.click()}><Upload size={16} />Upload Video</button>
      {err && <p className="mt-3 text-sm text-red-400">{err}</p>}
      <p className="mt-3 text-xs text-zinc-500">For videos you own or are authorized to process. Videos and clips are stored locally on this machine. YouTube page links are not downloaded; upload the file instead.</p></div>
    <div className="mt-6 grid grid-cols-2 gap-2 text-xs tracking-widest text-zinc-500 md:grid-cols-4">{["AI CLIPPING", "AUTOMATIC CAPTIONS", "CENTER REFRAMING", "MULTI-FORMAT EXPORT"].map(t => <div key={t} className="panel p-3 text-center">{t}</div>)}</div>
    {jobs.length > 0 && <div className="mt-10"><h2 className="mb-3 text-sm tracking-widest text-zinc-500">PROJECTS</h2>
      {jobs.map(j => <div key={j.id} className="panel mb-2 flex items-center justify-between p-3"><a href={`#/project/${j.id}`} className="flex-1 truncate hover:text-white">{j.name}</a>
        <span className="mx-3 text-xs text-zinc-500">{j.status}</span><button title="Delete Project" onClick={() => confirm("Delete this project and all its files?") && api.remove(j.id).then(load)}><Trash2 size={15} className="text-zinc-500 hover:text-red-400" /></button></div>)}</div>}
  </div>);
}
