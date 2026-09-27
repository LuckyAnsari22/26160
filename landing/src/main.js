import './styles.css';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { DASHBOARD_URL, GITHUB_URL, TEAM_NAME } from './config.js';
import { env } from './lib/env.js';
import { initHero } from './sections/hero/hero.js';
import { initProblem } from './sections/problem/problem.js';
import { initHow } from './sections/how/how.js';
import { initAnatomy } from './sections/anatomy/anatomy.js';

gsap.registerPlugin(ScrollTrigger);

// Links and names from config.js. Dashboard links already say href="/app/" in
// the markup (same origin); this only changes them for standalone `npm run dev`.
document.querySelectorAll('[data-dashboard-link]').forEach((a) => a.setAttribute('href', DASHBOARD_URL));
document.querySelectorAll('[data-github-link]').forEach((a) => (a.href = GITHUB_URL));
document.querySelectorAll('[data-team-name]').forEach((el) => (el.textContent = TEAM_NAME));
// Browser-frame caption in the demo section: where the dashboard really lives.
document.querySelectorAll('[data-dashboard-host]').forEach((el) => {
  const url = new URL(DASHBOARD_URL, location.href);
  el.textContent = `${url.host}${url.pathname.replace(/\/$/, '')}`;
});

// Header: transparent over the hero, solid once content scrolls beneath it.
const header = document.querySelector('header');
const onScroll = () => header.classList.toggle('is-solid', scrollY > innerHeight * 0.6);
addEventListener('scroll', onScroll, { passive: true });
onScroll();

initHero(env);
initProblem(env);
initHow(env);
initAnatomy(env);
