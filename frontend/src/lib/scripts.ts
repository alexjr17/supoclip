export type ScriptTone = "informative" | "energetic" | "story" | "calm" | "funny";

export interface ScriptCharacter {
  name: string;
  role: string;
  description: string;
  voice_tone: string;
  stock_keywords: string[];
}

export interface ScriptScene {
  order: number;
  narration: string;
  duration_seconds: number;
  visual_description: string;
  stock_keywords: string[];
  character_names: string[];
}

export interface VideoScript {
  title: string;
  hook: string;
  scenes: ScriptScene[];
  characters: ScriptCharacter[];
  total_duration_seconds: number;
}

export interface GenerateScriptOptions {
  idea: string;
  target_duration_seconds: number;
  tone: ScriptTone;
  language: string;
  with_characters: boolean;
}

export const SCRIPT_TONES: Array<{ value: ScriptTone; label: string }> = [
  { value: "informative", label: "Informative" },
  { value: "energetic", label: "Energetic" },
  { value: "story", label: "Story" },
  { value: "calm", label: "Calm" },
  { value: "funny", label: "Funny" },
];

export const SCRIPT_DURATIONS = [30, 45, 60, 90] as const;

export async function generateScript(options: GenerateScriptOptions): Promise<VideoScript> {
  const response = await fetch("/api/scripts/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });

  const text = await response.text();
  let data: Partial<VideoScript> & { detail?: string; error?: string } = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }

  if (!response.ok) {
    throw new Error(data.detail || data.error || "Failed to generate the script");
  }

  return data as VideoScript;
}

export interface StockCandidate {
  id: number;
  width: number;
  height: number;
  duration: number;
  thumbnail: string | null;
  preview_url: string | null;
  download_url: string | null;
  author: string | null;
  author_url: string | null;
  source: string;
}

export interface SceneFootage {
  order: number;
  keywords: string[];
  candidates: StockCandidate[];
  selected_id: number | null;
}

export interface FootageResult {
  scenes: SceneFootage[];
  /** Scenes that found nothing, so the user can rewrite their keywords. */
  scenes_without_footage: number[];
}

export async function fetchStockStatus(): Promise<{
  configured: boolean;
  provider: string;
}> {
  const response = await fetch("/api/scripts/stock-status", { cache: "no-store" });
  if (!response.ok) {
    return { configured: false, provider: "pexels" };
  }
  return response.json();
}

export async function findFootage(scenes: ScriptScene[]): Promise<FootageResult> {
  const response = await fetch("/api/scripts/find-footage", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scenes: scenes.map((scene) => ({
        order: scene.order,
        stock_keywords: scene.stock_keywords,
      })),
    }),
  });

  const text = await response.text();
  let data: Partial<FootageResult> & { detail?: string; error?: string } = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }

  if (!response.ok) {
    throw new Error(data.detail || data.error || "Failed to find stock footage");
  }

  return data as FootageResult;
}

/** Recomputes the total after the user edits scene durations by hand. */
export function totalDuration(scenes: ScriptScene[]): number {
  return Math.round(scenes.reduce((sum, scene) => sum + (scene.duration_seconds || 0), 0) * 10) / 10;
}
