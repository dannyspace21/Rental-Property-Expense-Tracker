# How to run your Rental Tracker (no coding needed)

## One-time setup (about 10 minutes)
1. Install **Docker Desktop** (free): https://www.docker.com/products/docker-desktop
   Run the installer, accept the defaults, and restart your computer if asked.
   (On a Raspberry Pi, install Docker with `curl -fsSL https://get.docker.com | sh`.)
2. Open **Docker Desktop** once and wait until it says it is running (green/"Engine running").
3. Unzip this folder somewhere permanent, for example your Documents folder.
   Don't run it from inside the zip file.
4. Optional: open `docker-compose.yml` in a text editor and set `TZ` to your time zone
   (for example `America/Chicago` or `America/Los_Angeles`).

## Start the app
- **Windows:** double-click `Start Expenses App.bat`
- **Mac:** double-click `Start Expenses App.command`
  (if Mac blocks it: right-click it > Open > Open)
- **Pi / Linux:** in the folder, run `docker compose up -d --build`

The first start takes a few minutes while it builds. After that it takes seconds.
Then open your browser to **http://localhost:8090**

## Use it on your phone
1. Find your computer's or Pi's address on your network (for example `192.168.1.50`).
2. On your phone, connected to the same Wi-Fi, open `http://192.168.1.50:8090`.
3. Add it to your home screen so it opens like an app:
   - **iPhone:** tap the Share button > **Add to Home Screen**.
   - **Android:** tap the ⋮ menu > **Add to Home screen** (or **Install app**).

## First steps
1. **More → Properties**: rename your property and (optionally) add the purchase price, down payment and land value.
   Add more properties here too.
2. **Rent → Add lease**: enter your tenant, rent and due day.
3. **More → Recurring bills**: add bills that repeat (HOA, management fee, insurance, taxes, mortgage).
4. **More → Upkeep**: tap a suggestion such as "Replace HVAC filter" to get reminders.

## Everyday use
- Tap the big **+** button to log an expense or income. Snap a photo of the receipt right there.
- When rent comes in, tap **Mark paid** on the Home screen or the Rent page.
- Tap any item in **Money** to edit or delete it.
- **Reports** has your Schedule E summary and a **PDF report** button for tax time.

## Import your mortgage statements
1. Sign in to your mortgage lender's website and find your statements (usually under **Statements** or **Documents**).
   Download the monthly statement PDF.
2. In the app: **More → Mortgage**. Choose the property and the PDF, then tap **Read statement**.
3. Check the interest, principal and escrow amounts, then tap **Save payment**.
4. Each January, do the same with your **Form 1098** (tap **Read 1098**). The app compares it with what you
   recorded during the year and fills in any difference.

Made a mistake? Tap **Undo** next to the import on the Mortgage page.

## Load your old Excel data
Go to **More**, scroll to **Import from Excel**, choose the property and your file, and tap Import.

## Where is my data?
In the `data` folder next to these files:
- `expenses.db`: all your records (saved on every tap)
- `receipts/`: receipt photos and PDFs
- `backups/`: automatic daily copies (the last 14 days)

To back up everything, use **More → Download backup** (a .zip with your data and receipts), or copy the `data` folder.

## Stopping it
Open Docker Desktop > Containers > press the Stop button. Start it again the same way you started it.
The app also restarts by itself whenever Docker starts.
