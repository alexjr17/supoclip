import { NextResponse } from "next/server";

import { createTextProxyResponse, fetchBackend } from "@/server/backend-api";
import { getServerSession } from "@/server/session";

export async function GET(request: Request) {
  const session = await getServerSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const language = new URL(request.url).searchParams.get("language") ?? "English";

  const upstream = await fetchBackend(
    `/scripts/voices?language=${encodeURIComponent(language)}`,
    { userId: session.user.id },
  );

  return createTextProxyResponse(upstream);
}
