from app.security import hash_password, verify_password

test_password = "DemoPassword123!"

# Hash the password
hashed = hash_password(test_password)

# Test the results
print("Hash generated:", bool(hashed))
print("Correct password accepted:", verify_password(test_password, hashed))
print("Wrong password rejected:", not verify_password("WrongPassword!", hashed))
print("Original password stored in hash:", test_password in hashed)
