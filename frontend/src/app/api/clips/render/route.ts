import fs from "node:fs/promises";

import { NextResponse } from "next/server";

import { getServerSession } from "@/server/session";
import { renderClip } from "@/server/remotion-render";
import { DEFAULT_SUBTITLE_STYLE } from "@/remotion/types";

// Rendering spawns a headless browser and encodes video: well past the default
// serverless budget, and it must run on Node rather than the edge runtime.
export const runtime = "nodejs";
export const maxDuration = 600;

/**
 * Render a clip through Remotion and return the mp4.
 *
 * The reason to render here rather than in the ffmpeg pipeline: libass cannot
 * draw colour emoji, so burned-in captions render them monochrome. A browser
 * does it natively.
 */
export async function POST(request: Request) {
  const session = await getServerSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let payload: {
    videoSrc?: string;
    durationInSeconds?: number;
    captions?: unknown;
    style?: Record<string, unknown>;
    hook?: { text: string; displayDurationSec: number } | null;
  };

  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { videoSrc, durationInSeconds } = payload;
  if (!videoSrc || typeof videoSrc !== "string") {
    return NextResponse.json({ error: "videoSrc is required" }, { status: 400 });
  }
  if (!durationInSeconds || durationInSeconds <= 0) {
    return NextResponse.json(
      { error: "durationInSeconds must be greater than zero" },
      { status: 400 },
    );
  }
  if (!Array.isArray(payload.captions)) {
    return NextResponse.json({ error: "captions must be an array" }, { status: 400 });
  }

  let rendered: Awaited<ReturnType<typeof renderClip>> | null = null;

  try {
    rendered = await renderClip({
      videoSrc,
      durationInSeconds,
      captions: payload.captions as never,
      style: { ...DEFAULT_SUBTITLE_STYLE, ...(payload.style ?? {}) } as never,
      hook: payload.hook ?? null,
    });

    const file = await fs.readFile(rendered.outputPath);

    return new Response(new Uint8Array(file), {
      status: 200,
      headers: {
        "Content-Type": "video/mp4",
        "Content-Disposition": 'attachment; filename="clip.mp4"',
        "Content-Length": String(file.byteLength),
      },
    });
  } catch (error) {
    console.error("Remotion render failed:", error);
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Rendering failed",
      },
      { status: 500 },
    );
  } finally {
    // Always remove the temp directory, including when the read above throws.
    await rendered?.cleanup().catch(() => undefined);
  }
}
