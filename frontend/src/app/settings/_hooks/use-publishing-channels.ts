"use client";

import { useCallback, useEffect, useState } from "react";

import {
  deleteProfile,
  disconnectAccount,
  fetchProfiles,
  renameProfile,
  type Profile,
} from "@/lib/profiles";

export type ChannelPlatform = "youtube" | "tiktok";

/**
 * Owns the publishing-channel list and the three mutations available on it.
 *
 * A single `busy` key (`"rename-<id>"`, `"delete-<id>"`, …) serialises the
 * mutations: every row reads it to disable its own buttons and to show a
 * spinner on exactly the control that was clicked.
 */
export function usePublishingChannels() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await fetchProfiles();
    setProfiles(data.profiles);
    setActiveProfileId(data.active_profile_id);
  }, []);

  useEffect(() => {
    refresh().catch((loadError) => {
      console.error("Failed to load publishing channels:", loadError);
    });
  }, [refresh]);

  /** Resolves to true only when the mutation and the refresh both succeeded. */
  const runMutation = useCallback(
    async (key: string, action: () => Promise<unknown>, fallbackMessage: string) => {
      if (busy) return false;
      setBusy(key);
      setError(null);
      try {
        await action();
        await refresh();
        return true;
      } catch (mutationError) {
        setError(mutationError instanceof Error ? mutationError.message : fallbackMessage);
        return false;
      } finally {
        setBusy(null);
      }
    },
    [busy, refresh],
  );

  const rename = useCallback(
    (profileId: string, name: string) =>
      runMutation(
        `rename-${profileId}`,
        () => renameProfile(profileId, name),
        "Failed to rename channel",
      ),
    [runMutation],
  );

  const disconnect = useCallback(
    (profileId: string, platform: ChannelPlatform) =>
      runMutation(
        `disconnect-${profileId}-${platform}`,
        () => disconnectAccount(profileId, platform),
        "Failed to disconnect account",
      ),
    [runMutation],
  );

  const remove = useCallback(
    (profileId: string) =>
      runMutation(`delete-${profileId}`, () => deleteProfile(profileId), "Failed to delete channel"),
    [runMutation],
  );

  const activeProfileName =
    profiles.find((profile) => profile.id === activeProfileId)?.name ?? null;

  return {
    profiles,
    activeProfileId,
    activeProfileName,
    busy,
    error,
    rename,
    disconnect,
    remove,
  };
}
