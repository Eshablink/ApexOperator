(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Keep this layer additive: it never replaces application event handlers.
  const scrollSignal = document.createElement("div");
  scrollSignal.className = "ao-scroll-signal";
  scrollSignal.setAttribute("aria-hidden", "true");
  document.body.appendChild(scrollSignal);

  const updateScroll = () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const progress = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    scrollSignal.style.transform = `scaleY(${progress})`;
  };
  updateScroll();
  window.addEventListener("scroll", updateScroll, { passive: true });
  window.addEventListener("resize", updateScroll, { passive: true });

  if (reduceMotion) return;

  // Pointer spotlight adds depth on desktop without affecting clicks or layout.
  const finePointer = window.matchMedia("(pointer: fine)").matches;
  if (finePointer) {
    const glow = document.createElement("div");
    glow.className = "ao-pointer-glow";
    glow.setAttribute("aria-hidden", "true");
    document.body.appendChild(glow);

    let raf = 0;
    let x = window.innerWidth / 2;
    let y = window.innerHeight / 2;
    let visible = false;

    const paint = () => {
      raf = 0;
      glow.style.left = `${x}px`;
      glow.style.top = `${y}px`;
    };
    window.addEventListener("pointermove", (event) => {
      x = event.clientX;
      y = event.clientY;
      if (!visible) {
        visible = true;
        glow.style.opacity = "1";
      }
      if (!raf) raf = requestAnimationFrame(paint);
    }, { passive: true });
    window.addEventListener("pointerleave", () => {
      visible = false;
      glow.style.opacity = "0";
    }, { passive: true });
  }

  // Reveal major sections once; no dependency on the app's existing state.
  const candidates = [
    ".metric-strip",
    ".architecture",
    ".controls-section",
    ".console-preview"
  ];
  const revealTargets = candidates
    .flatMap((selector) => [...document.querySelectorAll(selector)])
    .filter((node) => !node.classList.contains("ao-reveal"));

  revealTargets.forEach((node, index) => {
    node.classList.add("ao-reveal");
    node.style.transitionDelay = `${Math.min(index * 70, 210)}ms`;
  });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries, instance) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("ao-visible");
        instance.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    revealTargets.forEach((node) => observer.observe(node));
  } else {
    revealTargets.forEach((node) => node.classList.add("ao-visible"));
  }

  // Lightweight magnetic/parallax feel for the hero visual.
  const hero = document.querySelector(".hero");
  const visual = document.querySelector(".hero-visual");
  if (hero && visual && finePointer) {
    let raf = 0;
    const move = (event) => {
      const rect = hero.getBoundingClientRect();
      const dx = (event.clientX - (rect.left + rect.width / 2)) / rect.width;
      const dy = (event.clientY - (rect.top + rect.height / 2)) / rect.height;
      visual.style.setProperty("--ao-px", `${Math.max(-1, Math.min(1, dx)) * 8}px`);
      visual.style.setProperty("--ao-py", `${Math.max(-1, Math.min(1, dy)) * 6}px`);
      if (!raf) {
        raf = requestAnimationFrame(() => {
          raf = 0;
          visual.style.transform = "translate3d(var(--ao-px,0),var(--ao-py,0),0)";
        });
      }
    };
    hero.addEventListener("pointermove", move, { passive: true });
    hero.addEventListener("pointerleave", () => {
      visual.style.transform = "";
    }, { passive: true });
  }

  // Apply only to decorative preview cards; core console interactions remain untouched.
  document.querySelectorAll(".control-card,.arch-node,.kpi").forEach((node) => {
    node.addEventListener("pointerenter", () => node.classList.add("ao-tilt"), { passive: true });
  });
})();