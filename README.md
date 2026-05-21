```mermaid
classDiagram
    class System {
        -DeptManager deptManager
        -PatientManager patientManager
        -RoomManager roomManager
        -PharmacyManager pharmacyManager
        -AdmissionManager admissionManager
    }

    class PatientManager {
        -vector~Patient~ patients
        +addPatient(Patient patient) bool
        +removePatient(string patientId) bool
        +updatePatient(Patient patient) bool
        +findPatient(string patientName) Patient
        +getPatients() vector~Patient~
        +showPatientInfo(Patient patient) void
    }

    class Patient {
        -string fullName
        -string id
        -short age
        -string gender
        -string phone
        +getPatientID() string
        +getFullName() string
        +setFullName(string name) void
        +getAge() int
        +setAge(int age) void
    }

    %% العلاقات بأسلوب آمن ومؤطر بعلامات التنصيص
    System --> PatientManager : "يحتوي على"
    PatientManager --> Patient : "يدير ويحتوي على"
