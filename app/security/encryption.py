import sqlite3
from cryptography.fernet import Fernet


# ---------------------------------
# 1. Create an encryption key
# ---------------------------------
# In production this should come from a secret manager/KMS,
# NOT be generated every time the application starts.
key = Fernet.generate_key()
cipher = Fernet(key)

print("Encryption key:", key.decode())


# ---------------------------------
# 2. Example sensitive data
# ---------------------------------
card_number = "4111111111111111"

print("\nOriginal value:")
print(card_number)


# ---------------------------------
# 3. Encrypt before storing in DB
# ---------------------------------
encrypted_card = cipher.encrypt(card_number.encode())

print("\nEncrypted value:")
print(encrypted_card.decode())


# ---------------------------------
# 4. Store encrypted value in SQLite
# ---------------------------------
conn = sqlite3.connect(":memory:")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT,
    card_number BLOB
)
""")

cursor.execute(
    "INSERT INTO customers (name, card_number) VALUES (?, ?)",
    ("Jasmin", encrypted_card)
)

conn.commit()


# ---------------------------------
# 5. Retrieve from database
# ---------------------------------
cursor.execute(
    "SELECT name, card_number FROM customers WHERE name = ?",
    ("Jasmin",)
)

name, encrypted_value = cursor.fetchone()

print("\nValue retrieved from DB:")
print(encrypted_value.decode())


# ---------------------------------
# 6. Decrypt inside application
# ---------------------------------
decrypted_card = cipher.decrypt(encrypted_value).decode()

print("\nDecrypted inside application:")
print(decrypted_card)


# ---------------------------------
# 7. Mask before displaying/logging
# ---------------------------------
def mask_card(number):
    return "*" * (len(number) - 4) + number[-4:]


masked_card = mask_card(decrypted_card)

print("\nSafe value shown to user/logs:")
print(masked_card)


conn.close()
