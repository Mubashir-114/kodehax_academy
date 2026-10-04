(() => {
    "use strict";

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const header = document.querySelector("[data-site-header]");
    const updateHeader = () => header?.classList.toggle("is-scrolled", window.scrollY > 28);

    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });

    document.querySelectorAll("[data-dismiss-message]").forEach((button) => {
        button.addEventListener("click", () => button.closest(".flash-message")?.remove());
    });

    const revealItems = document.querySelectorAll(".reveal");
    if (reducedMotion || !("IntersectionObserver" in window)) {
        revealItems.forEach((item) => item.classList.add("is-visible"));
    } else {
        const revealObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.14, rootMargin: "0px 0px -48px" });
        revealItems.forEach((item) => revealObserver.observe(item));
    }

    const tabs = [...document.querySelectorAll("[data-program-tab]")];
    const panels = [...document.querySelectorAll("[data-program-panel]")];

    const selectProgram = (tab, focus = false) => {
        const target = tab.dataset.programTab;
        tabs.forEach((item) => {
            const active = item === tab;
            item.classList.toggle("is-active", active);
            item.setAttribute("aria-selected", String(active));
            item.tabIndex = active ? 0 : -1;
        });
        panels.forEach((panel) => {
            const active = panel.dataset.programPanel === target;
            panel.hidden = !active;
            panel.classList.toggle("is-active", active);
        });
        if (focus) tab.focus();
    };

    tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => selectProgram(tab));
        tab.addEventListener("keydown", (event) => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            let next = index;
            if (event.key === "ArrowDown") next = (index + 1) % tabs.length;
            if (event.key === "ArrowUp") next = (index - 1 + tabs.length) % tabs.length;
            if (event.key === "Home") next = 0;
            if (event.key === "End") next = tabs.length - 1;
            selectProgram(tabs[next], true);
        });
    });

    document.querySelectorAll("[data-accordion]").forEach((accordion) => {
        const items = [...accordion.querySelectorAll(".support-item")];
        items.forEach((item) => {
            const trigger = item.querySelector("button");
            trigger?.addEventListener("click", () => {
                const opening = !item.classList.contains("is-open");
                items.forEach((entry) => {
                    entry.classList.remove("is-open");
                    entry.querySelector("button")?.setAttribute("aria-expanded", "false");
                });
                if (opening) {
                    item.classList.add("is-open");
                    trigger.setAttribute("aria-expanded", "true");
                }
            });
        });
    });

    document.querySelectorAll("[data-auth-form]").forEach((form) => {
        form.querySelectorAll("input, select, textarea").forEach((input) => {
            input.classList.add("auth-input");
            const wrapper = input.parentElement;
            if (!wrapper?.classList.contains("auth-input-shell") || input.type !== "password") return;
            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "auth-password-toggle";
            toggle.textContent = "Show";
            toggle.setAttribute("aria-label", "Show password");
            wrapper.appendChild(toggle);
            toggle.addEventListener("click", () => {
                const hidden = input.type === "password";
                input.type = hidden ? "text" : "password";
                toggle.textContent = hidden ? "Hide" : "Show";
                toggle.setAttribute("aria-label", `${hidden ? "Hide" : "Show"} password`);
            });
        });
    });

    const counters = document.querySelectorAll("[data-count]");
    const animateCounter = (element) => {
        const target = Number(element.dataset.count || 0);
        if (reducedMotion) {
            element.textContent = target;
            return;
        }
        const start = performance.now();
        const duration = 1250;
        const tick = (now) => {
            const elapsed = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - elapsed, 3);
            element.textContent = Math.round(target * eased);
            if (elapsed < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    };

    if ("IntersectionObserver" in window) {
        const counterObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                animateCounter(entry.target);
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.55 });
        counters.forEach((counter) => counterObserver.observe(counter));
    } else {
        counters.forEach(animateCounter);
    }
})();
