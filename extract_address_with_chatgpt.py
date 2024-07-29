
import os
import json
import yaml

import numpy as np

from tqdm import tqdm
from openai import OpenAI

from utils.extract import extract_addresses, extract_transaction_ids
from utils.chatgpt import process_threads, process_deposit_response, process_withdraw_response, \
    process_withdraw2_response, process_hot_cold_response


try:  # loading the config file
    config = yaml.load(open("conf.yaml", "r"), Loader=yaml.FullLoader)
except FileNotFoundError:
    raise Exception("The config 'conf.yaml' is missing. See 'example_conf.yaml' for an example.")
except Exception as e:
    raise e


valid_entities = json.load(open("entities.json", "r"))  # list of well know entities


# First step: detecting threads / messages with addresses or transaction ids
if not os.path.exists("utils/threads_w_addresses_or_ids.json"):
    threads_w_addresses_or_ids = {}
    for file in tqdm(os.listdir(config["path_threads"])):  # looping over the threads
        if not file.endswith(".json"):
            continue
        thread = json.load(open(os.path.join(config["path_threads"], file)))
        thread_number = int(thread["thread_number"])
        message_indexes = [k for k in thread.keys() if k not in ["title", "thread_number", "thread_url",
                                                                 "num_messages"]]
        for message_index in message_indexes:  # looping over the messages
            message = thread[message_index]["message"]
            message_addresses = extract_addresses(message)
            message_tx_ids = extract_transaction_ids(message)
            if len(message_addresses) > 0 or len(message_tx_ids) > 0:
                if thread_number not in threads_w_addresses_or_ids:
                    threads_w_addresses_or_ids[thread_number] = []
                threads_w_addresses_or_ids[thread_number].append(int(message_index))
    with open("utils/threads_w_addresses_or_ids.json", "w") as f:
        json.dump(threads_w_addresses_or_ids, f, indent=4)
else:
    with open("utils/threads_w_addresses_or_ids.json", "r") as f:
        threads_w_addresses_or_ids = json.load(f)

num_threads = len(threads_w_addresses_or_ids)
num_messages = int(np.sum([np.sum(v) for v in threads_w_addresses_or_ids.values()]))
print(f"Num threads w at least one address / transaction id: {num_threads}, num messages: {num_messages}")


open_ai_client = OpenAI(api_key=config["openai_key"])  # OpenAI client
resp_folder = config["path_chatgpt_resps"]
if not os.path.exists(resp_folder):  # creating the folder for all responses received from ChatGPT
    os.mkdir(resp_folder)


# Second step: extracting deposit addresses

if config["do_deposit"]:

    with open("prompts/prompt_deposit.txt", "r") as f:  # loading the prompt
        deposit_prompt = f.readlines()
    deposit_prompt = ".".join(deposit_prompt)

    deposit_resp_folder = os.path.join(resp_folder, "deposit")
    if not os.path.exists(deposit_resp_folder):
        os.mkdir(deposit_resp_folder)

    print("Processing the threads to detect 'deposit addresses'.")
    process_threads(path_threads=config["path_threads"],
                    threads_w_addresses_or_ids=threads_w_addresses_or_ids,
                    open_ai_client=open_ai_client,
                    openai_model=config["openai_model"],
                    prompt=deposit_prompt,
                    resp_folder=deposit_resp_folder,
                    max_files_per_folder=config["max_files_per_folder"],
                    must_contain=["deposit", "deposited", "transfer", "transferred"],
                    add_transaction_details=True,
                    )

    print("Processing the responses to extract 'deposit addresses'.")
    process_deposit_response(resp_folder=deposit_resp_folder, valid_entities=valid_entities)


# Third step: extracting withdraw transactions

if config["do_withdraw"]:

    with open("prompts/prompt_withdraw.txt", "r") as f:  # loading the prompt
        withdraw_prompt = f.readlines()
    withdraw_prompt = ".".join(withdraw_prompt)

    withdraw_resp_folder = os.path.join(resp_folder, "withdraw")
    if not os.path.exists(withdraw_resp_folder):
        os.mkdir(withdraw_resp_folder)

    print("Processing the threads to detect 'withdrawal transactions'.")
    process_threads(path_threads=config["path_threads"],
                    threads_w_addresses_or_ids=threads_w_addresses_or_ids,
                    open_ai_client=open_ai_client,
                    openai_model=config["openai_model"],
                    prompt=withdraw_prompt,
                    resp_folder=withdraw_resp_folder,
                    max_files_per_folder=config["max_files_per_folder"],
                    must_contain=["withdraw", "withdrew", "withdrawn", "withdrawal"],
                    add_transaction_details=False
                    )

    print("Processing the responses to extract 'withdrawal transactions'.")
    process_withdraw_response(resp_folder=withdraw_resp_folder, valid_entities=valid_entities)


# Fourth step: extracting withdraw transactions (bis)

if config["do_withdraw2"]:

    with open("prompts/prompt_withdraw2.txt", "r") as f:  # loading the prompt
        withdraw2_prompt = f.readlines()
    withdraw2_prompt = ".".join(withdraw2_prompt)

    withdraw2_resp_folder = os.path.join(resp_folder, "withdraw2")
    if not os.path.exists(withdraw2_resp_folder):
        os.mkdir(withdraw2_resp_folder)

    print("Processing the threads to detect 'withdrawal addresses'.")
    process_threads(path_threads=config["path_threads"],
                    threads_w_addresses_or_ids=threads_w_addresses_or_ids,
                    open_ai_client=open_ai_client,
                    openai_model=config["openai_model"],
                    prompt=withdraw2_prompt,
                    resp_folder=withdraw2_resp_folder,
                    max_files_per_folder=config["max_files_per_folder"],
                    must_contain=["withdraw", "withdrew", "withdrawn", "withdrawal"],
                    add_transaction_details=False
                    )

    print("Processing the responses to extract 'withdrawal addresses'.")
    process_withdraw2_response(resp_folder=withdraw2_resp_folder, valid_entities=valid_entities,
                               path_threads=config["path_threads"])


# Last step: extracting hot / cold wallets

if config["do_hot_cold"]:

    with open("prompts/prompt_hot_cold.txt", "r") as f:  # loading the prompt
        hot_cold_prompt = f.readlines()
    hot_cold_prompt = ".".join(hot_cold_prompt)

    hot_cold_resp_folder = os.path.join(resp_folder, "hot_cold")
    if not os.path.exists(hot_cold_resp_folder):
        os.mkdir(hot_cold_resp_folder)

    print("Processing the threads to detect 'hot & cold wallets'.")
    process_threads(path_threads=config["path_threads"],
                    threads_w_addresses_or_ids=threads_w_addresses_or_ids,
                    open_ai_client=open_ai_client,
                    openai_model=config["openai_model"],
                    prompt=hot_cold_prompt,
                    resp_folder=hot_cold_resp_folder,
                    max_files_per_folder=config["max_files_per_folder"],
                    must_contain=["hot", "cold"],
                    add_transaction_details=False,
                    )

    print("Processing the responses to extract 'hot and cold addresses'.")
    process_hot_cold_response(resp_folder=hot_cold_resp_folder, valid_entities=valid_entities)
