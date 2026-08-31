import path from "node:path";
import os from "node:os";
import fs from "node:fs/promises";

import type { CaptionWord, HookConfig, SubtitleStyle } from "@/remotion/types";

/**
 * Load Remotion's Node packages at runtime, out of webpack's sight.
 *
 * They ship native .node binaries (the rspack binding, the browser launcher)
 * that webpack cannot parse and fails the whole route on. Three attempts were
 * needed to get out of its way:
 *
 *   - serverExternalPackages alone: webpack still walks a dynamic import().
 *   - createRequire + a variable specifier: webpack replaces the call with its
 *     own empty context module, so the route compiles and then throws
 *     "Cannot find module" from webpackEmptyContext at runtime.
 *   - eval("require"): webpack cannot analyse it at all, so the real Node
 *     require survives into the bundle and resolves from node_modules.
 *
 * The eval runs once, on a constant, and never on user input.
 */
const runtimeRequire: NodeRequire = eval("require");

function loadRemotion<T>(packageName: string): T {
  return runtimeRequire(packageName) as T;
}

/**
 * The Remotion bundle, built once per process.
 *
 * Bundling takes ~25s and the result is identical between renders, so it is
 * cached rather than rebuilt for every request.
 */
let bundlePromise: Promise<string> | null = null;

async function getBundle(): Promise<string> {
  if (!bundlePromise) {
    bundlePromise = (async () => {
      const { bundle } = loadRemotion<typeof import("@remotion/bundler")>(
        "@remotion/bundler",
      );
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

async function clearRenderTemp(activeBundle: string | null): Promise<void> {
  try {
    const tmp = os.tmpdir();
    const entries = await fs.readdir(tmp);

    const removable = entries.filter((name) => {
      const full = path.join(tmp, name);
      if (name.startsWith("react-motion-render")) return true;
      if (name.startsWith("remotion-") && name.includes("assets")) return true;
      if (name.startsWith("remotion-webpack-bundle")) {
        return !activeBundle || !activeBundle.includes(full);
      }
      return false;
    });

    await Promise.all(
      removable.map((name) =>
        fs.rm(path.join(tmp, name), { recursive: true, force: true }),
      ),
    );
  } catch (error) {
    console.warn("Could not clear Remotion temp directories:", error);
  }
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
    // Remotion defaults to one browser tab per core, and each tab pulls its
    // scene's stock clip independently. Ten parallel HD downloads made Pexels
    // drop connections outright (net::ERR_CONNECTION_CLOSED), leaving scenes
    // blank. Fewer tabs render slower but actually get their footage.
    concurrency: 2,
    // A stock clip can be tens of megabytes; the default media timeout is not
    // generous enough for that over a slow link.
    timeoutInMilliseconds: 120_000,
    onProgress: options.onProgress
      ? ({ progress }) => options.onProgress?.(progress)
      : undefined,
  });

  return {
    outputPath,
    cleanup: async () => {
      await fs.rm(outputDir, { recursive: true, force: true });
      await clearAssetCache();
    },
  };
}

/**
 * Delete the stock clips OffthreadVideo downloaded for this render.
 *
 * Remotion caches every fetched asset under /tmp and never reclaims it. Those
 * are whole stock videos: one ten-scene render left 467 MB behind, and enough
 * of them filled the host disk to the point where Docker itself would no
 * longer start. Failures here are ignored — a stale cache is a far smaller
 * problem than failing a render that already succeeded.
 */
async function clearAssetCache(): Promise<void> {
  try {
    const entries = await fs.readdir(os.tmpdir());
    await Promise.all(
      entries
        .filter((name) => name.startsWith("remotion-") && name.includes("assets"))
        .map((name) =>
          fs.rm(path.join(os.tmpdir(), name), { recursive: true, force: true }),
        ),
    );
  } catch (error) {
    console.warn("Could not clear the Remotion asset cache:", error);
  }
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
