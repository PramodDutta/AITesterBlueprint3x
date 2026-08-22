class MathOperation:

    def div(self, a, b):
        return a / b

    @staticmethod
    def sum(a, b):
        return a + b



t = MathOperation()
print(t.div(10, 10))

print(MathOperation.sum(10, 10))