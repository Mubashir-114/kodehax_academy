/**
 * Presentation-only behaviour for the profile Security → login 2FA panel.
 *
 * This script only mirrors the chosen preset and previews when the compact
 * password field is needed. It never authorizes or persists a policy change;
 * all security decisions and validation live on the server.
 */
(() => {
    "use strict";

    const setHidden = (element, hidden) => {
        if (!element) return;
        if (hidden) {
            element.setAttribute("hidden", "");
        } else {
            element.removeAttribute("hidden");
        }
    };

    const initForm = (form) => {
        const toggle = form.querySelector("[data-2fa-toggle]");
        const config = form.querySelector("[data-2fa-config]");
        const stateLabel = form.querySelector("[data-2fa-state]");
        const offNote = form.querySelector("[data-2fa-off-note]");
        const daysBlock = form.querySelector("[data-2fa-days-block]");
        const daysLabel = form.querySelector("[data-days-label]");
        const daysInput = form.querySelector("[data-days-input]");
        const modeInputs = Array.from(form.querySelectorAll("[data-2fa-mode]"));
        const presets = Array.from(form.querySelectorAll("[data-days-preset]"));
        const reauthBlock = form.querySelector("[data-reauth-password]");
        const passwordInput = reauthBlock
            ? reauthBlock.querySelector('input[name="current_password"]')
            : null;

        const currentMode = () => {
            const checked = modeInputs.find((input) => input.checked);
            return checked ? checked.value : "interval";
        };

        const syncDaysBlock = () => {
            const mode = currentMode();
            const isEveryLogin = mode === "every_login";
            setHidden(daysBlock, isEveryLogin);
            if (daysLabel) {
                daysLabel.textContent = mode === "inactivity" ? "After inactivity of" : "Every";
            }
        };

        const syncEnabled = () => {
            const enabled = Boolean(toggle && toggle.checked);
            setHidden(config, !enabled);
            setHidden(offNote, enabled);
            if (stateLabel) {
                stateLabel.textContent = enabled ? "ON" : "OFF";
            }
            if (enabled) {
                syncDaysBlock();
            }
        };

        const highlightPresets = (value) => {
            presets.forEach((button) => {
                button.classList.toggle(
                    "is-active",
                    button.dataset.daysPreset === String(value)
                );
            });
        };

        const policyIsWeaker = () => {
            const oldEnabled = form.dataset.currentEnabled === "true";
            const enabled = Boolean(toggle && toggle.checked);
            if (!oldEnabled || !enabled) return oldEnabled && !enabled;

            const oldMode = form.dataset.currentMode;
            const mode = currentMode();
            if (oldMode === "every_login") return mode !== "every_login";
            if (mode === "every_login") return false;
            if (oldMode !== mode) return true;
            return Number(daysInput && daysInput.value) > Number(form.dataset.currentDays);
        };

        const syncReauthPrompt = (force = false) => {
            if (!reauthBlock) return;
            const required = form.dataset.recentOtp !== "true" && (force || policyIsWeaker());
            setHidden(reauthBlock, !required);
            if (passwordInput) {
                passwordInput.required = required;
                if (required) passwordInput.autocomplete = "current-password";
            }
        };

        if (toggle) {
            toggle.addEventListener("change", () => {
                syncEnabled();
                syncReauthPrompt();
            });
        }
        modeInputs.forEach((input) => {
            input.addEventListener("change", () => {
                syncDaysBlock();
                syncReauthPrompt();
            });
        });
        presets.forEach((button) => {
            button.addEventListener("click", () => {
                if (daysInput) {
                    daysInput.value = button.dataset.daysPreset;
                }
                highlightPresets(button.dataset.daysPreset);
            });
        });
        if (daysInput) {
            daysInput.addEventListener("input", () => {
                highlightPresets(daysInput.value);
                syncReauthPrompt();
            });
        }

        form.addEventListener("submit", (event) => {
            if (
                form.dataset.recentOtp !== "true" &&
                policyIsWeaker() &&
                reauthBlock &&
                reauthBlock.hasAttribute("hidden")
            ) {
                event.preventDefault();
                syncReauthPrompt(true);
                if (passwordInput) passwordInput.focus();
            }
        });

        syncEnabled();
        syncReauthPrompt(form.dataset.forceReauth === "true");
        highlightPresets(daysInput ? daysInput.value : "");
    };

    document
        .querySelectorAll("[data-login-security-form]")
        .forEach((form) => initForm(form));
})();
