from serializer import Serializer
from storage_engine import StorageEngine
import random

# Create StorageEngine with serializer and specify dummy_data directory
storage_engine = StorageEngine(data_dir="dummy_data", serializer=Serializer())


schema_student = {
    "table_name": "student",
    "columns": [
        {"name": "StudentID", "type": "int"},
        {"name": "FullName", "type": "varchar", "length": 50},
        {"name": "GPA", "type": "float"}
    ]
}

schema_course = {
    "table_name": "course",
    "columns": [
        {"name": "CourseID", "type": "int"},
        {"name": "Year", "type": "int"},
        {"name": "CourseName", "type": "varchar", "length": 50},
        {"name": "CourseDescription", "type": "varchar", "length": 255}
    ]
}

schema_attends = {
    "table_name": "attends",
    "columns": [
        {"name": "StudentID", "type": "int"},
        {"name": "CourseID", "type": "int"},
        {"name": "Year", "type": "int"},
    ]
}


students = [
    {
        "StudentID": i,
        "FullName": f"Student_{i}",
        "GPA": round(random.uniform(2.0, 4.0), 2)
    }
    for i in range(1, 51)
]

courses = [
    {
        "CourseID": i,
        "Year": random.choice([2023, 2024, 2025]),
        "CourseName": f"Course_{i}",
        "CourseDescription": f"This is a description for course {i}. It covers topic {random.randint(1,10)} and includes several exercises."
    }
    for i in range(1, 51)
]

attends = [
    {
        "StudentID": random.randint(1, 50),
        "CourseID": random.randint(1, 50),
        "Year": random.choice([2023, 2024, 2025])
    }
    for _ in range(50)
]


# Use StorageEngine to write schema and data files
for schema, data in [
    (schema_student, students),
    (schema_course, courses),
    (schema_attends, attends)
]:
    storage_engine.write_schema_file(schema)
    storage_engine.write_data_file(schema["table_name"], data, schema)

print("Dummy data berhasil dibuat di folder Storage_Manager/data/dummy_data/")
