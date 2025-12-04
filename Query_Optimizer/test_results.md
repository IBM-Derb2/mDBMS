# Query Optimizer Unit Test Results

Test run date: 2025-12-03 15:31:58

---

## CostCalculatorTests.test_calculate_node_cost_uses_statistics

**Description:** Test Calculate Node Cost Uses Statistics

**Goal:** Verify the behavior of CostCalculatorTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users WHERE id = 1'}

**Expected Output:** {'total_cost': 82000}

**Results:** Pass

---

## CostCalculatorTests.test_get_cost_accepts_query_strings

**Description:** Test Get Cost Accepts Query Strings

**Goal:** Verify the behavior of CostCalculatorTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users'}

**Expected Output:** {'cost': 70000}

**Results:** Pass

---

## DistributionRuleTests.test_distribution_rule_structure

**Description:** Test Distribution Rule Structure

**Goal:** Verify the behavior of DistributionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'PAID'"}

**Expected Output:** {'theta_join_count': 1}

**Results:** Pass

---

## DistributionRuleTests.test_distribution_rule_with_theta_join

**Description:** Test Distribution Rule With Theta Join

**Goal:** Verify the behavior of DistributionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'PAID'"}

**Expected Output:** {'can_apply': False}

**Results:** Pass

---

## InternalParseQueryTests.test_parse_query_rejects_empty_string

**Description:** Test Parse Query Rejects Empty String

**Goal:** Verify the behavior of InternalParseQueryTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': '   '}

**Expected Output:** {'error': 'ValueError'}

**Results:** Pass

---

## InternalParseQueryTests.test_parse_select_creates_selection_stmt

**Description:** Test Parse Select Creates Selection Stmt

**Goal:** Verify the behavior of InternalParseQueryTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users WHERE id = 10'}

**Expected Output:** {'selection_count': 1}

**Results:** Pass

---

## OptimizationEngineTests.test_optimize_query_handles_cartesian_product

**Description:** Test Optimize Query Handles Cartesian Product

**Goal:** Verify the behavior of OptimizationEngineTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users u, orders o WHERE u.id = o.user_id'}

**Expected Output:** {'theta_joins': 0, 'cross_joins': 1}

**Results:** Pass

---

## OptimizationEngineTests.test_optimize_query_requires_parsed_query_instance

**Description:** Test Optimize Query Requires Parsed Query Instance

**Goal:** Verify the behavior of OptimizationEngineTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'parsed_query': None}

**Expected Output:** {'error': 'TypeError'}

**Results:** Pass

---

## OptimizationEngineTests.test_parse_query_invalid_keyword_raises_value_error

**Description:** Test Parse Query Invalid Keyword Raises Value Error

**Goal:** Verify the behavior of OptimizationEngineTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'RANDOM something'}

**Expected Output:** {'error': 'ValueError'}

**Results:** Pass

---

## OptimizationEngineTests.test_parse_query_returns_parsed_query_instance

**Description:** Test Parse Query Returns Parsed Query Instance

**Goal:** Verify the behavior of OptimizationEngineTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users'}

**Expected Output:** {'parsed_type': 'ParsedQuery'}

**Results:** Pass

---

## SQLTokenizerTests.test_tokenize_ignores_comments_and_captures_literals

**Description:** Test Tokenize Ignores Comments And Captures Literals

**Goal:** Verify the behavior of SQLTokenizerTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': "SELECT name, 'ACTIVE' as status -- inline comment\n\t\tFROM users /* block comment */\n\t\tWHERE age >= 18;"}

**Expected Output:** {'tokens': [('KEYWORD', 'SELECT'), ('IDENTIFIER', 'name'), ('PUNCTUATION', ','), ('STRING', 'ACTIVE'), ('KEYWORD', 'AS'), ('IDENTIFIER', 'status'), ('KEYWORD', 'FROM'), ('IDENTIFIER', 'users')]}

**Results:** Pass

---

## SQLTokenizerTests.test_tokenize_unclosed_string_raises_value_error

**Description:** Test Tokenize Unclosed String Raises Value Error

**Goal:** Verify the behavior of SQLTokenizerTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': "SELECT 'oops"}

**Expected Output:** {'error': 'ValueError'}

**Results:** Pass

---

## SelectionRuleTests.test_selection_rule_structure

**Description:** Test Selection Rule Structure

**Goal:** Verify the behavior of SelectionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users u, orders o WHERE u.id = o.user_id'}

**Expected Output:** {'cross_joins': 1, 'theta_joins': 0}

**Results:** Pass

---

## SelectionRuleTests.test_selection_rule_with_cross_join

**Description:** Test Selection Rule With Cross Join

**Goal:** Verify the behavior of SelectionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users u, orders o WHERE u.id = o.user_id'}

**Expected Output:** {'can_apply': False}

**Results:** Pass

---
