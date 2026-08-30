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

/** Recomputes the total after the user edits scene durations by hand. */
export function totalDuration(scenes: ScriptScene[]): number {
  return Math.round(scenes.reduce((sum, scene) => sum + (scene.duration_seconds || 0), 0) * 10) / 10;
}
