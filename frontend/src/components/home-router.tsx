"use client";

import dynamic from "next/dynamic";

import LandingPage from "@/components/landing-page";
import { useSession } from "@/lib/auth-client";
import { isLandingOnlyModeEnabled } from "@/lib/app-flags";

// Signed-in users land on the chooser; the clipping form itself now lives at
// /create so the two creation flows can sit side by side.
const HomeChooser = dynamic(
  () => import("@/components/home-chooser").then((mod) => mod.HomeChooser),
  { ssr: false },
);

export function HomeRouter() {
  const { data: session, isPending } = useSession();

  if (!isLandingOnlyModeEnabled && !isPending && session?.user) {
    return <HomeChooser />;
  }

  return <LandingPage />;
}
