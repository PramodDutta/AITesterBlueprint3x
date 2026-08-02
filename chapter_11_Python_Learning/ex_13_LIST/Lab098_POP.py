# squares = [1, 4, 9, 16, 25]
# print(squares)
# print(squares.pop()) # Remove and return item at index (default last)
# print(squares)
# print(squares.pop(1))
# print(squares)

# squares.clear()
# print(squares)

# # index(element, start, end)
# # Returns the index of the first occurrence of the element.
numbers = [10, 20, 30, 20, 40]
# print(numbers.index(20))
# print(numbers.count(20))

# numbers.sort()
# print(numbers)

# numbers.sort(reverse=True)
# print(numbers)

# # max() / min() / sum() Works for numerical lists.
# print(max(numbers))  # 40
# print(min(numbers))  # 10
# print(sum(numbers))  # 120

# Slicing (start, end-1) - index
# print(numbers)  # [10, 20, 20, 30, 40]
# print(numbers[1:4]) 


# print("apple" in numbers)
# print(20 in numbers)

l = list(range(1, 5))
print(l)

# Nested Lists
matrix = [[1,2,3], [4,5,6], [7,8,9]]
print(matrix[1][2])

del numbers[0]
print(numbers)