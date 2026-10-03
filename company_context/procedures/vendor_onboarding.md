---
id: vendor-onboarding
title: Add a new vendor to the ERP
keywords: [vendor, supplier, onboard, add, create, new, contact, master data]
systems: [internal_erp, internal_erp_api]
---

## When to use
A new supplier must exist in Ledgerly before its invoices can be recorded.

## Procedure
1. Check the ERP read API for a vendor with that exact name. If it exists, do not create a
   duplicate; report the existing record and any differences from the request.
2. Required details: vendor name, contact name, contact email, payment terms.
   If payment terms are not given, use the company default **NET30** and state that assumption.
   If the contact name or email is missing, ask the requester; do not invent contact details.
3. In Ledgerly use "New vendor", fill the form and save.
4. Read the confirmation message and note the ERP vendor id.

## Done when
The ERP read API returns exactly one vendor with that name, contact name, contact email and
payment terms.
