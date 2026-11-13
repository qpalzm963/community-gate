import { createRouter, createWebHistory } from 'vue-router'
import LoginView from './views/LoginView.vue'
import MonitorView from './views/MonitorView.vue'
import HouseholdsView from './views/HouseholdsView.vue'
import VisitorsView from './views/VisitorsView.vue'
import BlacklistView from './views/BlacklistView.vue'
import EventsView from './views/EventsView.vue'
import AlertsView from './views/AlertsView.vue'
import SettingsView from './views/SettingsView.vue'
import MobileCamView from './views/MobileCamView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true, standalone: true } },
    { path: '/mobile-cam', name: 'mobile-cam', component: MobileCamView, meta: { public: true, standalone: true } },
    { path: '/', name: 'monitor', component: MonitorView },
    { path: '/households', name: 'households', component: HouseholdsView },
    { path: '/visitors', name: 'visitors', component: VisitorsView },
    { path: '/blacklist', name: 'blacklist', component: BlacklistView },
    { path: '/events', name: 'events', component: EventsView },
    { path: '/alerts', name: 'alerts', component: AlertsView },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})
