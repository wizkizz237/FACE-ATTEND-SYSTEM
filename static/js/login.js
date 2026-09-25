document.addEventListener("DOMContentLoaded", function () {

    const loginForm = document.getElementById("loginForm");

    const username = document.getElementById("username");

    const password = document.getElementById("password");

    const passwordToggle =
        document.getElementById("passwordToggle");

    const signInButton =
        document.getElementById("signInButton");

    const buttonContent =
        signInButton
            ? signInButton.querySelector(".button-content")
            : null;

    const buttonLoading =
        signInButton
            ? signInButton.querySelector(".button-loading")
            : null;

    const forgotPassword =
        document.getElementById("forgotPassword");


    /* =====================================================
       PASSWORD SHOW / HIDE
    ===================================================== */

    if (passwordToggle && password) {

        passwordToggle.addEventListener("click", function () {

            const isPassword =
                password.type === "password";

            password.type =
                isPassword ? "text" : "password";

            const icon =
                passwordToggle.querySelector("i");

            if (icon) {

                icon.className =
                    isPassword
                        ? "bi bi-eye-slash"
                        : "bi bi-eye";

            }

            passwordToggle.setAttribute(
                "aria-label",
                isPassword
                    ? "Hide password"
                    : "Show password"
            );

        });

    }


    /* =====================================================
       CLEAR ERROR VISUALS
    ===================================================== */

    [username, password].forEach(function (field) {

        if (!field) {
            return;
        }

        field.addEventListener("input", function () {

            field.classList.remove("input-error");

        });

    });


    /* =====================================================
       FORM SUBMISSION
    ===================================================== */

    if (loginForm) {

        loginForm.addEventListener("submit", function (event) {

            let valid = true;


            if (!username.value.trim()) {

                username.classList.add("input-error");

                valid = false;

            }


            if (!password.value.trim()) {

                password.classList.add("input-error");

                valid = false;

            }


            if (!valid) {

                event.preventDefault();

                if (!username.value.trim()) {
                    username.focus();
                } else {
                    password.focus();
                }

                return;
            }


            /*
             * Show loading state.
             */

            if (signInButton) {

                signInButton.disabled = true;

                if (buttonContent) {
                    buttonContent.style.display = "none";
                }

                if (buttonLoading) {
                    buttonLoading.style.display = "inline-flex";
                }

            }

        });

    }


    /* =====================================================
       FORGOT PASSWORD
    ===================================================== */

    if (forgotPassword) {

        forgotPassword.addEventListener("click", function (event) {

            event.preventDefault();

            showNotification(
                "Please contact the system administrator to reset your password."
            );

        });

    }


    /* =====================================================
       AUTO FOCUS
    ===================================================== */

    if (username && !username.value.trim()) {
        username.focus();
    }


    /* =====================================================
       ENTER KEY
    ===================================================== */

    document.addEventListener("keydown", function (event) {

        if (event.key === "Enter") {

            const active =
                document.activeElement;

            if (
                active === username ||
                active === password
            ) {

                loginForm.requestSubmit();

            }

        }

    });


    /* =====================================================
       ESCAPE - HIDE PASSWORD
    ===================================================== */

    document.addEventListener("keydown", function (event) {

        if (event.key === "Escape") {

            if (
                password &&
                password.type === "text"
            ) {

                password.type = "password";

                const icon =
                    passwordToggle.querySelector("i");

                if (icon) {
                    icon.className = "bi bi-eye";
                }

            }

        }

    });


    /* =====================================================
       NOTIFICATION
    ===================================================== */

    function showNotification(message) {

        const existing =
            document.querySelector(".login-toast");

        if (existing) {
            existing.remove();
        }


        const toast =
            document.createElement("div");

        toast.className = "login-toast";

        toast.innerHTML = `
            <i class="bi bi-info-circle me-2"></i>
            ${message}
        `;


        document.body.appendChild(toast);


        setTimeout(function () {

            toast.classList.add("show");

        }, 50);


        setTimeout(function () {

            toast.classList.remove("show");

            setTimeout(function () {
                toast.remove();
            }, 300);

        }, 4000);

    }

});