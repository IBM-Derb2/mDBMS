import time
import os
import statistics
from storage_engine import StorageEngine
from serializer import Serializer
from utils import DataRetrieval, Condition

ITERATIONS = 100
TABLE_NAME = "student"
COLUMN_NAME = "FullName"
TARGET_NAME = "Student_5000" # (range 1-10000)

def measure_execution(storage, dr, label, iterations=1):
    times = []
    results_count = 0
    
    print(f"   Running {label} ({iterations}x)... ", end="", flush=True)
    
    for _ in range(iterations):
        start = time.perf_counter()
        res = storage.read_block(dr)
        end = time.perf_counter()
        
        times.append((end - start) * 1000) 
        results_count = res.rows_count
    
    return {
        "label": label,
        "avg": statistics.mean(times),
        "min": min(times),
        "max": max(times),
        "total_found": results_count
    }

def print_stats(stats):
    print(f"   -> Rata-rata : {stats['avg']:.4f} ms")
    print(f"   -> Tercepat  : {stats['min']:.4f} ms")
    print(f"   -> Terlambat : {stats['max']:.4f} ms")
    print(f"   -> Data Found: {stats['total_found']} rows")

def run_benchmark():
    print("="*60)
    print("       STORAGE ENGINE BENCHMARK: LINEAR vs INDEX")
    print("="*60)
    
    serializer = Serializer()
    storage = StorageEngine(serializer=serializer)
    
    data_path = f"data/{TABLE_NAME}.dat"
    if not os.path.exists(data_path):
        print(f"ERROR: File data '{data_path}' tidak ditemukan.")
        print("   Jalankan 'python Storage_Manager/generate_dummy_data.py' terlebih dahulu!")
        return

    print(f"Target Table  : {TABLE_NAME}")
    print(f"Target Column : {COLUMN_NAME}")
    print(f"Target Value  : '{TARGET_NAME}'")
    print(f"Iterations    : {ITERATIONS} kali per metode")
    print("-" * 60)

    condition = [Condition(column=COLUMN_NAME, operation="=", operand=TARGET_NAME)]

    # ==========================================
    # TEST 1: LINEAR SCAN
    # ==========================================
    print("\n[1] MENGUJI LINEAR SCAN (Full Scan)")
    dr_linear = DataRetrieval(
        table=TABLE_NAME,
        column=["*"],
        conditions=condition,
        search_type="linear"
    )
    
    stats_linear = measure_execution(storage, dr_linear, "Linear Scan", ITERATIONS)
    print_stats(stats_linear)

    # ==========================================
    # TEST 2: CREATE INDEX
    # ==========================================
    print("\n[2] MEMBUAT INDEX (Setup)")
    idx_file = f"data/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
    
    # Hapus index lama jika ada agar pengukuran 'create' valid
    if os.path.exists(idx_file):
        os.remove(idx_file)
        
    start_idx = time.perf_counter()
    storage.set_index(TABLE_NAME, COLUMN_NAME, "hash")
    end_idx = time.perf_counter()
    
    print(f"   -> Index dibuat dalam: {(end_idx - start_idx)*1000:.4f} ms")
    if os.path.exists(idx_file):
        size_kb = os.path.getsize(idx_file) / 1024
        print(f"   -> Ukuran File Index : {size_kb:.2f} KB")
    else:
        print("Gagal membuat file index!")
        return

    # ==========================================
    # TEST 3: INDEX SCAN
    # ==========================================
    print("\n[3] MENGUJI INDEX SCAN (Random Access)")
    dr_index = DataRetrieval(
        table=TABLE_NAME,
        column=["*"],
        conditions=condition,
        search_type="index",
        index_column=COLUMN_NAME
    )
    
    stats_index = measure_execution(storage, dr_index, "Index Scan", ITERATIONS)
    print_stats(stats_index)

    # ==========================================
    # KESIMPULAN
    # ==========================================
    print("\n" + "="*60)
    print("                   HASIL AKHIR")
    print("="*60)
    
    # Validasi Kebenaran Data
    if stats_linear["total_found"] == stats_index["total_found"]:
        print("VALIDASI DATA : SUKSES (Hasil kedua metode konsisten)")
    else:
        print("VALIDASI DATA : GAGAL (Jumlah data yang ditemukan berbeda!)")
        print(f"   Linear: {stats_linear['total_found']}, Index: {stats_index['total_found']}")

    print("-" * 60)
    print(f"{'Metode':<15} | {'Rata-rata (ms)':<15} | {'Min (ms)':<15}")
    print("-" * 60)
    print(f"{'Linear Scan':<15} | {stats_linear['avg']:<15.4f} | {stats_linear['min']:<15.4f}")
    print(f"{'Index Scan':<15} | {stats_index['avg']:<15.4f} | {stats_index['min']:<15.4f}")
    print("-" * 60)

    # Hitung Speedup
    if stats_index['avg'] > 0:
        speedup = stats_linear['avg'] / stats_index['avg']
        if speedup > 1:
            print(f"KESIMPULAN: Index Scan {speedup:.2f}x LEBIH CEPAT dari Linear Scan.")
        else:
            print(f"KESIMPULAN: Index Scan lebih lambat ({speedup:.2f}x). Overhead mungkin terlalu besar.")
    
if __name__ == "__main__":
    run_benchmark()