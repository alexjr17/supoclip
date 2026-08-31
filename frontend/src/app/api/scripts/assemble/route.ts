import fs from "node:fs/promises";

import { NextResponse } from "next/server";

import { getServerSession } from "@/server/session";
import { fetchBackend } from "@/server/backend-api";
import { renderComposition, type RenderQuality } from "@/server/remotion-render";
import { createJob, updateJob } from "@/server/render-jobs";
import { DEFAULT_SUBTITLE_STYLE } from "@/remotion/types";

// The job outlives the response, so this handler must stay on Node.
export const runtime = "nodejs";
export const maxDuration = 900;

/**
 * Store the finished video as a task so it can be published later.
 *
 * Returns null on failure rather than throwing: the render succeeded, and
 * losing the video because the library write failed would be the worse outcome.
 */
async function saveToLibrary(
  userId: string,
  file: Buffer,
  meta: { title?: string; duration: number },
): Promise<{ task_id: string } | null> {
  try {
    const form = new FormData();
    form.append("file", new Blob([new Uint8Array(file)], { type: "video/mp4" }), "generated.mp4");
    form.append("title", meta.title?.slice(0, 200) || "AI generated video");
    form.append("duration", String(meta.duration));

    const upstream = await fetchBackend("/scripts/save-video", {
      method: "POST",
      userId,
      body: form,
    });

    if (!upstream.ok) {
      console.error("Saving the generated video failed:", upstream.status);
      return null;
    }
    return await upstream.json();
  } catch (error) {
    console.error("Saving the generated video failed:", error);
    return null;
  }
}

interface IncomingScene {
  order?: number;
  videoSrc?: string;
  audioFilename?: string;
  durationInSeconds?: number;
  sourceDurationInSeconds?: number;
  captions?: unknown;
}

/**
 * Narration is inlined as a data URL rather than linked.
 *
 * The rendering browser has no session cookie, so pointing it at
 * /api/scripts/narration/... returns 401 and the video comes out silent.
 * Fetching here — where the session exists — and embedding the bytes avoids
 * inventing an auth bypass for the renderer.
 */
async function fetchNarrationDataUrl(userId: string, filename: string): Promise<string> {
  try {
    const upstream = await fetchBackend(
      `/scripts/narration/${encodeURIComponent(filename)}`,
      { userId },
    );
    if (!upstream.ok) {
      console.error(`Narration ${filename} unavailable: HTTP ${upstream.status}`);
      return "";
    }
    const buffer = Buffer.from(await upstream.arrayBuffer());
    return `data:audio/mpeg;base64,${buffer.toString("base64")}`;
  } catch (error) {
    console.error(`Narration ${filename} could not be read:`, error);
    return "";
  }
}

/**
 * Start assembling a generated script into a video.
 *
 * Returns a job id immediately; the render runs in the background and reports
 * progress on /api/scripts/assemble/{jobId}. Holding the request open for the
 * several minutes a render takes left the button silent, with no way to tell
 * slow from hung.
 */
export async function POST(request: Request) {
  const session = await getServerSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let payload: {
    scenes?: IncomingScene[];
    style?: Record<string, unknown>;
    title?: string;
    quality?: RenderQuality;
  };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const incoming = payload.scenes;
  if (!Array.isArray(incoming) || incoming.length === 0) {
    return NextResponse.json({ error: "scenes must be a non-empty array" }, { status: 400 });
  }

  const usableCount = incoming.filter((scene) => (scene.durationInSeconds ?? 0) > 0).length;
  if (usableCount === 0) {
    return NextResponse.json(
      { error: "No scene has a duration. Narrate the script first." },
      { status: 400 },
    );
  }

  const job = createJob();

  // Deliberately not awaited: the response goes out now and the render carries
  // on in the background, reporting through the job.
  void runAssembly(job.id, session.user.id, incoming, payload);

  return NextResponse.json({ jobId: job.id, scenes: usableCount }, { status: 202 });
}

async function runAssembly(
  jobId: string,
  userId: string,
  incoming: IncomingScene[],
  payload: { style?: Record<string, unknown>; title?: string; quality?: RenderQuality },
) {
  let rendered: Awaited<ReturnType<typeof renderComposition>> | null = null;

  try {
    updateJob(jobId, { status: "rendering", message: "Fetching narration" });

    const scenes = await Promise.all(
      incoming.map(async (scene, index) => ({
        order: scene.order ?? index + 1,
        videoSrc: scene.videoSrc ?? "",
        audioSrc: scene.audioFilename
          ? await fetchNarrationDataUrl(userId, scene.audioFilename)
          : "",
        durationInSeconds: scene.durationInSeconds ?? 0,
        sourceDurationInSeconds: scene.sourceDurationInSeconds,
        captions: Array.isArray(scene.captions) ? scene.captions : [],
      })),
    );

    const usable = scenes.filter((scene) => scene.durationInSeconds > 0);

    updateJob(jobId, { message: "Downloading footage" });

    rendered = await renderComposition({
      compositionId: "Generated",
      inputProps: {
        scenes: usable,
        style: { ...DEFAULT_SUBTITLE_STYLE, ...(payload.style ?? {}) },
      },
      quality: payload.quality,
      onProgress: (progress) =>
        updateJob(jobId, {
          progress,
          // Remotion reports 0 while it is still pulling the stock clips, which
          // is the slowest part; saying "downloading" there is more honest than
          // showing a bar stuck at zero.
          message:
            progress < 0.02
              ? "Downloading footage"
              : `Rendering ${Math.round(progress * 100)}%`,
        }),
    });

    updateJob(jobId, { status: "saving", progress: 1, message: "Saving to your library" });

    const file = await fs.readFile(rendered.outputPath);
    const saved = await saveToLibrary(userId, file, {
      title: payload.title,
      duration: usable.reduce((total, scene) => total + scene.durationInSeconds, 0),
    });

    updateJob(jobId, {
      status: "done",
      message: saved ? "Saved to your library" : "Rendered, but saving to the library failed",
      taskId: saved?.task_id ?? null,
    });
  } catch (error) {
    console.error("Assembly failed:", error);
    updateJob(jobId, {
      status: "error",
      error: error instanceof Error ? error.message : "Assembly failed",
      message: "Assembly failed",
    });
  } finally {
    await rendered?.cleanup().catch(() => undefined);
  }
}
