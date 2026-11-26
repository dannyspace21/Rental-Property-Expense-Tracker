# How to run your Rental Tracker (no coding needed)

There are two ways to run the app. Pick one:
- **Option A: Docker.** Works on Windows, Mac, Linux, a Raspberry Pi or a Docker-capable NAS.
- **Option B: Direct install.** For a Linux computer or Raspberry Pi, without Docker.

## Option A: Docker

### One-time setup (about 10 minutes)
1. Install **Docker Desktop** (free): https://www.docker.com/products/docker-desktop
   Run the installer, accept the defaults, and restart your computer if asked.
   (On a Raspberry Pi or Linux, install Docker with `curl -fsSL https://get.docker.com | sh`.)
2. Open **Docker Desktop** once and wait until it says it is running (green/"Engine running").
3. Unzip this folder somewhere permanent, for example your Documents folder.
   Don't run it from inside the zip file.
4. Open `docker-compose.yml` in a text editor. Set `PROPERTY_NAME` to your property's name and `TZ` to your
   time zone (for example `America/Chicago` or `America/Los_Angeles`).

### Start the app
- **Windows:** double-click `Start Expenses App.bat`
- **Mac:** double-click `Start Expenses App.command`
  (if Mac blocks it: right-click it > Open > Open)
- **Pi / Linux:** in the folder, run `docker compose up -d --build`

The first start takes a few minutes while it builds. After that it takes seconds.
Then open your browser to **http://localhost:8090**

## Option B: Direct install on Linux (no Docker)

### Install (about 5 minutes)
Open a terminal on the Linux computer or Pi (or connect to it with SSH) and run:

```bash
sudo apt install git python3 python3-venv
git clone https://github.com/dannyspace21/Rental-Property-Expense-Tracker.git
cd Rental-Property-Expense-Tracker
./install.sh
```
(On Fedora, use `sudo dnf install git python3` for the first line.)

- Run `./install.sh` as your normal user, **not** with `sudo`.
- It asks for your **property name**, then asks for your password once so it can set the app to start automatically.
- When it's done, it shows the address to open, for example `http://192.168.1.50:8090`.

### Handy commands
Run these from inside the `Rental-Property-Expense-Tracker` folder:
- **Is it running?** `systemctl status rental-tracker`
- **Something wrong?** `journalctl -u rental-tracker -n 50` shows the latest messages.
- **Update to the newest version:** `git pull && ./install.sh`
- **Change the port, property name or time zone:** edit `rental-tracker.env`, then run `./install.sh`.
- **Remove it:** `./install.sh --uninstall` (your data folder is kept).

## Use it on your phone
1. Find your computer's or Pi's address on your network (for example `192.168.1.50`). On Linux, `hostname -I` shows it.
2. On your phone, connected to the same Wi-Fi, open `http://192.168.1.50:8090`.
3. Add it to your home screen so it opens like an app:
   - **iPhone:** tap the Share button > **Add to Home Screen**.
   - **Android:** tap the ⋮ menu > **Add to Home screen** (or **Install app**).

## First steps
1. On **Home**, tap **Rename / edit** to give your property its real name (and address).
   Have more than one? Tap **+ Add property** at the top.
2. **Rent → Add lease**: enter your tenant, rent and due day.
3. Fill in the **Monthly charges** table on Home (management fee, due to agent, HOA) and tap **Save monthly charges**.

## Everyday use
- **Add an expense:** on **Home**, pick the property, fill in the date, what it was, category and cost, and tap **Add expense**.
  Tap *Notes, receipt, paid to…* to snap a photo of the receipt.
- **Management fee, agent or HOA:** type it into that month's row in the **Monthly charges** table and tap **Save monthly charges**.
- **Fix or delete an expense:** tap it in the expenses list on Home.
- **Rent came in?** On the **Rent** page, tap that month's box to mark it paid. Tap it again to undo.
- **Tax time:** **Reports** has your Schedule E summary and a **PDF report** button.
- **Light or dark mode:** tap the button at the top right, or choose on the **More** page.

## Add your loan and Form 1098
1. Go to **More → Properties** and tap your property (or tap **Rename / edit** on Home).
2. Under **Loan information**, fill in what you know (lender, loan type, interest rate...) and tap **Save loan information**.
3. Each January, sign in to your mortgage lender's website and download your **Form 1098** PDF
   (usually under **Statements**, **Documents** or **Tax documents**).
4. Back on the property's page, under **Form 1098 by year**, choose the file and tap **Import 1098**.
   Check the numbers and tap **Save**. The interest and property taxes go into your Schedule E report automatically.

Made a mistake? Tap **Remove** next to that year.

## Load your old Excel data
Go to **More**, scroll to **Import from Excel**, choose the property and your file, and tap Import.

## Where is my data?
In the `data` folder next to these files:
- `expenses.db`: all your records (saved on every tap)
- `receipts/`: receipt photos and PDFs
- `backups/`: automatic daily copies (the last 14 days)

To back up everything, use **More → Download everything (.zip)** (your data and receipts), or copy the `data` folder.

## Stopping it
- **Docker:** open Docker Desktop > Containers > press the Stop button (or run `docker compose down` in the folder).
  Start it again the same way you started it. The app also restarts by itself whenever Docker starts.
- **Direct install:** `sudo systemctl stop rental-tracker` stops it and `sudo systemctl start rental-tracker`
  starts it again. It also starts by itself whenever the computer boots.
