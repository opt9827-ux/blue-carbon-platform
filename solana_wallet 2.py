#!/usr/bin/env python3
"""
BhoomiChain — Solana Wallet + Blockchain Hashing Terminal
==========================================================
Run: python solana_wallet.py

Features
--------
• Generates a real Ed25519-style keypair (base58 public key + private seed)
• Streams live sensor rows from the dataset
• Hashes each batch → SHA-256 → Solana-style transaction signature
• Prints a coloured terminal ledger showing every on-chain entry
• Saves wallet + ledger to  data/wallet.json  and  data/ledger.json

NO external packages required beyond Python stdlib.
"""

import hashlib, json, os, time, secrets, csv, base64, struct
from datetime import datetime

# ── ANSI colours ─────────────────────────────────────────────────────────────
R  = "\033[31m";  G  = "\033[32m";  Y  = "\033[33m"
B  = "\033[34m";  M  = "\033[35m";  C  = "\033[36m"
W  = "\033[97m";  DIM = "\033[2m";  BOLD = "\033[1m";  RST = "\033[0m"
BG_DARK = "\033[40m"

BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def base58_encode(data: bytes) -> str:
    """Bitcoin/Solana base58 encoding."""
    n = int.from_bytes(data, "big")
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(BASE58_ALPHABET[r:r+1])
    result.extend([BASE58_ALPHABET[0:1]] * (len(data) - len(data.lstrip(b"\x00"))))
    return b"".join(reversed(result)).decode("ascii")

def generate_keypair():
    """
    Generate a mock Ed25519 keypair.
    Real Solana keypair = 64-byte seed || pubkey.
    We simulate this with secrets.token_bytes.
    """
    seed       = secrets.token_bytes(32)          # private seed
    # derive mock pubkey by hashing seed (real Ed25519 uses curve math)
    pubkey_raw = hashlib.sha256(seed + b"solana_ed25519_mock").digest()
    pubkey_b58 = base58_encode(pubkey_raw)
    privkey_b58 = base58_encode(seed + pubkey_raw)  # 64-byte secret key
    return {
        "public_key":  pubkey_b58,
        "private_key": privkey_b58,
        "seed_hex":    seed.hex(),
        "pubkey_hex":  pubkey_raw.hex(),
        "created_at":  datetime.utcnow().isoformat() + "Z",
        "network":     "devnet",
        "program_id":  base58_encode(hashlib.sha256(b"BhoomiChain_Program_v1").digest()),
    }

def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def build_transaction_signature(data_hash: str, pubkey: str, slot: int) -> str:
    """
    Simulate Solana transaction signature:
    sig = SHA-256(data_hash || pubkey || slot_bytes)
    Real Solana uses Ed25519 signing; this is deterministic mock.
    """
    slot_bytes = struct.pack(">Q", slot)
    combined   = (data_hash + pubkey).encode() + slot_bytes
    sig_bytes  = hashlib.sha256(combined).digest()
    # Solana sigs are 64 bytes base58; we extend with HMAC-like second pass
    sig_full   = sig_bytes + hashlib.sha256(sig_bytes + b"sol").digest()
    return base58_encode(sig_full)

def compute_soc_from_row(row):
    sm  = float(row.get("soil_moisture_pct", 40))
    st  = float(row.get("soil_temp_c", 28))
    hum = float(row.get("humidity_pct", 60))
    sm_n  = min(sm  / 60.0, 1.0)
    st_n  = max(0, 1 - (st - 15) / 35.0)
    hum_n = min(hum / 80.0, 1.0)
    return round(0.45*sm_n + 0.30*st_n + 0.20*hum_n, 4)

def irrigation_needed(sm, threshold=35.0):
    return sm < threshold

# ── Print helpers ─────────────────────────────────────────────────────────────
def clear_line():
    print("\r\033[K", end="")

def print_banner(wallet):
    os.system("clear" if os.name == "posix" else "cls")
    w = 82
    print(f"{BOLD}{BG_DARK}{G}{'═'*w}{RST}")
    print(f"{BOLD}{BG_DARK}{G}{'BhoomiChain — Solana Blockchain Ledger Terminal':^{w}}{RST}")
    print(f"{BOLD}{BG_DARK}{G}{'Decentralised Regenerative Agriculture Monitoring':^{w}}{RST}")
    print(f"{BOLD}{BG_DARK}{G}{'═'*w}{RST}")
    print()
    print(f"  {BOLD}{Y}WALLET DETAILS{RST}")
    print(f"  {DIM}{'─'*78}{RST}")
    print(f"  {C}Public Key    :{RST}  {BOLD}{W}{wallet['public_key']}{RST}")
    print(f"  {C}Program ID    :{RST}  {DIM}{wallet['program_id']}{RST}")
    print(f"  {C}Network       :{RST}  {G}Solana Devnet{RST}  (cluster: devnet.solana.com)")
    print(f"  {C}Created       :{RST}  {wallet['created_at']}")
    print(f"  {C}Private Key   :{RST}  {R}{'*' * 20}  [hidden — stored in data/wallet.json]{RST}")
    print()
    print(f"  {BOLD}{Y}LIVE SENSOR → BLOCKCHAIN FEED{RST}")
    print(f"  {DIM}{'─'*78}{RST}")
    print(f"  {DIM}{'Slot':<8} {'Timestamp':<20} {'Device':<18} {'SM%':<7} {'Temp°C':<8} "
          f"{'SOC':<6} {'💧Alert':<8} {'TxSig (truncated)'}{RST}")
    print(f"  {DIM}{'─'*78}{RST}")

def print_tx_row(slot, row, sig, soc, alert):
    ts  = row.get("timestamp","")[:19]
    dev = row.get("device_eui","")[-8:]
    sm  = float(row.get("soil_moisture_pct",0))
    st  = float(row.get("soil_temp_c",0))
    sig_short = sig[:28] + "…"
    alert_str = f"{R}⚠ WATER{RST}" if alert else f"{G}  OK   {RST}"
    sm_col    = R if sm < 35 else (Y if sm < 50 else G)
    print(f"  {DIM}{slot:<8}{RST} "
          f"{W}{ts:<20}{RST} "
          f"{C}{dev:<18}{RST} "
          f"{sm_col}{sm:<7.1f}{RST} "
          f"{Y}{st:<8.1f}{RST} "
          f"{M}{soc:<6.4f}{RST} "
          f"{alert_str}  "
          f"{DIM}{sig_short}{RST}")

def print_hash_block(data_hash, sig, slot, row):
    print(f"\n  {BOLD}{B}  ┌─ ON-CHAIN RECORD  (slot {slot}){RST}")
    print(f"  {B}  │  data_hash   :{RST} {Y}{data_hash}{RST}")
    print(f"  {B}  │  tx_sig      :{RST} {G}{sig}{RST}")
    print(f"  {B}  │  timestamp   :{RST} {row.get('timestamp','')}")
    print(f"  {B}  │  device      :{RST} {row.get('device_eui','')}")
    print(f"  {B}  │  payload     :{RST} {row.get('payload_hex','')}")
    print(f"  {B}  └─ CONFIRMED ✓{RST}\n")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    os.makedirs("data", exist_ok=True)
    DATASET = "data/bhoomichain_lorawan_dataset.csv"

    if not os.path.exists(DATASET):
        print(f"{R}Dataset not found. Run: python generate_dataset.py first.{RST}")
        return

    # Load or create wallet
    WALLET_FILE = "data/wallet.json"
    if os.path.exists(WALLET_FILE):
        with open(WALLET_FILE) as f:
            wallet = json.load(f)
        print(f"{G}Loaded existing wallet from {WALLET_FILE}{RST}")
    else:
        wallet = generate_keypair()
        with open(WALLET_FILE, "w") as f:
            json.dump(wallet, f, indent=2)
        print(f"{G}New wallet created → {WALLET_FILE}{RST}")

    # Load ledger
    LEDGER_FILE = "data/ledger.json"
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE) as f:
            ledger = json.load(f)
    else:
        ledger = []

    starting_slot = max((e["slot"] for e in ledger), default=0) + 1

    print_banner(wallet)

    # Stream dataset rows
    slot   = starting_slot
    batch  = []
    BATCH_SIZE = 3   # hash every 3 readings (one per device per timestamp)
    verbose_every = 12  # print detailed block every N batches

    with open(DATASET, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        rows_streamed = 0

        for row in reader:
            batch.append(row)

            if len(batch) >= BATCH_SIZE:
                # Build canonical JSON for hashing
                canonical = json.dumps(
                    [{k: v for k, v in r.items() if k != "payload_hex"}
                     for r in batch],
                    sort_keys=True, separators=(",", ":")
                )
                data_hash = sha256_hex(canonical)
                sig       = build_transaction_signature(
                    data_hash, wallet["public_key"], slot)
                soc_val   = compute_soc_from_row(batch[0])
                sm_val    = float(batch[0].get("soil_moisture_pct", 40))
                alert     = irrigation_needed(sm_val)

                # Store in ledger
                entry = {
                    "slot":        slot,
                    "timestamp":   batch[0]["timestamp"],
                    "device_eui":  batch[0]["device_eui"],
                    "data_hash":   data_hash,
                    "tx_sig":      sig,
                    "soc_index":   soc_val,
                    "soil_moisture": sm_val,
                    "soil_temp":   float(batch[0].get("soil_temp_c", 28)),
                    "air_temp":    float(batch[0].get("air_temp_c", 30)),
                    "humidity":    float(batch[0].get("humidity_pct", 60)),
                    "alert_water": alert,
                    "payload_hex": batch[0].get("payload_hex",""),
                }
                ledger.append(entry)

                # Print compact row
                print_tx_row(slot, batch[0], sig, soc_val, alert)

                # Print verbose block every Nth batch
                if slot % verbose_every == 0:
                    print_hash_block(data_hash, sig, slot, batch[0])

                # Flush ledger to disk every 50 entries
                if slot % 50 == 0:
                    with open(LEDGER_FILE, "w") as f:
                        json.dump(ledger[-500:], f, indent=2)  # keep last 500

                slot     += 1
                batch     = []
                rows_streamed += BATCH_SIZE

                time.sleep(0.04)   # 40ms between transactions (fast demo)

                # Stop after 200 slots for demo (run with --all flag for full)
                import sys
                if "--all" not in sys.argv and slot >= starting_slot + 200:
                    break

    # Final save
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)

    print(f"\n{BOLD}{G}{'═'*82}{RST}")
    print(f"{BOLD}{G}  ✅  BhoomiChain session complete!{RST}")
    print(f"{G}  Wallet   : {W}{wallet['public_key']}{RST}")
    print(f"{G}  Slots    : {starting_slot} → {slot-1}  ({slot-starting_slot} transactions){RST}")
    print(f"{G}  Ledger   : data/ledger.json  ({len(ledger)} entries){RST}")
    print(f"{G}  Dataset  : data/bhoomichain_lorawan_dataset.csv{RST}")
    print(f"{BOLD}{G}{'═'*82}{RST}\n")

if __name__ == "__main__":
    main()
