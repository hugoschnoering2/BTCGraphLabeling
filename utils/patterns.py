
import re

BASE58_PATTERN = "[13][123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{25,34}"
BASE58_PATTERN_BIS = "[13][123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{25,34}[ \n\t]"
BECH32_PATTERN = "bc1q[a-z0-9]{38}"
TXID_PATTERN = "[0-9a-fA-F]{64}"

DIRECTBET_PATTERN_BETID = re.compile(
    r"(https?://)?"   # Optional "http://" or "https://"
    r"(www\d?\.)?"    # Optional "www.", "www1.", etc.
    r"(directbet)"  # Domain name (may include subdomains)
    r"(\.eu)"  # Top-level domain (e.g., .com, .org)
    r"(/BetStatus\.cshtml)"     # Optional path
    r"(\?BetID=)?"
    r"([13][123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{25,34})"
)

DIRECTBET_PATTERN_AFFILIATE_ID = re.compile(
    r"(https?://)?"   # Optional "http://" or "https://"
    r"(www\d?\.)?"    # Optional "www.", "www1.", etc.
    r"(directbet)"  # Domain name (may include subdomains)
    r"(\.eu)"  # Top-level domain (e.g., .com, .org)
    r"(\?AffiliateID=)?"
    r"([13][123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{25,34})"
)

FAIRLAY_PATTERN = re.compile(
    r"(https?://)?"   # Optional "http://" or "https://"
    r"(www\d?\.)?"    # Optional "www.", "www1.", etc.
    r"(fairlay)"  # Domain name (may include subdomains)
    r"(\.com)"  # Top-level domain (e.g., .com, .org)
    r"(/[a-zA-Z0-9.-]+/)"
    r"([13][123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{25,34})"
    r"(/)"
)

URL_PATTERN = re.compile(
    r"(https?://)?"   # Optional "http://" or "https://"
    r"(www\d?\.)?"    # Optional "www.", "www1.", etc.
    r"([a-zA-Z0-9.-]+)"  # Domain name (may include subdomains)
    r"(\.[a-zA-Z]{2,})"  # Top-level domain (e.g., .com, .org)
    r"(:\d{2,5})?"     # Optional port number
    r"(/[^\s?#]*)?"     # Optional path
    r"(\?[^\s#]*)?"       # Optional query parameters
)
