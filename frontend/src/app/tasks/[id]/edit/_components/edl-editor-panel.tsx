"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Film, Loader2, Redo2, Undo2 } from "lucide-react";

import { fetchClipEdl, formatTimecode, rerenderClip, type ClipEdl } from "@/lib/edl";

import { EdlTimeline } from "./edl-timeline";
import { useEdlEditor } from "../_hooks/use-edl-editor";

interface EdlEditorPanelProps {
  taskId: string;
  clipId: string;
  /** Called after a successful re-render so the parent can refresh the clip. */
  onRendered: () => void;
}

/**
 * Non-destructive clip editing.
 *
 * The panel edits the clip's recipe (which source ranges it is cut from) and
 * re-renders from the master video. Trim/split here can therefore *extend* a
 * segment, and repeated edits never stack re-encoding loss — unlike the
 * trim/split controls that cut the finished mp4.
 */
export function EdlEditorPanel({ taskId, clipId, onRendered }: EdlEditorPanelProps) {
  const [edl, setEdl] = useState<ClipEdl | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRendering, setIsRendering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editor = useEdlEditor(edl?.source_duration ?? null);
  const { load } = editor;

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const loaded = await fetchClipEdl(taskId, clipId);
        if (cancelled) return;
        setEdl(loaded);
        load(loaded.segments);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load the timeline");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [taskId, clipId, load]);

  const handleRender = useCallback(async () => {
    if (editor.segments.length === 0) return;
    setIsRendering(true);
    setError(null);
    try {
      await rerenderClip(taskId, clipId, editor.segments);
      onRendered();
    } catch (renderError) {
      setError(renderError instanceof Error ? renderError.message : "Failed to re-render");
    } finally {
      setIsRendering(false);
    }
  }, [taskId, clipId, editor.segments, onRendered]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold text-black">Source timeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-9 w-1/3" />
        </CardContent>
      </Card>
    );
  }

  if (error && !edl) {
    return (
      <Alert className="border-red-200 bg-red-50">
        <AlertCircle className="h-4 w-4 text-red-500" />
        <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
      </Alert>
    );
  }

  if (!edl) return null;

  if (!edl.has_source_map) {
    return (
      <Alert className="border-amber-200 bg-amber-50">
        <AlertCircle className="h-4 w-4 text-amber-500" />
        <AlertDescription className="text-sm text-amber-800">
          This clip was generated before source tracking existed, so its original timeline is not
          recorded. Regenerate the task to edit it non-destructively; the trim and split controls
          below still work on the rendered file.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
          <Film className="h-4 w-4" />
          <span>Source timeline</span>
          <Badge variant="outline" className="text-[10px]">
            Non-destructive
          </Badge>
        </CardTitle>
        <CardDescription>
          Edits change which parts of the original video the clip uses, then re-render from the
          master — so segments can be extended again and quality never degrades.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <EdlTimeline
          edl={edl}
          segments={editor.segments}
          selected={editor.selected}
          onSelect={editor.select}
          onEdit={editor.editSegment}
          onSplit={editor.splitAt}
          onRemove={editor.removeSegment}
          onMove={editor.moveSegment}
          disabled={isRendering}
        />

        {error && (
          <Alert className="border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t pt-4">
          <Button
            size="sm"
            variant="outline"
            onClick={editor.undo}
            disabled={!editor.canUndo || isRendering}
          >
            <Undo2 className="h-4 w-4" />
            <span>Undo</span>
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={editor.redo}
            disabled={!editor.canRedo || isRendering}
          >
            <Redo2 className="h-4 w-4" />
            <span>Redo</span>
          </Button>

          <span className="ml-auto text-sm text-gray-600">
            {editor.segments.length} segment{editor.segments.length === 1 ? "" : "s"} ·{" "}
            {formatTimecode(editor.duration)}
          </span>

          <Button onClick={handleRender} disabled={isRendering || editor.segments.length === 0}>
            {isRendering ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Rendering...</span>
              </>
            ) : (
              <span>Apply and re-render</span>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
