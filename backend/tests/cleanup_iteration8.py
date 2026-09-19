"""Iteration 8 cleanup: remove TEST_ deposits/users created during testing and clear login_attempts."""
import os

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from pymongo import MongoClient  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
print("deposits removed:", db.deposits.delete_many({"description": {"$regex": "^TEST_"}}).deleted_count)
print("deposits (seeded rows) removed:", db.deposits.delete_many({"session_id": {"$regex": "^TEST_it8"}}).deleted_count)
print("users removed:", db.users.delete_many({"session_id": {"$regex": "^TEST_it8"}}).deleted_count)
db.users.update_one({"session_id": "discord_test_1"}, {"$unset": {"promo_code": "", "promo_bonus": ""}})
db.login_attempts.delete_many({})
print("remaining deposits:", db.deposits.count_documents({}))
