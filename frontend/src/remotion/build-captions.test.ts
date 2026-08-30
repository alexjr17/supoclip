import { describe, expect, it } from "vitest";

import { buildCaptions, estimateCaptions, mapWordsToClipTime } from "./build-captions";

const WORDS = [
  { text: "one", start: 10.0, end: 10.4 },
  { text: "two", start: 10.5, end: 10.9 },
  { text: "three", start: 20.0, end: 20.4 },
  { text: "four", start: 20.5, end: 20.9 },
];

describe("mapWordsToClipTime", () => {
  it("rebases words onto the clip's own timeline", () => {
    const mapped = mapWordsToClipTime(WORDS, [{ start: 10.0, end: 11.0 }]);

    expect(mapped).toEqual([
      { text: "one", start: 0, end: expect.closeTo(0.4, 5) },
      { text: "two", start: expect.closeTo(0.5, 5), end: expect.closeTo(0.9, 5) },
    ]);
  });

  it("stacks later segments after the earlier ones", () => {
    // Two one-second windows far apart in the source play back to back, so the
    // second window's words start at 1.0 in clip time, not at 20.
    const mapped = mapWordsToClipTime(WORDS, [
      { start: 10.0, end: 11.0 },
      { start: 20.0, end: 21.0 },
    ]);

    expect(mapped.map((word) => word.text)).toEqual(["one", "two", "three", "four"]);
    expect(mapped[2].start).toBeCloseTo(1.0, 5);
    expect(mapped[3].start).toBeCloseTo(1.5, 5);
  });

  it("drops words that fall in the gaps between segments", () => {
    const mapped = mapWordsToClipTime(WORDS, [{ start: 20.0, end: 21.0 }]);

    expect(mapped.map((word) => word.text)).toEqual(["three", "four"]);
  });

  it("keeps a word straddling a boundary on exactly one side", () => {
    const straddling = [{ text: "edge", start: 10.8, end: 11.2 }];
    // The midpoint (11.0) is outside the first segment and inside the second,
    // so the word appears once, in the second.
    const mapped = mapWordsToClipTime(straddling, [
      { start: 10.0, end: 11.0 },
      { start: 11.0, end: 12.0 },
    ]);

    expect(mapped).toHaveLength(1);
    expect(mapped[0].start).toBeCloseTo(1.0, 5);
  });

  it("respects the segment order rather than the source order", () => {
    // Reordering segments is a valid edit, so a later part of the source can
    // legitimately play first.
    const mapped = mapWordsToClipTime(WORDS, [
      { start: 20.0, end: 21.0 },
      { start: 10.0, end: 11.0 },
    ]);

    expect(mapped.map((word) => word.text)).toEqual(["three", "four", "one", "two"]);
  });

  it("returns nothing without segments", () => {
    expect(mapWordsToClipTime(WORDS, [])).toEqual([]);
  });
});

describe("buildCaptions", () => {
  it("converts seconds to milliseconds", () => {
    const captions = buildCaptions([{ text: "hi", start: 1.234, end: 1.5 }]);

    expect(captions[0]).toMatchObject({ text: "hi", startMs: 1234, endMs: 1500 });
  });

  it("attaches no emoji when they are switched off", () => {
    const captions = buildCaptions(
      [{ text: "money", start: 0, end: 1 }],
      { showEmojis: false },
    );

    expect(captions[0].emoji).toBeUndefined();
  });
});

describe("estimateCaptions", () => {
  it("spreads words evenly across the clip", () => {
    const captions = estimateCaptions("a b c d", 4, { showEmojis: false });

    expect(captions).toHaveLength(4);
    expect(captions[0].startMs).toBe(0);
    expect(captions[3].endMs).toBe(4000);
  });

  it("returns nothing for empty text or a zero-length clip", () => {
    expect(estimateCaptions("", 10)).toEqual([]);
    expect(estimateCaptions("hello", 0)).toEqual([]);
  });
});
