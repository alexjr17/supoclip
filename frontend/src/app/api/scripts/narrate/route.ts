import { NextResponse } from "next/server";

import { createTextProxyResponse, fetchBackend } from "@/server/backend-api";
import { getServerSession } from "@/server/session";

// Synthesising every scene is several network round trips; well past the
// default budget for a short script.
export const maxDuration = 300;

export async function POST(request: Request) {
  const session = await getServerSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.text();

  const upstream = await fetchBackend("/scripts/narrate", {
    method: "POST",
    userId: session.user.id,
    // charset is explicit: narration carries accented text, and the backend
    // rejects the body outright if it is decoded as anything but UTF-8.
    extraHeaders: { "Content-Type": "application/json; charset=utf-8" },
    body,
  });

  return createTextProxyResponse(upstream);
}
