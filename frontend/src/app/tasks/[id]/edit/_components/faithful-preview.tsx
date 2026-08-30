"use client";

import { useEffect, useMemo, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { ClipPreviewPlayer } from "@/components/clip-preview-player";
import { fetchClipEdl, type ClipEdl } from "@/lib/edl";
import {
  buildCaptions,
  estimateCaptions,
  mapWordsToClipTime,
} from "@/remotion/build-captions";

interface FaithfulPreviewProps {
  taskId: string;
  clipId: string;
  videoSrc: string;
  durationSeconds: number;
  clipText: string;
  showEmojis: boolean;
  hookTitle?: string | null;
  subtitleSize: number;
  /** 0-100 from the editor's slider, measured from the bottom of the frame. */
  subtitleYPercent: number;
  fontColor?: string | null;
  fontFamily?: string | null;
}

/**
 * The clip as it will actually look, drawn by Remotion.
 *
 * Word timings come from the EDL, projected into clip time, so captions land
 * where they really land rather than being spread evenly. When the clip has no
 * source map the timings are estimated and the panel says so.
 */
export function FaithfulPreview({
  taskId,
  clipId,
  videoSrc,
  durationSeconds,
  clipText,
  showEmojis,
  hookTitle,
  subtitleSize,
  subtitleYPercent,
  fontColor,
  fontFamily,
}: FaithfulPreviewProps) {
  const [edl, setEdl] = useState<ClipEdl | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setIsLoading(true);
      try {
        const loaded = await fetchClipEdl(taskId, clipId);
        if (!cancelled) setEdl(loaded);
      } catch {
        // A missing EDL is not an error here: the preview falls back to
        // estimated timings rather than refusing to render.
        if (!cancelled) setEdl(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [taskId, clipId]);

  const hasRealTimings = Boolean(edl?.words?.length && edl?.segments?.length);

  const captions = useMemo(() => {
    if (edl && hasRealTimings) {
      return buildCaptions(mapWordsToClipTime(edl.words, edl.segments), {
        showEmojis,
      });
    }
    return estimateCaptions(clipText, durationSeconds, { showEmojis });
  }, [edl, hasRealTimings, clipText, durationSeconds, showEmojis]);

  if (isLoading) {
    return <Skeleton className="aspect-[9/16] max-h-[520px] w-full rounded-xl" />;
  }

  return (
    <div className="space-y-3">
      <ClipPreviewPlayer
        videoSrc={videoSrc}
        durationSeconds={durationSeconds}
        captions={captions}
        hook={
          hookTitle ? { text: hookTitle, displayDurationSec: 4 } : null
        }
        style={{
          fontSize: subtitleSize,
          // The editor's slider is measured from the bottom; the composition
          // positions from the top.
          positionY: Math.min(0.95, Math.max(0.05, 1 - subtitleYPercent / 100)),
          ...(fontColor ? { fontColor } : {}),
          ...(fontFamily ? { fontFamily } : {}),
        }}
      />

      {!hasRealTimings && (
        <Alert className="border-amber-200 bg-amber-50">
          <AlertCircle className="h-4 w-4 text-amber-500" />
          <AlertDescription className="text-sm text-amber-800">
            Word timings are not available for this clip, so caption timing here is estimated from
            the transcript text. Emoji and styling are accurate.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
