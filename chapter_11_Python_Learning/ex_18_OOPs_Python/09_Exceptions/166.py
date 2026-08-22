def vwo_login(user):
    if user != "admin":
        raise Exception("Unauthorized Access!!")
    return "Welcome Admin"

# print(vwo_login("pramod"))
print(vwo_login("admin"))