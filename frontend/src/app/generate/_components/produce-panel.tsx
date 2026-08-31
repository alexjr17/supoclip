"use client";

import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertCircle, Clapperboard, Download, Loader2 } from "lucide-react";

import {
  assembleVideo,
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
}: ProducePanelProps) {
  const [isAssembling, setIsAssembling] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
            // Timings come from the synthesiser, so captions land on the word.
            captions: buildCaptions(scene.words, { showEmojis }),
          };
        });

      const blob = await assembleVideo(payload);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "generated.mp4";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
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
              <span>Rendering the video...</span>
            </>
          ) : (
            <>
              <Download className="h-4 w-4" />
              <span>Assemble and download</span>
            </>
          )}
        </Button>

        {error && (
          <Alert className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        <p className="text-xs text-gray-500">
          Rendering happens on the server and takes about as long as the video itself. Scenes: {scenes.length}.
        </p>
      </CardContent>
    </Card>
  );
}
