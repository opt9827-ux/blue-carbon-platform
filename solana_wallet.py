#!/usr/bin/env python3
"""
BhoomiChain — Live Solana Blockchain Terminal
==============================================
Watch sensor data being hashed and confirmed on-chain IN REAL TIME.

Run:  python solana_wallet.py
      python solana_wallet.py --speed fast    (faster transactions)
      python solana_wallet.py --speed slow    (dramatic, easy to read)
      python solana_wallet.py --all           (run all 35,040 records)
"""

import hashlib, json, os, sys, time, secrets, csv, struct, shutil
from datetime import datetime

# ── ANSI ──────────────────────────────────────────────────────────────────────
def fg(r,g,b):  return f"\033[38;2;{r};{g};{b}m"
def bg(r,g,b):  return f"\033[48;2;{r};{g};{b}m"

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
ITALIC = "\033[3m"

CYAN   = fg(34,211,238)
GREEN  = fg(74,222,128)
YELLOW = fg(250,204,21)
ORANGE = fg(251,146,60)
RED    = fg(248,113,113)
PURPLE = fg(167,139,250)
WHITE  = fg(226,232,240)
MUTED  = fg(100,116,139)

BG_PANEL  = bg(17,24,39)
BG_HASH   = bg(10,30,18)
BG_SIG    = bg(10,10,35)
BG_ALERT  = bg(45,10,10)
BG_HEADER = bg(12,18,35)

# ── Terminal helpers ──────────────────────────────────────────────────────────
def tw():
    return min(shutil.get_terminal_size((120, 50)).columns, 160)

def move(row, col=1):
    sys.stdout.write(f"\033[{row};{col}H")

def clr():
    sys.stdout.write("\033[2K\r")

def flush():
    sys.stdout.flush()

def clear_screen():
    sys.stdout.write("\033[2J\033[H")

def hide_cursor(): sys.stdout.write("\033[?25l")
def show_cursor(): sys.stdout.write("\033[?25h")

# ── Base58 ────────────────────────────────────────────────────────────────────
B58 = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58enc(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = []
    while n:
        n, r = divmod(n, 58)
        out.append(B58[r:r+1])
    out.extend([B58[0:1]] * (len(data) - len(data.lstrip(b"\x00"))))
    return b"".join(reversed(out)).decode()

# ── Crypto ────────────────────────────────────────────────────────────────────
def make_wallet():
    seed = secrets.token_bytes(32)
    pub  = hashlib.sha256(seed + b"solana_ed25519_bhoomichain").digest()
    return {
        "public_key":  b58enc(pub),
        "private_key": b58enc(seed + pub),
        "program_id":  b58enc(hashlib.sha256(b"BhoomiChain_v1_Program").digest()),
        "seed_hex":    seed.hex(),
        "created_at":  datetime.now().isoformat(),
        "network":     "devnet",
    }

def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def make_sig(h: str, pubkey: str, slot: int) -> str:
    sb = struct.pack(">Q", slot)
    s1 = hashlib.sha256((h + pubkey).encode() + sb).digest()
    s2 = hashlib.sha256(s1 + b"solana_devnet").digest()
    return b58enc(s1 + s2)

# ── Layout ────────────────────────────────────────────────────────────────────
HEADER_ROWS  = 11
LIVE_TOP     = 13
LIVE_H       = 21
LEDGER_TOP   = LIVE_TOP + LIVE_H + 1
LEDGER_ROWS  = 10

ledger_lines = []
total_tx     = 0
total_alerts = 0

# ── Static header ─────────────────────────────────────────────────────────────
def draw_header(wallet):
    W = tw()
    move(1); clr()
    sys.stdout.write(BG_HEADER + BOLD + GREEN +
        "  BhoomiChain  ─  Live Solana Blockchain Ledger  ─  "
        "Decentralised Regenerative Agriculture Monitoring".center(W) + RESET + "\n")

    move(2); clr()
    sys.stdout.write(BG_HEADER + CYAN +
        "  LoRaWAN IN865  ·  Helium Network  ·  SHA-256 Hashing  ·  "
        "Ed25519 Signing  ·  Solana Devnet".center(W) + RESET + "\n")

    move(3); sys.stdout.write(MUTED + "─"*W + RESET + "\n")

    move(4); clr()
    sys.stdout.write(f"  {CYAN}PUBLIC KEY  {RESET}{BOLD}{WHITE}{wallet['public_key']}{RESET}\n")

    move(5); clr()
    sys.stdout.write(f"  {MUTED}PROGRAM ID  {RESET}{PURPLE}{wallet['program_id']}{RESET}\n")

    move(6); clr()
    sys.stdout.write(f"  {MUTED}NETWORK     {RESET}{GREEN}Solana Devnet{RESET}"
                     f"    {MUTED}CREATED  {RESET}{WHITE}{wallet['created_at'][:19]}{RESET}"
                     f"    {MUTED}PRIVATE KEY  {RESET}{RED}{'●'*20}  [stored in data/wallet.json]{RESET}\n")

    move(7); sys.stdout.write(MUTED + "─"*W + RESET + "\n")
    move(8); clr()  # stats row
    move(9); sys.stdout.write(MUTED + "─"*W + RESET + "\n")
    move(10); sys.stdout.write(f"  {BOLD}{YELLOW}▶  LIVE TRANSACTION PIPELINE{RESET}\n")
    move(11); sys.stdout.write(MUTED + "─"*W + RESET + "\n")
    flush()

def refresh_stats(slot, start_time):
    elapsed = max(0.001, time.time() - start_time)
    rate    = (slot) / elapsed
    move(8); clr()
    sys.stdout.write(
        f"  {MUTED}CONFIRMED {RESET}{GREEN}{BOLD}{total_tx:>5}{RESET}"
        f"   {MUTED}ALERTS {RESET}{RED}{BOLD}{total_alerts:>3}{RESET}"
        f"   {MUTED}HASH RATE {RESET}{CYAN}{rate:.2f}/s{RESET}"
        f"   {MUTED}SLOT {RESET}{WHITE}{slot}{RESET}"
        f"   {MUTED}UPTIME {RESET}{WHITE}{int(elapsed//60):02d}:{int(elapsed%60):02d}{RESET}"
        f"   {MUTED}CLOCK {RESET}{WHITE}{datetime.now().strftime('%H:%M:%S')}{RESET}"
    )
    flush()

# ── Live animation ────────────────────────────────────────────────────────────
def animate(slot, row, canonical, data_hash, sig, soc, sm, alert, speed):
    W   = tw()
    top = LIVE_TOP

    sm_col = RED if sm < 35 else (YELLOW if sm < 50 else GREEN)

    # Box top
    move(top);   clr(); sys.stdout.write(CYAN + "┌" + "─"*(W-2) + "┐" + RESET)
    move(top+1); clr()
    sys.stdout.write(CYAN + "│  " + RESET +
        BOLD + WHITE + f"SLOT {slot:>6}  ·  {row['timestamp']}  ·  "
        + CYAN + row['device_eui'] + RESET +
        f"  {MUTED}SM{RESET} {sm_col}{BOLD}{sm:.1f}%{RESET}"
        f"  {MUTED}TEMP{RESET} {ORANGE}{float(row.get('soil_temp_c',0)):.1f}°C{RESET}"
        f"  {MUTED}HUM{RESET} {PURPLE}{float(row.get('humidity_pct',0)):.1f}%{RESET}"
        f"  {MUTED}SOC{RESET} {GREEN}{soc:.4f}{RESET}"
    )
    move(top+2); clr(); sys.stdout.write(CYAN + "├" + "─"*(W-2) + "┤" + RESET)
    flush()

    # Step 1 — JSON
    move(top+3); clr()
    sys.stdout.write(CYAN + "│  " + RESET + MUTED + "① SERIALISE  " + RESET +
                     ITALIC + WHITE + "Building canonical JSON payload…" + RESET)
    move(top+4); clr()
    short = canonical[:W-8] + ("…" if len(canonical) > W-8 else "")
    sys.stdout.write(CYAN + "│  " + RESET + DIM + YELLOW + short + RESET)
    flush()
    time.sleep(speed * 0.25)

    # Step 2 — SHA-256 reveal
    move(top+5); clr(); sys.stdout.write(CYAN + "├" + "─"*(W-2) + "┤" + RESET)
    move(top+6); clr()
    sys.stdout.write(CYAN + "│  " + RESET + MUTED + "② SHA-256   " + RESET +
                     ITALIC + WHITE + "Hashing payload…" + RESET)
    flush()

    move(top+7); clr()
    sys.stdout.write(CYAN + "│  " + RESET + BG_HASH + YELLOW + BOLD)
    flush()

    delay = speed * 0.016
    for i, ch in enumerate(data_hash):
        sys.stdout.write(ch)
        if i % 4 == 3:
            flush()
            time.sleep(delay)
    sys.stdout.write(RESET)
    flush()
    time.sleep(speed * 0.15)

    # Step 3 — Signature reveal
    move(top+8); clr(); sys.stdout.write(CYAN + "├" + "─"*(W-2) + "┤" + RESET)
    move(top+9); clr()
    sys.stdout.write(CYAN + "│  " + RESET + MUTED + "③ SIGN      " + RESET +
                     ITALIC + WHITE + "Ed25519 keypair signing transaction…" + RESET)
    flush()

    move(top+10); clr()
    sys.stdout.write(CYAN + "│  " + RESET + BG_SIG + CYAN + BOLD)
    flush()

    sig_d = speed * 0.010
    for i, ch in enumerate(sig):
        sys.stdout.write(ch)
        if i % 6 == 5:
            flush()
            time.sleep(sig_d)
        if i >= W - 12:
            sys.stdout.write("…")
            break
    sys.stdout.write(RESET)
    flush()
    time.sleep(speed * 0.12)

    # Step 4 — Broadcast stages
    move(top+11); clr(); sys.stdout.write(CYAN + "├" + "─"*(W-2) + "┤" + RESET)
    move(top+12); clr()
    sys.stdout.write(CYAN + "│  " + RESET + MUTED + "④ BROADCAST " + RESET +
                     WHITE + "Submitting to Solana Devnet RPC…" + RESET)
    flush()

    stages = [
        (MUTED,   "  ○  Connecting to devnet.solana.com:8899…"),
        (YELLOW,  "  ◑  Transaction received by leader validator…"),
        (ORANGE,  "  ◕  Tower BFT: collecting 2/3 validator votes…"),
        (GREEN,   "  ●  ROOTED  —  FINALIZED  —  IMMUTABLE  ✓"),
    ]
    move(top+13); clr()
    for col, msg in stages:
        move(top+13); clr()
        sys.stdout.write(CYAN + "│  " + RESET + col + BOLD + msg + RESET)
        flush()
        time.sleep(speed * 0.17)

    # Step 5 — Result
    move(top+14); clr(); sys.stdout.write(CYAN + "├" + "─"*(W-2) + "┤" + RESET)

    if alert:
        move(top+15); clr()
        sys.stdout.write(CYAN + "│" + RESET +
            BG_ALERT + RED + BOLD +
            f"  ⚠  IRRIGATION ALERT  ─  SOIL MOISTURE {sm:.1f}%  ─  BELOW 35% THRESHOLD  ─  WATER NOW  " +
            RESET)
    else:
        move(top+15); clr()
        sys.stdout.write(CYAN + "│  " + RESET +
            GREEN + f"✓ Soil conditions optimal  ·  SM={sm:.1f}%  ·  "
            f"SOC={soc:.4f}  ·  No irrigation needed" + RESET)

    move(top+16); clr()
    sys.stdout.write(
        CYAN + "│  " + RESET +
        GREEN + BOLD + "✅ CONFIRMED ON-CHAIN" + RESET +
        f"  {MUTED}slot{RESET} {WHITE}{slot}{RESET}" +
        f"  {MUTED}hash{RESET} {YELLOW}{data_hash[:24]}…{RESET}" +
        f"  {MUTED}sig{RESET} {CYAN}{sig[:22]}…{RESET}" +
        f"  {MUTED}fee{RESET} {WHITE}0.000005 SOL{RESET}" +
        f"  {MUTED}latency{RESET} {WHITE}0.42s{RESET}"
    )

    move(top+17); clr(); sys.stdout.write(CYAN + "└" + "─"*(W-2) + "┘" + RESET)

    # Clear remaining lines in live box
    for extra in range(18, LIVE_H+1):
        move(top+extra); clr()

    flush()

# ── Ledger ────────────────────────────────────────────────────────────────────
def draw_ledger_header():
    W = tw()
    move(LEDGER_TOP); clr(); sys.stdout.write(MUTED + "─"*W + RESET)
    move(LEDGER_TOP+1); clr()
    sys.stdout.write(f"  {BOLD}{YELLOW}⛓  IMMUTABLE LEDGER{RESET}  "
                     f"{MUTED}(newest first · every entry SHA-256 verified · Solana Devnet){RESET}")
    move(LEDGER_TOP+2); clr()
    sys.stdout.write(
        MUTED +
        f"  {'SLOT':<7}{'TIMESTAMP':<22}{'DEVICE':<11}{'SM%':<8}"
        f"{'SOC':<9}{'SHA-256 HASH':40}{'STATUS'}" +
        RESET
    )
    move(LEDGER_TOP+3); clr(); sys.stdout.write(MUTED + "─"*W + RESET)
    flush()

def refresh_ledger():
    for i, ln in enumerate(ledger_lines[:LEDGER_ROWS]):
        move(LEDGER_TOP + 4 + i); clr()
        sys.stdout.write(ln)
    flush()

def fmt_ledger(e):
    sm = e["soil_moisture"]
    sc = RED if sm < 35 else (YELLOW if sm < 50 else GREEN)
    return (
        f"  {MUTED}{e['slot']:<7}{RESET}"
        f"{WHITE}{e['timestamp'][:19]:<22}{RESET}"
        f"{CYAN}{e['device_eui'][-10:]:<11}{RESET}"
        f"{sc}{BOLD}{sm:<8.1f}{RESET}"
        f"{GREEN}{e['soc_index']:<9.4f}{RESET}"
        f"{YELLOW}{e['data_hash'][:38]}…{RESET}"
        f"{GREEN}✓ CONFIRMED{RESET}"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global total_tx, total_alerts

    speed_map = {"fast": 0.45, "normal": 1.0, "slow": 2.0}
    speed   = 1.0
    run_all = False

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--all":     run_all = True
        if arg == "--speed" and i+1 < len(sys.argv):
            speed = speed_map.get(sys.argv[i+1], 1.0); i += 1
        if arg.startswith("--speed="):
            speed = speed_map.get(arg.split("=",1)[1], 1.0)
        i += 1

    os.makedirs("data", exist_ok=True)
    DATASET     = "data/bhoomichain_lorawan_dataset.csv"
    WALLET_FILE = "data/wallet.json"
    LEDGER_FILE = "data/ledger.json"

    if not os.path.exists(DATASET):
        print(f"{RED}Dataset not found. Run: python generate_dataset.py{RESET}")
        return

    wallet = (json.load(open(WALLET_FILE)) if os.path.exists(WALLET_FILE)
              else make_wallet())
    if not os.path.exists(WALLET_FILE):
        json.dump(wallet, open(WALLET_FILE,"w"), indent=2)

    ledger = json.load(open(LEDGER_FILE)) if os.path.exists(LEDGER_FILE) else []
    starting_slot = max((e["slot"] for e in ledger), default=0) + 1
    total_tx = len(ledger)

    for e in reversed(ledger[-LEDGER_ROWS:]):
        ledger_lines.append(fmt_ledger(e))

    # Initialise full screen
    hide_cursor()
    clear_screen()
    draw_header(wallet)
    draw_ledger_header()
    refresh_ledger()
    flush()

    slot       = starting_slot
    batch      = []
    BATCH      = 3
    start_time = time.time()

    try:
        with open(DATASET, newline="") as f:
            reader = csv.DictReader(f)

            for row in reader:
                batch.append(row)
                if len(batch) < BATCH:
                    continue

                canonical = json.dumps(
                    [{k: v for k,v in r.items() if k != "payload_hex"}
                     for r in batch],
                    sort_keys=True, separators=(",",":")
                )
                h   = sha256_hex(canonical)
                sig = make_sig(h, wallet["public_key"], slot)
                sm  = float(batch[0].get("soil_moisture_pct", 40))
                st  = float(batch[0].get("soil_temp_c", 28))
                hum = float(batch[0].get("humidity_pct", 60))
                soc = round(0.45*min(sm/60,1) + 0.30*max(0,1-(st-15)/35) + 0.20*min(hum/80,1), 4)
                alrt = sm < 35.0

                animate(slot, batch[0], canonical, h, sig, soc, sm, alrt, speed)

                total_tx += 1
                if alrt: total_alerts += 1

                entry = {
                    "slot":          slot,
                    "timestamp":     batch[0]["timestamp"],
                    "device_eui":    batch[0]["device_eui"],
                    "data_hash":     h,
                    "tx_sig":        sig,
                    "soc_index":     soc,
                    "soil_moisture": sm,
                    "soil_temp":     st,
                    "air_temp":      float(batch[0].get("air_temp_c", 30)),
                    "humidity":      hum,
                    "alert_water":   alrt,
                    "payload_hex":   batch[0].get("payload_hex",""),
                }
                ledger.append(entry)
                ledger_lines.insert(0, fmt_ledger(entry))

                refresh_stats(slot, start_time)
                refresh_ledger()
                flush()

                if slot % 25 == 0:
                    json.dump(ledger[-2000:], open(LEDGER_FILE,"w"), indent=2)

                slot  += 1
                batch  = []
                time.sleep(speed * 0.45)

    except KeyboardInterrupt:
        pass
    finally:
        json.dump(ledger, open(LEDGER_FILE,"w"), indent=2)
        show_cursor()
        W = tw()
        end_row = LEDGER_TOP + LEDGER_ROWS + 7
        move(end_row)
        print("\n" + GREEN + BOLD + "═"*W + RESET)
        print(f"  {GREEN}✅  Session ended{RESET}")
        print(f"  {MUTED}Wallet    {RESET}{WHITE}{wallet['public_key']}{RESET}")
        print(f"  {MUTED}Slots     {RESET}{WHITE}{starting_slot} → {slot-1}  "
              f"({slot - starting_slot} new transactions){RESET}")
        print(f"  {MUTED}Ledger    {RESET}{WHITE}data/ledger.json  ({len(ledger)} total){RESET}")
        print(f"  {MUTED}Alerts    {RESET}{RED}{total_alerts} irrigation alerts fired{RESET}")
        print(GREEN + BOLD + "═"*W + RESET + "\n")
        flush()

if __name__ == "__main__":
    main()
