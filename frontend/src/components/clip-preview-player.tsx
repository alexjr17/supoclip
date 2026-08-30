"use client";

import { useMemo, useRef } from "react";
import { Player, type PlayerRef } from "@remotion/player";

import { ClipComposition } from "@/remotion/clip-composition";
import {
  DEFAULT_SUBTITLE_STYLE,
  type CaptionWord,
  type HookConfig,
  type SubtitleStyle,
} from "@/remotion/types";

const FPS = 30;

interface ClipPreviewPlayerProps {
  videoSrc: string;
  durationSeconds: number;
  captions: CaptionWord[];
  hook?: HookConfig | null;
  style?: Partial<SubtitleStyle>;
  className?: string;
}

/**
 * Real preview of a clip: the actual video with the actual captions, played by
 * Remotion rather than approximated with a mock phone frame.
 *
 * Two things this buys over the old preview. Captions are drawn by the browser,
 * so emoji appear in colour — the burned-in ffmpeg path renders them with a
 * monochrome font because libass cannot handle colour bitmap emoji fonts. And
 * because the same component would drive a server render, what is on screen is
 * what the exported file contains.
 */
export function ClipPreviewPlayer({
  videoSrc,
  durationSeconds,
  captions,
  hook = null,
  style,
  className,
}: ClipPreviewPlayerProps) {
  const playerRef = useRef<PlayerRef>(null);

  const resolvedStyle = useMemo(
    () => ({ ...DEFAULT_SUBTITLE_STYLE, ...style }),
    [style],
  );

  const inputProps = useMemo(
    () => ({ videoSrc, captions, style: resolvedStyle, hook }),
    [videoSrc, captions, resolvedStyle, hook],
  );

  // Remotion needs a positive integer frame count; a clip whose duration has
  // not loaded yet would otherwise throw.
  const durationInFrames = Math.max(1, Math.round(durationSeconds * FPS));

  return (
    <div className={className}>
      <Player
        ref={playerRef}
        component={ClipComposition}
        inputProps={inputProps}
        durationInFrames={durationInFrames}
        fps={FPS}
        compositionWidth={1080}
        compositionHeight={1920}
        style={{ width: "100%", borderRadius: 12, overflow: "hidden" }}
        controls
        acknowledgeRemotionLicense
      />
    </div>
  );
}
