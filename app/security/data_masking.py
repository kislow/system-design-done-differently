SENSITIVE_FIELDS = {
    "password",
    "token",
    "access_token",
    "authorization",
    "card_number",
    "cvv",
}

def mask_sensitive_data(data):
    masked = {}

    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELDS:
            masked[key] = "*******ENCRYPTED********"
        else:
            masked[key] = value

    return masked


payload = {
    "email": "user@example.com",
    "password": "SuperSecret123",
    "access_token": "eyJhbGciOi...",
    "card_number": "4111111111111111"
}

print(mask_sensitive_data(payload))
