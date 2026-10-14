"""File I/O templates (APSC 160 C, plus one Python). Registered on import.

Input files are rendered fresh for every test from `file_data`; `output_files`
are graded too; `missing_file_test` adds a test where the input file doesn't exist.
"""
from .c_problems import _c
from .problems import _spec, template


@template("file_io", 1, "c")
def c_file_sum(rng):
    return _c(
        kind="program", title="Sum the numbers in a file",
        file_data={"values": "list[int(-50..100)](0..12)"},
        input_files={"data.txt": "{lines:values}\n"},
        missing_file_test=True,
        prompt="""
            The file `data.txt` contains integers, one per line (it may be empty). Write a
            program that reads every integer in the file (use `fscanf` until it stops
            returning 1) and prints

            ```
            Count: <how many integers>
            Sum: <their sum>
            Average: <average with 2 decimal places>
            ```

            If the file is empty, print only `No data`. If `data.txt` cannot be opened,
            print `Error: could not open data.txt` and end the program. Close the file when
            you are done.
        """,
        reference="""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {
                FILE *in = fopen("data.txt", "r");
                if (in == NULL) {
                    printf("Error: could not open data.txt\\n");
                    return 1;
                }
                int x, count = 0, sum = 0;
                while (fscanf(in, "%d", &x) == 1) {
                    count++;
                    sum += x;
                }
                fclose(in);
                if (count == 0) {
                    printf("No data\\n");
                } else {
                    printf("Count: %d\\n", count);
                    printf("Sum: %d\\n", sum);
                    printf("Average: %.2f\\n", (double)sum / count);
                }
                return 0;
            }
        """)


@template("file_io", 2, "c")
def c_file_grade_report(rng):
    cutoff = rng.choice([50, 55, 60])
    return _c(
        kind="program", title="Grade report file",
        file_data={"scores": "list[int(0..100)](1..10)"},
        input_files={"grades.txt": "{len:scores}\n{lines:scores}\n"},
        output_files=["report.txt"],
        missing_file_test=True,
        prompt=f"""
            `grades.txt` starts with the number of students `n`, followed by `n` scores, one
            per line. Write a program that creates `report.txt` containing one line per
            student, numbered from 1:

            ```
            Student 1: 73 PASS
            Student 2: 41 FAIL
            ```

            A score of **{cutoff}** or more is a pass. After writing the file, print
            `Passed: <p> of <n>` to the screen. If `grades.txt` cannot be opened, print
            `Error opening grades.txt` and do not create `report.txt`. Close both files.
        """,
        reference=f"""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {{
                FILE *in = fopen("grades.txt", "r");
                if (in == NULL) {{
                    printf("Error opening grades.txt\\n");
                    return 1;
                }}
                FILE *out = fopen("report.txt", "w");
                int n, score, passed = 0;
                fscanf(in, "%d", &n);
                for (int i = 1; i <= n; i++) {{
                    fscanf(in, "%d", &score);
                    if (score >= {cutoff}) {{
                        fprintf(out, "Student %d: %d PASS\\n", i, score);
                        passed++;
                    }} else {{
                        fprintf(out, "Student %d: %d FAIL\\n", i, score);
                    }}
                }}
                fclose(in);
                fclose(out);
                printf("Passed: %d of %d\\n", passed, n);
                return 0;
            }}
        """)


@template("file_io", 2, "c")
def c_file_count_above(rng):
    return _c(
        title="Count values above a threshold in a file", function="count_above", returns="int",
        params=[{"name": "filename", "type": "const char[]", "input": 'choice("values.txt")'},
                {"name": "threshold", "type": "int", "input": "int(0..60)"}],
        file_data={"values": "list[int(0..100)](0..15)"},
        input_files={"values.txt": "{values}\n"},
        missing_file_test=True,
        prompt="""
            Write the function `count_above` that opens the file named `filename`, reads all
            of the integers in it (separated by spaces), and returns how many are **strictly
            greater** than `threshold`. If the file cannot be opened, return `-1`.
            Remember to close the file.
        """,
        reference="""
            int count_above(const char filename[], int threshold)
            {
                FILE *in = fopen(filename, "r");
                if (in == NULL) {
                    return -1;
                }
                int x, count = 0;
                while (fscanf(in, "%d", &x) == 1) {
                    if (x > threshold) count++;
                }
                fclose(in);
                return count;
            }
        """)


@template("file_io", 2, "c")
def c_file_write_table(rng):
    return _c(
        title="Write a table to a file", function="write_table", returns="int",
        params=[{"name": "filename", "type": "const char[]", "input": 'choice("table.txt")'},
                {"name": "n", "type": "int", "input": "int(0..12)"}],
        output_files=["table.txt"],
        prompt="""
            Write the function `write_table` that creates the file named `filename` and
            writes `n` lines to it. Line `i` (for `i` from 1 to `n`) contains `i`, `i*i` and
            `i*i*i` separated by single spaces, e.g. `3 9 27`. Return the number of lines
            written, or `-1` if the file could not be opened. Close the file before returning.
        """,
        reference="""
            int write_table(const char filename[], int n)
            {
                FILE *out = fopen(filename, "w");
                if (out == NULL) {
                    return -1;
                }
                for (int i = 1; i <= n; i++) {
                    fprintf(out, "%d %d %d\\n", i, i * i, i * i * i);
                }
                fclose(out);
                return n;
            }
        """)


@template("file_io", 3, "c")
def c_file_number_lines(rng):
    return _c(
        kind="program", title="Number the lines of a file",
        file_data={"text": "list[sentence(1..5)](0..8)"},
        input_files={"input.txt": "{lines:text}\n"},
        output_files=["numbered.txt"],
        missing_file_test=True,
        prompt="""
            Each line of `input.txt` holds a few words (at most 100 characters). Write a
            program that copies it to `numbered.txt`, putting the line number, a colon and a
            space in front of every line (`1: the first line`). Then print
            `Lines: <count>`. Use `fgets` to read whole lines. If `input.txt` cannot be
            opened, print `Cannot open input.txt`.
        """,
        reference="""
            #define _CRT_SECURE_NO_WARNINGS
            #include <stdio.h>

            int main(void)
            {
                char line[101];
                FILE *in = fopen("input.txt", "r");
                if (in == NULL) {
                    printf("Cannot open input.txt\\n");
                    return 1;
                }
                FILE *out = fopen("numbered.txt", "w");
                int count = 0;
                while (fgets(line, sizeof line, in) != NULL) {
                    count++;
                    fprintf(out, "%d: %s", count, line);
                }
                fclose(in);
                fclose(out);
                printf("Lines: %d\\n", count);
                return 0;
            }
        """)


@template("file_io", 2, "python")
def py_file_word_counts(rng):
    return _spec(
        title="Word counts from a file", function="count_words",
        inputs={"filename": 'choice("words.txt")'},
        file_data={"lines": "list[sentence(1..6)](0..8)"},
        input_files={"words.txt": "{lines:lines}\n"},
        output_files=["counts.txt"],
        missing_file_test=True,
        prompt="""
            Write `count_words(filename)`. It reads the text file `filename` and writes a
            file named `counts.txt` with one line per line of the input: the number of
            words on that line. It returns the total number of words. If `filename` does
            not exist, return `-1` and don't create `counts.txt`.
        """,
        reference="""
            def count_words(filename):
                try:
                    with open(filename) as f:
                        lines = f.read().splitlines()
                except FileNotFoundError:
                    return -1
                total = 0
                with open("counts.txt", "w") as out:
                    for line in lines:
                        n = len(line.split())
                        out.write(f"{n}\\n")
                        total += n
                return total
        """)
