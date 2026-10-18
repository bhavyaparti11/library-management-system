// Small progressive enhancements. Every feature still works without JavaScript.
document.addEventListener("DOMContentLoaded", () => {
    // Notifications: close button, and success messages fade out after 6 seconds.
    document.querySelectorAll(".toast").forEach((toast) => {
        const dismiss = () => {
            toast.classList.add("toast-hide");
            setTimeout(() => toast.remove(), 300);
        };
        const closeButton = toast.querySelector("[data-dismiss]");
        if (closeButton) {
            closeButton.addEventListener("click", dismiss);
        }
        if (toast.classList.contains("toast-success")) {
            setTimeout(dismiss, 6000);
        }
    });

    // Ask for confirmation before destructive actions such as deleting a book.
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });

    // Open and close the sidebar menu on small screens.
    const sidebar = document.getElementById("sidebar");
    const toggles = document.querySelectorAll("[data-toggle-sidebar]");
    toggles.forEach((toggle) => {
        toggle.addEventListener("click", () => {
            const isOpen = sidebar.classList.toggle("open");
            toggles.forEach((t) => t.setAttribute("aria-expanded", String(isOpen)));
        });
    });
});
