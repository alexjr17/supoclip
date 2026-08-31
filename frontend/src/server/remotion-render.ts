import path from "node:path";
import os from "node:os";
import fs from "node:fs/promises";
import { createRequire } from "node:module";

import type { CaptionWord, HookConfig, SubtitleStyle } from "@/remotion/types";

/**
 * Load Remotion's Node packages at runtime, out of webpack's sight.
 *
 * They ship native .node binaries (the rspack binding, the browser launcher)
 * that webpack cannot parse, and it fails the whole route trying. A dynamic
 * import() is not enough — webpack still walks it — so the specifier is held in
 * a variable, which defeats static analysis, and resolved with a real require.
 */
const nodeRequire = createRequire(import.meta.url);

function loadRemotion<T>(packageName: string): T {
  return nodeRequire(packageName) as T;
}

/**
 * Server-side Remotion rendering.
 *
 * This is the only way to get colour emoji into an exported clip. The ffmpeg
 * path burns captions with libass, which cannot render colour bitmap emoji
 * fonts (NotoColorEmoji is CBDT and only loads at fixed strike sizes), so it
 * falls back to a monochrome face and every emoji comes out grey. Remotion
 * rasterises the same React component the preview uses, in a real browser,
 * where colour emoji need no special handling.
 *
 * The bundle is expensive to build and identical between renders, so it is
 * created once per process and reused.
 */

let bundlePromise: Promise<string> | null = null;

async function getBundle(): Promise<string> {
  if (!bundlePromise) {
    bundlePromise = (async () => {
      const bundlerName = "@remotion/bundler";
      const { bundle } = loadRemotion<typeof import("@remotion/bundler")>(bundlerName);
      return bundle({
        entryPoint: path.join(process.cwd(), "src/remotion/root.tsx"),
        // Next's own webpack config is not reusable here; Remotion builds its
        // own, and only needs the alias so "@/..." imports resolve.
        webpackOverride: (config) => ({
          ...config,
          resolve: {
            ...config.resolve,
            alias: {
              ...(config.resolve?.alias ?? {}),
              "@": path.join(process.cwd(), "src"),
            },
          },
        }),
      });
    })();
  }
  return bundlePromise;
}

export interface RenderClipOptions {
  videoSrc: string;
  durationInSeconds: number;
  captions: CaptionWord[];
  style: SubtitleStyle;
  hook: HookConfig | null;
  /** Called with 0-1 as rendering proceeds. */
  onProgress?: (progress: number) => void;
}

export interface RenderCompositionOptions {
  compositionId: string;
  inputProps: Record<string, unknown>;
  onProgress?: (progress: number) => void;
}

export interface RenderedClip {
  outputPath: string;
  cleanup: () => Promise<void>;
}

/** Render any composition in the bundle. */
export async function renderComposition(
  options: RenderCompositionOptions,
): Promise<RenderedClip> {
  const rendererName = "@remotion/renderer";
  const { getCompositions, renderMedia, ensureBrowser } =
    loadRemotion<typeof import("@remotion/renderer")>(rendererName);

  // Downloads Chrome Headless Shell on first use; a no-op afterwards.
  await ensureBrowser();

  const serveUrl = await getBundle();
  const { compositionId, inputProps } = options;

  const compositions = await getCompositions(serveUrl, { inputProps });
  const composition = compositions.find((item) => item.id === compositionId);
  if (!composition) {
    throw new Error(`Remotion composition '${compositionId}' not found in the bundle`);
  }

  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), "supoclip-render-"));
  const outputPath = path.join(outputDir, "clip.mp4");

  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: outputPath,
    inputProps,
    onProgress: options.onProgress
      ? ({ progress }) => options.onProgress?.(progress)
      : undefined,
  });

  return {
    outputPath,
    cleanup: () => fs.rm(outputDir, { recursive: true, force: true }),
  };
}

/** Render a single edited clip. */
export function renderClip(options: RenderClipOptions): Promise<RenderedClip> {
  return renderComposition({
    compositionId: "Clip",
    inputProps: {
      videoSrc: options.videoSrc,
      durationInSeconds: options.durationInSeconds,
      captions: options.captions,
      style: options.style,
      hook: options.hook,
    },
    onProgress: options.onProgress,
  });
}
