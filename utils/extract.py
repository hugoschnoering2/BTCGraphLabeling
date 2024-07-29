
import datetime
import re
import base58
import bech32
import requests
import time

from typing import Optional

from utils.patterns import BASE58_PATTERN, BASE58_PATTERN_BIS, BECH32_PATTERN, TXID_PATTERN


def extract_addresses(text) -> list:
    addresses = set()
    for address in re.findall(BASE58_PATTERN, text):
        try:
            base58.b58decode_check(address)
            addresses.add(address)  # checksum is valid
        except:
            pass
    for address in re.findall(BASE58_PATTERN_BIS, text):
        address = address.replace(" ", "").replace("\n", "").replace("\t", "")
        try:
            base58.b58decode_check(address)
            addresses.add(address)  # checksum is valid
        except:
            pass
    for address in re.findall(BECH32_PATTERN, text):
        decoded = bech32.bech32_decode(address)
        if decoded[1] is not None:
            addresses.add(address)
    return list(addresses)


def extract_transaction_ids(text) -> list:
    transaction_ids = set()
    for tx_id in re.findall(TXID_PATTERN, text):
        transaction_ids.add(tx_id)
    return list(transaction_ids)


def get_transactions_from_address(address: str, max_num_transactions: int = 500, sleep_time: float = 0.2):
    url = f"https://blockchain.info/rawaddr/{address}"
    resp = requests.get(url=url)  # first batch of transactions
    data = resp.json()
    num_transaction = int(data["n_tx"])
    transactions = data["txs"]
    for i in range(1, min(num_transaction // 100 + 1, max_num_transactions // 100)):
        time.sleep(sleep_time)
        resp = requests.get(url=url, params={"offset": i * 100})
        data = resp.json()
        transactions.extend(data["txs"])
    return transactions


def get_transaction_from_id(tx_id: str):
    url = f"https://blockchain.info/rawtx/{tx_id}"
    return requests.get(url=url).json()


def get_transaction_repr(tx_id, conversion_rate: float = None, sleep_time=0., max_inputs: int = 10,
                         max_outputs: int = 10, last_call_timestamp: Optional[datetime.datetime] = None) \
        -> tuple[Optional[str], datetime.datetime]:

    url = f"https://blockchain.info/rawtx/{tx_id}"

    if last_call_timestamp is not None \
            and (last_call_timestamp > datetime.datetime.now() - datetime.timedelta(seconds=sleep_time)):
        time.sleep(sleep_time)

    try:
        data = requests.get(url).json()
        last_call_timestamp = datetime.datetime.now()
        inputs, outputs = data["inputs"], data["out"]
    except:  # impossible to retrieve the transaction data
        return None, datetime.datetime.now()

    if len(inputs) > max_inputs or len(outputs) > max_outputs:
        return None, last_call_timestamp  # the transaction is too large

    str_inputs = "Input TXOS:\n"
    for txo in inputs:
        try:
            new_str = f"\t{txo['prev_out']['addr']} sent {float(txo['prev_out']['value']) / 10 ** 8} bitcoins"
            if conversion_rate is not None:
                new_str += f" ({float(txo['prev_out']['value']) / 10 ** 8 * conversion_rate:.4f}$)"
            str_inputs += new_str + "\n"
        except:
            continue

    str_outputs = "Output TXOS:\n"
    for txo in outputs:
        try:
            new_str = f"\t{txo['addr']} received {float(txo['value']) / 10 ** 8} bitcoins"
            if conversion_rate is not None:
                new_str += f" ({float(txo['value']) / 10 ** 8 * conversion_rate:.4f}$)"
            str_outputs += new_str + "\n"
        except:
            continue

    str_tx_id = f"Tx id: {tx_id}\n" + str_inputs + str_outputs

    return str_tx_id, last_call_timestamp

