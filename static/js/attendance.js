document.addEventListener("DOMContentLoaded", () => {

    console.log("FaceAttend attendance.js loaded.");


    // =====================================================
    // ELEMENTS
    // =====================================================

    const video =
        document.getElementById("attendanceCamera");

    const canvas =
        document.getElementById("attendanceCanvas");

    const placeholder =
        document.getElementById("cameraPlaceholder");

    const cameraStatus =
        document.getElementById("cameraStatus");

    const cameraLiveText =
        document.getElementById("cameraLiveText");

    const detectionText =
        document.getElementById(
            "attendanceRecognitionMessage"
        );

    const startCameraBtn =
        document.getElementById(
            "startAttendanceCameraBtn"
        );

    const stopCameraBtn =
        document.getElementById(
            "stopAttendanceCameraBtn"
        );

    const closeAttendanceBtn =
        document.getElementById(
            "closeAttendanceBtn"
        );

    const employeeCard =
        document.getElementById(
            "attendanceEmployeeCard"
        );

    const employeeName =
        document.getElementById(
            "attendanceEmployeeName"
        );

    const employeeNumber =
        document.getElementById(
            "attendanceEmployeeNumber"
        );

    const employeeDepartment =
        document.getElementById(
            "attendanceEmployeeDepartment"
        );

    const employeePosition =
        document.getElementById(
            "attendanceEmployeePosition"
        );

    const otpCard =
        document.getElementById(
            "attendanceOtpCard"
        );

    const otpDestination =
        document.getElementById(
            "attendanceOtpDestination"
        );

    const sendOtpBtn =
        document.getElementById(
            "attendanceSendOtpBtn"
        );

    const otpInputSection =
        document.getElementById(
            "attendanceOtpInputSection"
        );

    const otpInput =
        document.getElementById(
            "attendanceOtpInput"
        );

    const verifyOtpBtn =
        document.getElementById(
            "attendanceVerifyOtpBtn"
        );

    const otpStatus =
        document.getElementById(
            "attendanceOtpStatus"
        );

    const attendanceStatusText =
        document.getElementById(
            "attendanceStatusText"
        );


    // =====================================================
    // STATE
    // =====================================================

    let stream = null;

    let recognitionTimer = null;

    let recognitionInProgress = false;

    let identifiedEmployeeId = null;

    let employeeIdentified = false;

    let otpInProgress = false;

    let attendanceCloseInProgress = false;


    // Automatically available when the active
    // attendance camera exists on the page.
    const sessionIsActive =
        Boolean(
            document.getElementById(
                "attendanceCamera"
            )
        );


    // =====================================================
    // CAMERA STATUS
    // =====================================================

    function setCameraStatus(
        message,
        active = false
    ) {

        if (!cameraStatus) {
            return;
        }

        cameraStatus.innerHTML = `
            <span class="status-dot"></span>
            ${message}
        `;

        cameraStatus.classList.toggle(
            "active",
            active
        );
    }


    // =====================================================
    // RECOGNITION MESSAGE
    // =====================================================

    function setRecognitionMessage(
        message,
        type = ""
    ) {

        if (!detectionText) {
            return;
        }

        detectionText.textContent =
            message;

        detectionText.classList.remove(
            "success",
            "error"
        );

        if (type) {

            detectionText.classList.add(
                type
            );

        }
    }


    // =====================================================
    // RESET EMPLOYEE RESULT
    // =====================================================

    function resetEmployeeResult() {

        identifiedEmployeeId = null;

        employeeIdentified = false;


        if (employeeCard) {

            employeeCard.style.display =
                "none";

        }


        if (otpCard) {

            otpCard.style.display =
                "none";

        }


        if (otpInputSection) {

            otpInputSection.style.display =
                "none";

        }


        if (otpInput) {

            otpInput.value = "";

        }


        if (otpStatus) {

            otpStatus.textContent = "";

        }


        if (sendOtpBtn) {

            sendOtpBtn.disabled =
                false;


            sendOtpBtn.innerHTML = `
                <i class="bi bi-envelope"></i>
                Send Verification Code
            `;

        }

    }


    // =====================================================
    // START CAMERA
    // =====================================================

    async function startCamera() {

        if (stream) {
            return;
        }


        if (!video) {

            console.error(
                "attendanceCamera element not found."
            );

            return;

        }


        try {

            if (
                !navigator.mediaDevices ||
                !navigator.mediaDevices.getUserMedia
            ) {

                throw new Error(
                    "Camera access is not supported by this browser."
                );

            }


            console.log(
                "Requesting attendance camera..."
            );


            stream =
                await navigator.mediaDevices.getUserMedia({

                    video: {

                        width: {
                            ideal: 1280
                        },

                        height: {
                            ideal: 720
                        },

                        facingMode: "user"

                    },

                    audio: false

                });


            console.log(
                "Attendance camera stream started."
            );


            video.srcObject =
                stream;


            await video.play();


            // =================================================
            // SHOW LIVE CAMERA
            // =================================================

            video.style.display =
                "block";

            video.style.visibility =
                "visible";

            video.style.opacity =
                "1";


            // =================================================
            // FORCE HIDE CAMERA PLACEHOLDER
            // =================================================

            if (placeholder) {

                placeholder.style.display =
                    "none";

                placeholder.style.visibility =
                    "hidden";

                placeholder.style.opacity =
                    "0";

                placeholder.style.pointerEvents =
                    "none";

                placeholder.classList.add(
                    "hidden"
                );

            }


            // =================================================
            // CANVAS
            // =================================================

            if (canvas) {

                canvas.width =
                    video.videoWidth ||
                    640;

                canvas.height =
                    video.videoHeight ||
                    480;

            }


            const cameraResolution =
                document.getElementById(
                    "cameraResolution"
                );


            if (cameraResolution) {

                cameraResolution.textContent =
                    `${
                        video.videoWidth ||
                        640
                    } × ${
                        video.videoHeight ||
                        480
                    }`;

            }


            // =================================================
            // CAMERA STATUS
            // =================================================

            setCameraStatus(
                "Camera Online",
                true
            );


            if (cameraLiveText) {

                cameraLiveText.textContent =
                    "Camera Online";

            }


            // =================================================
            // BUTTONS
            // =================================================

            if (startCameraBtn) {

                startCameraBtn.disabled =
                    true;


                startCameraBtn.innerHTML = `
                    <i class="bi bi-camera-video-fill"></i>
                    Camera Running
                `;

            }


            if (stopCameraBtn) {

                stopCameraBtn.disabled =
                    false;

            }


            // =================================================
            // MESSAGE
            // =================================================

            setRecognitionMessage(
                "Camera active. Looking for an enrolled employee..."
            );


            if (attendanceStatusText) {

                attendanceStatusText.textContent =
                    "Camera active. Position one enrolled employee clearly in front of the camera.";

            }


            // =================================================
            // START FACE RECOGNITION
            // =================================================

            startRecognition();

        } catch (error) {

            console.error(
                "Attendance camera error:",
                error
            );


            stream = null;


            setCameraStatus(
                "Camera Error",
                false
            );


            if (cameraLiveText) {

                cameraLiveText.textContent =
                    "Camera Error";

            }


            setRecognitionMessage(
                error.message ||
                "Unable to access the camera.",
                "error"
            );

        }

    }


    // =====================================================
    // STOP CAMERA
    // =====================================================

    function stopCamera() {

        stopRecognition();


        if (stream) {

            stream.getTracks().forEach(
                track => track.stop()
            );

            stream = null;

        }


        if (video) {

            video.srcObject =
                null;

            video.style.display =
                "none";

            video.style.visibility =
                "hidden";

            video.style.opacity =
                "0";

        }


        // =================================================
        // SHOW PLACEHOLDER AGAIN
        // =================================================

        if (placeholder) {

            placeholder.classList.remove(
                "hidden"
            );

            placeholder.style.display =
                "flex";

            placeholder.style.visibility =
                "visible";

            placeholder.style.opacity =
                "1";

            placeholder.style.pointerEvents =
                "auto";

        }


        if (startCameraBtn) {

            startCameraBtn.disabled =
                false;


            startCameraBtn.innerHTML = `
                <i class="bi bi-camera-video"></i>
                Start Camera
            `;

        }


        if (stopCameraBtn) {

            stopCameraBtn.disabled =
                true;

        }


        setCameraStatus(
            "Camera Offline",
            false
        );


        if (cameraLiveText) {

            cameraLiveText.textContent =
                "Camera Offline";

        }


        setRecognitionMessage(
            "Camera stopped. Start the camera to continue."
        );

    }


    // =====================================================
    // CAPTURE FRAME
    // =====================================================

    function captureFrame() {

        if (
            !video ||
            !canvas ||
            !video.videoWidth ||
            !video.videoHeight
        ) {

            return null;

        }


        canvas.width =
            video.videoWidth;


        canvas.height =
            video.videoHeight;


        const context =
            canvas.getContext("2d");


        if (!context) {

            return null;

        }


        context.drawImage(
            video,
            0,
            0,
            canvas.width,
            canvas.height
        );


        return canvas.toDataURL(
            "image/jpeg",
            0.85
        );

    }


    // =====================================================
    // START RECOGNITION
    // =====================================================

    function startRecognition() {

        stopRecognition();

        recognizeEmployee();

    }


    // =====================================================
    // STOP RECOGNITION
    // =====================================================

    function stopRecognition() {

        if (recognitionTimer) {

            clearTimeout(
                recognitionTimer
            );

            recognitionTimer =
                null;

        }

    }


    // =====================================================
    // SCHEDULE NEXT SCAN
    // =====================================================

    function scheduleNextScan() {

        if (
            !stream ||
            employeeIdentified ||
            attendanceCloseInProgress
        ) {

            return;

        }


        stopRecognition();


        recognitionTimer =
            setTimeout(
                recognizeEmployee,
                1200
            );

    }


    // =====================================================
    // RECOGNIZE EMPLOYEE
    // =====================================================

    async function recognizeEmployee() {

        if (
            recognitionInProgress ||
            !stream ||
            employeeIdentified ||
            attendanceCloseInProgress
        ) {

            return;

        }


        recognitionInProgress =
            true;


        try {

            const image =
                captureFrame();


            if (!image) {

                recognitionInProgress =
                    false;

                scheduleNextScan();

                return;

            }


            setRecognitionMessage(
                "Scanning employee face..."
            );


            if (cameraLiveText) {

                cameraLiveText.textContent =
                    "Scanning";

            }


            const response =
                await fetch(
                    "/face-recognition/identify",
                    {

                        method: "POST",

                        headers: {

                            "Content-Type":
                                "application/json"

                        },

                        credentials:
                            "same-origin",

                        body:
                            JSON.stringify({
                                image: image
                            })

                    }
                );


            const result =
                await response.json();


            console.log(
                "Recognition response:",
                result
            );


            if (!response.ok) {

                throw new Error(
                    result.message ||
                    "Face recognition request failed."
                );

            }


            if (!result.success) {

                setRecognitionMessage(
                    result.message ||
                    "Face recognition failed.",
                    "error"
                );


                recognitionInProgress =
                    false;


                scheduleNextScan();

                return;

            }


            // =================================================
            // NO FACE
            // =================================================

            if (
                !result.face_detected
            ) {

                setRecognitionMessage(
                    "Looking for employee face..."
                );


                recognitionInProgress =
                    false;


                scheduleNextScan();

                return;

            }


            // =================================================
            // MULTIPLE FACES
            // =================================================

            if (
                result.multiple_faces
            ) {

                setRecognitionMessage(
                    "Multiple faces detected. Only one employee should be visible.",
                    "error"
                );


                recognitionInProgress =
                    false;


                scheduleNextScan();

                return;

            }


            // =================================================
            // EMPLOYEE NOT RECOGNIZED
            // =================================================

            if (
                !result.recognized ||
                !result.employee
            ) {

                setRecognitionMessage(
                    result.message ||
                    "Employee could not be identified.",
                    "error"
                );


                recognitionInProgress =
                    false;


                scheduleNextScan();

                return;

            }


            // =================================================
            // EMPLOYEE IDENTIFIED
            // =================================================

            const employee =
                result.employee;


            identifiedEmployeeId =
                employee.id;


            employeeIdentified =
                true;


            stopRecognition();


            // =================================================
            // EMPLOYEE DETAILS
            // =================================================

            if (employeeName) {

                employeeName.textContent =
                    `${employee.first_name} ${employee.last_name}`;

            }


            if (employeeNumber) {

                employeeNumber.textContent =
                    employee.employee_number ||
                    "--";

            }


            if (employeeDepartment) {

                employeeDepartment.textContent =
                    employee.department_name ||
                    "Unassigned";

            }


            if (employeePosition) {

                employeePosition.textContent =
                    employee.position ||
                    "Not specified";

            }


            if (employeeCard) {

                employeeCard.style.display =
                    "block";

            }


            if (otpCard) {

                otpCard.style.display =
                    "block";

            }


            setRecognitionMessage(
                `Employee identified: ${employee.first_name} ${employee.last_name}`,
                "success"
            );


            if (cameraLiveText) {

                cameraLiveText.textContent =
                    "Employee Identified";

            }


            if (attendanceStatusText) {

                attendanceStatusText.textContent =
                    "Employee identity verified. Verification code required before attendance is recorded.";

            }


            // =================================================
            // SEND OTP AUTOMATICALLY
            // =================================================

            await sendOtp();


        } catch (error) {

            console.error(
                "Employee recognition error:",
                error
            );


            setRecognitionMessage(
                error.message ||
                "Unable to process face recognition.",
                "error"
            );


            employeeIdentified =
                false;


            scheduleNextScan();

        } finally {

            recognitionInProgress =
                false;

        }

    }


    // =====================================================
    // SEND OTP
    // =====================================================

    async function sendOtp() {

        if (!identifiedEmployeeId) {

            return;

        }


        if (otpInProgress) {

            return;

        }


        if (attendanceCloseInProgress) {

            return;

        }


        otpInProgress =
            true;


        if (sendOtpBtn) {

            sendOtpBtn.disabled =
                true;


            sendOtpBtn.innerHTML = `
                <span
                    class="spinner-border spinner-border-sm me-2">
                </span>
                Sending Code...
            `;

        }


        if (otpStatus) {

            otpStatus.textContent =
                "Sending verification code...";

        }


        try {

            const response =
                await fetch(
                    "/face-recognition/send-otp",
                    {

                        method: "POST",

                        headers: {

                            "Content-Type":
                                "application/json"

                        },

                        credentials:
                            "same-origin",

                        body:
                            JSON.stringify({

                                employee_id:
                                    identifiedEmployeeId

                            })

                    }
                );


            const result =
                await response.json();


            console.log(
                "OTP response:",
                result
            );


            if (!response.ok) {

                throw new Error(
                    result.message ||
                    "Unable to send verification code."
                );

            }


            if (!result.success) {

                throw new Error(
                    result.message ||
                    "Unable to send verification code."
                );

            }


            // =================================================
            // OTP SENT
            // =================================================

            if (otpDestination) {

                otpDestination.textContent =
                    `Verification code sent to ${
                        result.destination ||
                        "the employee's email"
                    }.`;

            }


            if (otpInputSection) {

                otpInputSection.style.display =
                    "block";

            }


            if (otpStatus) {

                otpStatus.textContent =
                    `Enter the six-digit code. The code expires in ${
                        result.expires_in ||
                        5
                    } minutes.`;

            }


            if (sendOtpBtn) {

                sendOtpBtn.innerHTML = `
                    <i class="bi bi-check-circle"></i>
                    Verification Code Sent
                `;

            }


            if (otpInput) {

                otpInput.focus();

            }


        } catch (error) {

            console.error(
                "OTP send error:",
                error
            );


            employeeIdentified =
                false;


            if (otpStatus) {

                otpStatus.textContent =
                    error.message ||
                    "Unable to send verification code.";

            }


            if (sendOtpBtn) {

                sendOtpBtn.disabled =
                    false;


                sendOtpBtn.innerHTML = `
                    <i class="bi bi-envelope"></i>
                    Send Verification Code
                `;

            }


            scheduleNextScan();

        } finally {

            otpInProgress =
                false;

        }

    }


    // =====================================================
    // VERIFY OTP
    // =====================================================

    async function verifyOtp() {

        console.log(
            "Attendance OTP verification started."
        );


        if (!identifiedEmployeeId) {

            if (otpStatus) {

                otpStatus.textContent =
                    "No employee has been identified.";

            }

            return;

        }


        const otp =
            otpInput
                ? otpInput.value.trim()
                : "";


        if (!/^\d{6}$/.test(otp)) {

            if (otpStatus) {

                otpStatus.textContent =
                    "Enter a valid 6-digit verification code.";

            }

            return;

        }


        if (verifyOtpBtn) {

            verifyOtpBtn.disabled =
                true;


            verifyOtpBtn.innerHTML = `
                <span
                    class="spinner-border spinner-border-sm me-2">
                </span>
                Verifying...
            `;

        }


        if (otpStatus) {

            otpStatus.textContent =
                "Verifying code and recording attendance...";

        }


        try {

            const response =
                await fetch(
                    "/face-recognition/verify-otp",
                    {

                        method: "POST",

                        headers: {

                            "Content-Type":
                                "application/json"

                        },

                        credentials:
                            "same-origin",

                        body:
                            JSON.stringify({

                                employee_id:
                                    identifiedEmployeeId,

                                otp:
                                    otp

                            })

                    }
                );


            const responseText =
                await response.text();


            let result;


            try {

                result =
                    JSON.parse(
                        responseText
                    );

            } catch (jsonError) {

                console.error(
                    "Invalid server response:",
                    responseText
                );


                throw new Error(
                    `Server returned an invalid response (${response.status}).`
                );

            }


            console.log(
                "Verify OTP response:",
                result
            );


            if (!response.ok) {

                throw new Error(
                    result.message ||
                    "Attendance verification failed."
                );

            }


            if (!result.success) {

                throw new Error(
                    result.message ||
                    "Attendance verification failed."
                );

            }


            // =================================================
            // ATTENDANCE SUCCESS
            // =================================================

            if (otpStatus) {

                otpStatus.textContent =
                    result.message ||
                    "Attendance recorded successfully.";

            }


            setRecognitionMessage(
                result.message ||
                "Attendance recorded successfully.",
                "success"
            );


            if (cameraLiveText) {

                cameraLiveText.textContent =
                    "Attendance Recorded";

            }


            if (attendanceStatusText) {

                attendanceStatusText.textContent =
                    result.message ||
                    "Attendance recorded successfully.";

            }


            if (verifyOtpBtn) {

                verifyOtpBtn.innerHTML = `
                    <i class="bi bi-check-circle-fill"></i>
                    Attendance Recorded
                `;

            }


            // =================================================
            // STOP CAMERA
            // =================================================

            stopCamera();


            // =================================================
            // REFRESH TABLE
            // =================================================

            setTimeout(
                () => {

                    window.location.reload();

                },
                1200
            );


        } catch (error) {

            console.error(
                "OTP verification error:",
                error
            );


            if (otpStatus) {

                otpStatus.textContent =
                    error.message ||
                    "Unable to verify the code.";

            }


            if (verifyOtpBtn) {

                verifyOtpBtn.disabled =
                    false;


                verifyOtpBtn.innerHTML = `
                    <i class="bi bi-check-circle"></i>
                    Verify & Record Attendance
                `;

            }

        }

    }


    // =====================================================
    // CLOSE TODAY'S ATTENDANCE
    // =====================================================

    async function closeAttendance() {

        if (
            attendanceCloseInProgress
        ) {

            return;

        }


        if (!closeAttendanceBtn) {

            return;

        }


        const confirmed =
            window.confirm(
                "Are you sure you want to close today's attendance session?"
            );


        if (!confirmed) {

            return;

        }


        attendanceCloseInProgress =
            true;


        // =================================================
        // STOP RECOGNITION
        // =================================================

        stopRecognition();


        // =================================================
        // DISABLE BUTTONS
        // =================================================

        if (closeAttendanceBtn) {

            closeAttendanceBtn.disabled =
                true;

            closeAttendanceBtn.innerHTML = `
                <span
                    class="spinner-border spinner-border-sm me-2"
                    role="status"
                    aria-hidden="true">
                </span>
                Closing Attendance...
            `;

        }


        if (startCameraBtn) {

            startCameraBtn.disabled =
                true;

        }


        if (stopCameraBtn) {

            stopCameraBtn.disabled =
                true;

        }


        if (sendOtpBtn) {

            sendOtpBtn.disabled =
                true;

        }


        if (verifyOtpBtn) {

            verifyOtpBtn.disabled =
                true;

        }


        if (attendanceStatusText) {

            attendanceStatusText.textContent =
                "Closing today's attendance session...";

        }


        try {

            const response =
                await fetch(
                    "/attendance/close",
                    {

                        method: "POST",

                        credentials:
                            "same-origin",

                        headers: {

                            "Content-Type":
                                "application/json"

                        }

                    }
                );


            const responseText =
                await response.text();


            let result;


            try {

                result =
                    JSON.parse(
                        responseText
                    );

            } catch (jsonError) {

                console.error(
                    "Invalid close-session response:",
                    responseText
                );


                throw new Error(
                    `Server returned an invalid response (${response.status}).`
                );

            }


            console.log(
                "Close attendance response:",
                result
            );


            if (!response.ok) {

                throw new Error(
                    result.message ||
                    "Unable to close today's attendance session."
                );

            }


            if (!result.success) {

                throw new Error(
                    result.message ||
                    "Unable to close today's attendance session."
                );

            }


            // =================================================
            // STOP CAMERA
            // =================================================

            stopCamera();


            // =================================================
            // SUCCESS MESSAGE
            // =================================================

            if (attendanceStatusText) {

                attendanceStatusText.textContent =
                    result.message ||
                    "Today's attendance session has been closed.";

            }


            setRecognitionMessage(
                result.message ||
                "Today's attendance session has been closed.",
                "success"
            );


            // =================================================
            // RELOAD PAGE
            // =================================================

            setTimeout(
                () => {

                    window.location.reload();

                },
                700
            );


        } catch (error) {

            console.error(
                "Close attendance error:",
                error
            );


            attendanceCloseInProgress =
                false;


            if (attendanceStatusText) {

                attendanceStatusText.textContent =
                    error.message ||
                    "Unable to close today's attendance session.";

            }


            setRecognitionMessage(
                error.message ||
                "Unable to close today's attendance session.",
                "error"
            );


            // =================================================
            // RESTORE BUTTON
            // =================================================

            if (closeAttendanceBtn) {

                closeAttendanceBtn.disabled =
                    false;


                closeAttendanceBtn.innerHTML = `
                    <i class="bi bi-stop-circle"></i>
                    Close Today's Attendance
                    <i class="bi bi-arrow-right"></i>
                `;

            }


            if (startCameraBtn) {

                startCameraBtn.disabled =
                    !video;

            }


            if (stream && stopCameraBtn) {

                stopCameraBtn.disabled =
                    false;

            }


            if (sendOtpBtn) {

                sendOtpBtn.disabled =
                    false;

            }


            if (verifyOtpBtn) {

                verifyOtpBtn.disabled =
                    false;

            }

        }

    }


    // =====================================================
    // OTP INPUT
    // =====================================================

    if (otpInput) {

        otpInput.addEventListener(
            "input",
            () => {

                otpInput.value =
                    otpInput.value
                        .replace(/\D/g, "")
                        .slice(0, 6);

            }
        );

    }


    // =====================================================
    // BUTTON EVENTS
    // =====================================================

    if (startCameraBtn) {

        startCameraBtn.addEventListener(
            "click",
            startCamera
        );

    }


    if (stopCameraBtn) {

        stopCameraBtn.addEventListener(
            "click",
            stopCamera
        );

    }


    if (closeAttendanceBtn) {

        closeAttendanceBtn.addEventListener(
            "click",
            closeAttendance
        );

    }


    if (sendOtpBtn) {

        sendOtpBtn.addEventListener(
            "click",
            sendOtp
        );

    }


    if (verifyOtpBtn) {

        verifyOtpBtn.addEventListener(
            "click",
            verifyOtp
        );

    }


    // =====================================================
    // CLEANUP
    // =====================================================

    window.addEventListener(
        "beforeunload",
        () => {

            stopRecognition();


            if (stream) {

                stream.getTracks().forEach(
                    track => track.stop()
                );

            }

        }
    );


    // =====================================================
    // AUTOMATIC CAMERA START
    // =====================================================

    if (sessionIsActive) {

        setTimeout(
            () => {

                startCamera();

            },
            500
        );

    }

});