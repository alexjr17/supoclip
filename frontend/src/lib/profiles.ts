export const ACTIVE_PROFILE_COOKIE = "supoclip_active_profile";

export interface ConnectedAccountSummary {
  connected: boolean;
  title?: string;
  handle?: string;
  channel_id?: string;
  display_name?: string;
  avatar_url?: string;
  open_id?: string;
  source?: string;
}

export interface Profile {
  id: string;
  name: string;
  is_default: boolean;
  accounts: {
    youtube: ConnectedAccountSummary;
    tiktok: ConnectedAccountSummary;
  };
}

export interface ProfilesResponse {
  profiles: Profile[];
  active_profile_id: string;
}

export function getActiveProfileId(): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${ACTIVE_PROFILE_COOKIE}=`;
  const match = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

export function setActiveProfileId(profileId: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${ACTIVE_PROFILE_COOKIE}=${encodeURIComponent(
    profileId,
  )}; path=/; max-age=31536000; samesite=lax`;
}

export async function fetchProfiles(): Promise<ProfilesResponse> {
  const response = await fetch("/api/profiles", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load publishing channels");
  }
  return response.json();
}

export async function createProfile(name: string): Promise<Profile> {
  const response = await fetch("/api/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || "Failed to create channel");
  }
  const data = await response.json();
  return data.profile;
}

export async function renameProfile(
  profileId: string,
  name: string,
): Promise<Profile> {
  const response = await fetch(`/api/profiles/${profileId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || "Failed to rename channel");
  }
  const data = await response.json();
  return data.profile;
}

export async function deleteProfile(profileId: string): Promise<void> {
  const response = await fetch(`/api/profiles/${profileId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || "Failed to delete channel");
  }
}

export async function disconnectAccount(
  profileId: string,
  platform: "youtube" | "tiktok",
): Promise<void> {
  const response = await fetch(
    `/api/profiles/${profileId}/accounts/${platform}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || "Failed to disconnect account");
  }
}
