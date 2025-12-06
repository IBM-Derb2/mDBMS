# Tokenizer Test Results

**Test Run Date:** 2025-12-06 15:47:45

---

## Tokenizer Tests

### Sample Tokenizations

#### Query: `SELECT * FROM users`

**Tokens:**

| Type | Value | Position |
|------|-------|----------|
| KEYWORD | `SELECT` | 0 |
| OPERATOR | `*` | 7 |
| KEYWORD | `FROM` | 9 |
| IDENTIFIER | `users` | 14 |
| EOF | `` | 19 |

#### Query: `SELECT name, age FROM users WHERE age > 18`

**Tokens:**

| Type | Value | Position |
|------|-------|----------|
| KEYWORD | `SELECT` | 0 |
| IDENTIFIER | `name` | 7 |
| PUNCTUATION | `,` | 11 |
| IDENTIFIER | `age` | 13 |
| KEYWORD | `FROM` | 17 |
| IDENTIFIER | `users` | 22 |
| KEYWORD | `WHERE` | 28 |
| IDENTIFIER | `age` | 34 |
| OPERATOR | `>` | 38 |
| NUMBER | `18` | 40 |
| EOF | `` | 42 |

#### Query: `SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id`

**Tokens:**

| Type | Value | Position |
|------|-------|----------|
| KEYWORD | `SELECT` | 0 |
| IDENTIFIER | `u` | 7 |
| PUNCTUATION | `.` | 8 |
| IDENTIFIER | `name` | 9 |
| KEYWORD | `FROM` | 14 |
| IDENTIFIER | `users` | 19 |
| IDENTIFIER | `u` | 25 |
| KEYWORD | `JOIN` | 27 |
| IDENTIFIER | `orders` | 32 |
| IDENTIFIER | `o` | 39 |
| KEYWORD | `ON` | 41 |
| IDENTIFIER | `u` | 44 |
| PUNCTUATION | `.` | 45 |
| IDENTIFIER | `id` | 46 |
| OPERATOR | `=` | 49 |
| IDENTIFIER | `o` | 51 |
| PUNCTUATION | `.` | 52 |
| IDENTIFIER | `user_id` | 53 |
| EOF | `` | 60 |

