class Father1:
    def money(self):
        print("F1 Money")

class Father2:
    def money(self):
        print("F2 Money")

class Child(Father1, Father2):
    def give_money(self):
        print("Son")
        self.money()


c = Child()
c.give_money() #MRO
