"use client";

import { useCallback, useRef } from "react";

import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Scissors, Trash2 } from "lucide-react";
import { formatTimecode, snapToWords, type ClipEdl, type EdlSegment } from "@/lib/edl";

// Distinct hues so neighbouring segments stay tellable apart at a glance.
const SEGMENT_COLORS = [
  "oklch(76% .17 50)",
  "oklch(70% .12 200)",
  "oklch(72% .13 140)",
  "oklch(70% .14 300)",
  "oklch(74% .13 90)",
  "oklch(68% .13 250)",
];

interface EdlTimelineProps {
  edl: ClipEdl;
  segments: EdlSegment[];
  selected: number;
  onSelect: (index: number) => void;
  onEdit: (index: number, segment: EdlSegment, options?: { preview?: boolean }) => void;
  onSplit: (index: number, time: number) => void;
  onRemove: (index: number) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  disabled: boolean;
}

/**
 * The source timeline: where in the master video each segment comes from.
 *
 * Segments are drawn against the *source* duration, not the clip's own length,
 * which is what makes extending visible — the gaps either side of a block are
 * material still available to pull back in.
 */
export function EdlTimeline({
  edl,
  segments,
  selected,
  onSelect,
  onEdit,
  onSplit,
  onRemove,
  onMove,
  disabled,
}: EdlTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const scale = edl.source_duration ?? Math.max(1, ...segments.map((s) => s.end));

  const timeAt = useCallback(
    (clientX: number) => {
      const track = trackRef.current;
      if (!track) return 0;
      const rect = track.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      return ratio * scale;
    },
    [scale],
  );

  const dragEdge = useCallback(
    (index: number, edge: "start" | "end") =>
      (event: React.PointerEvent<HTMLButtonElement>) => {
        if (disabled) return;
        event.preventDefault();
        event.stopPropagation();
        const pointerId = event.pointerId;
        (event.target as HTMLElement).setPointerCapture?.(pointerId);

        const move = (moveEvent: PointerEvent) => {
          const raw = timeAt(moveEvent.clientX);
          const snapped = snapToWords(raw, edl.words, edl.snap_window_seconds, edge);
          const current = segments[index];
          onEdit(
            index,
            edge === "start"
              ? { start: snapped, end: current.end }
              : { start: current.start, end: snapped },
            { preview: true },
          );
        };

        const up = (upEvent: PointerEvent) => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          const raw = timeAt(upEvent.clientX);
          const snapped = snapToWords(raw, edl.words, edl.snap_window_seconds, edge);
          const current = segments[index];
          // Commit once, so the whole drag is a single undo step.
          onEdit(
            index,
            edge === "start"
              ? { start: snapped, end: current.end }
              : { start: current.start, end: snapped },
          );
        };

        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
      },
    [disabled, edl.words, edl.snap_window_seconds, onEdit, segments, timeAt],
  );

  return (
    <div className="space-y-4">
      <div
        ref={trackRef}
        className="relative h-16 w-full overflow-hidden rounded-lg border bg-gray-100"
      >
        {segments.map((segment, index) => {
          const left = (segment.start / scale) * 100;
          const width = ((segment.end - segment.start) / scale) * 100;
          const isSelected = index === selected;

          return (
            <div
              key={`${index}-${segment.start}`}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(index);
              }}
              className={`absolute top-2 flex h-12 cursor-pointer items-center justify-center rounded-md text-[10px] font-medium text-black/70 transition-shadow ${
                isSelected ? "ring-2 ring-stone-900 ring-offset-1" : ""
              }`}
              style={{
                left: `${left}%`,
                width: `${Math.max(width, 0.5)}%`,
                backgroundColor: SEGMENT_COLORS[index % SEGMENT_COLORS.length],
              }}
              title={`${formatTimecode(segment.start)} → ${formatTimecode(segment.end)}`}
            >
              <button
                type="button"
                aria-label={`Drag start of segment ${index + 1}`}
                onPointerDown={dragEdge(index, "start")}
                className="absolute left-0 h-full w-2 cursor-ew-resize rounded-l-md bg-black/25 hover:bg-black/45"
              />
              <span className="pointer-events-none truncate px-3">{index + 1}</span>
              <button
                type="button"
                aria-label={`Drag end of segment ${index + 1}`}
                onPointerDown={dragEdge(index, "end")}
                className="absolute right-0 h-full w-2 cursor-ew-resize rounded-r-md bg-black/25 hover:bg-black/45"
              />
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>0:00.0</span>
        <span>
          {edl.source_duration
            ? `source ${formatTimecode(edl.source_duration)}`
            : "source length unknown"}
        </span>
      </div>

      {segments[selected] && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-white p-3">
          <span className="text-sm font-medium text-black">
            Segment {selected + 1} · {formatTimecode(segments[selected].start)} →{" "}
            {formatTimecode(segments[selected].end)}
          </span>
          <div className="ml-auto flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2"
              disabled={disabled || selected === 0}
              onClick={() => onMove(selected, -1)}
              aria-label="Move segment earlier"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2"
              disabled={disabled || selected === segments.length - 1}
              onClick={() => onMove(selected, 1)}
              aria-label="Move segment later"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2"
              disabled={disabled}
              onClick={() => {
                const segment = segments[selected];
                onSplit(selected, (segment.start + segment.end) / 2);
              }}
              aria-label="Split segment in half"
            >
              <Scissors className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-red-600 hover:text-red-700"
              disabled={disabled || segments.length <= 1}
              onClick={() => onRemove(selected)}
              aria-label="Delete segment"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
