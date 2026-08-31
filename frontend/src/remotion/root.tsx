import React from "react";
import { Composition, registerRoot } from "remotion";

import { ClipComposition } from "./clip-composition";
import {
  GeneratedVideo,
  totalFrames,
  type GeneratedVideoProps,
} from "./generated-video";
import { DEFAULT_SUBTITLE_STYLE, type ClipCompositionProps } from "./types";

export const CLIP_COMPOSITION_ID = "Clip";
export const GENERATED_COMPOSITION_ID = "Generated";
export const RENDER_FPS = 30;

const DEFAULT_PROPS: Omit<
  ClipCompositionProps,
  "durationInFrames" | "fps" | "width" | "height"
> = {
  videoSrc: "",
  captions: [],
  style: DEFAULT_SUBTITLE_STYLE,
  hook: null,
};

/**
 * Remotion's entry point for server rendering.
 *
 * The same <ClipComposition/> the Player uses in the browser, so a rendered
 * file and the on-screen preview cannot drift apart.
 *
 * Duration is supplied per render through calculateMetadata rather than being
 * fixed here: every clip is a different length.
 */
export function RemotionRoot() {
  return (
    <>
      <ClipComp />
      <GeneratedComp />
    </>
  );
}

// Typed explicitly: an inferred `never[]` for scenes does not satisfy
// Composition's prop constraint.
const GENERATED_DEFAULT_PROPS: GeneratedVideoProps = {
  scenes: [],
  style: DEFAULT_SUBTITLE_STYLE,
};

function GeneratedComp() {
  return (
    <Composition
      id={GENERATED_COMPOSITION_ID}
      component={GeneratedVideo}
      durationInFrames={RENDER_FPS * 10}
      fps={RENDER_FPS}
      width={1080}
      height={1920}
      defaultProps={GENERATED_DEFAULT_PROPS}
      calculateMetadata={({ props }) => ({
        // Total length is the sum of the scenes, each already timed by its own
        // narration.
        durationInFrames: totalFrames(props.scenes ?? [], RENDER_FPS),
      })}
    />
  );
}

function ClipComp() {
  return (
    <Composition
      id={CLIP_COMPOSITION_ID}
      component={ClipComposition}
      durationInFrames={RENDER_FPS * 10}
      fps={RENDER_FPS}
      width={1080}
      height={1920}
      defaultProps={DEFAULT_PROPS}
      calculateMetadata={({ props }) => {
        // The clip's own length is authoritative: deriving it from the last
        // caption would truncate a clip that ends on silence, and a clip with
        // no captions at all would come out one second long.
        const explicit = (props as { durationInSeconds?: number }).durationInSeconds;
        if (explicit && explicit > 0) {
          return { durationInFrames: Math.ceil(explicit * RENDER_FPS) };
        }

        const captions = props.captions ?? [];
        const lastMs = captions.length
          ? Math.max(...captions.map((word) => word.endMs))
          : 0;
        return { durationInFrames: Math.max(1, Math.ceil((lastMs / 1000) * RENDER_FPS)) };
      }}
    />
  );
}

registerRoot(RemotionRoot);
