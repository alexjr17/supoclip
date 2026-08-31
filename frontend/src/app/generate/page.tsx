"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Clock, Film, Sparkles } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/lib/auth-client";
import {
  fetchStockStatus,
  generateScript,
  totalDuration,
  type FootageResult,
  type NarrationResult,
  type ScriptScene,
  type VideoScript,
} from "@/lib/scripts";

import { CharacterSheet } from "./_components/character-sheet";
import { SceneCard } from "./_components/scene-card";
import { FootagePicker } from "./_components/footage-picker";
import { NarrationPanel } from "./_components/narration-panel";
import { ProducePanel } from "./_components/produce-panel";
import { ScriptBriefForm, type ScriptBrief } from "./_components/script-brief-form";

const DEFAULT_BRIEF: ScriptBrief = {
  idea: "",
  target_duration_seconds: 45,
  tone: "informative",
  language: "English",
  with_characters: false,
};

export default function GeneratePage() {
  const { data: session, isPending } = useSession();

  const [brief, setBrief] = useState<ScriptBrief>(DEFAULT_BRIEF);
  const [script, setScript] = useState<VideoScript | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stockConfigured, setStockConfigured] = useState(false);
  const [footage, setFootage] = useState<FootageResult | null>(null);
  const [footageSelection, setFootageSelection] = useState<Record<number, number>>({});
  const [narration, setNarration] = useState<NarrationResult | null>(null);

  useEffect(() => {
    void fetchStockStatus().then((status) => setStockConfigured(status.configured));
  }, []);

  const handleGenerate = async () => {
    setIsGenerating(true);
    setError(null);
    try {
      setScript(await generateScript(brief));
    } catch (generateError) {
      setError(
        generateError instanceof Error ? generateError.message : "Failed to generate the script",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  // Scene edits renumber the whole list so `order` always matches position.
  const updateScenes = (scenes: ScriptScene[]) => {
    if (!script) return;
    setScript({
      ...script,
      scenes: scenes.map((scene, index) => ({ ...scene, order: index + 1 })),
    });
  };

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
          <p className="mb-8 text-gray-600">You need to sign in to generate scripts</p>
          <Link href="/sign-in">
            <Button size="lg">Sign In</Button>
          </Link>
        </div>
      </div>
    );
  }

  const runtime = script ? totalDuration(script.scenes) : 0;

  return (
    <div className="min-h-screen bg-gray-50/50">
      <header className="sticky top-0 z-30 border-b bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <Link href="/">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
          </Link>
          {script && (
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <Clock className="h-4 w-4" />
              {/* Kept in one <span> so the changing text is that element's only
                  child: React then updates it via textContent instead of
                  reordering text nodes a page translator may have replaced. */}
              <span>
                {runtime}s · {script.scenes.length} scenes
              </span>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-6 px-4 py-10">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-black" />
            <h1 className="text-2xl font-bold text-black">Generate with AI</h1>
          </div>
          <p className="text-gray-600">
            Write the script first. Nothing is rendered until you are happy with it.
          </p>
        </div>

        <ScriptBriefForm
          brief={brief}
          onChange={setBrief}
          onSubmit={handleGenerate}
          isGenerating={isGenerating}
        />

        {error && (
          <Alert className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        {script && (
          <>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
                  <Film className="h-4 w-4" />
                  Script
                </CardTitle>
                <CardDescription>
                  Everything here is editable. Scene order and timing update as you change them.
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-5">
                <div className="space-y-2">
                  <Label className="text-xs font-medium text-gray-600">Title</Label>
                  <Input
                    value={script.title}
                    onChange={(event) => setScript({ ...script, title: event.target.value })}
                    className="h-9 text-sm"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-medium text-gray-600">
                    Hook <span className="font-normal text-gray-400">— the first line spoken</span>
                  </Label>
                  <Input
                    value={script.hook}
                    onChange={(event) => setScript({ ...script, hook: event.target.value })}
                    className="h-9 text-sm"
                  />
                </div>

                <div className="space-y-3">
                  {script.scenes.map((scene, index) => (
                    <SceneCard
                      key={`scene-${index}`}
                      scene={scene}
                      isFirst={index === 0}
                      isLast={index === script.scenes.length - 1}
                      onChange={(updated) =>
                        updateScenes(
                          script.scenes.map((existing, i) => (i === index ? updated : existing)),
                        )
                      }
                      onMove={(direction) => {
                        const target = index + direction;
                        if (target < 0 || target >= script.scenes.length) return;
                        const reordered = [...script.scenes];
                        [reordered[index], reordered[target]] = [
                          reordered[target],
                          reordered[index],
                        ];
                        updateScenes(reordered);
                      }}
                      onRemove={() =>
                        updateScenes(script.scenes.filter((_, i) => i !== index))
                      }
                    />
                  ))}
                </div>
              </CardContent>
            </Card>

            <CharacterSheet
              characters={script.characters}
              onChange={(characters) => setScript({ ...script, characters })}
            />

            <FootagePicker
              scenes={script.scenes}
              stockConfigured={stockConfigured}
              onResult={setFootage}
              onSelectionChange={setFootageSelection}
            />

            <NarrationPanel
              scenes={script.scenes}
              language={brief.language}
              result={narration}
              onNarrated={(result) => {
                setNarration(result);
                // The voice is the authority on scene length, so the script
                // adopts the measured durations.
                setScript((current) =>
                  current ? { ...current, scenes: result.retimed_scenes } : current,
                );
              }}
            />

            <ProducePanel
              scenes={script.scenes}
              footage={footage}
              narration={narration}
              selection={footageSelection}
              showEmojis
            />
          </>
        )}
      </main>
    </div>
  );
}
