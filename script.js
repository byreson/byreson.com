/* Optional progressive enhancement for the responsive navigation. */

const menuToggle = document.querySelector(".menu-toggle");
const navigation = document.querySelector("#nav-list");
const navLinks = [...document.querySelectorAll("[data-nav-link]")];

function setMenuOpen(isOpen, returnFocus = false) {
  if (!menuToggle || !navigation) return;

  menuToggle.setAttribute("aria-expanded", String(isOpen));
  navigation.classList.toggle("is-open", isOpen);
  document.body.classList.toggle("menu-open", isOpen);

  const menuLabel = menuToggle.querySelector(".menu-label");
  if (menuLabel) menuLabel.textContent = isOpen ? "Close" : "Menu";

  if (isOpen) navLinks[0]?.focus();
  else if (returnFocus) menuToggle.focus();
}

if (menuToggle && navigation) {
  menuToggle.addEventListener("click", () => {
    setMenuOpen(menuToggle.getAttribute("aria-expanded") !== "true");
  });

  navLinks.forEach((link) => link.addEventListener("click", () => setMenuOpen(false)));

  document.addEventListener("keydown", (event) => {
    const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
    if (!isOpen) return;

    if (event.key === "Escape") {
      setMenuOpen(false, true);
      return;
    }

    if (event.key === "Tab") {
      const focusableItems = [...navLinks, menuToggle].filter(Boolean);
      const firstItem = focusableItems[0];
      const lastItem = focusableItems[focusableItems.length - 1];

      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 704) setMenuOpen(false);
  });
}
