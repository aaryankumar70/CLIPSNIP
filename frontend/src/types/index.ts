export interface Job { id: string; name: string; status: "queued"|"processing"|"completed"|"failed"|"cancelled"; stage: string; progress: number; error: string|null; duration: number|null; elapsed: number; }
export interface Clip { id: string; project_id: string; start: number; end: number; title: string; hook: string; reason: string; score: number; category: string; caption_style: string; aspect: string; render_status: string; render_error: string|null; video_url: string|null; thumb_url: string|null; }
export interface Segment { start: number; end: number; text: string; }
export const fmt = (t: number) => { const s = Math.floor(t); return `${String(Math.floor(s/3600)).padStart(2,"0")}:${String(Math.floor(s/60)%60).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`; };
