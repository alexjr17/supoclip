"use client";

import { useCallback, useMemo, useReducer } from "react";

import { MIN_SEGMENT_SECONDS, segmentsDuration, type EdlSegment } from "@/lib/edl";

interface EditorState {
  segments: EdlSegment[];
  selected: number;
  past: EdlSegment[][];
  future: EdlSegment[][];
  /**
   * Snapshot taken when a drag starts.
   *
   * A drag fires dozens of "preview" updates. Without this, each one would push
   * a history entry and undo would rewind one pixel at a time. Holding the
   * pre-drag state means the whole gesture collapses into a single undo step.
   */
  pendingBase: EdlSegment[] | null;
}

type EditorAction =
  | { type: "init"; segments: EdlSegment[] }
  | { type: "select"; index: number }
  | { type: "preview"; segments: EdlSegment[] }
  | { type: "commit"; segments: EdlSegment[]; select?: number }
  | { type: "undo" }
  | { type: "redo" };

const EMPTY: EditorState = {
  segments: [],
  selected: 0,
  past: [],
  future: [],
  pendingBase: null,
};

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "init":
      return { segments: action.segments, selected: 0, past: [], future: [], pendingBase: null };

    case "select":
      return { ...state, selected: action.index };

    case "preview":
      // Live feedback only: history is untouched until the gesture commits.
      return {
        ...state,
        segments: action.segments,
        pendingBase: state.pendingBase ?? state.segments,
      };

    case "commit": {
      const base = state.pendingBase ?? state.segments;
      return {
        ...state,
        segments: action.segments,
        selected: Math.min(action.select ?? state.selected, action.segments.length - 1),
        past: [...state.past, base],
        future: [],
        pendingBase: null,
      };
    }

    case "undo": {
      if (state.past.length === 0) return state;
      const previous = state.past[state.past.length - 1];
      return {
        ...state,
        segments: previous,
        selected: Math.min(state.selected, previous.length - 1),
        past: state.past.slice(0, -1),
        future: [state.segments, ...state.future],
        pendingBase: null,
      };
    }

    case "redo": {
      if (state.future.length === 0) return state;
      const next = state.future[0];
      return {
        ...state,
        segments: next,
        selected: Math.min(state.selected, next.length - 1),
        past: [...state.past, state.segments],
        future: state.future.slice(1),
        pendingBase: null,
      };
    }

    default:
      return state;
  }
}

/** Clamp a segment so it stays valid and inside the master video. */
function clampSegment(segment: EdlSegment, sourceDuration: number | null): EdlSegment {
  const start = Math.max(0, segment.start);
  const upperBound = sourceDuration ?? Number.POSITIVE_INFINITY;
  const end = Math.min(Math.max(start + MIN_SEGMENT_SECONDS, segment.end), upperBound);
  return { start: Math.min(start, end - MIN_SEGMENT_SECONDS), end };
}

export function useEdlEditor(sourceDuration: number | null) {
  const [state, dispatch] = useReducer(editorReducer, EMPTY);

  const load = useCallback((segments: EdlSegment[]) => {
    dispatch({ type: "init", segments });
  }, []);

  const select = useCallback((index: number) => {
    dispatch({ type: "select", index });
  }, []);

  const editSegment = useCallback(
    (index: number, next: EdlSegment, { preview = false } = {}) => {
      const apply = (segments: EdlSegment[]) =>
        segments.map((segment, i) => (i === index ? clampSegment(next, sourceDuration) : segment));

      dispatch(
        preview
          ? { type: "preview", segments: apply(state.segments) }
          : { type: "commit", segments: apply(state.segments), select: index },
      );
    },
    [state.segments, sourceDuration],
  );

  const splitAt = useCallback(
    (index: number, time: number) => {
      const segment = state.segments[index];
      if (!segment) return;
      if (
        time - segment.start < MIN_SEGMENT_SECONDS ||
        segment.end - time < MIN_SEGMENT_SECONDS
      ) {
        return;
      }

      const segments = [
        ...state.segments.slice(0, index),
        { start: segment.start, end: time },
        { start: time, end: segment.end },
        ...state.segments.slice(index + 1),
      ];
      dispatch({ type: "commit", segments, select: index + 1 });
    },
    [state.segments],
  );

  const removeSegment = useCallback(
    (index: number) => {
      if (state.segments.length <= 1) return; // An EDL needs at least one segment.
      const segments = state.segments.filter((_, i) => i !== index);
      dispatch({ type: "commit", segments, select: Math.max(0, index - 1) });
    },
    [state.segments],
  );

  const moveSegment = useCallback(
    (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target < 0 || target >= state.segments.length) return;
      const segments = [...state.segments];
      [segments[index], segments[target]] = [segments[target], segments[index]];
      dispatch({ type: "commit", segments, select: target });
    },
    [state.segments],
  );

  const duration = useMemo(() => segmentsDuration(state.segments), [state.segments]);

  return {
    segments: state.segments,
    selected: state.selected,
    duration,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
    load,
    select,
    editSegment,
    splitAt,
    removeSegment,
    moveSegment,
    undo: () => dispatch({ type: "undo" }),
    redo: () => dispatch({ type: "redo" }),
  };
}
