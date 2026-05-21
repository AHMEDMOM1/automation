```mermaid
classDiagram

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
        +setPatientID(id string) void
        +getRoomID() string
        +setRoomID(id string) void
        +getDateFrom() Date
        +setDateFrom(date Date) void
        +getIsActive() bool
        +setIsActive(active bool) void
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
        -string phone
        -string specialization
        -string departmentID
        -vector~string~ patientsId
        +getDoctorID() string
        +getDoctorName() string
        +getSpecialization() string
        +setDoctorName(name string) void
        +setPhone(phone string) void
        +setSpecialization(spec string) void
        +setPatients(patients vector~Patient~) void
        +initializedForThisPatient(patientId string) bool
    }

    class MedicineManager {
        -vector~Medicine~ mediciens
        -vector~Medicine~ medicines
        -MedicineRepository medicineRepository
        +addMedicine(medicine Medicine) bool
        +findMedicine(medicineID string) Medicine
        +getAllMedicines() vector~Medicine~
        +updateMedicine(medicineID string, name string, price double) bool
        +deleteMedicine(medicineID string) bool
        +increaseStock(medicineID string, amount int) bool
        +decreaseStock(medicineID string, amount int) bool
        +getLowStockMedicines(threshold int) vector~Medicine~
        +findMedicineByName(name string) vector~Medicine~
        +isMedicineAvailable(medicineID string, requiredAmount int) bool
        -validateMedicine(medicine Medicine) bool
        -loadMedicines() void
        -saveMedicines() void
    }

    class Medicine {
        -string medicineId
        -string medicineName
        -int quantity
        -double price
        +Medicine(id string, name string, quantity int, price double)
        +getMedicineID() string
        +getMedicineName() string
        +setMedicineName(name string) void
        +getQuantityInStock() int
        +getPrice() double
        +setPrice(price double) void
    }

    class DepartmentManager {
        -vector~Department~ departments
        +addDepartment() bool
        +showDepartment() bool
        +editDepartment() bool
        +updateDepartment() bool
        +deleteDepartment() bool
        +findDepartment(depName string) department
        +save() bool
        +getDepartments() vector~department~
        +getHospitalState() void
    }

    class Department {
        -string Name
        -enum Type
        -string Manager
        -string id
        -int capacity
        +getType() enum
        +getName() string
        +getManagerName() string
        +setName(name string) void
        +setType(type enum) void
        +setManager(name string) void
        +setCapacity() void
        +getCapacity() int
    }

    class RoomManager {
        -vector~Room~ rooms
        +updateRoom() bool
        +findRoom() Room
        +getRooms() vector~Room~
        +getAvailableRooms() vector~Room~
        +getOccupiedRooms() vector~Room~
        +reserveRoom() bool
        +releaseRoom() bool
        +confirmSterilization() void
        +getRoomsOfDepartmentById(departmentId string) vector~Room~
    }

    class Room {
        -string Number
        -string Id
        -enum Status
        -string roomType
        -string departmentId
        +getRoomID() string
        +getRoomNumber() string
        +getRoomType() enum
        +getRoomStatus() enum
        +setRoomNumber(number string) void
        +setRoomType(type enum) void
        +setRoomStatus(status enum) void
    }

    class PatientManager {
        -vector~Patient~ patients
        +addPatient(patient Patient) bool
        +removePatient(patientId string) bool
        +updatePatient(patient Patient) bool
        +findPatient(patientName string) Patient
        +getPatients() vector~Patient~
        +showPatientInfo(patient Patient) void
    }

    class Patient {
        -string fullName
        -string id
        -short age
        -enum gender
        -string phone
        -string bloodType
        -string address
        -string responsibleDoctorId
        -string responsibleNurseId
        -date lastExaminationDate
        -Date admissionDate
        -string diagnosis
        -vector~string~ prescriptionsId
        +getPatientID() string
        +getFullName() string
        +setFullName(name string) void
        +getAge() int
        +setAge(age int) void
        +getPhone() string
        +setPhone(phone string) void
    }

    class PharmacyManager {
        -Pharmacy pharmacy
        -MedicineManager medicineManager
        -PrescriptionManager prescriptionManager
        +dispensePrescription(prescriptionID string) bool
        +getPendingPrescriptions() vector~Prescription~
        +checkStockAvailability(medicineID string, amount int) bool
        +getDispensingHistory() vector~Prescription~
    }

    class Pharmacy {
        -string id
        -string name
        -string location
        +getPharmacyID() string
        +getName() string
        +setName(name string) void
        +getLocation() string
        +setLocation(loc string) void
    }

    class PrescriptionManager {
        -vector~Prescription~ prescriptions
        -PrescriptionRepository prescriptionRepository
        +createPrescription(patientID string, doctorID string, medicineID string, dosage string) Prescription
        +getAllPrescriptions() vector~Prescription~
        +findPrescription(prescriptionID string) Prescription
        -deletePrescription(prescriptionID string) bool
        +sendToPharmacy(prescriptionID string) bool
        +markAsDispensed(prescriptionID string) bool
        +getPendingPrescriptions() vector~Prescription~
        +getPrescriptionsByPatient(patientID string) vector~Prescription~
        +getPrescriptionsByDoctor(doctorID string) vector~Prescription~
        +getPrescriptionsByMedicine(medicineID string) vector~Prescription~
        -validatePrescription(patientID string, doctorID string, medicineID string) bool
        -loadFromRepository() void
        -saveToRepository() void
    }

    class Prescription {
        -String id
        -String patientID
        -String doctorID
        -String medicineID
        -String dosage
        -Date dateIssued
        -enum status
        +getPrescriptionId() String
        +getPatientID() String
        +getDoctorID() String
        +getMedicineID() String
        +getDosage() String
        +getDateIssued() Date
        +getStatus() enum
        +GetPrescriptionDetails() String
    }

    class NurseManager {
        -vector~Nurse~ nurses
        +addNurse(nurse Nurse) bool
        +deleteNurse(nurseId string) bool
        +updateNurse(nurse Nurse) bool
        +findNurse(nurseName string) Nurse
        +getNurses() vector~Nurse~
        +showNurseInfo(nurse Nurse) void
        +getNurseById(id string) Nurse
        +getNursesByDept(deptId string) vector~Nurse~
        +isNurseAvailable(id string) bool
    }

    class Nurse {
        -string nurseID
        -string nurseName
        -string phone
        -vector~string~ patientsId
        +getNurseID() string
        +getNurseName() string
        +getPhone() string
        +getPatientId() vector~string~
        +setNurseName(name string) void
        +setPhone(phone string) void
        +setPatientId(patientId vector~string~) void
    }

    System --> DepartmentManager
    System --> PatientManager
    System --> RoomManager
    System --> PharmacyManager
    System --> AdmissionManager
    PharmacyManager --> MedicineManager
    PharmacyManager --> PrescriptionManager
    AdmissionManager --> RoomManager
    DoctorManager --> Doctor
    DepartmentManager --> Department
    RoomManager --> Room
    PatientManager --> Patient
    NurseManager --> Nurse
    AdmissionManager --> Admission
    MedicineManager --> Medicine
    PharmacyManager --> Pharmacy
    PrescriptionManager --> Prescription
