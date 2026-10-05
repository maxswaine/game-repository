from enum import Enum


class UserSegmentEnum(str, Enum):
    student_full_time_education = "Student / Full-time Education"
    traveller = "Traveller"
    teacher_education_worker = "Teacher / Education Worker"
    other = "Other"
