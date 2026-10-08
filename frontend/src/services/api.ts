import type { Job, Clip, Segment } from "../types";
async function j<T>(r: Response): Promise<T> {
  if (!r.ok) { let m = r.statusText; try { const b = await r.json(); m = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch {} throw new Error(m); }
  return r.status === 204 ? (undefined as T) : r.json();
}
export const api = {
  create: (f: { url?: string; file?: File }) => { const fd = new FormData(); if (f.url) fd.append("url", f.url); if (f.file) fd.append("file", f.file); return fetch("/api/jobs", { method: "POST", body: fd }).then(j<{ id: string }>); },
  jobs: () => fetch("/api/jobs").then(j<Job[]>),
  job: (id: string) => fetch(`/api/jobs/${id}`).then(j<Job>),
  transcript: (id: string) => fetch(`/api/jobs/${id}/transcript`).then(j<{ segments: Segment[] }>),
  clips: (id: string, sort: string) => fetch(`/api/jobs/${id}/clips?sort=${sort}`).then(j<Clip[]>),
  clip: (id: string) => fetch(`/api/clips/${id}`).then(j<Clip>),
  patch: (id: string, b: Partial<Clip>) => fetch(`/api/clips/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then(j<Clip>),
  render: (id: string) => fetch(`/api/clips/${id}/render`, { method: "POST" }).then(j<unknown>),
  remove: (id: string) => fetch(`/api/projects/${id}`, { method: "DELETE" }).then(j<void>),
};
