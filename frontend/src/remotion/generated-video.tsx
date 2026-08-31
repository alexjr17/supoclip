"use client";

import React from "react";
import { AbsoluteFill, Audio, Loop, OffthreadVideo, Sequence } from "remotion";

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
  /**
   * Length of the stock clip itself, when known. A clip shorter than the scene
   * is looped; without this it would freeze on its last frame.
   */
  sourceDurationInSeconds?: number;
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
  // OffthreadVideo always, never <Video>.
  //
  // The previous `typeof window === "undefined" ? OffthreadVideo : Video` was
  // wrong: during a render the composition runs INSIDE headless Chrome, so
  // `window` exists and <Video> was always chosen. <Video> depends on the HTML
  // element seeking to the right position, which is not frame-accurate under
  // render — frames get duplicated or skipped and the result visibly stutters.
  // OffthreadVideo extracts the exact frame instead, and works in the Player.

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
              <SceneFootage
                src={scene.videoSrc}
                sceneFrames={durationInFrames}
                sourceDurationInSeconds={scene.sourceDurationInSeconds}
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

/**
 * One scene's stock clip, looped when it is shorter than the scene.
 *
 * OffthreadVideo has no `loop` prop — that belongs to <Video>, which is not
 * frame-accurate under render. Remotion's <Loop> repeats the clip instead, and
 * a clip longer than the scene is simply cut off by the enclosing Sequence.
 * Without a known source length there is nothing to loop against, so the clip
 * plays once and holds its last frame.
 */
function SceneFootage({
  src,
  sceneFrames,
  sourceDurationInSeconds,
}: {
  src: string;
  sceneFrames: number;
  sourceDurationInSeconds?: number;
}) {
  const style = { width: "100%", height: "100%", objectFit: "cover" as const };
  const sourceFrames = sourceDurationInSeconds
    ? Math.max(1, Math.floor(sourceDurationInSeconds * 30))
    : 0;

  if (!sourceFrames || sourceFrames >= sceneFrames) {
    return <OffthreadVideo src={src} style={style} />;
  }

  return (
    <Loop durationInFrames={sourceFrames} layout="none">
      <OffthreadVideo src={src} style={style} />
    </Loop>
  );
}
