# How to run your Expense Tracker (no coding needed)

## One-time setup (about 10 minutes)
1. Install **Docker Desktop** (free): https://www.docker.com/products/docker-desktop
   Run the installer, accept the defaults, and restart your computer if asked.
2. Open **Docker Desktop** once and wait until it says it is running (green/"Engine running").
3. Unzip this folder somewhere permanent, for example your Documents folder.
   Don't run it from inside the zip file.

## Start the app
- **Windows:** double-click `Start Expenses App.bat`
- **Mac:** double-click `Start Expenses App.command`
  (if Mac blocks it: right-click it > Open > Open)

The first start takes a few minutes while it builds. After that it takes seconds.
Then open your browser to **http://localhost:8080**

If double-clicking doesn't work, open a terminal (Windows: search "PowerShell"; Mac: search "Terminal"),
go into this folder, and run: `docker compose up -d --build`

## Load your Excel data
On the page, open **Import from Excel / Back up** at the bottom, choose
`your Excel file`, and click Import. Do this once.

## Everyday use
- Pick a year tab, fill in **Add an expense**, click **Add expense**.
- **Edit** or **Delete** sits at the end of each row.
- Fill in the monthly table and click **Save monthly charges**.
- **Export to PDF** (top right) downloads a printable PDF for that year.

## Where is my data?
In the `data` folder next to these files (`expenses.db`). It is saved on every click.
To back up, copy that file or use **Download a backup** in the app.

## Stopping it
Open Docker Desktop > Containers > press the Stop button. Start it again the same way you started it.
The app also restarts by itself whenever Docker Desktop starts.
