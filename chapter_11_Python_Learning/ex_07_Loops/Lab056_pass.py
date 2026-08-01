for i in range(0, 10, 1):
    if i == 6 or i == 5:
        print(i)
    else:
        pass # do nothing


# | i  | Condition | O/P
# | 0  | 0 == 6 -> False | O/P - Nothing will be printed
# | 1  | 1 == 6 -> False | O/P - Nothing will be printed
# | 2  | 2 == 6 -> False | O/P - Nothing will be printed
# | 3  | 3 == 6 -> False | O/P - Nothing will be printed
# | 4  | 4 == 6 -> False | O/P - Nothing will be printed
# | 5  | 5 == 5 -> True | O/P - 5
# | 6  | 6 == 5 -> True | O/P - 6
# | 7  | 7 == 6 -> False | O/P - Nothing will be printed
# | 8  | 8 == 6 -> False | O/P - Nothing will be printed
# | 9  | 9 == 6 -> False | O/P - Nothing will be printed
# | 10  | 10 == 6 -> For loop finished