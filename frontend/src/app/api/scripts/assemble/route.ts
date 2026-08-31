import fs from "node:fs/promises";

import { NextResponse } from "next/server";

import { getServerSession } from "@/server/session";
import { fetchBackend } from "@/server/backend-api";
import { renderComposition } from "@/server/remotion-render";
import { DEFAULT_SUBTITLE_STYLE } from "@/remotion/types";

// Assembly renders a multi-scene video in a headless browser: far past the
// default budget, and Node-only.
export const runtime = "nodejs";
export const maxDuration = 900;

/**
 * Fetch one narration file from the backend and inline it.
 *
 * A scene whose audio cannot be fetched renders silent rather than failing the
 * whole assembly — losing one scene's voice is better than losing the video.
 */
async function fetchNarrationDataUrl(
  userId: string,
  filename: string,
): Promise<string> {
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
 * Store the finished video as a task so it can be published later.
 *
 * Returns null on failure rather than throwing: the render succeeded, and
 * losing the download because the library write failed would be the worse
 * outcome.
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
 * Assemble a generated script into a video.
 *
 * Each scene is its stock clip, its narration, and its captions, laid end to
 * end. Scene length comes from the narration rather than the script's estimate:
 * those estimates run more than double the real length, so assembling on them
 * would pad every scene with silence.
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

  // Narration is inlined as a data URL rather than linked.
  //
  // The rendering browser has no session cookie, so pointing it at
  // /api/scripts/narration/... returns 401 and the video comes out silent.
  // Fetching here — where the session exists — and embedding the bytes avoids
  // inventing an auth bypass for the renderer. Short-form narration is a few
  // hundred KB per scene, which is fine to carry in the props.
  const scenes = await Promise.all(
    incoming.map(async (scene, index) => ({
      order: scene.order ?? index + 1,
      videoSrc: scene.videoSrc ?? "",
      audioSrc: scene.audioFilename
        ? await fetchNarrationDataUrl(session.user.id, scene.audioFilename)
        : "",
      durationInSeconds: scene.durationInSeconds ?? 0,
      sourceDurationInSeconds: scene.sourceDurationInSeconds,
      captions: Array.isArray(scene.captions) ? scene.captions : [],
    })),
  );

  const usable = scenes.filter((scene) => scene.durationInSeconds > 0);
  if (usable.length === 0) {
    return NextResponse.json(
      { error: "No scene has a duration. Narrate the script first." },
      { status: 400 },
    );
  }

  let rendered: Awaited<ReturnType<typeof renderComposition>> | null = null;

  try {
    rendered = await renderComposition({
      compositionId: "Generated",
      inputProps: {
        scenes: usable,
        style: { ...DEFAULT_SUBTITLE_STYLE, ...(payload.style ?? {}) },
      },
    });

    const file = await fs.readFile(rendered.outputPath);

    // Keep it in the platform as well as handing it back. A generated video is
    // saved as a completed task so it appears in the listing and can be
    // scheduled and published exactly like a clipped one. A failure here is
    // logged but not fatal: the user still gets their download.
    const saved = await saveToLibrary(session.user.id, file, {
      title: typeof payload.title === "string" ? payload.title : undefined,
      duration: usable.reduce((total, scene) => total + scene.durationInSeconds, 0),
    });

    return new Response(new Uint8Array(file), {
      status: 200,
      headers: {
        "Content-Type": "video/mp4",
        "Content-Disposition": 'attachment; filename="generated.mp4"',
        "Content-Length": String(file.byteLength),
        // Lets the client link straight to the saved video.
        ...(saved ? { "x-supoclip-task-id": saved.task_id } : {}),
      },
    });
  } catch (error) {
    console.error("Assembly failed:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Assembly failed" },
      { status: 500 },
    );
  } finally {
    await rendered?.cleanup().catch(() => undefined);
  }
}
