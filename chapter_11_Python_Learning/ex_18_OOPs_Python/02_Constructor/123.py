class MobilePhone:
    model = None

    def __init__(self):
        print("This is Constructor, I will be called when the Object is created!")
        # self - keyword which points to the current attributes
        print(self.model)

    def talk(self):
        print("Normal F(n)")

iphone = MobilePhone()
iphone.talk()