const root = document.documentElement;
const body = document.body;
const drawer = document.querySelector("[data-drawer]");
const drawerTriggers = document.querySelectorAll("[data-open-drawer]");
const drawerClose = document.querySelectorAll("[data-close-drawer]");
const sidebarTriggers = document.querySelectorAll("[data-open-sidebar]");
const sidebarClose = document.querySelectorAll("[data-close-sidebar]");
const themeButtons = document.querySelectorAll("[data-theme-value]");

const setTheme = (theme) => {
  root.setAttribute("data-theme", theme);
  localStorage.setItem("expense-tracker-theme", theme);
  themeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.themeValue === theme);
  });
};

const savedTheme = localStorage.getItem("expense-tracker-theme");
if (savedTheme) {
  setTheme(savedTheme);
}

drawerTriggers.forEach((button) => {
  button.addEventListener("click", () => {
    body.classList.add("drawer-open");
    if (drawer) {
      const firstField = drawer.querySelector("input, select");
      if (firstField) {
        setTimeout(() => firstField.focus(), 80);
      }
    }
  });
});

drawerClose.forEach((button) => {
  button.addEventListener("click", () => body.classList.remove("drawer-open"));
});

sidebarTriggers.forEach((button) => {
  button.addEventListener("click", () => body.classList.add("sidebar-open"));
});

sidebarClose.forEach((button) => {
  button.addEventListener("click", () => body.classList.remove("sidebar-open"));
});

themeButtons.forEach((button) => {
  button.addEventListener("click", () => setTheme(button.dataset.themeValue));
});

