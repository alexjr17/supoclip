import { NextResponse } from "next/server";

import { getServerSession } from "@/server/session";
import { getJob, isFinished } from "@/server/render-jobs";

export const runtime = "nodejs";
export const maxDuration = 900;

const POLL_INTERVAL_MS = 1000;

/**
 * Progress for a running assembly, as Server-Sent Events.
 *
 * Mirrors how the clipping pipeline reports progress, so the generation flow
 * behaves the same way from the user's side: the work runs in the background
 * and the page follows it.
 *
 * The job is polled from memory rather than pushed, because Remotion reports
 * progress through a callback rather than an event emitter. A second is fine
 * for something that takes minutes.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const session = await getServerSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { jobId } = await params;
  if (!getJob(jobId)) {
    return NextResponse.json({ error: "Job not found" }, { status: 404 });
  }

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      let closed = false;

      const send = (data: unknown) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
        } catch {
          closed = true;
        }
      };

      while (!closed) {
        const job = getJob(jobId);

        if (!job) {
          // Swept after completion: the client reconnected too late. The video
          // is still in the library, so this is not an error.
          send({ status: "done", progress: 1, message: "Finished", taskId: null });
          break;
        }

        send({
          status: job.status,
          progress: job.progress,
          message: job.message,
          taskId: job.taskId,
          error: job.error,
        });

        if (isFinished(job)) break;

        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }

      if (!closed) {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Without this a proxy can hold the whole stream until it ends, which
      // defeats the point.
      "X-Accel-Buffering": "no",
    },
  });
}
