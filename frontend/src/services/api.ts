import type { Job, Clip, Segment, AppSettings, YouTubeStatus, HealthStatus } from "../types";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let m = r.statusText;
    try {
      const b = await r.json();
      m = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {}
    throw new Error(m);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export const api = {
  create: (f: { url?: string; file?: File }) => {
    const fd = new FormData();
    if (f.url) fd.append("url", f.url);
    if (f.file) fd.append("file", f.file);
    return fetch("/api/jobs", { method: "POST", body: fd }).then(j<{ id: string; ids?: string[]; count?: number }>);
  },
  jobs: () => fetch("/api/jobs").then(j<Job[]>),
  job: (id: string) => fetch(`/api/jobs/${id}`).then(j<Job>),
  retry: (id: string) => fetch(`/api/jobs/${id}/retry`, { method: "POST" }).then(j<{ status: string }>),
  cancel: (id: string) => fetch(`/api/jobs/${id}/cancel`, { method: "POST" }).then(j<{ status: string }>),
  transcript: (id: string) => fetch(`/api/jobs/${id}/transcript`).then(j<{ segments: Segment[] }>),
  clips: (id: string, sort: string) => fetch(`/api/jobs/${id}/clips?sort=${sort}`).then(j<Clip[]>),
  clip: (id: string) => fetch(`/api/clips/${id}`).then(j<Clip>),
  patch: (id: string, b: Partial<Clip>) =>
    fetch(`/api/clips/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(b),
    }).then(j<Clip>),
  render: (id: string) => fetch(`/api/clips/${id}/render`, { method: "POST" }).then(j<unknown>),
  remove: (id: string) => fetch(`/api/projects/${id}`, { method: "DELETE" }).then(j<void>),

  // Health
  health: () => fetch("/api/health").then(j<HealthStatus>),

  // Settings
  getSettings: () => fetch("/api/settings").then(j<AppSettings>),
  updateSettings: (s: Partial<AppSettings>) =>
    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(s),
    }).then(j<AppSettings>),

  // YouTube OAuth & Uploads
  youtubeStatus: () => fetch("/api/youtube/status").then(j<YouTubeStatus>),
  youtubeConnect: () => fetch("/api/youtube/connect", { method: "POST" }).then(j<{ status: string; auth_url?: string }>),
  youtubeDisconnect: () => fetch("/api/youtube/disconnect", { method: "POST" }).then(j<{ authenticated: boolean }>),
  uploadClip: (cid: string, body?: { privacy_status?: string; publish_at?: string }) =>
    fetch(`/api/clips/${cid}/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(j<{ status: string; upload_id: string }>),
  uploadAll: (pid: string, body?: { spread_minutes?: number; privacy_status?: string; clip_ids?: string[] }) =>
    fetch(`/api/projects/${pid}/upload-all`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(j<{ status: string; count: number; spread_minutes: number }>),
};
