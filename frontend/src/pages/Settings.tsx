import { useEffect, useState } from "react";
import { Save, AlertTriangle, Cpu, Film, Tag, Upload, HardDrive, Wifi, Youtube, CheckCircle2, AlertCircle, Loader2, ExternalLink } from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import type { AppSettings, YouTubeStatus } from "../types";

export default function Settings() {
  const { toast } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [ytStatus, setYtStatus] = useState<YouTubeStatus | null>(null);
  const [authorizingYt, setAuthorizingYt] = useState(false);
  const [tagsStr, setTagsStr] = useState("");
  const [hashtagsStr, setHashtagsStr] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadYtStatus = () => {
    api.youtubeStatus()
      .then(setYtStatus)
      .catch(() => {});
  };

  useEffect(() => {
    api.getSettings()
      .then(s => {
        setSettings(s);
        setTagsStr((s.default_tags || []).join(", "));
        setHashtagsStr((s.default_hashtags || []).join(" "));
      })
      .catch(e => toast.error(`Failed to load settings: ${e.message}`))
      .finally(() => setLoading(false));

    loadYtStatus();
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
        } catch {}
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

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);

    const parsedTags = tagsStr.split(",").map(t => t.trim()).filter(Boolean);
    const parsedHashtags = hashtagsStr.split(/[\s,]+/).map(t => t.trim()).filter(Boolean);

    try {
      const updated = await api.updateSettings({
        ...settings,
        default_tags: parsedTags,
        default_hashtags: parsedHashtags,
      });
      setSettings(updated);
      toast.success("Settings saved successfully");
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-zinc-500">Loading settings...</div>;
  }
  if (!settings) {
    return <div className="p-8 text-red-400">Settings unavailable.</div>;
  }

  return (
    <div className="mx-auto max-w-4xl py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Settings</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Configure local AI models, clip lengths, rendering layouts, and YouTube upload defaults.
          </p>
        </div>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="btn btn-primary shadow-lg shadow-accent/20"
        >
          <Save size={16} />
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Clips Configuration */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center gap-2 text-white font-medium">
            <Film size={18} className="text-accent" />
            <span>Clip Generation</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Min Length (seconds)</label>
              <input
                type="number"
                min={15}
                max={300}
                className="input w-full"
                value={settings.clip_min_s}
                onChange={e => setSettings({ ...settings, clip_min_s: parseInt(e.target.value) || 60 })}
              />
              <p className="mt-1 text-xs text-zinc-500">Default: 60s</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Max Length (seconds)</label>
              <input
                type="number"
                min={30}
                max={600}
                className="input w-full"
                value={settings.clip_max_s}
                onChange={e => setSettings({ ...settings, clip_max_s: parseInt(e.target.value) || 120 })}
              />
              <p className="mt-1 text-xs text-zinc-500">Default: 120s (ideal 75-100s)</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Max Clips per Video</label>
              <input
                type="number"
                min={1}
                max={30}
                className="input w-full"
                value={settings.max_clips}
                onChange={e => setSettings({ ...settings, max_clips: parseInt(e.target.value) || 15 })}
              />
              <p className="mt-1 text-xs text-zinc-500">Default: 15 clips</p>
            </div>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Default Layout</label>
              <select
                className="input w-full"
                value={settings.layout}
                onChange={e => setSettings({ ...settings, layout: e.target.value as "blur_fit" | "center_crop" })}
              >
                <option value="blur_fit">Blur Fit (Blurred background)</option>
                <option value="center_crop">Center Crop</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Caption Style</label>
              <select
                className="input w-full"
                value={settings.caption_style}
                onChange={e => setSettings({ ...settings, caption_style: e.target.value as any })}
              >
                <option value="highlight">Highlight (Default)</option>
                <option value="viral">Viral (Neon Pop)</option>
                <option value="creator">Creator (Animated pop)</option>
                <option value="bold">Bold</option>
                <option value="classic">Classic</option>
                <option value="minimal">Minimal</option>
                <option value="off">Off (No captions)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Output Resolution</label>
              <select
                className="input w-full"
                value={settings.output_resolution}
                onChange={e => setSettings({ ...settings, output_resolution: e.target.value as "720x1280" | "1080x1920" })}
              >
                <option value="720x1280">720x1280 (Fastest on CPU)</option>
                <option value="1080x1920">1080x1920 (High Definition)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Local AI Models */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center gap-2 text-white font-medium">
            <Cpu size={18} className="text-accent" />
            <span>Local AI & Transcription</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Ollama Model</label>
              <input
                className="input w-full font-mono text-xs"
                value={settings.ollama_model}
                onChange={e => setSettings({ ...settings, ollama_model: e.target.value })}
              />
              <p className="mt-1 text-xs text-zinc-500">Default: qwen2.5:3b-instruct</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Ollama Context (num_ctx)</label>
              <input
                type="number"
                min={2048}
                max={32768}
                step={1024}
                className="input w-full"
                value={settings.ollama_num_ctx}
                onChange={e => setSettings({ ...settings, ollama_num_ctx: parseInt(e.target.value) || 4096 })}
              />
              <p className="mt-1 text-xs text-zinc-500">Default: 4096 tokens</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Whisper Model</label>
              <input
                className="input w-full font-mono text-xs"
                value={settings.whisper_model}
                onChange={e => setSettings({ ...settings, whisper_model: e.target.value })}
              />
              <p className="mt-1 text-xs text-zinc-500">Default: base.en (CPU optimized)</p>
            </div>
          </div>
        </div>

        {/* Download & Language */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center gap-2 text-white font-medium">
            <Film size={18} className="text-accent" />
            <span>Download & Captions</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Download Quality</label>
              <select
                className="input w-full"
                value={settings.download_quality}
                onChange={e => setSettings({ ...settings, download_quality: e.target.value as "720p" | "1080p" })}
              >
                <option value="720p">720p (Recommended)</option>
                <option value="1080p">1080p</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Preferred Caption Language</label>
              <input
                className="input w-full"
                value={settings.caption_language}
                onChange={e => setSettings({ ...settings, caption_language: e.target.value })}
              />
              <p className="mt-1 text-xs text-zinc-500">e.g. en, es, fr</p>
            </div>
          </div>
        </div>

        {/* Metadata & Attribution */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center gap-2 text-white font-medium">
            <Tag size={18} className="text-accent" />
            <span>Metadata & Attribution</span>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Default Tags (comma-separated)</label>
              <input
                className="input w-full"
                value={tagsStr}
                onChange={e => setTagsStr(e.target.value)}
                placeholder="gaming, gta6, shorts, viral"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Default Hashtags</label>
              <input
                className="input w-full"
                value={hashtagsStr}
                onChange={e => setHashtagsStr(e.target.value)}
                placeholder="#gaming #shorts"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Description Footer Template</label>
              <input
                className="input w-full font-mono text-xs"
                value={settings.footer_template}
                onChange={e => setSettings({ ...settings, footer_template: e.target.value })}
              />
              <p className="mt-1 text-xs text-zinc-500">
                Variables: &#123;source_title&#125;, &#123;channel&#125;, &#123;source_url&#125;
              </p>
            </div>
          </div>
        </div>

        {/* YouTube Upload Defaults & Channel Authorization */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2 text-white font-medium">
              <Youtube size={20} className="text-red-500" />
              <span>YouTube Channel & Upload Defaults</span>
            </div>
            {ytStatus?.authenticated ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                <CheckCircle2 size={12} /> Connected
              </span>
            ) : ytStatus?.has_client_secret ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30">
                Credentials Ready
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-500/15 text-zinc-400 border border-zinc-500/30">
                Not Connected
              </span>
            )}
          </div>

          {/* YouTube Authorization Action Card */}
          <div className="p-4 mb-5 rounded-xl border border-line bg-black/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-xs text-zinc-200 font-semibold">
                {ytStatus?.authenticated
                  ? "Authorized via Google OAuth (Desktop App)"
                  : ytStatus?.has_client_secret
                  ? "Google OAuth client credentials detected in storage/"
                  : "Client secret file missing in storage/client_secret.json"}
              </p>
              <p className="text-[11px] text-zinc-400 mt-0.5">
                {ytStatus?.authenticated
                  ? "Direct uploads and spread scheduling are ready for use."
                  : ytStatus?.has_client_secret
                  ? "Click Authorize to connect your channel and grant upload permissions."
                  : "Create Desktop App credentials in Google Cloud Console and save as storage/client_secret.json."}
              </p>
            </div>
            <div className="shrink-0">
              {ytStatus?.authenticated ? (
                <button
                  type="button"
                  onClick={handleDisconnectYouTube}
                  className="btn btn-ghost text-xs text-zinc-400 hover:text-red-400"
                >
                  Disconnect
                </button>
              ) : ytStatus?.has_client_secret ? (
                <button
                  type="button"
                  onClick={handleConnectYouTube}
                  disabled={authorizingYt}
                  className="btn btn-primary text-xs flex items-center gap-2 shadow-lg shadow-red-500/20"
                >
                  {authorizingYt ? <Loader2 size={14} className="animate-spin" /> : <Youtube size={14} />}
                  {authorizingYt ? "Authorizing..." : "Authorize YouTube Channel"}
                </button>
              ) : (
                <a
                  href="https://console.cloud.google.com/"
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-ghost text-xs text-zinc-400 hover:text-white inline-flex items-center gap-1"
                >
                  Setup Guide <ExternalLink size={12} />
                </a>
              )}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Default Privacy Status</label>
              <select
                className="input w-full"
                value={settings.upload_privacy}
                onChange={e => setSettings({ ...settings, upload_privacy: e.target.value as any })}
              >
                <option value="public">Public</option>
                <option value="unlisted">Unlisted</option>
                <option value="private">Private</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Spread Upload Interval (minutes)</label>
              <input
                type="number"
                min={1}
                max={1440}
                className="input w-full"
                value={settings.spread_minutes}
                onChange={e => setSettings({ ...settings, spread_minutes: parseInt(e.target.value) || 60 })}
              />
              <p className="mt-1 text-xs text-zinc-500">Spaces scheduled video publication</p>
            </div>
          </div>
        </div>

        {/* Storage & LAN Mode */}
        <div className="panel p-5">
          <div className="mb-4 flex items-center gap-2 text-white font-medium">
            <HardDrive size={18} className="text-accent" />
            <span>Storage & Network</span>
          </div>
          <div className="space-y-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 rounded border-line bg-black/40 text-accent focus:ring-accent"
                checked={settings.delete_source_after_render}
                onChange={e => setSettings({ ...settings, delete_source_after_render: e.target.checked })}
              />
              <div>
                <span className="text-sm font-medium text-zinc-200">Delete source video after rendering</span>
                <p className="text-xs text-zinc-500">Conserves laptop disk space once all clips are generated</p>
              </div>
            </label>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Uploaded Clips Retention (days)</label>
              <input
                type="number"
                min={0}
                max={365}
                className="input w-full max-w-xs"
                value={settings.cleanup_days ?? 7}
                onChange={e => setSettings({ ...settings, cleanup_days: parseInt(e.target.value) || 0 })}
              />
              <p className="mt-1 text-xs text-zinc-500">Deletes rendered files of uploaded clips after N days (0 to disable)</p>
            </div>

            <div className="border-t border-line/60 pt-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded border-line bg-black/40 text-accent focus:ring-accent"
                  checked={settings.lan_mode}
                  onChange={e => setSettings({ ...settings, lan_mode: e.target.checked })}
                />
                <div className="flex items-center gap-2">
                  <Wifi size={16} className="text-zinc-400" />
                  <span className="text-sm font-medium text-zinc-200">Enable LAN Mode (0.0.0.0)</span>
                </div>
              </label>
              {settings.lan_mode && (
                <div className="mt-2.5 flex items-start gap-2 rounded-lg border border-yellow-500/30 bg-yellow-950/40 p-3 text-xs text-yellow-300">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5 text-yellow-400" />
                  <span>
                    Warning: LAN mode makes Clipper accessible to anyone on your local network without authentication.
                    Ensure your network is trusted.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button type="submit" disabled={saving} className="btn btn-primary px-6">
            <Save size={16} />
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </form>
    </div>
  );
}
