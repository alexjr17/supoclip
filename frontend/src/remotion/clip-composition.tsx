"use client";

import React from "react";
import { AbsoluteFill, OffthreadVideo } from "remotion";

import { HookOverlay } from "./hook-overlay";
import { Subtitles } from "./subtitles";
import type { ClipCompositionProps } from "./types";

/**
 * A clip as Remotion sees it: the rendered video with captions and the hook
 * drawn on top as React.
 *
 * In the Player this is a live preview; the same component is what a server
 * render would rasterise, so what the user sees is what the file contains.
 */
export function ClipComposition({
  videoSrc,
  captions,
  style,
  hook,
}: Omit<ClipCompositionProps, "durationInFrames" | "fps" | "width" | "height">) {
  // OffthreadVideo always, never <Video>.
  //
  // The previous `typeof window === "undefined" ? OffthreadVideo : Video` was
  // wrong: during a render the composition runs INSIDE headless Chrome, so
  // `window` exists and <Video> was always chosen. <Video> depends on the HTML
  // element seeking to the right position, which is not frame-accurate under
  // render — frames get duplicated or skipped and the result visibly stutters.
  // OffthreadVideo extracts the exact frame instead, and works in the Player.
  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      {/* An empty source renders on black rather than throwing: a caption-only
          render is a legitimate case, and a clip whose file is momentarily
          unreachable should not take the whole render down with it. */}
      {videoSrc ? (
        <OffthreadVideo
          src={videoSrc}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
      ) : null}

      {hook ? <HookOverlay hook={hook} /> : null}

      <Subtitles captions={captions} style={style} />
    </AbsoluteFill>
  );
}
