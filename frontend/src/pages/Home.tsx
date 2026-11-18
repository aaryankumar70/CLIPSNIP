import { useEffect, useRef, useState } from "react";
import {
  Upload,
  Sparkles,
  Trash2,
  RotateCcw,
  XCircle,
  ExternalLink,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Film,
  Youtube,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import { fmt, type Job, type YouTubeStatus } from "../types";

export default function Home() {
  const { toast } = useToast();
  const [urls, setUrls] = useState("");
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [ytStatus, setYtStatus] = useState<YouTubeStatus | null>(null);
  const [authorizingYt, setAuthorizingYt] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadJobs = () => {
    api.jobs()
      .then(setJobs)
      .catch(() => {});
  };

  const loadYtStatus = () => {
    api.youtubeStatus()
      .then(setYtStatus)
      .catch(() => {});
  };

  useEffect(() => {
    loadJobs();
    loadYtStatus();
    const interval = setInterval(() => {
      loadJobs();
      loadYtStatus();
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleConnectYouTube = async () => {
    try {
      setAuthorizingYt(true);
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
            setAuthorizingYt(false);
            toast.success("Successfully connected to YouTube!");
          } else if (attempts > 60) {
            clearInterval(interval);
            setAuthorizingYt(false);
          }
        } catch {
          // ignore transient poll error
        }
      }, 2000);
    } catch (e) {
      setAuthorizingYt(false);
      toast.error((e as Error).message);
    }
  };

  const handleDisconnectYouTube = async () => {
    try {
      await api.youtubeDisconnect();
      toast.info("Disconnected YouTube channel");
      loadYtStatus();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleStartUrls = async () => {
    const trimmed = urls.trim();
    if (!trimmed) return;
    setBusy(true);

    try {
      const res = await api.create({ url: trimmed });
      toast.success(
        res.count && res.count > 1
          ? `Queued ${res.count} video processing jobs`
          : "Video processing job started"
      );
      setUrls("");
      loadJobs();
      if (res.id) {
        location.hash = `#/project/${res.id}`;
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setBusy(true);
    try {
      const res = await api.create({ file });
      toast.success(`Uploaded ${file.name} successfully`);
      loadJobs();
      location.hash = `#/project/${res.id}`;
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.retry(id);
      toast.info("Job re-queued");
      loadJobs();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const handleCancel = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.cancel(id);
      toast.info("Job cancelled");
      loadJobs();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const handleDelete = async (id: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete project "${name}" and all its clips?`)) return;
    try {
      await api.remove(id);
      toast.success("Project deleted");
      loadJobs();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const getStatusBadge = (j: Job) => {
    switch (j.status) {
      case "processing":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Loader2 size={12} className="animate-spin" />
            {j.stage || "processing"}
          </span>
        );
      case "completed":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">
            <CheckCircle2 size={12} />
            Completed
          </span>
        );
      case "queued":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
            <Clock size={12} />
            Queued
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
            <AlertCircle size={12} />
            Failed
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">
            <XCircle size={12} />
            Cancelled
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="mx-auto max-w-4xl pt-6 pb-16">
      {/* Hero Header */}
      <div className="text-center max-w-2xl mx-auto mb-8">
        <h1 className="text-4xl font-extrabold tracking-tight text-white md:text-5xl">
          Automated Short-Form Studio
        </h1>
        <p className="mt-3 text-base text-zinc-400">
          Paste YouTube links from creators who allow clipping. ClipSnip transcribes speech, selects viral hooks, burns in
          word-level captions, and queues YouTube Shorts.
        </p>
      </div>

      {/* YouTube Channel Authorization Card */}
      <div className="panel p-5 mb-6 border-line bg-panel/70 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="p-2.5 rounded-xl bg-red-500/10 text-red-500 border border-red-500/20">
            <Youtube size={26} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-white">YouTube Upload Studio</h3>
              {ytStatus?.authenticated ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                  <CheckCircle2 size={12} /> Connected
                </span>
              ) : ytStatus?.reconnect_needed ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
                  <AlertCircle size={12} /> OAuth Token Expired
                </span>
              ) : ytStatus?.has_client_secret ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30">
                  Credentials Ready
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-500/15 text-zinc-400 border border-zinc-500/30">
                  No Credentials Found
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-zinc-400">
              {ytStatus?.authenticated
                ? "Your YouTube channel is authorized. You can publish clips directly as Shorts."
                : ytStatus?.reconnect_needed
                ? "Your 7-day Google Cloud testing token expired. Click to re-authorize."
                : ytStatus?.has_client_secret
                ? "client_secret.json found in storage/. Authorize ClipSnip to upload to your channel."
                : "Place storage/client_secret.json to connect your YouTube channel for auto-uploads."}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {ytStatus?.authenticated ? (
            <button
              onClick={handleDisconnectYouTube}
              className="btn btn-ghost text-xs text-zinc-400 hover:text-red-400"
            >
              Disconnect
            </button>
          ) : ytStatus?.has_client_secret ? (
            <button
              onClick={handleConnectYouTube}
              disabled={authorizingYt}
              className="btn btn-primary text-xs flex items-center gap-2 shadow-lg shadow-red-500/20"
            >
              {authorizingYt ? <Loader2 size={14} className="animate-spin" /> : <Youtube size={14} />}
              {authorizingYt
                ? "Waiting for Approval..."
                : ytStatus?.reconnect_needed
                ? "Re-authorize YouTube"
                : "Authorize YouTube Channel"}
            </button>
          ) : (
            <a
              href="https://console.cloud.google.com/"
              target="_blank"
              rel="noreferrer"
              className="btn btn-ghost text-xs text-zinc-400 hover:text-white inline-flex items-center gap-1.5"
            >
              Setup Guide <ExternalLink size={12} />
            </a>
          )}
        </div>
      </div>

      {/* Main Ingest Panel */}
      <div className="panel p-6 shadow-2xl">
        <label className="block text-sm font-medium text-zinc-300 mb-2">
          Paste YouTube or Direct Video Links (one per line)
        </label>
        <textarea
          rows={3}
          className="input w-full font-mono text-xs leading-relaxed resize-y"
          placeholder="https://www.youtube.com/watch?v=...&#10;https://youtu.be/...&#10;https://youtube.com/shorts/..."
          value={urls}
          onChange={e => setUrls(e.target.value)}
        />

        <div className="mt-4 flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button
              onClick={handleStartUrls}
              disabled={busy || !urls.trim()}
              className="btn btn-primary w-full sm:w-auto justify-center"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              Start Clipping
            </button>
            <span className="text-xs text-zinc-500">or</span>
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              hidden
              onChange={e => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              className="btn btn-ghost w-full sm:w-auto justify-center"
            >
              <Upload size={16} />
              Upload MP4 / MOV
            </button>
          </div>
          <span className="text-xs text-zinc-500">Local processing · Zero cloud API cost</span>
        </div>
      </div>

      {/* Features Bar */}
      <div className="mt-6 grid grid-cols-2 gap-3 text-xs tracking-wider text-zinc-400 md:grid-cols-4">
        {[
          "SMART HOOK DETECTION",
          "WORD-SYNC CAPTIONS",
          "BLUR-FIT REFRAMING",
          "YOUTUBE SHORTS UPLOAD",
        ].map(item => (
          <div key={item} className="panel p-3 text-center border-line/60 bg-panel/40">
            {item}
          </div>
        ))}
      </div>

      {/* Job History / Live Queue Table */}
      <div className="mt-12">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold tracking-wider text-zinc-400 uppercase">
            Queue & History ({jobs.length})
          </h2>
          <span className="text-xs text-zinc-500">Auto-refreshes every 3s</span>
        </div>

        {jobs.length === 0 ? (
          <div className="panel p-8 text-center text-zinc-500">
            <Film className="w-10 h-10 mx-auto mb-2 text-zinc-600 opacity-60" />
            <p>No projects in queue. Paste a YouTube link above to start.</p>
          </div>
        ) : (
          <div className="panel overflow-hidden border-line divide-y divide-line/60">
            {jobs.map(job => (
              <div
                key={job.id}
                onClick={() => (location.hash = `#/project/${job.id}`)}
                className="group flex flex-col md:flex-row md:items-center justify-between p-4 gap-4 hover:bg-white/[0.02] cursor-pointer transition"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-medium text-white truncate max-w-md group-hover:text-accent transition">
                      {job.name || "Untitled Video"}
                    </span>
                    {getStatusBadge(job)}
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-500">
                    {job.duration ? <span>Duration: {fmt(job.duration)}</span> : null}
                    {job.elapsed > 0 && <span>Elapsed: {Math.round(job.elapsed)}s</span>}
                    {job.eta ? (
                      <span className="text-accent font-medium">ETA: ~{Math.round(job.eta)}s</span>
                    ) : null}
                  </div>

                  {job.status === "processing" && (
                    <div className="mt-2.5 w-full max-w-md h-1.5 rounded-full bg-white/10 overflow-hidden">
                      <div
                        className="h-full bg-accent transition-all duration-300"
                        style={{ width: `${Math.max(5, job.progress)}%` }}
                      />
                    </div>
                  )}

                  {job.status === "failed" && job.error && (
                    <p className="mt-1.5 text-xs text-red-400 line-clamp-1">{job.error}</p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                  {job.status === "processing" && (
                    <button
                      title="Cancel job"
                      onClick={e => handleCancel(job.id, e)}
                      className="btn btn-ghost px-2.5 py-1 text-xs text-zinc-400 hover:text-red-400"
                    >
                      <XCircle size={14} />
                      Cancel
                    </button>
                  )}

                  {(job.status === "failed" || job.status === "cancelled") && (
                    <button
                      title="Retry job"
                      onClick={e => handleRetry(job.id, e)}
                      className="btn btn-ghost px-2.5 py-1 text-xs text-zinc-300 hover:text-white"
                    >
                      <RotateCcw size={14} />
                      Retry
                    </button>
                  )}

                  <a
                    href={`#/project/${job.id}`}
                    onClick={e => e.stopPropagation()}
                    className="btn btn-ghost px-2.5 py-1 text-xs text-zinc-300 hover:text-white"
                  >
                    <ExternalLink size={14} />
                    Open
                  </a>

                  <button
                    title="Delete project"
                    onClick={e => handleDelete(job.id, job.name, e)}
                    className="p-2 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-white/5 transition"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
