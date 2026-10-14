"""APSC 160-style C templates. Registered into problems._TEMPLATES on import.

Function questions give the exact prototype (like APSC 160 PrairieLearn
questions); program questions read with scanf and print with printf, and their
output is compared exactly (trailing whitespace ignored).
"""
import textwrap

from .problems import template


def _c(**kw):
    kw["language"] = "c"
    kw["reference"] = textwrap.dedent(kw["reference"]).strip() + "\n"
    kw["prompt"] = textwrap.dedent(kw["prompt"]).strip()
    return kw


def _arr(name="data", src="list[int(-50..50)](0..12)", const=True, elem="int"):
    return {"name": name, "type": f"{'const ' if const else ''}{elem}[]", "input": src}


def _size(of="data", name="size"):
    return {"name": name, "type": "int", "size_of": of}


# ----------------------------------------------------------------- arrays

@template("arrays", 1, "c")
def c_count_in_range(rng):
    lo = rng.randint(-20, 0)
    hi = lo + rng.randint(10, 40)
    return _c(
        title=f"Count values in [{lo}, {hi}]", function="count_in_range", returns="int",
        params=[_arr(), _size()],
        prompt=f"""
            Write the function `count_in_range` that returns how many elements of the
            array `data` (which has `size` elements) are between **{lo}** and **{hi}**,
            inclusive.
        """,
        reference=f"""
            int count_in_range(const int data[], int size)
            {{
                int count = 0;
                for (int i = 0; i < size; i++) {{
                    if (data[i] >= {lo} && data[i] <= {hi}) {{
                        count++;
                    }}
                }}
                return count;
            }}
        """)


@template("arrays", 1, "c")
def c_average(rng):
    return _c(
        title="Array average", function="average", returns="double",
        params=[_arr(src="list[int(0..100)](1..10)"), _size()],
        prompt="""
            Write the function `average` that returns the average (mean) of the `size`
            integers in `data` as a `double`. `size` is always at least 1.
        """,
        reference="""
            double average(const int data[], int size)
            {
                int sum = 0;
                for (int i = 0; i < size; i++) {
                    sum += data[i];
                }
                return (double)sum / size;
            }
        """)


@template("arrays", 1, "c")
def c_index_of_max(rng):
    return _c(
        title="Index of the maximum", function="index_of_max", returns="int",
        params=[_arr(src="list[int(-20..20)](1..12)"), _size()],
        prompt="""
            Write the function `index_of_max` that returns the index of the largest
            element of `data`. If the largest value appears more than once, return the
            index of its **first** occurrence. `size` is always at least 1.
        """,
        reference="""
            int index_of_max(const int data[], int size)
            {
                int best = 0;
                for (int i = 1; i < size; i++) {
                    if (data[i] > data[best]) {
                        best = i;
                    }
                }
                return best;
            }
        """)


@template("arrays", 2, "c")
def c_reverse_array(rng):
    return _c(
        title="Reverse an array in place", function="reverse_array", returns="void",
        params=[_arr(src="list[int(0..99)](0..11)", const=False), _size()],
        prompt="""
            Write the function `reverse_array` that reverses the order of the `size`
            elements of `data` **in place** (modify the array; do not print anything).
        """,
        reference="""
            void reverse_array(int data[], int size)
            {
                for (int i = 0; i < size / 2; i++) {
                    int tmp = data[i];
                    data[i] = data[size - 1 - i];
                    data[size - 1 - i] = tmp;
                }
            }
        """)


@template("arrays", 2, "c")
def c_running_sum(rng):
    return _c(
        title="Running sum", function="running_sum", returns="void",
        params=[_arr("src", "list[int(-10..10)](0..10)"),
                {"name": "dest", "type": "int[]", "out_len": "src"}, _size("src")],
        prompt="""
            Write the function `running_sum` that fills `dest` so that `dest[i]` is the
            sum of `src[0]` through `src[i]`. Both arrays have `size` elements.
        """,
        reference="""
            void running_sum(const int src[], int dest[], int size)
            {
                int total = 0;
                for (int i = 0; i < size; i++) {
                    total += src[i];
                    dest[i] = total;
                }
            }
        """)


@template("arrays", 2, "c")
def c_count_above_average(rng):
    return _c(
        title="Count above average", function="count_above_average", returns="int",
        params=[_arr(src="list[int(0..20)](1..12)"), _size()],
        prompt="""
            Write the function `count_above_average` that returns how many elements of
            `data` are **strictly greater** than the average of all `size` elements.
            `size` is always at least 1. Careful: the average may not be a whole number.
        """,
        reference="""
            int count_above_average(const int data[], int size)
            {
                double sum = 0;
                for (int i = 0; i < size; i++) {
                    sum += data[i];
                }
                double avg = sum / size;
                int count = 0;
                for (int i = 0; i < size; i++) {
                    if (data[i] > avg) {
                        count++;
                    }
                }
                return count;
            }
        """)


# --------------------------------------------------------------- pointers

@template("pointers", 2, "c")
def c_min_max(rng):
    return _c(
        title="Minimum and maximum", function="min_max", returns="void",
        params=[_arr(src="list[int(-99..99)](1..12)"), _size(),
                {"name": "min", "type": "int*"}, {"name": "max", "type": "int*"}],
        prompt="""
            Write the function `min_max` that finds the smallest and largest elements of
            `data` and stores them in the variables pointed to by `min` and `max`.
            `size` is always at least 1.
        """,
        reference="""
            void min_max(const int data[], int size, int *min, int *max)
            {
                *min = data[0];
                *max = data[0];
                for (int i = 1; i < size; i++) {
                    if (data[i] < *min) *min = data[i];
                    if (data[i] > *max) *max = data[i];
                }
            }
        """)


@template("pointers", 2, "c")
def c_sort3(rng):
    return _c(
        title="Sort three values", function="sort3", returns="void",
        params=[{"name": "a", "type": "int*", "input": "int(-9..9)"},
                {"name": "b", "type": "int*", "input": "int(-9..9)"},
                {"name": "c", "type": "int*", "input": "int(-9..9)"}],
        edge_cases=[[3, 2, 1], [1, 1, 0], [5, 5, 5]],
        prompt="""
            Write the function `sort3` that rearranges the three integers pointed to by
            `a`, `b` and `c` so that afterwards `*a <= *b <= *c`.
        """,
        reference="""
            static void swap_ints(int *x, int *y)
            {
                int t = *x;
                *x = *y;
                *y = t;
            }

            void sort3(int *a, int *b, int *c)
            {
                if (*a > *b) swap_ints(a, b);
                if (*b > *c) swap_ints(b, c);
                if (*a > *b) swap_ints(a, b);
            }
        """)


@template("pointers", 3, "c")
def c_split_time(rng):
    return _c(
        title="Split seconds into h:m:s", function="split_time", returns="void",
        params=[{"name": "total_seconds", "type": "int", "input": "int(0..200000)"},
                {"name": "hours", "type": "int*"}, {"name": "minutes", "type": "int*"},
                {"name": "seconds", "type": "int*"}],
        edge_cases=[[0], [59], [60], [3599], [3600]],
        prompt="""
            Write the function `split_time` that converts `total_seconds` into hours,
            minutes and seconds (minutes and seconds each between 0 and 59) and stores
            them through the pointers `hours`, `minutes` and `seconds`.
        """,
        reference="""
            void split_time(int total_seconds, int *hours, int *minutes, int *seconds)
            {
                *hours = total_seconds / 3600;
                *minutes = (total_seconds % 3600) / 60;
                *seconds = total_seconds % 60;
            }
        """)


# -------------------------------------------------------- functions/loops

@template("functions", 1, "c")
def c_is_prime(rng):
    return _c(
        title="Is it prime?", function="is_prime", returns="int",
        params=[{"name": "n", "type": "int", "input": "int(0..200)"}],
        edge_cases=[[0], [1], [2], [3], [4], [97], [121]],
        num_tests=16,
        prompt="""
            Write the function `is_prime` that returns `1` if `n` is a prime number and
            `0` otherwise. Remember that 0 and 1 are not prime.
        """,
        reference="""
            int is_prime(int n)
            {
                if (n < 2) return 0;
                for (int d = 2; d * d <= n; d++) {
                    if (n % d == 0) return 0;
                }
                return 1;
            }
        """)


@template("loops", 1, "c")
def c_sum_digits(rng):
    return _c(
        title="Sum of digits", function="sum_digits", returns="int",
        params=[{"name": "n", "type": "int", "input": "int(0..999999)"}],
        edge_cases=[[0], [7], [10]],
        prompt="""
            Write the function `sum_digits` that returns the sum of the decimal digits of
            the non-negative integer `n`. For example, `sum_digits(4096)` is `19`.
        """,
        reference="""
            int sum_digits(int n)
            {
                int sum = 0;
                while (n > 0) {
                    sum += n % 10;
                    n /= 10;
                }
                return sum;
            }
        """)


@template("loops", 2, "c")
def c_gcd(rng):
    return _c(
        title="Greatest common divisor", function="gcd", returns="int",
        params=[{"name": "a", "type": "int", "input": "int(1..500)"},
                {"name": "b", "type": "int", "input": "int(1..500)"}],
        edge_cases=[[12, 18], [7, 13], [9, 9]],
        prompt="""
            Write the function `gcd` that returns the greatest common divisor of the
            positive integers `a` and `b`.
        """,
        reference="""
            int gcd(int a, int b)
            {
                while (b != 0) {
                    int r = a % b;
                    a = b;
                    b = r;
                }
                return a;
            }
        """)


@template("loops", 2, "c")
def c_series_sum(rng):
    return _c(
        title="Harmonic series", function="harmonic", returns="double",
        params=[{"name": "n", "type": "int", "input": "int(1..50)"}],
        edge_cases=[[1], [2]],
        prompt="""
            Write the function `harmonic` that returns the sum
            `1 + 1/2 + 1/3 + ... + 1/n` as a `double` (`n >= 1`).
        """,
        reference="""
            double harmonic(int n)
            {
                double sum = 0.0;
                for (int i = 1; i <= n; i++) {
                    sum += 1.0 / i;
                }
                return sum;
            }
        """)


# ------------------------------------------------------------ conditionals

@template("conditionals", 1, "c")
def c_shipping_cost(rng):
    w1 = rng.choice([1, 2])
    w2 = w1 + rng.choice([3, 4, 5])
    c1 = rng.choice([5.0, 6.5, 7.25])
    c2 = c1 + rng.choice([4.0, 5.5])
    rate = rng.choice([1.5, 2.0, 2.25])
    return _c(
        title="Shipping cost", function="shipping_cost", returns="double",
        params=[{"name": "weight", "type": "double", "input": "float(0..15)"}],
        edge_cases=[[float(w1)], [float(w2)], [w1 + 0.01], [w2 + 1.0]],
        prompt=f"""
            A courier charges by package weight (kg): **{c1:.2f}** dollars for packages up to
            and including {w1} kg, **{c2:.2f}** dollars for packages over {w1} kg up to and
            including {w2} kg, and above {w2} kg it charges {c2:.2f} dollars plus
            **{rate:.2f}** dollars for every kg over {w2} (fractions count proportionally).
            Write `shipping_cost` that returns the cost for a package of the given weight.
        """,
        reference=f"""
            double shipping_cost(double weight)
            {{
                if (weight <= {w1}) {{
                    return {c1};
                }} else if (weight <= {w2}) {{
                    return {c2};
                }} else {{
                    return {c2} + {rate} * (weight - {w2});
                }}
            }}
        """)


@template("conditionals", 2, "c")
def c_days_in_month(rng):
    return _c(
        title="Days in a month", function="days_in_month", returns="int",
        params=[{"name": "month", "type": "int", "input": "int(1..12)"},
                {"name": "year", "type": "int", "input": "choice(1900|2000|2023|2024|2100|1996)"}],
        edge_cases=[[2, 2024], [2, 1900], [2, 2000], [2, 2023], [4, 2024], [12, 2023]],
        num_tests=16,
        prompt="""
            Write `days_in_month` that returns the number of days in the given `month`
            (1 = January ... 12 = December) of the given `year`. February has 29 days in a
            leap year: a year divisible by 4, except years divisible by 100 unless they
            are also divisible by 400.
        """,
        reference="""
            int days_in_month(int month, int year)
            {
                if (month == 2) {
                    int leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
                    return leap ? 29 : 28;
                }
                if (month == 4 || month == 6 || month == 9 || month == 11) {
                    return 30;
                }
                return 31;
            }
        """)


# ---------------------------------------------------------------- strings

@template("strings", 1, "c")
def c_count_char(rng):
    return _c(
        title="Count a character", function="count_char", returns="int",
        params=[{"name": "str", "type": "const char[]", "input": "str(0..20, abcde)"},
                {"name": "ch", "type": "char", "input": 'choice("a"|"b"|"e"|"z")'}],
        prompt="""
            Write `count_char` that returns how many times the character `ch` appears in
            the null-terminated string `str`.
        """,
        reference="""
            int count_char(const char str[], char ch)
            {
                int count = 0;
                for (int i = 0; str[i] != '\\0'; i++) {
                    if (str[i] == ch) count++;
                }
                return count;
            }
        """)


@template("strings", 2, "c")
def c_to_upper(rng):
    return _c(
        title="Convert to upper case", function="to_upper_case", returns="void",
        params=[{"name": "str", "type": "char[]", "input": "str(0..16, text)"}],
        constraints={"forbid_builtins": ["toupper"]},
        prompt="""
            Write `to_upper_case` that converts every lowercase letter in the
            null-terminated string `str` to uppercase, **in place**. Other characters are
            unchanged. Do not use `toupper` -- use the fact that `'a' - 'A'` is the
            distance between lowercase and uppercase letters.
        """,
        reference="""
            void to_upper_case(char str[])
            {
                for (int i = 0; str[i] != '\\0'; i++) {
                    if (str[i] >= 'a' && str[i] <= 'z') {
                        str[i] = str[i] - 'a' + 'A';
                    }
                }
            }
        """)


@template("strings", 2, "c")
def c_is_palindrome(rng):
    return _c(
        title="Palindrome check", function="is_palindrome", returns="int",
        params=[{"name": "str", "type": "const char[]", "input": "str(1..6, ab)"}],
        edge_cases=[["a"], ["abba"], ["abcba"], ["ab"], ["racecar"]],
        prompt="""
            Write `is_palindrome` that returns `1` if the null-terminated string `str`
            reads the same forwards and backwards, and `0` otherwise. You may use
            `strlen` (include `<string.h>`).
        """,
        reference="""
            #include <string.h>

            int is_palindrome(const char str[])
            {
                int i = 0, j = (int)strlen(str) - 1;
                while (i < j) {
                    if (str[i] != str[j]) return 0;
                    i++;
                    j--;
                }
                return 1;
            }
        """)


# -------------------------------------------------------------- 2D arrays

@template("2d_arrays", 2, "c")
def c_column_sum(rng):
    return _c(
        title="Column sum", function="column_sum", returns="int",
        params=[{"name": "grid", "type": "const int[][4]", "input": "grid[int(-9..9)](1..5, 4..4)"},
                {"name": "rows", "type": "int", "rows_of": "grid"},
                {"name": "col", "type": "int", "input": "int(0..3)"}],
        prompt="""
            `grid` is a 2D array with `rows` rows and 4 columns. Write `column_sum` that
            returns the sum of the values in column `col` (0-based).
        """,
        reference="""
            int column_sum(const int grid[][4], int rows, int col)
            {
                int sum = 0;
                for (int r = 0; r < rows; r++) {
                    sum += grid[r][col];
                }
                return sum;
            }
        """)


@template("2d_arrays", 2, "c")
def c_max_row(rng):
    return _c(
        title="Row with the largest sum", function="max_row", returns="int",
        params=[{"name": "grid", "type": "const int[][5]", "input": "grid[int(-9..9)](1..6, 5..5)"},
                {"name": "rows", "type": "int", "rows_of": "grid"}],
        prompt="""
            `grid` is a 2D array with `rows` rows and 5 columns. Write `max_row` that
            returns the index of the row whose elements have the largest sum (the first
            such row if there is a tie).
        """,
        reference="""
            int max_row(const int grid[][5], int rows)
            {
                int best = 0, best_sum = 0;
                for (int r = 0; r < rows; r++) {
                    int sum = 0;
                    for (int c = 0; c < 5; c++) sum += grid[r][c];
                    if (r == 0 || sum > best_sum) {
                        best = r;
                        best_sum = sum;
                    }
                }
                return best;
            }
        """)


# ------------------------------------------------------- whole programs (io)

@template("io", 1, "c")
def c_prog_sum_average(rng):
    return _c(
        kind="program", title="Sum and average", topic="io",
        inputs={"nums": "list[int(-100..100)](1..10)"},
        stdin="{len:nums}\n{nums}\n",
        prompt="""
            Write a complete program that reads a positive integer `n` followed by `n`
            integers (using `scanf`) and prints exactly two lines:

            ```
            Sum = <sum>
            Average = <average with 2 decimal places>
            ```

            Do not print any prompts.
        """,
        reference="""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {
                int n, x, sum = 0;
                scanf("%d", &n);
                for (int i = 0; i < n; i++) {
                    scanf("%d", &x);
                    sum += x;
                }
                printf("Sum = %d\\n", sum);
                printf("Average = %.2f\\n", (double)sum / n);
                return 0;
            }
        """)


@template("loops", 1, "c")
def c_prog_triangle(rng):
    ch = rng.choice(["*", "#", "+"])
    return _c(
        kind="program", title="Print a triangle",
        inputs={"n": "int(1..9)"},
        stdin="{n}\n",
        prompt=f"""
            Write a program that reads a positive integer `n` and prints a right triangle
            of `{ch}` characters with `n` rows: row 1 has one `{ch}`, row 2 has two, and so
            on. No spaces, no prompts. For `n = 3`:

            ```
            {ch}
            {ch}{ch}
            {ch}{ch}{ch}
            ```
        """,
        reference=f"""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {{
                int n;
                scanf("%d", &n);
                for (int row = 1; row <= n; row++) {{
                    for (int i = 0; i < row; i++) {{
                        printf("{ch}");
                    }}
                    printf("\\n");
                }}
                return 0;
            }}
        """)


@template("conditionals", 1, "c")
def c_prog_largest(rng):
    return _c(
        kind="program", title="Largest of three",
        inputs={"a": "int(-50..50)", "b": "int(-50..50)", "c": "int(-50..50)"},
        stdin="{a} {b} {c}\n",
        edge_cases=[[5, 5, 1], [1, 5, 5], [-3, -3, -3]],
        prompt="""
            Write a program that prints `Enter three integers: `, reads three integers,
            then prints `Largest: <value>` on its own line. Example run (input `3 9 2`):

            ```
            Enter three integers: Largest: 9
            ```

            (The input you type does not appear in the output.)
        """,
        reference="""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {
                int a, b, c;
                printf("Enter three integers: ");
                scanf("%d %d %d", &a, &b, &c);
                int largest = a;
                if (b > largest) largest = b;
                if (c > largest) largest = c;
                printf("Largest: %d\\n", largest);
                return 0;
            }
        """)


@template("loops", 2, "c")
def c_prog_sentinel(rng):
    return _c(
        kind="program", title="Sentinel-controlled loop",
        inputs={"nums": "list[int(0..100)](0..10)"},
        stdin="{nums} -1\n",
        prompt="""
            Write a program that reads non-negative integers until it reads `-1` (the
            sentinel, which is not part of the data). Then print

            ```
            Count: <how many values were read>
            Maximum: <largest value>
            ```

            If no values were entered before `-1`, print only `No data`. No prompts.
        """,
        reference="""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {
                int x, count = 0, max = 0;
                scanf("%d", &x);
                while (x != -1) {
                    if (count == 0 || x > max) max = x;
                    count++;
                    scanf("%d", &x);
                }
                if (count == 0) {
                    printf("No data\\n");
                } else {
                    printf("Count: %d\\n", count);
                    printf("Maximum: %d\\n", max);
                }
                return 0;
            }
        """)


@template("loops", 2, "c")
def c_prog_temperature_table(rng):
    return _c(
        kind="program", title="Temperature table",
        inputs={"start": "int(-20..0)", "stop": "int(0..40)", "step": "int(1..10)"},
        stdin="{start} {stop} {step}\n",
        prompt="""
            Write a program that reads three integers `start`, `stop` and `step` and prints
            a Celsius-to-Fahrenheit table: one line for each Celsius value `start`,
            `start + step`, `start + 2*step`, ... as long as the value is `<= stop`.
            Each line looks like `-5 C = 23.0 F` (Fahrenheit with 1 decimal place,
            F = C * 9 / 5 + 32). No prompts.
        """,
        reference="""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {
                int start, stop, step;
                scanf("%d %d %d", &start, &stop, &step);
                for (int c = start; c <= stop; c += step) {
                    printf("%d C = %.1f F\\n", c, c * 9.0 / 5.0 + 32.0);
                }
                return 0;
            }
        """)


@template("io", 1, "c")
def c_prog_circle(rng):
    return _c(
        kind="program", title="Circle area and circumference",
        inputs={"r": "float(0..50)"},
        stdin="{r}\n",
        prompt="""
            Write a program that prints `Enter the radius: `, reads a radius (a `double`,
            use `%lf`), and prints

            ```
            Area: <area>
            Circumference: <circumference>
            ```

            both with 2 decimal places. Use `#define PI 3.14159265358979`.
        """,
        reference="""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>
            #define PI 3.14159265358979

            int main(void)
            {
                double r;
                printf("Enter the radius: ");
                scanf("%lf", &r);
                printf("Area: %.2f\\n", PI * r * r);
                printf("Circumference: %.2f\\n", 2 * PI * r);
                return 0;
            }
        """)
