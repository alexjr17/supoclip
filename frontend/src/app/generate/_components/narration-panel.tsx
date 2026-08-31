"use client";

import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AlertCircle, AudioLines, Loader2 } from "lucide-react";

import {
  fetchVoices,
  narrateScript,
  type NarrationResult,
  type ScriptScene,
  type Voice,
} from "@/lib/scripts";

interface NarrationPanelProps {
  scenes: ScriptScene[];
  language: string;
  result: NarrationResult | null;
  onNarrated: (result: NarrationResult) => void;
}

/**
 * Voice-over for the script.
 *
 * The measured duration is shown next to the script's estimate on purpose: the
 * estimates come from a word count and run more than double the real length, and
 * seeing that is what explains why the timeline changes after narrating.
 */
export function NarrationPanel({
  scenes,
  language,
  result,
  onNarrated,
}: NarrationPanelProps) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState<string>("");
  const [isNarrating, setIsNarrating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchVoices(language).then((loaded) => {
      if (cancelled) return;
      setVoices(loaded);
      // Reset rather than keep a voice from another language.
      setVoice("");
    });
    return () => {
      cancelled = true;
    };
  }, [language]);

  const handleNarrate = async () => {
    setIsNarrating(true);
    setError(null);
    try {
      onNarrated(
        await narrateScript(scenes, { language, voice: voice || null }),
      );
    } catch (narrateError) {
      setError(narrateError instanceof Error ? narrateError.message : "Narration failed");
    } finally {
      setIsNarrating(false);
    }
  };

  const failed = result?.scenes.filter((scene) => scene.error) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
          <AudioLines className="h-4 w-4" />
          <span>Voice-over</span>
        </CardTitle>
        <CardDescription>
          Narrates every scene and re-times the script from how long the voice actually takes.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Voice</Label>
          <Select value={voice} onValueChange={setVoice} disabled={isNarrating}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={`Default ${language} voice`} />
            </SelectTrigger>
            <SelectContent>
              {voices.map((option) => (
                <SelectItem key={option.name} value={option.name}>
                  {option.name} · {option.gender}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={handleNarrate}
          disabled={isNarrating || scenes.length === 0}
          className="w-full"
        >
          {isNarrating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Narrating {scenes.length} scenes...</span>
            </>
          ) : (
            <>
              <AudioLines className="h-4 w-4" />
              <span>Narrate the script</span>
            </>
          )}
        </Button>

        {error && (
          <Alert className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        {result && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-black">
                Real runtime: {result.total_duration}s
              </span>
              <Badge variant="outline" className="text-[10px]">
                {result.scenes.length} scenes
              </Badge>
            </div>

            <div className="space-y-1">
              {result.scenes.map((scene) => (
                <div
                  key={scene.order}
                  className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs"
                >
                  <span className="font-medium text-black">Scene {scene.order}</span>
                  {scene.error ? (
                    <span className="text-red-600">{scene.error}</span>
                  ) : (
                    <>
                      <span className="text-gray-600">{scene.duration}s</span>
                      {scene.estimated_duration ? (
                        <span className="text-gray-400">
                          (estimated {scene.estimated_duration}s)
                        </span>
                      ) : null}
                      <span className="ml-auto text-gray-400">
                        {scene.words.length} words timed
                      </span>
                    </>
                  )}
                </div>
              ))}
            </div>

            {failed.length > 0 && (
              <Alert className="border-amber-200 bg-amber-50">
                <AlertCircle className="h-4 w-4 text-amber-500" />
                <AlertDescription className="text-sm text-amber-800">
                  {failed.length} scene{failed.length === 1 ? "" : "s"} could not be narrated and
                  keep their estimated length, so they stay in the timeline.
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
