# What's new

## Version 3.4 · November 26, 2026
- **Form 1098 import reads every box.** It now handles lender PDFs that draw text word by word or letter by letter,
  values printed in the corner of each box, rotated pages and an instructions page, and finds the **lender** from the form.
- **Clearer review screen:** tax year, lender, property and account at the top, then **boxes 1 through 11 in the form's
  order** (box 7 checkbox, box 8 address, box 9 count, box 10 description and amount), then the taxes and insurance paid from escrow.
  The "Add to the app" column and "Compare & adjust" section are gone; saving updates your Schedule E to match the form.
- **Edit** a saved 1098 from the property's page.

## Version 3.3 · November 26, 2026
- **Loan information and Form 1098 now live on each property's page** (More → Properties → your property,
  or **Rename / edit** on Home): lender, loan type, interest rate, original amount, origination date and account
  (last 4 digits), plus a **Form 1098 by year** table with interest, balance, property taxes, mortgage insurance and the PDF.
- Importing a 1098 fills in any blank loan details for you.
- The separate **Mortgage** page and the **monthly mortgage statement import** were removed to keep things simple.
  The yearly 1098 covers what you need for taxes. Entries from earlier statement imports are kept.

## Version 3.2 · November 26, 2026
- **Form 1098 import rebuilt.** It now reads the official IRS form when your lender fills it in electronically
  (the numbers are stored in form fields, which the old reader couldn't see), the printed version, and lenders'
  own year-end statements ("Interest Paid", "Real Estate Taxes Disbursed"…).
- The import also picks up the **outstanding principal (box 2)**, **origination date (box 3)** and the
  **last 4 digits of the account number**, and keeps them with each year's 1098.

## Version 3.1 · November 26, 2026
Expenses and monthly charges are separate again, just like the original app.
- **Home has two separate sections:** **Expenses** (repairs, trips, supplies… with the add form and the year's list) and **Monthly charges**, the original 12-month table with **Mgmt fee**, **Due to agent**, **HOA** and **Note** columns.
- Type straight into the monthly table and tap **Save monthly charges**, like before.
- The summary is split again: **Total for the year**, **Expenses**, **Management fees**, **Due to agent**, **HOA** (and **Mortgage** if you import statements).
- Your original monthly notes (like "late fee") are back in the Note column.
- "Monthly bills" under More is renamed **Recurring bills** so it isn't confused with Monthly charges.

## Version 3.0 · November 26, 2026
A simpler, cleaner layout built around what matters most: your expenses.
- **Home works like the original app again:** pick your property at the top, pick a year, and add expenses right on the page. That year's list and your monthly bills table are below.
- **Your properties are front and center.** Switch between them, add one, or rename one from the top of Home.
- **Rent is easier:** each lease shows a box for every month. Tap a month to mark it paid (past months too), and tap again to undo.
- **Light and dark mode:** pick Automatic, Light or Dark on the More page, or tap the button at the top right.
- **Simpler menu:** Home, Rent, Reports and More. Search & export, Upkeep and Vendors moved under More.
- New **About & what's new** page (this one).
- Reports now include a month-by-month chart.

## Version 2.2 · November 24, 2026
- The app now runs on port **8090**.
- New **direct install for Linux** (no Docker needed): `./install.sh`.
- Mortgage import wording works for any lender.
- **Security:** other websites can no longer submit forms to the app through your browser; CSV exports can't run spreadsheet formulas.
- Fixed: deleting an imported mortgage entry no longer removes the statement PDF.

## Version 2.1 · November 23, 2026
- **Import mortgage statements (PDF):** each payment is split into interest, principal and escrow automatically.
- **Import Form 1098 (PDF):** compares the year's mortgage interest, property taxes and insurance with what's recorded and fills in the difference.

## Version 2.0 · November 23, 2026
- **Multiple properties.**
- **Income tracking** and net cash flow.
- Categories that match **IRS Schedule E**, with a Schedule E summary (PDF or CSV).
- Monthly bills that add themselves, receipt photos, leases and rent tracking, maintenance reminders, vendors with a 1099 check, depreciation and investment numbers.
- Works on phones; automatic daily backups.
- Your existing data was upgraded automatically (the original is kept as `data/backup-before-upgrade.db`).

## Version 1.0
- Yearly expense lists, monthly charges (management fee, agent, HOA), yearly totals, PDF export, Excel import and backup.
