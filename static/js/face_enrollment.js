document.addEventListener("DOMContentLoaded", function () {

    const video = document.getElementById("enrollmentCamera");
    const placeholder = document.getElementById("cameraPlaceholder");
    const startCameraBtn = document.getElementById("startEnrollmentCamera");
    const captureFaceBtn = document.getElementById("captureFaceBtn");
    const cameraStatus = document.getElementById("enrollmentCameraStatus");
    const faceGuide = document.getElementById("faceGuide");

    let cameraStream = null;

    // =========================================================
    // START CAMERA
    // =========================================================

    async function startCamera() {

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {

            alert("Camera access is not supported by this browser.");
            return;
        }

        try {

            cameraStream = await navigator.mediaDevices.getUserMedia({
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

            video.srcObject = cameraStream;

            await video.play();

            placeholder.style.display = "none";
            video.style.display = "block";

            if (faceGuide) {
                faceGuide.classList.add("active");
            }

            if (captureFaceBtn) {
                captureFaceBtn.disabled = false;
            }

            if (cameraStatus) {
                cameraStatus.textContent = "Camera Live";
            }

        } catch (error) {

            console.error("Camera error:", error);

            if (error.name === "NotAllowedError") {

                alert(
                    "Camera permission was denied. Please allow camera access and try again."
                );

            } else if (error.name === "NotFoundError") {

                alert(
                    "No camera was found on this device."
                );

            } else {

                alert(
                    "Unable to start the camera. Please check your camera connection."
                );
            }
        }
    }


    // =========================================================
// CAPTURE FACE
// =========================================================

async function captureFace() {

    if (!video || !cameraStream) {
        return;
    }

    if (video.videoWidth === 0 || video.videoHeight === 0) {

        alert("Camera is not ready yet.");

        return;
    }

    // ---------------------------------------------
    // CREATE CANVAS
    // ---------------------------------------------

    const canvas = document.createElement("canvas");

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const context = canvas.getContext("2d");

    context.drawImage(
        video,
        0,
        0,
        canvas.width,
        canvas.height
    );


    // ---------------------------------------------
    // CONVERT TO JPEG
    // ---------------------------------------------

    const imageData = canvas.toDataURL(
        "image/jpeg",
        0.90
    );


    // ---------------------------------------------
    // DISABLE BUTTON
    // ---------------------------------------------

    captureFaceBtn.disabled = true;

    const originalHTML = captureFaceBtn.innerHTML;

    captureFaceBtn.innerHTML = `
        <span class="spinner-border spinner-border-sm"
              aria-hidden="true"></span>
        Saving...
    `;


    // ---------------------------------------------
    // SEND TO FLASK
    // ---------------------------------------------

    try {

        const employeeId =
            window.location.pathname.split("/").filter(Boolean).pop();


        const response = await fetch(
            `/face-enrollment/${employeeId}/capture`,
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    image: imageData
                })
            }
        );


        const result = await response.json();


        if (!response.ok || !result.success) {

            throw new Error(
                result.message || "Unable to save image."
            );
        }


        // -----------------------------------------
        // UPDATE COUNTER
        // -----------------------------------------

        const imageCount =
            document.getElementById("imageCount");

        if (imageCount) {

            imageCount.textContent =
                `${result.image_count}/10`;
        }


        const progressNumber =
            document.getElementById("progressNumber");

        if (progressNumber) {

            progressNumber.textContent =
                result.image_count;
        }


        // -----------------------------------------
        // UPDATE PROGRESS BAR
        // -----------------------------------------

        const progressBar =
            document.getElementById("captureProgressBar");

        if (progressBar) {

            progressBar.style.width =
                `${(result.image_count / 10) * 100}%`;
        }


        // -----------------------------------------
        // SUCCESS FEEDBACK
        // -----------------------------------------

        captureFaceBtn.innerHTML = `
            <i class="bi bi-check-circle-fill"></i>
            Captured
        `;


        setTimeout(function () {

            if (result.face_trained) {

                captureFaceBtn.innerHTML = `
                    <i class="bi bi-check-circle-fill"></i>
                    Enrollment Complete
                `;

                captureFaceBtn.disabled = true;

                if (cameraStatus) {
                    cameraStatus.textContent =
                        "Enrollment Complete";
                }

            } else {

                captureFaceBtn.innerHTML =
                    originalHTML;

                captureFaceBtn.disabled = false;

            }

        }, 900);


    } catch (error) {

        console.error(
            "Face capture error:",
            error
        );

        alert(
            error.message ||
            "Unable to save the captured image."
        );

        captureFaceBtn.innerHTML =
            originalHTML;

        captureFaceBtn.disabled = false;
    }
}
    // =========================================================
    // CAPTURE FEEDBACK
    // =========================================================

    function showCaptureFeedback() {

        if (!captureFaceBtn) {
            return;
        }

        const originalHTML = captureFaceBtn.innerHTML;

        captureFaceBtn.disabled = true;

        captureFaceBtn.innerHTML = `
            <i class="bi bi-check-circle-fill"></i>
            Captured
        `;


        setTimeout(function () {

            captureFaceBtn.disabled = false;

            captureFaceBtn.innerHTML = originalHTML;

        }, 1000);
    }


    // =========================================================
    // BUTTON EVENTS
    // =========================================================

    if (startCameraBtn) {

        startCameraBtn.addEventListener(
            "click",
            startCamera
        );

    }


    if (captureFaceBtn) {

        captureFaceBtn.addEventListener(
            "click",
            captureFace
        );

    }


    // =========================================================
    // STOP CAMERA WHEN LEAVING PAGE
    // =========================================================

    window.addEventListener(
        "beforeunload",
        function () {

            if (cameraStream) {

                cameraStream
                    .getTracks()
                    .forEach(function (track) {
                        track.stop();
                    });

            }

        }
    );

});