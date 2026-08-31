"use client";

import React from "react";
import { AbsoluteFill, Audio, OffthreadVideo, Sequence, Video } from "remotion";

import { Subtitles } from "./subtitles";
import type { CaptionWord, SubtitleStyle } from "./types";

export interface GeneratedScene {
  order: number;
  /** Stock clip for this scene. Empty renders on black. */
  videoSrc: string;
  /** Synthesised narration. Empty leaves the scene silent. */
  audioSrc: string;
  /** Measured from the narration, not estimated from word count. */
  durationInSeconds: number;
  captions: CaptionWord[];
}

// A type alias, not an interface: Remotion's Composition requires props
// assignable to Record<string, unknown>, and interfaces get no implicit index
// signature while type aliases do.
export type GeneratedVideoProps = {
  scenes: GeneratedScene[];
  style: SubtitleStyle;
};

/**
 * A generated video: stock footage per scene, narrated, with captions.
 *
 * Scenes are laid end to end with each one lasting exactly as long as its
 * narration. That is why the narration step re-times the script — assembling on
 * the model's word-count estimate would pad every scene with silence, since the
 * estimates run more than double the real length.
 *
 * Captions are per-scene and already rebased to that scene's own timeline, so a
 * scene can be reordered or re-narrated without touching the others.
 */
export function GeneratedVideo({ scenes, style }: GeneratedVideoProps) {
  const VideoTag = typeof window === "undefined" ? OffthreadVideo : Video;

  let elapsedFrames = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      {scenes.map((scene) => {
        const durationInFrames = Math.max(1, Math.round(scene.durationInSeconds * 30));
        const from = elapsedFrames;
        elapsedFrames += durationInFrames;

        return (
          <Sequence
            key={`${scene.order}-${from}`}
            from={from}
            durationInFrames={durationInFrames}
          >
            {scene.videoSrc ? (
              <VideoTag
                src={scene.videoSrc}
                // The stock clip is almost never exactly the narration's
                // length. Looping keeps the frame filled for a short clip;
                // a long one is simply cut off by the sequence.
                loop
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            ) : null}

            {scene.audioSrc ? <Audio src={scene.audioSrc} /> : null}

            <Subtitles captions={scene.captions} style={style} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
}

export function totalFrames(scenes: GeneratedScene[], fps = 30): number {
  return Math.max(
    1,
    scenes.reduce(
      (total, scene) => total + Math.max(1, Math.round(scene.durationInSeconds * fps)),
      0,
    ),
  );
}
