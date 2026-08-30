"use client";

import { useCallback, useEffect, useState } from "react";

import { track } from "@/lib/datafast";
import { isPaidBillingPlan, type BillingPlanId } from "@/lib/billing-plans";

export interface BillingSummary {
  monetization_enabled: boolean;
  plan: string;
  subscription_status: string;
  subscription_provider: string | null;
  usage_count: number;
  usage_limit: number | null;
  remaining: number | null;
  upgrade_required: boolean;
}

/**
 * Owns the billing summary and the single action attached to it: paid plans
 * open the Stripe customer portal, free plans start a checkout session.
 *
 * Billing failures are reported here rather than in the shared preferences
 * alert, so the message lands next to the button the user actually pressed.
 */
export function useBillingSummary(userId: string | null) {
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;

    const fetchSummary = async () => {
      try {
        const response = await fetch("/api/tasks/billing-summary", { cache: "no-store" });
        if (!response.ok) return;
        setSummary(await response.json());
      } catch (fetchError) {
        console.error("Failed to fetch billing summary:", fetchError);
      }
    };

    void fetchSummary();
  }, [userId]);

  const startAction = useCallback(
    async (selectedPlan?: BillingPlanId) => {
      if (!summary?.monetization_enabled) return;

      const isPaid = isPaidBillingPlan(summary.plan);
      const route = isPaid ? "/api/billing/portal" : "/api/billing/checkout";
      const body = !isPaid && selectedPlan ? JSON.stringify({ plan: selectedPlan }) : undefined;

      try {
        setIsActionLoading(true);
        setError(null);
        const response = await fetch(route, {
          method: "POST",
          ...(body ? { headers: { "Content-Type": "application/json" }, body } : {}),
        });

        const responseText = await response.text();
        let data: { url?: string; error?: string } = {};
        if (responseText) {
          try {
            data = JSON.parse(responseText);
          } catch {
            data = { error: responseText };
          }
        }

        if (!response.ok || !data.url) {
          throw new Error(data.error || "Unable to open billing");
        }

        track(isPaid ? "billing_portal_opened" : "billing_checkout_started", {
          plan: summary.plan,
          selected_plan: selectedPlan,
        });
        window.location.href = data.url;
      } catch (billingError) {
        setError(billingError instanceof Error ? billingError.message : "Billing action failed");
      } finally {
        setIsActionLoading(false);
      }
    },
    [summary],
  );

  return { summary, isActionLoading, error, startAction };
}
