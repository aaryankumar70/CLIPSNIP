import { useEffect, useRef, useState } from "react"; import { Check, Circle, Loader2, Download, Pencil } from "lucide-react";
import { api } from "../services/api"; import { fmt, type Clip, type Job, type Segment } from "../types"; import Editor from "../components/Editor";
const STAGES: [string, string][] = [["ingesting", "Video received"], ["audio", "Extracting audio"], ["transcribing", "Transcribing speech"], ["analyzing", "Finding important moments"], ["clips", "Generating clips & captions"]];
export default function Project({ id }: { id: string }) {
  const [job, setJob] = useState<Job | null>(null); const [err, setErr] = useState(""); const [tab, setTab] = useState<"clips" | "transcript">("clips");
  const [clips, setClips] = useState<Clip[]>([]); const [sort, setSort] = useState("score"); const [segs, setSegs] = useState<Segment[]>([]); const [edit, setEdit] = useState<Clip | null>(null); const vid = useRef<HTMLVideoElement>(null);
  useEffect(() => { let on = true; const t = setInterval(() => api.job(id).then(j => on && setJob(j)).catch(e => setErr(e.message)), 1500); api.job(id).then(setJob).catch(e => setErr(e.message)); return () => { on = false; clearInterval(t); }; }, [id]);
  const loadClips = () => api.clips(id, sort).then(setClips).catch(() => {});
  useEffect(() => { if (job?.status === "completed") { loadClips(); api.transcript(id).then(t => setSegs(t.segments)); } }, [job?.status, sort]);
  useEffect(() => { if (!clips.some(c => c.render_status === "rendering")) return; const t = setInterval(loadClips, 2000); return () => clearInterval(t); }, [clips]);
  if (err) return <p className="text-red-400">{err}</p>; if (!job) return <Loader2 className="animate-spin" />;
  if (job.status === "failed") return <div className="panel max-w-xl p-6"><h2 className="mb-2 text-lg">Processing failed</h2><p className="text-red-400">{job.error}</p><a href="#/" className="btn btn-ghost mt-4">Back</a></div>;
  if (job.status !== "completed") { const cur = STAGES.findIndex(s => s[0] === job.stage);
    return (<div className="panel mx-auto max-w-xl p-6"><h2 className="mb-1 tracking-widest">ANALYZING</h2>
      <p className="mb-4 text-xs text-zinc-500">{Math.round(job.progress)}% · {Math.round(job.elapsed)}s elapsed{job.duration ? ` · video ${fmt(job.duration)}` : ""}</p>
      <div className="mb-5 h-1.5 overflow-hidden rounded bg-white/10"><div className="h-full bg-accent transition-all" style={{ width: `${job.progress}%` }} /></div>
      {STAGES.map(([k, l], i) => <div key={k} className="flex items-center gap-3 py-1.5 text-sm">{i < cur ? <Check size={16} className="text-green-400" /> : i === cur ? <Loader2 size={16} className="animate-spin text-accent" /> : <Circle size={16} className="text-zinc-600" />}<span className={i > cur ? "text-zinc-600" : ""}>{l}</span></div>)}</div>); }
  return (<div><div className="mb-4 flex flex-wrap items-center gap-3"><h1 className="mr-auto truncate text-xl">{job.name}</h1>
    {(["clips", "transcript"] as const).map(t => <button key={t} className={`btn ${tab === t ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab(t)}>{t === "clips" ? "Clips" : "Transcript"}</button>)}</div>
    {tab === "clips" ? <>
      <div className="mb-4 flex items-center justify-between"><p className="text-xs text-zinc-500">AI Clip Score is the model's estimate of content quality, not a prediction of virality.</p>
        <select className="input" value={sort} onChange={e => setSort(e.target.value)}><option value="score">Highest Score</option><option value="newest">Newest</option><option value="longest">Longest</option><option value="shortest">Shortest</option></select></div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{clips.map(c => <div key={c.id} className="panel overflow-hidden">
        {c.video_url ? <video src={c.video_url} poster={c.thumb_url ?? undefined} controls preload="none" className="aspect-video w-full bg-black object-contain" /> : <div className="grid aspect-video place-items-center bg-black text-xs text-zinc-500">{c.render_status === "failed" ? c.render_error : c.render_status}</div>}
        <div className="p-3"><h3 className="truncate font-medium">{c.title}</h3><p className="mt-1 text-xs text-zinc-500">AI Score {Math.round(c.score)} · {c.category} · {fmt(c.start)} — {fmt(c.end)}</p><p className="mt-1 line-clamp-2 text-xs text-zinc-400">{c.reason}</p>
          <div className="mt-3 flex gap-2"><button className="btn btn-ghost" onClick={() => setEdit(c)}><Pencil size={14} />Edit</button>
            <a className={`btn btn-ghost ${c.video_url ? "" : "pointer-events-none opacity-40"}`} href={`/api/clips/${c.id}/download`}><Download size={14} />Download</a></div></div></div>)}</div></> :
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]"><video ref={vid} src={`/api/jobs/${id}/source`} controls className="w-full rounded-xl bg-black" />
        <div className="panel max-h-[70vh] overflow-y-auto p-2">{segs.map((s, i) => <button key={i} onClick={() => { if (vid.current) { vid.current.currentTime = s.start; vid.current.play(); } }} className="block w-full rounded-lg p-2 text-left text-sm hover:bg-white/5"><span className="mr-2 text-xs text-accent">{fmt(s.start).slice(3)}</span>{s.text}</button>)}</div></div>}
    {edit && <Editor clip={edit} duration={job.duration ?? 0} onClose={() => { setEdit(null); loadClips(); }} />}
  </div>);
}
