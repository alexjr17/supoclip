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

/** Create the task up front so the user can watch it from the listing. */
async function startTask(userId: string, title?: string): Promise<string | null> {
  try {
    const upstream = await fetchBackend("/scripts/start-video", {
      method: "POST",
      userId,
      extraHeaders: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title?.slice(0, 200) || "AI generated video" }),
    });
    if (!upstream.ok) return null;
    return (await upstream.json()).task_id ?? null;
  } catch (error) {
    console.error("Could not create the generation task:", error);
    return null;
  }
}

/**
 * Mirror progress onto the task.
 *
 * Best-effort and never awaited on the render's critical path: a dropped
 * progress update must not slow down or fail the render itself.
 */
async function reportTask(
  userId: string,
  taskId: string,
  progress: number,
  message: string,
): Promise<void> {
  try {
    await fetchBackend("/scripts/video-progress", {
      method: "POST",
      userId,
      extraHeaders: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, progress, message }),
    });
  } catch {
    // Ignored on purpose; see above.
  }
}

async function attachToTask(
  userId: string,
  taskId: string,
  file: Buffer,
  duration: number,
): Promise<boolean> {
  try {
    const form = new FormData();
    form.append("file", new Blob([new Uint8Array(file)], { type: "video/mp4" }), "generated.mp4");
    form.append("task_id", taskId);
    form.append("duration", String(duration));

    const upstream = await fetchBackend("/scripts/attach-video", {
      method: "POST",
      userId,
      body: form,
    });
    if (!upstream.ok) {
      console.error("Attaching the generated video failed:", upstream.status);
      return false;
    }
    return true;
  } catch (error) {
    console.error("Attaching the generated video failed:", error);
    return false;
  }
}

async function failTask(userId: string, taskId: string, message: string): Promise<void> {
  try {
    await fetchBackend("/scripts/fail-video", {
      method: "POST",
      userId,
      extraHeaders: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, progress: 0, message }),
    });
  } catch {
    // Ignored: the render already failed, and the message is a courtesy.
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

  // Created before any work, so the video shows up in the listing immediately
  // with a progress bar, the same way a clipped one does.
  const taskId = await startTask(userId, payload.title);
  updateJob(jobId, { taskId, status: "rendering", message: "Fetching narration" });
  if (taskId) void reportTask(userId, taskId, 2, "Fetching narration");

  try {
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
    const duration = usable.reduce((total, scene) => total + scene.durationInSeconds, 0);

    updateJob(jobId, { message: "Downloading footage" });
    if (taskId) void reportTask(userId, taskId, 5, "Downloading footage");

    // Progress is mirrored to the task at intervals rather than on every
    // callback: Remotion fires per frame, and a database write per frame would
    // cost more than the render.
    let lastReported = 0;

    rendered = await renderComposition({
      compositionId: "Generated",
      inputProps: {
        scenes: usable,
        style: { ...DEFAULT_SUBTITLE_STYLE, ...(payload.style ?? {}) },
      },
      quality: payload.quality,
      onProgress: (progress) => {
        const message =
          progress < 0.02
            ? "Downloading footage"
            : `Rendering ${Math.round(progress * 100)}%`;
        updateJob(jobId, { progress, message });

        const percent = Math.round(progress * 90);
        if (taskId && percent >= lastReported + 5) {
          lastReported = percent;
          void reportTask(userId, taskId, Math.max(5, percent), message);
        }
      },
    });

    updateJob(jobId, { status: "saving", progress: 1, message: "Saving to your library" });
    if (taskId) void reportTask(userId, taskId, 95, "Saving");

    const file = await fs.readFile(rendered.outputPath);
    const attached = taskId ? await attachToTask(userId, taskId, file, duration) : false;

    updateJob(jobId, {
      status: "done",
      message: attached ? "Saved to your library" : "Rendered, but saving failed",
      taskId: attached ? taskId : null,
    });
  } catch (error) {
    console.error("Assembly failed:", error);
    const message = error instanceof Error ? error.message : "Assembly failed";
    if (taskId) await failTask(userId, taskId, message);
    updateJob(jobId, { status: "error", error: message, message: "Assembly failed" });
  } finally {
    await rendered?.cleanup().catch(() => undefined);
  }
}
