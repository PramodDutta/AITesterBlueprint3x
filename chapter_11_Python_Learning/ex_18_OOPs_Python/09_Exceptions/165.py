try:
    a = int(input("Enter num 1"))
    b = int(input("Enter num 2"))
    c = a / b
except ValueError:
    print("Value Error")
except ZeroDivisionError:
    print("Div Error")
else: # Runs only if try block succeeds.
    print(c)
finally:
    print("I will always execute!")