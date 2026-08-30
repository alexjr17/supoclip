"use client";

import { useCallback, useEffect, useState } from "react";

import { track } from "@/lib/datafast";
import type { CustomFontFace } from "@/components/custom-font-faces";

export interface FontChoice extends CustomFontFace {
  name: string;
  display_name: string;
}

interface UserPreferences {
  fontFamily: string;
  fontSize: number;
  fontColor: string;
  notifyOnCompletion: boolean;
}

export const DEFAULT_FONT_FAMILY = "TikTokSans-Regular";

/**
 * Owns the caption defaults (font family/size/colour) and the completion-email
 * toggle: the four values persisted together by PATCH /api/preferences.
 *
 * `userId` is null until Better Auth resolves the session. Passing it in keeps
 * the loading flag honest — an anonymous visitor resolves to "not fetching"
 * instead of being stuck behind a skeleton forever.
 */
export function useClipDefaults(userId: string | null, sessionPending: boolean) {
  const [fonts, setFonts] = useState<FontChoice[]>([]);
  const [fontFamily, setFontFamily] = useState(DEFAULT_FONT_FAMILY);
  const [fontSize, setFontSize] = useState(24);
  const [fontColor, setFontColor] = useState("#FFFFFF");
  const [completionEmails, setCompletionEmails] = useState(true);

  const [isFetching, setIsFetching] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const loadFonts = async () => {
      try {
        const response = await fetch("/api/fonts", { cache: "no-store" });
        if (response.ok) {
          const data = await response.json();
          setFonts(data.fonts || []);
        }
      } catch (fontError) {
        console.error("Failed to load fonts:", fontError);
      }
    };

    void loadFonts();
  }, []);

  useEffect(() => {
    // Wait for Better Auth before deciding anything about the session.
    if (sessionPending) return;

    // Anonymous visitor: nothing to load, and the page must be allowed to
    // render its sign-in prompt rather than an endless skeleton.
    if (!userId) {
      setIsFetching(false);
      return;
    }

    const loadPreferences = async () => {
      setIsFetching(true);
      try {
        const response = await fetch("/api/preferences");
        if (response.ok) {
          const data: UserPreferences = await response.json();
          setFontFamily(data.fontFamily);
          setFontSize(data.fontSize);
          setFontColor(data.fontColor);
          setCompletionEmails(data.notifyOnCompletion ?? true);
        }
      } catch (preferencesError) {
        console.error("Failed to load preferences:", preferencesError);
      } finally {
        setIsFetching(false);
      }
    };

    void loadPreferences();
  }, [userId, sessionPending]);

  const save = useCallback(async () => {
    setIsSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const response = await fetch("/api/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fontFamily,
          fontSize,
          fontColor,
          notifyOnCompletion: completionEmails,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to save preferences");
      }

      track("preferences_saved");
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (saveError) {
      console.error("Error saving preferences:", saveError);
      setError(saveError instanceof Error ? saveError.message : "Failed to save preferences");
    } finally {
      setIsSaving(false);
    }
  }, [fontFamily, fontSize, fontColor, completionEmails]);

  return {
    fonts,
    fontFamily,
    setFontFamily,
    fontSize,
    setFontSize,
    fontColor,
    setFontColor,
    completionEmails,
    setCompletionEmails,
    isFetching,
    isSaving,
    error,
    success,
    save,
  };
}
