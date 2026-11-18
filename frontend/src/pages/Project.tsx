import { useEffect, useRef, useState } from "react";
import {
  Check,
  Circle,
  Loader2,
  Download,
  Pencil,
  Upload,
  Archive,
  ExternalLink,
  Youtube,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import { fmt, type Clip, type Job, type Segment, type YouTubeStatus } from "../types";
import Editor from "../components/Editor";

const STAGES: [string, string][] = [
  ["ingesting", "Video Download & Ingest"],
  ["transcribing", "Speech Transcription (json3 / Whisper)"],
  ["analyzing", "AI Clip Selection & Scoring"],
  ["metadata", "Shorts Metadata Generation"],
  ["clips", "Video Re-encoding & ASS Captions"],
];

export default function Project({ id }: { id: string }) {
  const { toast } = useToast();
  const [job, setJob] = useState<Job | null>(null);
  const [tab, setTab] = useState<"clips" | "transcript">("clips");
  const [clips, setClips] = useState<Clip[]>([]);
  const [sort, setSort] = useState("score");
  const [segs, setSegs] = useState<Segment[]>([]);
  const [editClip, setEditClip] = useState<Clip | null>(null);
  const vidRef = useRef<HTMLVideoElement>(null);

  // Multi-select & Upload state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [ytStatus, setYtStatus] = useState<YouTubeStatus | null>(null);
  const [uploadPrivacy, setUploadPrivacy] = useState<"public" | "unlisted" | "private">("public");
  const [useSpread, setUseSpread] = useState(false);
  const [spreadMinutes, setSpreadMinutes] = useState(60);
  const [uploadingBulk, setUploadingBulk] = useState(false);

  // Poll project status
  useEffect(() => {
    let active = true;
    const fetchJob = () => {
      api.job(id)
        .then(j => active && setJob(j))
        .catch(e => toast.error(e.message));
    };
    fetchJob();
    const interval = setInterval(fetchJob, 2500);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [id]);

  const loadClips = () => {
    api.clips(id, sort)
      .then(setClips)
      .catch(() => {});
  };

  const loadYtStatus = () => {
    api.youtubeStatus()
      .then(setYtStatus)
      .catch(() => {});
  };

  useEffect(() => {
    loadYtStatus();
  }, []);

  useEffect(() => {
    if (job?.status === "completed") {
      loadClips();
      api.transcript(id)
        .then(t => setSegs(t.segments || []))
        .catch(() => {});
    }
  }, [job?.status, sort]);

  // Poll clips when any clip is rendering or uploading
  useEffect(() => {
    const hasActiveRendering = clips.some(c => c.render_status === "rendering");
    const hasActiveUploads = clips.some(c => c.youtube_status === "uploading" || c.youtube_status === "queued");
    if (!hasActiveRendering && !hasActiveUploads) return;

    const interval = setInterval(loadClips, 2500);
    return () => clearInterval(interval);
  }, [clips]);

  const handleSelectAll = () => {
    if (selectedIds.size === clips.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(clips.map(c => c.id)));
    }
  };

  const toggleSelect = (cid: string) => {
    const next = new Set(selectedIds);
    if (next.has(cid)) next.delete(cid);
    else next.add(cid);
    setSelectedIds(next);
  };

  const handleConnectYouTube = async () => {
    try {
      toast.info("Starting YouTube authorization...");
      const res = await api.youtubeConnect();
      if (res.auth_url) {
        window.open(res.auth_url, "_blank");
        toast.info("Opened authorization window. Please grant permissions and return here.");
      }
      let attempts = 0;
      const interval = setInterval(async () => {
        attempts++;
        try {
          const s = await api.youtubeStatus();
          setYtStatus(s);
          if (s.authenticated) {
            clearInterval(interval);
            toast.success("Successfully connected to YouTube!");
          } else if (attempts > 60) {
            clearInterval(interval);
          }
        } catch {
          // ignore transient poll error
        }
      }, 2000);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleDisconnectYouTube = async () => {
    try {
      await api.youtubeDisconnect();
      toast.info("Disconnected from YouTube");
      loadYtStatus();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleUploadSingle = async (clipId: string) => {
    try {
      await api.uploadClip(clipId, { privacy_status: uploadPrivacy });
      toast.info("Clip added to YouTube upload queue");
      loadClips();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleUploadBulk = async (onlySelected: boolean) => {
    const targetClipIds = onlySelected ? Array.from(selectedIds) : undefined;
    if (onlySelected && (!targetClipIds || targetClipIds.length === 0)) {
      toast.error("No clips selected");
      return;
    }

    setUploadingBulk(true);
    try {
      const res = await api.uploadAll(id, {
        privacy_status: uploadPrivacy,
        spread_minutes: useSpread ? spreadMinutes : 0,
        clip_ids: targetClipIds,
      });
      toast.success(
        res.spread_minutes > 0
          ? `Queued ${res.count} clips spaced ${res.spread_minutes}m apart`
          : `Queued ${res.count} clips for YouTube upload`
      );
      loadClips();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUploadingBulk(false);
    }
  };

  if (!job) {
    return (
      <div className="flex h-64 items-center justify-center text-zinc-500">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  // Processing View
  if (job.status !== "completed") {
    const curIdx = STAGES.findIndex(s => s[0] === job.stage);
    return (
      <div className="panel mx-auto max-w-xl p-8 my-10 shadow-2xl">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-bold tracking-tight text-white uppercase">
            {job.status === "failed" ? "Processing Failed" : "Processing Video"}
          </h2>
          <span className="text-xs font-mono text-accent">
            {job.status === "failed" ? "ERROR" : `${Math.round(job.progress)}%`}
          </span>
        </div>

        <p className="text-xs text-zinc-400 mb-6">
          {job.name} · {job.duration ? `Length ${fmt(job.duration)} · ` : ""}
          {Math.round(job.elapsed)}s elapsed
          {job.eta ? ` · ~${Math.round(job.eta)}s remaining` : ""}
        </p>

        {job.status === "failed" ? (
          <div className="rounded-lg border border-red-500/30 bg-red-950/40 p-4 mb-6 text-sm text-red-300">
            <p className="font-medium mb-1">Failed to process video:</p>
            <p className="text-xs text-red-400 font-mono break-words">{job.error}</p>
          </div>
        ) : (
          <div className="mb-6 h-2 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full bg-accent transition-all duration-300"
              style={{ width: `${Math.max(4, job.progress)}%` }}
            />
          </div>
        )}

        <div className="space-y-3 mb-6">
          {STAGES.map(([k, label], i) => {
            const isDone = curIdx > i || job.status === "completed";
            const isCurrent = curIdx === i && job.status === "processing";
            return (
              <div key={k} className="flex items-center gap-3 text-sm">
                {isDone ? (
                  <Check size={16} className="text-green-400 shrink-0" />
                ) : isCurrent ? (
                  <Loader2 size={16} className="animate-spin text-accent shrink-0" />
                ) : (
                  <Circle size={16} className="text-zinc-600 shrink-0" />
                )}
                <span className={isDone ? "text-zinc-200" : isCurrent ? "text-accent font-medium" : "text-zinc-600"}>
                  {label}
                </span>
              </div>
            );
          })}
        </div>

        <div className="flex gap-3 pt-2">
          {job.status === "failed" && (
            <button
              onClick={() => api.retry(job.id).then(() => toast.info("Retrying job..."))}
              className="btn btn-primary text-xs"
            >
              <RotateCcw size={14} />
              Retry Job
            </button>
          )}
          <a href="#/" className="btn btn-ghost text-xs">
            Back to Queue
          </a>
        </div>
      </div>
    );
  }

  // Completed Project View
  const readyClips = clips.filter(c => c.render_status === "ready");

  return (
    <div className="pb-20">
      {/* Top Header & Navigation */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-white truncate max-w-xl">{job.name}</h1>
            <span className="px-2 py-0.5 rounded text-xs bg-green-500/10 text-green-400 border border-green-500/20 font-medium">
              {clips.length} clips
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400">
            Source duration: {job.duration ? fmt(job.duration) : "N/A"} · Processed in {Math.round(job.elapsed)}s
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-line bg-panel p-1">
            <button
              className={`rounded px-3 py-1 text-xs font-medium transition ${
                tab === "clips" ? "bg-accent text-black" : "text-zinc-400 hover:text-white"
              }`}
              onClick={() => setTab("clips")}
            >
              Clips ({clips.length})
            </button>
            <button
              className={`rounded px-3 py-1 text-xs font-medium transition ${
                tab === "transcript" ? "bg-accent text-black" : "text-zinc-400 hover:text-white"
              }`}
              onClick={() => setTab("transcript")}
            >
              Full Transcript
            </button>
          </div>

          <a
            href={`/api/projects/${id}/export`}
            download
            className="btn btn-ghost text-xs text-zinc-300 hover:text-white"
            title="Download ZIP with all clips and metadata.csv"
          >
            <Archive size={14} />
            Export ZIP
          </a>
        </div>
      </div>

      {tab === "clips" ? (
        <>
          {/* YouTube Integration Card & Bulk Actions Bar */}
          <div className="panel p-5 mb-8 border-line bg-panel/60">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
              <div className="flex items-center gap-3">
                <Youtube className="w-6 h-6 text-red-500 shrink-0" />
                <div>
                  <h3 className="text-sm font-semibold text-white">YouTube Upload Studio</h3>
                  <p className="text-xs text-zinc-400">
                    {ytStatus?.authenticated ? (
                      <span className="text-green-400 inline-flex items-center gap-1">
                        <CheckCircle2 size={12} /> Connected (OAuth Desktop App)
                      </span>
                    ) : ytStatus?.reconnect_needed ? (
                      <span className="text-yellow-400 inline-flex items-center gap-1">
                        <AlertTriangle size={12} /> OAuth Token Expired. Reconnect required.
                      </span>
                    ) : (
                      <span className="text-zinc-400">
                        Connect YouTube to upload Shorts directly from Clipper.
                      </span>
                    )}
                  </p>
                </div>
              </div>

              <div>
                {ytStatus?.authenticated ? (
                  <button
                    onClick={handleDisconnectYouTube}
                    className="btn btn-ghost text-xs text-zinc-400 hover:text-red-400"
                  >
                    Disconnect
                  </button>
                ) : (
                  <button
                    onClick={handleConnectYouTube}
                    className="btn btn-primary text-xs"
                  >
                    <Youtube size={14} />
                    {ytStatus?.reconnect_needed ? "Reconnect YouTube" : "Connect YouTube"}
                  </button>
                )}
              </div>
            </div>

            {/* Bulk Upload Controls */}
            {ytStatus?.authenticated && (
              <div className="pt-4 border-t border-line/60 flex flex-wrap items-center justify-between gap-4">
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-400">Privacy:</span>
                    <select
                      className="input py-1 text-xs"
                      value={uploadPrivacy}
                      onChange={e => setUploadPrivacy(e.target.value as any)}
                    >
                      <option value="public">Public</option>
                      <option value="unlisted">Unlisted</option>
                      <option value="private">Private</option>
                    </select>
                  </div>

                  <label className="flex items-center gap-2 cursor-pointer text-zinc-300">
                    <input
                      type="checkbox"
                      checked={useSpread}
                      onChange={e => setUseSpread(e.target.checked)}
                      className="rounded border-line bg-black/40 text-accent focus:ring-accent"
                    />
                    <span>Spread uploads every</span>
                  </label>

                  {useSpread && (
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min={5}
                        max={1440}
                        value={spreadMinutes}
                        onChange={e => setSpreadMinutes(parseInt(e.target.value) || 60)}
                        className="input w-16 py-1 text-xs"
                      />
                      <span className="text-zinc-400">min</span>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleUploadBulk(true)}
                    disabled={uploadingBulk || selectedIds.size === 0}
                    className="btn btn-ghost text-xs"
                  >
                    <Upload size={14} />
                    Upload Selected ({selectedIds.size})
                  </button>
                  <button
                    onClick={() => handleUploadBulk(false)}
                    disabled={uploadingBulk || readyClips.length === 0}
                    className="btn btn-primary text-xs"
                  >
                    <Upload size={14} />
                    Upload All ({readyClips.length})
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Clips Toolbar: Selection & Sorting */}
          <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
            <div className="flex items-center gap-3 text-xs">
              <button
                onClick={handleSelectAll}
                className="btn btn-ghost px-2.5 py-1 text-xs text-zinc-300"
              >
                {selectedIds.size === clips.length && clips.length > 0 ? "Deselect All" : "Select All"}
              </button>
              <span className="text-zinc-500">
                {selectedIds.size} of {clips.length} selected
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-400">Sort by:</span>
              <select
                className="input py-1 text-xs"
                value={sort}
                onChange={e => setSort(e.target.value)}
              >
                <option value="score">Highest AI Score</option>
                <option value="newest">Newest</option>
                <option value="longest">Longest</option>
                <option value="shortest">Shortest</option>
              </select>
            </div>
          </div>

          {/* Clips Grid */}
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {clips.map(c => {
              const isSelected = selectedIds.has(c.id);
              const durationS = Math.max(0, c.end - c.start);

              return (
                <div
                  key={c.id}
                  className={`panel overflow-hidden border transition flex flex-col ${
                    isSelected ? "border-accent ring-1 ring-accent" : "border-line"
                  }`}
                >
                  {/* Thumbnail / Video Preview */}
                  <div className="relative aspect-[9/16] bg-black max-h-[360px] overflow-hidden flex items-center justify-center">
                    {c.video_url && c.render_status === "ready" ? (
                      <video
                        src={c.video_url}
                        poster={c.thumb_url || undefined}
                        controls
                        preload="none"
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="text-center p-4 text-xs text-zinc-500">
                        {c.render_status === "rendering" ? (
                          <div className="flex flex-col items-center gap-1.5 text-accent">
                            <Loader2 className="animate-spin w-5 h-5" />
                            <span>Rendering...</span>
                          </div>
                        ) : c.render_status === "failed" ? (
                          <span className="text-red-400">{c.render_error || "Render failed"}</span>
                        ) : (
                          <span>Pending render</span>
                        )}
                      </div>
                    )}

                    {/* Card Checkbox */}
                    <div className="absolute top-2 left-2 z-10">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(c.id)}
                        className="w-5 h-5 rounded border-line bg-black/60 text-accent focus:ring-accent cursor-pointer"
                      />
                    </div>

                    {/* Duration badge */}
                    <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded text-xs bg-black/80 text-white font-mono">
                      {durationS.toFixed(1)}s
                    </div>
                  </div>

                  {/* Card Content */}
                  <div className="p-4 flex-1 flex flex-col justify-between space-y-3">
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-accent/10 text-accent border border-accent/20">
                          Score {Math.round(c.score)}
                        </span>
                        <span className="text-xs text-zinc-500 capitalize">{c.category || "Gaming"}</span>
                      </div>
                      <h3 className="font-semibold text-white line-clamp-2 text-sm" title={c.title}>
                        {c.title}
                      </h3>
                      {c.hook && (
                        <p className="mt-1 text-xs text-zinc-400 line-clamp-1 italic">
                          Hook: {c.hook}
                        </p>
                      )}
                    </div>

                    {/* YouTube Status Badge */}
                    {c.youtube_status && c.youtube_status !== "ready" && (
                      <div className="pt-2 border-t border-line/60">
                        {c.youtube_status === "uploaded" && c.youtube_url ? (
                          <a
                            href={c.youtube_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 font-medium"
                          >
                            <Youtube size={14} />
                            View on YouTube Shorts
                            <ExternalLink size={12} />
                          </a>
                        ) : c.youtube_status === "uploading" ? (
                          <span className="text-xs text-blue-400 inline-flex items-center gap-1">
                            <Loader2 size={12} className="animate-spin" /> Uploading to YouTube...
                          </span>
                        ) : c.youtube_status === "queued" ? (
                          <span className="text-xs text-yellow-400 inline-flex items-center gap-1">
                            <Clock size={12} />
                            {c.publish_at ? `Scheduled for ${new Date(c.publish_at).toLocaleTimeString()}` : "Queued for upload"}
                          </span>
                        ) : (
                          <span className="text-xs text-red-400 inline-flex items-center gap-1">
                            <AlertTriangle size={12} /> Upload error: {c.youtube_error}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Card Actions */}
                    <div className="flex items-center gap-2 pt-2 border-t border-line/60">
                      <button
                        onClick={() => setEditClip(c)}
                        className="btn btn-ghost flex-1 justify-center text-xs py-1.5"
                      >
                        <Pencil size={13} />
                        Edit
                      </button>

                      {ytStatus?.authenticated && c.render_status === "ready" && c.youtube_status !== "uploaded" && (
                        <button
                          onClick={() => handleUploadSingle(c.id)}
                          title="Upload clip to YouTube"
                          className="btn btn-ghost text-xs py-1.5 text-red-400 hover:text-red-300"
                        >
                          <Upload size={13} />
                        </button>
                      )}

                      <a
                        href={`/api/clips/${c.id}/download`}
                        download
                        className={`btn btn-ghost text-xs py-1.5 px-3 ${
                          c.render_status === "ready" ? "text-zinc-300 hover:text-white" : "pointer-events-none opacity-30"
                        }`}
                        title="Download MP4"
                      >
                        <Download size={13} />
                      </a>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        /* Full Transcript View with seekable video player */
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          <div>
            <video
              ref={vidRef}
              src={`/api/jobs/${id}/source`}
              controls
              className="w-full rounded-xl bg-black border border-line aspect-video"
            />
            <p className="mt-2 text-xs text-zinc-500">
              Click any line in the transcript to jump to that timestamp in the source video.
            </p>
          </div>

          <div className="panel max-h-[75vh] overflow-y-auto p-3 space-y-1 divide-y divide-line/40">
            {segs.map((s, idx) => (
              <button
                key={idx}
                onClick={() => {
                  if (vidRef.current) {
                    vidRef.current.currentTime = s.start;
                    vidRef.current.play();
                  }
                }}
                className="w-full text-left p-2.5 rounded-lg hover:bg-white/5 transition flex items-start gap-3 group"
              >
                <span className="text-xs font-mono text-accent shrink-0 pt-0.5 group-hover:underline">
                  {fmt(s.start).slice(3)}
                </span>
                <span className="text-xs text-zinc-300 leading-relaxed">{s.text}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Clip Edit Drawer */}
      {editClip && (
        <Editor
          clip={editClip}
          duration={job.duration || 600}
          onClose={() => {
            setEditClip(null);
            loadClips();
          }}
        />
      )}
    </div>
  );
}
