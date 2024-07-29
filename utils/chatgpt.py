import os
import re
import json
import time
import datetime

import pandas as pd

from tqdm import tqdm

from utils.extract import extract_addresses, extract_transaction_ids, get_transaction_repr, \
    get_transactions_from_address, get_transaction_from_id


btc_usd = pd.read_csv("utils/BTC-USD.csv", index_col=0)  # conversion rate BTC/USD
btc_usd.index = pd.to_datetime(btc_usd.index)


def construct_raw_message(title, message, tx_strs: list) -> str:
    raw = "\n".join(line.lstrip() for line in message.splitlines() if line.strip())
    raw = f"Title: {title}\n\nPost: {raw}"
    txs = "\n".join([v for v in tx_strs])
    if len(txs) > 0:
        raw += "\n\nTransactions:\n" + txs
    return raw


def process_threads(path_threads: str,
                    threads_w_addresses_or_ids: dict,
                    open_ai_client,
                    openai_model: str,
                    prompt: str,
                    resp_folder: str,
                    max_files_per_folder: int,
                    must_contain: list,
                    add_transaction_details: bool
                    ):

    # get the list of already processed threads
    if os.path.exists(os.path.join(resp_folder, "already_processed.txt")):
        with open(os.path.join(resp_folder, "already_processed.txt"), "r") as f:
            already_processed = json.load(f)
    else:
        already_processed = []

    last_call_timestamp = None  # last call to the Blockchain.com API
    threads = sorted(list(threads_w_addresses_or_ids.keys()))
    threads = [thread for thread in threads if int(thread) not in already_processed]

    try:

        for i, t in tqdm(enumerate(threads), total=len(threads)):  # looping over the threads

            thread = json.load(open(os.path.join(path_threads, f"{t}.json")))
            title = thread["title"]
            thread_number = thread["thread_number"]

            res_dict_thread = {}  # dict to save the messages sent and received

            message_indexes = sorted(threads_w_addresses_or_ids[t])

            for message_index in tqdm(message_indexes, disable=len(message_indexes) < 200):  # looping over the messages

                message = thread[str(message_index)]["message"]
                date = datetime.datetime.strptime(thread[str(message_index)]["date"], "%Y-%m-%d %H:%M:%S") \
                    .replace(day=1, hour=0, minute=0, second=0)  # datetime of the message
                conversion_rate = btc_usd.loc[date][["Open", "Close"]].mean() if date in btc_usd.index else None

                words = set(message.lower().split(" "))
                if len(words.intersection(must_contain)) == 0:
                    continue

                message_addresses = extract_addresses(message)
                message_tx_ids = extract_transaction_ids(message)
                tx_strs = []

                if add_transaction_details:
                    for tx_id in message_tx_ids:  # for each transaction, transform it into a string
                        tx_str, last_call_timestamp = get_transaction_repr(tx_id=tx_id, conversion_rate=conversion_rate,
                                                                           last_call_timestamp=last_call_timestamp,
                                                                           sleep_time=0.1)
                        if tx_str is not None:
                            tx_strs.append(tx_str)
                    if len(message_addresses) == 0 \
                            and len(tx_strs) == 0:  # no address / tx --> no label can be inferred from this post
                        continue
                elif len(message_addresses) == 0 and len(message_tx_ids) == 0:
                    continue

                # raw post to be sent to ChatGPT
                raw = construct_raw_message(title=title, message=message, tx_strs=tx_strs)

                # we replace the bitcoin addresses / transaction ids in order to avoid misspelling
                raw_addresses = extract_addresses(raw)
                raw_tx_ids = extract_transaction_ids(raw)
                processed = raw
                for j, address in enumerate(raw_addresses):
                    processed = processed.replace(address, f"$btc_address_{j}")
                for j, tx_id in enumerate(raw_tx_ids):
                    processed = processed.replace(tx_id, f"$btc_tx_id_{j}")

                # send the processed input to ChatGPT
                response = open_ai_client.chat.completions.create(
                    model=openai_model,
                    messages=[{"role": "system", "content": prompt},
                              {"role": "user", "content": processed}])
                raw_response = response.choices[0].message.content

                # process the answer
                processed_response = raw_response
                for j, address in enumerate(raw_addresses):
                    processed_response = processed_response.replace(f"$btc_address_{j}", address)
                for j, tx_id in enumerate(raw_tx_ids):
                    processed_response = processed_response.replace(f"$btc_tx_id_{j}", tx_id)

                # information to be saved
                message_dict = {"title": title,
                                "message": message, "message_addresses": message_addresses,
                                "message_tx_ids": message_tx_ids,
                                "raw": raw, "raw_addresses": raw_addresses, "raw_tx_ids": raw_tx_ids,
                                "processed": processed,
                                "raw_response": raw_response, "processed_response": processed_response
                                }

                res_dict_thread[message_index] = message_dict

            already_processed.append(int(t))

            if len(res_dict_thread) > 0:  # if the dict of conversations is not empty

                q = thread_number // max_files_per_folder
                thread_folder = os.path.join(resp_folder,
                                             f"{q * max_files_per_folder}-{(q + 1) * max_files_per_folder}")
                if not os.path.exists(thread_folder):
                    os.mkdir(thread_folder)

                with open(os.path.join(thread_folder, f"{thread_number}.json"), "w") as f:
                    json.dump(res_dict_thread, f, indent=4)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        with open(os.path.join(resp_folder, "already_processed.txt"), "w") as f:
            json.dump(already_processed, f)
        raise e

    with open(os.path.join(resp_folder, "already_processed.txt"), "w") as f:
        json.dump(already_processed, f)


def process_deposit_response(resp_folder: str, valid_entities: dict):

    folders = os.listdir(resp_folder)
    response_files = []
    for folder in folders:
        if not os.path.isdir(os.path.join(resp_folder, folder)):
            continue
        for f in os.listdir(os.path.join(resp_folder, folder)):
            if f.endswith(".json"):
                response_files.append(os.path.join(resp_folder, folder, f))

    def extract_information(text):
        entity_pattern = re.compile(r"Entity:\s*([^\n]+)")
        deposit_addresses_pattern = re.compile(r"Deposit addresses:\s*([^\n]+)")
        entity_match = entity_pattern.search(text)
        deposit_addresses_match = deposit_addresses_pattern.search(text)
        return {
            "Entity": entity_match.group(1).strip() if entity_match else None,
            "Deposit addresses": [addr.strip() for addr in
                                  deposit_addresses_match.group(1).split(",")] if deposit_addresses_match else None
        }

    # load responses that have already been processed
    path_processed_responses = os.path.join(resp_folder, "processed_responses.json")
    if os.path.exists(path_processed_responses):
        with open(path_processed_responses, "r") as f:
            dict_processed_responses = json.load(f)
    else:
        dict_processed_responses = {}

    for file in tqdm(response_files, total=len(response_files)):

        with open(file, "r") as f:
            responses = json.load(f)

        thread_number = file.split("/")[-1].replace(".json", "")
        if thread_number not in dict_processed_responses:
            dict_processed_responses[thread_number] = {}

        for message_index, response in responses.items():

            if message_index in dict_processed_responses[thread_number]:  # message already processed
                continue

            processed_response = response["processed_response"]
            dict_processed_response = {"processed_response": processed_response}
            dict_processed_responses[thread_number][message_index] = dict_processed_response

            info = extract_information(processed_response)
            dict_processed_response.update({str(k): str(v) for k, v in info.items()})
            if info["Deposit addresses"] is None:  # info cannot be properly parsed
                continue

            deposit_addresses = []
            for address in info["Deposit addresses"]:
                for a in extract_addresses(str(address)):
                    deposit_addresses.append(a)
            dict_processed_response["deposit_addresses"] = deposit_addresses
            if len(deposit_addresses) == 0:  # no deposit address
                continue

            if info["Entity"] is None:  # no entity
                continue

            mentioned_valid_entities = set()
            for entity_name in valid_entities:
                if entity_name.lower() in str(info["Entity"]).lower():
                    if valid_entities[entity_name]["alias"] is None:
                        mentioned_valid_entities.add(entity_name)
                    else:
                        mentioned_valid_entities.add(valid_entities[entity_name]["alias"])
            mentioned_valid_entities = list(mentioned_valid_entities)
            dict_processed_response["mentioned_valid_entities"] = mentioned_valid_entities

            if len(mentioned_valid_entities) != 1:
                continue

            entity_name = mentioned_valid_entities[0]
            entity_type = valid_entities[entity_name]["category"]
            dict_processed_response["entity_name"] = entity_name
            dict_processed_response["entity_type"] = entity_type

    with open(path_processed_responses, "w") as f:
        json.dump(dict_processed_responses, f, indent=2)


def process_withdraw_response(resp_folder: str, valid_entities: dict):

    folders = os.listdir(resp_folder)
    response_files = []
    for folder in folders:
        if not os.path.isdir(os.path.join(resp_folder, folder)):
            continue
        for f in os.listdir(os.path.join(resp_folder, folder)):
            if f.endswith(".json"):
                response_files.append(os.path.join(resp_folder, folder, f))

    def extract_information(text):
        entity_pattern = re.compile(r"Entity:\s*([^\n]+)")
        type_of_entity_pattern = re.compile(r"Type of entity:\s*([^\n]+)")
        withdraw_transactions_pattern = re.compile(r"Withdraw transactions:\s*\[?([^\]\n]+)\]?")
        entity_match = entity_pattern.search(text)
        type_of_entity_match = type_of_entity_pattern.search(text)
        withdraw_transactions_match = withdraw_transactions_pattern.search(text)
        return {
            "Entity": entity_match.group(1) if entity_match else None,
            "Type of entity": type_of_entity_match.group(1) if type_of_entity_match else None,
            "Withdraw transactions": withdraw_transactions_match.group(1).split(",") if withdraw_transactions_match
            else None
        }

    # load responses that have already been processed
    path_processed_responses = os.path.join(resp_folder, "processed_responses.json")
    if os.path.exists(path_processed_responses):
        with open(path_processed_responses, "r") as f:
            dict_processed_responses = json.load(f)
    else:
        dict_processed_responses = {}

    try:

        for file in tqdm(response_files, total=len(response_files)):

            with open(file, "r") as f:
                responses = json.load(f)

            thread_number = file.split("/")[-1].replace(".json", "")
            if thread_number not in dict_processed_responses:
                dict_processed_responses[thread_number] = {}

            for message_index, response in responses.items():

                if message_index in dict_processed_responses[thread_number]:  # message already processed
                    continue

                processed_response = response["processed_response"]
                dict_processed_response = {"processed_response": processed_response}
                dict_processed_responses[thread_number][message_index] = dict_processed_response

                if len(response["raw_tx_ids"]) == 0:  # no withdrawal transaction
                    continue

                info = extract_information(processed_response)
                dict_processed_response.update({str(k): str(v) for k, v in info.items()})
                if info["Withdraw transactions"] is None:  # info cannot be properly parsed
                    continue

                tx_ids = extract_transaction_ids(str(info["Withdraw transactions"]))
                dict_processed_response["withdraw_tx_ids"] = tx_ids
                if len(tx_ids) == 0:  # no withdrawal transaction
                    continue

                if info["Entity"] is None:  # no entity
                    continue

                mentioned_valid_entities = set()
                for entity_name in valid_entities:
                    if entity_name.lower() in str(info["Entity"]).lower():
                        if valid_entities[entity_name]["alias"] is None:
                            mentioned_valid_entities.add(entity_name)
                        else:
                            mentioned_valid_entities.add(valid_entities[entity_name]["alias"])
                mentioned_valid_entities = list(mentioned_valid_entities)
                dict_processed_response["mentioned_valid_entities"] = mentioned_valid_entities

                if len(mentioned_valid_entities) != 1:
                    continue

                entity_name = mentioned_valid_entities[0]
                entity_type = valid_entities[entity_name]["category"]
                dict_processed_response["entity_name"] = entity_name
                dict_processed_response["entity_type"] = entity_type

                if entity_type is None:  # unknown or not 'interesting'
                    continue

                try:
                    input_addresses = set()
                    for tx_id in tx_ids:  # extract here the input addresses
                        transaction = get_transaction_from_id(tx_id=tx_id)
                        for txo in transaction.get("inputs", []):
                            input_addresses.add(txo["prev_out"]["addr"])
                        time.sleep(0.1)
                    dict_processed_response["addresses"] = list(input_addresses)
                except Exception as e:
                    del dict_processed_responses[thread_number][message_index]
                    raise e

    except KeyboardInterrupt:
        pass
    except Exception as e:
        try:
            del dict_processed_responses[thread_number][message_index]
        except:
            pass
        with open(path_processed_responses, "w") as f:
            json.dump(dict_processed_responses, f, indent=2)
        raise e

    try:
        del dict_processed_responses[thread_number][message_index]
    except:
        pass
    with open(path_processed_responses, "w") as f:
        json.dump(dict_processed_responses, f, indent=2)


def process_withdraw2_response(resp_folder: str, valid_entities: dict, path_threads: str):

    folders = os.listdir(resp_folder)
    response_files = []
    for folder in folders:
        if not os.path.isdir(os.path.join(resp_folder, folder)):
            continue
        for f in os.listdir(os.path.join(resp_folder, folder)):
            if f.endswith(".json"):
                response_files.append(os.path.join(resp_folder, folder, f))

    def extract_information(text):
        entity_pattern = re.compile(r"Entity:\s*([^\n]+)")
        type_of_entity_pattern = re.compile(r"Type of entity:\s*([^\n]+)")
        withdraw_addresses_pattern = re.compile(r"Withdraw addresses:\s*\[([^\]]+)\]")
        entity_match = entity_pattern.search(text)
        type_of_entity_match = type_of_entity_pattern.search(text)
        withdraw_addresses_match = withdraw_addresses_pattern.search(text)
        return {
            "Entity": entity_match.group(1).strip() if entity_match else None,
            "Type of entity": type_of_entity_match.group(1).strip() if type_of_entity_match else None,
            "Withdraw addresses": [addr.strip() for addr in
                                   withdraw_addresses_match.group(1).split(",")] if withdraw_addresses_match else []
        }

    def extract_numbers(text):
        number_pattern = re.compile(r"(-?\d+\.?\d*|\d+\.?\d*)\s*(bitcoin|btc|satoshi)?")
        matches = number_pattern.findall(text)
        return [match[0] for match in matches if
                not re.search(r"unknown|amount withdrawn|balance withdrawn|not specified", text,
                              re.IGNORECASE)]

    # load responses that have already been processed
    path_processed_responses = os.path.join(resp_folder, "processed_responses.json")
    if os.path.exists(path_processed_responses):
        with open(path_processed_responses, "r") as f:
            dict_processed_responses = json.load(f)
    else:
        dict_processed_responses = {}

    try:

        for file in tqdm(response_files, total=len(response_files)):

            with open(file, "r") as f:
                responses = json.load(f)

            thread_number = file.split("/")[-1].replace(".json", "")
            if thread_number not in dict_processed_responses:
                dict_processed_responses[thread_number] = {}

            for message_index, response in responses.items():

                if message_index in dict_processed_responses[thread_number]:  # message already processed
                    continue

                processed_response = response["processed_response"]
                dict_processed_response = {"processed_response": processed_response}
                dict_processed_responses[thread_number][message_index] = dict_processed_response

                if len(response["raw_addresses"]) == 0:  # no withdraw address
                    continue

                info = extract_information(processed_response)
                dict_processed_response.update({str(k): str(v) for k, v in info.items()})

                withdrawals = []
                for i in range(len(info["Withdraw addresses"]) // 2):
                    address = info["Withdraw addresses"][i * 2]
                    address = extract_addresses(address)
                    if len(address) != 1:
                        continue
                    address = address[0]
                    amount = info["Withdraw addresses"][i * 2 + 1]
                    for a in extract_addresses(amount):
                        amount = amount.replace(a, "")
                    amount = amount.lower()
                    in_satoshi, in_mbtc = "satoshi" in amount, "mbtc" in amount
                    detected_amount = extract_numbers(amount)
                    if len(detected_amount) != 1:
                        continue
                    detected_amount = float(detected_amount[0])
                    if in_satoshi:
                        detected_amount /= 10 ** 8
                    elif in_mbtc:
                        detected_amount /= 10 ** 4
                    withdrawals.append((address, detected_amount))

                dict_processed_response["withdrawals"] = withdrawals

                if len(withdrawals) == 0:  # no withdrawal
                    continue

                if info["Entity"] is None:  # no entity
                    continue

                mentioned_valid_entities = set()
                for entity_name in valid_entities:
                    if entity_name.lower() in str(info["Entity"]).lower():
                        if valid_entities[entity_name]["alias"] is None:
                            mentioned_valid_entities.add(entity_name)
                        else:
                            mentioned_valid_entities.add(valid_entities[entity_name]["alias"])
                mentioned_valid_entities = list(mentioned_valid_entities)
                dict_processed_response["mentioned_valid_entities"] = mentioned_valid_entities

                if len(mentioned_valid_entities) != 1:  # more than one entity detected
                    continue

                entity_name = mentioned_valid_entities[0]
                entity_type = valid_entities[entity_name]["category"]
                dict_processed_response["entity_name"] = entity_name
                dict_processed_response["entity_type"] = entity_type

                if entity_type is None:  # unknown or not 'interesting'
                    continue

                with open(os.path.join(path_threads, file.split("/")[-1]), "r") as f:
                    thread = json.load(f)

                message_date = datetime.datetime.strptime(thread[message_index]["date"], "%Y-%m-%d %H:%M:%S")
                dict_processed_response["message_date"] = str(message_date)

                dict_withdrawals = {}
                for address, amount in withdrawals:
                    if address not in dict_withdrawals:
                        dict_withdrawals[address] = [amount]
                    else:
                        dict_withdrawals[address].append(amount)

                try:

                    entity_addresses = []
                    final_withdraw_txs = []

                    for address, amounts in dict_withdrawals.items():

                        time.sleep(4)
                        txs = get_transactions_from_address(address=address, max_num_transactions=200,
                                                            sleep_time=4)
                        candidates_txs = []  # all possible withdrawal transactions
                        # involving the address within the time window of the message

                        for tx in txs:
                            tx_date = datetime.datetime.fromtimestamp(tx["time"])
                            if not (message_date - datetime.timedelta(days=3) <= tx_date
                                    <= message_date + datetime.timedelta(days=3)):
                                continue  # not in the time window
                            inputs_with_address = [txo for txo in tx["inputs"]
                                                   if txo["prev_out"].get("addr", "") == address]
                            if len(inputs_with_address) > 0:  # not a withdrawal if 'address' is in the input
                                continue
                            outputs_with_address_and_amount = [txo for txo in tx["out"]
                                                               if txo.get("addr", "") == address]
                            if len(outputs_with_address_and_amount) == 1:
                                candidates_txs.append((tx, outputs_with_address_and_amount[0]))

                        for amount in amounts:
                            amount_candidate_txs = []

                            for tx, txo in candidates_txs:
                                if txo["value"] * 0.99 <= amount * 10 ** 8 <= txo["value"] * 1.01:
                                    amount_candidate_txs.append(tx)

                            if len(amount_candidate_txs) == 1:  # it is a match !
                                match_tx = amount_candidate_txs[0]
                                final_withdraw_txs.append({
                                    "tx_id": match_tx["hash"],
                                    "tx_date": str(datetime.datetime.fromtimestamp(match_tx["time"])),
                                    "address": address,  "amount": amount})
                                for txo in match_tx["inputs"]:
                                    entity_addresses.append(txo["prev_out"]["addr"])

                    dict_processed_response["entity_addresses"] = entity_addresses
                    dict_processed_response["final_withdraw_txs"] = final_withdraw_txs

                except KeyboardInterrupt:
                    del dict_processed_responses[thread_number][message_index]
                    raise KeyboardInterrupt
                except Exception as e:
                    del dict_processed_responses[thread_number][message_index]
                    raise e

    except KeyboardInterrupt:
        try:
            del dict_processed_responses[thread_number][message_index]
        except:
            pass
    except Exception as e:
        try:
            del dict_processed_responses[thread_number][message_index]
        except:
            pass
        with open(path_processed_responses, "w") as f:
            json.dump(dict_processed_responses, f, indent=2)
        raise e

    with open(path_processed_responses, "w") as f:
        json.dump(dict_processed_responses, f, indent=2)


def process_hot_cold_response(resp_folder: str, valid_entities: dict):

    folders = os.listdir(resp_folder)
    response_files = []
    for folder in folders:
        if not os.path.isdir(os.path.join(resp_folder, folder)):
            continue
        for f in os.listdir(os.path.join(resp_folder, folder)):
            if f.endswith(".json"):
                response_files.append(os.path.join(resp_folder, folder, f))

    def extract_information(text):
        addresses_pattern = re.compile(r"Addresses:\s*\[(.*?)\]", re.DOTALL)
        matches = addresses_pattern.findall(text)
        address_entity_pairs = []
        for match in matches:
            pairs = re.findall(r"\('([^']+)', '([^']+)'\)", match)
            address_entity_pairs.extend(pairs)
        return address_entity_pairs

    # load responses that have already been processed
    path_processed_responses = os.path.join(resp_folder, "processed_responses.json")
    if os.path.exists(path_processed_responses):
        with open(path_processed_responses, "r") as f:
            dict_processed_responses = json.load(f)
    else:
        dict_processed_responses = {}

    unknown_entities = dict()

    for file in response_files:

        with open(file, "r") as f:
            responses = json.load(f)

        thread_number = file.split("/")[-1].replace(".json", "")
        if thread_number not in dict_processed_responses:
            dict_processed_responses[thread_number] = {}

        for message_index, response in responses.items():

            if message_index in dict_processed_responses[thread_number]:  # message already processed
                continue

            processed_response = response["processed_response"]
            dict_processed_response = {"processed_response": processed_response}
            dict_processed_responses[thread_number][message_index] = dict_processed_response

            pair_address_entity = extract_information(processed_response)
            dict_processed_response["pair_address_entity"] = pair_address_entity
            if len(pair_address_entity) == 0:
                continue

            detected_addresses = dict()

            for raw_address, raw_entity in pair_address_entity:

                address = extract_addresses(raw_address)
                if len(address) != 1:
                    continue
                address = address[0]

                mentioned_valid_entities = set()
                for entity_name in valid_entities:
                    if entity_name.lower() in raw_entity.lower():
                        if valid_entities[entity_name]["alias"] is None:
                            mentioned_valid_entities.add(entity_name)
                        else:
                            mentioned_valid_entities.add(valid_entities[entity_name]["alias"])
                mentioned_valid_entities = list(mentioned_valid_entities)

                if len(mentioned_valid_entities) != 1:  # no or too many entities mentioned
                    if len(mentioned_valid_entities) < 1:
                        unknown_entities[raw_entity] = unknown_entities.get(raw_entity, 0) + 1
                    continue

                entity_name = mentioned_valid_entities[0]
                entity_type = valid_entities[entity_name]["category"]

                if entity_type is None:
                    continue

                if entity_name not in detected_addresses:
                    detected_addresses[entity_name] = {"addresses": [address],
                                                       "category": entity_type}
                elif address not in detected_addresses[entity_name]["addresses"]:
                    detected_addresses[entity_name]["addresses"].append(address)

            dict_processed_response["detected_addresses"] = detected_addresses

    with open(path_processed_responses, "w") as f:
        json.dump(dict_processed_responses, f, indent=2)
