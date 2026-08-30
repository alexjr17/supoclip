"use client";

import { useCallback, useEffect, useState } from "react";

interface YoutubeChannel {
  title?: string | null;
  handle?: string | null;
}

interface TiktokUser {
  display_name?: string | null;
}

export interface PlatformConnection {
  configured: boolean;
  /** Human-readable name of the connected account, or null when disconnected. */
  accountName: string | null;
}

const DISCONNECTED: PlatformConnection = { configured: false, accountName: null };

/**
 * Owns the OAuth connection state for YouTube and TikTok.
 *
 * Both platforms are reported by the same GET /api/publish/status call and
 * both connect by redirecting to an auth URL, so they share one hook rather
 * than duplicating the fetch/redirect/error dance twice.
 */
export function usePlatformConnections() {
  const [youtube, setYoutube] = useState<PlatformConnection>(DISCONNECTED);
  const [tiktok, setTiktok] = useState<PlatformConnection>(DISCONNECTED);
  const [connecting, setConnecting] = useState<"youtube" | "tiktok" | null>(null);
  const [messages, setMessages] = useState<{ youtube: string | null; tiktok: string | null }>({
    youtube: null,
    tiktok: null,
  });

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const response = await fetch("/api/publish/status");
        if (!response.ok) return;

        const data = await response.json();
        const channel: YoutubeChannel | null = data.channel ?? null;
        const user: TiktokUser | null = data.tiktok_user ?? null;

        setYoutube({
          configured: data.youtube_configured ?? false,
          accountName: channel?.title ?? channel?.handle ?? null,
        });
        setTiktok({
          configured: data.tiktok_configured ?? false,
          accountName: user?.display_name ?? null,
        });
      } catch (statusError) {
        console.error("Failed to load publishing status:", statusError);
      }
    };

    void loadStatus();
  }, []);

  const connect = useCallback(async (platform: "youtube" | "tiktok") => {
    const notConfigured =
      platform === "youtube"
        ? "YouTube is not configured. Set YOUTUBE_CLIENT_ID first."
        : "TikTok is not configured. Set TIKTOK_CLIENT_KEY first.";

    setConnecting(platform);
    setMessages((current) => ({ ...current, [platform]: null }));

    try {
      const response = await fetch(`/api/publish/${platform}/auth-url`);
      const data = await response.json();
      if (!response.ok || !data.url) {
        throw new Error(data.detail || notConfigured);
      }
      // Leaving the page: keep the button in its "Redirecting…" state.
      window.location.href = data.url;
    } catch (connectError) {
      setMessages((current) => ({
        ...current,
        [platform]:
          connectError instanceof Error
            ? connectError.message
            : `Failed to connect ${platform === "youtube" ? "YouTube" : "TikTok"}`,
      }));
      setConnecting(null);
    }
  }, []);

  return { youtube, tiktok, connecting, messages, connect };
}
