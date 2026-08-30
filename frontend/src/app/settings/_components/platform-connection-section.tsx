"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { AlertCircle, CheckCircle } from "lucide-react";

import { ErrorAlert, SettingsSection } from "./settings-section";
import type { PlatformConnection } from "../_hooks/use-platform-connections";

interface PlatformConnectionSectionProps {
  id: string;
  platform: "youtube" | "tiktok";
  label: string;
  icon: ReactNode;
  description: string;
  /** Shown under the account name once connected. */
  connectedHint: string;
  /** Shown under "Not connected" to explain what connecting buys the user. */
  disconnectedHint: string;
  fallbackAccountName: string;
  connection: PlatformConnection;
  activeProfileName: string | null;
  isConnecting: boolean;
  message: string | null;
  onConnect: (platform: "youtube" | "tiktok") => void;
}

/**
 * One connect/reconnect card, shared by YouTube and TikTok.
 *
 * The two platforms differ only in their copy and icon, so they render through
 * the same component instead of the two near-identical 60-line blocks this
 * page used to carry.
 */
export function PlatformConnectionSection({
  id,
  platform,
  label,
  icon,
  description,
  connectedHint,
  disconnectedHint,
  fallbackAccountName,
  connection,
  activeProfileName,
  isConnecting,
  message,
  onConnect,
}: PlatformConnectionSectionProps) {
  return (
    <SettingsSection
      id={id}
      icon={icon}
      title={label}
      description={
        <>
          {description}
          {activeProfileName && (
            <span className="mt-1 block text-xs text-gray-500">
              Applies to active channel:{" "}
              <span className="font-medium text-black">{activeProfileName}</span>
            </span>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-4 rounded-lg border p-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          {connection.configured ? (
            <CheckCircle className="h-5 w-5 shrink-0 text-green-500" />
          ) : (
            <AlertCircle className="h-5 w-5 shrink-0 text-gray-400" />
          )}
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-black">
              {connection.configured
                ? `Connected: ${connection.accountName ?? fallbackAccountName}`
                : "Not connected"}
            </p>
            <p className="text-xs text-gray-500">
              {connection.configured ? connectedHint : disconnectedHint}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant={connection.configured ? "outline" : "default"}
          onClick={() => onConnect(platform)}
          disabled={isConnecting}
          className="shrink-0"
        >
          {isConnecting ? "Redirecting..." : connection.configured ? "Reconnect" : `Connect ${label.split(" ")[0]}`}
        </Button>
      </div>

      {message && <ErrorAlert>{message}</ErrorAlert>}
    </SettingsSection>
  );
}
