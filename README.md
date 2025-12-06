# Mini DBMS by IBM Derb2

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/DBMS-active-green?logo=databricks&logoColor=white" alt="DBMS"/>
  <img src="https://img.shields.io/badge/Custom-module-orange?logo=gear&logoColor=white" alt="Custom"/>
</p>

## Table of Contents

- [Description](#description)
- [Technology](#technology)
- [Features](#features)
- [Requirements](#requirements)
- [Running the mDBMS](#Running-the-mdbms)
- [Creators](#creators)

---

# Description

This project is a mini Database Management System (DBMS) implemented with Python with the following functionalities:

1. Query Processing: SELECT FROM, UPDATE, JOIN ON, NATURAL JOIN, WHERE
2. Query Optimization
3. Storage Management
4. Failure Recovery
5. Concurrency Control

---

# Technology

- **Python 3.10+**
- Uses only **standard Python libraries** (no external dependencies)

---

# Requirements

- **Python 3.10 or higher** installed
- A terminal or command prompt to run the scripts
- No additional packages or libraries required

---

# Running the mDBMS

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
   IBM-Derb2> SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'PAID'
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

# Creators

## Super Group IBM Derb2

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
        <td>Inisialisasi global types dan constants, merge, tree parser, tokenizer, internal get_cost, cost integration</td>
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
