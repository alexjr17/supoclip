"use client";

import { Button } from "@/components/ui/button";
import { CreditCard } from "lucide-react";

import {
  formatBillingPlanName,
  getPublicBillingPlans,
  isPaidBillingPlan,
  type BillingPlanId,
} from "@/lib/billing-plans";

import { ErrorAlert, SettingsSection } from "./settings-section";
import type { BillingSummary } from "../_hooks/use-billing-summary";

interface BillingSectionProps {
  summary: BillingSummary;
  isActionLoading: boolean;
  error: string | null;
  onAction: (plan?: BillingPlanId) => void;
}

export function BillingSection({
  summary,
  isActionLoading,
  error,
  onAction,
}: BillingSectionProps) {
  const isPaid = isPaidBillingPlan(summary.plan);
  const paidPlans = getPublicBillingPlans();

  const usageLabel = summary.upgrade_required
    ? "Current plan cannot create generations."
    : summary.usage_limit === null
      ? `${summary.usage_count} generations in this billing period`
      : `${summary.usage_count}/${summary.usage_limit} generations used this period`;

  return (
    <SettingsSection
      id="billing"
      icon={<CreditCard className="h-4 w-4" />}
      title="Billing"
      description={isPaid ? usageLabel : "Video processing requires a paid plan."}
    >
      <div className="rounded-lg border bg-gray-50 p-4">
        <p className="text-sm text-gray-600">{usageLabel}</p>
        <p className="text-sm text-gray-500">
          Plan: {formatBillingPlanName(summary.plan)} ({summary.subscription_status})
        </p>
      </div>

      {isPaid ? (
        summary.subscription_provider === "apple" ? (
          <p className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600">
            Managed through the App Store
          </p>
        ) : (
          <Button
            type="button"
            variant="outline"
            onClick={() => onAction()}
            disabled={isActionLoading}
            className="w-full"
          >
            {isActionLoading ? "Loading..." : "Manage billing"}
          </Button>
        )
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {paidPlans.map((plan) => (
            <Button
              key={plan.id}
              type="button"
              variant={plan.highlighted ? "default" : "outline"}
              onClick={() => onAction(plan.id)}
              disabled={isActionLoading}
              className="h-auto min-h-12 flex-col gap-0.5 py-2"
            >
              <span>{isActionLoading ? "Loading..." : plan.cta}</span>
              <span className="text-xs font-normal opacity-80">
                ${plan.priceMonthly}/mo · {plan.generationLimit} generations
              </span>
            </Button>
          ))}
        </div>
      )}

      {error && <ErrorAlert>{error}</ErrorAlert>}
    </SettingsSection>
  );
}
