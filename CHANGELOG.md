# What's new

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
