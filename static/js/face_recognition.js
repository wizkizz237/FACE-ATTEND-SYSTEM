document.addEventListener("DOMContentLoaded", () => {

    // =====================================================
    // ELEMENTS
    // =====================================================

    const video =
        document.getElementById("recognitionCamera");

    const canvas =
        document.getElementById("faceCanvas");

    const cameraContainer =
        document.getElementById("cameraContainer");

    const startCameraBtn =
        document.getElementById("startCameraBtn");

    const stopCameraBtn =
        document.getElementById("stopCameraBtn");

    const cameraStatus =
        document.getElementById("cameraStatus");

    const cameraResolution =
        document.getElementById("cameraResolution");

    const recognitionStatus =
        document.getElementById("recognitionStatus");

    const recognitionMessage =
        document.getElementById("recognitionMessage");

    const detectionText =
        document.getElementById("detectionText");


    // =====================================================
    // EMPLOYEE RESULT
    // =====================================================

    const employeeResultCard =
        document.getElementById("employeeResultCard");

    const identifiedEmployeeName =
        document.getElementById(
            "identifiedEmployeeName"
        );

    const identifiedEmployeeNumber =
        document.getElementById(
            "identifiedEmployeeNumber"
        );

    const identifiedEmployeeDepartment =
        document.getElementById(
            "identifiedEmployeeDepartment"
        );

    const identifiedEmployeePosition =
        document.getElementById(
            "identifiedEmployeePosition"
        );

    const identifiedEmployeeScore =
        document.getElementById(
            "identifiedEmployeeScore"
        );


    // =====================================================
    // OTP ELEMENTS
    // =====================================================

    const otpCard =
        document.getElementById("otpCard");

    const otpDestination =
        document.getElementById("otpDestination");

    const sendOtpBtn =
        document.getElementById("sendOtpBtn");

    const otpInputSection =
        document.getElementById("otpInputSection");

    const otpInput =
        document.getElementById("otpInput");

    const verifyOtpBtn =
        document.getElementById("verifyOtpBtn");

    const otpStatus =
        document.getElementById("otpStatus");


    // =====================================================
    // BASIC ELEMENT CHECK
    // =====================================================

    if (!video) {
        console.error(
            "Face Recognition: recognitionCamera element not found."
        );
        return;
    }

    if (!canvas) {
        console.error(
            "Face Recognition: faceCanvas element not found."
        );
        return;
    }

    if (!cameraContainer) {
        console.error(
            "Face Recognition: cameraContainer element not found."
        );
        return;
    }


    const context =
        canvas.getContext("2d");


    if (!context) {
        console.error(
            "Face Recognition: unable to create canvas context."
        );
        return;
    }


    // =====================================================
    // STATE
    // =====================================================

    let cameraStream = null;

    let recognitionTimer = null;

    let recognitionRunning = false;

    let requestInProgress = false;

    let identifiedEmployeeId = null;

    let attendanceVerified = false;

    let otpVerificationInProgress = false;

    let lastRecognizedEmployeeId = null;

    let lastRecognitionTime = 0;


    // =====================================================
    // CONFIGURATION
    // =====================================================

    const RECOGNITION_INTERVAL = 1500;

    const RECOGNITION_COOLDOWN = 5000;


    // =====================================================
    // CAMERA STATUS
    // =====================================================

    function setCameraOnline() {

        if (!cameraStatus) {
            return;
        }

        cameraStatus.classList.add("online");

        cameraStatus.innerHTML = `
            <span class="status-dot"></span>
            Camera Online
        `;
    }


    function setCameraOffline() {

        if (!cameraStatus) {
            return;
        }

        cameraStatus.classList.remove("online");

        cameraStatus.innerHTML = `
            <span class="status-dot"></span>
            Camera Offline
        `;
    }


    // =====================================================
    // RECOGNITION STATUS
    // =====================================================

    function setRecognitionStatus(
        title,
        message
    ) {

        if (recognitionStatus) {

            recognitionStatus.textContent =
                title;
        }

        if (recognitionMessage) {

            recognitionMessage.textContent =
                message;
        }
    }


    function setDetectionText(text) {

        if (detectionText) {

            detectionText.textContent =
                text;
        }
    }


    // =====================================================
    // EMPLOYEE RESULT
    // =====================================================

    function hideEmployeeResult() {

        if (employeeResultCard) {

            employeeResultCard.style.display =
                "none";
        }
    }


    function showEmployeeResult(
        employee,
        distance
    ) {

        if (!employeeResultCard) {
            return;
        }

        const fullName =
            `${employee.first_name || ""} ${employee.last_name || ""}`.trim();


        if (identifiedEmployeeName) {

            identifiedEmployeeName.textContent =
                fullName || "--";
        }


        if (identifiedEmployeeNumber) {

            identifiedEmployeeNumber.textContent =
                employee.employee_number || "--";
        }


        if (identifiedEmployeeDepartment) {

            identifiedEmployeeDepartment.textContent =
                employee.department_name ||
                "No Department";
        }


        if (identifiedEmployeePosition) {

            identifiedEmployeePosition.textContent =
                employee.position ||
                "No Position";
        }


        if (identifiedEmployeeScore) {

            identifiedEmployeeScore.textContent =
                distance !== undefined &&
                distance !== null
                    ? Number(distance).toFixed(2)
                    : "--";
        }


        employeeResultCard.style.display =
            "block";
    }


    // =====================================================
    // OTP STATUS
    // =====================================================

    function setOtpStatus(
        message,
        type = ""
    ) {

        if (!otpStatus) {
            return;
        }

        otpStatus.textContent =
            message;

        otpStatus.classList.remove(
            "text-success",
            "text-danger",
            "text-warning"
        );

        if (type) {

            otpStatus.classList.add(
                type
            );
        }
    }


    // =====================================================
    // OTP CARD RESET
    // =====================================================

    function resetOtpCard() {

        identifiedEmployeeId =
            null;

        attendanceVerified =
            false;

        otpVerificationInProgress =
            false;


        if (otpCard) {

            otpCard.style.setProperty(
                "display",
                "none",
                "important"
            );
        }


        if (otpDestination) {

            otpDestination.textContent =
                "Verification code will be sent to the employee's email.";
        }


        if (otpInputSection) {

            otpInputSection.style.setProperty(
                "display",
                "none",
                "important"
            );
        }


        if (otpInput) {

            otpInput.value = "";

            otpInput.disabled = false;
        }


        if (sendOtpBtn) {

            sendOtpBtn.disabled =
                false;

            sendOtpBtn.innerHTML = `
                <i class="bi bi-envelope me-2"></i>
                Send Verification Code
            `;
        }


        if (verifyOtpBtn) {

            verifyOtpBtn.disabled =
                false;

            verifyOtpBtn.innerHTML = `
                <i class="bi bi-check-circle me-2"></i>
                Verify & Record Attendance
            `;
        }


        setOtpStatus("");
    }


    // =====================================================
    // SHOW OTP CARD
    // =====================================================

    function showOtpCard(employee) {

        if (!otpCard) {

            console.error(
                "Face Recognition: otpCard element not found."
            );

            return;
        }


        identifiedEmployeeId =
            Number(employee.id);


        attendanceVerified =
            false;

        otpVerificationInProgress =
            false;


        otpCard.style.setProperty(
            "display",
            "block",
            "important"
        );


        if (otpDestination) {

            otpDestination.textContent =
                "A verification code will be sent to the employee's registered email address.";
        }


        if (otpInputSection) {

            otpInputSection.style.setProperty(
                "display",
                "none",
                "important"
            );
        }


        if (otpInput) {

            otpInput.value = "";

            otpInput.disabled = false;
        }


        if (sendOtpBtn) {

            sendOtpBtn.disabled =
                false;

            sendOtpBtn.innerHTML = `
                <i class="bi bi-envelope me-2"></i>
                Send Verification Code
            `;
        }


        if (verifyOtpBtn) {

            verifyOtpBtn.disabled =
                false;

            verifyOtpBtn.innerHTML = `
                <i class="bi bi-check-circle me-2"></i>
                Verify & Record Attendance
            `;
        }


        setOtpStatus("");
    }


    // =====================================================
    // CLEAR FACE BOX
    // =====================================================

    function clearFaceBox() {

        context.clearRect(
            0,
            0,
            canvas.width,
            canvas.height
        );
    }


    // =====================================================
    // DRAW FACE BOX
    // =====================================================

    function drawFaceBox(face) {

        clearFaceBox();

        if (!face) {
            return;
        }

        if (
            !video.videoWidth ||
            !video.videoHeight
        ) {
            return;
        }


        const scaleX =
            canvas.width /
            video.videoWidth;

        const scaleY =
            canvas.height /
            video.videoHeight;


        const x =
            face.x * scaleX;

        const y =
            face.y * scaleY;

        const width =
            face.width * scaleX;

        const height =
            face.height * scaleY;


        context.strokeStyle =
            "#4da3ff";

        context.lineWidth =
            3;

        context.strokeRect(
            x,
            y,
            width,
            height
        );


        const cornerSize =
            18;


        context.strokeStyle =
            "#4da3ff";

        context.lineWidth =
            4;


        // Top left
        context.beginPath();

        context.moveTo(
            x,
            y + cornerSize
        );

        context.lineTo(
            x,
            y
        );

        context.lineTo(
            x + cornerSize,
            y
        );

        context.stroke();


        // Top right
        context.beginPath();

        context.moveTo(
            x + width - cornerSize,
            y
        );

        context.lineTo(
            x + width,
            y
        );

        context.lineTo(
            x + width,
            y + cornerSize
        );

        context.stroke();


        // Bottom left
        context.beginPath();

        context.moveTo(
            x,
            y + height - cornerSize
        );

        context.lineTo(
            x,
            y + height
        );

        context.lineTo(
            x + cornerSize,
            y + height
        );

        context.stroke();


        // Bottom right
        context.beginPath();

        context.moveTo(
            x + width - cornerSize,
            y + height
        );

        context.lineTo(
            x + width,
            y + height
        );

        context.lineTo(
            x + width,
            y + height - cornerSize
        );

        context.stroke();
    }


    // =====================================================
    // CAPTURE CAMERA FRAME
    // =====================================================

    function captureFrame() {

        const tempCanvas =
            document.createElement("canvas");

        const width =
            video.videoWidth;

        const height =
            video.videoHeight;


        if (!width || !height) {
            return null;
        }


        tempCanvas.width =
            width;

        tempCanvas.height =
            height;


        const tempContext =
            tempCanvas.getContext("2d");


        if (!tempContext) {
            return null;
        }


        tempContext.drawImage(
            video,
            0,
            0,
            width,
            height
        );


        return tempCanvas.toDataURL(
            "image/jpeg",
            0.70
        );
    }


    // =====================================================
    // SEND OTP
    // =====================================================

    async function sendOtp(event) {

        // IMPORTANT:
        // Prevent form submission / page reload.
        if (event) {

            event.preventDefault();

            event.stopPropagation();
        }


        if (otpVerificationInProgress) {
            return;
        }


        if (!identifiedEmployeeId) {

            setOtpStatus(
                "No employee has been identified.",
                "text-danger"
            );

            return;
        }


        if (!sendOtpBtn) {

            console.error(
                "sendOtpBtn element not found."
            );

            return;
        }


        sendOtpBtn.disabled =
            true;


        sendOtpBtn.innerHTML = `
            <span
                class="spinner-border spinner-border-sm me-2"
                role="status"
                aria-hidden="true"
            ></span>
            Sending...
        `;


        setOtpStatus(
            "Sending verification code...",
            "text-warning"
        );


        try {

            console.log(
                "Sending OTP for employee:",
                identifiedEmployeeId
            );


            const response =
                await fetch(
                    "/face-recognition/send-otp",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "Accept":
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


            const responseText =
                await response.text();


            console.log(
                "Send OTP HTTP status:",
                response.status
            );


            console.log(
                "Send OTP raw response:",
                responseText
            );


            let result;


            try {

                result =
                    JSON.parse(
                        responseText
                    );

            } catch (parseError) {

                throw new Error(
                    "The server returned an invalid response."
                );
            }


            if (
                !response.ok ||
                !result.success
            ) {

                throw new Error(
                    result.message ||
                    "Unable to send verification code."
                );
            }


            // =================================================
            // OTP WAS SENT SUCCESSFULLY
            // =================================================

            console.log(
                "OTP sent successfully:",
                result
            );


            if (otpDestination) {

                otpDestination.textContent =
                    `Verification code sent to ${
                        result.destination ||
                        "the registered email address"
                    }.`;
            }


            // =================================================
            // CRITICAL FIX
            // =================================================
            // Force the OTP input section to become visible.
            // !important overrides any CSS hiding it.
            // =================================================

            if (otpInputSection) {

                otpInputSection.style.setProperty(
                    "display",
                    "block",
                    "important"
                );

                otpInputSection.style.setProperty(
                    "visibility",
                    "visible",
                    "important"
                );

                otpInputSection.style.setProperty(
                    "opacity",
                    "1",
                    "important"
                );

                otpInputSection.removeAttribute(
                    "hidden"
                );

                console.log(
                    "OTP input section is now visible."
                );

            } else {

                console.error(
                    "CRITICAL: otpInputSection element was not found."
                );
            }


            setOtpStatus(
                `Verification code sent. It expires in ${
                    result.expires_in || 5
                } minutes.`,
                "text-success"
            );


            sendOtpBtn.disabled =
                false;


            sendOtpBtn.innerHTML = `
                <i class="bi bi-arrow-repeat me-2"></i>
                Send New Code
            `;


            if (otpInput) {

                otpInput.disabled =
                    false;

                otpInput.focus();
            }


        } catch (error) {

            console.error(
                "Send OTP error:",
                error
            );


            setOtpStatus(
                error.message ||
                "Unable to send verification code.",
                "text-danger"
            );


            sendOtpBtn.disabled =
                false;


            sendOtpBtn.innerHTML = `
                <i class="bi bi-envelope me-2"></i>
                Send Verification Code
            `;
        }
    }


    // =====================================================
    // VERIFY OTP
    // =====================================================

    async function verifyOtp(event) {

        if (event) {

            event.preventDefault();

            event.stopPropagation();
        }


        if (otpVerificationInProgress) {
            return;
        }


        if (!identifiedEmployeeId) {

            setOtpStatus(
                "No employee has been identified.",
                "text-danger"
            );

            return;
        }


        if (!otpInput) {

            setOtpStatus(
                "OTP input field was not found.",
                "text-danger"
            );

            return;
        }


        const otp =
            otpInput.value
                .replace(/\D/g, "")
                .slice(0, 6);


        otpInput.value =
            otp;


        if (!/^\d{6}$/.test(otp)) {

            setOtpStatus(
                "Enter the 6-digit verification code.",
                "text-danger"
            );

            otpInput.focus();

            return;
        }


        if (!verifyOtpBtn) {
            return;
        }


        otpVerificationInProgress =
            true;


        verifyOtpBtn.disabled =
            true;


        verifyOtpBtn.innerHTML = `
            <span
                class="spinner-border spinner-border-sm me-2"
                role="status"
                aria-hidden="true"
            ></span>
            Verifying...
        `;


        setOtpStatus(
            "Verifying verification code...",
            "text-warning"
        );


        try {

            const response =
                await fetch(
                    "/face-recognition/verify-otp",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "Accept":
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


            console.log(
                "Verify OTP HTTP status:",
                response.status
            );


            console.log(
                "Verify OTP raw response:",
                responseText
            );


            let result;


            try {

                result =
                    JSON.parse(
                        responseText
                    );

            } catch (parseError) {

                throw new Error(
                    "The server returned an invalid response."
                );
            }


            if (
                !response.ok ||
                !result.success
            ) {

                throw new Error(
                    result.message ||
                    "Invalid verification code."
                );
            }


            attendanceVerified =
                true;


            otpVerificationInProgress =
                false;


            otpInput.disabled =
                true;


            verifyOtpBtn.disabled =
                true;


            verifyOtpBtn.innerHTML = `
                <i class="bi bi-check-circle-fill me-2"></i>
                Attendance Recorded
            `;


            setOtpStatus(
                result.message ||
                "Attendance recorded successfully.",
                "text-success"
            );


            setRecognitionStatus(
                "Attendance Recorded",
                result.message ||
                "Employee attendance has been recorded successfully."
            );


            setDetectionText(
                "Attendance Recorded"
            );


            console.log(
                "Attendance verification successful:",
                result
            );


            // Hide OTP card after a short delay.
            setTimeout(
                () => {

                    if (otpCard) {

                        otpCard.style.setProperty(
                            "display",
                            "none",
                            "important"
                        );
                    }

                },
                4000
            );


        } catch (error) {

            console.error(
                "Verify OTP error:",
                error
            );


            otpVerificationInProgress =
                false;


            verifyOtpBtn.disabled =
                false;


            verifyOtpBtn.innerHTML = `
                <i class="bi bi-check-circle me-2"></i>
                Verify & Record Attendance
            `;


            setOtpStatus(
                error.message ||
                "Unable to verify the code.",
                "text-danger"
            );


            otpInput.focus();
        }
    }


    // =====================================================
    // IDENTIFY EMPLOYEE
    // =====================================================

    async function identifyEmployee() {

        if (
            !recognitionRunning ||
            requestInProgress ||
            !cameraStream
        ) {
            return;
        }


        const image =
            captureFrame();


        if (!image) {
            return;
        }


        requestInProgress =
            true;


        try {

            const response =
                await fetch(
                    "/face-recognition/identify",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "Accept":
                                "application/json"
                        },

                        credentials:
                            "same-origin",

                        body:
                            JSON.stringify({
                                image:
                                    image
                            })
                    }
                );


            if (!response.ok) {

                throw new Error(
                    `Server returned HTTP ${response.status}`
                );
            }


            const result =
                await response.json();


            console.log(
                "Recognition response:",
                result
            );


            // =================================================
            // SERVER ERROR
            // =================================================

            if (!result.success) {

                setRecognitionStatus(
                    "Recognition Error",
                    result.message ||
                    "Unable to process the camera image."
                );


                setDetectionText(
                    "Recognition Error"
                );


                hideEmployeeResult();

                clearFaceBox();

                return;
            }


            // =================================================
            // NO FACE
            // =================================================

            if (
                result.face_detected === false
            ) {

                setRecognitionStatus(
                    "Searching for face",
                    "Position an employee inside the scanning area."
                );


                setDetectionText(
                    "No Face Detected"
                );


                hideEmployeeResult();

                resetOtpCard();

                clearFaceBox();

                return;
            }


            // =================================================
            // MULTIPLE FACES
            // =================================================

            if (
                result.multiple_faces
            ) {

                setRecognitionStatus(
                    "Multiple faces detected",
                    result.message ||
                    "Only one employee should be visible."
                );


                setDetectionText(
                    "Multiple Faces"
                );


                hideEmployeeResult();

                resetOtpCard();

                clearFaceBox();

                return;
            }


            // =================================================
            // UNKNOWN EMPLOYEE
            // =================================================

            if (
                !result.recognized
            ) {

                setRecognitionStatus(
                    "Employee not recognized",
                    result.message ||
                    "The detected face does not match an enrolled employee."
                );


                setDetectionText(
                    "Unknown Employee"
                );


                hideEmployeeResult();

                resetOtpCard();


                if (result.face) {

                    drawFaceBox(
                        result.face
                    );
                }


                return;
            }


            // =================================================
            // EMPLOYEE IDENTIFIED
            // =================================================

            const employee =
                result.employee;


            if (!employee) {

                setRecognitionStatus(
                    "Recognition Error",
                    "Employee information was not returned."
                );


                setDetectionText(
                    "Recognition Error"
                );


                hideEmployeeResult();

                resetOtpCard();

                return;
            }


            const fullName =
                `${employee.first_name || ""} ${
                    employee.last_name || ""
                }`.trim();


            // =================================================
            // FACE BOX
            // =================================================

            if (result.face) {

                drawFaceBox(
                    result.face
                );
            }


            // =================================================
            // STATUS
            // =================================================

            setRecognitionStatus(
                "Employee Identified",
                `${fullName} • ${
                    employee.employee_number || "--"
                }`
            );


            setDetectionText(
                "Employee Identified"
            );


            // =================================================
            // EMPLOYEE RESULT
            // =================================================

            showEmployeeResult(
                employee,
                result.confidence
            );


            // =================================================
            // OTP
            // =================================================

            if (
                Number(identifiedEmployeeId) !==
                Number(employee.id)
            ) {

                showOtpCard(
                    employee
                );
            }


            // =================================================
            // LOGGING
            // =================================================

            const now =
                Date.now();


            if (
                lastRecognizedEmployeeId !==
                    employee.id
                ||
                now - lastRecognitionTime >
                    RECOGNITION_COOLDOWN
            ) {

                console.log(
                    "Employee identified:",
                    employee
                );


                lastRecognizedEmployeeId =
                    employee.id;


                lastRecognitionTime =
                    now;
            }


            // Stop repeated recognition requests.
            stopRecognition();


        } catch (error) {

            console.error(
                "Face recognition request failed:",
                error
            );


            setRecognitionStatus(
                "Connection Error",
                "Unable to communicate with the recognition server."
            );


            setDetectionText(
                "Server Error"
            );


            hideEmployeeResult();


        } finally {

            requestInProgress =
                false;
        }
    }


    // =====================================================
    // START RECOGNITION
    // =====================================================

    function startRecognition() {

        if (recognitionRunning) {
            return;
        }


        recognitionRunning =
            true;


        setRecognitionStatus(
            "Searching for face",
            "Position an employee inside the scanning area."
        );


        setDetectionText(
            "Face Recognition Active"
        );


        hideEmployeeResult();

        resetOtpCard();


        identifyEmployee();


        recognitionTimer =
            setInterval(
                identifyEmployee,
                RECOGNITION_INTERVAL
            );
    }


    // =====================================================
    // STOP RECOGNITION
    // =====================================================

    function stopRecognition() {

        recognitionRunning =
            false;


        if (recognitionTimer) {

            clearInterval(
                recognitionTimer
            );

            recognitionTimer =
                null;
        }


        clearFaceBox();
    }


    // =====================================================
    // START CAMERA
    // =====================================================

    async function startCamera() {

        if (cameraStream) {
            return;
        }


        if (
            !navigator.mediaDevices ||
            !navigator.mediaDevices.getUserMedia
        ) {

            setRecognitionStatus(
                "Camera unavailable",
                "Your browser does not support camera access."
            );


            setDetectionText(
                "Camera Unavailable"
            );


            return;
        }


        try {

            attendanceVerified =
                false;

            lastRecognizedEmployeeId =
                null;

            lastRecognitionTime =
                0;


            hideEmployeeResult();

            resetOtpCard();

            clearFaceBox();


            cameraStream =
                await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: "user",

                        width: {
                            ideal: 1280
                        },

                        height: {
                            ideal: 720
                        }
                    },

                    audio: false
                });


            video.srcObject =
                cameraStream;


            await new Promise(
                (resolve) => {

                    if (
                        video.readyState >= 1
                    ) {

                        resolve();

                        return;
                    }


                    video.addEventListener(
                        "loadedmetadata",
                        resolve,
                        {
                            once: true
                        }
                    );
                }
            );


            await video.play();


            canvas.width =
                video.videoWidth;

            canvas.height =
                video.videoHeight;


            cameraContainer.classList.add(
                "camera-active"
            );


            if (startCameraBtn) {

                startCameraBtn.disabled =
                    true;
            }


            if (stopCameraBtn) {

                stopCameraBtn.disabled =
                    false;
            }


            setCameraOnline();


            if (cameraResolution) {

                cameraResolution.textContent =
                    `${video.videoWidth} × ${video.videoHeight}`;
            }


            setRecognitionStatus(
                "Searching for face",
                "Position an employee inside the scanning area."
            );


            setDetectionText(
                "Face Recognition Active"
            );


            startRecognition();


        } catch (error) {

            console.error(
                "Camera startup error:",
                error
            );


            if (cameraStream) {

                cameraStream
                    .getTracks()
                    .forEach(
                        track => {
                            track.stop();
                        }
                    );


                cameraStream =
                    null;
            }


            video.srcObject =
                null;


            cameraContainer.classList.remove(
                "camera-active"
            );


            if (startCameraBtn) {

                startCameraBtn.disabled =
                    false;
            }


            if (stopCameraBtn) {

                stopCameraBtn.disabled =
                    true;
            }


            setCameraOffline();


            if (
                error.name ===
                "NotAllowedError"
            ) {

                setRecognitionStatus(
                    "Camera permission denied",
                    "Allow camera access in your browser and try again."
                );


                setDetectionText(
                    "Permission Required"
                );


            } else if (
                error.name ===
                "NotFoundError"
            ) {

                setRecognitionStatus(
                    "No camera found",
                    "Connect a camera and try again."
                );


                setDetectionText(
                    "Camera Not Found"
                );


            } else {

                setRecognitionStatus(
                    "Camera error",
                    error.message ||
                    "Unable to start the camera."
                );


                setDetectionText(
                    "Camera Error"
                );
            }
        }
    }


    // =====================================================
    // STOP CAMERA
    // =====================================================

    function stopCamera() {

        stopRecognition();


        if (cameraStream) {

            cameraStream
                .getTracks()
                .forEach(
                    track => {
                        track.stop();
                    }
                );


            cameraStream =
                null;
        }


        video.srcObject =
            null;


        cameraContainer.classList.remove(
            "camera-active"
        );


        if (startCameraBtn) {

            startCameraBtn.disabled =
                false;
        }


        if (stopCameraBtn) {

            stopCameraBtn.disabled =
                true;
        }


        if (cameraResolution) {

            cameraResolution.textContent =
                "Camera ready";
        }


        setRecognitionStatus(
            "Waiting for camera",
            "Start the camera to begin scanning."
        );


        setDetectionText(
            "Face Recognition Standby"
        );


        hideEmployeeResult();

        resetOtpCard();

        clearFaceBox();

        setCameraOffline();
    }


    // =====================================================
    // SEND OTP BUTTON
    // =====================================================

    if (sendOtpBtn) {

        sendOtpBtn.addEventListener(
            "click",
            (event) => {

                event.preventDefault();

                event.stopPropagation();

                sendOtp(event);
            }
        );

    } else {

        console.warn(
            "sendOtpBtn element was not found."
        );
    }


    // =====================================================
    // VERIFY OTP BUTTON
    // =====================================================

    if (verifyOtpBtn) {

        verifyOtpBtn.addEventListener(
            "click",
            (event) => {

                event.preventDefault();

                event.stopPropagation();

                verifyOtp(event);
            }
        );

    } else {

        console.warn(
            "verifyOtpBtn element was not found."
        );
    }


    // =====================================================
    // OTP FORM PROTECTION
    // =====================================================

    if (verifyOtpBtn) {

        const otpForm =
            verifyOtpBtn.closest("form");


        if (otpForm) {

            otpForm.addEventListener(
                "submit",
                (event) => {

                    event.preventDefault();

                    event.stopPropagation();

                    verifyOtp(event);
                }
            );
        }
    }


    if (sendOtpBtn) {

        const sendOtpForm =
            sendOtpBtn.closest("form");


        if (sendOtpForm) {

            sendOtpForm.addEventListener(
                "submit",
                (event) => {

                    event.preventDefault();

                    event.stopPropagation();

                    sendOtp(event);
                }
            );
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


        otpInput.addEventListener(
            "keydown",
            (event) => {

                if (
                    event.key ===
                    "Enter"
                ) {

                    event.preventDefault();

                    event.stopPropagation();

                    verifyOtp(event);
                }
            }
        );
    }


    // =====================================================
    // CAMERA BUTTONS
    // =====================================================

    if (startCameraBtn) {

        startCameraBtn.addEventListener(
            "click",
            (event) => {

                event.preventDefault();

                startCamera();
            }
        );
    }


    if (stopCameraBtn) {

        stopCameraBtn.addEventListener(
            "click",
            (event) => {

                event.preventDefault();

                stopCamera();
            }
        );
    }


    // =====================================================
    // CLEANUP
    // =====================================================

    window.addEventListener(
        "beforeunload",
        () => {

            stopCamera();
        }
    );


    // =====================================================
    // INITIAL STATE
    // =====================================================

    setCameraOffline();


    setRecognitionStatus(
        "Waiting for camera",
        "Start the camera to begin scanning."
    );


    setDetectionText(
        "Face Recognition Standby"
    );


    hideEmployeeResult();

    resetOtpCard();


    // =====================================================
    // DEBUG
    // =====================================================

    console.log(
        "Face Recognition JavaScript loaded successfully."
    );

});