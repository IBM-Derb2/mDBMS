# Query Optimizer Unit Test Results

Test run date: 2025-11-20 20:45:23

---

## CostCalculatorTests.test_internal_get_cost_rejects_raw_query_strings

**Description:** Test Internal Get Cost Rejects Raw Query Strings

**Goal:** Verify the behavior of CostCalculatorTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users'}

**Expected Output:** {'error': 'TypeError'}

**Results:** Pass

---

## DistributionRuleTests.test_distribution_rule_apply_preserves_join_structure

**Description:** Test Distribution Rule Apply Preserves Join Structure

**Goal:** Verify the behavior of DistributionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'PAID'"}

**Expected Output:** {'join_count': 1, 'root_type': 'SELECT'}

**Results:** Pass

---

## DistributionRuleTests.test_distribution_rule_detects_selection_over_join

**Description:** Test Distribution Rule Detects Selection Over Join

**Goal:** Verify the behavior of DistributionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'PAID'"}

**Expected Output:** {'can_apply': True}

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

## InternalParseQueryTests.test_parse_select_creates_where_branch

**Description:** Test Parse Select Creates Where Branch

**Goal:** Verify the behavior of InternalParseQueryTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users WHERE id = 10'}

**Expected Output:** {'where_count': 1}

**Results:** Pass

---

## OptimizationEngineTests.test_optimize_query_converts_cartesian_product_to_join

**Description:** Test Optimize Query Converts Cartesian Product To Join

**Goal:** Verify the behavior of OptimizationEngineTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users u, orders o WHERE u.id = o.user_id'}

**Expected Output:** {'join_count': 1, 'from_child_type': 'JOIN'}

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

## SelectionRuleTests.test_selection_rule_converts_cartesian_product_into_join

**Description:** Test Selection Rule Converts Cartesian Product Into Join

**Goal:** Verify the behavior of SelectionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users u, orders o WHERE u.id = o.user_id'}

**Expected Output:** {'join_count': 1, 'from_child_type': 'JOIN'}

**Results:** Pass

---

## SelectionRuleTests.test_selection_rule_detects_applicability

**Description:** Test Selection Rule Detects Applicability

**Goal:** Verify the behavior of SelectionRuleTests

**Method:** Unit test

**Success Criterion:** Test passes without assertion errors

**Input:** {'query': 'SELECT * FROM users u, orders o WHERE u.id = o.user_id'}

**Expected Output:** {'can_apply': True}

**Results:** Pass

---
