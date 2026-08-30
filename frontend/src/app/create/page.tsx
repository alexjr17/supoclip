"use client";

import dynamic from "next/dynamic";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/lib/auth-client";

// The clipping form is a large client component; keep it out of the shared
// bundle so the chooser at / stays light.
const HomeApp = dynamic(() => import("@/components/home-app"), { ssr: false });

export default function CreateClipPage() {
  const { data: session, isPending } = useSession();

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white p-4">
        <div className="space-y-4">
          <Skeleton className="mx-auto h-4 w-32" />
          <Skeleton className="mx-auto h-4 w-48" />
        </div>
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="min-h-screen bg-white">
        <div className="mx-auto max-w-4xl px-4 py-24 text-center">
          <h1 className="mb-4 text-3xl font-bold text-black">Sign In Required</h1>
          <p className="mb-8 text-gray-600">You need to sign in to create clips</p>
          <Link href="/sign-in">
            <Button size="lg">Sign In</Button>
          </Link>
        </div>
      </div>
    );
  }

  return <HomeApp />;
}
