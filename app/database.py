from pymongo import MongoClient
from app.config import settings

client = MongoClient(settings.MONGO_URI)
db = client[settings.MONGO_DB]

# Collections
users_col = db.users
templates_col = db.templates
campaigns_col = db.campaigns
messages_col = db.messages
transactions_col = db.transactions
service_providers_col = db.service_providers
wallet_ledger_col = db.wallet_ledger
whitelist_col = db.whitelist
# ================= SERVICE PROVIDERS =================

service_providers_col = db["service_providers"]
user_providers_col = db["user_providers"]

