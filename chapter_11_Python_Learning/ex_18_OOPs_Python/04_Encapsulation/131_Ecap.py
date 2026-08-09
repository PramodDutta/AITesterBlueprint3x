class VWOLoginPage:
    def __init__(self,email_arg,password_arg):
        self.email = email_arg
        self.password = password_arg

    def login_confirm(self):
        if self.email == "pramod@gmail.com" and self.password == "pass123":
            print("Allowed to Login")
        else:
            print("Login Failed")


email = input("Enter the vwo login email ")
password = input("Enter the vwo login password ")

vwo_object_ref = VWOLoginPage(email,password)
vwo_object_ref.login_confirm()