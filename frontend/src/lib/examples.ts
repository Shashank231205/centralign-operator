// Example requests shown on the home page. Any natural-language request works; these match
// the procedures in company_context/.
export const EXAMPLE_REQUESTS = [
  "Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our internal system, and tell me once it is done.",
  "Add a new vendor Globex with contact Hank Scorpio, hank@globex.test, to the ERP.",
  "Find all overdue invoices and export them to a CSV report.",
] as const;
