"use strict";

const navToggle = document.querySelector(".nav-toggle");
const siteNav = document.querySelector(".site-nav");
const navLinks = [...document.querySelectorAll(".site-nav a[href^='#']")];
const year = document.getElementById("year");
const topbar = document.querySelector(".topbar");
const heroPortrait = document.querySelector(".hero-portrait");

if (year) {
  year.textContent = new Date().getFullYear();
}

if (navToggle && siteNav) {
  navToggle.addEventListener("click", () => {
    const isOpen = siteNav.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
    document.body.classList.toggle("menu-open", isOpen);
  });

  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      siteNav.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
      document.body.classList.remove("menu-open");
    });
  });
}

const revealTargets = [
  ...document.querySelectorAll(
    ".about-panel, .stack-panel, .work-section, .experience-section, .credentials-panel, .cta-section, .project-card, .stack-grid > div, .credential-grid > div"
  ),
];

revealTargets.forEach((item, index) => {
  item.classList.add("motion-reveal");
  item.style.setProperty("--delay", `${Math.min((index % 6) * 70, 350)}ms`);
});

const revealObserver = new IntersectionObserver(
  (entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("motion-visible");
      observer.unobserve(entry.target);
    });
  },
  { threshold: 0.13, rootMargin: "0px 0px -60px 0px" }
);

revealTargets.forEach((item) => revealObserver.observe(item));

const sections = [...document.querySelectorAll("main section[id]")];

const sectionObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;

      navLinks.forEach((link) => {
        const target = link.getAttribute("href");
        link.classList.toggle("active", target === "#" + entry.target.id);
      });
    });
  },
  { threshold: 0.35, rootMargin: "-15% 0px -55% 0px" }
);

sections.forEach((section) => sectionObserver.observe(section));

window.addEventListener(
  "scroll",
  () => {
    if (topbar) {
      topbar.classList.toggle("is-scrolled", window.scrollY > 24);
    }
  },
  { passive: true }
);

const canHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (canHover && !reduceMotion) {
  document.querySelectorAll(".project-card").forEach((card) => {
    card.addEventListener("mousemove", (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;

      card.style.setProperty("--ry", `${x * 4.5}deg`);
      card.style.setProperty("--rx", `${-y * 4.5}deg`);
    });

    card.addEventListener("mouseleave", () => {
      card.style.setProperty("--ry", "0deg");
      card.style.setProperty("--rx", "0deg");
    });
  });

  if (heroPortrait) {
    heroPortrait.addEventListener("mousemove", (event) => {
      const rect = heroPortrait.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;

      heroPortrait.style.setProperty("--hero-ry", `${x * 4}deg`);
      heroPortrait.style.setProperty("--hero-rx", `${-y * 4}deg`);
    });

    heroPortrait.addEventListener("mouseleave", () => {
      heroPortrait.style.setProperty("--hero-ry", "0deg");
      heroPortrait.style.setProperty("--hero-rx", "0deg");
    });
  }
}
