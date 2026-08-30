export interface EdlSegment {
  start: number;
  end: number;
}

export interface TranscriptWord {
  text: string;
  start: number;
  end: number;
}

export interface ClipEdl {
  clip_id: string;
  task_id: string;
  segments: EdlSegment[];
  /** False for clips rendered before source maps existed: they can only shrink. */
  has_source_map: boolean;
  /** Null when the master is a YouTube URL that is not on disk right now. */
  source_duration: number | null;
  total_duration: number;
  snap_window_seconds: number;
  words: TranscriptWord[];
}

export const MIN_SEGMENT_SECONDS = 0.5;

export function segmentsDuration(segments: EdlSegment[]): number {
  return segments.reduce((total, segment) => total + (segment.end - segment.start), 0);
}

export function formatTimecode(seconds: number): string {
  if (!Number.isFinite(seconds)) return "–:––";
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

/**
 * Move a cut onto the nearest word boundary, mirroring the backend's rule.
 *
 * Done on the client too so dragging *feels* snapped while the pointer moves;
 * the backend still snaps on save, and is the authority.
 */
export function snapToWords(
  time: number,
  words: TranscriptWord[],
  window: number,
  prefer: "nearest" | "start" | "end" = "nearest",
): number {
  if (words.length === 0) return time;

  let best: number | null = null;
  let bestDistance = Infinity;

  for (const word of words) {
    const candidates: number[] = [];
    if (prefer === "nearest" || prefer === "start") candidates.push(word.start);
    if (prefer === "nearest" || prefer === "end") candidates.push(word.end);

    for (const candidate of candidates) {
      const distance = Math.abs(candidate - time);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = candidate;
      }
    }
  }

  return best !== null && bestDistance <= window ? best : time;
}

export async function fetchClipEdl(taskId: string, clipId: string): Promise<ClipEdl> {
  const response = await fetch(`/api/tasks/${taskId}/clips/${clipId}/edl`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to load the clip timeline"));
  }
  return response.json();
}

export async function rerenderClip(
  taskId: string,
  clipId: string,
  segments: EdlSegment[],
): Promise<{ clip_id: string; filename: string; duration: number; segments: EdlSegment[] }> {
  const response = await fetch(`/api/tasks/${taskId}/clips/${clipId}/rerender`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segments }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Failed to re-render the clip"));
  }
  return response.json();
}

async function readError(response: Response, fallback: string): Promise<string> {
  const text = await response.text();
  if (!text) return fallback;
  try {
    const data = JSON.parse(text);
    return data.detail || data.error || fallback;
  } catch {
    return fallback;
  }
}
