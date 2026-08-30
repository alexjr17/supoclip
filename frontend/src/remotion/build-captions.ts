import { annotateCaptionWords } from "@/lib/emoji-captions";

import type { CaptionWord } from "./types";

export interface SourceWord {
  text: string;
  /** Seconds from the start of the clip. */
  start: number;
  end: number;
}

/**
 * Turn word timings into caption words, attaching the same emojis the render
 * pipeline picks.
 *
 * `annotateCaptionWords` mirrors `emoji_captions.py` on the backend, so the
 * preview and the burned-in captions choose identical emojis — the only
 * difference is that the browser draws them in colour.
 */
export function buildCaptions(
  words: SourceWord[],
  { showEmojis = true }: { showEmojis?: boolean } = {},
): CaptionWord[] {
  const texts = words.map((word) => word.text);
  const emojiByIndex = annotateCaptionWords(texts, { enableEmoji: showEmojis });

  return words.map((word, index) => ({
    text: word.text,
    startMs: Math.round(word.start * 1000),
    endMs: Math.round(word.end * 1000),
    emoji: emojiByIndex.get(index) || undefined,
  }));
}

/**
 * Project source-video word timings into clip time.
 *
 * The EDL gives words against the master video and the segments the clip is cut
 * from. A clip is those segments played back to back, so a word's position is
 * its offset inside its segment plus the length of every segment before it.
 * Words falling in the gaps between segments were cut and are dropped.
 */
export function mapWordsToClipTime(
  words: SourceWord[],
  segments: Array<{ start: number; end: number }>,
): SourceWord[] {
  if (segments.length === 0) return [];

  const mapped: SourceWord[] = [];
  let elapsed = 0;

  for (const segment of segments) {
    const length = segment.end - segment.start;

    for (const word of words) {
      // Keep a word when its midpoint falls inside the segment, so one clipped
      // at a boundary lands on exactly one side instead of being duplicated.
      const midpoint = (word.start + word.end) / 2;
      if (midpoint < segment.start || midpoint >= segment.end) continue;

      mapped.push({
        text: word.text,
        start: elapsed + Math.max(0, word.start - segment.start),
        end: elapsed + Math.min(length, word.end - segment.start),
      });
    }

    elapsed += length;
  }

  return mapped.sort((a, b) => a.start - b.start);
}

/**
 * Fallback when no word timings exist: spread the clip's text evenly.
 *
 * Rough, but it keeps the preview useful for clips transcribed before word
 * timings were stored, rather than showing no captions at all.
 */
export function estimateCaptions(
  text: string,
  durationSeconds: number,
  { showEmojis = true }: { showEmojis?: boolean } = {},
): CaptionWord[] {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0 || durationSeconds <= 0) return [];

  const perWord = (durationSeconds * 1000) / words.length;
  return buildCaptions(
    words.map((word, index) => ({
      text: word,
      start: (index * perWord) / 1000,
      end: ((index + 1) * perWord) / 1000,
    })),
    { showEmojis },
  );
}
