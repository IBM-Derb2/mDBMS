# Mini DBMS by IBM Derb2

> Yes, mDBMS from scratch.
>
> <br>

<p align="center">
    <img width="600px" src="https://github.com/user-attachments/assets/9eb1b38b-474c-4197-8754-d137893dd712">
</p>


<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/DBMS-active-green?logo=databricks&logoColor=white" alt="DBMS"/>
  <img src="https://img.shields.io/badge/Custom-module-orange?logo=gear&logoColor=white" alt="Custom"/>
</p>

---

# Table of Contents <a name="table-of-contents"></a>

- [Description](#description)
- [Technology](#technology)
- [Requirements](#requirements)
- [Running the mDBMS](#running-the-mdbms)
- [Creators](#creators)

---

# The mDBMS <a name="mdbms"></a>

<div align="center">

<img src="https://github.com/user-attachments/assets/1e174a4d-b1da-4724-8e20-9212799b16ca" width="100%" alt="cover">

</div>

---

# Description <a name="description"></a>

This project is a mini Database Management System (DBMS) implemented with Python with the following functionalities:

## 1. Query Processor

Query processor is the component responsible for handling query execution. It must be able to interact and coordinate with other components for queries to be executed properly. The Query Processor handles 5 types of queries:

- **Transaction Control**: `BEGIN TRANSACTION`, `COMMIT`, `ROLLBACK`
- **Concurrency Control**: `SET CONCURRENCY` (lock-based, timestamp-based, validation-based, multi-version)
- **Standard Queries**: `SELECT`, `UPDATE`, `DELETE`, `INSERT`, `CREATE TABLE`, `DROP TABLE`
- **Query Clauses**: `FROM`, `JOIN`, `WHERE`, `ORDER BY`, `LIMIT`, `AS`

The `execute_query()` method is the main method that receives a query from the user and returns an ExecutionResult object containing the requested data or a message. It transforms queries into tree structures using the query optimizer's `parse_query()` and `optimize_query()` methods, then processes each node recursively.

## 2. Query Optimizer

Query optimizer performs parsing, optimization, and cost calculation for query execution:

### Parse Query

Transforms SQL query strings into structured `ParsedQuery` objects through:

- **Tokenization**: Breaking SQL strings into tokens (lexical analysis)
- **Parsing**: Analyzing tokens to determine parser type (syntax analysis)
  - `DDLParser`: CREATE, DROP, BEGIN, COMMIT
  - `DMLParser`: SELECT, INSERT, UPDATE, DELETE
  - `ExpressionParser`: WHERE, arithmetic, logical expressions

### Optimize Query

Implements **Rule-Based Optimization** using relational algebra rules iteratively until convergence:

1. **DistributionRule (Priority 1)**: Push operations down

   - **Selection Pushdown**: Move WHERE conditions closer to source tables
   - **Projection Pushdown**: Only retrieve necessary columns

2. **SelectionRule (Priority 2)**: Optimize selections

   - Convert Cartesian Product + WHERE to Theta Join
   - Decompose conjunctive selections (AND conditions)
   - Reorder selections by selectivity

3. **ProjectionRule (Priority 3)**: Eliminate redundant projections

   - Reduce processed columns to save memory and I/O

4. **JoinRule (Priority 4)**: Optimize join order
   - Join smallest tables first to minimize intermediate results

### Get Cost

The `calculate_cost()` method implements recursive tree traversal to estimate query execution costs by mapping each node type to appropriate cost formulas using statistics from Storage Manager.

**Implementation Limitation**: Data types are limited to INT, FLOAT, CHAR, and VARCHAR.

## 3. Concurrency Control Manager

Manages query scheduling and transaction concurrency to ensure correct and consistent execution when transactions run concurrently.

### Key Methods

- `begin_transaction()`: Generate unique transaction ID with format `{ip}:{port}-{timestamp}-{counter}`
- `log_object()`: Record objects in transactions for lock/timestamp assignment
- `validate_object()`: Validate if an object is allowed to perform specific actions
- `commit_transaction()`: Commit transaction and make all changes permanent
- `abort_transaction()`: Cancel transaction and perform rollback via Failure Recovery Manager
- `set_concurrency_mechanism()`: Switch between concurrency control strategies

### Concurrency Strategies

1. **Lock-Based Strategy**: Uses Shared/Exclusive locks with Two-Phase Locking (2PL)

   - Deadlock prevention: Wound-Wait or Wait-Die schemes
   - Timeout mechanism: 5 seconds

2. **Timestamp-Based Strategy**: Uses timestamp ordering to serialize transactions

   - Aborts transactions that violate timestamp order

3. **Validation-Based Strategy**: Optimistic Concurrency Control (OCC)

   - Validates conflicts at commit time

4. **Multi-Version Strategy**: MVCC with snapshot isolation
   - Each transaction sees consistent snapshot
   - First-committer-wins for writes

### ACID Properties

- **Atomicity**: WAL integration with FRM for all-or-nothing transactions
- **Consistency**: State transition validation and unique transaction IDs
- **Isolation**: Strategy-specific isolation (Serializability or Snapshot Isolation)
- **Durability**: Write-Ahead Logging and checkpoints for crash recovery

### Deadlock Management

- **Detection**: Wait-For Graph with DFS cycle detection
- **Resolution**: Youngest transaction selected as victim
- **Prevention**: Wound-Wait, Wait-Die schemes, and timeout mechanism

## 4. Storage Manager

Manages physical data storage operations and provides services to other components.

### Architecture

- **StorageEngine**: Handles block read/write, deletion, indexing, and table statistics
- **Serializer**: Converts data between Python format and binary (1024-byte blocks)
- **Indexing**: HashIndex and BPlusTreeIndex for fast data access

### Operations

**Read Block**:

- Index-based reading using HashIndex/BPlusTreeIndex for optimized access
- Full table scan with deserialization when index unavailable
- Combines disk data with buffer from FRM for transaction visibility
- Applies WHERE conditions and column projections

**Write Block**:

- **INSERT**: Validates primary key uniqueness, writes to buffer via BufferManager
- **UPDATE**: Combines disk and buffer data, evaluates expressions, updates via buffer
- Follows write-ahead logging mechanism

**Delete Block**:

- Reads from disk and buffer, marks matching rows as deleted in buffer
- Supports transaction rollback through FRM undo mechanism

**Indexing**:

- `set_index()`: Builds HashIndex or BPlusTreeIndex on specified columns
- Persistent storage allows reloading for optimized queries

**Table Statistics**: Provides metadata for query optimization cost calculations

## 5. Failure Recovery

Ensures database consistency and durability through crash recovery and transaction rollback:

- **Write-Ahead Logging (WAL)**: All operations logged before execution
- **Buffer Manager**: Manages in-memory buffer pool with WAL rules
- **Checkpoint**: Saves system state with active transaction list
- **Recovery**:
  - REDO committed transactions
  - UNDO uncommitted transactions
  - Restore consistent state after crash
- **Rollback**: Uses undo logs to revert transaction changes

---

# Technology <a name="technology"></a>

- **Python 3.10+**
- Uses only **standard Python libraries** (no external dependencies)

---

# Requirements <a name="requirements"></a>

- **Python 3.10 or higher** installed
- A terminal or command prompt to run the scripts
- No additional packages or libraries required

---

# Running the mDBMS <a name="running-the-mdbms"></a>

1. Make executable scripts

   ```bash
   chmod +x sclient.sh
   chmod +x sserver.sh
   ```

2. Run Client and Server

   On a terminal start the server:

   ```bash
   ./sserver.sh
   ```

   and in a different terminal than server, run client:

   ```bash
   ./sclient.sh
   ```

3. Start running commands on Client

   A. Do query

   ```sql
   IBM-Derb2> SELECT * FROM attends;
   IBM-Derb2> SELECT * FROM student s, attends a WHERE s.studentid = a.studentid ORDER BY gpa ASC LIMIT 10;
   ```

   B. Do Transaction

   ```sql
   IBM-Derb2> BEGIN TRANSACTION;
   IBM-Derb2> UPDATE student SET GPA = 0.0 WHERE StudentID = 13520001;
   IBM-Derb2> ROLLBACK; -- or COMMIT
   ```

   C. Exit

   ```bash
   IBM-Derb2> exit
   ```

---

# Creators <a name="creators"></a>

### <p align="center"><i>~ Super Group IBM Derb2 ~</i></p>

<br>

### Swift Group - Query Processor

<table>
    <tr align="left">
        <td><b>NIM</b></td>
        <td><b>Name</b></td>
        <td align="center"><b>GitHub</b></td>
        <td><b>Responsibilities</b></td>
    </tr>
    <tr align="left">
        <td>13519024</td>
        <td>M Hilal Alhamdy</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/hilalhmdy" >
                <img src="https://avatars.githubusercontent.com/u/68505934?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @hilalhmdy </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Laporan</td>
    </tr>
    <tr align="left">
        <td>13523118</td>
        <td>Farrel Athalla Putra</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/farrelathalla" >
                <img src="https://avatars.githubusercontent.com/u/130957219?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @farrelathalla </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Inisialisasi program, Integrasi program, fungsi execute_query, fungsi meng-handle query DML, debugging, testing</td>
    </tr>
    <tr align="left">
        <td>13523022</td>
        <td>Kenneth Ricardo Chandra</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/KennethRicardoC" >
                <img src="https://avatars.githubusercontent.com/u/166089884?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @KennethRicardoC </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Integrasi program, fungsi meng-handle transaction, fungsi memproses node query join, debugging, testing, laporan</td>
    </tr>
    <tr align="left">
        <td>13523060</td>
        <td>Angelina Efrina Prahastaputri</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/angelinaefrina" >
                <img src="https://avatars.githubusercontent.com/u/153846022?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @angelinaefrina </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Integrasi program, fungsi memproses node query select, fungsi meng-handle kondisi from, debugging, testing, laporan</td>
    </tr>
    <tr align="left">
        <td>13523112</td>
        <td>Aria Judhistira</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/TukangLas21" >
                <img src="https://avatars.githubusercontent.com/u/167204304?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @TukangLas21 </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Kelas diagram, integrasi program, fungsi meng-handle rollback, fungsi meng-handle commit, debugging, testing, laporan</td>
    </tr>
</table>

### Kotlin Group - Storage Manager

<table>
    <tr align="left">
        <td><b>NIM</b></td>
        <td><b>Name</b></td>
        <td align="center"><b>GitHub</b></td>
        <td><b>Responsibilities</b></td>
    </tr>
    <tr align="left">
        <td>13523078</td>
        <td>Anella Utari Gunadi</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/anellautari" >
                <img src="https://avatars.githubusercontent.com/u/166348291?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @anellautari </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Laporan, refactor data folder,
StorageEngine read_block(), class DataRetrieval, fixing write_blocks(), UnitTest.py, _create_table(), _delete_table(),</td>
    </tr>
    <tr align="left">
        <td>13523006</td>
        <td>William Andrian Dharma T</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/kirisame-ame" >
                <img src="https://avatars.githubusercontent.com/u/156988122?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @kirisame-ame </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Laporan, StorageEngine _evaluate_expression(), get_stats(), class Statistics,
UnitTest.py, Interface untuk BufferManager</td>
    </tr>
    <tr align="left">
        <td>13523004</td>
        <td>Razi Rachman Widyadhana</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/zirachw" >
                <img src="https://avatars.githubusercontent.com/u/148220821?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @zirachw </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Laporan, Integrasi dengan komponen lain, Skeleton client.py dan server.py, StorageEngine write_block(), class DataWrite, Serializer, Rows, Condition, UnitTest.py</td>
    </tr>
    <tr align="left">
        <td>13523096</td>
        <td>Muhammad Edo Raduputu Aprima</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/poetoeee" >
                <img src="https://avatars.githubusercontent.com/u/153411701?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @poetoeee </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Laporan, Diagram class, StorageEngine delete_block(), class DataDeletion, UnitTest.py</td>
    </tr>
    <tr align="left">
        <td>13523100</td>
        <td>Aryo Wisanggeni</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/Staryo40" >
                <img src="https://avatars.githubusercontent.com/u/139449070?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @Staryo40 </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Laporan, index.py,
StorageEngine set_index(),
_update_indexes(),
b_plus_tree_index.py, hash_index.py,</td>
    </tr>
</table>

### Java Group - Concurrency Control Manager

<table>
    <tr align="left">
        <td><b>NIM</b></td>
        <td><b>Name</b></td>
        <td align="center"><b>GitHub</b></td>
        <td><b>Responsibilities</b></td>
    </tr>
    <tr align="left">
        <td>13523018</td>
        <td>Raka Daffa Iftikhaar</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/rakdaf08" >
                <img src="https://avatars.githubusercontent.com/u/195661877?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @rakdaf08 </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Mengerjakan komponen ACID properties, transaction lifecycle, concurrency-control, dan thread safety.</td>
    </tr>
    <tr align="left">
        <td>13523038</td>
        <td>Abrar Abhirama Widyadhana</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/Abrar-Abhirama" >
                <img src="https://avatars.githubusercontent.com/u/184033072?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @Abrar-Abhirama </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Mengerjakan log untuk setiap objek, merancang struktur kelas/folder komponen, rollback, abort dan integrasi</td>
    </tr>
    <tr align="left">
        <td>13523008</td>
        <td>Varel Tiara</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/varel183" >
                <img src="https://avatars.githubusercontent.com/u/163633131?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @varel183 </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Mengerjakan bagian validate object, undo log, prevent deadlock dan membuat class diagram dan deskripsinya.</td>
    </tr>
    <tr align="left">
        <td>13523058</td>
        <td>Noumisyifa Nabila Nareswari</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/numshv" >
                <img src="https://avatars.githubusercontent.com/u/149067096?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @numshv </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Mengerjakan bagian manage end transaction dan bikin unit test.</td>
    </tr>
</table>

### Haskell Group - Failure Recovery

<table>
    <tr align="left">
        <td><b>NIM</b></td>
        <td><b>Name</b></td>
        <td align="center"><b>GitHub</b></td>
        <td><b>Responsibilities</b></td>
    </tr>
    <tr align="left">
        <td>13523014</td>
        <td>Nicholas Andhika Lucas</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/andhikalucas" >
                <img src="https://avatars.githubusercontent.com/u/164333795?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @andhikalucas </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Bagian model log parser dan log entry, recovery, logika rollback, unit testing, dan laporan</td>
    </tr>
    <tr align="left">
        <td>13523016</td>
        <td>Clarissa Nethania Tambunan</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/4clarissaNT4" >
                <img src="https://avatars.githubusercontent.com/u/199760631?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @4clarissaNT4  </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Bagian buffer manager dan implementasi aturan write ahead log di buffer manager, diagram kelas, dan laporan</td>
    </tr>
    <tr align="left">
        <td>13523102</td>
        <td>Michael Alexander Angkawijaya</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/angkaberapa" >
                <img src="https://avatars.githubusercontent.com/u/163782592?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @angkaberapa </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Save checkpoint, Integrasi dengan storage manager, clear WAL logic, testing, dan laporan</td>
    </tr>
    <tr align="left">
        <td>13523042</td>
        <td>Abdullah Farhan</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/Farhanabd05" >
                <img src="https://avatars.githubusercontent.com/u/163700293?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @Farhanabd05 </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Integrasi menjadi satu kelas, testing dan refactor buffer manager dan recovery, integrasi dengan komponen lain, dan laporan</td>
    </tr>
</table>

### Elixir Group - Query Optimizer

<table>
    <tr align="left">
        <td><b>NIM</b></td>
        <td><b>Name</b></td>
        <td align="center"><b>GitHub</b></td>
        <td><b>Responsibilities</b></td>
    </tr>
    <tr align="left">
        <td>13523036</td>
        <td>Yonatan Edward Njoto</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/yonatan-nyo" >
                <img src="https://avatars.githubusercontent.com/u/113841843?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @yonatan-nyo </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Inisialisasi global types dan constants, merge, tree parser, tokenizer, internal get_cost, cost integration, optimizer</td>
    </tr>
    <tr align="left">
        <td>13523082</td>
        <td>Aramazaya</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/Aramazaya" >
                <img src="https://avatars.githubusercontent.com/u/166960944?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @Aramazaya </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Refactor cost dengan global types dan constants, bagian awal dari get_cost</td>
    </tr>
    <tr align="left">
        <td>13523080</td>
        <td>Diyah Susan Nugrahani</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/DiyahSusan" >
                <img src="https://avatars.githubusercontent.com/u/162612711?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @DiyahSusan </b></sub>
            </a><br/>
            </div>
        </td>
        <td>Parse_query test and fix, push selection and push projection, refactor optimization, laporan</td>
    </tr>
    <tr align="left">
        <td>13523106</td>
        <td>Athian Nugraha Muarajuang</td>
        <td align="center" >
            <div style="margin-right: 20px;">
            <a href="https://github.com/Starath" >
                <img src="https://avatars.githubusercontent.com/u/164960528?v=4" width="48px;" alt=""/>
                <br/> <sub><b> @Starath </b></sub>
            </a><br/>
            </div>
        </td>
        <td>DML test and fix, refactor parsers, diagram class, laporan.</td>
    </tr>
</table>
