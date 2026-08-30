"use client";

import type { ReactNode } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertCircle, CheckCircle } from "lucide-react";

interface SettingsSectionProps {
  /** Anchor target for the sidebar navigation. */
  id: string;
  title: string;
  description: ReactNode;
  icon?: ReactNode;
  /** Rendered on the right of the header — a badge or a small action. */
  action?: ReactNode;
  children: ReactNode;
}

/**
 * The card shell every settings section shares, so headings, spacing and the
 * scroll-anchor behaviour stay identical across the page.
 */
export function SettingsSection({
  id,
  title,
  description,
  icon,
  action,
  children,
}: SettingsSectionProps) {
  return (
    // scroll-mt keeps the heading clear of the sticky top bar when jumped to.
    <Card id={id} className="scroll-mt-24">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
          {icon}
          {title}
        </CardTitle>
        <CardDescription className="text-sm text-gray-600">{description}</CardDescription>
        {action ? <div className="col-start-2 row-span-2 self-start">{action}</div> : null}
      </CardHeader>
      <CardContent className="space-y-6">{children}</CardContent>
    </Card>
  );
}

export function ErrorAlert({ children }: { children: ReactNode }) {
  if (!children) return null;

  return (
    <Alert className="border-red-200 bg-red-50">
      <AlertCircle className="h-4 w-4 text-red-500" />
      <AlertDescription className="text-sm text-red-700">{children}</AlertDescription>
    </Alert>
  );
}

export function SuccessAlert({ children }: { children: ReactNode }) {
  if (!children) return null;

  return (
    <Alert className="border-green-200 bg-green-50">
      <CheckCircle className="h-4 w-4 text-green-500" />
      <AlertDescription className="text-sm text-green-700">{children}</AlertDescription>
    </Alert>
  );
}
