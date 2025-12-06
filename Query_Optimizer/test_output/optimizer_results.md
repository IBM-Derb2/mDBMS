# Optimizer Test Results

**Test Run Date:** 2025-12-06 15:40:43

---

## Optimizer Tests

### Query Cost Analysis

| Query | Cost |
|-------|------|
| `SELECT * FROM users...` | 70000.00 |
| `SELECT * FROM users WHERE id = 1...` | 82000.00 |
| `SELECT * FROM users u JOIN orders o ON u.id = o.us...` | 1220000.00 |
| `SELECT * FROM users, orders WHERE users.id = order...` | 13200550000.00 |

