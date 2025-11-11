# Berkas: Concurrency_Control_Manager/test_log_object.py
#
# Ini adalah skrip untuk MENGUJI log_object SECARA TERISOLASI.
#
# Cara menjalankan:
# 1. Pastikan Anda berada di direktori mDBMS/ (satu level DI ATAS)
# 2. Jalankan: python -m Concurrency_Control_Manager.test_log_object
#
# (Perhatikan tanda titik di depan 'lib' di import berikut)
from .lib.lock_based_strategy import LockBasedStrategy, LockEntry

# Kita perlu "objek" data palsu untuk diuji
class DummyRow:
    def __init__(self, id):
        self.id = id
    def __repr__(self):
        # Ini akan digunakan oleh _get_object_id()
        return f"Row(id={self.id})"

print("--- MEMULAI TES UNIT UNTUK log_object ---")

# Buat objek data palsu kita
obj_A = DummyRow(id=101)
obj_B = DummyRow(id=102)

# ID Transaksi palsu
T1 = 1
T2 = 2

# 1. Buat instance dari strategi Anda
strategy = LockBasedStrategy()
print("\n[Inisialisasi] Lock table awal:", strategy.lock_table)


# ==========================================================
# SKENARIO 1: Menerapkan WRITE Lock (Eksklusif)
# ==========================================================
print("\n--- SKENARIO 1: WRITE Lock ---")
print(f"Menguji: T1 me-log 'write' pada {obj_A}")
strategy.log_object(obj_A, T1, 'write')

# Cek Hasilnya
print("Lock Table Sekarang:", strategy.lock_table)
# Tes Otomatis (Assertion)
assert strategy.lock_table['Row(id=101)'].lock_type == 'write'
assert strategy.lock_table['Row(id=101)'].holders == {T1}
print("✅ Tes 1 Lulus!")


# ==========================================================
# SKENARIO 2: Menerapkan READ Lock (Baru)
# ==========================================================
print("\n--- SKENARIO 2: READ Lock (Baru) ---")
print(f"Menguji: T1 me-log 'read' pada {obj_B}")
strategy.log_object(obj_B, T1, 'read')

# Cek Hasilnya
print("Lock Table Sekarang:", strategy.lock_table)
# Tes Otomatis (Assertion)
assert strategy.lock_table['Row(id=102)'].lock_type == 'read'
assert strategy.lock_table['Row(id=102)'].holders == {T1}
print("✅ Tes 2 Lulus!")


# ==========================================================
# SKENARIO 3: Menerapkan READ Lock (Shared)
# ==========================================================
print("\n--- SKENARIO 3: READ Lock (Shared) ---")
print(f"Menguji: T2 me-log 'read' pada {obj_B} (yang sudah di-lock T1)")
strategy.log_object(obj_B, T2, 'read')

# Cek Hasilnya
print("Lock Table Sekarang:", strategy.lock_table)
# Tes Otomatis (Assertion)
assert strategy.lock_table['Row(id=102)'].lock_type == 'read'
assert strategy.lock_table['Row(id=102)'].holders == {T1, T2} # Harusnya ada T1 dan T2
print("✅ Tes 3 Lulus!")


# ==========================================================
# SKENARIO 4: READ Lock oleh pemegang WRITE Lock
# ==========================================================
print("\n--- SKENARIO 4: READ oleh Pemegang WRITE ---")
print(f"Menguji: T1 (pemegang WRITE) me-log 'read' pada {obj_A}")
strategy.log_object(obj_A, T1, 'read')

# Cek Hasilnya (Seharusnya tidak berubah)
print("Lock Table Sekarang:", strategy.lock_table)
# Tes Otomatis (Assertion)
assert strategy.lock_table['Row(id=101)'].lock_type == 'write' # Harus tetap WRITE
assert strategy.lock_table['Row(id=101)'].holders == {T1}
print("✅ Tes 4 Lulus!")

print("\n--- SEMUA TES log_object LULUS! ---")