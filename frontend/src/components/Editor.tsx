import { useEffect, useState } from "react";
import { X, Play, RefreshCw, Download, Check, AlertCircle, Loader2, Save } from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import { fmt, type Clip } from "../types";

export default function Editor({
  clip,
  duration,
  onClose,
}: {
  clip: Clip;
  duration: number;
  onClose: () => void;
}) {
  const { toast } = useToast();
  const [c, setC] = useState<Clip>(clip);
  const [start, setStart] = useState(clip.start);
  const [end, setEnd] = useState(clip.end);
  const [title, setTitle] = useState(clip.title || "");
  const [description, setDescription] = useState(clip.description || "");
  const [tags, setTags] = useState(clip.tags || "");
  const [captionStyle, setCaptionStyle] = useState(clip.caption_style || "highlight");
  const [aspect, setAspect] = useState(clip.aspect || "9:16");

  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(c.render_status === "rendering");

  useEffect(() => {
    if (!rendering) return;
    const interval = setInterval(() => {
      api.clip(c.id).then(updated => {
        setC(updated);
        if (updated.render_status !== "rendering") {
          setRendering(false);
          if (updated.render_status === "ready") {
            toast.success("Clip rendered successfully!");
          } else if (updated.render_status === "failed") {
            toast.error(updated.render_error || "Render failed");
          }
        }
      });
    }, 1500);
    return () => clearInterval(interval);
  }, [rendering, c.id]);

  const handleSaveDetailsOnly = async () => {
    setSaving(true);
    try {
      const updated = await api.patch(c.id, {
        title,
        description,
        tags,
      });
      setC(updated);
      toast.success("Clip metadata updated");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleRerender = async () => {
    setRendering(true);
    try {
      await api.patch(c.id, {
        start,
        end,
        title,
        description,
        tags,
        caption_style: captionStyle as any,
        aspect: aspect as any,
      });
      await api.render(c.id);
      setC(prev => ({ ...prev, render_status: "rendering" }));
      toast.info("Re-rendering clip...");
    } catch (e) {
      toast.error((e as Error).message);
      setRendering(false);
    }
  };

  const clipDuration = Math.max(0, end - start);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="panel max-h-[90vh] w-full max-w-4xl overflow-y-auto p-6 shadow-2xl border-line">
        <div className="flex items-center justify-between pb-4 border-b border-line mb-6">
          <div>
            <h2 className="text-xl font-bold text-white">Clip Editor</h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              Refine boundaries, edit YouTube metadata, change caption styling, or trigger re-render.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-zinc-400 hover:text-white hover:bg-white/5 transition"
          >
            <X size={20} />
          </button>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {/* Left Column: Video Preview and Timeline */}
          <div className="space-y-4">
            <div className="relative aspect-[9/16] max-h-[480px] mx-auto w-full bg-black rounded-xl overflow-hidden flex items-center justify-center border border-line">
              {c.video_url && c.render_status === "ready" ? (
                <video
                  key={`${c.video_url}?t=${c.start}`}
                  src={c.video_url}
                  poster={c.thumb_url || undefined}
                  controls
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="text-center p-6 text-zinc-500">
                  {c.render_status === "rendering" ? (
                    <div className="flex flex-col items-center gap-2 text-accent">
                      <Loader2 className="w-8 h-8 animate-spin" />
                      <span>Rendering new clip with FFmpeg...</span>
                    </div>
                  ) : c.render_status === "failed" ? (
                    <div className="text-red-400">
                      <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                      <p className="text-sm font-medium">Render Failed</p>
                      <p className="text-xs mt-1 text-zinc-400">{c.render_error}</p>
                    </div>
                  ) : (
                    <div>Preview available after rendering</div>
                  )}
                </div>
              )}
            </div>

            {/* Timeline Range Sliders */}
            <div className="panel p-4 space-y-3 bg-black/30">
              <div className="flex justify-between text-xs text-zinc-400">
                <span>Start: {fmt(start)}</span>
                <span className="font-semibold text-white">Duration: {clipDuration.toFixed(1)}s</span>
                <span>End: {fmt(end)}</span>
              </div>
              <div className="space-y-2">
                <input
                  type="range"
                  min={0}
                  max={duration || 600}
                  step={0.1}
                  value={start}
                  onChange={e => setStart(Math.min(parseFloat(e.target.value), end - 5))}
                  className="w-full accent-accent"
                />
                <input
                  type="range"
                  min={0}
                  max={duration || 600}
                  step={0.1}
                  value={end}
                  onChange={e => setEnd(Math.max(parseFloat(e.target.value), start + 5))}
                  className="w-full accent-accent"
                />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs text-zinc-400 block mb-1">Start (seconds)</label>
                  <input
                    type="number"
                    step={0.1}
                    className="input w-full"
                    value={start}
                    onChange={e => setStart(parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="flex-1">
                  <label className="text-xs text-zinc-400 block mb-1">End (seconds)</label>
                  <input
                    type="number"
                    step={0.1}
                    className="input w-full"
                    value={end}
                    onChange={e => setEnd(parseFloat(e.target.value) || 0)}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Metadata & Settings Form */}
          <div className="space-y-4 text-sm">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">
                Title (max 90 chars)
              </label>
              <input
                className="input w-full"
                maxLength={90}
                value={title}
                onChange={e => setTitle(e.target.value)}
              />
              <span className="text-xs text-zinc-500 float-right mt-0.5">{title.length}/90</span>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">
                Description (Shorts Summary & Attribution)
              </label>
              <textarea
                rows={4}
                className="input w-full text-xs font-sans resize-y"
                value={description}
                onChange={e => setDescription(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">
                Tags (comma-separated, max 500 chars)
              </label>
              <input
                className="input w-full text-xs"
                value={tags}
                onChange={e => setTags(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Caption Style</label>
                <select
                  className="input w-full text-xs"
                  value={captionStyle}
                  onChange={e => setCaptionStyle(e.target.value)}
                >
                  <option value="highlight">Highlight (Default)</option>
                  <option value="creator">Creator (Pop)</option>
                  <option value="bold">Bold</option>
                  <option value="classic">Classic</option>
                  <option value="minimal">Minimal</option>
                  <option value="off">Off</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Aspect Ratio</label>
                <select
                  className="input w-full text-xs"
                  value={aspect}
                  onChange={e => setAspect(e.target.value)}
                >
                  <option value="9:16">9:16 (Vertical Shorts)</option>
                  <option value="1:1">1:1 (Square)</option>
                  <option value="16:9">16:9 (Landscape)</option>
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-2 pt-4">
              <button
                type="button"
                onClick={handleRerender}
                disabled={rendering || saving}
                className="btn btn-primary justify-center"
              >
                {rendering ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                {rendering ? "Rendering in Progress..." : "Re-render Clip"}
              </button>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleSaveDetailsOnly}
                  disabled={rendering || saving}
                  className="btn btn-ghost flex-1 justify-center text-xs"
                >
                  <Save size={14} />
                  Save Details Only
                </button>

                {c.rendered_path && c.render_status === "ready" && (
                  <a
                    href={`/api/clips/${c.id}/download`}
                    download
                    className="btn btn-ghost flex-1 justify-center text-xs text-zinc-300 hover:text-white"
                  >
                    <Download size={14} />
                    Download MP4
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
