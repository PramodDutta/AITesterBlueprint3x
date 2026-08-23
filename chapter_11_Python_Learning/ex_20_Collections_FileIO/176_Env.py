from dotenv import load_dotenv
import os
load_dotenv() 

print(os.getenv('DB_PASSWORD'))

if os.getenv('DB_PASSWORD') == "superSecret123!":
    print("Welcome Admin")
else:
    print("Goodbye")