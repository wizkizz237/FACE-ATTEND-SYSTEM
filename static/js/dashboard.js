document.addEventListener("DOMContentLoaded", function () {

    /* =====================================================
       MOBILE SIDEBAR
    ====================================================== */

    const mobileMenuBtn =
        document.getElementById("mobileMenuBtn");

    const sidebar =
        document.querySelector(".sidebar");

    if (mobileMenuBtn && sidebar) {

        mobileMenuBtn.addEventListener(
            "click",
            function () {

                sidebar.classList.toggle("open");

            }
        );

    }


    /* =====================================================
       NOTIFICATION ELEMENTS
    ====================================================== */

    const notificationButton =
        document.getElementById("notificationButton");

    const notificationDropdown =
        document.getElementById("notificationDropdown");

    const notificationCount =
        document.getElementById("notificationCount");

    const notificationList =
        document.getElementById("notificationList");

    const markAllButton =
        document.getElementById("markAllNotifications");


    if (
        !notificationButton ||
        !notificationDropdown ||
        !notificationCount ||
        !notificationList
    ) {

        return;

    }


    /* =====================================================
       NOTIFICATION ICON
    ====================================================== */

    function getNotificationIcon(type) {

        switch (type) {

            case "success":
                return "bi-check-circle";

            case "warning":
                return "bi-exclamation-triangle";

            case "error":
                return "bi-x-circle";

            default:
                return "bi-info-circle";
        }

    }


    /* =====================================================
       FORMAT TIME
    ====================================================== */

    function formatNotificationTime(dateString) {

        if (!dateString) {
            return "";
        }

        const date =
            new Date(
                dateString.replace(" ", "T")
            );

        if (Number.isNaN(date.getTime())) {
            return dateString;
        }

        const now = new Date();

        const difference =
            Math.floor(
                (now - date) / 1000
            );

        if (difference < 60) {
            return "Just now";
        }

        if (difference < 3600) {

            return (
                Math.floor(
                    difference / 60
                ) + " min ago"
            );

        }

        if (difference < 86400) {

            return (
                Math.floor(
                    difference / 3600
                ) + " hr ago"
            );

        }

        if (difference < 172800) {
            return "Yesterday";
        }

        return date.toLocaleDateString(
            undefined,
            {
                day: "2-digit",
                month: "short",
                year: "numeric"
            }
        );

    }


    /* =====================================================
       LOAD NOTIFICATIONS
    ====================================================== */

    async function loadNotifications() {

        try {

            const response =
                await fetch(
                    "/api/notifications",
                    {
                        method: "GET",
                        headers: {
                            "Accept": "application/json"
                        }
                    }
                );

            if (!response.ok) {

                throw new Error(
                    "Unable to load notifications."
                );

            }

            const data =
                await response.json();

            if (!data.success) {

                throw new Error(
                    data.message ||
                    "Unable to load notifications."
                );

            }


            /* =============================================
               UPDATE COUNT
            ============================================== */

            const unreadCount =
                Number(
                    data.unread_count || 0
                );

            notificationCount.textContent =
                unreadCount > 99
                    ? "99+"
                    : unreadCount;

            if (unreadCount > 0) {

                notificationCount.classList.add(
                    "visible"
                );

            } else {

                notificationCount.classList.remove(
                    "visible"
                );

            }


            /* =============================================
               EMPTY STATE
            ============================================== */

            if (
                !data.notifications ||
                data.notifications.length === 0
            ) {

                notificationList.innerHTML = `

                    <div class="notification-empty">

                        <i class="bi bi-bell-slash"></i>

                        <span>
                            No notifications available.
                        </span>

                    </div>

                `;

                return;

            }


            /* =============================================
               BUILD NOTIFICATIONS
            ============================================== */

            notificationList.innerHTML =
                data.notifications
                    .map(function (notification) {

                        const type =
                            notification.notification_type ||
                            "info";

                        const icon =
                            getNotificationIcon(
                                type
                            );

                        const unread =
                            Number(
                                notification.is_read
                            ) === 0;

                        return `

                            <div
                                class="notification-item
                                ${unread ? "unread" : ""}"
                                data-id="${notification.id}"
                            >

                                <div
                                    class="
                                        notification-icon
                                        ${type}
                                    "
                                >

                                    <i
                                        class="
                                            bi
                                            ${icon}
                                        "
                                    ></i>

                                </div>


                                <div
                                    class="notification-content"
                                >

                                    <div
                                        class="
                                            notification-title
                                        "
                                    >

                                        <span>
                                            ${escapeHtml(
                                                notification.title
                                            )}
                                        </span>

                                    </div>


                                    <div
                                        class="
                                            notification-message
                                        "
                                    >
                                        ${escapeHtml(
                                            notification.message
                                        )}
                                    </div>


                                    <div
                                        class="
                                            notification-time
                                        "
                                    >
                                        ${formatNotificationTime(
                                            notification.created_at
                                        )}
                                    </div>

                                </div>


                                ${
                                    unread
                                        ? `
                                            <span
                                                class="
                                                    notification-unread-dot
                                                "
                                            ></span>
                                        `
                                        : ""
                                }

                            </div>

                        `;

                    })
                    .join("");


            /* =============================================
               CLICK NOTIFICATION
            ============================================== */

            document
                .querySelectorAll(
                    ".notification-item"
                )
                .forEach(function (item) {

                    item.addEventListener(
                        "click",
                        async function () {

                            const id =
                                item.dataset.id;

                            if (!id) {
                                return;
                            }

                            try {

                                await fetch(
                                    `/api/notifications/${id}/read`,
                                    {
                                        method: "POST",
                                        headers: {
                                            "Accept":
                                                "application/json"
                                        }
                                    }
                                );

                                item.classList.remove(
                                    "unread"
                                );

                                const dot =
                                    item.querySelector(
                                        ".notification-unread-dot"
                                    );

                                if (dot) {
                                    dot.remove();
                                }

                                loadNotifications();

                            } catch (error) {

                                console.error(
                                    "Notification read error:",
                                    error
                                );

                            }

                        }
                    );

                });

        } catch (error) {

            console.error(
                "Notification loading error:",
                error
            );

            notificationList.innerHTML = `

                <div class="notification-empty">

                    <i class="bi bi-exclamation-circle"></i>

                    <span>
                        Unable to load notifications.
                    </span>

                </div>

            `;

        }

    }


    /* =====================================================
       ESCAPE HTML
    ====================================================== */

    function escapeHtml(value) {

        const div =
            document.createElement("div");

        div.textContent =
            value ?? "";

        return div.innerHTML;

    }


    /* =====================================================
       TOGGLE DROPDOWN
    ====================================================== */

    notificationButton.addEventListener(
        "click",
        function (event) {

            event.stopPropagation();

            notificationDropdown.classList.toggle(
                "open"
            );

        }
    );


    /* =====================================================
       CLOSE DROPDOWN
    ====================================================== */

    document.addEventListener(
        "click",
        function (event) {

            if (
                !notificationDropdown.contains(
                    event.target
                ) &&
                !notificationButton.contains(
                    event.target
                )
            ) {

                notificationDropdown.classList.remove(
                    "open"
                );

            }

        }
    );


    /* =====================================================
       MARK ALL READ
    ====================================================== */

    if (markAllButton) {

        markAllButton.addEventListener(
            "click",
            async function (event) {

                event.stopPropagation();

                try {

                    const response =
                        await fetch(
                            "/api/notifications/read-all",
                            {
                                method: "POST",
                                headers: {
                                    "Accept":
                                        "application/json"
                                }
                            }
                        );

                    const data =
                        await response.json();

                    if (data.success) {

                        await loadNotifications();

                    }

                } catch (error) {

                    console.error(
                        "Mark all notifications error:",
                        error
                    );

                }

            }
        );

    }


    /* =====================================================
       INITIAL LOAD
    ====================================================== */

    loadNotifications();


    /* =====================================================
       REFRESH PERIODICALLY
    ====================================================== */

    setInterval(
        loadNotifications,
        30000
    );

});