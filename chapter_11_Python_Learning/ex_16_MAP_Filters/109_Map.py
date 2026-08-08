numbers = [1, 2, 3, 4, 5]

def sq(x):
    return x ** 2

# Map - Apply the fn on each element and give you same size list.

all_number = list(map(sq, numbers))
print(all_number)