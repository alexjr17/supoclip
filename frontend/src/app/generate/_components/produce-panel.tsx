"use client";

import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { AlertCircle, CheckCircle, Clapperboard, Loader2 } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import {
  assembleVideo,
  type AssemblyProgress,
  type FootageResult,
  type NarrationResult,
  type ScriptScene,
} from "@/lib/scripts";
import { buildCaptions } from "@/remotion/build-captions";

interface ProducePanelProps {
  scenes: ScriptScene[];
  footage: FootageResult | null;
  narration: NarrationResult | null;
  /** Chosen stock clip per scene order, when the user overrode the default. */
  selection: Record<number, number>;
  showEmojis: boolean;
  /** Used as the saved video's name in the library. */
  title: string;
}

/**
 * The final step: stock plus voice plus captions into one video.
 *
 * Narration is required, not optional. Scene length comes from the voice, so
 * without it there is nothing to time the timeline against — the script's own
 * estimates run more than double the real length.
 */
export function ProducePanel({
  scenes,
  footage,
  narration,
  selection,
  showEmojis,
  title,
}: ProducePanelProps) {
  const [isAssembling, setIsAssembling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedTaskId, setSavedTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState<AssemblyProgress | null>(null);

  const canAssemble = Boolean(narration && narration.scenes.some((s) => s.duration > 0));

  const handleAssemble = async () => {
    if (!narration) return;
    setIsAssembling(true);
    setError(null);

    try {
      const footageByOrder = new Map(
        (footage?.scenes ?? []).map((scene) => [scene.order, scene]),
      );

      const payload = narration.scenes
        .filter((scene) => scene.duration > 0)
        .map((scene) => {
          const sceneFootage = footageByOrder.get(scene.order);
          const chosenId = selection[scene.order] ?? sceneFootage?.selected_id;
          const clip = sceneFootage?.candidates.find(
            (candidate) => candidate.id === chosenId,
          );

          return {
            order: scene.order,
            // An empty source renders on black rather than failing, so a scene
            // with no footage still appears with its narration and captions.
            videoSrc: clip?.download_url ?? clip?.preview_url ?? "",
            audioFilename: scene.audio_filename,
            durationInSeconds: scene.duration,
            // Pexels reports the clip's own length; a clip shorter than the
            // scene is looped rather than freezing on its last frame.
            sourceDurationInSeconds: clip?.duration,
            // Timings come from the synthesiser, so captions land on the word.
            captions: buildCaptions(scene.words, { showEmojis }),
          };
        });

      const result = await assembleVideo(payload, title, setProgress);
      setSavedTaskId(result.taskId);
    } catch (assembleError) {
      setError(assembleError instanceof Error ? assembleError.message : "Assembly failed");
    } finally {
      setIsAssembling(false);
    }
  };

  const scenesWithoutFootage = narration
    ? narration.scenes.filter((scene) => {
        if (scene.duration <= 0) return false;
        const sceneFootage = footage?.scenes.find((item) => item.order === scene.order);
        const chosenId = selection[scene.order] ?? sceneFootage?.selected_id;
        return !chosenId;
      }).length
    : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
          <Clapperboard className="h-4 w-4" />
          <span>Produce the video</span>
        </CardTitle>
        <CardDescription>
          Lays every scene end to end with its footage, voice-over and captions, and renders the
          result. Emoji come out in colour.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3">
        {!canAssemble && (
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            <AlertDescription className="text-sm text-amber-800">
              Narrate the script first. Scene length comes from the voice, so there is nothing to
              time the video against until then.
            </AlertDescription>
          </Alert>
        )}

        {canAssemble && scenesWithoutFootage > 0 && (
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            <AlertDescription className="text-sm text-amber-800">
              {scenesWithoutFootage} scene{scenesWithoutFootage === 1 ? "" : "s"} have no footage
              chosen and will render on black, with their narration and captions.
            </AlertDescription>
          </Alert>
        )}

        <Button
          onClick={handleAssemble}
          disabled={!canAssemble || isAssembling}
          className="h-11 w-full"
        >
          {isAssembling ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{progress?.message ?? "Starting..."}</span>
            </>
          ) : (
            <>
              <Clapperboard className="h-4 w-4" />
              <span>Assemble the video</span>
            </>
          )}
        </Button>

        {isAssembling && (
          <div className="space-y-1">
            <Progress value={Math.round((progress?.progress ?? 0) * 100)} />
            <p className="text-xs text-gray-500">
              {/* Remotion sits at 0 while it pulls the stock clips, which is the
                  slow part — the message says what is happening meanwhile. */}
              {progress?.status === "saving"
                ? "Almost there"
                : `${Math.round((progress?.progress ?? 0) * 100)}% · you can leave this page, the render continues`}
            </p>
          </div>
        )}

        {error && (
          <Alert className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        {savedTaskId && (
          <Alert className="border-green-200 bg-green-50">
            <CheckCircle className="h-4 w-4 text-green-500" />
            <AlertDescription className="text-sm text-green-700">
              Saved to your library — open{" "}
              <Link href={`/tasks/${savedTaskId}`} className="font-medium underline">
                the video
              </Link>{" "}
              to schedule or publish it to YouTube and TikTok.
            </AlertDescription>
          </Alert>
        )}

        <p className="text-xs text-gray-500">
          The render runs in the background and downloads each scene&apos;s stock clip first, so
          expect several minutes for {scenes.length} scene{scenes.length === 1 ? "" : "s"}. It
          finishes and saves even if you navigate away.
        </p>
      </CardContent>
    </Card>
  );
}
