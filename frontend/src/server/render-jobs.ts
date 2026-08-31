import { randomUUID } from "node:crypto";

/**
 * Background render jobs with progress.
 *
 * Assembly renders a multi-scene video in a headless browser: minutes of work
 * for anything past a handful of scenes. Holding the HTTP request open for that
 * gives the user a button that sits silent with no way to tell "slow" from
 * "hung" — which is exactly what happened. So the request starts a job and
 * returns immediately, and the client follows progress on a separate stream,
 * the same shape the clipping pipeline already uses.
 *
 * State lives in this process rather than Redis. A dev server restart loses the
 * progress channel, but not the work: a finished render is saved to the library
 * before the job is marked done, so the video survives even if nobody was
 * watching. Moving this to Redis is what a multi-instance deployment would need.
 */

export type RenderJobStatus = "queued" | "rendering" | "saving" | "done" | "error";

export interface RenderJob {
  id: string;
  status: RenderJobStatus;
  /** 0-1 while rendering. */
  progress: number;
  message: string;
  /** Set once the video is stored and publishable. */
  taskId: string | null;
  error: string | null;
  startedAt: number;
  finishedAt: number | null;
}

const jobs = new Map<string, RenderJob>();

// Finished jobs are kept briefly so a client that reconnects still sees the
// outcome, then dropped so the map cannot grow without bound.
const RETAIN_FINISHED_MS = 10 * 60 * 1000;

function sweep() {
  const now = Date.now();
  for (const [id, job] of jobs) {
    if (job.finishedAt && now - job.finishedAt > RETAIN_FINISHED_MS) {
      jobs.delete(id);
    }
  }
}

export function createJob(): RenderJob {
  sweep();
  const job: RenderJob = {
    id: randomUUID(),
    status: "queued",
    progress: 0,
    message: "Queued",
    taskId: null,
    error: null,
    startedAt: Date.now(),
    finishedAt: null,
  };
  jobs.set(job.id, job);
  return job;
}

export function getJob(id: string): RenderJob | undefined {
  return jobs.get(id);
}

export function updateJob(id: string, patch: Partial<RenderJob>): void {
  const job = jobs.get(id);
  if (!job) return;
  Object.assign(job, patch);
  if (patch.status === "done" || patch.status === "error") {
    job.finishedAt = Date.now();
  }
}

export function isFinished(job: RenderJob): boolean {
  return job.status === "done" || job.status === "error";
}
