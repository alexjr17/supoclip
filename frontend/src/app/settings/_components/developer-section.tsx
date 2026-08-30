"use client";

import Link from "next/link";
import { ChevronRight, KeyRound, Terminal } from "lucide-react";

import { SettingsSection } from "./settings-section";

export function DeveloperSection() {
  return (
    <SettingsSection
      id="developer"
      icon={<Terminal className="h-4 w-4" />}
      title="Developer"
      description="Programmatic access for tools like the SupoClip MCP server."
    >
      <Link href="/settings/api-keys" className="block">
        <div className="flex items-center justify-between rounded-lg border p-4 transition-colors hover:bg-gray-50">
          <div className="flex items-center gap-3">
            <KeyRound className="h-5 w-5 text-black" />
            <div>
              <p className="text-sm font-medium text-black">API keys</p>
              <p className="text-xs text-gray-500">Create and manage API keys</p>
            </div>
          </div>
          <ChevronRight className="h-4 w-4 text-gray-400" />
        </div>
      </Link>
    </SettingsSection>
  );
}


