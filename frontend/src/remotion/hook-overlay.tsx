"use client";

import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import type { HookConfig } from "./types";

/**
 * The AI-written hook title, burned into the top safe area for the first
 * seconds — the same treatment `build_hook_title_ass` applies in the render
 * pipeline, so the preview matches the output.
 */
export function HookOverlay({ hook }: { hook: HookConfig }) {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  const endFrame = Math.round(hook.displayDurationSec * fps);
  if (frame > endFrame) return null;

  const entrance = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 160, mass: 0.5 },
    from: 0,
    to: 1,
  });

  // Fade out over the last half second rather than cutting, which reads as a
  // dropped frame at 30fps.
  const fadeFrames = Math.round(fps * 0.5);
  const opacity = interpolate(
    frame,
    [0, fadeFrames, endFrame - fadeFrames, endFrame],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <div
      style={{
        position: "absolute",
        top: "8%",
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        padding: `0 ${Math.round(width * 0.08)}px`,
        opacity,
        transform: `translateY(${interpolate(entrance, [0, 1], [-24, 0])}px)`,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0,0,0,0.82)",
          color: "#FFFFFF",
          padding: "0.5em 0.75em",
          borderRadius: "0.35em",
          fontFamily: "system-ui, -apple-system, sans-serif",
          fontSize: Math.round(width * 0.055),
          fontWeight: 800,
          lineHeight: 1.2,
          textAlign: "center",
          textWrap: "balance",
        }}
      >
        {hook.text}
      </div>
    </div>
  );
}
