from typing import List
import struct
import re

class Serializer:
    def __init__(self) -> None:
        self.block_size = 1024
        pass

    def deserialize_with_blocks(self, binary_data: bytes, columns: List[dict]) -> list:
        """
        desisialisasi data biner dengan alokasi blok menjadi baris.

        Args:
            binary_data (bytes): Data biner dengan alokasi blok.
            columns List(dict): Kamus skema dengan nama kolom dan tipe data.

        Returns:
            list: Daftar baris yang sudah dide-serial-kan dalam bentuk dictionary.
        """

        block_size = 1024
        row_size = 0
        offsets = []

        for column in columns:
            if column["type"] == "int":
                offsets.append((column["name"], row_size, 4))
                row_size += 4
            elif column["type"] == "varchar":
                length = column.get("length")
                offsets.append((column["name"], row_size, length+1))
                row_size += length+1
            elif column["type"] == "float":
                offsets.append((column["name"], row_size, 8))
                row_size += 8
            elif column["type"] == "char":
                length = column.get("length")
                offsets.append((column["name"], row_size, length+1))
                row_size += length+1

        rows = []
        for i in range(0, len(binary_data), block_size):
            current_block = binary_data[i:i+block_size]
            for j in range(0, len(current_block), row_size):
                row_data = current_block[j:j+row_size]
                if len(row_data) < row_size:
                    break
                row = {}
                for column_name, offset, length in offsets:
                    if length == 4:
                        row[column_name] = int.from_bytes(row_data[offset:offset+4], byteorder='big')
                    elif length == 8:
                        row[column_name] = struct.unpack('d', row_data[offset:offset+8])[0]
                    else:
                        marker = row_data[offset]
                        if marker == 1:  # varchar
                            row[column_name] = row_data[offset+1:offset+length].decode('utf-8').rstrip('\x00')
                        elif marker == 2:  # char
                            char_data = row_data[offset+1:offset+length]
                            row[column_name] = ''.join(chr(b) if b != 0 else ' ' for b in char_data)
                        else:
                            row[column_name] = None  # fallback
                rows.append(row)
        
        return rows
    
    def serialize_with_blocks(self, rows: list, column: dict) -> bytes:
        """
        serialisasi baris-baris data menjadi data biner dengan alokasi blok.

        Args:
            rows (list): Daftar baris (dictionary) yang akan diserialisasi.
            column (dict): Skema tabel dengan nama kolom dan tipe data.
            block_size (int): Ukuran tetap setiap blok dalam byte.

        Returns:
            bytes: Data biner yang mewakili baris-baris dengan alokasi blok.
        """

        block_size = 1024
        binary_data = bytearray()
        current_block = bytearray(block_size)
        current_block_size = 0
        row_size = 0
        offsets = []

        for column in column["columns"]:
            if column["type"] == "int":
                offsets.append((column["name"], "int", row_size, 4))
                row_size += 4
            elif column["type"] == "varchar":
                length = column.get("length", 20)
                offsets.append((column["name"], "varchar", row_size, length))
                row_size += length
            elif column["type"] == "float":
                offsets.append((column["name"], "float", row_size, 8))
                row_size += 8
            elif column["type"] == "char":
                length = column.get("length", 20)
                offsets.append((column["name"], "char", row_size, length))
                row_size += length
            else:
                raise ValueError(f"Tipe kolom tidak didukung: {column['type']}")
        
        
        # binary_data = b""
        for row in rows:
            row_binary = bytearray()
            for column_name, column_type, offset, length in offsets:
                if column_type == "int":
                    row_binary += int(row[column_name]).to_bytes(4, byteorder="big")
                elif column_type == "varchar":
                    row_binary += b'\x01'  # penanda untuk varchar
                    row_binary += row[column_name].encode().ljust(length, b"\x00")
                elif column_type == "float":
                    row_binary += struct.pack('d', row[column_name])
                elif column_type == "char":
                    row_binary += b'\x02'  # penanda untuk char
                    row_binary += row[column_name].encode().ljust(length, b"\x00")
                else:
                    raise ValueError(f"Tipe kolom tidak didukung: {column_type}")

            if current_block_size + len(row_binary) > block_size:
                binary_data.extend(current_block)
                current_block = bytearray(block_size)
                current_block_size = 0

            current_block[current_block_size:current_block_size+len(row_binary)] = row_binary
            current_block_size += len(row_binary)

        binary_data.extend(current_block[:current_block_size])
        return bytes(binary_data)

    def serialize_schema(self, schema: List[dict]) -> bytes:
        """
        serialisasi skema tabel menjadi data biner.

        Args:
            schema (dict): Skema tabel dengan nama tabel dan kolom.
            contoh:
            schema_users = {
                "table_name": "users",
                "columns": [
                    {"name": "id", "type": "int"},
                    {"name": "nama", "type": "varchar", "length": 20},
                    {"name": "umur", "type": "int"}
                ]
            }

        Returns:
            bytes: Data biner yang mewakili skema tabel.
        """

        binary_data = bytearray()

        # nama tabel
        table_name = schema["table_name"]
        binary_data.extend(table_name.encode('utf-8'))
        binary_data.append(0)  # Null terminator

        # kolom
        for column in schema["columns"]:
            # nama kolom
            column_name = column["name"]
            binary_data.extend(column_name.encode('utf-8'))
            binary_data.append(0)  # Null terminator

            # tipe kolom
            column_type = column["type"]
            binary_data.extend(column_type.encode('utf-8'))
            binary_data.append(0)  # Null terminator

            # panjang varchar jika tipe kolom adalah varchar
            if column_type == "varchar" or column_type == "char":
                length = column["length"]
                binary_data.extend(length.to_bytes(1, byteorder="big"))

        return bytes(binary_data)

    def deserialize_schema(self, binary_data: bytes) -> list[dict]:
        """
        deserialisasi data biner menjadi skema tabel.

        Args:
            binary_data (bytes): Data biner yang mewakili skema tabel.
            isi dari binary data:
            namatabel, null
            dilanjutkan dengan:
            namakolom, tipekolom
            jika tipekolom = varchar maka akan menjadi:
            namakolom, varchar, panjangvarchar

        Returns:
            dict: Skema tabel dengan nama tabel dan kolom.
        """
        
        i = 0

        # nama tabel
        table_name_end = binary_data.index(b"\x00", i)
        table_name = binary_data[i:table_name_end].decode('utf-8')
        i = table_name_end + 1

        columns = []

        while i < len(binary_data):
            column = {}

            # nama kolom
            name_end = binary_data.index(b"\x00", i)
            column["name"] = binary_data[i:name_end].decode('utf-8')
            i = name_end + 1

            # tipe kolom
            type_end = binary_data.index(b"\x00", i)
            column["type"] = binary_data[i:type_end].decode('utf-8')
            i = type_end + 1

            # panjang varchar jika tipe kolom adalah varchar
            if column["type"] == "varchar" or column["type"] == "char":
                column["length"] = int.from_bytes(binary_data[i:i+1], byteorder="big")
                i += 1

            columns.append(column)

        return {
            "table_name": table_name,
            "columns": columns
        }
        
    def convert_to_operation(self, value: list):
        # as example [2, "*", "umur"] will be converted to string "2 * umur"
        pattern = re.compile(r'\d+|\+|\-|\*|\/|\(|\)')
        
        # Join the list into string
        operation = ' '.join(map(str, value))
        
        return operation