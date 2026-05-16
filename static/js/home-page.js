document.addEventListener('DOMContentLoaded', function () {
    const heroImage = document.querySelector('.hero-image');
    if (heroImage) {
        window.requestAnimationFrame(() => heroImage.classList.add('visible'));
    }

    const cards = Array.from(document.querySelectorAll('.showcase-card'));
    if ('IntersectionObserver' in window && cards.length) {
        const observer = new IntersectionObserver((entries, obs) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) {
                    return;
                }

                const card = entry.target;
                const index = Number(card.dataset.index || 0);
                const delay = Math.min(index * 120, 360);

                window.setTimeout(() => {
                    card.classList.add('in-view');
                }, delay);

                obs.unobserve(card);
            });
        }, {
            threshold: 0.18,
        });

        cards.forEach((card) => observer.observe(card));
    } else {
        cards.forEach((card) => card.classList.add('in-view'));
    }

    const parallaxTarget = document.querySelector('.hero-figure');
    let latestScroll = 0;
    let ticking = false;

    function updateParallax() {
        if (!parallaxTarget) {
            ticking = false;
            return;
        }

        const transformY = latestScroll * 0.08;
        parallaxTarget.style.transform = `translateY(${transformY}px)`;
        ticking = false;
    }

    if (parallaxTarget) {
        window.addEventListener('scroll', () => {
            latestScroll = window.scrollY;
            if (!ticking) {
                window.requestAnimationFrame(updateParallax);
                ticking = true;
            }
        });
    }
});
