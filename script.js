/* Small progressive enhancements: navigation, section reveals, and scroll state. */

const header = document.querySelector("[data-header]");
const menuToggle = document.querySelector(".menu-toggle");
const navigation = document.querySelector("#nav-list");
const navLinks = [...document.querySelectorAll("[data-nav-link]")];
const sections = [...document.querySelectorAll("main section[id]:not(#top)")];
const revealItems = [...document.querySelectorAll(".reveal")];
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

/** Keep the mobile menu's visual and accessibility states in sync. */
function setMenuOpen(isOpen) {
  if (!menuToggle || !navigation) return;

  menuToggle.setAttribute("aria-expanded", String(isOpen));
  navigation.classList.toggle("is-open", isOpen);
  document.body.classList.toggle("menu-open", isOpen);

  const menuLabel = menuToggle.querySelector(".menu-label");
  if (menuLabel) menuLabel.textContent = isOpen ? "Close" : "Menu";
}

if (menuToggle && navigation) {
  menuToggle.addEventListener("click", () => {
    const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
    setMenuOpen(!isOpen);
  });

  navLinks.forEach((link) => {
    link.addEventListener("click", () => setMenuOpen(false));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setMenuOpen(false);
      menuToggle.focus();
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 704) setMenuOpen(false);
  });
}

/** Update the compact header and the slim page-progress indicator together. */
let scrollFrameRequested = false;

function updateScrollState() {
  const scrollableHeight = document.documentElement.scrollHeight - window.innerHeight;
  const progress = scrollableHeight > 0 ? window.scrollY / scrollableHeight : 0;

  header?.classList.toggle("is-scrolled", window.scrollY > 24);
  document.documentElement.style.setProperty(
    "--scroll-progress",
    String(Math.min(Math.max(progress, 0), 1))
  );
  scrollFrameRequested = false;
}

window.addEventListener(
  "scroll",
  () => {
    if (!scrollFrameRequested) {
      window.requestAnimationFrame(updateScrollState);
      scrollFrameRequested = true;
    }
  },
  { passive: true }
);

updateScrollState();

/** Reveal content once as it enters the viewport; show it immediately if unsupported. */
if ("IntersectionObserver" in window && !prefersReducedMotion.matches) {
  document.documentElement.classList.add("is-reveal-ready");

  const revealObserver = new IntersectionObserver(
    (entries, observer) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { rootMargin: "0px 0px -8%", threshold: 0.08 }
  );

  revealItems.forEach((item) => revealObserver.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add("is-visible"));
}

/** Mark the navigation link for the section occupying the middle of the screen. */
if ("IntersectionObserver" in window) {
  const sectionObserver = new IntersectionObserver(
    (entries) => {
      const visibleEntry = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

      if (!visibleEntry) return;

      navLinks.forEach((link) => {
        const isCurrent = link.getAttribute("href") === `#${visibleEntry.target.id}`;
        if (isCurrent) {
          link.setAttribute("aria-current", "true");
        } else {
          link.removeAttribute("aria-current");
        }
      });
    },
    { rootMargin: "-35% 0px -50%", threshold: [0, 0.1, 0.5] }
  );

  sections.forEach((section) => sectionObserver.observe(section));
}
