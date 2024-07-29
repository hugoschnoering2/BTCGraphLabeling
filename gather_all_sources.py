
import os
import yaml
import json

import pandas as pd

try:  # loading the config file
    config = yaml.load(open("conf.yaml", "r"), Loader=yaml.FullLoader)
except FileNotFoundError:
    raise Exception("The config 'conf.yaml' is missing. See 'example_conf.yaml' for an example.")
except Exception as e:
    raise e

final_addresses = pd.DataFrame([], columns=["address", "entity", "category", "source"], index=[])

if os.path.exists(config["path_other_sources"]):

    for file in ["coinbase.txt",  # MINING
                 "coinmarketcap.txt", "defillama.txt",  # EXCHANGE
                 "montreal.txt", "padua.txt", "padua_sextorsion.txt",  # RANSOMWARE
                 "wbtc.txt",  # BRIDGE
                 "sdn.txt"  # VARIOUS
                 ]:

        new_addresses = pd.read_csv(os.path.join(config["path_other_sources"], file))
        if len(final_addresses) == 0:
            final_addresses = new_addresses
        else:
            final_addresses = pd.concat([final_addresses, new_addresses], axis=0, ignore_index=True)


# bet addresses
bet_addresses = dict()
if os.path.exists(os.path.join(config["path_other_sources"], "bet.txt")):
    bet_df = pd.read_csv(os.path.join(config["path_other_sources"], "bet.txt"), index_col=0)
    for address, row in bet_df.iterrows():
        bet_addresses[address] = row["entity"]


# address -> (entity_name -> (entity_category, count)
bitcointalk_addresses = dict()

# deposit addresses
if os.path.exists(os.path.join(config["path_chatgpt_resps"], "deposit", "processed_responses.json")):
    with open(os.path.join(config["path_chatgpt_resps"], "deposit", "processed_responses.json"), "r") as f:
        data = json.load(f)
    for thread_response in data.values():
        for thread_message in thread_response.values():
            if "entity_name" not in thread_message or "entity_type" not in thread_message or \
                    "deposit_addresses" not in thread_message:
                continue
            entity_name = thread_message["entity_name"]
            entity_type = thread_message["entity_type"]
            addresses = thread_message["deposit_addresses"]
            for address in addresses:
                if address not in bet_addresses:
                    if address not in bitcointalk_addresses:
                        bitcointalk_addresses[address] = {entity_name: {"entity_category": entity_type,
                                                                        "count": 1}}
                    elif entity_name not in bitcointalk_addresses[address]:
                        bitcointalk_addresses[address][entity_name] = {"entity_category": entity_type, "count": 1}
                    else:
                        bitcointalk_addresses[address][entity_name]["count"] += 1

# hot / cold wallets
if os.path.exists(os.path.join(config["path_chatgpt_resps"], "hot_cold", "processed_responses.json")):
    with open(os.path.join(config["path_chatgpt_resps"], "hot_cold", "processed_responses.json"), "r") as f:
        data = json.load(f)
    for thread_response in data.values():
        for thread_message in thread_response.values():
            if "detected_addresses" not in thread_message:
                continue
            for entity_name in thread_message["detected_addresses"]:
                entity_type = thread_message["detected_addresses"][entity_name]["category"]
                addresses = thread_message["detected_addresses"][entity_name]["addresses"]
                for address in addresses:
                    if address not in bet_addresses:
                        if address not in bitcointalk_addresses:
                            bitcointalk_addresses[address] = {entity_name: {"entity_category": entity_type,
                                                                            "count": 1}}
                        elif entity_name not in bitcointalk_addresses[address]:
                            bitcointalk_addresses[address][entity_name] = {"entity_category": entity_type, "count": 1}
                        else:
                            bitcointalk_addresses[address][entity_name]["count"] += 1


# withdrawal transactions
if os.path.exists(os.path.join(config["path_chatgpt_resps"], "withdraw", "processed_responses.json")):
    with open(os.path.join(config["path_chatgpt_resps"], "withdraw", "processed_responses.json"), "r") as f:
        data = json.load(f)
    for thread_response in data.values():
        for thread_message in thread_response.values():
            if "entity_name" not in thread_message or "entity_type" not in thread_message \
                    or "addresses" not in thread_message:
                continue
            entity_name = thread_message["entity_name"]
            entity_type = thread_message["entity_type"]
            addresses = thread_message["addresses"]
            for address in addresses:
                if address not in bet_addresses:
                    if address not in bitcointalk_addresses:
                        bitcointalk_addresses[address] = {entity_name: {"entity_category": entity_type,
                                                                        "count": 1}}
                    elif entity_name not in bitcointalk_addresses[address]:
                        bitcointalk_addresses[address][entity_name] = {"entity_category": entity_type, "count": 1}
                    else:
                        bitcointalk_addresses[address][entity_name]["count"] += 1


# withdrawal2 transactions
if os.path.exists(os.path.join(config["path_chatgpt_resps"], "withdraw2", "processed_responses.json")):
    with open(os.path.join(config["path_chatgpt_resps"], "withdraw2", "processed_responses.json"), "r") as f:
        data = json.load(f)
    for thread_response in data.values():
        for thread_message in thread_response.values():
            if "entity_name" not in thread_message or "entity_type" not in thread_message \
                    or "entity_addresses" not in thread_message:
                continue
            entity_name = thread_message["entity_name"]
            entity_type = thread_message["entity_type"]
            addresses = thread_message["entity_addresses"]
            for address in addresses:
                if address not in bet_addresses:
                    if address not in bitcointalk_addresses:
                        bitcointalk_addresses[address] = {entity_name: {"entity_category": entity_type,
                                                                        "count": 1}}
                    elif entity_name not in bitcointalk_addresses[address]:
                        bitcointalk_addresses[address][entity_name] = {"entity_category": entity_type, "count": 1}
                    else:
                        bitcointalk_addresses[address][entity_name]["count"] += 1


final_bitcointalk_addresses = {k: {"entity": v, "category": "BET", "source": "BitcoinTalk"}
                               for k, v in bet_addresses.items()}
for address, v in bitcointalk_addresses.items():
    if len(v) == 1:
        for entity_name in v.keys():
            final_bitcointalk_addresses[address] = {"entity": entity_name,
                                                    "category": v[entity_name]["entity_category"],
                                                    "source": "BitcoinTalk"}
    else:
        categories = {v[entity_name]["entity_category"] for entity_name in v.keys()}
        if len(categories) == 1:
            final_bitcointalk_addresses[address] = {"entity": "",
                                                    "category": list(categories)[0],
                                                    "source": "BitcoinTalk"}


final_bitcointalk_addresses = pd.DataFrame(final_bitcointalk_addresses).T.sort_values(by="entity")\
    .reset_index(names="address")


if os.path.exists(config["path_other_sources"]):
    bitcointalk_profile_addresses = pd.read_csv(os.path.join(config["path_other_sources"], "bitcointalk_profile.txt"))
    bitcointalk_profile_addresses = bitcointalk_profile_addresses.loc[
        ~bitcointalk_profile_addresses["address"].isin(final_bitcointalk_addresses["address"])]


final_addresses = pd.concat([final_bitcointalk_addresses,  bitcointalk_profile_addresses, final_addresses], axis=0,
                            ignore_index=True)
final_addresses = final_addresses[~final_addresses["category"].isna()]


# Save the addresses
final_addresses.to_csv("addresses.csv")
