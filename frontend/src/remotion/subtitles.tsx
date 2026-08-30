"use client";

import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import type { CaptionWord, SubtitleStyle } from "./types";

// How many words are on screen at once. Matches the burned-in captions, which
// show a short rolling window rather than a full sentence.
const WINDOW_SIZE = 5;

interface SubtitlesProps {
  captions: CaptionWord[];
  style: SubtitleStyle;
}

/**
 * Word-synced captions, rendered by the browser.
 *
 * The reason this exists rather than reusing the burned-in ASS path: libass
 * cannot render colour emoji. Colour emoji fonts (NotoColorEmoji) are CBDT
 * bitmap fonts that only load at fixed strike sizes, so the ffmpeg pipeline
 * falls back to the monochrome "Noto Emoji" face and every emoji comes out
 * grey. A browser renders the same characters in colour with no special
 * handling at all.
 */
export function Subtitles({ captions, style }: SubtitlesProps) {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const timeMs = (frame / fps) * 1000;

  if (captions.length === 0) return null;

  const activeIndex = captions.findIndex(
    (word) => timeMs >= word.startMs && timeMs < word.endMs,
  );

  // Between words, keep showing the window around the last word that played so
  // captions do not flicker out during pauses.
  const anchorIndex =
    activeIndex >= 0
      ? activeIndex
      : captions.reduce(
          (last, word, index) => (timeMs >= word.endMs ? index : last),
          -1,
        );

  if (anchorIndex < 0) return null;

  const windowStart = Math.max(0, anchorIndex - Math.floor(WINDOW_SIZE / 2));
  const visible = captions.slice(windowStart, windowStart + WINDOW_SIZE);

  const outline = style.borderWidth
    ? `${style.borderWidth}px ${style.borderColor}`
    : undefined;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: height * style.positionY,
        transform: "translateY(-50%)",
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        gap: `0 ${Math.round(style.fontSize * 0.28)}px`,
        padding: `0 ${Math.round(style.fontSize * 0.8)}px`,
        textAlign: "center",
      }}
    >
      {visible.map((word, index) => {
        const absoluteIndex = windowStart + index;
        const isActive = absoluteIndex === activeIndex;

        return (
          <WordChip
            key={`${absoluteIndex}-${word.startMs}`}
            word={word}
            isActive={isActive}
            style={style}
            outline={outline}
            fps={fps}
            frame={frame}
          />
        );
      })}
    </div>
  );
}

interface WordChipProps {
  word: CaptionWord;
  isActive: boolean;
  style: SubtitleStyle;
  outline?: string;
  fps: number;
  frame: number;
}

function WordChip({ word, isActive, style, outline, fps, frame }: WordChipProps) {
  const highlight = isActive && style.animation !== "none";

  // "pop" scales the active word in with a spring keyed to when it starts, so
  // the animation lands on the word rather than on the frame it happens to be.
  const startFrame = Math.round((word.startMs / 1000) * fps);
  const popScale =
    style.animation === "pop" && isActive
      ? spring({
          frame: frame - startFrame,
          fps,
          config: { damping: 12, stiffness: 200, mass: 0.4 },
          from: 0.82,
          to: 1,
        })
      : 1;

  // "karaoke" leaves already-spoken words dimmed instead of highlighting one.
  const opacity =
    style.animation === "karaoke" && !isActive
      ? interpolate(1, [0, 1], [0.55, 0.55])
      : 1;

  return (
    <span
      style={{
        display: "inline-block",
        transform: `scale(${popScale})`,
        opacity,
        color: highlight ? style.highlightColor : style.fontColor,
        fontFamily: `'${style.fontFamily}', system-ui, -apple-system, sans-serif`,
        fontSize: style.fontSize,
        fontWeight: 800,
        lineHeight: 1.25,
        letterSpacing: "-0.01em",
        WebkitTextStroke: outline,
        paintOrder: "stroke fill",
        backgroundColor:
          style.bgOpacity > 0 ? `rgba(0,0,0,${style.bgOpacity})` : undefined,
        padding: style.bgOpacity > 0 ? "0.05em 0.2em" : undefined,
        borderRadius: style.bgOpacity > 0 ? "0.12em" : undefined,
      }}
    >
      {word.text}
      {word.emoji ? (
        // No stroke on the emoji: an outline around a colour glyph reads as a
        // smudge, and the emoji already separates itself from the video.
        <span style={{ WebkitTextStroke: "0", marginLeft: "0.18em" }}>
          {word.emoji}
        </span>
      ) : null}
    </span>
  );
}
