class QueryTypes:
    # DDL (Data Definition Language)
    CREATE = "CREATE"
    CREATE_TABLE = "CREATE_TABLE"
    ALTER = "ALTER"
    DROP = "DROP"
    DROP_TABLE = "DROP_TABLE"
    TRUNCATE = "TRUNCATE"
    CONSTRAINT = "CONSTRAINT"
    DATA_TYPE = "DATA_TYPE"
    COLUMN_DEF = "COLUMN_DEF"
    COLUMN_DEFS = "COLUMN_DEFS"

    # DML (Data Manipulation Language)
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    MERGE = "MERGE"
    SET = "SET"
    VALUES = "VALUES"

    # Transaction Control
    BEGIN_TRANSACTION = "BEGIN_TRANSACTION"
    COMMIT = "COMMIT"

    # Clause keywords
    FROM = "FROM"
    WHERE = "WHERE"
    AS = "AS"
    GROUP = "GROUP"
    HAVING = "HAVING"
    ORDER = "ORDER"
    ORDER_BY = "ORDER_BY"
    ORDER_ITEM = "ORDER_ITEM"
    BY = "BY"
    ASC = "ASC"
    DESC = "DESC"
    LIMIT = "LIMIT"
    OFFSET = "OFFSET"
    UNION = "UNION"
    INTERSECT = "INTERSECT"
    EXCEPT = "EXCEPT"
    ALL = "ALL"
    DISTINCT = "DISTINCT"
    INTO = "INTO"
    ON = "ON"
    JOIN = "JOIN"
    CROSS_JOIN = "CROSS_JOIN"
    DROP_MODE = "DROP_MODE"

    # Node types (tree/AST)
    TABLE = "TABLE"
    COLUMN = "COLUMN"
    COLUMNS = "COLUMNS"
    IDENTIFIER = "IDENTIFIER"
    CONDITION = "CONDITION"
    COMPARISON = "COMPARISON"
    OPERATOR = "OPERATOR"
    LITERAL = "LITERAL"

    # Parser/test types
    ALIAS = "ALIAS"
    ASSIGNMENT = "ASSIGNMENT"

    PROJECT = "PROJECT"