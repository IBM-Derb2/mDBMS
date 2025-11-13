from serializer import Serializer
import random

serializer = Serializer()

# === SCHEMA ===
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

# === DATA ===
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

# === SERIALIZE TO FILE ===
for schema, data in [
    (schema_student, students),
    (schema_course, courses),
    (schema_attends, attends)
]:
    # serialize schema
    schema_bytes = serializer.serialize_schema(schema)
    with open(f"data_demo/{schema['table_name']}_schema.dat", "wb") as f:
        f.write(schema_bytes)

    # serialize data
    data_bytes = serializer.serialize_with_blocks(data, schema)
    with open(f"data_demo/{schema['table_name']}.dat", "wb") as f:
        f.write(data_bytes)

print("Dummy data berhasil dibuat di folder data_demo/")
