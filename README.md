```mermaid
classDiagram
%%{init: {"layout": "elk"}}%%

class System {
    -DeptManager deptManager
    -PatientManager patientManager
    -RoomManager roomManager
    -PharmacyManager pharmacyManager
    -AdmissionManager admissionManager
}

class AdmissionManager {
    -vector~Admission~ admissions
    -AdmissionRepository admissionRepository
    -RoomManager roomManager
    +admitPatient(patientID string, roomID string, dateFrom Date) Admission
    +dischargePatient(admissionID string, dateTo Date) bool
    +findAdmission(admissionID string) Admission
    +getActiveAdmissionForPatient(patientID string) Admission
    +getActiveAdmissionForRoom(roomID string) Admission
    +isRoomAvailableNow(roomID string) bool
    +getAdmissionHistoryForPatient(patientID string) vector~Admission~
    +getAdmissionHistoryForRoom(roomID string) vector~Admission~
    +getAllActiveAdmissions() vector~Admission~
    -validateAdmission(patientID string, roomID string) bool
    -loadFromRepository() void
    -saveToRepository() void
}

class Admission {
    -string admissionID
    -string patientID
    -string roomID
    -date dateFrom
    -date dateTo
    -bool isActive
    +getPatientID() string
    +getRoomID() string
    +getDateFrom() Date
    +getIsActive() bool
}

class DoctorManager {
    -vector~Doctor~ doctors
    +getDoctors() vector~Doctor~
    +findDoctor(doctorName string) Doctor
    +addDoctor(doctor Doctor) bool
    +deleteDoctor(doctorId string) bool
    +updateDoctor(doctor Doctor) bool
}

class Doctor {
    -string doctorID
    -string doctorName
    -string specialization
    -string departmentID
    -vector~string~ patientsId
    +getDoctorName() string
    +getSpecialization() string
}

class MedicineManager {
    -vector~Medicine~ medicines
    -MedicineRepository medicineRepository
    +addMedicine(medicine Medicine) bool
    +findMedicine(medicineID string) Medicine
    +getAllMedicines() vector~Medicine~
}

class Medicine {
    -string medicineId
    -string medicineName
    -int quantity
    -double price
    +getMedicineName() string
    +getQuantityInStock() int
    +getPrice() double
}

class DepartmentManager {
    -vector~Department~ departments
    +addDepartment() bool
    +getDepartments() vector~Department~
}

class Department {
    -string Name
    -enum Type
    -string Manager
    -int capacity
    +getName() string
    +getManagerName() string
}

class RoomManager {
    -vector~Room~ rooms
    +updateRoom() bool
    +getRooms() vector~Room~
    +getAvailableRooms() vector~Room~
}

class Room {
    -string Id
    -string Number
    -enum Status
    +getRoomNumber() string
    +getRoomStatus() enum
}

class PatientManager {
    -vector~Patient~ patients
    +addPatient(patient Patient) bool
    +getPatients() vector~Patient~
}

class Patient {
    -string fullName
    -string id
    -int age
    -string phone
    +getFullName() string
    +getAge() int
}

class PharmacyManager {
    -Pharmacy pharmacy
    -MedicineManager medicineManager
    -PrescriptionManager prescriptionManager
    +dispensePrescription(prescriptionID string) bool
    +getPendingPrescriptions() vector~Prescription~
}

class Pharmacy {
    -string id
    -string name
    -string location
    +getPharmacyID() string
    +getName() string
}

class PrescriptionManager {
    -vector~Prescription~ prescriptions
    +createPrescription(patientID string, doctorID string, medicineID string, dosage string) Prescription
    +getAllPrescriptions() vector~Prescription~
    +findPrescription(prescriptionID string) Prescription
}

class Prescription {
    -String id
    -String patientID
    -String doctorID
    -String medicineID
    -String dosage
    +getPrescriptionId() String
    +getPatientID() String
    +getDoctorID() String
}

class NurseManager {
    -vector~Nurse~ nurses
    +addNurse(nurse Nurse) bool
    +getNurses() vector~Nurse~
}

class Nurse {
    -string nurseID
    -string nurseName
    -string phone
    +getNurseName() string
}

System --> DepartmentManager
System --> PatientManager
System --> RoomManager
System --> PharmacyManager
System --> AdmissionManager
System --> DoctorManager
System --> NurseManager

PharmacyManager --> MedicineManager
PharmacyManager --> PrescriptionManager
AdmissionManager --> RoomManager
AdmissionManager --> Admission
DoctorManager --> Doctor
DepartmentManager --> Department
RoomManager --> Room
PatientManager --> Patient
NurseManager --> Nurse
MedicineManager --> Medicine
PharmacyManager --> Pharmacy
PrescriptionManager --> Prescription

classDef core fill:#eef2ff,stroke:#818cf8
classDef manager fill:#f0fdfa,stroke:#2dd4bf
classDef entity fill:#fefce8,stroke:#facc15

class System core
class AdmissionManager manager
class DoctorManager manager
class DepartmentManager manager
class RoomManager manager
class PatientManager manager
class PharmacyManager manager
class PrescriptionManager manager
class NurseManager manager
class MedicineManager manager
class Admission entity
class Doctor entity
class Department entity
class Room entity
class Patient entity
class Pharmacy entity
class Prescription entity
class Medicine entity
class Nurse entity
