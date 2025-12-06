# Optimizer Test Results

**Test Run Date:** 2025-12-06 16:50:16

---

## Optimizer Tests

### Simple Query

**Query:**
```sql
SELECT * FROM users WHERE id = 1
```

> ⚠️ **Tree was NOT modified - no optimizations applied**

#### Before Optimization

- **Estimated Cost:** 82,000
- **Estimated Rows:** 1,000

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ RELATION = 'users'
  └─ OPERATOR = '='
    ├─ COLUMN = 'id'
    └─ LITERAL = '1'
```

#### After Optimization

- **Estimated Cost:** 82,000
- **Estimated Rows:** 1,000

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ RELATION = 'users'
  └─ OPERATOR = '='
    ├─ COLUMN = 'id'
    └─ LITERAL = '1'
```

#### Optimization Results

| Metric | Before | After | Difference | Improvement |
|--------|--------|-------|------------|-----------|
| **Cost** | 82,000 | 82,000 | 0 | 0.00% |
| **Rows** | 1,000 | 1,000 | 0 | - |

---

### Cartesian Product to Theta Join

**Query:**
```sql
SELECT * FROM users u, orders o WHERE u.id = o.user_id
```

> ✅ **Tree was modified by optimizer**

#### Before Optimization

- **Estimated Cost:** 13,200,550,000
- **Estimated Rows:** 100,000,000

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ CROSS_JOIN
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    └─ ALIAS = 'o'
      └─ RELATION = 'orders'
  └─ OPERATOR = '='
    ├─ COLUMN = 'u.id'
    └─ COLUMN = 'o.user_id'
```

#### After Optimization

- **Estimated Cost:** 1,316,000
- **Estimated Rows:** 8,000

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ THETA_JOIN
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    ├─ ALIAS = 'o'
      └─ RELATION = 'orders'
    └─ OPERATOR = '='
      ├─ COLUMN = 'u.id'
      └─ COLUMN = 'o.user_id'
  └─ OPERATOR = '='
    ├─ COLUMN = 'u.id'
    └─ COLUMN = 'o.user_id'
```

#### Optimization Results

| Metric | Before | After | Difference | Improvement |
|--------|--------|-------|------------|-----------|
| **Cost** | 13,200,550,000 | 1,316,000 | 13,199,234,000 | 99.99% |
| **Rows** | 100,000,000 | 8,000 | 99,992,000 | - |

---

### Selection Pushdown

**Query:**
```sql
SELECT * FROM users WHERE age > 18
```

> ⚠️ **Tree was NOT modified - no optimizations applied**

#### Before Optimization

- **Estimated Cost:** 86,600
- **Estimated Rows:** 3,300

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ RELATION = 'users'
  └─ OPERATOR = '>'
    ├─ COLUMN = 'age'
    └─ LITERAL = '18'
```

#### After Optimization

- **Estimated Cost:** 86,600
- **Estimated Rows:** 3,300

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ RELATION = 'users'
  └─ OPERATOR = '>'
    ├─ COLUMN = 'age'
    └─ LITERAL = '18'
```

#### Optimization Results

| Metric | Before | After | Difference | Improvement |
|--------|--------|-------|------------|-----------|
| **Cost** | 86,600 | 86,600 | 0 | 0.00% |
| **Rows** | 3,300 | 3,300 | 0 | - |

---

### Multiple Conditions

**Query:**
```sql
SELECT * FROM users u, orders o 
        WHERE u.id = o.user_id 
        AND u.status = 'ACTIVE' 
        AND o.total > 100
```

> ✅ **Tree was modified by optimizer**

#### Before Optimization

- **Estimated Cost:** 13,007,150,000
- **Estimated Rows:** 3,300,000

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ CROSS_JOIN
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    └─ ALIAS = 'o'
      └─ RELATION = 'orders'
  └─ OPERATOR = 'AND'
    ├─ OPERATOR = 'AND'
      ├─ OPERATOR = '='
        ├─ COLUMN = 'u.id'
        └─ COLUMN = 'o.user_id'
      └─ OPERATOR = '='
        ├─ COLUMN = 'u.status'
        └─ LITERAL = 'ACTIVE'
    └─ OPERATOR = '>'
      ├─ COLUMN = 'o.total'
      └─ LITERAL = '100'
```

#### After Optimization

- **Estimated Cost:** 1,300,528
- **Estimated Rows:** 264

**Tree Structure:**
```
PROJECTION = ['*']
└─ SELECTION_STMT
  ├─ THETA_JOIN
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    ├─ ALIAS = 'o'
      └─ RELATION = 'orders'
    └─ OPERATOR = '='
      ├─ COLUMN = 'u.id'
      └─ COLUMN = 'o.user_id'
  └─ OPERATOR = 'AND'
    ├─ OPERATOR = 'AND'
      ├─ OPERATOR = '='
        ├─ COLUMN = 'u.id'
        └─ COLUMN = 'o.user_id'
      └─ OPERATOR = '='
        ├─ COLUMN = 'u.status'
        └─ LITERAL = 'ACTIVE'
    └─ OPERATOR = '>'
      ├─ COLUMN = 'o.total'
      └─ LITERAL = '100'
```

#### Optimization Results

| Metric | Before | After | Difference | Improvement |
|--------|--------|-------|------------|-----------|
| **Cost** | 13,007,150,000 | 1,300,528 | 13,005,849,472 | 99.99% |
| **Rows** | 3,300,000 | 264 | 3,299,736 | - |

---

### Complex Join

**Query:**
```sql
SELECT u.name, o.total 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        WHERE o.status = 'PAID' 
        AND u.age >= 18
```

> ⚠️ **Tree was NOT modified - no optimizations applied**

#### Before Optimization

- **Estimated Cost:** 1,305,280
- **Estimated Rows:** 2,640

**Tree Structure:**
```
PROJECTION = ['u.name', 'o.total']
└─ SELECTION_STMT
  ├─ THETA_JOIN = 'INNER'
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    ├─ ALIAS = 'o'
      └─ RELATION = 'orders'
    └─ OPERATOR = '='
      ├─ COLUMN = 'u.id'
      └─ COLUMN = 'o.user_id'
  └─ OPERATOR = 'AND'
    ├─ OPERATOR = '='
      ├─ COLUMN = 'o.status'
      └─ LITERAL = 'PAID'
    └─ OPERATOR = '>='
      ├─ COLUMN = 'u.age'
      └─ LITERAL = '18'
```

#### After Optimization

- **Estimated Cost:** 1,305,280
- **Estimated Rows:** 2,640

**Tree Structure:**
```
PROJECTION = ['u.name', 'o.total']
└─ SELECTION_STMT
  ├─ THETA_JOIN = 'INNER'
    ├─ ALIAS = 'u'
      └─ RELATION = 'users'
    ├─ ALIAS = 'o'
      └─ RELATION = 'orders'
    └─ OPERATOR = '='
      ├─ COLUMN = 'u.id'
      └─ COLUMN = 'o.user_id'
  └─ OPERATOR = 'AND'
    ├─ OPERATOR = '='
      ├─ COLUMN = 'o.status'
      └─ LITERAL = 'PAID'
    └─ OPERATOR = '>='
      ├─ COLUMN = 'u.age'
      └─ LITERAL = '18'
```

#### Optimization Results

| Metric | Before | After | Difference | Improvement |
|--------|--------|-------|------------|-----------|
| **Cost** | 1,305,280 | 1,305,280 | 0 | 0.00% |
| **Rows** | 2,640 | 2,640 | 0 | - |

---

