---
id: overdue-report
title: Produce an overdue payables report
keywords: [overdue, late, past due, report, export, csv, unpaid, payables, aging]
systems: [internal_erp_api, internal_erp, workspace]
---

## When to use
Finance asks which supplier invoices are overdue.

## Definitions
An invoice is overdue when its status is unpaid and its due date is before today.

## Procedure
1. Get the overdue invoices from the ERP read API (`status=overdue`). The "Payable invoices"
   screen with the overdue filter shows the same data if the API is unavailable.
2. Write a CSV to the workspace named `overdue_invoices.csv` with the columns:
   `vendor, invoice_number, amount, currency, due_date, days_overdue` (due_date as YYYY-MM-DD,
   days_overdue as a whole number of days before today).
3. One row per overdue invoice, sorted by due date (oldest first).

## Done when
The CSV exists in the workspace and contains exactly the invoice numbers the ERP reports as
overdue.
