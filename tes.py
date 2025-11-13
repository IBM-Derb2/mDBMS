from Query_Optimizer.optimization_engine import OptimizationEngine

if __name__ == "__main__":

    # TESTING untuk parser poin 8-14
    q8 = "BEGIN TRANSACTION;"
    q9 = "COMMIT;"
    q10 = "DELETE FROM employee WHERE department = 'RnD';"
    q11 = "INSERT INTO users (id, name) VALUES (101, 'Ahmad');"
    q12 = "CREATE TABLE employees (id integer PRIMARY KEY, name varchar(100), code char(4), salary float, dept_id integer, FOREIGN KEY (dept_id) REFERENCES departments(id));"
    q13 = "DROP TABLE users;"
    q14 = "SELECT id AS user_id, name AS user_name FROM users;"
    # buat instance dari parser
    parser = OptimizationEngine()

    # panggil fungsi parse_query
    parsed_result = parser.parse_query(q14)

    print(parsed_result)
