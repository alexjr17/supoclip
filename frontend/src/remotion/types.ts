export interface CaptionWord {
  text: string;
  /** Milliseconds from the start of the clip. */
  startMs: number;
  endMs: number;
  /** Emoji rendered right after the word, when the annotator picked one. */
  emoji?: string;
}

export type SubtitleAnimation = "none" | "word-highlight" | "pop" | "karaoke";

export interface SubtitleStyle {
  fontFamily: string;
  fontSize: number;
  fontColor: string;
  highlightColor: string;
  borderColor: string;
  borderWidth: number;
  /** 0 hides the caption background entirely. */
  bgOpacity: number;
  animation: SubtitleAnimation;
  /** Vertical position as a fraction of frame height (0.75 = 75% down). */
  positionY: number;
}

export interface HookConfig {
  text: string;
  /** How long the hook stays on screen from the start of the clip. */
  displayDurationSec: number;
}

export interface ClipCompositionProps {
  videoSrc: string;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  captions: CaptionWord[];
  style: SubtitleStyle;
  hook: HookConfig | null;
}

export const DEFAULT_SUBTITLE_STYLE: SubtitleStyle = {
  fontFamily: "TikTokSans-Regular",
  fontSize: 52,
  fontColor: "#FFFFFF",
  highlightColor: "#FFDD00",
  borderColor: "#000000",
  borderWidth: 3,
  bgOpacity: 0,
  animation: "word-highlight",
  // Matches where the ffmpeg pipeline burns captions today.
  positionY: 0.75,
};
