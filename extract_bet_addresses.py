
import os
import re
import yaml
import json
import base58

from tqdm import tqdm

from utils.patterns import BASE58_PATTERN, BASE58_PATTERN_BIS, DIRECTBET_PATTERN_BETID, \
    DIRECTBET_PATTERN_AFFILIATE_ID, FAIRLAY_PATTERN


try:  # loading the config file
    config = yaml.load(open("conf.yaml", "r"), Loader=yaml.FullLoader)
except FileNotFoundError:
    raise Exception("The config 'conf.yaml' is missing. See 'example_conf.yaml' for an example.")
except Exception as e:
    raise e


bet_addresses = []
path_threads = config["path_threads"]
files = os.listdir(path_threads)

try:

    for file in tqdm(files, total=len(files)):  # looping over all collected threads

        if not file.endswith(".json"):
            continue

        thread = json.load(open(os.path.join(path_threads, file), "r"))
        message_indexes = [k for k in thread.keys() if k not in ["title", "thread_number", "thread_url",
                                                                 "num_messages"]]

        for i in message_indexes:

            message = thread[i].get("message", "")
            detected_addresses = set()  # all Bitcoin addresses detected in the message

            for address in re.findall(BASE58_PATTERN, message):
                try:
                    decoded_address = base58.b58decode_check(address)
                    detected_addresses.add(address)
                except:
                    pass

            for address in re.findall(BASE58_PATTERN_BIS, message):
                address_ = address.replace(" ", "").replace("\n", "").replace("\t", "")
                try:
                    decoded_address = base58.b58decode_check(address)
                    detected_addresses.add(address)
                except:
                    pass

            if len(detected_addresses) == 0:
                continue

            for directbet_betid_url in re.findall(DIRECTBET_PATTERN_BETID, message):
                address = directbet_betid_url[6]
                if address in detected_addresses:
                    bet_addresses.append((address, "DirectBet"))

            for directbet_affiliateid_url in re.findall(DIRECTBET_PATTERN_AFFILIATE_ID, message):
                address = directbet_affiliateid_url[5]
                if address in detected_addresses:
                    bet_addresses.append((address, "DirectBet"))

            for fairlay_id in re.findall(FAIRLAY_PATTERN, message):
                address = fairlay_id[5]
                if address in detected_addresses:
                    bet_addresses.append((address, "Fairlay"))

except KeyboardInterrupt:
    pass
except Exception as e:
    raise e

with open(os.path.join(config["path_other_sources"], "bet.txt"), "w") as f:
    f.write("address,entity,category,source\n")
    for address, entity in bet_addresses:
        f.write(f"{address},{entity},BET,BitcoinTalk\n")
