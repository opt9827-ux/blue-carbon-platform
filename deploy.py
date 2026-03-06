# File: deploy.py
import json
from web3 import Web3

# --- 1. PASTE YOUR PRIVATE KEY HERE ---
GANACHE_RPC_URL = "http://127.0.0.1:7545"
YOUR_PRIVATE_KEY = "0xbfc5e532178ff249456fd62bdb49a32e535819e024a0711785e08e597657ee14" 

# --- Details for CarbonToken.sol (already filled in) ---
YOUR_CONTRACT_ABI = [{"inputs":[],"stateMutability":"nonpayable","type":"constructor"},{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"balances","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"farmer","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"mint","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"}]
YOUR_CONTRACT_BYTECODE = "608060405234801561001057600080fd5b506040518060400160405280601581526020017f566572696669656420436172626f6e20546f6b656e000000000000000000000081525060019081610048919061019f565b506040518060400160405280600381526020017f56435400000000000000000000000000000000000000000000000000000000008152506002908161008d919061019f565b5034801561009957600080fd5b5033600081815481106100ab57fe5b9060005260206000209081019282156100d15791600091906100d7565b5055506101c1565b600080fd5b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b600061010b826100d7565b9050919050565b61011b8161010e565b82525050565b60006020820190506101346000830184610112565b92915050565b60006040828403121561014f5761014e61010a565b5b600061015d84828501610127565b91505092915050565b600081519050919050565b600082825260208201905092915050565b60005b838110156101b0578082015181840152602081019050610195565b60008484015250505050565b6000601f19601f830116905091905056fea264697066735822122043686e082f45511b7d1421255e4d2919ab56c2306940a6b7e3f81e3a4e526a6364736f6c63430008140033"

# --- DEPLOYMENT SCRIPT ---
w3 = Web3(Web3.HTTPProvider(GANACHE_RPC_URL))
if not w3.is_connected(): print("Failed to connect to Ganache."); exit()
try:
    account = w3.eth.account.from_key(YOUR_PRIVATE_KEY)
    w3.eth.default_account = account.address
    print(f"Using account {account.address} to deploy contract.")
except Exception as e: print(f"Error with private key: {e}."); exit()
try:
    Contract = w3.eth.contract(abi=YOUR_CONTRACT_ABI, bytecode=YOUR_CONTRACT_BYTECODE)
    tx = Contract.constructor().build_transaction({'nonce': w3.eth.get_transaction_count(account.address),'gasPrice': w3.eth.gas_price})
    signed_tx = w3.eth.account.sign_transaction(tx, YOUR_PRIVATE_KEY)
    print("Deploying contract to Ganache...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("\n----------------------------------------------------")
    print(f"✅ Contract deployed successfully!")
    print(f"📜 Contract Address: {tx_receipt.contractAddress}")
    print("----------------------------------------------------")
except Exception as e: print(f"Error deploying contract: {e}."); exit()