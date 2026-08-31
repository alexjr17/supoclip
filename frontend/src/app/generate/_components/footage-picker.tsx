"use client";

import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertCircle, Film, Loader2, Search } from "lucide-react";

import { findFootage, type FootageResult, type ScriptScene } from "@/lib/scripts";

interface FootagePickerProps {
  scenes: ScriptScene[];
  /** False when the deployment has no PEXELS_API_KEY. */
  stockConfigured: boolean;
}

/**
 * Candidate stock clips for each scene.
 *
 * A short list per scene rather than one automatic pick: stock search is
 * imprecise, and which near-miss actually works is the author's judgement.
 */
export function FootagePicker({ scenes, stockConfigured }: FootagePickerProps) {
  const [result, setResult] = useState<FootageResult | null>(null);
  const [selection, setSelection] = useState<Record<number, number>>({});
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    setIsSearching(true);
    setError(null);
    try {
      const found = await findFootage(scenes);
      setResult(found);
      setSelection(
        Object.fromEntries(
          found.scenes
            .filter((scene) => scene.selected_id !== null)
            .map((scene) => [scene.order, scene.selected_id as number]),
        ),
      );
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Search failed");
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
          <Film className="h-4 w-4" />
          <span>Scene footage</span>
        </CardTitle>
        <CardDescription>
          Finds stock clips matching each scene&apos;s keywords. Pick the shot you want before
          anything is rendered.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {!stockConfigured && (
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            <AlertDescription className="text-sm text-amber-800">
              Stock search needs <code className="font-mono">PEXELS_API_KEY</code> in your
              environment. Add one and restart the backend to enable it.
            </AlertDescription>
          </Alert>
        )}

        <Button
          onClick={handleSearch}
          disabled={isSearching || !stockConfigured || scenes.length === 0}
          className="w-full"
        >
          {isSearching ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Searching {scenes.length} scenes...</span>
            </>
          ) : (
            <>
              <Search className="h-4 w-4" />
              <span>Find footage for every scene</span>
            </>
          )}
        </Button>

        {error && (
          <Alert className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        {result?.scenes_without_footage.length ? (
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            <AlertDescription className="text-sm text-amber-800">
              No footage found for scene
              {result.scenes_without_footage.length === 1 ? " " : "s "}
              {result.scenes_without_footage.join(", ")}. Try more concrete, filmable keywords —
              &quot;woman typing laptop&quot; works better than &quot;productivity&quot;.
            </AlertDescription>
          </Alert>
        ) : null}

        {result?.scenes.map((scene) => (
          <div key={scene.order} className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                Scene {scene.order}
              </Badge>
              <span className="truncate text-xs text-gray-500">
                {scene.keywords.join(", ") || "no keywords"}
              </span>
            </div>

            {scene.candidates.length === 0 ? (
              <p className="text-sm text-gray-500">No matches.</p>
            ) : (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {scene.candidates.map((candidate) => {
                  const isSelected = selection[scene.order] === candidate.id;
                  return (
                    <button
                      key={candidate.id}
                      type="button"
                      onClick={() =>
                        setSelection((current) => ({
                          ...current,
                          [scene.order]: candidate.id,
                        }))
                      }
                      className={`overflow-hidden rounded-md border-2 transition-colors ${
                        isSelected ? "border-stone-900" : "border-transparent hover:border-gray-300"
                      }`}
                    >
                      {candidate.thumbnail ? (
                        // eslint-disable-next-line @next/next/no-img-element -- remote stock host, not in next.config images
                        <img
                          src={candidate.thumbnail}
                          alt={`Option for scene ${scene.order}`}
                          className="aspect-[9/16] w-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="aspect-[9/16] w-full bg-gray-100" />
                      )}
                      <span className="block truncate px-1 py-0.5 text-[10px] text-gray-500">
                        {candidate.duration}s · {candidate.author ?? "unknown"}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ))}

        {result && (
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            <AlertDescription className="text-sm text-amber-800">
              Assembly is not wired up yet: choosing shots does not produce a video. Voice-over and
              rendering come next.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
