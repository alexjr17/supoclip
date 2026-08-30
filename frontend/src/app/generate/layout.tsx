import { noIndexMetadata } from "@/lib/seo";

export const metadata = noIndexMetadata;

export default function GenerateLayout({ children }: { children: React.ReactNode }) {
  return children;
}
