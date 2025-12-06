# Parser Test Results

**Test Run Date:** 2025-12-06 15:53:34

---

## Parser Tests

### Sample Parse Trees

#### Simple SELECT

**Query:** `SELECT * FROM users`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ RELATION = 'users'
```

#### SELECT with WHERE

**Query:** `SELECT * FROM users WHERE id = 1`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ SELECTION_STMT
    ├─ RELATION = 'users'
    └─ OPERATOR = '='
      ├─ COLUMN = 'id'
      └─ LITERAL = '1'
```

#### SELECT with Multiple Columns

**Query:** `SELECT name, age, email FROM users WHERE age > 18`

**Parse Tree Structure:**

```
PROJECTION = '['name', 'age', 'email']'
  └─ SELECTION_STMT
    ├─ RELATION = 'users'
    └─ OPERATOR = '>'
      ├─ COLUMN = 'age'
      └─ LITERAL = '18'
```

#### Basic JOIN

**Query:** `SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id`

**Parse Tree Structure:**

```
PROJECTION = '['u.name', 'o.total']'
  └─ THETA_JOIN = 'INNER'
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    ├─ ALIAS = 'o'
      └─ RELATION = 'orders'
    └─ OPERATOR = '='
      ├─ COLUMN = 'u.id'
      └─ COLUMN = 'o.user_id'
```

#### JOIN with WHERE

**Query:** `SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id WHERE o.total > 100`

**Parse Tree Structure:**

```
PROJECTION = '['u.name', 'o.total']'
  └─ SELECTION_STMT
    ├─ THETA_JOIN = 'INNER'
      ├─ ALIAS = 'u'
        └─ RELATION = 'users'
      ├─ ALIAS = 'o'
        └─ RELATION = 'orders'
      └─ OPERATOR = '='
        ├─ COLUMN = 'u.id'
        └─ COLUMN = 'o.user_id'
    └─ OPERATOR = '>'
      ├─ COLUMN = 'o.total'
      └─ LITERAL = '100'
```

#### JOIN with Complex ON

**Query:** `SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND u.status = 'ACTIVE'`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ THETA_JOIN = 'INNER'
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    ├─ ALIAS = 'o'
      └─ RELATION = 'orders'
    └─ OPERATOR = 'AND'
      ├─ OPERATOR = '='
        ├─ COLUMN = 'u.id'
        └─ COLUMN = 'o.user_id'
      └─ OPERATOR = '='
        ├─ COLUMN = 'u.status'
        └─ LITERAL = 'ACTIVE'
```

#### Self-Join

**Query:** `SELECT e1.name, e2.name FROM employees e1 JOIN employees e2 ON e1.manager_id = e2.id`

**Parse Tree Structure:**

```
PROJECTION = '['e1.name', 'e2.name']'
  └─ THETA_JOIN = 'INNER'
    ├─ ALIAS = 'e1'
      └─ RELATION = 'employees'
    ├─ ALIAS = 'e2'
      └─ RELATION = 'employees'
    └─ OPERATOR = '='
      ├─ COLUMN = 'e1.manager_id'
      └─ COLUMN = 'e2.id'
```

#### Multiple JOINs

**Query:** `SELECT u.name, o.total, p.name FROM users u JOIN orders o ON u.id = o.user_id JOIN products p ON o.product_id = p.id`

**Parse Tree Structure:**

```
PROJECTION = '['u.name', 'o.total', 'p.name']'
  └─ THETA_JOIN = 'INNER'
    ├─ THETA_JOIN = 'INNER'
      ├─ ALIAS = 'u'
        └─ RELATION = 'users'
      ├─ ALIAS = 'o'
        └─ RELATION = 'orders'
      └─ OPERATOR = '='
        ├─ COLUMN = 'u.id'
        └─ COLUMN = 'o.user_id'
    ├─ ALIAS = 'p'
      └─ RELATION = 'products'
    └─ OPERATOR = '='
      ├─ COLUMN = 'o.product_id'
      └─ COLUMN = 'p.id'
```

#### Cross Join (Implicit)

**Query:** `SELECT * FROM users, orders`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ CROSS_JOIN
    ├─ RELATION = 'users'
    └─ RELATION = 'orders'
```

#### Cross Join with WHERE

**Query:** `SELECT * FROM users, orders WHERE users.id = orders.user_id`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ SELECTION_STMT
    ├─ CROSS_JOIN
      ├─ RELATION = 'users'
      └─ RELATION = 'orders'
    └─ OPERATOR = '='
      ├─ COLUMN = 'users.id'
      └─ COLUMN = 'orders.user_id'
```

#### NATURAL JOIN

**Query:** `SELECT * FROM users NATURAL JOIN orders`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ NATURAL_JOIN
    ├─ RELATION = 'users'
    └─ RELATION = 'orders'
```

#### Complex WHERE with AND/OR

**Query:** `SELECT * FROM users WHERE (age > 18 AND status = 'ACTIVE') OR balance > 1000`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ SELECTION_STMT
    ├─ RELATION = 'users'
    └─ OPERATOR = 'OR'
      ├─ OPERATOR = 'AND'
        ├─ OPERATOR = '>'
          ├─ COLUMN = 'age'
          └─ LITERAL = '18'
        └─ OPERATOR = '='
          ├─ COLUMN = 'status'
          └─ LITERAL = 'ACTIVE'
      └─ OPERATOR = '>'
        ├─ COLUMN = 'balance'
        └─ LITERAL = '1000'
```

#### JOIN with Nested Conditions

**Query:** `SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND (o.status = 'ACTIVE' OR o.status = 'PENDING')`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ THETA_JOIN = 'INNER'
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    ├─ ALIAS = 'o'
      └─ RELATION = 'orders'
    └─ OPERATOR = 'AND'
      ├─ OPERATOR = '='
        ├─ COLUMN = 'u.id'
        └─ COLUMN = 'o.user_id'
      └─ OPERATOR = 'OR'
        ├─ OPERATOR = '='
          ├─ COLUMN = 'o.status'
          └─ LITERAL = 'ACTIVE'
        └─ OPERATOR = '='
          ├─ COLUMN = 'o.status'
          └─ LITERAL = 'PENDING'
```

#### Four Table JOIN

**Query:** `SELECT * FROM t1 JOIN t2 ON t1.id = t2.t1_id JOIN t3 ON t2.id = t3.t2_id JOIN t4 ON t3.id = t4.t3_id`

**Parse Tree Structure:**

```
PROJECTION = '['*']'
  └─ THETA_JOIN = 'INNER'
    ├─ THETA_JOIN = 'INNER'
      ├─ THETA_JOIN = 'INNER'
        ├─ RELATION = 't1'
        ├─ RELATION = 't2'
        └─ OPERATOR = '='
          ├─ COLUMN = 't1.id'
          └─ COLUMN = 't2.t1_id'
      ├─ RELATION = 't3'
      └─ OPERATOR = '='
        ├─ COLUMN = 't2.id'
        └─ COLUMN = 't3.t2_id'
    ├─ RELATION = 't4'
    └─ OPERATOR = '='
      ├─ COLUMN = 't3.id'
      └─ COLUMN = 't4.t3_id'
```

