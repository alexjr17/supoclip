"use client";

import React from "react";
import { AbsoluteFill, OffthreadVideo, Video } from "remotion";

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
  // OffthreadVideo is the accurate path for server rendering but needs a
  // Node-side extractor; in the browser Player it is unavailable, so the
  // plain Video tag is used there.
  const VideoTag = typeof window === "undefined" ? OffthreadVideo : Video;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      <VideoTag
        src={videoSrc}
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
      />

      {hook ? <HookOverlay hook={hook} /> : null}

      <Subtitles captions={captions} style={style} />
    </AbsoluteFill>
  );
}
