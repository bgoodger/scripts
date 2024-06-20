def expand_ranges(ranges):
    expanded_list = []
    for r in ranges.split(", "):
        start, end = map(int, r.split('-'))
        expanded_list.extend(range(start, end + 1))
    return expanded_list

# Define the ranges as a string
ranges = "1000-1920, 2000-2239, 2555-2574, 2740-2786"

# Expand the ranges and convert the list to a comma-separated string
expanded_list = expand_ranges(ranges)
comma_separated_list = ", ".join(map(str, expanded_list))

print(comma_separated_list)
