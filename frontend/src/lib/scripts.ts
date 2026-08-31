import { formatSupportMessage, parseApiError } from "@/lib/api-error";

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

export interface NarrationWord {
  text: string;
  start: number;
  end: number;
}

export interface SceneNarration {
  order: number;
  narration: string;
  /** Measured from the synthesised voice, not estimated from word count. */
  duration: number;
  estimated_duration: number | null;
  words: NarrationWord[];
  audio_filename: string | null;
  error: string | null;
}

export interface NarrationResult {
  scenes: SceneNarration[];
  total_duration: number;
}

export interface Voice {
  name: string;
  locale: string;
  gender: string;
}

export async function fetchVoices(language: string): Promise<Voice[]> {
  const response = await fetch(
    `/api/scripts/voices?language=${encodeURIComponent(language)}`,
    { cache: "no-store" },
  );
  if (!response.ok) return [];
  return (await response.json()).voices ?? [];
}

export async function narrateScript(
  scenes: ScriptScene[],
  options: { language: string; gender?: string; voice?: string | null },
): Promise<NarrationResult> {
  const response = await fetch("/api/scripts/narrate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scenes: scenes.map((scene) => ({
        order: scene.order,
        narration: scene.narration,
        duration_seconds: scene.duration_seconds,
      })),
      language: options.language,
      gender: options.gender ?? "female",
      voice: options.voice ?? null,
    }),
  });

  if (!response.ok) {
    throw new Error(formatSupportMessage(await parseApiError(response, "Narration failed")));
  }
  return response.json();
}

export interface AssembleScene {
  order: number;
  videoSrc: string;
  audioFilename: string | null;
  durationInSeconds: number;
  /** Stock clip length, so a clip shorter than the scene can be looped. */
  sourceDurationInSeconds?: number;
  captions: Array<{ text: string; startMs: number; endMs: number; emoji?: string }>;
}

/**
 * Renders the assembled video, returning the file and where it was saved.
 *
 * `taskId` is null when the render succeeded but storing it in the library did
 * not — the download still works, it just is not listed for publishing.
 */
export async function assembleVideo(
  scenes: AssembleScene[],
  title?: string,
): Promise<{ blob: Blob; taskId: string | null }> {
  const response = await fetch("/api/scripts/assemble", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenes, title }),
  });

  if (!response.ok) {
    throw new Error(formatSupportMessage(await parseApiError(response, "Assembly failed")));
  }

  return {
    blob: await response.blob(),
    taskId: response.headers.get("x-supoclip-task-id"),
  };
}

/** Recomputes the total after the user edits scene durations by hand. */
export function totalDuration(scenes: ScriptScene[]): number {
  return Math.round(scenes.reduce((sum, scene) => sum + (scene.duration_seconds || 0), 0) * 10) / 10;
}
