import { useState } from "react";
import {
  X,
  Clock,
  Calendar,
  Sparkles,
  Youtube,
  AlertCircle,
  Loader2,
  CheckCircle2,
  CalendarCheck,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import type { Clip } from "../types";

interface ScheduleModalProps {
  clip: Clip;
  onClose: () => void;
  onScheduled: (updatedClipId: string) => void;
}

export default function ScheduleModal({ clip, onClose, onScheduled }: ScheduleModalProps) {
  const { toast } = useToast();
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  // Compute a default scheduled time (tomorrow at 18:00 local time)
  const getDefaultDateTime = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(18, 0, 0, 0);
    // Format to YYYY-MM-DDTHH:mm for datetime-local input
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const [dateTimeLocal, setDateTimeLocal] = useState<string>(() => {
    if (clip.publish_at) {
      try {
        const d = new Date(clip.publish_at);
        const pad = (n: number) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      } catch {
        return getDefaultDateTime();
      }
    }
    return getDefaultDateTime();
  });

  const setPresetTime = (hoursFromNow?: number, specificTimeTomorrow?: { h: number; m: number }, daysAhead: number = 0) => {
    const d = new Date();
    if (hoursFromNow !== undefined) {
      d.setHours(d.getHours() + hoursFromNow);
    } else if (specificTimeTomorrow) {
      d.setDate(d.getDate() + daysAhead);
      d.setHours(specificTimeTomorrow.h, specificTimeTomorrow.m, 0, 0);
    }
    const pad = (n: number) => String(n).padStart(2, "0");
    setDateTimeLocal(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    );
  };

  const handleSchedule = async () => {
    if (!dateTimeLocal) {
      toast.error("Please pick a scheduled date and time");
      return;
    }

    const scheduledDate = new Date(dateTimeLocal);
    if (isNaN(scheduledDate.getTime())) {
      toast.error("Invalid date or time selected");
      return;
    }

    const now = new Date();
    if (scheduledDate.getTime() <= now.getTime() + 60000) {
      toast.error("Scheduled time must be at least 2 minutes in the future");
      return;
    }

    setSubmitting(true);
    try {
      const isoUtc = scheduledDate.toISOString();
      await api.uploadClip(clip.id, {
        privacy_status: "private",
        publish_at: isoUtc,
      });

      toast.success(
        `Scheduled for ${scheduledDate.toLocaleDateString([], {
          weekday: "short",
          month: "short",
          day: "numeric",
        })} at ${scheduledDate.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
      );
      onScheduled(clip.id);
      onClose();
    } catch (err) {
      toast.error(`Scheduling failed: ${(err as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelSchedule = async () => {
    setCancelling(true);
    try {
      await api.cancelClipUpload(clip.id);
      toast.info("Scheduled upload cancelled");
      onScheduled(clip.id);
      onClose();
    } catch (err) {
      toast.error(`Failed to cancel schedule: ${(err as Error).message}`);
    } finally {
      setCancelling(false);
    }
  };

  const isCurrentlyScheduled = clip.youtube_status === "queued" && Boolean(clip.publish_at);
  const formattedCurrentSchedule = clip.publish_at
    ? new Date(clip.publish_at).toLocaleString([], {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="panel max-w-lg w-full p-6 shadow-2xl border-line bg-panel/95 relative">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-line mb-5">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
              <Youtube size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                Schedule YouTube Short
              </h2>
              <p className="text-xs text-zinc-400">
                Automate your Shorts upload with YouTube's scheduled release
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-white/5 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Current Schedule Banner if already queued */}
        {isCurrentlyScheduled && formattedCurrentSchedule && (
          <div className="mb-5 rounded-lg border border-indigo-500/30 bg-indigo-950/30 p-3.5 flex items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 text-indigo-300">
              <CalendarCheck size={16} className="text-indigo-400 shrink-0" />
              <div>
                <span className="font-semibold text-white">Currently Scheduled: </span>
                {formattedCurrentSchedule}
              </div>
            </div>
            <button
              onClick={handleCancelSchedule}
              disabled={cancelling}
              className="text-red-400 hover:text-red-300 font-medium underline shrink-0 transition"
            >
              {cancelling ? "Cancelling..." : "Cancel"}
            </button>
          </div>
        )}

        {/* Clip Preview Info */}
        <div className="panel p-3 bg-black/40 border-line/60 mb-5 flex items-start gap-3">
          <div className="w-16 h-20 rounded bg-zinc-900 border border-line overflow-hidden shrink-0 flex items-center justify-center">
            {clip.thumb_url ? (
              <img src={clip.thumb_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <Youtube size={20} className="text-zinc-600" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-accent/20 text-accent border border-accent/30">
                Score {Math.round(clip.score)}
              </span>
              <span className="text-[10px] text-zinc-400 font-mono">
                {(clip.end - clip.start).toFixed(1)}s
              </span>
              {clip.category && (
                <span className="text-[10px] px-1.5 py-0.5 rounded text-zinc-400 bg-white/5 capitalize">
                  {clip.category}
                </span>
              )}
            </div>
            <p className="text-xs font-semibold text-white truncate" title={clip.title}>
              {clip.title}
            </p>
            {clip.hook && (
              <p className="text-[11px] text-zinc-400 italic truncate mt-0.5">
                Hook: {clip.hook}
              </p>
            )}
          </div>
        </div>

        {/* Quick Presets */}
        <div className="mb-4">
          <label className="block text-xs font-medium text-zinc-300 mb-2 flex items-center gap-1.5">
            <Sparkles size={13} className="text-accent" />
            Quick Presets (Best Shorts Viewing Hours)
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => setPresetTime(1)}
              className="px-2.5 py-1.5 rounded-lg border border-line bg-white/5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 hover:border-accent/40 text-left transition"
            >
              ⚡ In 1 Hour
            </button>
            <button
              type="button"
              onClick={() => setPresetTime(undefined, { h: 12, m: 0 }, 1)}
              className="px-2.5 py-1.5 rounded-lg border border-line bg-white/5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 hover:border-accent/40 text-left transition"
            >
              🥗 Tomorrow 12:00 PM
            </button>
            <button
              type="button"
              onClick={() => setPresetTime(undefined, { h: 18, m: 0 }, 1)}
              className="px-2.5 py-1.5 rounded-lg border border-indigo-500/30 bg-indigo-500/10 text-xs text-indigo-300 hover:text-white hover:bg-indigo-500/20 text-left transition font-medium"
            >
              🔥 Tomorrow 6:00 PM
            </button>
            <button
              type="button"
              onClick={() => setPresetTime(undefined, { h: 20, m: 0 }, 1)}
              className="px-2.5 py-1.5 rounded-lg border border-line bg-white/5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 hover:border-accent/40 text-left transition"
            >
              🌙 Tomorrow 8:00 PM
            </button>
            <button
              type="button"
              onClick={() => setPresetTime(undefined, { h: 18, m: 0 }, 2)}
              className="px-2.5 py-1.5 rounded-lg border border-line bg-white/5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 hover:border-accent/40 text-left transition"
            >
              📅 In 2 Days 6:00 PM
            </button>
            <button
              type="button"
              onClick={() => setPresetTime(undefined, { h: 18, m: 0 }, 3)}
              className="px-2.5 py-1.5 rounded-lg border border-line bg-white/5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 hover:border-accent/40 text-left transition"
            >
              📅 In 3 Days 6:00 PM
            </button>
          </div>
        </div>

        {/* Date Time Picker */}
        <div className="mb-5">
          <label className="block text-xs font-medium text-zinc-300 mb-1.5 flex items-center gap-1.5">
            <Calendar size={13} className="text-zinc-400" />
            Specific Release Date & Time
          </label>
          <input
            type="datetime-local"
            value={dateTimeLocal}
            onChange={e => setDateTimeLocal(e.target.value)}
            className="input w-full text-sm text-white font-mono bg-black/60 border-line focus:border-accent focus:ring-1 focus:ring-accent"
          />
          <p className="text-[11px] text-zinc-500 mt-1.5 flex items-center gap-1">
            <Clock size={11} />
            YouTube will safely store the video in Private status until this exact time, then switch it to Public.
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-line">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost text-xs text-zinc-400 hover:text-white px-3 py-2"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSchedule}
            disabled={submitting}
            className="btn btn-primary text-xs px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white shadow-lg shadow-indigo-500/25 flex items-center gap-1.5 font-medium"
          >
            {submitting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <CalendarCheck size={14} />
            )}
            {submitting
              ? "Scheduling..."
              : isCurrentlyScheduled
              ? "Update Schedule"
              : "Schedule Video"}
          </button>
        </div>
      </div>
    </div>
  );
}
