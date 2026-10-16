# Rental Property Expense Tracker

A simple, private web app for tracking rental property expenses. Runs on your own computer with Docker.
Your data stays in a local file (`data/expenses.db`) and is never sent anywhere.

**Features:** yearly expense lists, monthly charges (management fee, agent, HOA), yearly totals,
PDF export, Excel import, one-click backup.

## Quick start
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop) and open it.
2. Download this project (green **Code** button > **Download ZIP**) and unzip it.
3. Windows: double-click `Start Expenses App.bat`. Mac: double-click `Start Expenses App.command`.
   Or run `docker compose up -d --build` in the folder.
4. Open http://localhost:8080

Set your property name in `docker-compose.yml` (the `PROPERTY_NAME` line).
See `HOW_TO_RUN.md` for beginner-friendly steps.

## Excel import format
Each sheet is named by year (e.g. `2025`). Expenses are in columns A (description), B (date), C (cost),
starting at row 3 and ending at a row labeled "Total". The 12 monthly rows are in rows 3-14 with
management fee, agent and HOA in columns F, G, H and an optional note in column I.

## License
MIT
