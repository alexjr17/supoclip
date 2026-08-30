"use client";

import Link from "next/link";
import Image from "next/image";
import { ArrowRight, List, Scissors, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProfileSwitcher } from "@/components/profile-switcher";
import { useSession } from "@/lib/auth-client";

interface ModeCardProps {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  bullets: string[];
  cta: string;
  badge?: string;
  featured?: boolean;
}

function ModeCard({
  href,
  icon,
  title,
  description,
  bullets,
  cta,
  badge,
  featured,
}: ModeCardProps) {
  return (
    <Link href={href} className="group block">
      <div
        className={`flex h-full flex-col rounded-xl border p-6 transition-all hover:-translate-y-0.5 hover:shadow-md ${
          featured ? "border-stone-900 bg-white" : "border-gray-200 bg-white"
        }`}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div
            className={`flex h-11 w-11 items-center justify-center rounded-lg ${
              featured ? "bg-stone-900 text-white" : "bg-gray-100 text-black"
            }`}
          >
            {icon}
          </div>
          {badge && (
            <Badge variant="outline" className="text-[10px]">
              {badge}
            </Badge>
          )}
        </div>

        <h2 className="mb-1 text-lg font-semibold text-black">{title}</h2>
        <p className="mb-4 text-sm text-gray-600">{description}</p>

        <ul className="mb-6 space-y-1.5">
          {bullets.map((bullet) => (
            <li key={bullet} className="flex items-start gap-2 text-sm text-gray-600">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
              {bullet}
            </li>
          ))}
        </ul>

        <div className="mt-auto flex items-center gap-1.5 text-sm font-medium text-black">
          {cta}
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </div>
      </div>
    </Link>
  );
}

/**
 * Entry screen: the two ways to end up with a vertical clip.
 *
 * Clipping starts from a video that already exists; generation starts from an
 * idea. They share nothing until the render step, so they get separate doors
 * rather than one form with a mode toggle.
 */
export function HomeChooser() {
  const { data: session } = useSession();

  return (
    <div className="min-h-screen bg-white">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-3">
            <Image src="/logo.png" alt="SupoClip" width={24} height={24} className="rounded-lg" />
            <span className="text-xl font-bold text-black">SupoClip</span>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/list">
              <Button variant="outline" size="sm">
                <List className="h-4 w-4" />
                All generations
              </Button>
            </Link>
            <ProfileSwitcher />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-16">
        <div className="mb-10">
          <h1 className="mb-2 text-3xl font-bold text-black">
            {session?.user?.name ? `Hi ${session.user.name.split(" ")[0]}` : "What are we making?"}
          </h1>
          <p className="text-gray-600">
            Start from a video you already have, or from nothing but an idea.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <ModeCard
            href="/create"
            icon={<Scissors className="h-5 w-5" />}
            title="Clip a video"
            description="Paste a YouTube link or upload a file. The AI finds the moments worth cutting."
            bullets={[
              "Virality scoring picks the best segments",
              "Face-aware 9:16 crop with word-synced captions",
              "Publish straight to YouTube or TikTok",
            ]}
            cta="Start clipping"
          />

          <ModeCard
            href="/generate"
            icon={<Sparkles className="h-5 w-5" />}
            title="Generate with AI"
            description="Describe an idea. The AI writes the script, scene by scene, with its cast."
            bullets={[
              "Scenes with narration, timing and stock keywords",
              "Character sheet keeps names and tone consistent",
              "Edit everything before anything is rendered",
            ]}
            cta="Write a script"
            badge="Beta"
            featured
          />
        </div>
      </main>
    </div>
  );
}
