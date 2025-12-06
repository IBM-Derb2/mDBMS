import random

from Storage_Manager.storage_engine import StorageEngine
from Storage_Manager.serializer import Serializer

DATA_DIR = ""

print("\nSetup: Generating data")

random.seed(2025)
serializer = Serializer()

storage = StorageEngine(data_dir=DATA_DIR, serializer=serializer)

schema_student = {
    "table_name": "student",
    "columns": [
        {"name": "studentid", "type": "int"},
        {"name": "fullname", "type": "varchar", "length": 50},
        {"name": "gpa", "type": "float"}
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
        {"name": "studentid", "type": "int"},
        {"name": "CourseID", "type": "int"},
        {"name": "Year", "type": "int"},
    ]
}

students = [
    {
        "studentid": i,
        "fullname": f"Student_{i}",
        "gpa": round(random.uniform(2.0, 4.0), 2)
    }
    for i in range(1, 10001)
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
        "studentid": random.randint(1, 10000),
        "CourseID": random.randint(1, 50),
        "Year": random.choice([2023, 2024, 2025])
    }
    for _ in range(50)
]

for schema, data in [
    (schema_student, students),
    (schema_course, courses),
    (schema_attends, attends)
]:
    storage.write_schema_file(schema)
    storage.write_data_file(schema["table_name"], data, schema)

print(f"Setup: Data generation complete and stored in 'data/{DATA_DIR}' directory.")
print(f"Created: 3 tables (student: {len(students)} rows, course: {len(courses)} rows, attends: {len(attends)} rows)")
