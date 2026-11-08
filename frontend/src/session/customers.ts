// Demo customer directory. Names stay in the browser for display only: the backend stores the
// customer ID, never the name, so session history holds no personal data.
export type CustomerProfile = {
  name: string;
  role: string;
};

const DEMO_CUSTOMERS: Record<string, CustomerProfile> = {
  "1": { name: "Carl Wayne", role: "Floor supervisor · Line 3" },
};

export function customerProfile(customerId: string): CustomerProfile | null {
  return DEMO_CUSTOMERS[customerId] ?? null;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}
