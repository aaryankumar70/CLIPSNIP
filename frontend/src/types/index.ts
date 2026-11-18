export interface Job {
  id: string;
  name: string;
  status: "queued" | "processing" | "completed" | "failed" | "cancelled";
  stage: string;
  progress: number;
  error: string | null;
  duration: number | null;
  elapsed: number;
  eta: number | null;
}

export interface Clip {
  id: string;
  project_id: string;
  start: number;
  end: number;
  title: string;
  hook: string;
  reason: string;
  score: number;
  category: string;
  caption_style: string;
  aspect: string;
  render_status: string;
  render_error: string | null;
  video_url: string | null;
  thumb_url: string | null;
  description: string | null;
  tags: string | null;
  youtube_status: string | null;
  youtube_video_id: string | null;
  youtube_url: string | null;
  youtube_error: string | null;
  publish_at: string | null;
  rendered_path?: string | null;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
}

export interface YouTubeStatus {
  authenticated: boolean;
  reconnect_needed: boolean;
  has_client_secret: boolean;
  error: string | null;
}

export interface AppSettings {
  clip_min_s: number;
  clip_max_s: number;
  max_clips: number;
  layout: "blur_fit" | "center_crop";
  caption_style: "classic" | "bold" | "highlight" | "creator" | "minimal" | "off";
  output_resolution: "720x1280" | "1080x1920";
  download_quality: "720p" | "1080p";
  caption_language: string;
  upload_privacy: "public" | "unlisted" | "private";
  spread_minutes: number;
  default_tags: string[];
  default_hashtags: string[];
  footer_template: string;
  delete_source_after_render: boolean;
  lan_mode: boolean;
  ollama_model: string;
  ollama_num_ctx: number;
  whisper_model: string;
}

export interface HealthStatus {
  ok: boolean;
  ffmpeg?: boolean;
  ffprobe?: boolean;
  ollama?: boolean;
  ollama_model?: boolean;
  model_name?: string;
  disk_free_gb?: number;
  warnings?: string[];
}

export const fmt = (t: number) => {
  const s = Math.floor(t);
  return `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
